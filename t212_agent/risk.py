"""Position sizing and daily risk limits."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class RiskManager:
    risk_per_trade_pct: float
    max_position_pct: float
    max_open_positions: int
    max_daily_loss_pct: float
    max_trades_per_day: int

    start_of_day_value: float | None = None
    trades_today: int = 0

    def reset_day(self, account_value: float) -> None:
        self.start_of_day_value = account_value
        self.trades_today = 0

    def daily_loss_hit(self, account_value: float) -> bool:
        if not self.start_of_day_value:
            return False
        drawdown = (self.start_of_day_value - account_value) / self.start_of_day_value
        return drawdown * 100 >= self.max_daily_loss_pct

    def can_open(self, open_positions: int, account_value: float) -> tuple[bool, str]:
        if self.daily_loss_hit(account_value):
            return False, "daily loss limit reached"
        if open_positions >= self.max_open_positions:
            return False, "max open positions reached"
        if self.trades_today >= self.max_trades_per_day:
            return False, "max trades per day reached"
        return True, ""

    def size(self, account_value: float, free_cash: float, price: float, stop: float) -> float:
        """Shares to buy so that hitting `stop` loses ~risk_per_trade_pct of the account."""
        per_share_risk = price - stop
        if price <= 0 or per_share_risk <= 0:
            return 0.0
        by_risk = account_value * self.risk_per_trade_pct / 100 / per_share_risk
        by_cap = account_value * self.max_position_pct / 100 / price
        by_cash = free_cash * 0.98 / price  # small buffer for FX fees / slippage
        qty = min(by_risk, by_cap, by_cash)
        # T212 supports fractional shares; round down to 2 dp (some instruments need fewer).
        return math.floor(qty * 100) / 100 if qty > 0 else 0.0
