"""Low turnover: buy at most one "stock in play" per day and hold it to the close.

The skeptic's lane. A 0.34% round trip (2 bps slippage + 0.15% FX each side)
is larger than almost every published intraday effect in large caps, so the
strategy trades only on the rare days when a stock shows the setup with the
largest gross edge we could document: a big gap up on unusually heavy opening
volume (usually an earnings / news catalyst) that *holds* through the first
hour. It buys the single best such name at the 10:30 bar open and holds it to
the close. No intraday exit signal; a protective stop sits below the first
hour's low.

Evidence: opening-range / "stocks in play" continuation (Zarattini, Barbon &
Aziz 2023/24), day-0 continuation of earnings gaps (post-earnings drift
literature), and the strong-close-of-first-hour filter. See
tournament/low_turnover.md for sources, results and caveats.

Uses 1h bars. Signal is computed on the 09:30-10:30 bar only (after it closes),
fills at the 10:30 bar's open. Everything from previous days is shifted, so
there is no look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import Strategy


@dataclass
class LowTurnover(Strategy):
    min_gap: float = 0.02        # open vs previous close
    min_rvol: float = 3.0        # first-hour volume vs 20-day avg first-hour volume
    rvol_days: int = 20
    min_fh: float = 0.0          # first-hour return (close vs open) must exceed this
    min_clv: float = 0.0         # first hour must close in the top (1 - min_clv) of its range
    high_days: int = 120         # first hour must close above the highest high of the prior N sessions (0 = off)
    stop_buffer: float = 0.25    # extra stop room, as a fraction of the first-hour range
    overrides: dict = field(default_factory=lambda: {
        "max_open_positions": 1,
        "max_trades_per_day": 1,
        "risk_per_trade_pct": 2.0,
        "max_position_pct": 50.0,
    })

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        day = pd.Series(df.index.date, index=df.index)
        first = ~day.duplicated()                       # first bar of each session

        # Per-session table built only from data known by the end of the first bar.
        sess = pd.DataFrame({
            "o1": df["open"][first.values].values,
            "h1": df["high"][first.values].values,
            "l1": df["low"][first.values].values,
            "c1": df["close"][first.values].values,
            "v1": df["volume"][first.values].values,
        }, index=day[first].values)
        last_close = df["close"].groupby(day.values).last()
        sess["pc"] = last_close.shift(1).reindex(sess.index)   # previous session close
        sess["v1avg"] = sess["v1"].shift(1).rolling(self.rvol_days, min_periods=10).mean()
        day_high = df["high"].groupby(day.values).max().reindex(sess.index)

        gap = sess["o1"] / sess["pc"] - 1
        rvol = sess["v1"] / sess["v1avg"]
        rng = (sess["h1"] - sess["l1"]).clip(lower=1e-9)
        clv = (sess["c1"] - sess["l1"]) / rng           # where the first hour closed in its range
        sig = (gap > self.min_gap) & (rvol > self.min_rvol) & (sess["c1"] / sess["o1"] - 1 > self.min_fh) & (clv >= self.min_clv)
        if self.high_days:
            # Prior sessions only (shift 1); with a short history fall back to what exists (>= 20 sessions).
            prior_high = day_high.shift(1).rolling(self.high_days, min_periods=20).max()
            sig &= sess["c1"] > prior_high

        entry = pd.Series(False, index=df.index)
        entry[first.values] = sig.fillna(False).values
        stop = pd.Series(np.nan, index=df.index)
        stop[first.values] = ((sess["c1"] - sess["l1"]) + self.stop_buffer * rng).values
        score = pd.Series(-np.inf, index=df.index)
        score[first.values] = clv.fillna(-np.inf).values

        out["entry"] = entry.values
        out["exit"] = False
        out["stop_dist"] = stop.values
        out["target_dist"] = np.nan
        out["score"] = score.values
        return out


STRATEGY = LowTurnover(name="low_turnover", interval="1h")
