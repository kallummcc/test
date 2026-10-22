"""Intraday market data.

The Trading 212 API does not provide price history, so bars come from Yahoo
Finance via yfinance. Yahoo data can be delayed; swap in a real-time feed by
implementing `get_bars` with the same return shape.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


def get_bars(symbol: str, interval: str = "5m", period: str = "5d") -> pd.DataFrame:
    """Return OHLCV bars indexed by timestamp, columns: open high low close volume."""
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=period, interval=interval, prepost=False)
    if df.empty:
        log.warning("No bars returned for %s", symbol)
        return df
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    return df.dropna()
