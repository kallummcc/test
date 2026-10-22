"""Benchmark: coin-flip entries with an ATR stop and 2R target.

A strategy with no edge can still pass a prop challenge by luck (it needs +10%
before -10%), so this sets the "luck" bar a real edge has to beat.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy, atr


@dataclass
class RandomEntry(Strategy):
    trades_per_day: float = 0.5  # per pair
    stop_atr: float = 3.0
    target_r: float = 2.0
    seed: int = 1

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        rng = np.random.default_rng(sum(map(ord, pair)) * 1000 + self.seed)
        out = df.copy()
        a = atr(df, 24)
        fire = rng.random(len(df)) < self.trades_per_day / 24
        out["entry"] = np.where(fire, rng.choice([-1, 1], len(df)), 0)
        out["exit"] = False
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_r * self.stop_atr * a
        out["score"] = rng.random(len(df))
        return out


STRATEGY = RandomEntry(name="random_entry", risk_pct=1.0)
