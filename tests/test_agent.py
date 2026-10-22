from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from t212_agent import agent as agent_mod
from t212_agent.agent import Agent, ManagedPosition
from t212_agent.config import Config, parse_symbols
from t212_agent.risk import RiskManager
from t212_agent.strategy import Action, evaluate

NY = ZoneInfo("America/New_York")


def make_bars(closes, start="2026-10-21 09:30"):
    idx = pd.date_range(start, periods=len(closes), freq="5min", tz=NY)
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes + 0.2, "low": closes - 0.2, "close": closes,
         "volume": 1000.0},
        index=idx,
    )


class FakeClient:
    dry_run = False

    def __init__(self, held=None):
        self.orders = []
        self.held = held or {}

    def account_cash(self):
        return {"total": 10_000, "free": 10_000}

    def positions(self):
        return [{"ticker": t, "quantity": q} for t, q in self.held.items()]

    def market_order(self, ticker, quantity):
        self.orders.append((ticker, quantity))
        self.held[ticker] = self.held.get(ticker, 0) + quantity
        return {"id": len(self.orders)}


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agent_mod, "STATE_FILE", tmp_path / "state.json")


def cfg():
    return Config(api_key="x", symbols={"AAPL_US_EQ": "AAPL"})


def test_parse_symbols():
    assert parse_symbols("AAPL_US_EQ:AAPL, VOD_UK_EQ") == {
        "AAPL_US_EQ": "AAPL", "VOD_UK_EQ": "VOD"}


def test_bull_cross_above_vwap_buys():
    closes = [100 - i * 0.1 for i in range(30)] + [97.5 + i for i in range(10)]
    bars = make_bars(closes)
    signals = [evaluate(bars.iloc[:n], 9, 21, 14, in_position=False).action
               for n in range(25, len(bars) + 1)]
    # Exactly one entry, on the bar where the fast EMA crosses the slow one.
    assert signals.count(Action.BUY) == 1


def test_flat_market_holds():
    sig = evaluate(make_bars([100.0] * 40), 9, 21, 14, in_position=False)
    assert sig.action is Action.HOLD


def test_risk_sizing_respects_caps():
    rm = RiskManager(1.0, 20.0, 3, 2.0, 10)
    # Risk budget 100 / 1 per share = 100 shares, but 20% cap = 2000/100 = 20 shares.
    assert rm.size(10_000, 10_000, 100, 99) == 20
    # Cash-limited.
    assert rm.size(10_000, 500, 100, 99) == 4.9


def test_daily_loss_limit():
    rm = RiskManager(1.0, 20.0, 3, 2.0, 10)
    rm.reset_day(10_000)
    assert not rm.daily_loss_hit(9_850)
    assert rm.daily_loss_hit(9_800)
    assert rm.can_open(0, 9_800)[0] is False


def test_stop_loss_sells_managed_position():
    client = FakeClient(held={"AAPL_US_EQ": 10})
    bars = make_bars([100.0] * 40)
    a = Agent(cfg(), client, bars_fn=lambda *_: bars)
    a.positions["AAPL_US_EQ"] = ManagedPosition("AAPL_US_EQ", 10, 105, 101, 110, "")
    a.step(datetime(2026, 10, 21, 11, 0, tzinfo=NY))
    assert client.orders == [("AAPL_US_EQ", -10)]
    assert not a.positions


def test_end_of_day_flattens_only_managed_positions():
    client = FakeClient(held={"AAPL_US_EQ": 5, "TSLA_US_EQ": 3})  # TSLA is a user holding
    bars = make_bars([100.0] * 40)
    a = Agent(cfg(), client, bars_fn=lambda *_: bars)
    a.positions["AAPL_US_EQ"] = ManagedPosition("AAPL_US_EQ", 5, 100, 95, 110, "")
    a.step(datetime(2026, 10, 21, 15, 55, tzinfo=NY))
    assert client.orders == [("AAPL_US_EQ", -5)]


def test_no_trading_outside_session():
    client = FakeClient()
    a = Agent(cfg(), client, bars_fn=lambda *_: make_bars([100.0] * 40))
    a.step(datetime(2026, 10, 24, 11, 0, tzinfo=NY))  # Saturday
    a.step(datetime(2026, 10, 21, 8, 0, tzinfo=NY))
    assert client.orders == []


def test_live_requires_explicit_acknowledgement(monkeypatch):
    monkeypatch.delenv("I_UNDERSTAND_THIS_TRADES_REAL_MONEY", raising=False)
    c = Config(api_key="x", symbols={"A": "A"}, environment="live", dry_run=False)
    with pytest.raises(ValueError):
        c.validate()
