"""Backtest a forex strategy and score it against the FTMO 2-Step challenge.

    python -m prop_fx.backtest --strategy donchian --data-dir data/fx
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import engine, ftmo, strategies
from .instruments import PAIRS


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    ts = next(c for c in ("timestamp", "datetime", "date", "time") if c in df.columns)
    df.index = pd.to_datetime(df.pop(ts), utc=True)
    df = df[["open", "high", "low", "close"]].astype(float).sort_index()
    df = df[~df.index.duplicated()]
    # Drop Yahoo's occasional zero-range placeholder bars.
    return df[(df["high"] >= df["low"]) & (df["close"] > 0)]


def load_dir(data_dir: str, interval: str, pairs=None, start=None, end=None) -> dict:
    bars = {}
    for p in pairs or PAIRS:
        f = Path(data_dir) / f"{p}_{interval}.csv"
        if not f.exists():
            continue
        df = load_csv(f)
        if start:
            df = df[df.index >= pd.Timestamp(start, tz="UTC")]
        if end:
            df = df[df.index < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
        bars[p] = df
    return bars


def trade_stats(res: engine.EngineResult, initial: float) -> dict:
    trades = res.trades
    pnl = np.array([t.pnl for t in trades])
    r = np.array([t.r_multiple for t in trades])
    equity = initial + res.realized + res.floating_close
    times = res.times
    eq = pd.Series(equity, index=times)
    peak = eq.cummax()
    daily = eq.groupby(eq.index.normalize()).last().pct_change().dropna()
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    by_year = pd.Series(pnl, index=[pd.Timestamp(t.exit_time).year for t in trades]
                        ).groupby(level=0).sum() / initial * 100 if len(pnl) else pd.Series(dtype=float)
    return {
        "period": f"{times[0].date()} -> {times[-1].date()}",
        "net_return_pct": round(float(pnl.sum()) / initial * 100, 2),
        "max_drawdown_pct": round(float(((eq - peak) / peak).min()) * 100, 2),
        "sharpe": round(float(daily.mean() / daily.std() * math.sqrt(252)), 2)
        if len(daily) > 2 and daily.std() > 0 else None,
        "trades": int(len(pnl)),
        "trades_per_week": round(len(pnl) / max(1, (times[-1] - times[0]).days / 7), 2),
        "win_rate_pct": round(100 * len(wins) / len(pnl), 1) if len(pnl) else 0.0,
        "avg_r": round(float(r.mean()), 3) if len(r) else 0.0,
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2)
        if len(losses) and losses.sum() < 0 else None,
        "by_year_pct": {int(k): round(float(v), 2) for k, v in by_year.items()},
        "by_pair_pct": {k: round(v / initial * 100, 2) for k, v in pd.Series(
            pnl, index=[t.pair for t in trades]).groupby(level=0).sum().items()} if len(pnl) else {},
    }


def main(argv=None) -> dict:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strategy", default="donchian",
                   help=f"one of: {', '.join(strategies.available())}")
    p.add_argument("--data-dir", default="data/fx")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--trade-from", default=None, help="earlier bars only warm up indicators")
    p.add_argument("--balance", type=float, default=100_000)
    p.add_argument("--commission", type=float, default=5.0, help="USD per lot round turn")
    p.add_argument("--spread-mult", type=float, default=1.0)
    p.add_argument("--slippage-pips", type=float, default=0.1)
    p.add_argument("--boot", type=int, default=2000, help="bootstrap challenges")
    p.add_argument("--out", default=None, help="directory for trades.csv")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    strat = strategies.load(args.strategy)
    bars = load_dir(args.data_dir, strat.interval, strat.pairs, args.start, args.end)
    cfg = engine.EngineConfig(args.balance, args.commission, spread_mult=args.spread_mult,
                              slippage_pips=args.slippage_pips)
    trade_from = pd.Timestamp(args.trade_from, tz="UTC") if args.trade_from else None
    res = engine.run(strat, bars, cfg, trade_from)
    if trade_from is not None:
        keep = res.times >= trade_from
        k0 = np.flatnonzero(keep)[0]
        base = res.realized[k0 - 1] if k0 else 0.0
        res = engine.EngineResult(res.times[keep], res.realized[keep] - base,
                                  res.floating_close[keep], res.floating_worst[keep],
                                  res.flat[keep], res.opened[keep],
                                  [t for t in res.trades if pd.Timestamp(t.entry_time) >= trade_from])
    summary = {"strategy": strat.name, "pairs": len(bars), "risk_pct": strat.risk_pct,
               **trade_stats(res, args.balance),
               "ftmo": ftmo.evaluate(res, ftmo.Rules(initial_balance=args.balance), args.boot)}
    if args.out:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        pd.DataFrame([asdict(t) for t in res.trades]).to_csv(Path(args.out) / "trades.csv",
                                                             index=False)
    if args.json:
        print(json.dumps(summary, default=str))
    else:
        print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
