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
    df["vwap"] = pv / vol.replace(0, pd.NA)
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

    df = add_indicators(df, fast, slow, atr_period)
    last, prev = df.iloc[-1], df.iloc[-2]
    price, atr = float(last["close"]), float(last["atr"])
    vwap = last["vwap"]

    crossed_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    crossed_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]
    above_vwap = pd.notna(vwap) and price > float(vwap)

    if not in_position and crossed_up and above_vwap:
        return Signal(Action.BUY, price, atr, "EMA bull cross above VWAP")
    if in_position and crossed_down:
        return Signal(Action.SELL, price, atr, "EMA bear cross")
    if in_position and pd.notna(vwap) and price < float(vwap):
        return Signal(Action.SELL, price, atr, "lost VWAP")
    return Signal(Action.HOLD, price, atr, "no signal")
