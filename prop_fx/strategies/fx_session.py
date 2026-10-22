"""Session-based FX strategy (placeholder; final rules set after dev testing)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy, atr

LONDON = "Europe/London"


def _session_frame(df: pd.DataFrame) -> pd.DataFrame:
    """London-local clock features. Bar label = bar OPEN time; a bar labelled hour h
    closes at h+1 London time. DST is handled by converting to Europe/London."""
    loc = df.index.tz_convert(LONDON)
    return pd.DataFrame({"hr": loc.hour, "day": loc.normalize().tz_localize(None),
                         "wd": loc.weekday}, index=df.index)


@dataclass
class FxSession(Strategy):
    mode: str = "sweep"  # "breakout" | "sweep" | "fixfade" | "nycont"
    asia_end: int = 7  # Asian range = London-local bars 00:00 .. asia_end-1 (closes at asia_end)
    win_start: int = 7  # first bar (London hour label) on which a signal may fire
    win_end: int = 10  # last bar label on which a signal may fire
    exit_hour: int = 16  # flatten at this London hour's open (the WM/R 4pm fix)
    stop_buf_atr: float = 0.25  # extra stop buffer beyond the structural level (ATR units)
    min_stop_atr: float = 0.75
    max_stop_atr: float = 4.0
    target_mode: str = "opposite"  # "opposite" side of range | "mid" | "r" (target_r * stop)
    target_r: float = 1.5
    min_range_atr: float = 1.0  # Asian range must be at least this many hourly ATRs
    max_range_atr: float = 6.0
    atr_n: int = 24
    trend_n: int = 0  # >0: only trade in the direction of close vs SMA(trend_n) of daily closes
    stop_mode: str = "mid"  # breakout: "mid" of Asian range | "opp" opposite side

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        s = _session_frame(df)
        a = atr(df, self.atr_n)
        hi, lo, cl, op = df["high"], df["low"], df["close"], df["open"]
        day = s["day"]
        in_asia = s["hr"] < self.asia_end
        a_hi = hi.where(in_asia).groupby(day).cummax().groupby(day).ffill()
        a_lo = lo.where(in_asia).groupby(day).cummin().groupby(day).ffill()
        # the range is only complete once the asia_end-1 bar has closed
        n_asia = in_asia.astype(int).groupby(day).cumsum()
        complete = (~in_asia) & (n_asia >= self.asia_end - 1)
        rng = a_hi - a_lo
        rng_ok = complete & (rng >= self.min_range_atr * a) & (rng <= self.max_range_atr * a)
        window = (s["hr"] >= self.win_start) & (s["hr"] <= self.win_end) & (s["wd"] < 5)

        entry = pd.Series(0, index=df.index)
        stop = pd.Series(np.nan, index=df.index)
        target = pd.Series(np.nan, index=df.index)
        buf = self.stop_buf_atr * a

        trend = self._trend(df) if self.trend_n else pd.Series(0, index=df.index)

        if self.mode == "breakout":
            # session high/low touched so far today after the Asian range
            long_sig = rng_ok & window & (cl > a_hi)
            short_sig = rng_ok & window & (cl < a_lo)
            entry[long_sig] = 1
            entry[short_sig] = -1
            ref_l = (a_hi + a_lo) / 2 if self.stop_mode == "mid" else a_lo
            ref_s = (a_hi + a_lo) / 2 if self.stop_mode == "mid" else a_hi
            stop[long_sig] = (cl - ref_l + buf)[long_sig]
            stop[short_sig] = (ref_s - cl + buf)[short_sig]
            target[:] = self.target_r * stop if self.target_r > 0 else np.nan
        elif self.mode == "sweep":
            # liquidity sweep: bar trades through the Asian extreme but closes back inside
            post = (~in_asia)
            ext_hi = hi.where(post).groupby(day).cummax()
            ext_lo = lo.where(post).groupby(day).cummin()
            short_sig = rng_ok & window & (hi > a_hi) & (cl < a_hi) & (cl > a_lo)
            long_sig = rng_ok & window & (lo < a_lo) & (cl > a_lo) & (cl < a_hi)
            both = short_sig & long_sig
            short_sig &= ~both
            long_sig &= ~both
            entry[short_sig] = -1
            entry[long_sig] = 1
            stop[short_sig] = (ext_hi - cl + buf)[short_sig]
            stop[long_sig] = (cl - ext_lo + buf)[long_sig]
            if self.target_mode == "opposite":
                target[short_sig] = (cl - a_lo)[short_sig]
                target[long_sig] = (a_hi - cl)[long_sig]
            elif self.target_mode == "mid":
                mid = (a_hi + a_lo) / 2
                target[short_sig] = (cl - mid)[short_sig]
                target[long_sig] = (mid - cl)[long_sig]
            else:
                target[:] = self.target_r * stop
        elif self.mode == "fixfade":
            # fade the 3h run-up into the 16:00 London fix (Evans 2017; Krohn et al. 2024)
            sig_bar = (s["hr"] == 15) & (s["wd"] < 5)
            move = cl - op.shift(2)  # open of 13:00 bar -> close of 15:00 bar (=16:00)
            big = move.abs() >= self.min_range_atr * a
            entry[sig_bar & big & (move > 0)] = -1
            entry[sig_bar & big & (move < 0)] = 1
            stop[:] = self.max_stop_atr * a
            target[:] = self.target_r * stop
        elif self.mode == "nycont":
            # NY open continuation of the London-morning move
            sig_bar = (s["hr"] == self.win_start) & (s["wd"] < 5)
            lon_open = op.where(s["hr"] == self.asia_end).groupby(day).ffill()
            move = cl - lon_open
            big = move.abs() >= self.min_range_atr * a
            entry[sig_bar & big & (move > 0)] = 1
            entry[sig_bar & big & (move < 0)] = -1
            stop[:] = self.max_stop_atr * a
            target[:] = self.target_r * stop
        else:
            raise ValueError(self.mode)

        if self.trend_n:
            entry = entry.where(entry * trend > 0, 0)
        if self.mode in ("breakout", "sweep"):
            stop = stop.clip(lower=self.min_stop_atr * a, upper=self.max_stop_atr * a)
            ok = entry != 0
            if self.target_mode != "r" or self.mode == "breakout":
                pass
            # require a non-trivial target
            ok &= target > 0.5 * stop if self.mode == "sweep" else ok
            entry = entry.where(ok | (entry == 0), 0)
            # first signal of the day only
            first = (entry != 0).astype(int).groupby(day).cumsum()
            entry = entry.where(first == 1, 0)
        else:
            if self.mode == "breakout":
                pass

        if self.target_r <= 0:
            target[:] = np.nan
        out["entry"] = entry.astype(int)
        out["exit"] = (s["hr"] == self.exit_hour - 1).to_numpy()
        out["stop_dist"] = stop
        out["target_dist"] = target
        out["score"] = (target / stop).replace([np.inf, -np.inf], np.nan).fillna(0)
        return out


    def _trend(self, df: pd.DataFrame) -> pd.Series:
        """+1/-1: last COMPLETED UTC daily close vs its SMA(trend_n). No look-ahead."""
        daily = df["close"].resample("1D").last().dropna()
        sig = np.sign(daily - daily.rolling(self.trend_n).mean())
        sig.index = sig.index + pd.Timedelta("1D")  # known once the day has closed
        avail = pd.DataFrame({"t": df.index + pd.Timedelta("1h")})
        m = pd.merge_asof(avail, sig.rename("s").rename_axis("k").reset_index(),
                          left_on="t", right_on="k", direction="backward")
        return pd.Series(m["s"].fillna(0).to_numpy(), index=df.index)


STRATEGY = FxSession(name="fx_session", risk_pct=1.0, max_positions=3, daily_stop_pct=3.0)
