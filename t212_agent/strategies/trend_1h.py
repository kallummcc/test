"""trend_1h: first-hour channel breakout on "stocks in play", hourly bars.

Idea (see tournament/trend_1h.md for sources): intraday trend following works
best on stocks with abnormal participation (Zarattini, Barbon & Aziz 2024,
opening-range breakout on "Stocks in Play"; Gao et al. 2018 / Baltussen et al.
2021 intraday momentum). On 1h bars the first bar (09:30-10:30) is the opening
range. We go long only when

  * the first hour traded far more volume than its own recent norm
    (relative volume vs the prior `rv_lookback` sessions' first hours), and
  * the first hour closed up by at least `min_move_atr` x the stock's daily
    range (ATR%, prior sessions only),

then hold to the close (the engine flattens). One entry per symbol per day,
which keeps turnover low against the ~0.34% round trip. The stop sits below
the first-hour low (the bottom of the opening channel), capped at
`max_stop_atr` daily ATRs.

No look-ahead: daily statistics use only completed prior sessions (.shift()),
and the first-hour features are known at the 09:30 bar's close; the engine
fills at the 10:30 open.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import Strategy


@dataclass
class Trend1h(Strategy):
    rv_lookback: int = 20       # sessions for the first-hour volume norm
    rv_min: float = 2.0         # first-hour volume / its prior-sessions mean
    atr_days: int = 14          # daily range lookback (prior sessions)
    min_move_atr: float = 0.5   # first-hour open->close move, in daily-ATR units
    max_stop_atr: float = 1.0   # stop distance cap, in daily-ATR units (price)
    stop_at_fh_low: bool = True  # False: stop = max_stop_atr x daily ATR (catastrophe stop)
    late_breakout: bool = False  # also enter on a later close above the first-hour high
    vwap_exit: bool = False     # exit on an hourly close below session VWAP

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        day = pd.Index(out.index.date)
        first = ~day.duplicated()  # first bar of each session (09:30-10:30)

        # --- daily stats from completed prior sessions only
        g = out.groupby(day)
        daily = pd.DataFrame({
            "h": g["high"].max(), "l": g["low"].min(), "c": g["close"].last(),
            "v1": g["volume"].first(),
        })
        prev_c = daily["c"].shift(1)
        tr = pd.concat([daily["h"] - daily["l"], (daily["h"] - prev_c).abs(),
                        (daily["l"] - prev_c).abs()], axis=1).max(axis=1)
        daily["atr"] = tr.rolling(self.atr_days).mean().shift(1)
        daily["v1_norm"] = daily["v1"].rolling(self.rv_lookback).mean().shift(1)

        atr_d = pd.Series(daily["atr"].reindex(day).to_numpy(), index=out.index)
        v1_norm = pd.Series(daily["v1_norm"].reindex(day).to_numpy(), index=out.index)

        # --- first-hour (opening channel) features, known at that bar's close
        fh_open = out["open"].where(first).groupby(day).transform("first")
        fh_high = out["high"].where(first).groupby(day).transform("first")
        fh_low = out["low"].where(first).groupby(day).transform("first")
        fh_close = out["close"].where(first).groupby(day).transform("first")
        fh_vol = out["volume"].where(first).groupby(day).transform("first")

        rv = fh_vol / v1_norm
        move = fh_close - fh_open
        in_play = (rv >= self.rv_min) & (move >= self.min_move_atr * atr_d)

        if self.late_breakout:
            # wait for confirmation: a later hourly close above the first-hour high
            brk = (~first) & (out["close"] > fh_high)
            entry = in_play & brk
        else:
            entry = first & in_play
        # one entry per symbol per session
        entry = entry & (entry.astype(int).groupby(day).cumsum() == 1)

        # stop: below the opening-channel low, capped at max_stop_atr daily ATRs
        if self.stop_at_fh_low:
            stop = (out["close"] - fh_low).clip(lower=0.1 * atr_d)
            stop = np.minimum(stop, self.max_stop_atr * atr_d)
        else:
            stop = self.max_stop_atr * atr_d

        exit_ = pd.Series(False, index=out.index)
        if self.vwap_exit:
            tp = (out["high"] + out["low"] + out["close"]) / 3
            vwap = (tp * out["volume"]).groupby(day).cumsum() / \
                out["volume"].groupby(day).cumsum()
            exit_ = out["close"] < vwap

        out["entry"] = entry.fillna(False) & atr_d.notna() & v1_norm.notna()
        out["exit"] = exit_
        out["stop_dist"] = stop
        out["target_dist"] = np.nan
        out["score"] = rv.fillna(-np.inf)
        return out


STRATEGY = Trend1h(
    name="trend_1h",
    interval="1h",
    overrides={
        "risk_per_trade_pct": 1.0,
        "max_position_pct": 33.0,
        "max_open_positions": 3,
    },
)
