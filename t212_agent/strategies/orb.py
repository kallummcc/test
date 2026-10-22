"""Opening Range Breakout on "stocks in play" (long only).

Adapted from Zarattini, Barbon & Aziz (2024), "A Profitable Day Trading Strategy
For The U.S. Equity Market" (SSRN 4729284), and Zarattini & Aziz (2023), "Can Day
Trading Really Be Profitable?" (SSRN 4416622).

Paper rules (5-minute ORB on stocks in play):
  * opening range (OR) = the first 5-minute candle;
  * trade only stocks whose OR volume is unusually high versus the same window on
    the prior 14 sessions (relative volume, RV >= 1), ranked by RV;
  * direction from the OR candle: bullish candle -> long breakout of the OR high
    (bearish -> short, which a Trading 212 Invest/ISA account cannot do);
  * stop = 10% of the 14-day ATR; no target; exit at the close.

Adaptations for this engine and account (long only, market orders, 0.34% round trip):
  * the paper's 5-minute OR on 7,000 stocks loses to costs on 100 large caps with tight
    10%-ATR stops (see tournament/orb.md), so the submitted STRATEGY uses the 60-minute
    OR on hourly bars, where 2.8 years of data exist;
  * "in play" is made stricter (RV >= 5) because the paper's top-20 out of ~7,000 stocks
    are extreme-RV names, and only the fattest-tailed days pay for a 0.34% round trip;
  * the OR candle must be up 0.5%-4% (a clear direction but not an exhausted spike);
  * entry at the next bar's open after the OR completes (Zarattini & Aziz 2023 enter at
    the open of the candle after the OR), stop at the OR low, no target, out at the close;
  * relative volume and ATR use completed prior sessions only (shifted daily aggregates).

No look-ahead: the OR high/volume are only used from the bar that completes the OR
onwards, and everything daily is shifted by one session.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import Strategy


@dataclass
class OpeningRangeBreakout(Strategy):
    or_minutes: int = 5          # opening-range length (5 in the paper)
    lookback: int = 14           # days for relative volume and ATR (paper: 14)
    min_history: int = 5         # sessions needed before trading (data is short)
    rv_min: float = 1.0          # relative-volume threshold (paper: >= 1, take the top)
    stop_atr: float = 0.10       # stop = stop_atr * daily ATR (paper: 10%)
    stop_mode: str = "atr"       # "atr": stop_atr * ATR; "or_low": below the opening-range low
    min_or_ret: float = 0.0      # OR candle body (close/open - 1) must be at least this
    max_or_ret: float = np.inf   # ... and at most this
    require_bull_or: bool = True  # OR candle must close above its open (paper's direction rule)
    entry_mode: str = "breakout"  # "breakout": close > OR high; "open": enter right after OR
    last_entry: str = "11:00"    # no fresh breakout signals after this time (bar close)

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        bar_min = {"5m": 5, "1h": 60}[self.interval]
        n_or = max(1, self.or_minutes // bar_min)
        day = pd.Series(out.index.date, index=out.index)
        k = out.groupby(day.values).cumcount()  # bar number within session
        out["k"] = k.values

        # ---- opening range (known only once bar n_or-1 has closed)
        in_or = out["k"] < n_or
        g = out[in_or].groupby(day[in_or].values)
        or_tab = pd.DataFrame({
            "or_open": g["open"].first(),
            "or_close": g["close"].last(),
            "or_high": g["high"].max(),
            "or_low": g["low"].min(),
            "or_vol": g["volume"].sum(),
            "or_bars": g["open"].size(),
        })

        # ---- daily bars from completed sessions -> ATR and average OR volume (shifted)
        gd = out.groupby(day.values)
        daily = pd.DataFrame({"h": gd["high"].max(), "l": gd["low"].min(), "c": gd["close"].last()})
        prev_c = daily["c"].shift(1)
        tr = pd.concat([daily["h"] - daily["l"], (daily["h"] - prev_c).abs(),
                        (daily["l"] - prev_c).abs()], axis=1).max(axis=1)
        atr_prior = tr.rolling(self.lookback, min_periods=self.min_history).mean().shift(1)
        orv_prior = or_tab["or_vol"].rolling(self.lookback,
                                             min_periods=self.min_history).mean().shift(1)
        or_tab["rv"] = or_tab["or_vol"] / orv_prior
        or_tab["atr"] = atr_prior.reindex(or_tab.index)

        m = or_tab.reindex(day.values)
        m.index = out.index
        after_or = out["k"] >= n_or - 1          # OR fully known at this bar's close
        complete = m["or_bars"] == n_or
        ok_day = complete & (m["rv"] >= self.rv_min) & (m["atr"] > 0)
        if self.require_bull_or:
            ok_day &= m["or_close"] > m["or_open"]
        or_ret = m["or_close"] / m["or_open"] - 1
        ok_day &= (or_ret >= self.min_or_ret) & (or_ret <= self.max_or_ret)
        ok_day = ok_day.fillna(False).astype(bool)

        if self.entry_mode == "open":
            trig = ok_day & (out["k"] == n_or - 1)
        else:
            hh, mm = map(int, self.last_entry.split(":"))
            close_time = out.index + pd.Timedelta(minutes=bar_min)
            in_window = (close_time.hour * 60 + close_time.minute) <= hh * 60 + mm
            above = (out["close"] > m["or_high"]) & (out["k"] >= n_or) & after_or
            above = above.fillna(False)
            # first bar of the session that closes above the OR high
            first_above = above & (above.groupby(day.values).cumsum() == 1)
            trig = ok_day & first_above & in_window

        out["entry"] = trig.astype(bool)
        out["exit"] = False
        if self.stop_mode == "or_low":
            # Zarattini & Aziz (2023): stop at the other side of the opening range.
            # The fill is the next open, approximated by this bar's close; floor at 0.1 ATR.
            dist = np.maximum(out["close"] - m["or_low"], 0.1 * m["atr"])
        else:
            dist = self.stop_atr * m["atr"]
        out["stop_dist"] = dist.where(out["entry"], np.nan)
        out["target_dist"] = np.nan
        out["score"] = m["rv"].fillna(-np.inf)
        return out.drop(columns=["k"])


STRATEGY = OpeningRangeBreakout(
    name="orb",
    interval="1h",
    or_minutes=60,          # first hourly bar = opening range (9:30-10:30)
    rv_min=5.0,             # "in play": first-hour volume >= 5x its 14-day average
    min_or_ret=0.005,       # first hour up at least 0.5% ...
    max_or_ret=0.04,        # ... and at most 4% (not an exhausted spike)
    entry_mode="open",      # buy at the 10:30 open, right after the range completes
    stop_mode="or_low",     # stop at the opening-range low; no target; exit at the close
    overrides={
        "skip_first_minutes": 5,
        # Zarattini et al. risk 1% of equity per trade; signals are rare (~1 every 4 days)
        "risk_per_trade_pct": 1.0,
        "max_position_pct": 40.0,
    },
)
