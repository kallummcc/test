"""Pluggable strategies for the backtester and live agent.

A strategy turns one symbol's OHLCV bars into per-bar columns:

    entry       bool   go long at the next bar's open
    exit        bool   close an open long at the next bar's open
    stop_dist   float  stop-loss distance below the entry price (price units, > 0)
    target_dist float  take-profit distance above entry (NaN = no target)
    score       float  ranking when several symbols signal on the same bar (higher first)

Rules every strategy must respect (Trading 212 Invest/ISA):
  * long only, no leverage, no shorting
  * flat by the end of every session (the engine enforces this)
  * signals on bar t may only use data up to and including bar t (no look-ahead)
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Strategy:
    name: str = "base"
    interval: str = "5m"  # "5m" or "1h"
    # Optional overrides of Config risk/session settings, e.g. {"max_open_positions": 5}
    overrides: dict = field(default_factory=dict)

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:  # pragma: no cover - interface
        raise NotImplementedError


ALLOWED_OVERRIDES = {
    "risk_per_trade_pct": (0.1, 2.0),
    "max_position_pct": (5.0, 100.0),
    "max_open_positions": (1, 10),
    "max_daily_loss_pct": (0.5, 5.0),
    "max_trades_per_day": (1, 30),
    "skip_first_minutes": (0, 120),
    "no_new_entries_minutes_before_close": (0, 300),
    "flatten_minutes_before_close": (0, 60),
}


def apply_overrides(cfg, strategy: Strategy):
    """Copy of cfg with the strategy's overrides applied, clamped to allowed ranges."""
    from dataclasses import replace

    changes = {}
    for key, value in strategy.overrides.items():
        if key not in ALLOWED_OVERRIDES:
            raise ValueError(f"{strategy.name}: override {key!r} is not allowed")
        lo, hi = ALLOWED_OVERRIDES[key]
        changes[key] = type(lo)(min(max(value, lo), hi))
    return replace(cfg, bar_interval=strategy.interval, **changes)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.date
    pv = (typical * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    return pv / vol.where(vol > 0)


def load(name: str) -> Strategy:
    """Instantiate `t212_agent.strategies.<name>.STRATEGY`."""
    module = importlib.import_module(f"{__name__}.{name}")
    return module.STRATEGY


def available() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))
