# Short Interest Effect – Long Only (QuantConnect)

A LEAN/QuantConnect version of Quantpedia's *Short Interest Effect – Long Only* strategy
(Boehmer, Huszar & Jordan, *The Good News in Short Interest*).

## Rules

1. Universe: NYSE, AMEX and NASDAQ common stocks (no ADRs), price above $5.
2. Optional liquidity filter: keep the most traded 50% by dollar volume. The paper finds
   the effect is strongest in heavily traded stocks. Set `liquidity_fraction` = 1.0 to turn it off.
3. Score each stock by its short-interest ratio, using the latest *published* short interest
   divided by shares outstanding.
4. Hold the lowest 1st percentile, with a minimum of 10 and a maximum of 100 names.
5. Weight the stocks equally and rebalance monthly.

## Short interest data

LEAN has no built-in short interest dataset, so the algorithm reads a CSV:

```
date,ticker,short_interest,avg_daily_volume
2024-01-12,AAPL,105000000,55000000
```

`date` is the FINRA settlement date. The algorithm adds `publication_lag_days` (12 by default)
before using a record, so it never trades on data before FINRA has published it.

To build the file, run `build_short_interest_csv.py` on your own machine. It pulls FINRA's
public Consolidated Short Interest API. Then either:

- upload the CSV to the Object Store under the key `short_interest.csv`, or
- host it somewhere and set the `short_interest_url` parameter.

Data from any other vendor works too, as long as it uses the same columns.

## Parameters

| name | default | meaning |
|---|---|---|
| `short_interest_key` | `short_interest.csv` | Object Store key |
| `short_interest_url` | *(empty)* | URL to use if the key is missing |
| `metric` | `relative` | `relative` (SI / shares outstanding) or `days_to_cover` (SI / avg daily volume) |
| `percentile` | `0.01` | fraction of scored stocks to hold |
| `min_holdings` / `max_holdings` | `10` / `100` | limits on the number of holdings |
| `min_price` | `5.0` | minimum share price |
| `liquidity_fraction` | `0.5` | most-liquid fraction of the universe to keep |
| `publication_lag_days` | `12` | days added to the settlement date before data is used |
| `max_staleness_days` | `45` | records older than this are ignored |
