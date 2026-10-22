"""Benchmark for the gold tournament: ~2 coin-flip trades a day on XAUUSD with a
high-win-rate geometry (target 0.6x the stop). Any win rate can be bought by
shrinking the target; this shows what that geometry gives with zero edge."""

from __future__ import annotations

from dataclasses import dataclass

from .random_entry import RandomEntry


@dataclass
class RandomGold(RandomEntry):
    pass


STRATEGY = RandomGold(name="random_gold", trades_per_day=3.0, stop_atr=2.0, target_r=0.6,
                      risk_pct=1.0, max_positions=1, max_trades_per_day=2, daily_stop_pct=3.0,
                      pairs=("XAUUSD",))
