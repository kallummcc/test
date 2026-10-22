from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from prop_fx import mt5_trader
from prop_fx.mt5_trader import MAGIC, MT5Trader, TraderConfig
from prop_fx.strategies import Strategy

NOW = datetime(2026, 3, 4, 10, 0, 30, tzinfo=timezone.utc)  # a Wednesday
SERVER_OFFSET_H = 2


class FakeMT5:
    TIMEFRAME_H1 = 16385
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    POSITION_TYPE_BUY, POSITION_TYPE_SELL = 0, 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TRADE_RETCODE_DONE = 10009

    def __init__(self, now=NOW):
        self.now = now
        self.balance = 100_000.0
        self.equity = 100_000.0
        self.positions = []
        self.sent = []

    def account_info(self):
        return SimpleNamespace(balance=self.balance, equity=self.equity)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(time=self.now.timestamp() + SERVER_OFFSET_H * 3600,
                               bid=1.1000, ask=1.1001)

    def symbol_info(self, symbol):
        return SimpleNamespace(trade_tick_value=1.0, trade_tick_size=0.00001, volume_step=0.01,
                               volume_min=0.01, volume_max=50.0, digits=5, filling_mode=1)

    def copy_rates_from_pos(self, symbol, tf, start, count):
        end = pd.Timestamp(self.now).floor("h")  # current forming bar
        idx = pd.date_range(end=end, periods=count, freq="h")
        server = ((idx + pd.Timedelta(hours=SERVER_OFFSET_H)) - pd.Timestamp(0, tz="UTC")
                  ) // pd.Timedelta(seconds=1)
        close = 1.10 + np.linspace(0, 0.01, count)
        return np.array(list(zip(server, close, close + 0.0005, close - 0.0005, close)),
                        dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                               ("close", "f8")])

    def positions_get(self):
        return self.positions

    def order_send(self, req):
        self.sent.append(req)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="done")


@dataclass
class LongOnLastBar(Strategy):
    def prepare(self, df, pair):
        out = df.copy()
        out["entry"] = 1
        out["exit"] = False
        out["stop_dist"] = 0.0020
        out["target_dist"] = 0.0040
        out["score"] = 1.0
        self.seen_last = df.index[-1]
        return out


@pytest.fixture(autouse=True)
def tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mt5_trader, "STATE_FILE", tmp_path / "state.json")


def make(mt5=None, **cfg):
    mt5 = mt5 or FakeMT5()
    strat = LongOnLastBar(name="t", risk_pct=0.5, max_positions=2, pairs=("EURUSD",))
    trader = MT5Trader(TraderConfig(dry_run=False, **cfg), mt5, strat, now_fn=lambda: mt5.now)
    return trader, mt5, strat


def test_uses_closed_bars_in_utc():
    trader, mt5, strat = make()
    df = trader.closed_bars("EURUSD")
    # The 10:00 UTC bar is still forming at 10:00:30, so the last closed bar is 09:00 UTC.
    assert df.index[-1] == pd.Timestamp("2026-03-04 09:00", tz="UTC")


def test_order_has_server_side_stop_target_and_risk_size():
    trader, mt5, _ = make()
    trader.on_bar()
    assert len(mt5.sent) == 1
    req = mt5.sent[0]
    # $500 risk / (0.0020 * $100,000 per price unit) = 2.5 lots
    assert req["volume"] == pytest.approx(2.5)
    assert req["sl"] == pytest.approx(1.1001 - 0.0020)
    assert req["tp"] == pytest.approx(1.1001 + 0.0040)
    assert req["magic"] == MAGIC


def test_acts_once_per_bar():
    trader, mt5, _ = make()
    trader.on_bar()
    trader.on_bar()
    assert len(mt5.sent) == 1


def test_daily_guard_flattens_and_halts():
    trader, mt5, _ = make()
    trader.guard()  # records day-start balance
    mt5.positions = [SimpleNamespace(symbol="EURUSD", magic=MAGIC, type=0, volume=1.0,
                                     ticket=7, profit=-4100.0)]
    mt5.equity = 95_900.0  # -4.1% on the day, past the 4% guard
    assert trader.guard() is False
    assert mt5.sent and mt5.sent[0]["position"] == 7
    mt5.sent.clear()
    trader.on_bar()
    assert mt5.sent == []  # no new trades for the rest of the day


def test_ignores_positions_from_other_bots_or_manual_trades():
    trader, mt5, _ = make()
    mt5.positions = [SimpleNamespace(symbol="EURUSD", magic=1, type=0, volume=1.0, ticket=9,
                                     profit=0.0)]
    trader.close_all("test")
    assert mt5.sent == []


def test_friday_evening_closes_everything():
    friday = datetime(2026, 3, 6, 19, 58, tzinfo=timezone.utc)
    trader, mt5, _ = make(mt5=FakeMT5(now=friday))
    mt5.positions = [SimpleNamespace(symbol="EURUSD", magic=MAGIC, type=1, volume=0.5,
                                     ticket=3, profit=10.0)]
    assert trader.guard() is False
    assert mt5.sent[0]["type"] == FakeMT5.ORDER_TYPE_BUY  # closing a short


def test_stops_trading_when_target_reached():
    trader, mt5, _ = make(phase_target_pct=10)
    mt5.balance = mt5.equity = 110_500.0
    trader.on_bar()
    assert mt5.sent == []


def test_risk_multiplier_doubles_lots():
    trader, mt5, _ = make(risk_mult=2.0)
    trader.on_bar()
    assert mt5.sent[0]["volume"] == pytest.approx(5.0)  # 2 x 2.5 lots
