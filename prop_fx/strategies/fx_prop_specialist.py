"""fx_prop_specialist: a plain trend-filtered 20-day breakout with the risk set for FTMO.

The thesis is that you pass FTMO mostly through risk engineering. The signal is modest
and well documented (the Turtle "System 1" 20-day channel breakout, only taken in the
direction of the 100-day trend). All the tuning went into the parts the prop rules
punish: size, number of open positions, the daily stop and weekend flatness.

Signal (per pair, decided at the close of hourly bar t, filled at the next open):
  * hi20 / lo20 = highest high / lowest low of the last 20 *completed* UTC daily bars
  * sma100      = 100-day SMA of completed daily closes
  * long  when the hourly close crosses above hi20 and close > sma100
  * short when the hourly close crosses below lo20 and close < sma100
  * stop = 1.0 x ATR(20) of completed daily bars; target = 2R. Otherwise the trade is
    held until the engine's Friday 20:00 UTC flat rule (so there is no weekend gap and
    swap costs at most 4 nights).
  * score (to rank simultaneous signals) = distance from the channel mid-point in ATRs.

Risk (chosen on 2024-01..2025-06 only, from a plateau rather than the peak; see
tournament_fx/fx_prop_specialist.md):
  * risk_pct 1.0      -> 10 losing R in a row to reach the 10% max-loss line
  * max_positions 4   -> worst simultaneous stop-out = 4% < 5% daily limit
  * daily_stop_pct 3  -> flat and no new trades for the day after -3% (at least 2% buffer)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy


def _daily(df: pd.DataFrame) -> pd.DataFrame:
    """UTC daily OHLC indexed by the day's START (label='left')."""
    return df.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def _known_at_close(df: pd.DataFrame, daily_series: pd.Series) -> pd.Series:
    """Align a daily series to hourly bars so that only fully completed days are used.

    A day labelled D completes at D+1 00:00 UTC; hourly bar t is complete at t+1h.
    This mirrors `strategies.higher_tf` (no look-ahead).
    """
    s = daily_series.copy()
    s.index = s.index + pd.Timedelta("1D")
    s = s.rename("v").rename_axis("k").reset_index()
    t = pd.DataFrame({"t": df.index + pd.Timedelta("1h")})
    m = pd.merge_asof(t, s, left_on="t", right_on="k", direction="backward")
    return pd.Series(m["v"].to_numpy(), index=df.index)


@dataclass
class PropSpecialist(Strategy):
    channel_days: int = 20
    trend_days: int = 100
    atr_days: int = 20
    stop_atr: float = 1.0
    target_r: float = 2.0

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        d = _daily(df)
        prev_c = d["close"].shift(1)
        tr = pd.concat([d["high"] - d["low"], (d["high"] - prev_c).abs(),
                        (d["low"] - prev_c).abs()], axis=1).max(axis=1)
        hi = _known_at_close(df, d["high"].rolling(self.channel_days).max())
        lo = _known_at_close(df, d["low"].rolling(self.channel_days).min())
        # min_periods: if the data starts without 100 days of history (e.g. a short hold-out
        # file with no warm-up), use the longest trend average available, from 20 days up.
        sma = _known_at_close(df, d["close"].rolling(self.trend_days,
                                                     min_periods=self.channel_days).mean())
        a = _known_at_close(df, tr.rolling(self.atr_days).mean())

        c, pc = df["close"], df["close"].shift(1)
        up = (c > hi) & (pc <= hi) & (c > sma)
        dn = (c < lo) & (pc >= lo) & (c < sma)
        out["entry"] = np.where(up, 1, np.where(dn, -1, 0))
        out["exit"] = False
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_r * self.stop_atr * a
        out["score"] = ((c - (hi + lo) / 2).abs() / a).replace([np.inf, -np.inf], np.nan)
        return out


STRATEGY = PropSpecialist(name="fx_prop_specialist", risk_pct=1.0, max_positions=4,
                          daily_stop_pct=3.0)
