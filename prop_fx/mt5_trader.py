"""Run a prop_fx strategy live on MetaTrader 5 with FTMO guardrails.

Requires Windows (or Wine) with the MT5 terminal installed and logged in, plus
`pip install MetaTrader5`. Configuration is read from environment / .env:

    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER   account credentials (e.g. FTMO-Demo)
    MT5_PATH                              optional path to terminal64.exe
    FX_STRATEGY=fx_trend                  strategy module in prop_fx/strategies
    FX_SYMBOL_SUFFIX=                     broker symbol suffix, e.g. ".r" (FTMO: none)
    CHALLENGE_BALANCE=100000              the account's INITIAL balance
    PHASE_TARGET_PCT=10                   10 for phase 1, 5 for phase 2, 0 when funded
    DAILY_GUARD_PCT=4.0                   flatten + halt for the day at this daily loss
    MAX_GUARD_PCT=9.0                     flatten + halt for good at this total loss
    DRY_RUN=true                          log orders instead of sending them

    python -m prop_fx.mt5_trader --check   # verify the connection and exit
    python -m prop_fx.mt5_trader           # trade

The guard limits sit inside FTMO's 5% daily / 10% max loss so that slippage on
the way out can't breach the real limits. Stops and targets are placed on the
broker's server with each order, so they still work if this script dies.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from t212_agent.config import _load_dotenv

from . import strategies
from .instruments import PAIRS

log = logging.getLogger("prop_fx.mt5")
PRAGUE = ZoneInfo("Europe/Prague")
MAGIC = 212_500
STATE_FILE = Path("mt5_state.json")


@dataclass
class TraderConfig:
    strategy: str = "donchian"
    symbol_suffix: str = ""
    initial_balance: float = 100_000.0
    phase_target_pct: float = 10.0
    daily_guard_pct: float = 4.0
    max_guard_pct: float = 9.0
    dry_run: bool = True
    bars: int = 3000  # hourly history fed to the strategy (walk-forward needs ~12+ weeks)
    log_file: str = "mt5_trades.jsonl"

    @classmethod
    def from_env(cls) -> "TraderConfig":
        _load_dotenv()
        env = os.getenv
        return cls(
            strategy=env("FX_STRATEGY", cls.strategy),
            symbol_suffix=env("FX_SYMBOL_SUFFIX", ""),
            initial_balance=float(env("CHALLENGE_BALANCE", cls.initial_balance)),
            phase_target_pct=float(env("PHASE_TARGET_PCT", cls.phase_target_pct)),
            daily_guard_pct=float(env("DAILY_GUARD_PCT", cls.daily_guard_pct)),
            max_guard_pct=float(env("MAX_GUARD_PCT", cls.max_guard_pct)),
            dry_run=env("DRY_RUN", "true").lower() in {"1", "true", "yes"},
        )


class MT5Trader:
    def __init__(self, cfg: TraderConfig, mt5, strategy=None, now_fn=None) -> None:
        self.cfg = cfg
        self.mt5 = mt5
        self.strategy = strategy or strategies.load(cfg.strategy)
        self.now = now_fn or (lambda: datetime.now(timezone.utc))
        self.pairs = [p for p in PAIRS if self.strategy.pairs is None or p in self.strategy.pairs]
        self.state = {"day": None, "day_start_balance": None, "halted_day": None,
                      "halted_for_good": False, "last_bar": {}}
        if STATE_FILE.exists():
            self.state.update(json.loads(STATE_FILE.read_text()))

    # ---------------------------------------------------------------- helpers
    def sym(self, pair: str) -> str:
        return pair + self.cfg.symbol_suffix

    def _save(self) -> None:
        STATE_FILE.write_text(json.dumps(self.state, indent=2))

    def _journal(self, event: str, **fields) -> None:
        rec = {"ts": self.now().isoformat(), "event": event, **fields}
        with open(self.cfg.log_file, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        log.info("%s %s", event, fields)

    def server_offset(self, pair: str) -> timedelta:
        """MT5 bar times are in broker server time; find its offset from UTC."""
        tick = self.mt5.symbol_info_tick(self.sym(pair))
        hours = round((tick.time - self.now().timestamp()) / 3600)
        return timedelta(hours=hours)

    def closed_bars(self, pair: str) -> pd.DataFrame:
        rates = self.mt5.copy_rates_from_pos(self.sym(pair), self.mt5.TIMEFRAME_H1, 0,
                                             self.cfg.bars + 1)
        if rates is None or len(rates) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        offset = self.server_offset(pair)
        df.index = pd.to_datetime(df["time"], unit="s", utc=True) - offset
        df = df[["open", "high", "low", "close"]].astype(float)
        return df.iloc[:-1]  # drop the bar still forming

    def my_positions(self) -> dict[str, object]:
        out = {}
        for p in self.mt5.positions_get() or []:
            if p.magic == MAGIC:
                pair = p.symbol[: 6]
                out[pair] = p
        return out

    def lots_for(self, pair: str, stop_dist: float) -> float:
        info = self.mt5.symbol_info(self.sym(pair))
        value_per_price = info.trade_tick_value / info.trade_tick_size  # per 1 lot
        risk = self.strategy.risk_pct / 100 * self.cfg.initial_balance
        lots = risk / (stop_dist * value_per_price)
        step = info.volume_step
        lots = math.floor(lots / step) * step
        return round(min(lots, info.volume_max), 2) if lots >= info.volume_min else 0.0

    def _filling(self, pair: str) -> int:
        mode = self.mt5.symbol_info(self.sym(pair)).filling_mode
        if mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        if mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def _send(self, request: dict) -> bool:
        if self.cfg.dry_run:
            self._journal("dry_run_order", **request)
            return True
        result = self.mt5.order_send(request)
        ok = result is not None and result.retcode == self.mt5.TRADE_RETCODE_DONE
        self._journal("order" if ok else "order_failed", request=request,
                      retcode=getattr(result, "retcode", None),
                      comment=getattr(result, "comment", None))
        return ok

    def open(self, pair: str, side: int, stop_dist: float, target_dist: float) -> None:
        lots = self.lots_for(pair, stop_dist)
        if lots <= 0:
            self._journal("skip_size_zero", pair=pair)
            return
        tick = self.mt5.symbol_info_tick(self.sym(pair))
        price = tick.ask if side > 0 else tick.bid
        digits = self.mt5.symbol_info(self.sym(pair)).digits
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": self.sym(pair),
            "volume": lots,
            "type": self.mt5.ORDER_TYPE_BUY if side > 0 else self.mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": round(price - side * stop_dist, digits),
            "tp": round(price + side * target_dist, digits)
            if target_dist and math.isfinite(target_dist) and target_dist > 0 else 0.0,
            "deviation": 10,
            "magic": MAGIC,
            "comment": self.strategy.name[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self._filling(pair),
        }
        self._send(req)

    def close(self, position, reason: str) -> None:
        pair = position.symbol[:6]
        tick = self.mt5.symbol_info_tick(position.symbol)
        is_long = position.type == self.mt5.POSITION_TYPE_BUY
        req = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": self.mt5.ORDER_TYPE_SELL if is_long else self.mt5.ORDER_TYPE_BUY,
            "position": position.ticket,
            "price": tick.bid if is_long else tick.ask,
            "deviation": 20,
            "magic": MAGIC,
            "comment": reason[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self._filling(pair),
        }
        self._journal("close", pair=pair, reason=reason, profit=position.profit)
        self._send(req)

    def close_all(self, reason: str) -> None:
        for pos in self.my_positions().values():
            self.close(pos, reason)

    # ----------------------------------------------------------------- guard
    def guard(self) -> bool:
        """Enforce FTMO limits. Returns True when new trades are allowed."""
        acct = self.mt5.account_info()
        now = self.now()
        day = now.astimezone(PRAGUE).date().isoformat()
        if self.state["day"] != day:
            self.state.update(day=day, day_start_balance=acct.balance)
            self._journal("new_day", balance=acct.balance, equity=acct.equity)
        b0 = self.cfg.initial_balance
        if self.state["halted_for_good"]:
            return False
        if acct.equity <= b0 * (1 - self.cfg.max_guard_pct / 100):
            self.close_all("max loss guard")
            self.state["halted_for_good"] = True
            self._journal("halt_max_loss", equity=acct.equity)
            return False
        daily_floor = self.state["day_start_balance"] - self.cfg.daily_guard_pct / 100 * b0
        strat_floor = (self.state["day_start_balance"] - self.strategy.daily_stop_pct / 100 * b0
                       if self.strategy.daily_stop_pct else -math.inf)
        if self.state["halted_day"] == day:
            return False
        if acct.equity <= max(daily_floor, strat_floor):
            self.close_all("daily loss guard")
            self.state["halted_day"] = day
            self._journal("halt_day", equity=acct.equity, floor=max(daily_floor, strat_floor))
            return False
        if self.cfg.phase_target_pct and acct.balance >= b0 * (1 + self.cfg.phase_target_pct / 100):
            if not self.my_positions():
                self._journal("target_reached", balance=acct.balance)
                return False
        nxt = now + timedelta(minutes=5)
        if (nxt.weekday() == 4 and nxt.hour >= 20) or nxt.weekday() >= 5:
            self.close_all("weekend")
            return False
        return not (nxt.weekday() == 4 and nxt.hour >= 16)

    # ------------------------------------------------------------------ loop
    def on_bar(self) -> None:
        allowed = self.guard()
        self._save()
        positions = self.my_positions()
        if not allowed:
            return
        decisions = []
        for pair in self.pairs:
            df = self.closed_bars(pair)
            if df.empty:
                continue
            bar_time = str(df.index[-1])
            if self.state["last_bar"].get(pair) == bar_time:
                continue  # already acted on this bar
            self.state["last_bar"][pair] = bar_time
            row = self.strategy.prepare(df, pair).iloc[-1]
            pos = positions.get(pair)
            if pos is not None and bool(row["exit"]):
                self.close(pos, "strategy exit")
                pos = None
            side = int(row["entry"]) if pd.notna(row["entry"]) else 0
            if side and row["stop_dist"] > 0:
                if pos is not None:
                    is_long = pos.type == self.mt5.POSITION_TYPE_BUY
                    if (side > 0) == is_long:
                        continue
                    self.close(pos, "reverse")
                    positions.pop(pair, None)
                score = row["score"] if pd.notna(row["score"]) else -math.inf
                decisions.append((score, pair, side, row["stop_dist"], row["target_dist"]))
        slots = self.strategy.max_positions - len(self.my_positions())
        for _, pair, side, sd, td in sorted(decisions, reverse=True)[: max(slots, 0)]:
            self.open(pair, side, float(sd), float(td))
        self._save()

    def run(self, poll_seconds: int = 20) -> None:
        log.info("Trading %s on %s pairs (%s)", self.strategy.name, len(self.pairs),
                 "DRY RUN" if self.cfg.dry_run else "LIVE ORDERS")
        last_hour = None
        while True:
            now = self.now()
            # Act once per hour, a few seconds after the hourly bar closes.
            if now.minute == 0 and now.second >= 5 and last_hour != now.replace(
                    minute=0, second=0, microsecond=0):
                last_hour = now.replace(minute=0, second=0, microsecond=0)
                try:
                    self.on_bar()
                except Exception:  # keep the guard loop alive
                    log.exception("on_bar failed")
            else:
                try:
                    self.guard()  # equity guard runs between bars too
                    self._save()
                except Exception:
                    log.exception("guard failed")
            time.sleep(poll_seconds)


def connect(mt5) -> None:
    kwargs = {}
    if os.getenv("MT5_PATH"):
        kwargs["path"] = os.getenv("MT5_PATH")
    if os.getenv("MT5_LOGIN"):
        kwargs.update(login=int(os.getenv("MT5_LOGIN")), password=os.getenv("MT5_PASSWORD", ""),
                      server=os.getenv("MT5_SERVER", ""))
    if not mt5.initialize(**kwargs):
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")


def main() -> None:
    p = argparse.ArgumentParser(description="Run a prop_fx strategy on MetaTrader 5")
    p.add_argument("--check", action="store_true", help="verify connection and exit")
    p.add_argument("--flatten", action="store_true", help="close this bot's positions and exit")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise SystemExit("pip install MetaTrader5 (Windows only; MT5 terminal must be installed)")
    cfg = TraderConfig.from_env()
    connect(mt5)
    trader = MT5Trader(cfg, mt5)
    if args.check:
        a = mt5.account_info()
        print(f"Connected: {a.login} on {a.server}, balance {a.balance} {a.currency}, "
              f"equity {a.equity}, leverage 1:{a.leverage}")
        for pair in trader.pairs:
            info = mt5.symbol_info(trader.sym(pair))
            print(f"  {trader.sym(pair)}: {'ok' if info else 'NOT FOUND (check FX_SYMBOL_SUFFIX)'}")
        return
    if args.flatten:
        trader.close_all("manual flatten")
        return
    trader.run()


if __name__ == "__main__":
    main()
