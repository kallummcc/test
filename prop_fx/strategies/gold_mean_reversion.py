"""Gold (XAUUSD) intraday mean reversion of pullbacks, self-tuning via walk-forward.

Base rule (GoldMR): gold's intraday session move tends to persist (we measured strong
intraday momentum in dev), so we never fade the session trend. Instead we fade the
*pullback* against it: when the session (opened at the CME reopen, 18:00 New York time,
DST-aware since Round 3) is up more than `trend_thr` hourly ATRs and an hourly bar closes
down, buy (mirror for shorts). A daily regime filter
(close vs 20-day SMA) makes trades against the multi-day trend require a 2x stronger
session move. High-win-rate geometry: target < stop, short time exit.

`STRATEGY` wraps it in `PriorWalkForward` (a `prop_fx.adaptive.WalkForward` subclass): every
Monday it re-scores 54 candidate sets on the trailing 12 weeks (objective: total R) and trades
the winner; while it has no history yet it trades a fixed middle-of-grid prior set.
See tournament_gold/gold_mean_reversion.md for research, learning cycles and results.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import Strategy, atr, higher_tf
from ..adaptive import WalkForward, grid


def _daily_sma(df: pd.DataFrame, n: int) -> pd.Series:
    """SMA of the last n *closed* UTC daily closes, aligned to hourly bars (no look-ahead)."""
    d = df["close"].resample("1D", label="left", closed="left").last().dropna()
    sma = d.rolling(n).mean()
    sma.index = sma.index + pd.Timedelta("1D")
    t = pd.DataFrame({"t": df.index + pd.Timedelta("1h")})
    m = pd.merge_asof(t, sma.rename("v").rename_axis("done").reset_index(), left_on="t",
                      right_on="done", direction="backward")
    return pd.Series(m["v"].to_numpy(), index=df.index)


@dataclass
class GoldMR(Strategy):
    """Fade the pullback, never the session trend.

    session move  st = (close - session open) / ATR, session opens 23:00 UTC
    pullback      `pull` consecutive hourly closes against the session move
                  ("bars"), or RSI(2) beyond `rsi_lvl` against it ("rsi")
    entry         in the direction of the session move when |st| > trend_thr
    exits         stop `stop_atr`, target `target_atr` (hourly ATR), time exit
    """

    trend_thr: float = 0.5
    pull_mode: str = "bars"  # "bars" or "rsi"
    pull: int = 2
    rsi_lvl: float = 25.0
    atr_len: int = 24
    stop_atr: float = 1.5
    target_atr: float = 0.75
    max_hold_h: int = 4
    hours: tuple[int, int] = (1, 19)  # UTC bar-open hours allowed to signal
    refire: bool = False  # True: every qualifying bar may enter (not only the first of a run)
    daily_align: int = 0  # >0: daily regime = last closed daily close vs SMA(daily_align)
    against_mult: float = float("inf")  # trades against that regime need against_mult x trend_thr
    clock: str = "utc"  # "utc": session opens 23:00 UTC, hours in UTC; "ny": CME clock (DST-aware)
    be_after: int = 0  # >0: from this many bars after the latest signal, exit on a close >= be_r x stop
    be_r: float = 0.1

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        c = df["close"]
        a = atr(df, self.atr_len)
        if self.clock == "ny":
            # CME Globex gold reopens at 18:00 New York time (22:00 UTC in summer, 23:00 in
            # winter); the session is keyed on New York time + 6h so it starts at that reopen.
            ny = df.index.tz_convert("America/New_York")
            session = (ny + pd.Timedelta(hours=6)).normalize()
            hour = pd.Index(((ny.hour + 5) % 24))  # NY hour expressed on the winter-UTC scale
        else:
            session = (df.index + pd.Timedelta(hours=1)).normalize()  # 23:00 UTC -> next day
            hour = df.index.hour
        s_open = df["open"].groupby(np.asarray(session)).transform("first")
        st = (c - s_open) / a
        if self.pull_mode == "bars":
            down = pd.Series(True, index=df.index)
            up = pd.Series(True, index=df.index)
            for k in range(self.pull):
                down &= c.shift(k) < c.shift(k + 1)
                up &= c.shift(k) > c.shift(k + 1)
        else:
            d = c.diff()
            gain = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
            loss = (-d).clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
            r2 = 100 - 100 / (1 + gain / loss)
            down, up = r2 < self.rsi_lvl, r2 > 100 - self.rsi_lvl
        ok = (hour >= self.hours[0]) & (hour <= self.hours[1])
        long_sig = ok & (st > self.trend_thr) & down
        short_sig = ok & (st < -self.trend_thr) & up
        if self.daily_align:
            # Daily regime: trades against the multi-day trend need a stronger session move
            # (against_mult x trend_thr); against_mult=inf forbids them entirely.
            dly = higher_tf(df, "1D")["close"]
            sma = _daily_sma(df, self.daily_align)
            up_d, dn_d = (dly > sma).to_numpy(), (dly < sma).to_numpy()
            strong = self.trend_thr * self.against_mult
            long_sig &= up_d | (st > strong).to_numpy()
            short_sig &= dn_d | (st < -strong).to_numpy()
        side = pd.Series(np.where(long_sig, 1, np.where(short_sig, -1, 0)), index=df.index)
        entry = side if self.refire else side.where(side != side.shift(1), 0)
        out["entry"] = entry.astype(int)
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_atr * a
        ts = pd.Series(df.index, index=df.index)
        since = (ts - ts.where(entry != 0).ffill()).dt.total_seconds() / 3600
        ex = np.array((since >= self.max_hold_h).fillna(False).to_numpy(), dtype=bool)
        if self.be_after > 0:
            # Bank a small profit (gold_trend's break-even idea): measured from the fill of the
            # latest signal (next bar's open), known once that bar exists; executed next open.
            pos = np.arange(len(df))
            si = pd.Series(np.where(entry != 0, pos, np.nan)).ffill().to_numpy()
            ok_i = ~np.isnan(si)
            sii = np.where(ok_i, si, 0).astype(int)
            fill = df["open"].shift(-1).to_numpy()[sii]
            side_i = entry.to_numpy()[sii]
            age = pos - sii
            gain = side_i * (c.to_numpy() - fill)
            ex |= ok_i & (age >= self.be_after) & (gain >= self.be_r * (self.stop_atr * a).to_numpy()[sii])
        out["exit"] = ex
        out["score"] = st.abs()
        return out


@dataclass
class PriorWalkForward(WalkForward):
    """WalkForward that trades a fixed `prior` parameter set whenever the stock learner
    would sit flat: the first `train_weeks` of any data set (cold start) and weeks where no
    candidate has `min_trades` in the trailing window. Idea borrowed from gold_prop. Every
    learned week is exactly the stock WalkForward choice."""

    prior: dict = field(default_factory=dict)

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = super().prepare(df, pair)
        if not self.prior:
            return out
        flat = (out["param_set"] == -1).to_numpy()
        if flat.any():
            frame = replace(self.base, **self.prior).prepare(df, pair)
            for col in ("entry", "exit", "stop_dist", "target_dist", "score"):
                out.loc[flat, col] = frame.loc[flat, col].to_numpy()
        return out


# Account settings (Round 3).
# - 1.5% risk per trade, at most 2 trades a day, one open position.
# - daily_stop_pct=2.0: the day halts once closed + floating loss reaches 2%. One full stop
#   (1.5%) still allows a second trade, so the worst normal day is about 2% + one stop = 3.5%.
#   At the judge's DOUBLE risk (3% per trade), the first full loss halts the day, and the
#   worst case is about 2% + 3% = 5% only if a partial loser is followed by a full one;
#   in-sample at double risk there were 0 daily-limit breaches (vs 5 with a 3% daily stop).
BASE = GoldMR(name="gold_mean_reversion", pull=1, refire=True, daily_align=20, against_mult=2.0,
              clock="ny", risk_pct=1.5, max_positions=1, max_trades_per_day=2,
              daily_stop_pct=2.0, pairs=("XAUUSD",))

# 54 candidate sets (Round 3: trend_thr grid one step lower, for frequency).
GRID = grid(trend_thr=[0.2, 0.4, 0.6], target_atr=[0.6, 0.8, 1.0], stop_atr=[1.25, 1.5, 2.0],
            max_hold_h=[3, 5])

# Traded while the learner has < 12 weeks of history (cold start) or no qualifying set: the
# middle of the grid, not a tuned set.
PRIOR = {"trend_thr": 0.4, "target_atr": 0.8, "stop_atr": 1.5, "max_hold_h": 3}

STRATEGY = PriorWalkForward(name="gold_mean_reversion", base=BASE, candidates=GRID,
                            train_weeks=12, refit_weeks=1, objective="expectancy",
                            min_trades=10, prior=PRIOR)
