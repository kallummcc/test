"""Intraday mean reversion: buy capitulation days in up-trending large caps, sell at the close.

An intraday (flat-every-night) adaptation of Larry Connors' RSI(2) pullback rule, which is
the best-documented short-term mean-reversion setup for US equities, combined with the
intraday-reversal / liquidity-provision literature (Heston, Korajczyk & Sadka 2010) that
says intraday selling pressure from temporary liquidity imbalances tends to reverse.

Rules (hourly bars, America/New_York, regular session):
  1. Trend filter : yesterday's close > SMA of the last `trend_days` daily closes
                    (completed sessions only; at least `min_days` sessions of history).
  2. Oversold     : RSI(`rsi_len`) of DAILY closes, as of yesterday's close, < `rsi_entry`
                    (the classic Connors RSI(2) oversold reading in an uptrend).
  3. Capitulation : the selling continues today -- the latest closed hourly bar is at
                    least `drop_pct` % below yesterday's close.
  4. Entry        : the first bar of the day on which 1-3 all hold, filled at the next
                    bar's open (engine). One entry per symbol per day.
  5. Exit         : hold to the close (the engine flattens before the bell). A wide
                    catastrophe stop of `stop_mult` x hourly ATR also sizes the trade.
  Score          : the size of today's drop (deepest first) when several symbols fire.

No look-ahead: daily RSI / SMA / prior close come from completed sessions and are shifted
one day; the intraday drop uses the current bar's close only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import Strategy, atr


def wilder_rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn
    return (100 - 100 / (1 + rs)).where(dn > 0, 100.0)


@dataclass
class MeanReversion(Strategy):
    trend_days: int = 50
    min_days: int = 10
    rsi_len: int = 2
    rsi_entry: float = 5.0
    drop_pct: float = 2.0
    atr_period: int = 14
    stop_mult: float = 3.0
    overrides: dict = field(default_factory=dict)

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        day = out.index.date
        # Daily series from completed sessions; shift(1) => known before today's open.
        dclose = out["close"].groupby(day).last()
        prev_close = dclose.shift(1)
        prev_sma = dclose.rolling(self.trend_days, min_periods=self.min_days).mean().shift(1)
        prev_rsi = wilder_rsi(dclose, self.rsi_len).shift(1)
        prev_rsi[dclose.expanding().count().shift(1) < self.min_days] = np.nan

        pc = prev_close.reindex(day).to_numpy()
        uptrend = prev_close.reindex(day).to_numpy() > prev_sma.reindex(day).to_numpy()
        oversold = prev_rsi.reindex(day).to_numpy() < self.rsi_entry
        drop = out["close"].to_numpy() / pc - 1  # today's move vs yesterday's close
        cond = pd.Series(uptrend & oversold & (drop < -self.drop_pct / 100), index=out.index)
        # Only the first qualifying bar of each session.
        first = cond & (cond.astype(int).groupby(day).cumsum() == 1)

        a = atr(out, self.atr_period)
        out["atr"] = a
        out["entry"] = first & a.notna()
        out["exit"] = False  # hold to the close; the engine flattens every session
        out["stop_dist"] = self.stop_mult * a
        out["target_dist"] = np.nan
        out["score"] = pd.Series(-drop, index=out.index).fillna(-np.inf)
        return out


# Sizing: ~1/3 of equity per trade (3 slots), so the edge is not diluted by idle cash.
# The 3-ATR stop sets the risk-based size; at 2% risk the 33% position cap binds.
STRATEGY = MeanReversion(
    name="mean_reversion",
    interval="1h",
    overrides={"risk_per_trade_pct": 2.0, "max_position_pct": 33.0, "max_daily_loss_pct": 5.0},
)
