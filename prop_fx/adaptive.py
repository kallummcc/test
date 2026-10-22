"""Walk-forward self-optimisation: strategies that keep re-tuning themselves.

`WalkForward` wraps a base strategy and a grid of candidate parameter sets.
Every `refit_weeks` (at the Monday open) it scores every candidate on the
trailing `train_weeks` of data only, switches to the best one, and trades that
for the next period. Nothing from the future is ever used, so the backtest is a
fair simulation of a bot that learns as it goes. Live, the same `prepare()` runs
on the recent bars from MT5, so the bot re-tunes itself every week.

How it stays fast: the engine sizes every trade from the initial balance, so a
candidate's trades don't depend on when you start counting. Each candidate is
run once over the whole history, and each training window just slices its trade
list.

Objectives (`objective=`):
  "expectancy"   total R in the window (rewards edge x frequency)
  "win_rate"     win rate, subject to avg R > 0 (high win rate that still pays)
  "sharpe"       mean R / std R per trade
  "pass_score"   total R minus a penalty for the worst day (prop-firm friendly)
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import engine
from .strategies import Strategy

OBJECTIVES = ("expectancy", "win_rate", "sharpe", "pass_score")


def grid(**axes) -> list[dict]:
    """grid(a=[1, 2], b=[3]) -> [{'a': 1, 'b': 3}, {'a': 2, 'b': 3}]"""
    keys = list(axes)
    return [dict(zip(keys, combo)) for combo in itertools.product(*axes.values())]


def score_trades(trades: pd.DataFrame, objective: str, min_trades: int) -> float:
    if len(trades) < min_trades:
        return -math.inf
    r = trades["r"].to_numpy()
    if objective == "expectancy":
        return float(r.sum())
    if objective == "win_rate":
        return float((r > 0).mean()) if r.mean() > 0 else -math.inf
    if objective == "sharpe":
        return float(r.mean() / r.std()) if r.std() > 0 else -math.inf
    if objective == "pass_score":
        worst_day = trades.groupby(trades["day"])["r"].sum().min()
        return float(r.sum() + 2.0 * min(worst_day, 0.0))
    raise ValueError(f"unknown objective {objective!r}; choose from {OBJECTIVES}")


@dataclass
class WalkForward(Strategy):
    base: Strategy | None = None
    candidates: list[dict] = field(default_factory=list)
    train_weeks: int = 12
    refit_weeks: int = 1
    objective: str = "expectancy"
    min_trades: int = 10
    keep_log: bool = True

    def __post_init__(self):
        if self.base is not None:
            # Account-level settings come from the base strategy.
            for attr in ("interval", "risk_pct", "max_positions", "daily_stop_pct",
                         "max_trades_per_day", "pairs"):
                setattr(self, attr, getattr(self.base, attr))
        self.log: list[dict] = []

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        if not self.candidates:
            return self.base.prepare(df, pair)
        variants = [replace(self.base, **params) for params in self.candidates]
        frames, trade_tables = [], []
        for v in variants:
            frame = v.prepare(df, pair)
            frames.append(frame)
            res = engine.run(_Fixed(frame, v), {pair: df})
            t = pd.DataFrame([{"entry": pd.Timestamp(x.entry_time), "r": x.r_multiple}
                              for x in res.trades], columns=["entry", "r"])
            t["day"] = t["entry"].dt.normalize() if len(t) else []
            trade_tables.append(t)

        utc = df.index.tz_convert("UTC")
        monday = (utc - pd.to_timedelta(utc.weekday, "D")).normalize()
        week_starts = pd.DatetimeIndex(sorted(set(monday)))
        out = frames[0].copy()
        out["entry"], out["exit"] = 0, False
        out["param_set"] = -1
        train = pd.Timedelta(weeks=self.train_weeks)
        refits = week_starts[:: self.refit_weeks]
        for k, start in enumerate(refits):
            end = refits[k + 1] if k + 1 < len(refits) else utc[-1] + pd.Timedelta(hours=1)
            if start - train < utc[0]:
                continue  # not enough history to learn from yet: stay flat
            scores = []
            for t in trade_tables:
                window = t[(t["entry"] >= start - train) & (t["entry"] < start)] if len(t) else t
                scores.append(score_trades(window, self.objective, self.min_trades))
            best = int(np.argmax(scores))
            if not math.isfinite(scores[best]):
                continue  # nothing worth trading in the last window: sit out
            rows = (utc >= start) & (utc < end)
            for col in ("entry", "exit", "stop_dist", "target_dist", "score"):
                out.loc[rows, col] = frames[best].loc[rows, col].to_numpy()
            out.loc[rows, "param_set"] = best
            if self.keep_log:
                self.log.append({"pair": pair, "from": str(start), "params": self.candidates[best],
                                 "train_score": round(scores[best], 3)})
        return out

    def current_params(self) -> dict | None:
        """Parameters the bot is using now (the latest refit)."""
        return self.log[-1]["params"] if self.log else None


@dataclass
class _Fixed(Strategy):
    """Replays an already-prepared frame through the engine."""

    frame: pd.DataFrame | None = None
    src: Strategy | None = None

    def __init__(self, frame, src):
        super().__init__(name=f"{src.name}-fixed", interval=src.interval, risk_pct=src.risk_pct,
                         max_positions=src.max_positions, daily_stop_pct=src.daily_stop_pct,
                         max_trades_per_day=src.max_trades_per_day, pairs=src.pairs)
        self.frame = frame

    def prepare(self, df, pair):
        return self.frame
