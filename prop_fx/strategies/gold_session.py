"""gold_session: two session slots a day on XAUUSD, with direction logic re-learned weekly.

Slot 1 (London open): at `lon_entry` London time, look at the Asian-session move
(London 00:00 open -> now). Trade WITH it ("follow") or AGAINST it ("fade").
Slot 2 (New York open): at `ny_entry` New York time, look at the London-session move
(London 07:00 open -> now). Follow or fade it.

Each trade: stop = stop_atr x ATR(24h), target = tgt_r x stop (tgt_r < 1 = high-win-rate
bracket), time exit at `lon_exit` (London clock) / `ny_exit` (New York clock).
Clock times are converted with Europe/London and America/New_York, so UK and US DST,
including the 2-3 "mismatch" weeks each spring/autumn, are handled per session.
Bars are labelled by their OPEN time: a signal on the bar labelled h-1 is decided at h
and fills at the next bar's open (h).

`STRATEGY` wraps the base in `WalkForward`: every week it re-scores a small grid of
direction logic / entry hour / geometry on the trailing `train_weeks` only.
See tournament_gold/gold_session.md for the research, grid and learning journal.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import Strategy, atr
from ..adaptive import WalkForward, grid

MODES = {"follow": 1, "fade": -1, "off": 0, "long": 2, "short": -2}  # +-2 = fixed direction


@dataclass
class GoldSession(Strategy):
    lon_mode: str = "fade"
    lon_entry: int = 8  # London hour at which the London-slot trade is entered
    lon_exit: int = 12  # London hour at which it is flattened
    ny_mode: str = "fade"
    ny_entry: int = 9  # New York hour at which the NY-slot trade is entered
    ny_exit: int = 12  # New York hour at which it is flattened
    ny_ref: str = "london"  # NY-slot reference move: "london" (07:00 London open) | "nyopen" (08:00 NY)
    min_move_atr: float = 0.0  # prior-session |move| must be >= this many ATRs (0 = always)
    stop_atr: float = 1.5
    tgt_r: float = 0.6
    atr_n: int = 24
    bail_atr: float = 0.0  # >0: exit at the first hourly close >= bail_atr*ATR in profit (0 = off)
    trend_n: int = 0  # >0: skip trades against sign(close - SMA(trend_n) of daily closes)

    def prepare(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        a = atr(df, self.atr_n)
        lon = df.index.tz_convert("Europe/London")
        ny = df.index.tz_convert("America/New_York")
        lh, nh = pd.Series(lon.hour, index=df.index), pd.Series(ny.hour, index=df.index)
        lday = pd.Series(lon.normalize().tz_localize(None), index=df.index)
        weekday = pd.Series(lon.weekday, index=df.index)
        op, cl = df["open"], df["close"]

        # session anchors (opens), forward-filled within the London calendar day
        asia_open = op.where(lh == 0).groupby(lday).ffill()
        london_open = op.where(lh == 7).groupby(lday).ffill()
        nday = pd.Series(ny.normalize().tz_localize(None), index=df.index)
        ny_open = op.where(nh == 8).groupby(nday).ffill()

        entry = pd.Series(0, index=df.index, dtype=int)
        score = pd.Series(0.0, index=df.index)
        trend = self._trend(df) if self.trend_n else None

        def slot(sig_bar, move, mode):
            nonlocal entry, score
            d = MODES[mode]
            if d == 0:
                return
            ok = sig_bar & move.notna() & (move.abs() >= self.min_move_atr * a) & (move != 0)
            if abs(d) == 2:  # fixed-direction slot (bias re-learned by the walk-forward)
                side = pd.Series(int(np.sign(d)), index=df.index)
            else:
                side = (np.sign(move) * d).fillna(0).astype(int)
            if trend is not None:
                ok &= side * trend > 0
            entry = entry.mask(ok, side)
            score = score.mask(ok, (move.abs() / a).fillna(0))

        wk = weekday < 5
        slot(wk & (lh == self.lon_entry - 1), cl - asia_open, self.lon_mode)
        ny_anchor = london_open if self.ny_ref == "london" else ny_open
        slot(wk & (nh == self.ny_entry - 1), cl - ny_anchor, self.ny_mode)

        # never let the London exit flag kill a fresh NY trade: London exit only applies
        # before the NY entry hour on the NY clock
        exit_ = ((lh == self.lon_exit - 1) & (nh < self.ny_entry)) | (nh == self.ny_exit - 1)

        if self.bail_atr > 0:
            exit_ = exit_ | self._bailout(entry, exit_, op, cl, a)

        stop = self.stop_atr * a
        out["entry"] = entry.astype(int)
        out["exit"] = exit_.to_numpy()
        out["stop_dist"] = stop
        out["target_dist"] = self.tgt_r * stop if self.tgt_r > 0 else np.nan
        out["score"] = score
        return out

    def _bailout(self, entry, exit_, op, cl, a) -> pd.Series:
        """Flag the first close that is >= bail_atr*ATR beyond the (assumed) fill price.

        The fill is the open of the bar after the signal bar; a flag on bar j uses only
        bars up to j and is executed by the engine at bar j+1's open. Flags stop at the
        slot's own time-exit flag. Flags on bars with no open position are ignored by
        the engine."""
        flag = np.zeros(len(entry), dtype=bool)
        ent, ex = entry.to_numpy(), exit_.to_numpy()
        o, c, at = op.to_numpy(), cl.to_numpy(), a.to_numpy()
        for i in np.flatnonzero(ent != 0):
            if i + 1 >= len(o):
                break
            fill, side, thr = o[i + 1], ent[i], self.bail_atr * at[i]
            for j in range(i + 1, min(i + 12, len(o))):
                if ex[j] or (j > i + 1 and ent[j] != 0):
                    break
                if side * (c[j] - fill) >= thr:
                    flag[j] = True
                    break
        return pd.Series(flag, index=entry.index)

    def _trend(self, df: pd.DataFrame) -> pd.Series:
        """+1/-1: last COMPLETED UTC daily close vs its SMA(trend_n). No look-ahead."""
        daily = df["close"].resample("1D").last().dropna()
        sig = np.sign(daily - daily.rolling(self.trend_n).mean())
        sig.index = sig.index + pd.Timedelta("1D")
        avail = pd.DataFrame({"t": df.index + pd.Timedelta("1h")})
        m = pd.merge_asof(avail, sig.rename("s").rename_axis("k").reset_index(),
                          left_on="t", right_on="k", direction="backward")
        return pd.Series(m["s"].fillna(0).to_numpy(), index=df.index)


# Risk: 1.5% per trade, one position at a time, <= 2 trades per Prague day, so a worst day
# is two full stops = 3.0%; the 3.5% daily stop leaves 1.5% gap headroom under FTMO's 5%.
BASE = GoldSession(name="gold_session_base", risk_pct=1.5, max_positions=1,
                   max_trades_per_day=2, daily_stop_pct=3.5, pairs=("XAUUSD",),
                   bail_atr=0.25)  # learning cycle 6: bail-out exit (kept)

# 16 candidate sets: direction logic per slot x NY entry hour x target. Re-scored weekly.
CANDIDATES = grid(lon_mode=["follow", "fade"], ny_mode=["follow", "fade"],
                  ny_entry=[9, 10], tgt_r=[0.6, 0.8])

STRATEGY = WalkForward(name="gold_session", base=BASE, candidates=CANDIDATES,
                       train_weeks=12, refit_weeks=1, objective="expectancy", min_trades=10)
