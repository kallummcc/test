"""Baseline: 4-hour Donchian channel breakout, both directions, ATR stop and 2R target."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy, atr, higher_tf


@dataclass
class Donchian(Strategy):
    lookback: int = 20  # hourly bars
    stop_atr: float = 2.0
    target_r: float = 2.0

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        a = atr(df, 14)
        upper = df["high"].rolling(self.lookback).max().shift(1)
        lower = df["low"].rolling(self.lookback).min().shift(1)
        trend = higher_tf(df, "1D")["close"]
        out["entry"] = 0
        out.loc[(df["close"] > upper) & (df["close"] > trend), "entry"] = 1
        out.loc[(df["close"] < lower) & (df["close"] < trend), "entry"] = -1
        out["exit"] = False
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_r * self.stop_atr * a
        out["score"] = ((df["close"] - trend).abs() / a).replace([np.inf, -np.inf], np.nan)
        return out


STRATEGY = Donchian(name="donchian")
