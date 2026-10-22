from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from prop_fx import engine, ftmo
from prop_fx.instruments import PAIRS, pip_value_usd
from prop_fx.strategies import Strategy, available, higher_tf, load


def fx_bars(weeks=4, start="2025-01-06", drift=0.0, vol=0.0008, seed=0, price=1.10):
    """Synthetic 24x5 hourly bars (Mon 00:00 -> Fri 21:00 UTC)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=weeks * 7 * 24, freq="h", tz="UTC")
    idx = idx[(idx.weekday < 4) | ((idx.weekday == 4) & (idx.hour < 21))]
    close = price * np.exp(np.cumsum(rng.normal(drift, vol, len(idx))))
    open_ = np.r_[close[0], close[:-1]]
    wick = np.abs(rng.normal(0, vol / 3, len(idx))) * close
    return pd.DataFrame({"open": open_, "close": close,
                         "high": np.maximum(open_, close) + wick,
                         "low": np.minimum(open_, close) - wick}, index=idx)


@dataclass
class AlwaysLong(Strategy):
    stop: float = 0.0020

    def prepare(self, df, pair):
        out = df.copy()
        out["entry"] = 1
        out["exit"] = False
        out["stop_dist"] = self.stop
        out["target_dist"] = np.nan
        out["score"] = 0.0
        return out


def test_pip_values():
    assert pip_value_usd(PAIRS["EURUSD"], {}) == pytest.approx(10.0)
    assert pip_value_usd(PAIRS["USDJPY"], {"USDJPY": 150.0}) == pytest.approx(100_000 * 0.01 / 150)
    assert pip_value_usd(PAIRS["EURGBP"], {"GBPUSD": 1.25}) == pytest.approx(12.5)


def test_stop_loss_costs_about_one_r():
    # Steady decline: every long is stopped out.
    df = fx_bars(weeks=1, drift=-0.0005, vol=0.0001)
    s = AlwaysLong(name="t", risk_pct=0.5, max_positions=1)
    res = engine.run(s, {"EURUSD": df})
    stops = [t for t in res.trades if t.reason == "stop"]
    assert stops
    for t in stops:
        assert -1.15 < t.r_multiple < -0.95  # 1R plus spread/slippage/commission
        assert t.lots == pytest.approx(500 / (20 * 10), abs=0.01)


def test_never_holds_over_weekend():
    res = engine.run(AlwaysLong(name="t", stop=0.05), {"EURUSD": fx_bars(weeks=3)})
    assert res.trades
    for t in res.trades:
        a, b = pd.Timestamp(t.entry_time), pd.Timestamp(t.exit_time)
        assert a.isocalendar().week == b.isocalendar().week
        assert b.weekday() < 4 or b.hour <= 20


def test_higher_tf_has_no_lookahead():
    df = fx_bars(weeks=1)
    d = higher_tf(df, "1D")
    # During Tuesday, the daily close available must be Monday's last close.
    tue = df.index[(df.index.weekday == 1) & (df.index.hour == 12)][0]
    monday_close = df[df.index.weekday == 0]["close"].iloc[-1]
    assert d.loc[tue, "close"] == pytest.approx(monday_close)
    # The 23:00 Monday bar closes at midnight, completing Monday's daily bar.
    mon23 = df.index[(df.index.weekday == 0) & (df.index.hour == 23)][0]
    assert d.loc[mon23, "close"] == pytest.approx(monday_close)


def _result(daily_pnls, bars_per_day=24, start="2025-01-06"):
    """EngineResult where each weekday makes `pnl` closed P&L at its last bar."""
    days = pd.bdate_range(start, periods=len(daily_pnls))
    times, realized, cum = [], [], 0.0
    for d, pnl in zip(days, daily_pnls):
        for h in range(bars_per_day):
            times.append(pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=h))
            if h == bars_per_day - 1:
                cum += pnl
            realized.append(cum)
    n = len(times)
    opened = np.zeros(n, dtype=int)
    opened[::bars_per_day] = 1
    return engine.EngineResult(pd.DatetimeIndex(times), np.array(realized), np.zeros(n),
                               np.zeros(n), np.ones(n, dtype=bool), opened)


def test_ftmo_pass_and_fail_rules():
    rules = ftmo.Rules(max_weeks=12)
    good = ftmo.weeks_from(_result([1_000] * 120), rules)  # +1%/day
    r = ftmo.run_challenge(good, rules)
    # +1%/day: phase 1 (+10%) on weekday 10, phase 2 (+5%) five weekdays later.
    assert r == {"phase1": "pass", "phase2": "pass", "weeks": 3, "days": 15,
                 "phase1_days": 10, "phase2_days": 5}

    # A -6% day breaches the 5% daily limit.
    bad_day = ftmo.weeks_from(_result([500, -6_000] + [1_000] * 60), rules)
    r = ftmo.run_challenge(bad_day, rules)
    assert r["phase1"] == "fail" and r["phase1_days"] == 2  # failed on day 2

    # Slow bleed through -10% fails the max loss even with no bad single day.
    bleed = ftmo.weeks_from(_result([-900] * 30), rules)
    assert ftmo.run_challenge(bleed, rules)["phase1"] == "fail"

    # Needs 4 trading days even if the target is hit on day one.
    fast = ftmo.weeks_from(_result([11_000, 0, 0, 0, 0] * 10), rules)
    out = ftmo.run_phase(fast, 10.0, rules)
    assert out[0] == "pass"


def test_bundled_strategies_load_and_run():
    bars = {"EURUSD": fx_bars(weeks=3, seed=1), "USDJPY": fx_bars(weeks=3, seed=2, price=150),
            "XAUUSD": fx_bars(weeks=3, seed=5, price=3000)}
    for name in available():
        res = engine.run(load(name), bars)
        summary = ftmo.evaluate(res, n_boot=20)
        assert summary["weeks"] >= 3, name


def test_gold_contract_specs():
    gold = PAIRS["XAUUSD"]
    # $0.01 move on 1 lot (100 oz) = $1; a $10 move = $1,000 per lot.
    assert pip_value_usd(gold, {}) == pytest.approx(1.0)
    df = fx_bars(weeks=1, drift=-0.0005, vol=0.0001, price=3000.0)
    res = engine.run(AlwaysLong(name="g", stop=10.0, risk_pct=1.0, max_positions=1),
                     {"XAUUSD": df})
    stop = next(t for t in res.trades if t.reason == "stop")
    assert stop.lots == pytest.approx(1.0)  # $1,000 risk / $10 stop / $100 per $1 per lot
    assert -1.1 < stop.r_multiple < -0.95


@dataclass
class FixedSide(Strategy):
    side: int = 1
    stop: float = 0.0030

    def prepare(self, df, pair):
        out = df.copy()
        hour = df.index.hour
        out["entry"] = np.where(hour == 8, self.side, 0)  # one trade a day
        out["exit"] = hour == 16
        out["stop_dist"] = self.stop
        out["target_dist"] = np.nan
        out["score"] = 0.0
        return out


def test_walk_forward_learns_from_the_past_only():
    from prop_fx.adaptive import WalkForward, grid

    df = fx_bars(weeks=10, drift=0.0003, vol=0.0003, seed=3)  # steady uptrend
    wf = WalkForward(name="wf", base=FixedSide(name="b", max_positions=1),
                     candidates=grid(side=[1, -1]), train_weeks=3, min_trades=3)
    out = wf.prepare(df, "EURUSD")
    weeks = pd.Series(out["param_set"].to_numpy(), index=df.index).resample("W-MON", label="left",
                                                                             closed="left").max()
    assert (weeks.iloc[:3] == -1).all()  # no history yet -> flat
    assert (weeks.iloc[4:] == 0).all()  # learned that long (side=+1) works in an uptrend
    assert wf.current_params() == {"side": 1}

    # No look-ahead: truncating the future doesn't change past decisions.
    cut = df.index[len(df) * 7 // 10]
    early = WalkForward(name="wf", base=FixedSide(name="b", max_positions=1),
                        candidates=grid(side=[1, -1]), train_weeks=3,
                        min_trades=3).prepare(df[df.index <= cut], "EURUSD")
    common = early.index
    pd.testing.assert_series_equal(early["entry"], out.loc[common, "entry"])


def test_max_trades_per_day_cap():
    df = fx_bars(weeks=2, seed=4)

    @dataclass
    class EveryBar(AlwaysLong):
        def prepare(self, df, pair):
            out = super().prepare(df, pair)
            out["exit"] = True  # flat after each bar, so it wants a new trade every hour
            return out

    res = engine.run(EveryBar(name="t", stop=0.01, max_positions=1, max_trades_per_day=2),
                     {"EURUSD": df})
    per_day = pd.Series(1, index=[pd.Timestamp(t.entry_time).tz_convert("Europe/Prague").date()
                                  for t in res.trades]).groupby(level=0).sum()
    assert per_day.max() == 2


def test_position_closed_before_missing_day():
    df = fx_bars(weeks=1, vol=0.0001, seed=8)
    wed = df.index[df.index.weekday == 2]
    gapped = df.drop(wed)  # a dropped day mid-week
    res = engine.run(AlwaysLong(name="t", stop=0.05, max_positions=1), {"EURUSD": gapped})
    gap_closes = [t for t in res.trades if t.reason == "data gap"]
    assert gap_closes and pd.Timestamp(gap_closes[0].exit_time).weekday() == 1


def test_scale_risk_doubles_position_size_and_walk_forward_base():
    from prop_fx.adaptive import WalkForward, grid
    from prop_fx.strategies import scale_risk

    df = fx_bars(weeks=1, drift=-0.0005, vol=0.0001)
    one = engine.run(AlwaysLong(name="t", risk_pct=0.5, max_positions=1), {"EURUSD": df})
    two = engine.run(scale_risk(AlwaysLong(name="t", risk_pct=0.5, max_positions=1), 2),
                     {"EURUSD": df})
    assert two.trades[0].lots == pytest.approx(2 * one.trades[0].lots)
    wf = WalkForward(name="wf", base=FixedSide(name="b", risk_pct=1.5), candidates=grid(side=[1]))
    wf2 = scale_risk(wf, 2)
    assert wf2.risk_pct == 3.0 and wf2.base.risk_pct == 3.0
    assert scale_risk(AlwaysLong(name="t", risk_pct=2.0), 3).risk_pct == 5.0  # capped
