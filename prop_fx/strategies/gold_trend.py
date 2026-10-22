"""gold_trend: intraday trend trading on XAUUSD, wrapped in a walk-forward learner.

Idea (see tournament_gold/gold_trend.md): trade only in the direction of the prevailing
trend, which is measured on completed bars and is symmetric long/short. Enter on an
hourly trigger, and harvest a modest target so that the win rate is high. Expectancy
comes from the trend filter tilting the odds; the tight target supplies the win rate.

Entry triggers (`entry_mode`):
  "pullback"  close makes a `pb_hours` low (uptrend) / high (downtrend): buy the dip
  "breakout"  close makes a `brk_hours` high (uptrend) / low (downtrend)
  "strong"    the hourly bar closes > `strong_atr` x ATR in the trend direction
Trend (`trend_mode`):
  "ema"       sign(EMA(fast) - EMA(slow)) on hourly closes
  "daily"     sign(close - close `trend_days` completed days ago)
Exits: stop = `stop_atr` x ATR(24h); target = `target_r` x stop; time exit `max_hold`
hours after the latest entry signal; flat by `flat_hour` UTC; trend flip.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from . import Strategy, atr
from ..adaptive import WalkForward, grid


def daily_closes(df: pd.DataFrame) -> pd.Series:
    """Completed UTC-day closes, indexed by the time each day closed."""
    d = df["close"].resample("1D", label="left", closed="left").last().dropna()
    d.index = d.index + pd.Timedelta("1D")
    return d


def align(series: pd.Series, df: pd.DataFrame) -> pd.Series:
    """Value known at the close of each hourly bar (no look-ahead)."""
    left = pd.DataFrame({"t": df.index + pd.Timedelta("1h")})
    right = series.rename("v").rename_axis("tc").reset_index()
    m = pd.merge_asof(left, right, left_on="t", right_on="tc", direction="backward")
    return pd.Series(m["v"].to_numpy(), index=df.index)


@dataclass
class GoldTrend(Strategy):
    trend_mode: str = "ema"
    ema_fast: int = 24
    ema_slow: int = 120
    trend_days: int = 10
    entry_mode: str = "pullback"
    pb_hours: int = 6
    brk_hours: int = 12
    strong_atr: float = 1.0
    stop_atr: float = 1.5
    target_r: float = 0.6
    max_hold: int = 8
    start_hour: int = 7
    end_hour: int = 18
    flat_hour: int = 20
    clock_hours: tuple = (8, 13)  # "clock" mode: decide at the close of the bar ending here (UTC)
    clock_local: int = 0  # >0: decide at this LOCAL hour in London and in New York (DST-aware)
    mom_hours: int = 12  # "clock" mode: direction = sign of the last mom_hours return
    min_move: float = 0.0  # "clock" mode: |mom_hours move| must exceed this many ATRs
    be_after: int = 0  # >0: from this many bars after entry, take any close >= be_r x stop in profit
    be_r: float = 0.1
    cut_after: int = 0  # >0: from this many bars after entry, cut a trade losing >= cut_r x stop
    cut_r: float = 0.5
    side_mode: int = 0  # 0 both, 1 long only, -1 short only (diagnostics only)

    def trend(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        if self.trend_mode == "daily":
            d = daily_closes(df)
            return align(np.sign(d - d.shift(self.trend_days)), df).fillna(0.0)
        f = c.ewm(span=self.ema_fast, adjust=False).mean()
        s = c.ewm(span=self.ema_slow, adjust=False).mean()
        t = np.sign(f - s)
        t.iloc[: self.ema_slow] = 0.0  # warm-up
        return t

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        c = df["close"]
        a = atr(df, 24)
        tr = self.trend(df)
        hour = df.index.hour
        window = (hour >= self.start_hour) & (hour < self.end_hour)

        if self.entry_mode == "pullback":
            lo = df["low"].rolling(self.pb_hours).min().shift(1)
            hi = df["high"].rolling(self.pb_hours).max().shift(1)
            up, dn = c < lo, c > hi
        elif self.entry_mode == "breakout":
            hi = df["high"].rolling(self.brk_hours).max().shift(1)
            lo = df["low"].rolling(self.brk_hours).min().shift(1)
            up, dn = c > hi, c < lo
        elif self.entry_mode == "clock":
            close_hour = (df.index + pd.Timedelta("1h")).hour
            mv = c - c.shift(self.mom_hours)
            if self.clock_local:
                t_close = df.index + pd.Timedelta("1h")
                ldn = t_close.tz_convert("Europe/London").hour == self.clock_local
                nyc = t_close.tz_convert("America/New_York").hour == self.clock_local
                when = ldn | nyc
            else:
                when = np.isin(close_hour, list(self.clock_hours))
            at = when & (mv.abs() > self.min_move * a)
            up, dn = at & (mv > 0), at & (mv < 0)
            tr = pd.Series(1.0, index=df.index)  # the momentum itself is the trend
            window = np.ones(len(df), dtype=bool)
            long_sig, short_sig = up, dn
        else:  # strong close
            move = c - c.shift(1)
            up, dn = move > self.strong_atr * a, move < -self.strong_atr * a

        if self.entry_mode != "clock":
            long_sig = (tr > 0) & up & window
            short_sig = (tr < 0) & dn & window
        if self.side_mode > 0:
            short_sig &= False
        if self.side_mode < 0:
            long_sig &= False
        entry = np.where(long_sig, 1, np.where(short_sig, -1, 0))
        out["entry"] = entry

        # Time exit: `max_hold` bars after the most recent entry signal.
        idx = pd.Series(np.where(entry != 0, np.arange(len(df)), np.nan), index=df.index).ffill()
        age = np.arange(len(df)) - idx.to_numpy()
        close_hour = (df.index + pd.Timedelta("1h")).hour
        flip = ((tr != tr.shift(1)) & (tr.shift(1) != 0)).to_numpy()
        ex = (age >= self.max_hold) | (close_hour == self.flat_hour) | flip
        if self.be_after > 0 or self.cut_after > 0:
            # Reconstruct the latest signal's fill (next bar's open) to express a
            # "bank a small profit" rule through exit signals.
            sig_i = idx.to_numpy()
            ok = ~np.isnan(sig_i)
            si = np.where(ok, sig_i, 0).astype(int)
            fill = df["open"].shift(-1).to_numpy()[si]  # open of the bar after the signal (known once that bar exists)
            side = entry[si]
            stop0 = (self.stop_atr * a).to_numpy()[si]
            gain = side * (c.to_numpy() - fill)
            if self.be_after > 0:
                ex |= ok & (age >= self.be_after) & (gain >= self.be_r * stop0)
            if self.cut_after > 0:
                ex |= ok & (age >= self.cut_after) & (gain <= -self.cut_r * stop0)
        out["exit"] = ex & (entry == 0)
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_r * self.stop_atr * a
        out["score"] = 1.0
        return out


@dataclass
class PriorWalkForward(WalkForward):
    """WalkForward that trades a fixed `prior` candidate (instead of sitting flat) while it
    has fewer than `train_weeks` of history, or when no candidate has enough trades in the
    window. Same refit mechanics as prop_fx.adaptive.WalkForward (idea from gold_prop)."""

    prior: dict | None = None

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = super().prepare(df, pair)
        if self.prior is None:
            return out
        flat = (out["param_set"] == -1).to_numpy()
        if not flat.any():
            return out
        pf = replace(self.base, **self.prior).prepare(df, pair)
        utc = df.index.tz_convert("UTC")
        monday = (utc - pd.to_timedelta(utc.weekday, "D")).normalize()
        # switch only at a week boundary: rows of weeks that had no learned set at all
        learned_weeks = set(monday[~flat])
        rows = np.array([m not in learned_weeks for m in monday])
        for col in ("entry", "exit", "stop_dist", "target_dist", "score"):
            out.loc[rows, col] = pf.loc[rows, col].to_numpy()
        out.loc[rows, "param_set"] = -2  # -2 = prior
        if self.keep_log:
            for m in sorted(set(monday[rows])):
                self.log.append({"pair": pair, "from": str(m), "params": self.prior, "train_score": None})
        return out


# Final configuration after the learning cycles in tournament_gold/gold_trend.md (C5).
BASE = GoldTrend(
    name="gold_trend_base",
    entry_mode="clock",  # London (08 UTC) and New York (13 UTC) decisions, with the momentum
    clock_hours=(8, 13),
    risk_pct=1.5,  # two full losses = 3%: still 2% under the 5% daily limit
    daily_stop_pct=2.5,  # after one loss, a second trade floating -1% more halts the day
    max_positions=1,
    max_trades_per_day=2,
    pairs=("XAUUSD",),
)

CANDIDATES = grid(mom_hours=[6, 12, 24], stop_atr=[1.5, 2.5], target_r=[0.5, 0.7],
                  max_hold=[4, 8], be_after=[1, 2])  # 48 sets

STRATEGY = WalkForward(name="gold_trend", base=BASE, candidates=CANDIDATES,
                       train_weeks=12, refit_weeks=1, objective="sharpe", min_trades=15)
