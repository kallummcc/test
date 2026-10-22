"""Event-driven backtester for the intraday strategy.

Reuses the live strategy signals and RiskManager, and mirrors the agent's
session rules (skip the open, no late entries, flatten before close, daily
loss limit). Execution model:

* Signals are computed on a closed bar and filled at the *next* bar's open.
* Stops / targets are checked intrabar against the bar's low / high. A gap
  through the level fills at the open. If both are touched in one bar the
  stop is assumed to hit first (conservative).
* Each fill pays `slippage_bps` and `fx_fee_pct` (Trading 212 charges 0.15%
  FX on instruments not in your account currency, e.g. US shares on a GBP
  account). There is no commission.

Usage:
    python -m t212_agent.backtest --source alpaca --start 2020-01-01
    python -m t212_agent.backtest --source csv --data-dir data
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .config import Config, load_config
from .risk import RiskManager
from .strategy import add_signals

log = logging.getLogger("t212_agent.backtest")

INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30}


# ---------------------------------------------------------------- data loading
def regular_session(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Keep bars that start inside the regular session, in exchange local time."""
    df = df.tz_convert(cfg.timezone) if df.index.tz else df.tz_localize(cfg.timezone)
    start = df.index.indexer_between_time(cfg.session_open, cfg.session_close,
                                          include_end=False)
    df = df.iloc[start]
    return df[df.index.dayofweek < 5]


def load_csv(path: Path) -> pd.DataFrame:
    """CSV with columns timestamp,open,high,low,close,volume (timestamps tz-aware or UTC)."""
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    ts_col = next(c for c in ("timestamp", "datetime", "date", "time", "t") if c in df.columns)
    df.index = pd.to_datetime(df.pop(ts_col), utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    return df[["open", "high", "low", "close", "volume"]].astype(float).sort_index()


def load_alpaca(symbol: str, start: str, end: str | None, interval: str,
                feed: str = "sip") -> pd.DataFrame:
    """Split/dividend-adjusted bars from Alpaca's market data API (free account works).

    Needs ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY.
    """
    key, secret = os.getenv("ALPACA_API_KEY_ID"), os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY (free at alpaca.markets)")
    # Free plans can't query SIP data from the last 15 minutes.
    end = end or (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "timeframe": f"{INTERVAL_MINUTES[interval]}Min",
        "start": start if "T" in start else f"{start}T00:00:00Z",
        "end": end if "T" in end else f"{end}T23:59:59Z",
        "limit": 10000,
        "adjustment": "all",
        "feed": feed,
    }
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    rows: list[dict] = []
    while True:
        resp = requests.get(f"https://data.alpaca.markets/v2/stocks/{symbol}/bars",
                            params=params, headers=headers, timeout=30)
        if resp.status_code == 429:
            time.sleep(3)
            continue
        resp.raise_for_status()
        payload = resp.json()
        rows.extend(payload.get("bars") or [])
        token = payload.get("next_page_token")
        log.info("%s: %d bars downloaded", symbol, len(rows))
        if not token:
            break
        params["page_token"] = token
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.pop("t"), utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def load_yahoo(symbol: str, interval: str) -> pd.DataFrame:
    """Yahoo only serves intraday bars for roughly the last 60 days."""
    from . import data

    return data.get_bars(symbol, interval, "60d")


def load_bars(symbol: str, args: argparse.Namespace, cfg: Config) -> pd.DataFrame:
    cache = Path(args.data_dir) / f"{symbol}_{cfg.bar_interval}.csv"
    if args.source == "csv":
        if not cache.exists():
            raise SystemExit(f"Missing {cache}")
        df = load_csv(cache)
    elif args.source == "alpaca":
        if cache.exists() and not args.refresh:
            df = load_csv(cache)
        else:
            df = load_alpaca(symbol, args.start, args.end, cfg.bar_interval, args.feed)
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.rename_axis("timestamp").to_csv(cache)
    else:
        df = load_yahoo(symbol, cfg.bar_interval)
    df = regular_session(df, cfg)
    start = pd.Timestamp(args.start, tz=cfg.timezone)
    df = df[df.index >= start]
    if args.end:
        df = df[df.index < pd.Timestamp(args.end, tz=cfg.timezone) + pd.Timedelta(days=1)]
    return df


# ------------------------------------------------------------------ simulation
@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_cost: float  # cash paid including fees
    stop: float
    target: float
    entry_time: pd.Timestamp


@dataclass
class Trade:
    symbol: str
    entry_time: str
    exit_time: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float
    reason: str


@dataclass
class BacktestResult:
    starting_balance: float
    equity: pd.Series
    trades: list[Trade] = field(default_factory=list)
    benchmark: pd.Series | None = None


class Backtester:
    def __init__(self, cfg: Config, starting_balance: float = 1000.0,
                 slippage_bps: float = 2.0, fx_fee_pct: float = 0.15) -> None:
        self.cfg = cfg
        self.balance0 = starting_balance
        self.cost_rate = slippage_bps / 10_000 + fx_fee_pct / 100
        self.bar_delta = pd.Timedelta(minutes=INTERVAL_MINUTES[cfg.bar_interval])

    def _session_marks(self, ts: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
        def at(hhmm: str) -> pd.Timestamp:
            h, m = map(int, hhmm.split(":"))
            return ts.normalize() + pd.Timedelta(hours=h, minutes=m)

        open_, close = at(self.cfg.session_open), at(self.cfg.session_close)
        entry_from = open_ + pd.Timedelta(minutes=self.cfg.skip_first_minutes)
        entry_until = close - pd.Timedelta(minutes=self.cfg.no_new_entries_minutes_before_close)
        flatten_at = close - pd.Timedelta(minutes=self.cfg.flatten_minutes_before_close)
        return entry_from, entry_until, flatten_at

    def run(self, bars: dict[str, pd.DataFrame]) -> BacktestResult:
        cfg = self.cfg
        frames = {
            s: add_signals(df, cfg.fast_ema, cfg.slow_ema, cfg.atr_period)
            for s, df in bars.items() if not df.empty
        }
        if not frames:
            raise ValueError("no bars to backtest")
        # One wide frame per field, aligned on the union of timestamps.
        timeline = sorted(set().union(*(df.index for df in frames.values())))
        cols = ["open", "high", "low", "close", "atr", "entry", "cross_down", "below_vwap"]
        panel = {c: pd.DataFrame({s: df[c] for s, df in frames.items()}).reindex(timeline)
                 for c in cols}
        arr = {c: panel[c].to_numpy(dtype=float) for c in cols}
        symbols = list(frames)
        times = pd.DatetimeIndex(timeline)
        days = times.normalize()

        risk = RiskManager(cfg.risk_per_trade_pct, cfg.max_position_pct, cfg.max_open_positions,
                           cfg.max_daily_loss_pct, cfg.max_trades_per_day)
        cash = self.balance0
        positions: dict[int, Position] = {}
        pending: dict[int, tuple[str, float, str]] = {}  # col -> (BUY/SELL, atr, reason)
        last_close = np.full(len(symbols), np.nan)
        trades: list[Trade] = []
        equity_vals: list[float] = []
        halted = False
        current_day = None
        marks = None

        def mark_to_market() -> float:
            return cash + sum(p.qty * last_close[j] * (1 - self.cost_rate)
                              for j, p in positions.items())

        def close_position(j: int, price: float, when: pd.Timestamp, reason: str) -> None:
            nonlocal cash
            p = positions.pop(j)
            proceeds = p.qty * price * (1 - self.cost_rate)
            cash += proceeds
            pnl = proceeds - p.entry_cost
            trades.append(Trade(symbols[j], str(p.entry_time), str(when), p.qty,
                                round(p.entry_price, 4), round(price, 4), round(pnl, 4),
                                round(pnl / p.entry_cost * 100, 3), reason))

        for i, ts in enumerate(times):
            if days[i] != current_day:
                # A position can only be left over if a day's data ended early.
                for j in list(positions):
                    close_position(j, last_close[j], times[i - 1], "end of data for day")
                pending.clear()
                current_day = days[i]
                marks = self._session_marks(ts)
                risk.reset_day(mark_to_market())
                halted = False
            entry_from, entry_until, flatten_at = marks
            decision_time = ts + self.bar_delta  # the bar has closed

            o, h, l, c = arr["open"][i], arr["high"][i], arr["low"][i], arr["close"][i]

            # 1) Fill orders decided on the previous bar at this bar's open.
            for j, (side, atr, reason) in list(pending.items()):
                if np.isnan(o[j]):
                    continue  # no bar for this symbol yet; keep the order pending
                del pending[j]
                price = o[j]
                if side == "SELL" and j in positions:
                    close_position(j, price, ts, reason)
                elif side == "BUY" and j not in positions:
                    stop = price - cfg.stop_atr_mult * atr
                    target = price + cfg.target_atr_mult * atr
                    eff_price = price * (1 + self.cost_rate)
                    qty = risk.size(mark_to_market(), cash, eff_price, stop)
                    if qty <= 0:
                        continue
                    cost = qty * eff_price
                    cash -= cost
                    positions[j] = Position(symbols[j], qty, price, cost, stop, target, ts)
                    risk.trades_today += 1

            # 2) Intrabar stop loss / take profit.
            for j, p in list(positions.items()):
                if np.isnan(o[j]):
                    continue
                if l[j] <= p.stop:
                    close_position(j, min(o[j], p.stop), ts, "stop loss")
                elif h[j] >= p.target:
                    close_position(j, max(o[j], p.target), ts, "take profit")

            np.copyto(last_close, c, where=~np.isnan(c))
            equity = mark_to_market()
            equity_vals.append(equity)

            # 3) Decisions at the bar close, executed next bar.
            if decision_time >= flatten_at:
                for j in positions:
                    pending[j] = ("SELL", 0.0, "end of day")
                for j in [j for j, v in pending.items() if v[0] == "BUY"]:
                    del pending[j]
                continue
            if not halted and risk.daily_loss_hit(equity):
                halted = True
                for j in positions:
                    pending[j] = ("SELL", 0.0, "daily loss limit")
            if halted:
                continue
            for j in range(len(symbols)):
                if np.isnan(c[j]) or j in pending:
                    continue
                if j in positions:
                    if arr["cross_down"][i, j] == 1:
                        pending[j] = ("SELL", 0.0, "EMA bear cross")
                    elif arr["below_vwap"][i, j] == 1:
                        pending[j] = ("SELL", 0.0, "lost VWAP")
                elif arr["entry"][i, j] == 1 and entry_from <= decision_time < entry_until:
                    queued = sum(1 for v in pending.values() if v[0] == "BUY")
                    ok, _ = risk.can_open(len(positions) + queued, equity)
                    if ok and risk.trades_today + queued < cfg.max_trades_per_day:
                        pending[j] = ("BUY", arr["atr"][i, j], "EMA bull cross above VWAP")

        # Close anything still open at the very end of the data.
        for j in list(positions):
            close_position(j, last_close[j], times[-1], "end of backtest")
        if equity_vals:
            equity_vals[-1] = cash

        equity = pd.Series(equity_vals, index=times, name="equity")
        bench = self._buy_and_hold(frames)
        return BacktestResult(self.balance0, equity, trades, bench)

    def _buy_and_hold(self, frames: dict[str, pd.DataFrame]) -> pd.Series:
        """Equal-weight buy & hold of the same symbols, same costs, for comparison."""
        closes = pd.DataFrame({s: df["close"] for s, df in frames.items()}).ffill()
        first = pd.Series({s: df["open"].iloc[0] for s, df in frames.items()})
        alloc = self.balance0 / len(frames)
        qty = alloc * (1 - self.cost_rate) / first
        return (closes * qty).sum(axis=1).rename("buy_and_hold")


# --------------------------------------------------------------------- metrics
def summarize(res: BacktestResult) -> dict:
    eq = res.equity
    daily = eq.groupby(eq.index.normalize()).last()
    rets = daily.pct_change().dropna()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1 / 365.25)
    final = float(eq.iloc[-1])
    peak = eq.cummax()
    pnls = np.array([t.pnl for t in res.trades])
    wins, losses = pnls[pnls > 0], pnls[pnls <= 0]
    out = {
        "period": f"{eq.index[0].date()} -> {eq.index[-1].date()}",
        "starting_balance": res.starting_balance,
        "final_balance": round(final, 2),
        "total_return_pct": round((final / res.starting_balance - 1) * 100, 2),
        "cagr_pct": round(((final / res.starting_balance) ** (1 / years) - 1) * 100, 2),
        "max_drawdown_pct": round(float(((eq - peak) / peak).min()) * 100, 2),
        "sharpe": round(float(rets.mean() / rets.std() * math.sqrt(252)), 2)
        if len(rets) > 1 and rets.std() > 0 else float("nan"),
        "trades": len(pnls),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 1) if len(pnls) else 0.0,
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2)
        if len(losses) and losses.sum() < 0 else float("inf"),
        "trading_days": int(len(daily)),
    }
    if res.benchmark is not None and len(res.benchmark):
        b = float(res.benchmark.iloc[-1])
        out["buy_and_hold_final"] = round(b, 2)
        out["buy_and_hold_return_pct"] = round((b / res.starting_balance - 1) * 100, 2)
    return out


def yearly_table(res: BacktestResult) -> pd.DataFrame:
    eq = res.equity
    year_end = eq.groupby(eq.index.year).last()
    year_start = pd.concat([pd.Series([res.starting_balance]), year_end.iloc[:-1]]).to_numpy()
    trades = pd.Series([pd.Timestamp(t.exit_time).year for t in res.trades])
    return pd.DataFrame({
        "end_balance": year_end.round(2),
        "return_pct": ((year_end / year_start - 1) * 100).round(2),
        "trades": trades.value_counts().reindex(year_end.index, fill_value=0),
    })


def main() -> None:
    p = argparse.ArgumentParser(description="Backtest the intraday strategy")
    p.add_argument("--source", choices=["alpaca", "csv", "yahoo"], default="alpaca")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--balance", type=float, default=1000.0)
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--fx-fee-pct", type=float, default=0.15,
                   help="T212 FX fee per side; use 0 if the shares trade in your account currency")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--feed", default="sip", help="Alpaca feed: sip (all exchanges) or iex")
    p.add_argument("--refresh", action="store_true", help="re-download cached Alpaca data")
    p.add_argument("--out", default="backtest_results")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if args.source == "yahoo":
        log.warning("Yahoo only has ~60 days of intraday bars; --start is effectively ignored")

    bars = {sym: load_bars(sym, args, cfg) for sym in cfg.symbols.values()}
    for sym, df in bars.items():
        log.info("%s: %d bars %s -> %s", sym, len(df),
                 df.index.min() if len(df) else "-", df.index.max() if len(df) else "-")

    res = Backtester(cfg, args.balance, args.slippage_bps, args.fx_fee_pct).run(bars)
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    res.equity.to_csv(out / "equity.csv")
    pd.DataFrame([asdict(t) for t in res.trades]).to_csv(out / "trades.csv", index=False)

    print("\n=== Backtest summary ===")
    for k, v in summarize(res).items():
        print(f"{k:>24}: {v}")
    print("\n=== By year ===")
    print(yearly_table(res).to_string())
    print(f"\nEquity curve and trade list written to {out}/")


if __name__ == "__main__":
    main()
