"""Gold (XAUUSD) intraday mean reversion of pullbacks, self-tuning via walk-forward.

Base rule (GoldMR): gold's intraday session move tends to persist (we measured strong
intraday momentum in dev), so we never fade the session trend. Instead we fade the
*pullback* against it: when the session (opened 23:00 UTC) is up more than `trend_thr`
hourly ATRs and an hourly bar closes down, buy (mirror for shorts). A daily regime filter
(close vs 20-day SMA) makes trades against the multi-day trend require a 2x stronger
session move. High-win-rate geometry: target < stop, short time exit.

`STRATEGY` wraps it in `prop_fx.adaptive.WalkForward`: every Monday it re-scores 54
candidate sets on the trailing 12 weeks (objective: total R) and trades the winner.
See tournament_gold/gold_mean_reversion.md for research, learning cycles and results.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    daily_align: int = 0
    against_mult: float = float("inf")  # >0: also require close vs SMA(daily_align) of daily closes to agree

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        c = df["close"]
        a = atr(df, self.atr_len)
        session = (df.index + pd.Timedelta(hours=1)).normalize()  # 23:00 UTC -> next day
        s_open = df["open"].groupby(session).transform("first")
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
        hour = df.index.hour
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
        out["exit"] = (since >= self.max_hold_h).fillna(False).to_numpy()
        out["score"] = st.abs()
        return out


# Account settings: 1.5% risk per trade, at most 2 trades a day and one open position, so the
# worst normal day is two full stops = 3.0% (= daily_stop_pct), leaving 2% headroom under
# FTMO's 5% daily limit for gaps/slippage through a stop.
BASE = GoldMR(name="gold_mean_reversion", pull=1, refire=True, daily_align=20, against_mult=2.0,
              risk_pct=1.5, max_positions=1, max_trades_per_day=2, daily_stop_pct=3.0,
              pairs=("XAUUSD",))

# 54 candidate sets; the walk-forward re-picks one every Monday from the trailing 12 weeks.
GRID = grid(trend_thr=[0.4, 0.6, 0.8], target_atr=[0.6, 0.8, 1.0], stop_atr=[1.25, 1.5, 2.0],
            max_hold_h=[3, 5])

STRATEGY = WalkForward(name="gold_mean_reversion", base=BASE, candidates=GRID,
                       train_weeks=12, refit_weeks=1, objective="expectancy", min_trades=10)
