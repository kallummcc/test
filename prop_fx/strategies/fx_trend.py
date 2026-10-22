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
* Exit: the daily trend flips or goes neutral (optional channel exit via `exit_hours`,
  disabled in the final config); the engine flattens everything by Friday 20:00 UTC.

Research modes kept for reproducibility of the logged variants: 'daily' (enter every day
at start_hour in the trend direction), 'pullback' (buy channel lows in an uptrend) and
'session' (intraday momentum). The final configuration uses mode='breakout'.
Needs ~50 completed daily bars of hourly history before it can trade (MA warm-up).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy, atr


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
    mode: str = "breakout"  # 'breakout' | 'daily' | 'session'
    # session mode: intraday time-series momentum
    sig_hour: int = 8  # decide at the close of the bar ending at this UTC hour
    exit_hour: int = 20  # flatten at this UTC hour
    min_move: float = 0.5  # |move since 00:00 UTC| in units of daily vol
    stop_vol: float = 1.0  # stop distance in daily vols
    need_trend: int = 0  # 1 = the move must agree with the daily trend

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

        if self.mode == "session":
            return self._session(df, d, trend)
        if self.mode == "daily":
            go = pd.Series(hour == self.start_hour, index=df.index)
            long_sig, short_sig = (trend > 0) & go, (trend < 0) & go
        elif self.mode == "pullback":
            long_sig = (trend > 0) & (df["close"] < lo) & window
            short_sig = (trend < 0) & (df["close"] > hi) & window
        else:
            long_sig = (trend > 0) & (df["close"] > hi) & window
            short_sig = (trend < 0) & (df["close"] < lo) & window
        out["entry"] = np.where(long_sig, 1, np.where(short_sig, -1, 0))
        # Exit any position whose trend has gone, or that breaks the opposite channel.
        # (Positions are only ever opened with the trend, so this is unambiguous.)
        prev_trend = trend.shift(1).fillna(0.0)
        flipped = (trend != prev_trend) & (prev_trend != 0)
        if self.mode == "pullback":  # take profit when price recovers to the channel top
            chan = ((trend > 0) & (df["close"] > xhi)) | ((trend < 0) & (df["close"] < xlo))
        else:
            chan = ((trend > 0) & (df["close"] < xlo)) | ((trend < 0) & (df["close"] > xhi))
        out["exit"] = (flipped | chan) & ~long_sig & ~short_sig
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = (self.target_r * self.stop_atr * a) if self.target_r else np.nan
        # Prefer the strongest breakouts relative to volatility.
        dist = np.where(long_sig, df["close"] - hi, np.where(short_sig, lo - df["close"], 0.0))
        if self.mode == "pullback":
            dist = np.where(long_sig, lo - df["close"], np.where(short_sig, df["close"] - hi, 0.0))
        if self.mode == "daily":
            dist = (d - d.shift(self.mom_days)).abs().reindex(df.index, method="ffill").to_numpy()
        out["score"] = pd.Series(dist, index=df.index) / a
        out["score"] = out["score"].replace([np.inf, -np.inf], np.nan)
        return out

    def _session(self, df, d, trend):
        out = df.copy()
        lc = np.log(df["close"])
        day = df.index.normalize()
        # Daily vol from completed UTC days, aligned to each hourly bar.
        dvol_d = np.log(d).diff().rolling(20).std()
        dvol = dvol_d.reindex(df.index, method="ffill")
        day_open = pd.Series(np.log(df["open"]).to_numpy(), index=df.index).groupby(day).transform("first")
        first_hour = pd.Series(df.index.hour, index=df.index).groupby(day).transform("min")
        move = (lc - day_open) / dvol
        close_hour = (df.index + pd.Timedelta("1h")).hour
        at_sig = (close_hour == self.sig_hour) & (first_hour == 0)
        sgn = np.sign(move)
        ok = at_sig & (move.abs() >= self.min_move)
        if self.need_trend:
            ok &= sgn == trend
        out["entry"] = np.where(ok, sgn, 0).astype(int)
        out["exit"] = close_hour == self.exit_hour
        out["stop_dist"] = self.stop_vol * dvol * df["close"]
        out["target_dist"] = (self.target_r * self.stop_vol * dvol * df["close"]) if self.target_r else np.nan
        out["score"] = move.abs()
        return out


# Final configuration (variant V22 in tournament_fx/fx_trend.md).
STRATEGY = FxTrend(
    name="fx_trend",
    brk_hours=72,  # ~3-day channel: the H4/D1-scale breakout, timed on 1h closes
    exit_hours=10**6,  # no channel exit: hold to stop, trend flip, or Friday flat
    stop_atr=5.0,  # 5 x ATR(24h) ~ one daily range: survives intraday noise for a week
    risk_pct=1.0,
    max_positions=4,
    daily_stop_pct=3.0,
    pairs=("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
           "EURJPY", "GBPJPY", "AUDJPY"),  # no EURGBP / EURCHF: low-vol, range-bound crosses
)
