"""Main trading loop.

The agent only manages positions it opened itself (tracked in a state file), so
existing long-term holdings in the same account are never touched.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import data
from .config import Config, load_config
from .risk import RiskManager
from .strategy import Action, evaluate
from .t212_client import T212Error, Trading212Client

log = logging.getLogger("t212_agent")

STATE_FILE = Path("agent_state.json")


@dataclass
class ManagedPosition:
    ticker: str
    quantity: float
    entry_price: float
    stop: float
    target: float
    opened_at: str


class Agent:
    def __init__(self, cfg: Config, client: Trading212Client, bars_fn=data.get_bars) -> None:
        self.cfg = cfg
        self.client = client
        self.bars_fn = bars_fn
        self.tz = ZoneInfo(cfg.timezone)
        self.risk = RiskManager(
            cfg.risk_per_trade_pct,
            cfg.max_position_pct,
            cfg.max_open_positions,
            cfg.max_daily_loss_pct,
            cfg.max_trades_per_day,
        )
        self.positions: dict[str, ManagedPosition] = {}
        self.trading_day: date | None = None
        self.halted_reason = ""
        self._load_state()

    # ----------------------------------------------------------- persistence
    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            return
        raw = json.loads(STATE_FILE.read_text())
        self.positions = {t: ManagedPosition(**p) for t, p in raw.get("positions", {}).items()}
        if raw.get("trading_day"):
            self.trading_day = date.fromisoformat(raw["trading_day"])
            self.risk.start_of_day_value = raw.get("start_of_day_value")
            self.risk.trades_today = raw.get("trades_today", 0)

    def _save_state(self) -> None:
        STATE_FILE.write_text(
            json.dumps(
                {
                    "positions": {t: asdict(p) for t, p in self.positions.items()},
                    "trading_day": self.trading_day.isoformat() if self.trading_day else None,
                    "start_of_day_value": self.risk.start_of_day_value,
                    "trades_today": self.risk.trades_today,
                },
                indent=2,
            )
        )

    def _journal(self, event: str, **fields) -> None:
        record = {"ts": datetime.now(self.tz).isoformat(), "event": event, **fields}
        with open(self.cfg.log_file, "a") as fh:
            fh.write(json.dumps(record) + "\n")
        log.info("%s %s", event, fields)

    # --------------------------------------------------------------- session
    def _session_times(self, now: datetime) -> tuple[datetime, datetime]:
        def at(hhmm: str) -> datetime:
            h, m = map(int, hhmm.split(":"))
            return now.replace(hour=h, minute=m, second=0, microsecond=0)

        return at(self.cfg.session_open), at(self.cfg.session_close)

    def market_open(self, now: datetime) -> bool:
        if now.weekday() >= 5:
            return False
        open_, close = self._session_times(now)
        return open_ <= now < close

    def can_enter(self, now: datetime) -> bool:
        open_, close = self._session_times(now)
        return (
            now >= open_ + timedelta(minutes=self.cfg.skip_first_minutes)
            and now < close - timedelta(minutes=self.cfg.no_new_entries_minutes_before_close)
        )

    def must_flatten(self, now: datetime) -> bool:
        _, close = self._session_times(now)
        return now >= close - timedelta(minutes=self.cfg.flatten_minutes_before_close)

    # --------------------------------------------------------------- account
    def account_value(self) -> tuple[float, float]:
        """Return (total account value, free cash)."""
        cash = self.client.account_cash()
        total, free = float(cash.get("total", 0)), float(cash.get("free", 0))
        if self.client.dry_run:
            # Orders aren't really placed, so simulate their effect on cash and P&L.
            for p in self.positions.values():
                free -= p.entry_price * p.quantity
                bars = self.bars_fn(self.cfg.symbols[p.ticker], self.cfg.bar_interval, "1d")
                if not bars.empty:
                    total += (float(bars["close"].iloc[-1]) - p.entry_price) * p.quantity
        return total, free

    def _reconcile(self) -> None:
        """Drop managed positions the broker no longer holds (e.g. closed manually)."""
        if self.client.dry_run or not self.positions:
            return
        held = {p["ticker"]: float(p["quantity"]) for p in self.client.positions()}
        for ticker in list(self.positions):
            if held.get(ticker, 0) <= 0:
                self._journal("position_missing_at_broker", ticker=ticker)
                del self.positions[ticker]
            else:
                # Never try to sell more than the broker says we have.
                self.positions[ticker].quantity = min(self.positions[ticker].quantity, held[ticker])

    # --------------------------------------------------------------- trading
    def _buy(self, ticker: str, price: float, atr: float, account: float, free: float, reason: str):
        stop = price - self.cfg.stop_atr_mult * atr
        target = price + self.cfg.target_atr_mult * atr
        qty = self.risk.size(account, free, price, stop)
        if qty <= 0:
            log.info("Skip %s: size is zero", ticker)
            return
        order = self.client.market_order(ticker, qty)
        self.positions[ticker] = ManagedPosition(
            ticker, qty, price, round(stop, 4), round(target, 4), datetime.now(self.tz).isoformat()
        )
        self.risk.trades_today += 1
        self._journal("buy", ticker=ticker, qty=qty, price=price, stop=stop, target=target,
                      reason=reason, order_id=order.get("id"))

    def _sell(self, ticker: str, price: float, reason: str) -> None:
        pos = self.positions[ticker]
        order = self.client.market_order(ticker, -pos.quantity)
        pnl = (price - pos.entry_price) * pos.quantity
        self._journal("sell", ticker=ticker, qty=pos.quantity, price=price,
                      pnl=round(pnl, 2), reason=reason, order_id=order.get("id"))
        del self.positions[ticker]

    def flatten_all(self, reason: str) -> None:
        for ticker in list(self.positions):
            bars = self.bars_fn(self.cfg.symbols[ticker], self.cfg.bar_interval, "1d")
            price = float(bars["close"].iloc[-1]) if not bars.empty else self.positions[ticker].entry_price
            try:
                self._sell(ticker, price, reason)
            except T212Error as exc:
                log.error("Failed to flatten %s: %s", ticker, exc)
        self._save_state()

    def step(self, now: datetime | None = None) -> None:
        now = now or datetime.now(self.tz)
        if not self.market_open(now):
            return

        if self.trading_day != now.date():
            self.trading_day = now.date()
            self.risk.reset_day(self.account_value()[0])
            self.halted_reason = ""
            self._journal("new_day", start_value=self.risk.start_of_day_value)

        self._reconcile()

        if self.must_flatten(now):
            if self.positions:
                self.flatten_all("end of day")
            return

        account, free = self.account_value()
        if self.risk.daily_loss_hit(account) and not self.halted_reason:
            self.halted_reason = "daily loss limit"
            self._journal("halt", reason=self.halted_reason, account=account)
            self.flatten_all("daily loss limit")
            return

        for ticker, symbol in self.cfg.symbols.items():
            try:
                bars = self.bars_fn(symbol, self.cfg.bar_interval, "5d")
            except Exception as exc:  # data provider hiccups shouldn't kill the loop
                log.warning("Data error for %s: %s", symbol, exc)
                continue
            if bars.empty:
                continue
            # Drop the still-forming bar so signals use closed candles only.
            closed = bars.iloc[:-1]
            live_price = float(bars["close"].iloc[-1])
            pos = self.positions.get(ticker)

            if pos:
                if live_price <= pos.stop:
                    self._sell(ticker, live_price, f"stop loss {pos.stop}")
                    continue
                if live_price >= pos.target:
                    self._sell(ticker, live_price, f"take profit {pos.target}")
                    continue

            sig = evaluate(closed, self.cfg.fast_ema, self.cfg.slow_ema, self.cfg.atr_period,
                           in_position=pos is not None)
            if sig.action is Action.SELL and pos:
                self._sell(ticker, live_price, sig.reason)
            elif sig.action is Action.BUY and not pos and self.can_enter(now):
                ok, why = self.risk.can_open(len(self.positions), account)
                if not ok:
                    log.info("Skip %s buy: %s", ticker, why)
                    continue
                try:
                    self._buy(ticker, live_price, sig.atr, account, free, sig.reason)
                    account, free = self.account_value()
                except T212Error as exc:
                    log.error("Buy %s failed: %s", ticker, exc)

        self._save_state()

    def run(self) -> None:
        mode = "DRY RUN" if self.client.dry_run else "ORDERS ENABLED"
        log.info("Starting agent on %s (%s), symbols=%s", self.cfg.environment, mode,
                 list(self.cfg.symbols))
        try:
            while True:
                try:
                    self.step()
                except T212Error as exc:
                    log.error("API error: %s", exc)
                time.sleep(self.cfg.poll_seconds)
        except KeyboardInterrupt:
            log.info("Interrupted; flattening managed positions")
            self.flatten_all("shutdown")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trading 212 intraday agent")
    parser.add_argument("--check", action="store_true", help="verify credentials and exit")
    parser.add_argument("--flatten", action="store_true", help="close managed positions and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    cfg.validate()
    client = Trading212Client(cfg.base_url, cfg.api_key, cfg.api_secret, dry_run=cfg.dry_run)
    agent = Agent(cfg, client)

    if args.check:
        info = client.account_info()
        cash = client.account_cash()
        print(f"Connected to {cfg.environment}: account {info.get('id')} "
              f"({info.get('currencyCode')}), total={cash.get('total')} free={cash.get('free')}")
        return
    if args.flatten:
        agent.flatten_all("manual flatten")
        return
    agent.run()


if __name__ == "__main__":
    main()
