"""gold_xasset: XAUUSD traded on cross-asset (FX) information, self-tuned by walk-forward.

Idea
----
Gold is priced in dollars, and on hourly bars about 14% of its variance is the dollar
(corr about -0.37 with a USD strength index built from the 12 FX pairs). The rest is
gold's own, idiosyncratic flow. The base signal splits gold's recent move into
  * the part the dollar explains   (beta_t x USD-index move), and
  * the residual                   (gold move - beta_t x USD move).
A large residual move (gold moving on its own, not because of the dollar) is followed,
in the direction of the residual. `mode=-1` fades it instead (kept as a grid axis).

Rules (base strategy, one parameter set)
----------------------------------------
1. USD index = least-squares currency-strength decomposition of the 12 FX pairs
   (`fx_strength.currency_index`), read from os.environ["FX_DATA_DIR"] (default
   data/fx), clipped to the gold df's time window and aligned to gold bars with a
   backward as-of join (FX bar t closes at the same time as gold bar t).
2. beta_t = rolling OLS slope of hourly gold log-returns on USD-index returns over the
   trailing `beta_win` bars (only past data).
3. resid_L = gold log-return over `lookback` bars - beta_t x USD return over the same bars.
   z = resid_L / trailing std(resid_L, `z_win` bars).
4. Entry when |z| crosses above `z_th` (fresh signal only), side = mode x sign(z),
   optionally only if gold's raw move agrees (`confirm`), optionally only in `hours` (UTC).
5. Stop = `stop_atr` x ATR(24 h), target = `target_atr` x ATR (target < stop gives the
   high win rate the user asked for), time exit `hold` bars after the signal. An opposite
   fresh signal reverses the position (engine default).
6. Flat before the daily break: exit at the close of the 19:00 UTC bar, no signals 19-21 UTC
   (roll days / holidays leave holes there with $20-80 contract jumps).
7. Account: 1 position, max 2 trades a day, 2% risk, 4% daily stop (two full losers = 4%).

Learning-cycle history is in tournament_gold/gold_xasset.md.

`STRATEGY` wraps this in `prop_fx.adaptive.WalkForward`, which re-picks the parameter set
every week from the trailing `train_weeks` of walk-forward results.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import Strategy, atr
from ..adaptive import WalkForward, grid
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
    lookback: int = 12  # bars for the residual move
    z_th: float = 1.5
    z_win: int = 500  # bars for the z-score scale
    beta_win: int = 500  # bars for the rolling gold-on-USD beta
    mode: int = 1  # +1 follow the residual, -1 fade it
    confirm: bool = False  # require gold's raw move to agree with the residual
    stop_atr: float = 2.0
    target_atr: float = 1.0
    hold: int = 8  # bars after the signal before the time exit
    hours: tuple[int, ...] | None = None  # UTC signal hours allowed (None = all)
    fresh_only: bool = True  # True: only the bar where |z| crosses z_th; False: every bar beyond it
    haven_lb: int | None = None  # if set: longs need JPY/CHF up over this many bars, shorts down
    flat_hour: int | None = 19  # exit at the close of this UTC bar; no signals until the reopen

    def features(self, df: pd.DataFrame) -> pd.DataFrame:
        fx = fx_features(df)
        lg = np.log(df["close"])
        rg, ru = lg.diff(), fx["USD"].diff()
        cov = (rg * ru).rolling(self.beta_win, min_periods=100).mean() - (
            rg.rolling(self.beta_win, min_periods=100).mean()
            * ru.rolling(self.beta_win, min_periods=100).mean())
        var = ru.rolling(self.beta_win, min_periods=100).var(ddof=0)
        beta = cov / var
        pg, pu = lg.diff(self.lookback), fx["USD"].diff(self.lookback)
        resid = pg - beta * pu
        z = resid / resid.rolling(self.z_win, min_periods=100).std()
        haven = (fx["JPY"] + fx["CHF"]) / 2
        hv = haven.diff(self.haven_lb) if self.haven_lb else pd.Series(np.nan, index=df.index)
        return pd.DataFrame({"beta": beta, "pg": pg, "pu": pu, "resid": resid, "z": z, "hv": hv})

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        f = self.features(df)
        z = f["z"]
        fresh = (z.abs() > self.z_th)
        if self.fresh_only:
            fresh &= ~(z.shift(1).abs() > self.z_th)
        side = self.mode * np.sign(z)
        ok = fresh & z.notna()
        if self.confirm:
            ok &= np.sign(f["pg"]) == np.sign(z)
        if self.haven_lb:
            ok &= np.sign(f["hv"]) == side
        if self.hours is not None:
            ok &= np.isin(df.index.hour, self.hours)
        entry = np.where(ok, side, 0).astype(int)
        # time exit: `hold` bars after the most recent signal bar
        pos = np.arange(len(df))
        last = pd.Series(np.where(entry != 0, pos, np.nan), index=df.index).ffill()
        out["entry"] = entry
        out["exit"] = (pos - last.to_numpy()) == self.hold
        if self.flat_hour is not None:
            # Never hold through the daily break (21-23 UTC): roll days and holidays leave
            # holes there, and the next bar can jump $20-80 between contracts.
            h = df.index.hour
            late = (h >= self.flat_hour) & (h <= 21)
            out.loc[late, "entry"] = 0
            out["exit"] |= h == self.flat_hour
        a = atr(df, 24)
        out["stop_dist"] = self.stop_atr * a
        out["target_dist"] = self.target_atr * a
        out["score"] = z.abs()
        return out


# Grid: 18 sets. The walk-forward re-picks one every Monday from the trailing 4 weeks.
BASE = GoldXAsset(name="gold_xasset_base", risk_pct=2.0, max_positions=1,
                  max_trades_per_day=2, daily_stop_pct=4.0, pairs=("XAUUSD",))

CANDIDATES = grid(lookback=[3, 6, 12], z_th=[0.5, 0.75, 1.0], target_atr=[0.8, 1.0])

STRATEGY = WalkForward(name="gold_xasset", base=BASE, candidates=CANDIDATES,
                       train_weeks=4, refit_weeks=1, objective="expectancy", min_trades=10)
