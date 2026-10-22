"""gold_xasset (Round 3, final): gold's own momentum, vetoed when the dollar explains the move.

Round 1-2 version (git 4b25161) followed the sign of gold's dollar-adjusted residual. It
lost to an always-long copy of itself (+0.014R vs +0.037R): the residual sign put ~45% of
trades short at bad moments. The Round-2 cross-examination showed that the one edge that
survived every test (gold_trend) follows gold's RAW momentum, and that its P&L is ~88%
ex-dollar. So the revision:

Rules (base strategy, one parameter set)
----------------------------------------
1. USD index = least-squares currency-strength decomposition of the 12 FX pairs
   (`fx_strength.currency_index`), read from os.environ["FX_DATA_DIR"] (default
   data/fx), clipped to the gold df's time window, aligned to gold bars with a backward
   as-of join (FX bar t closes at the same time as gold bar t).
2. beta_t = rolling OLS slope of hourly gold log-returns on USD-index returns, trailing
   `beta_win` bars. pg = gold log-return over `lookback` bars, pu = USD return over the
   same bars, resid = pg - beta_t * pu.
3. DIRECTION = sign(pg): gold's own raw momentum. Trigger: |pg| / trailing std(pg) crosses
   above `z_th` (fresh cross only).
4. CROSS-ASSET VETO: skip the trade unless at least `gold_share` of the move is gold's own,
   i.e. sign(pg) * resid >= gold_share * |pg|. A move that is mostly the dollar (gold up only
   because USD fell) is not traded.
5. Exits: stop `stop_atr` x ATR(24h); target `target_atr` x ATR; break-even exit (from
   gold_trend): from `be_after` bars after the fill, exit at the first close that is
   >= `be_r` x stop in profit; time exit `hold` bars after the signal; flat at the close of
   the 19:00 UTC bar, no signals 19-21 UTC (futures roll / holiday holes sit in the break).
6. Account: 1 position, max 2 trades a day, risk 1.5% / daily stop 2.5%. After one full
   loser (-1.5%) a second trade may run until the day is -2.5% (worst ~ -3% with slippage).
   At the judge's double-risk test (3% a trade, same 2.5% stop) one full loss halts the day.
   (A 3.0% daily stop breached the 5% limit 4 times at double risk: a -1.002R stop left the
   day at -2.99%, just inside the stop, and the second trade then lost too.)

`STRATEGY` = PriorWalkForward (a WalkForward subclass, idea from gold_prop): every Monday
it re-picks the best of 18 sets on the trailing 8 weeks (Sharpe objective, as in
gold_trend); while it has less than 8 weeks of history it trades a fixed prior set
instead of sitting flat, so a short hold-out file still trades from week 1.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import Strategy, atr
from .. import engine
from ..adaptive import WalkForward, _Fixed, grid, score_trades
from .fx_strength import UNIVERSE, currency_index

_CACHE: dict = {}


def fx_dir() -> str:
    return os.environ.get("FX_DATA_DIR", "data/fx")


def _fx_index(t0: pd.Timestamp, t1: pd.Timestamp) -> pd.DataFrame:
    from ..backtest import load_csv

    d = fx_dir()
    key = (d, t0, t1)
    if key not in _CACHE:
        closes = {}
        for p in UNIVERSE:
            f = Path(d) / f"{p}_1h.csv"
            if f.exists():
                v = load_csv(f)
                v = v[(v.index >= t0) & (v.index <= t1)]
                if not v.empty:
                    closes[p] = v["close"]
        if not closes:
            raise FileNotFoundError(f"gold_xasset: no FX hourly files in {d!r} (set FX_DATA_DIR)")
        _CACHE.clear()
        _CACHE[key] = currency_index(pd.DataFrame(closes).sort_index())
    return _CACHE[key]


def fx_features(df: pd.DataFrame) -> pd.DataFrame:
    """FX currency indices aligned to the gold bars (as-of, backward: no look-ahead)."""
    idx = _fx_index(df.index[0], df.index[-1])
    m = pd.merge_asof(pd.DataFrame({"t": df.index}), idx.rename_axis("ts").reset_index(),
                      left_on="t", right_on="ts", direction="backward")
    m.index = df.index
    return m.drop(columns=["t", "ts"])


@dataclass
class GoldXAsset(Strategy):
    lookback: int = 6  # bars for gold's move
    z_th: float = 1.0
    z_win: int = 500
    beta_win: int = 500
    direction: str = "raw"  # "raw": sign of gold's move; "resid": sign of the ex-USD residual (R1-2)
    gold_share: float | None = 0.5  # veto: >= this share of the move must be gold's own (None = off)
    stop_atr: float = 2.0
    target_atr: float = 1.0
    hold: int = 8
    be_after: int = 1  # 0 = off; else break-even exit from this many bars after the fill
    be_r: float = 0.1
    flat_hour: int | None = 19
    fresh_only: bool = True  # True: only the bar where |z| crosses z_th; False: every bar beyond it
    long_only: bool = False  # diagnostics only (always-long control)

    def features(self, df: pd.DataFrame) -> pd.DataFrame:
        fx = fx_features(df)
        lg = np.log(df["close"])
        rg, ru = lg.diff(), fx["USD"].diff()
        mp = 100
        cov = (rg * ru).rolling(self.beta_win, min_periods=mp).mean() - (
            rg.rolling(self.beta_win, min_periods=mp).mean()
            * ru.rolling(self.beta_win, min_periods=mp).mean())
        beta = cov / ru.rolling(self.beta_win, min_periods=mp).var(ddof=0)
        pg, pu = lg.diff(self.lookback), fx["USD"].diff(self.lookback)
        resid = pg - beta * pu
        zg = pg / pg.rolling(self.z_win, min_periods=mp).std()
        zr = resid / resid.rolling(self.z_win, min_periods=mp).std()
        return pd.DataFrame({"beta": beta, "pg": pg, "pu": pu, "resid": resid, "zg": zg, "zr": zr})

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        f = self.features(df)
        z = f["zg"] if self.direction == "raw" else f["zr"]
        fresh = (z.abs() > self.z_th) & z.notna()
        if self.fresh_only:
            fresh &= ~(z.shift(1).abs() > self.z_th)
        side = np.sign(z)
        ok = fresh.copy()
        if self.gold_share is not None:
            own = np.sign(f["pg"]) * f["resid"]
            ok &= own >= self.gold_share * f["pg"].abs()
        h = df.index.hour
        if self.flat_hour is not None:
            ok &= ~((h >= self.flat_hour) & (h <= 21))
        entry = np.where(ok, side, 0).astype(int)
        if self.long_only:
            entry = np.abs(entry)
        n = len(df)
        pos = np.arange(n)
        last = pd.Series(np.where(entry != 0, pos, np.nan), index=df.index).ffill().to_numpy()
        age = pos - last
        ex = age == self.hold
        a = atr(df, 24)
        if self.be_after > 0:
            okl = ~np.isnan(last)
            si = np.where(okl, last, 0).astype(int)
            fill = df["open"].shift(-1).to_numpy()[si]  # open of the bar after the signal
            sd = entry[si]
            stop0 = (self.stop_atr * a).to_numpy()[si]
            gain = sd * (df["close"].to_numpy() - fill)
            # age >= be_after >= 1 guarantees that the fill bar has already opened
            ex |= okl & (age >= self.be_after) & (gain >= self.be_r * stop0)
        if self.flat_hour is not None:
            ex |= h == self.flat_hour
        out["entry"] = entry
        out["exit"] = ex & (entry == 0)
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_atr * a
        out["score"] = z.abs()
        return out


@dataclass
class PriorWalkForward(WalkForward):
    """adaptive.WalkForward plus a prior: until `train_weeks` of history exist (or when no
    candidate has `min_trades` in the window) it trades candidate `prior` instead of sitting
    flat. Every other refit is exactly WalkForward's: trailing window only."""

    prior: int | None = None

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
            scores = [score_trades(t[(t["entry"] >= start - train) & (t["entry"] < start)],
                                   self.objective, self.min_trades) if learned else -math.inf
                      for t in tables]
            best = int(np.argmax(scores))
            if not math.isfinite(scores[best]):
                if self.prior is None:
                    continue
                best = self.prior
            rows = (utc >= start) & (utc < end)
            for col in ("entry", "exit", "stop_dist", "target_dist", "score"):
                out.loc[rows, col] = frames[best].loc[rows, col].to_numpy()
            out.loc[rows, "param_set"] = best
            if self.keep_log:
                self.log.append({"pair": pair, "from": str(start), "params": self.candidates[best],
                                 "learned": bool(learned and math.isfinite(scores[best])),
                                 "train_score": round(float(scores[best]), 3)
                                 if math.isfinite(scores[best]) else None})
        return out


# Risk: 1.5% a trade, max 2 trades/day, 2.5% daily stop. At double risk (3%/trade, same
# 2.5% stop) one full loss halts the day.
BASE = GoldXAsset(name="gold_xasset_base", risk_pct=1.5, max_positions=1,
                  max_trades_per_day=2, daily_stop_pct=2.5, pairs=("XAUUSD",))

# 18 sets: lookback x trigger threshold x target. Stop 2 ATR, hold 8, break-even from bar 1.
CANDIDATES = grid(lookback=[3, 6, 12], z_th=[0.75, 1.0, 1.25], target_atr=[0.8, 1.0])
PRIOR = CANDIDATES.index({"lookback": 6, "z_th": 1.0, "target_atr": 1.0})  # middle of the grid

STRATEGY = PriorWalkForward(name="gold_xasset", base=BASE, candidates=CANDIDATES,
                            train_weeks=8, refit_weeks=1, objective="sharpe", min_trades=10,
                            prior=PRIOR)
