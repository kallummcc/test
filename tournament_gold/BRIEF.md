# Gold (XAUUSD) Self-Learning Tournament: Rules for every bot

The user wants an FTMO bot (MT5, $100k 2-Step) that trades **XAUUSD about 2 times a day** with a
**high win rate**, and **keeps learning and optimising itself as it trades**. Five bots each
champion one approach. They research it, build it as a **self-optimising walk-forward
strategy**, improve it over several documented learning cycles, then attack each other and
defend their own. The judge decides on **hidden data (Apr–Oct 2026)**. On that data your
walk-forward keeps learning week by week, exactly as it would live.

## What the user asked for (scored)
| Requirement | Target |
|---|---|
| Instrument | XAUUSD only (`pairs=("XAUUSD",)`; cross-asset bots may *read* FX data as inputs) |
| Frequency | about **2 trades a day**: `max_trades_per_day=2`, and you must average **≥ 1.2/day** |
| Win rate | **≥ 60%**, *and* positive net expectancy (avg R > 0, PF > 1) |
| FTMO | pass both phases often, with a low Phase 1 fail rate and no 5% daily-limit breaches |
| Learns as it goes | built on `prop_fx.adaptive.WalkForward`, plus ≥ 3 documented learning cycles |

**The trap: a high win rate is cheap.** `random_gold` (coin flips, target 0.6× the stop) already
wins **58.9%** with zero edge (avg R +0.009) and passes both phases only **7.0%** of the time.
You must beat it on **both** win rate and expectancy. A 75% win rate that loses 3R on the
losers is worse than useless here, because the 5% daily limit punishes fat-tailed losses.

**Gold-specific trap:** gold rose from about $2,300 to $5,000+ in-sample. A long bias alone looks
brilliant. Report your long and short results separately, and show that the edge isn't just
"buy gold". The hold-out may not trend the same way.

## Data
- `data/gold/XAUUSD_1h.csv`: COMEX gold futures (GC=F) as the XAUUSD proxy, **2024-05-31 → 2026-03-31**.
  It trades about 23 hours a day, with a daily break around 21:00–22:00 UTC. It is cleaned:
  10 contract-roll days where Yahoo mixed two contracts were dropped
  (`prop_fx/gold_data.py`). Prices sit a few dollars above spot (the futures basis), and
  intraday moves track spot closely.
- `data/gold/XAUUSD_1d.csv`: daily bars, 2000 → 2026-03-31. Use them for research only;
  continuous-contract roll jumps aren't removed from the daily file.
- `data/fx/*.csv`: 12 FX pairs, hourly and daily, through 2026-03-31. Use these as
  **inputs** only (for example USD strength).
  Read them from `os.environ.get("FX_DATA_DIR", "data/fx")` so the judge can point you at
  the hold-out.
- Costs (`prop_fx/instruments.py`): $0.30 spread, $5 per lot commission, 0.1-pip slippage.
  One lot is 100 oz, so a $1 move is $100 per lot. Leverage is capped at 1:30.
  Nothing after 2026-03-31 is available to you. Don't fetch newer gold or FX prices,
  and don't open any directory outside `/home/user/test`; either one disqualifies you.

## How to build it
1. A base strategy, `prop_fx/strategies/gold_<lane>.py`, with tunable fields. The interface
   is in `prop_fx/strategies/__init__.py`. Stops and targets are distances in dollars.
2. Wrap it in `WalkForward` (`prop_fx/adaptive.py`):
   - Give it a candidate grid; keep it small (≤ ~60 sets).
   - Use `train_weeks` and `refit_weeks`.
   - Use an objective: `expectancy`, `win_rate`, `sharpe`, `pass_score`, or add your own
     scorer in your own module.

   The module must export `STRATEGY = WalkForward(...)`. Every refit uses only trailing
   data, and the first `train_weeks` of any data set are flat while it learns.
3. **Learning cycles (at least 3), each logged in your write-up:**
   - **Diagnose:** look at the walk-forward out-of-sample trades. Find out where it loses
     (time of day, regime, side, stop vs target hits).
   - **Hypothesise one change:** a new filter, exit, grid axis or objective.
   - **Re-run the walk-forward.**
   - **Keep the change or revert it**, with numbers.

   This is how your bot "learns". Changing the code because of a result counts as using that
   data, so say which data each cycle looked at. Keep the last ~25% of in-sample
   (2025-11 → 2026-03) as a **final check** that you look at as rarely as possible, and
   report how often you looked.
4. `risk_pct`, `daily_stop_pct`, `max_positions` and `max_trades_per_day=2` are your
   choices; justify them. At 2 trades a day, `daily_stop_pct` should leave room under 5%
   even if both trades lose.

## Running
```bash
python -m prop_fx.backtest --strategy gold_<lane> --data-dir data/gold --json
# --end 2025-10-31 for the development period; full run for the final check
# --spread-mult 2 for the cost stress test
python -m prop_fx.backtest --strategy random_gold --data-dir data/gold --json   # benchmark
```
The JSON includes `win_rate_pct`, `trades_per_day`, `avg_r`, `profit_factor`, `by_year_pct`,
and `ftmo` (bootstrap and historical pass rates). For the long/short split and time-of-day
analysis, use `--out DIR` and read `DIR/trades.csv`. To see what the bot learned, print
`STRATEGY.log` after a run.

## Files you may write
- `prop_fx/strategies/gold_<lane>.py`
- `tournament_gold/gold_<lane>.md`: pitch and learning journal
- `tournament_gold/critiques/gold_<lane>.md` (in the debate round)
- `tournament_gold/runs/gold_<lane>/` for scratch work

Don't modify the engine or shared files, and don't edit another bot's files. If you
believe the engine has a bug, describe it in your write-up. Don't commit.

## How the judge picks the winner
The hold-out is scored on the hidden data, with walk-forward learning continuing through it.
1. **Hard requirements:** win rate ≥ 60%, trades a day ≥ 1.2, avg R > 0, and no daily-limit
   breaches. A strategy that misses any of these can't win.
2. **Bootstrap pass rate for both phases** and Phase 1 fail rate. It must beat `random_gold`.
3. **Robustness:** the 2× spread test, long and short both contributing, consistency on the
   final-check period, and the size of the grid and number of variants tried.
4. **Debate:** claims a critic disproved with a backtest count against you.
