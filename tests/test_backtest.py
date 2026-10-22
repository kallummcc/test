import numpy as np
import pandas as pd
import pytest

from t212_agent.backtest import Backtester, load_csv, regular_session, summarize, yearly_table
from t212_agent.config import Config

NY = "America/New_York"


def session_bars(days, seed=0, drift=0.0, vol=0.002, start="2021-03-01"):
    """Synthetic 5m regular-session bars (random walk) for mechanical tests only."""
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range(start, periods=days):
        idx.extend(pd.date_range(f"{d.date()} 09:30", f"{d.date()} 15:55", freq="5min", tz=NY))
    idx = pd.DatetimeIndex(idx)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, len(idx))))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, vol / 2, len(idx))) * close
    return pd.DataFrame({
        "open": open_, "close": close,
        "high": np.maximum(open_, close) + spread,
        "low": np.minimum(open_, close) - spread,
        "volume": rng.integers(1_000, 10_000, len(idx)).astype(float),
    }, index=idx)


def cfg():
    return Config(api_key="x", symbols={"A_US_EQ": "A", "B_US_EQ": "B"})


def test_flat_market_makes_no_trades():
    df = session_bars(5, vol=0.0)
    res = Backtester(cfg(), 1000).run({"A": df})
    assert res.trades == []
    assert res.equity.iloc[-1] == pytest.approx(1000)


def test_never_holds_overnight_and_respects_limits():
    c = cfg()
    bars = {"A": session_bars(60, seed=1), "B": session_bars(60, seed=2)}
    res = Backtester(c, 1000).run(bars)
    assert res.trades, "random walk should trigger some trades"
    for t in res.trades:
        entry, exit_ = pd.Timestamp(t.entry_time), pd.Timestamp(t.exit_time)
        assert entry.date() == exit_.date()
        assert entry.time() >= pd.Timestamp("09:45").time()
        assert exit_.time() <= pd.Timestamp("15:50").time()
        # Never more than 20% of a ~1000 account in one position.
        assert t.qty * t.entry_price <= 0.2 * 1000 * 1.5
    per_day = pd.Series([pd.Timestamp(t.entry_time).date() for t in res.trades]).value_counts()
    assert per_day.max() <= c.max_trades_per_day
    # Trade P&L should reconcile to the final balance.
    assert res.equity.iloc[-1] == pytest.approx(1000 + sum(t.pnl for t in res.trades), abs=0.05)


def test_costs_reduce_returns():
    bars = {"A": session_bars(40, seed=3)}
    free = Backtester(cfg(), 1000, slippage_bps=0, fx_fee_pct=0).run(bars)
    costly = Backtester(cfg(), 1000, slippage_bps=10, fx_fee_pct=0.15).run(bars)
    assert costly.equity.iloc[-1] < free.equity.iloc[-1]


def test_stop_loss_fills_at_stop_or_gap_open():
    res = Backtester(cfg(), 1000).run({"A": session_bars(60, seed=4)})
    stops = [t for t in res.trades if t.reason == "stop loss"]
    assert stops
    assert all(t.exit_price < t.entry_price for t in stops)


def test_summary_and_yearly_table():
    res = Backtester(cfg(), 1000).run({"A": session_bars(300, seed=5)})
    s = summarize(res)
    assert s["starting_balance"] == 1000
    assert s["trades"] == len(res.trades)
    table = yearly_table(res)
    assert list(table.index) == sorted(set(res.equity.index.year))


def test_csv_loader_and_session_filter(tmp_path):
    idx = pd.date_range("2022-01-03 13:00", periods=48, freq="5min", tz="UTC")  # 08:00-11:55 NY
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                      index=idx.rename("timestamp"))
    path = tmp_path / "X_5m.csv"
    df.to_csv(path)
    loaded = regular_session(load_csv(path), cfg())
    assert loaded.index.min().strftime("%H:%M") == "09:30"
    assert len(loaded) == 30


def test_alpaca_loader_follows_pagination(monkeypatch):
    from t212_agent import backtest

    pages = [
        {"bars": [{"t": "2022-01-03T14:30:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}],
         "next_page_token": "abc"},
        {"bars": [{"t": "2022-01-03T14:35:00Z", "o": 1.5, "h": 2, "l": 1, "c": 1.8, "v": 5}],
         "next_page_token": None},
    ]
    seen = []

    class Resp:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    def fake_get(url, params, headers, timeout):
        seen.append(dict(params))
        return Resp(pages[len(seen) - 1])

    monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(backtest.requests, "get", fake_get)
    df = backtest.load_alpaca("AAPL", "2022-01-03", "2022-01-04", "5m")
    assert len(df) == 2 and df["close"].tolist() == [1.5, 1.8]
    assert seen[1]["page_token"] == "abc"
    assert seen[0]["adjustment"] == "all" and seen[0]["timeframe"] == "5Min"


def test_trade_from_warms_up_without_trading():
    df = session_bars(30, seed=6)
    cutoff = pd.Timestamp(sorted(set(df.index.date))[15], tz=NY)
    res = Backtester(cfg(), 1000, trade_from=cutoff).run({"A": df})
    assert res.equity.index.min() >= cutoff
    assert all(pd.Timestamp(t.entry_time) >= cutoff for t in res.trades)
    assert res.equity.iloc[0] == pytest.approx(1000)


def test_all_bundled_strategies_produce_required_columns():
    from t212_agent import strategies

    df = session_bars(5, seed=7)
    for name in strategies.available():
        out = strategies.load(name).prepare(df)
        assert {"entry", "exit", "stop_dist", "target_dist", "score"} <= set(out.columns), name
        assert len(out) == len(df), name
