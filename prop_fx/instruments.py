"""Forex contract specs and USD conversion (account currency is USD)."""

from __future__ import annotations

from dataclasses import dataclass

LOT_UNITS = 100_000


@dataclass(frozen=True)
class Pair:
    symbol: str
    pip: float
    spread_pips: float  # typical raw spread on a prop-firm ECN feed
    contract: float = LOT_UNITS  # units of the base per 1.0 lot
    leverage: float = 100.0  # max account leverage the prop firm allows on this symbol

    @property
    def base(self) -> str:
        return self.symbol[:3]

    @property
    def quote(self) -> str:
        return self.symbol[3:]


# Spreads are deliberately a little wider than typical FTMO raw spreads so the
# backtest is not flattered (raw majors are often 0.0-0.3 pips at liquid hours).
PAIRS: dict[str, Pair] = {
    p.symbol: p
    for p in [
        Pair("EURUSD", 0.0001, 0.3),
        Pair("GBPUSD", 0.0001, 0.5),
        Pair("USDJPY", 0.01, 0.4),
        Pair("AUDUSD", 0.0001, 0.4),
        Pair("USDCAD", 0.0001, 0.6),
        Pair("USDCHF", 0.0001, 0.6),
        Pair("NZDUSD", 0.0001, 0.7),
        Pair("EURJPY", 0.01, 0.7),
        Pair("GBPJPY", 0.01, 1.2),
        Pair("EURGBP", 0.0001, 0.6),
        Pair("AUDJPY", 0.01, 0.8),
        Pair("EURCHF", 0.0001, 0.8),
        # Gold: 1 lot = 100 oz, quoted to $0.01. ~$0.30 spread is a typical
        # prop-firm XAUUSD spread outside news; leverage capped conservatively.
        Pair("XAUUSD", 0.01, 30.0, contract=100, leverage=30.0),
    ]
}

# Fallback conversion rates (USD per 1 unit of currency) when the pair needed
# for conversion is not in the backtest universe.
FALLBACK_USD_PER = {"USD": 1.0, "EUR": 1.10, "GBP": 1.30, "JPY": 1 / 150, "CHF": 1.15,
                    "CAD": 1 / 1.37, "AUD": 0.66, "NZD": 0.60, "XAU": 2500.0}


def usd_per_unit(ccy: str, prices: dict[str, float]) -> float:
    """USD value of one unit of `ccy`, using live prices of USD pairs when available."""
    if ccy == "USD":
        return 1.0
    direct, inverse = f"{ccy}USD", f"USD{ccy}"
    if prices.get(direct):
        return prices[direct]
    if prices.get(inverse):
        return 1.0 / prices[inverse]
    return FALLBACK_USD_PER[ccy]


def pip_value_usd(pair: Pair, prices: dict[str, float]) -> float:
    """USD value of a one-pip move on one standard lot."""
    return pair.pip * pair.contract * usd_per_unit(pair.quote, prices)


def notional_usd(pair: Pair, lots: float, prices: dict[str, float]) -> float:
    return lots * pair.contract * usd_per_unit(pair.base, prices)
