# Strategy Tournament — Rules for every bot

Five bots each champion one intraday strategy for a **£1,000 Trading 212 Invest/ISA
account** trading **Nasdaq-100 stocks**. The bots research, build, backtest, then
attack each other's strategies and defend their own. The winner is decided by the
judge on **hidden out-of-sample data** that no bot can see.

## Hard constraints (from the broker and account)
- **Long only.** No shorting, no leverage, no options, no ETFs (UK retail can't buy US ETFs).
- **Flat every night.** The engine force-sells 10 min before the close.
- Market orders only. Each side pays **2 bps slippage + 0.15% FX fee** (GBP account
  trading USD shares), so a round trip costs about **0.34%**. That is the default, and
  the judge scores with it. Also report `--fx-fee-pct 0` (a USD account) as a secondary number.
- Fractional shares are allowed. The engine sizes positions with `RiskManager`: by default
  0.5% of equity at risk per trade, at most 20% of equity per position, 3 open positions,
  10 trades a day, and a 2% daily loss halt. You may change these through `overrides`,
  within the ranges in `ALLOWED_OVERRIDES` (`t212_agent/strategies/__init__.py`).

## The code
- Read `t212_agent/strategies/__init__.py` (interface), `t212_agent/strategies/ema_vwap.py`
  (example) and `t212_agent/backtest.py` (engine: next-bar-open fills, intrabar
  stops/targets, the stop counts first when both are hit).
- Your strategy goes in **`t212_agent/strategies/<your_lane>.py`** and exports `STRATEGY`.
  `prepare(df)` gets ONE symbol's bars: a DatetimeIndex in America/New_York, regular
  session only, with columns open/high/low/close/volume. It must return per-bar
  `entry, exit, stop_dist, target_dist, score`.
  `interval` is `"5m"` or `"1h"`.
- **No look-ahead.** Bar t may use only data up to and including bar t. Signals fill at
  the next bar's open. (Hint: `df.index.date` groups sessions; anything computed from
  a whole day must use `.shift()` / expanding windows.)
- Don't modify the engine or anyone else's files. Only write:
  - `t212_agent/strategies/<your_lane>.py`
  - `tournament/<your_lane>.md` (your pitch, rebuttal, and so on)
  - `tournament/critiques/<your_lane>.md` (in the debate round)
  - scratch output under `tournament/runs/<your_lane>/`
- Don't commit or push. Don't touch `.env`.

## Data (in-sample only)
`data/insample/` holds the 100 Nasdaq-100 stocks:
- `SYMBOL_5m.csv`: 5-minute bars, **2026-07-30 → 2026-09-23** (39 sessions)
- `SYMBOL_1h.csv`: hourly bars, **2023-11-24 → 2026-09-23** (~2.8 years)

Data after 2026-09-23 is the judge's hidden hold-out. Don't try to get more recent
data from the web or anywhere else; doing so disqualifies you.

## Running a backtest
```bash
python -m t212_agent.backtest --source csv --data-dir data/insample --symbols all \
    --strategy <your_lane> --json --out tournament/runs/<your_lane>
# optional: --start / --end to split dev vs validation, --trade-from DATE to warm up indicators
```
Baseline to beat (`ema_vwap`, 5m, all 100 stocks, in-sample): **£1,000 → £786 (−21.4%)**,
390 trades, profit factor 0.40. Buy & hold of the universe: +3.6%.

## Overfitting discipline (critics will check)
- Base the strategy on published or well-documented evidence and cite sources.
- Split your in-sample data: develop on the earlier ~2/3 and validate on the last ~1/3.
  Report both.
- Keep a count of **every parameter variant you tried** and report it. Lots of tuning
  for a tiny gain will be attacked.
- With £1,000 and a 0.34% round-trip cost, turnover kills. Show the gross vs net effect.

## How the judge picks the winner
1. **Hold-out net return** at default costs (GBP account), with the **Sharpe ratio**
   and **max drawdown** as qualifiers. A strategy that loses money on the hold-out cannot win.
2. Robustness evidence that survived the debate: dev vs validation consistency,
   the parameter count, and the number of trades (a sample that's too small is weak evidence).
3. The quality of the arguments. Claims that a critic disproved with a backtest count against you.
