"""Long-only intraday momentum strategy.

Entry: fast EMA crosses above slow EMA on the latest closed bar, and price is
above today's VWAP (trend confirmation).
Exit: ATR-based stop loss / take profit, a bearish EMA cross, or a close below
VWAP. All positions are flattened before the session close by the agent.

Long-only because Trading 212 Invest/ISA accounts cannot short.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    action: Action
    price: float
    atr: float
    reason: str


def add_indicators(df: pd.DataFrame, fast: int, slow: int, atr_period: int) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()

    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.rolling(atr_period).mean()

    # VWAP that resets every trading day.
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.date
    pv = (typical * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    df["vwap"] = pv / vol.where(vol > 0)
    return df


def add_signals(df: pd.DataFrame, fast: int, slow: int, atr_period: int) -> pd.DataFrame:
    """Indicators plus per-bar entry/exit flags (vectorised, used by the backtester)."""
    df = add_indicators(df, fast, slow, atr_period)
    above = df["ema_fast"] > df["ema_slow"]
    below = df["ema_fast"] < df["ema_slow"]
    prev_fast, prev_slow = df["ema_fast"].shift(1), df["ema_slow"].shift(1)
    df["cross_up"] = above & (prev_fast <= prev_slow)
    df["cross_down"] = below & (prev_fast >= prev_slow)
    df["above_vwap"] = df["close"] > df["vwap"]
    df["below_vwap"] = df["close"] < df["vwap"]
    df["entry"] = df["cross_up"] & df["above_vwap"] & df["atr"].notna()
    df.loc[df.index[: max(slow, atr_period) + 1], "entry"] = False
    return df


def evaluate(
    df: pd.DataFrame,
    fast: int,
    slow: int,
    atr_period: int,
    in_position: bool,
) -> Signal:
    if len(df) < max(slow, atr_period) + 2:
        return Signal(Action.HOLD, float("nan"), float("nan"), "not enough bars")

    last = add_signals(df, fast, slow, atr_period).iloc[-1]
    price, atr = float(last["close"]), float(last["atr"])

    if not in_position and last["entry"]:
        return Signal(Action.BUY, price, atr, "EMA bull cross above VWAP")
    if in_position and last["cross_down"]:
        return Signal(Action.SELL, price, atr, "EMA bear cross")
    if in_position and last["below_vwap"]:
        return Signal(Action.SELL, price, atr, "lost VWAP")
    return Signal(Action.HOLD, price, atr, "no signal")
