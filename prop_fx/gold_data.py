"""Gold (XAUUSD proxy) data: Yahoo COMEX gold futures (GC=F), cleaned.

Spot XAUUSD isn't on Yahoo or Alpaca, and Alpaca's PAXG/USD has no 2024-2025
bars and ~3x inflated hourly ranges. GC=F trades ~23h a day like XAUUSD and
moves almost tick-for-tick with spot intraday (a small basis aside), but around
contract rolls Yahoo mixes two contracts, producing $30-60 phantom wicks for a
few days. `clean_futures` drops those days.

    python -m prop_fx.gold_data --out data/gold          # download + clean
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def contaminated_days(df: pd.DataFrame, wick_mult: float = 3.5, min_bars: int = 4) -> list:
    """Days with >= min_bars bars whose wick exceeds wick_mult x the rolling median range."""
    med = (df["high"] - df["low"]).rolling(200, min_periods=20).median()
    body_lo = df[["open", "close"]].min(axis=1)
    body_hi = df[["open", "close"]].max(axis=1)
    bad = ((body_lo - df["low"]) > wick_mult * med) | ((df["high"] - body_hi) > wick_mult * med)
    per_day = bad.groupby(df.index.tz_convert("UTC").date).sum()
    return sorted(per_day[per_day >= min_bars].index)


def clean_futures(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    days = contaminated_days(df)
    keep = ~pd.Index(df.index.tz_convert("UTC").date).isin(days)
    return df[keep], days


def download(out: Path) -> None:
    import yfinance as yf

    out.mkdir(parents=True, exist_ok=True)
    for interval, period in (("1h", "730d"), ("1d", "max")):
        d = yf.download("GC=F", period=period, interval=interval, progress=False,
                        auto_adjust=False)
        d.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in d.columns]
        d = d[["open", "high", "low", "close"]].dropna()
        if interval == "1h":
            d.index = pd.to_datetime(d.index, utc=True)
            d, days = clean_futures(d)
            print(f"dropped {len(days)} contract-roll days: {days}")
        d.rename_axis("timestamp").to_csv(out / f"XAUUSD_{interval}.csv")
        print(interval, len(d), d.index[0], d.index[-1])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="data/gold")
    download(Path(p.parse_args().out))
