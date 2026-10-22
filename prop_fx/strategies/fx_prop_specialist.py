"""fx_prop_specialist: two plain, opposite-regime FX rules with the risk set for FTMO.

The thesis is that you pass FTMO mostly through risk engineering. There is no strong
signal here. G10 FX at intraday-to-weekly horizons is close to efficient after costs
(see tournament_fx/fx_prop_specialist.md). So the strategy pairs two simple, well-known
rules that tend to win in OPPOSITE regimes, which makes the P&L less regime-dependent,
and puts the tuning into size, the number of open positions and the daily stop.

Per pair, decided at the close of hourly bar t, filled at the next bar's open:

  A. Trend-filtered 20-day breakout (Turtle "System 1" with a 100-day trend filter)
     * long  when the hourly close crosses above the high of the last 20 completed
       weekday UTC daily bars and is above their 100-day SMA; short is the mirror image.
     * stop 0.85 x daily ATR(20), target 2R.
  B. Weekly short-term reversal (Monday only)
     * at the Monday 07:00 UTC open, trade AGAINST the return of the last 5 completed
       weekday daily bars (last week's move).
     * stop 1.275 x daily ATR(20) (1.5 x the breakout stop), no target. The engine's Friday 20:00 UTC rule flattens it.
  B is used only on bars where A has no signal. When signals compete for slots, A ranks
  first (score 10 + channel distance), then B (size of last week's move in ATRs).

Risk (see the .md for the curves and the comparison with random_entry):
  * risk_pct 1.0, max_positions 6, daily_stop_pct 2.0
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy


def _daily(df: pd.DataFrame) -> pd.DataFrame:
    """Weekday UTC daily OHLC indexed by the day's START. Sunday-evening stub bars are dropped."""
    d = df.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return d[d.index.weekday < 5]


def _known_at_close(df: pd.DataFrame, daily_series: pd.Series) -> pd.Series:
    """Align a daily series to hourly bars, using only fully completed days (no look-ahead).

    A day labelled D completes at D+1 00:00 UTC, and hourly bar t completes at t+1h.
    This matches `strategies.higher_tf`.
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
    brk_stop_atr: float = 0.85
    brk_target_r: float = 2.0
    rev_days: int = 5
    rev_stop_atr: float = 1.275  # 1.5 x the breakout stop
    rev_hour_utc: int = 7

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        d = _daily(df)
        prev_c = d["close"].shift(1)
        tr = pd.concat([d["high"] - d["low"], (d["high"] - prev_c).abs(),
                        (d["low"] - prev_c).abs()], axis=1).max(axis=1)
        a = _known_at_close(df, tr.rolling(self.atr_days).mean())
        hi = _known_at_close(df, d["high"].rolling(self.channel_days).max())
        lo = _known_at_close(df, d["low"].rolling(self.channel_days).min())
        # If the data starts without 100 days of history (a short hold-out file with no
        # warm-up), use the longest trend average available, from 20 days up.
        sma = _known_at_close(df, d["close"].rolling(self.trend_days,
                                                     min_periods=self.channel_days).mean())
        mom = _known_at_close(df, np.log(d["close"]).diff(self.rev_days))

        c, pc = df["close"], df["close"].shift(1)
        brk = np.where((c > hi) & (pc <= hi) & (c > sma), 1,
                       np.where((c < lo) & (pc >= lo) & (c < sma), -1, 0))
        nxt = df.index + pd.Timedelta("1h")  # the fill bar
        monday_open = (nxt.weekday == 0) & (nxt.hour == self.rev_hour_utc)
        rev = np.where(monday_open & mom.notna().to_numpy(), -np.sign(mom.fillna(0)), 0).astype(int)
        use_rev = (brk == 0) & (rev != 0)

        out["entry"] = np.where(brk != 0, brk, rev)
        out["exit"] = False
        out["stop_dist"] = np.where(use_rev, self.rev_stop_atr * a, self.brk_stop_atr * a)
        out["target_dist"] = np.where(use_rev, np.nan, self.brk_target_r * self.brk_stop_atr * a)
        brk_score = ((c - (hi + lo) / 2).abs() / a).replace([np.inf, -np.inf], np.nan).fillna(0)
        rev_score = (mom.abs() / (a / c)).replace([np.inf, -np.inf], np.nan).fillna(0)
        out["score"] = np.where(brk != 0, 10 + brk_score, rev_score)
        return out


STRATEGY = PropSpecialist(name="fx_prop_specialist", risk_pct=1.0, max_positions=6,
                          daily_stop_pct=2.0)
