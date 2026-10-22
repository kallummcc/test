"""gold_prop: the prop-firm specialist for XAUUSD.

Thesis: a >=60% win rate that also passes FTMO comes from trade geometry and risk
engineering placed on a modest, simple edge. Each piece is on purpose:

  edge      trade in the direction of the recent hourly trend (24h slope of an EMA)
            at fixed session times. Time-series momentum (Moskowitz, Ooi & Pedersen
            2012) is the documented, plain edge. Shorts are allowed and symmetric.
  geometry  stop = stop_atr x ATR(24h), target = target_r x stop with target_r < 1.
            The target/stop ratio buys the win rate; the walk-forward picks it.
  calendar  entries only at three session fills (01 UTC Asia, 10 UTC London, 16 UTC
            NY afternoon). Never in the high-impact US data window (12-15 UTC) or the
            thin daily break. Every position is flattened 1h before the next session
            ("session exit"), so the slot is free and the bot really trades ~2 a day.
  regime    no new entries while ATR(24) > 1.5 x its 20-day median (volatility shock:
            fat tails, gaps, and that's where the daily limit gets breached).
  risk      1.5% a trade, max 1 position, max 2 trades a day, 3% daily stop. Two full
            losses = 3%, which leaves a 2% buffer under FTMO's 5% daily limit.
  learning  PropWalkForward re-picks the geometry (stop_atr x target_r, 16 sets) every
            Monday from the trailing 12 weeks only, by a prop objective. Sets with win
            rate >= 60% AND avg R > 0 rank first, then by total R + 2 x worst day.
            Until 12 weeks of history exist it trades a fixed prior set
            (2.0 ATR / 0.6R) instead of sitting flat.

Signals at the close of bar t fill at bar t+1's open; only data up to bar t is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .. import engine
from ..adaptive import WalkForward, _Fixed, grid, score_trades
from . import Strategy, atr


@dataclass
class GoldTrendSession(Strategy):
    trend_len: int = 100            # hourly EMA span
    entry_hours: tuple = (1, 10, 16)  # UTC hours of the FILL bar (Asia, London mid, NY pm)
    stop_atr: float = 2.0
    target_r: float = 0.8
    max_hold: int = 0               # bars; 0 = hold to stop/target/Friday close
    sides: str = "both"             # "both" | "long" | "short"
    skip_hours: tuple = (12, 13, 14, 15, 21, 22)
    max_vol_ratio: float = 1.5      # skip entries if ATR(24) > this x its 20-day median; 0 = off
    session_exit: bool = True       # flatten 1h before each entry session (frees the slot)

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        c = df["close"]
        a = atr(df, 24)
        ema = c.ewm(span=self.trend_len, adjust=False, min_periods=self.trend_len).mean()
        direction = np.sign(ema - ema.shift(24)).fillna(0).to_numpy()
        if self.sides == "long":
            direction = np.where(direction > 0, direction, 0)
        elif self.sides == "short":
            direction = np.where(direction < 0, direction, 0)
        fill_hour = (df.index + pd.Timedelta("1h")).hour
        when = np.isin(fill_hour, self.entry_hours) & ~np.isin(fill_hour, self.skip_hours)
        if self.max_vol_ratio:
            calm = (a / a.rolling(24 * 20, min_periods=24 * 5).median()) <= self.max_vol_ratio
            when &= calm.to_numpy()
        entry = np.where(when, direction, 0).astype(int)
        out["entry"] = entry
        if self.max_hold:
            sig = pd.Series(entry != 0, index=df.index)
            out["exit"] = sig.shift(self.max_hold, fill_value=False).to_numpy() & (entry == 0)
        else:
            out["exit"] = False
        if self.session_exit:
            # exit flag on bar t closes at bar t+1's open = 1 hour before the next session fill
            pre = np.isin(fill_hour, [(h - 1) % 24 for h in self.entry_hours])
            out["exit"] = np.asarray(out["exit"], dtype=bool) | pre
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_r * self.stop_atr * a
        out["score"] = 1.0
        return out


def prop_score(trades: pd.DataFrame, min_trades: int, min_win: float = 0.60) -> float:
    """Prop objective: qualified (win >= min_win and avg R > 0) candidates rank above all
    others; within a tier, total R + 2 x worst day (in R, if negative)."""
    if len(trades) < min_trades:
        return -math.inf
    r = trades["r"].to_numpy()
    base = score_trades(trades, "pass_score", min_trades)
    qualified = (r > 0).mean() >= min_win and r.mean() > 0
    return base + (1000.0 if qualified else 0.0)


@dataclass
class PropWalkForward(WalkForward):
    """WalkForward with two prop-firm additions. The mechanics are the same as
    prop_fx.adaptive.WalkForward: each weekly refit scores every candidate on the
    trailing `train_weeks` only.
      * objective "prop" (see prop_score), as well as the built-in ones;
      * `prior`: index of a default candidate to trade while there is not yet enough
        history to learn from (or when no candidate has enough trades), instead of
        sitting flat. None keeps the stock behaviour (flat)."""
    min_win: float = 0.60
    prior: int | None = None

    def _score(self, w: pd.DataFrame) -> float:
        if self.objective == "prop":
            return prop_score(w, self.min_trades, self.min_win)
        return score_trades(w, self.objective, self.min_trades)

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        if not self.candidates:
            return self.base.prepare(df, pair)
        variants = [replace(self.base, **p) for p in self.candidates]
        frames, tables = [], []
        for v in variants:
            frame = v.prepare(df, pair)
            frames.append(frame)
            res = engine.run(_Fixed(frame, v), {pair: df})
            t = pd.DataFrame([{"entry": pd.Timestamp(x.entry_time), "r": x.r_multiple}
                              for x in res.trades], columns=["entry", "r"])
            t["day"] = t["entry"].dt.normalize() if len(t) else []
            tables.append(t)
        utc = df.index.tz_convert("UTC")
        monday = (utc - pd.to_timedelta(utc.weekday, "D")).normalize()
        refits = pd.DatetimeIndex(sorted(set(monday)))[:: self.refit_weeks]
        out = frames[0].copy()
        out["entry"], out["exit"], out["param_set"] = 0, False, -1
        train = pd.Timedelta(weeks=self.train_weeks)
        for k, start in enumerate(refits):
            end = refits[k + 1] if k + 1 < len(refits) else utc[-1] + pd.Timedelta(hours=1)
            learned = start - train >= utc[0]
            windows = [t[(t["entry"] >= start - train) & (t["entry"] < start)] for t in tables]
            scores = [self._score(w) for w in windows] if learned else [-math.inf] * len(tables)
            best = int(np.argmax(scores))
            if not math.isfinite(scores[best]):
                if self.prior is None:
                    continue  # stock behaviour: stay flat
                best = self.prior
            rows = (utc >= start) & (utc < end)
            for col in ("entry", "exit", "stop_dist", "target_dist", "score"):
                out.loc[rows, col] = frames[best].loc[rows, col].to_numpy()
            out.loc[rows, "param_set"] = best
            if self.keep_log:
                w = windows[best]
                self.log.append({"pair": pair, "from": str(start), "params": self.candidates[best],
                                 "learned": bool(learned and math.isfinite(scores[best])),
                                 "train_score": round(float(scores[best]), 3)
                                 if math.isfinite(scores[best]) else None,
                                 "train_n": int(len(w)),
                                 "train_win": round(float((w["r"] > 0).mean()), 3) if len(w) else None,
                                 "train_avg_r": round(float(w["r"].mean()), 3) if len(w) else None})
        return out


# risk 1.5% a trade, 2 trades a day max, so two full losses = 3% and the 3% daily stop
# leaves a 2% buffer under FTMO's 5% daily limit for gaps and slippage.
BASE = GoldTrendSession(name="gold_prop_base", risk_pct=1.5, max_positions=1,
                        max_trades_per_day=2, daily_stop_pct=3.0, pairs=("XAUUSD",))

CANDIDATES = grid(stop_atr=[1.5, 2.0, 2.5, 3.0], target_r=[0.4, 0.5, 0.6, 0.7])  # 16 sets
PRIOR = CANDIDATES.index({"stop_atr": 2.0, "target_r": 0.6})  # traded until it has 12 weeks

STRATEGY = PropWalkForward(name="gold_prop", base=BASE, candidates=CANDIDATES,
                           train_weeks=12, refit_weeks=1, objective="prop",
                           min_trades=10, min_win=0.60, prior=PRIOR)
