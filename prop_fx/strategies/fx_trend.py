"""fx_trend: within-week time-series momentum with an hourly breakout entry.

Evidence base: time-series momentum (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi &
Pedersen 2017) -- the sign of an asset's own past 1-12 month return predicts its next
month's return, including in currency forwards. O'Brien et al. find that time-series
momentum accounts for the historical profits of classic FX technical rules (moving
averages, channel breakouts). FTMO Standard forces us flat every Friday, so we harvest
the trend inside each week:

* Trend (daily, closed bars only): sign of the close vs the close `mom_days` trading
  days earlier must agree with the sign of close vs its `ma_days` simple average.
* Entry (1h): close breaks the prior `brk_hours` high (long) / low (short) in the
  trend direction, between `start_hour` and `end_hour` UTC (liquid London/NY hours).
* Stop: `stop_atr` x ATR(24h). No fixed target unless `target_r` is set.
* Exit: close crosses the prior `exit_hours` low (long) / high (short), or the daily
  trend flips; the engine flattens everything by Friday 20:00 UTC.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy, atr, higher_tf


def daily_closes(df: pd.DataFrame) -> pd.Series:
    """Series of completed daily closes (UTC days), indexed by the time each closed."""
    d = df["close"].resample("1D", label="left", closed="left").last().dropna()
    d.index = d.index + pd.Timedelta("1D")
    return d


@dataclass
class FxTrend(Strategy):
    mom_days: int = 20
    ma_days: int = 50
    brk_hours: int = 24
    exit_hours: int = 24
    stop_atr: float = 3.0
    atr_hours: int = 24
    target_r: float | None = None
    start_hour: int = 7
    end_hour: int = 17

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        # Daily trend from fully closed UTC days only (no look-ahead).
        d = daily_closes(df)
        mom = np.sign(d - d.shift(self.mom_days))
        ma = np.sign(d - d.rolling(self.ma_days).mean())
        trend_d = pd.Series(np.where(mom == ma, mom, 0.0), index=d.index)
        t_close = pd.DataFrame({"t": df.index + pd.Timedelta("1h")})
        tr = pd.merge_asof(t_close, trend_d.rename("trend").rename_axis("tc").reset_index(),
                           left_on="t", right_on="tc", direction="backward")
        trend = pd.Series(tr["trend"].to_numpy(), index=df.index).fillna(0.0)

        a = atr(df, self.atr_hours)
        hi = df["high"].rolling(self.brk_hours).max().shift(1)
        lo = df["low"].rolling(self.brk_hours).min().shift(1)
        xhi = df["high"].rolling(self.exit_hours).max().shift(1)
        xlo = df["low"].rolling(self.exit_hours).min().shift(1)
        hour = df.index.hour
        window = (hour >= self.start_hour) & (hour < self.end_hour)

        long_sig = (trend > 0) & (df["close"] > hi) & window
        short_sig = (trend < 0) & (df["close"] < lo) & window
        out["entry"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))
        # Exit any position whose trend has gone, or that breaks the opposite channel.
        # (Positions are only ever opened with the trend, so this is unambiguous.)
        prev_trend = trend.shift(1).fillna(0.0)
        flipped = (trend != prev_trend) & (prev_trend != 0)
        out["exit"] = (flipped | ((trend > 0) & (df["close"] < xlo))
                       | ((trend < 0) & (df["close"] > xhi))) & ~long_sig & ~short_sig
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = (self.target_r * self.stop_atr * a) if self.target_r else np.nan
        # Prefer the strongest breakouts relative to volatility.
        dist = np.where(long_sig, df["close"] - hi, np.where(short_sig, lo - df["close"], 0.0))
        out["score"] = pd.Series(dist, index=df.index) / a
        out["score"] = out["score"].replace([np.inf, -np.inf], np.nan)
        return out


STRATEGY = FxTrend(name="fx_trend", risk_pct=0.5, max_positions=4, daily_stop_pct=3.0)
