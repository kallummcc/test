"""Baseline: the original EMA-cross-above-VWAP momentum strategy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..strategy import add_signals
from . import Strategy


@dataclass
class EmaVwap(Strategy):
    fast: int = 9
    slow: int = 21
    atr_period: int = 14
    stop_mult: float = 1.5
    target_mult: float = 3.0

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = add_signals(df, self.fast, self.slow, self.atr_period)
        out["exit"] = out["cross_down"] | out["below_vwap"]
        out["stop_dist"] = self.stop_mult * out["atr"]
        out["target_dist"] = self.target_mult * out["atr"]
        out["score"] = (out["close"] / out["vwap"] - 1).fillna(-np.inf)
        return out


STRATEGY = EmaVwap(name="ema_vwap", interval="5m")
