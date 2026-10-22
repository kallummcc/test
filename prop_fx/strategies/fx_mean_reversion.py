"""FX mean reversion: fade intraday over-extension from yesterday's pivot.

Rule: during 07:00-16:59 UTC, when an hourly close is more than 1.25 daily ATR(20) away
from yesterday's pivot (H+L+C)/3, fade it at the next open (first bar of the excursion,
at most one signal per pair per UTC day). Stop 1.25 daily ATR; take profit back at the
pivot level; time exit after 48h; the engine flattens Friday 20:00 UTC.

Evidence and caveats: tournament_fx/fx_mean_reversion.md. In short: FX intraday
reversals after large moves are linked to dealer inventory / fixing flows (Krohn,
Mueller & Whelan 2024, J. Finance) and to take-profit order clustering at prominent
levels (Osler 2003). A trend (efficiency-ratio) filter was tested and rejected.

Daily features are built from the pair's own hourly bars (UTC days, weekend stubs
dropped) and are only visible once that daily bar has fully closed, as in `higher_tf`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy


def _daily(df: pd.DataFrame) -> pd.DataFrame:
    d = df.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return d[d.index.weekday < 5]  # drop Sunday-evening stubs


def _align(daily_feats: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Row t of the result = features of the latest daily bar closed by the close of bar t."""
    f = daily_feats.copy()
    f.index = f.index + pd.Timedelta("1D")  # time the daily bar completes
    f = f.rename_axis("done").reset_index()
    t = pd.DataFrame({"t": df.index + pd.Timedelta("1h")})
    m = pd.merge_asof(t, f, left_on="t", right_on="done", direction="backward")
    m.index = df.index
    return m.drop(columns=["t", "done"])


@dataclass
class FxMeanReversion(Strategy):
    ref: str = "pivot"  # "pivot" = yesterday's (H+L+C)/3, "sma" = 5-day SMA of daily closes
    mean_len: int = 5
    atr_len: int = 20  # daily ATR (from hourly bars, UTC days)
    z_entry: float = 1.25  # stretch from the reference, in daily ATRs, needed to fade
    er_len: int = 20
    er_max: float | None = None  # optional trend filter (efficiency ratio of daily closes)
    hours: tuple[int, int] = (7, 16)  # UTC hours (bar open) a signal may fire: London+NY overlap
    stop_atr: float = 1.25  # stop distance in daily ATRs
    target_mode: str = "ref"  # "ref" = back to yesterday's pivot, "r" = fixed multiple, "none"
    target_r: float = 1.0
    max_hold_h: int = 48  # time exit; the engine also flattens Friday 20:00 UTC
    one_per_day: bool = True

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        d = _daily(df)
        c = d["close"]
        prev = c.shift(1)
        tr = pd.concat([d["high"] - d["low"], (d["high"] - prev).abs(), (d["low"] - prev).abs()],
                       axis=1).max(axis=1)
        feats = pd.DataFrame(index=d.index)
        feats["atr"] = tr.rolling(self.atr_len).mean()
        feats["ref"] = ((d["high"] + d["low"] + c) / 3 if self.ref == "pivot"
                        else c.rolling(self.mean_len).mean())
        feats["er"] = (c - c.shift(self.er_len)).abs() / c.diff().abs().rolling(self.er_len).sum()
        f = _align(feats, df)

        stretch = (df["close"] - f["ref"]) / f["atr"]
        hour = df.index.hour
        ok = (hour >= self.hours[0]) & (hour <= self.hours[1])
        if self.er_max is not None:
            ok &= (f["er"] < self.er_max).to_numpy()
        side = pd.Series(np.where(ok & (stretch > self.z_entry), -1,
                                  np.where(ok & (stretch < -self.z_entry), 1, 0)), index=df.index)
        entry = side.where(side != side.shift(1), 0)  # only the first bar of an excursion
        if self.one_per_day:
            day = df.index.normalize()
            entry = entry.where((entry != 0).groupby(day).cumsum() <= 1, 0)
        out["entry"] = entry.astype(int)

        stop = self.stop_atr * f["atr"]
        if self.target_mode == "ref":
            tgt = (df["close"] - f["ref"]).abs()
        elif self.target_mode == "r":
            tgt = self.target_r * stop
        else:
            tgt = pd.Series(np.nan, index=df.index)
        out["stop_dist"] = stop
        out["target_dist"] = tgt

        ts = pd.Series(df.index, index=df.index)
        hours_since = (ts - ts.where(entry != 0).ffill()).dt.total_seconds() / 3600
        out["exit"] = (hours_since >= self.max_hold_h).fillna(False).to_numpy()
        out["score"] = stretch.abs()
        return out


# Sizing (see the write-up): 1.5% per trade; daily stop = 2 full losers = 3.0%, well inside
# FTMO's 5% daily limit; 5 slots cap simultaneous open risk at 7.5% (all stopped in one hour).
STRATEGY = FxMeanReversion(name="fx_mean_reversion", risk_pct=1.5, max_positions=5,
                           daily_stop_pct=3.0)
