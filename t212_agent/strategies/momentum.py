"""Intraday momentum in "stocks in play": first-hour breakout on abnormal volume.

Evidence base (see tournament/momentum.md for links and caveats):
  * Zarattini, Barbon & Aziz (2024), "A Profitable Day Trading Strategy for the
    U.S. Equity Market": opening-range momentum works on single US stocks only
    when they are "in play" (relative volume of the opening bars >> normal).
  * Zarattini, Aziz & Barbon (2024), "Beat the Market" (SPY): a move outside the
    "noise area" (average absolute move from the open at that time of day over
    the previous 14 sessions) signals a demand/supply imbalance that tends to
    persist into the close.
  * Gao, Han, Li & Zhou (2018, JFE) and Baltussen, Da, Lammers & Martens (2021,
    JFE): early-session returns predict late-session returns.

Rules (hourly bars; decision at the close of the first bar = 10:30 ET, filled at
the 10:30 bar's open, held to the engine's end-of-day exit):

    rvol  = volume of the first hour / mean first-hour volume of the previous
            `rvol_lookback` sessions                         (stock is "in play")
    sigma = mean |close(first hour) / open - 1| over the previous `lookback`
            sessions                                          (its noise area)
    z     = (close(first hour) / open - 1) / sigma

    entry : rvol >= rvol_min  and  z >= z_min
    exit  : none intraday (the edge accrues into the close); flat at the close
    stop  : catastrophic stop `stop_mult` x ATR(14) below the fill (also sizes)
    score : z  (strongest move in units of the stock's own noise first)

Everything is computed from completed bars of the current day plus prior
sessions (rolling stats are shifted one session), so there is no look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy, atr, session_vwap


def _same_slot_mean(values: pd.Series, day: pd.Index, slot: np.ndarray, window: int) -> pd.Series:
    """Mean of `values` at the same intraday slot over the previous `window` sessions."""
    grid = pd.DataFrame({"day": day, "slot": slot, "v": values.to_numpy()})
    wide = grid.pivot(index="day", columns="slot", values="v")
    hist = wide.rolling(window, min_periods=window).mean().shift(1)  # prior sessions only
    stacked = hist.stack(future_stack=True)
    idx = pd.MultiIndex.from_arrays([day, slot])
    return pd.Series(stacked.reindex(idx).to_numpy(), index=values.index)


@dataclass
class Momentum(Strategy):
    lookback: int = 14        # sessions in the noise-area average (Beat the Market: 14)
    rvol_lookback: int = 20   # sessions in the relative-volume baseline
    rvol_min: float = 3.0     # "in play": first-hour volume >= 3x normal
    z_min: float = 2.0        # first-hour move >= 2 noise-sigmas above the open
    signal_slot: int = 0      # bar slot that may signal (0 = first hourly bar)
    atr_period: int = 14
    stop_mult: float = 3.0    # catastrophic stop in ATRs

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        day = pd.Index(out.index.date)
        slot = out.groupby(day).cumcount().to_numpy()
        day_open = out["open"].groupby(day).transform("first")
        cum_vol = out["volume"].groupby(day).cumsum()

        move = out["close"] / day_open - 1
        sigma = _same_slot_mean(move.abs(), day, slot, self.lookback)
        vol_base = _same_slot_mean(cum_vol, day, slot, self.rvol_lookback)
        rvol = cum_vol / vol_base.where(vol_base > 0)
        z = move / sigma.where(sigma > 0)

        out["vwap"] = session_vwap(out)
        out["atr"] = atr(out, self.atr_period)
        out["rvol"] = rvol
        out["z"] = z

        signal = (
            (slot == self.signal_slot)
            & (rvol >= self.rvol_min)
            & (z >= self.z_min)
            & out["atr"].notna()
        )
        out["entry"] = signal.fillna(False).astype(bool)
        out["exit"] = False
        out["stop_dist"] = self.stop_mult * out["atr"]
        out["target_dist"] = np.nan
        out["score"] = z.replace([np.inf, -np.inf], np.nan).fillna(-np.inf)
        return out


STRATEGY = Momentum(name="momentum", interval="1h")
