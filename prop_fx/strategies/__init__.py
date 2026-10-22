"""Pluggable forex strategies.

`prepare(df, pair)` receives ONE pair's bars (UTC DatetimeIndex, columns
open/high/low/close; Yahoo FX has no volume) and returns per-bar columns:

    entry       int    +1 open long, -1 open short, 0 nothing (fills at next bar's open;
                       an opposite signal reverses an open position)
    exit        bool   close any open position at the next bar's open
    stop_dist   float  stop-loss distance from entry in price units (> 0, required)
    target_dist float  take-profit distance in price units (NaN = none)
    score       float  ranking when several pairs signal on the same bar (higher first)

The engine enforces: no positions over the weekend (FTMO Standard account),
fixed-dollar risk sizing, spread + commission, and the FTMO rules.
Signals on bar t may only use data up to and including bar t.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass

import pandas as pd


@dataclass
class Strategy:
    name: str = "base"
    interval: str = "1h"
    risk_pct: float = 0.5  # % of the INITIAL challenge balance risked per trade (0.1-2.0)
    max_positions: int = 3  # max simultaneous positions across all pairs (1-8)
    daily_stop_pct: float | None = None  # stop trading for the day after this loss (% of initial)
    max_trades_per_day: int | None = None  # cap on new positions per day (Prague day)
    pairs: tuple[str, ...] | None = None  # None = every pair in the data set

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError


LIMITS = {"risk_pct": (0.1, 2.0), "max_positions": (1, 8), "daily_stop_pct": (0.5, 4.5),
          "max_trades_per_day": (1, 20)}


def validated(strategy: Strategy) -> Strategy:
    for key, (lo, hi) in LIMITS.items():
        value = getattr(strategy, key)
        if value is not None and not lo <= value <= hi:
            raise ValueError(f"{strategy.name}: {key}={value} outside [{lo}, {hi}]")
    return strategy


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def higher_tf(df: pd.DataFrame, rule: str, bar: str = "1h") -> pd.DataFrame:
    """OHLC of a higher timeframe (e.g. '4h', '1D'), aligned to `df` without look-ahead.

    Row t holds the most recent higher-timeframe bar that had fully *closed* by the
    close of lower bar t. Daily bars use UTC midnight boundaries.
    """
    agg = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    agg.index = agg.index + pd.Timedelta(rule)  # time the bar completes
    agg = agg.rename_axis("ht_close_time").reset_index()
    lower_close = pd.DataFrame({"t": df.index + pd.Timedelta(bar)})
    merged = pd.merge_asof(lower_close, agg, left_on="t", right_on="ht_close_time",
                           direction="backward")
    merged.index = df.index
    return merged[["open", "high", "low", "close"]]


def load(name: str) -> Strategy:
    module = importlib.import_module(f"{__name__}.{name}")
    return validated(module.STRATEGY)


def available() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))
