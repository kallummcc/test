# Forex Prop-Firm Tournament: Rules for every bot

Five bots each champion one forex strategy built to **pass the FTMO 2-Step challenge**
(a $100k account, traded through MetaTrader 5). The bots research, build, backtest,
then attack each other's strategies and defend their own. The judge decides the winner
on **hidden out-of-sample data (Apr–Oct 2026)** that no bot can see.

## FTMO rules (enforced by `prop_fx/ftmo.py`)
- **Phase 1** needs +10%; **Phase 2** needs +5% of the initial balance. The target
  counts on closed balance with no open positions, and needs at least 4 trading days.
- **Maximum Daily Loss** is 5% of the initial balance, measured from the balance at
  midnight Prague time and **including floating losses**. The engine uses each bar's
  worst intrabar price.
- **Maximum Loss** is 10% of the initial balance, with equity measured the same way.
- Each phase is capped at 12 weeks; going past the cap counts as a timeout.
- **No positions over the weekend** (Standard account). The engine closes everything
  by Friday 20:00 UTC and opens nothing after Friday 16:00 UTC.
- No HFT, no tick scalping, no latency or news arbitrage: FTMO bans these, and our
  hourly data can't model them anyway.

## The code
- Interface: `prop_fx/strategies/__init__.py`. Example strategies: `prop_fx/strategies/donchian.py`
  and `prop_fx/strategies/random_entry.py`.
  Engine: `prop_fx/engine.py`. Challenge simulator: `prop_fx/ftmo.py`. Command line: `prop_fx/backtest.py`.
- Your strategy goes in **`prop_fx/strategies/<your_lane>.py`** and exports `STRATEGY`.
  `prepare(df, pair)` gets ONE pair's hourly bars: a UTC index with open/high/low/close and
  **no volume**. It returns per-bar `entry` (+1 long / −1 short / 0), `exit`, `stop_dist`,
  `target_dist`, `score`. Long and short are both allowed.
- Strategy-level settings: `risk_pct` (0.1–2.0% of the initial balance per trade),
  `max_positions` (1–8), `daily_stop_pct` (0.5–4.5%; stops trading for the day, useful
  as a guard against the 5% daily rule), and `pairs` (a subset of the 12).
- **No look-ahead.** Bar t may use only data up to and including bar t, and fills happen
  at the next bar's open. Use `higher_tf(df, "4h"/"1D")` for higher timeframes. It returns
  only bars that have fully closed. Using a raw `df.resample()` is look-ahead.
- Costs: per-pair spreads (`prop_fx/instruments.py`), 0.1-pip slippage, $5 commission
  per lot round trip. Swap is not modelled; mention it if your strategy holds overnight.
- Only write:
  - `prop_fx/strategies/<your_lane>.py`
  - `tournament_fx/<your_lane>.md`
  - `tournament_fx/critiques/<your_lane>.md`
  - scratch output under `tournament_fx/runs/<your_lane>/`

  Don't modify the engine or other bots' files. Don't commit, and don't touch `.env`.

## Data (in-sample only)
`data/fx/` holds 12 pairs: EURUSD GBPUSD USDJPY AUDUSD USDCAD USDCHF NZDUSD EURJPY GBPJPY
EURGBP AUDJPY EURCHF.
- `PAIR_1h.csv`: **2024-01-05 → 2026-03-31** (about 118 trading weeks)
- `PAIR_1d.csv`: daily bars from about 2003 → 2026-03-31. Use them for research and regime
  context. Strategies trade on hourly bars.

Anything after 2026-03-31 is hidden. Don't fetch newer FX prices from the web or any
other source, and don't open any directory outside `/home/user/test`. Breaking this
rule disqualifies you.

## Running
```bash
python -m prop_fx.backtest --strategy <your_lane> --data-dir data/fx --json
# --start/--end to split dev and validation; --trade-from DATE warms up indicators
# --spread-mult 2 to stress-test costs; --boot N sets the number of bootstrap challenges
```
The output has trade stats and `ftmo`. The `ftmo` section has `historical` (a challenge
started every week) and `bootstrap` (2,000 challenges built from randomly drawn weeks).

**Benchmarks to beat (in-sample, both phases passed):**
- `random_entry` (coin flips at 1% risk): **7.8%** bootstrap, 7.1% historical. This is the luck line.
- `donchian` baseline: **6.6%** bootstrap, −61.5% net.

## Overfitting discipline (critics will check)
- Base the strategy on published or well-documented evidence and cite sources.
- Develop on 2024-01 → 2025-06 and validate on 2025-07 → 2026-03. Report both.
- Count and report **every variant you tried**.
- Tuning `risk_pct` is legitimate, since risk sizing is a real prop-firm skill. But a high
  pass rate from extreme risk on a zero-edge signal is just gambling. Show your **edge**
  (net expectancy per trade, profit factor) separately from the pass rate.

## How the judge picks the winner
1. **Hold-out pass rate for both phases** (bootstrap over the hidden weeks), with
   the Phase 1 fail rate and net expectancy as qualifiers. It must beat `random_entry`
   on the same hold-out.
2. Robustness that survives the debate: dev vs validation consistency, the number of
   variants tried, the 2× spread stress test, and the number of trades.
3. Argument quality. Claims a critic disproved with a backtest count against you.
