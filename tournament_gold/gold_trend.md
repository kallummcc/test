# gold_trend: session-open intraday momentum on XAUUSD, self-tuning walk-forward (Bot 1)

**One line:** at 08:00 UTC (London) and 13:00 UTC (New York), go with the sign of gold's last 6/12/24-hour move. The stop is 1.5–2.5×ATR(24h) and the target 0.5–0.7× the stop. A break-even rule banks any profit of at least +0.1× the stop from the 1st or 2nd hour onward. There is a time exit at 4–8h and a flat at 20:00 UTC. A weekly walk-forward re-tunes 48 parameter sets on the trailing 12 weeks (Sharpe objective). Account settings: 1.5% risk, 1 position, 2 trades a day, 2.5% daily stop.

## 1. Research (sources)
- **Intraday momentum.** Gao, Han, Li & Zhou (JFE 2018) show that the first half-hour return, *measured from the previous close*, predicts the last half-hour return. Baltussen, Da, Lammers & Martens (JFE 2021) find "market intraday momentum" in 60+ futures, commodities included: the return over the rest of the day predicts the final 30 minutes. https://alphaarchitect.com/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/ , https://www3.nd.edu/~zda/intramom.pdf , https://ideas.repec.org/a/eee/jfinec/v142y2021i1p377-403.html
- **Gold-specific.** In Chinese gold futures, the first half-hour of the *active* session predicts later half-hour returns. When night trading launched, the predictive window moved to the new session open. In other words, momentum attaches to **session opens**, which is the premise of this strategy. https://ideas.repec.org/a/eee/finlet/v58y2023ipas154461232300394x.html , https://acfr.aut.ac.nz/__data/assets/pdf_file/0008/686816/4a-Z-Ivy-Zhou.pdf . Other commodity futures show the same pattern. https://ideas.repec.org/a/wly/jfutmk/v40y2020i4p632-650.html
- **Around-the-clock gold.** A CBS thesis (Donati & Jung) finds gold tends to rise in Asian hours and fall in Western hours, with effects around the London fix. These are diurnal flows, which is why each decision uses the *preceding* 6–24h return, mostly Asian and European hours, rather than a fixed long bias. https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/
- **Time-series momentum.** Moskowitz, Ooi & Pedersen (2012), whose sample includes gold, is the slow-horizon parent of this effect. https://papers.ssrn.com/abstract=2089463
- **Win rate vs expectancy.** Tight targets raise win rate and shrink the average win (6% vs 20% profit targets gave 69% vs 54% wins). Win rate alone is meaningless without the payoff ratio. https://trendinvestorpro.com/tcstrat-pt8-increasing-frequency-percent-profit-targets/ , https://www.tradezella.com/blog/trading-expectancy
- **Caveat:** I found no peer-reviewed COMEX-gold test of the exact session-open rule. The direct evidence is my own dev-period analysis, below.

**My dev-only exploration** (`runs/gold_trend/explore.py`, `explore2.py`, data before 2025-11-01). Breakouts and "strong bar" continuation were small and asymmetric. Short-side continuation was mostly negative: in a bull market, dips get bought. Fixed-time entries in the direction of the trailing move were the cleanest. After subtracting each hour's unconditional drift, the 13 UTC decision with a 12h lookback gave +0.25 ATR over the next 4h, and 08 UTC with a 6h lookback gave +0.17. **That table had 50 cells, so the 08/13 choice is data-mined (see weaknesses).**

## 2. Exact rules (`prop_fx/strategies/gold_trend.py`)
- **Decision bars.** Decisions are taken at the close of the bars ending 08:00 and 13:00 UTC; the fill is at the next open. Direction = sign(close − close `mom_hours` ago). The rule is symmetric: no long bias is built in.
- **Stop:** `stop_atr` × ATR(24h) in dollars.
- **Target:** `target_r` × stop.
- **Exits, all via exit signals at the next open:**
  - Break-even: from `be_after` bars after entry, exit at the first close at least +0.1× the stop in profit.
  - Time exit: `max_hold` bars after the signal.
  - Flat at 20:00 UTC, before the 21–22 UTC futures break.
  - The engine closes everything on Friday.
- **Opposite signal:** if the 13:00 signal is opposite to an open 08:00 trade, the engine reverses the position.
- **Walk-forward** (`WalkForward`, `train_weeks=12`, `refit_weeks=1`, `objective="sharpe"`, `min_trades=15`). The grid is 3 × 2 × 2 × 2 × 2 = **48 sets**:
  - `mom_hours` {6, 12, 24}
  - `stop_atr` {1.5, 2.5}
  - `target_r` {0.5, 0.7}
  - `max_hold` {4, 8}
  - `be_after` {1, 2}

  Every Monday it scores all 48 sets on the trailing 12 weeks of their trades and trades the best one for the week. The first 12 weeks of any data set are flat.
- **What it learned over the full run** (84 refits):
  - `mom_hours` 12 ×40, 24 ×32, 6 ×12
  - `stop_atr` 2.5 ×46, 1.5 ×38
  - `target_r` 0.7 ×49, 0.5 ×35
  - `max_hold` 8 ×65
  - `be_after` 1 ×51

  In March 2026 it had moved to 24h momentum with a 1.5 ATR stop.
- **Risk settings.**
  - `risk_pct=1.5`. With `max_positions=1` and `max_trades_per_day=2`, the worst normal day is two full stops, −3%, leaving 2% headroom under the 5% daily limit for gaps.
  - `daily_stop_pct=2.5`. After one full loss (−1.5%), the second trade is flattened at about −1% more.
  - 2.0% risk gave a marginally higher pass rate but tripled Phase 1 failures, from 5.5% to 14.2% (C3b), so I rejected it.
- **Implementation note.** The break-even rule rebuilds the fill price from the *latest* signal (the next bar's open). The truncation test shows no look-ahead: 0 mismatches in 200 cuts. If the 13:00 signal is skipped (for example, the 2-trades cap was already reached), the rule would apply to the wrong entry. With 2 decision slots and a 2-trade cap, that cannot happen.

## 3. Learning journal (all walk-forward runs on dev, 2024-05-31 → 2025-10-31; walk-forward out-of-sample from 2024-08-26)
Each cycle looked **only at dev walk-forward out-of-sample trades** (`runs/gold_trend/trades_*.csv`). Numbers are post-warm-up trades (`runs/gold_trend/wf_log.jsonl`). Bootstrap is over post-warm-up weeks.

| cycle | diagnosis (dev data) | single change | n | trades/day | win% | avg R | PF | boot pass_both / P1 fail | decision |
|---|---|---|---|---|---|---|---|---|---|
| C0 | baseline clock (08/13), 24-set grid, expectancy objective, 1% risk | – | 514 | 1.45 | 59.3 | +0.051 | 1.18 | 21.9 / 4.0 | baseline |
| C1 | win rate 59% (<60). Time exits: 128 trades, 41% win, −0.13R | break-even exit from bar 2 at +0.1×stop | 556 | 1.57 | **67.3** | +0.048 | 1.19 | 21.6 / 3.2 | **keep** (+8pp win rate, expectancy unchanged) |
| C2a | the parameter picked changes most weeks: noisy selection? | train 26 weeks | 421 | 1.55 | 68.9 | +0.051 | 1.22 | 18.1 / 0.7 | **revert**: on the same window +0.051 vs C1 +0.084 |
| C2b | same | objective `sharpe` | 547 | 1.54 | 69.8 | **+0.063** | 1.29 | 27.4 / 1.1 | **keep** (same-window +0.094 vs +0.084) |
| C3a | edge fine, pass rate low: target needs variance | risk 1.5%, daily stop 2.5% | 547 | 1.54 | 69.8 | +0.062 | 1.29 | **53.4 / 5.5** | **keep** |
| C3b | same | risk 2.0%, daily stop 3.0% | 549 | 1.55 | 68.5 | +0.050 | 1.22 | 56.0 / 14.2 (hist P1 fail 25.5) | revert: P1 fails triple |
| C4 | stops (91 at −1R) are the main loss | cut losers at −0.5×stop after 3 bars | 540 | 1.52 | 68.3 | +0.054 | 1.25 | 45.5 / 6.2 | **revert** |
| C5 | break-even timing fixed by me, not learned | add `be_after` {1,2} to the grid (24→48 sets) | 547 | 1.54 | **72.8** | **+0.075** | **1.38** | **64.5 / 2.5** | **keep → FINAL** |
| C5b | robustness: are 08/13 special? | hours (7,13) | 543 | 1.53 | 64.5 | +0.012 | 1.05 | 15.2 / 16.7 | diagnostic, shorts −0.009R |
| C5c | same | hours (9,14) | 556 | 1.57 | 63.3 | +0.011 | 1.05 | 13.9 / 15.4 | diagnostic, shorts −0.031R |
| C6a | UTC hours drift 1h vs sessions with DST | DST-aware 08:00 London/NY local | 518 | 1.46 | 70.7 | +0.039 | 1.17 | 35.1 / 15.6 | revert |
| C6b | same | 09:00 local | 540 | 1.52 | 68.7 | +0.031 | 1.14 | 27.8 / 9.3 | revert |
| C7 | let the bot learn hours {7/13, 8/13, 9/14} | hours as a grid axis | 538 | 1.52 | 70.6 | +0.038 | 1.17 | 33.7 / 12.6 | revert (selection noise) |
| C7b | smaller grid check | 16 sets (mom 12/24, max_hold 8) | 534 | 1.50 | 73.4 | +0.071 | 1.35 | 58.9 / 4.5 | not adopted (≈ C5) |

**Variant count:**
- 8 static probes (S01–S08: pullback, breakout, strong-bar, daily trend, 4 clock geometries; `static_log.jsonl`);
- 14 walk-forward runs (the table above);
- 86 exploration cells.

**Final-check holdout (2025-11 → 2026-03): looked at once, after freezing C5.** That look was a single batch of runs (full, final, 2× spread, random). No change was made after it.

## 4. Results (`python -m prop_fx.backtest --strategy gold_trend --data-dir data/gold`)

| run | trades | trades/day | win % | avg R | PF | net % | max DD | boot pass_both | boot P1 fail | hist pass_both | hist P1 fail | daily breaches |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev (`--end 2025-10-31`) * | 547 | 1.28 (1.54 traded) | 72.8 | +0.075 | 1.38 | +61.2 | −10.7 | 52.2% | 2.0% | 48.5% | 0.0% | 0 |
| dev, 2× spread | 547 | 1.28 | 72.4 | +0.063 | 1.32 | +51.7 | −11.1 | 43.2% | 3.0% | 45.6% | 2.9% | 0 |
| **final check** (`--trade-from 2025-11-01`) | 183 | **1.46** | **69.4** | **+0.055** | **1.23** | +14.7 | −9.1 | **41.9%** | 7.0% | 63.6% (n=11) | 0.0% | 0 |
| final check, 2× spread | 183 | 1.46 | 69.4 | +0.048 | 1.20 | +13.0 | −9.1 | 37.6% | 7.5% | 63.6% | 0.0% | 0 |
| full * | 730 | 1.32 | 71.9 | +0.070 | 1.34 | +75.9 | −10.7 | **52.8%** | 3.6% | 47.1% | 0.0% | 0 |
| full, 2× spread | 730 | 1.32 | 71.6 | +0.060 | 1.29 | +64.7 | −11.1 | 45.1% | 4.5% | 44.7% | 2.4% | 0 |
| random_gold, dev | 560 | 1.31 | 57.1 | −0.023 | 0.93 | −12.8 | −21.1 | 2.5% | 30.1% | 0.0% | 32.8% | 1 |
| random_gold, final | 160 | 1.28 | 59.4 | −0.024 | 0.93 | −3.6 | −13.2 | 3.5% | 23.7% | 0.0% | 25.0% | 0 |
| random_gold, full | 720 | 1.30 | 58.9 | +0.009 | 1.03 | +6.8 | −13.7 | 7.0% | 12.2% | 1.2% | 8.1% | 0 |

\* Includes the 12 flat learning weeks, which dilute trades/day and add timeouts to the bootstrap. The worst week in the full run was −4.3%. By year: 2024 +12.5% (from late August), 2025 +44.4%, 2026 Q1 +19.0%.

**Long vs short. Is it just "buy gold"? No: shorts earn more per trade than longs.**

| period | long n / win % / avg R / net | short n / win % / avg R / net |
|---|---|---|
| dev (traded) | 311 / 75.2 / +0.068 / +31.3% | 236 / 69.5 / **+0.085** / +29.8% |
| final check | 106 / 70.8 / +0.039 / +6.3% | 77 / 67.5 / **+0.075** / +8.5% |
| full | 417 / 74.1 / +0.060 / +37.6% | 313 / 69.0 / **+0.083** / +38.3% |

The signal is long 57% of the time, which is the bull market leaking into the trailing-return sign. P&L is split evenly between the two sides.

Final check by month (avg R): Nov −0.13, Dec +0.04, Jan +0.16, Feb +0.11, Mar +0.09. November 2025 was the one losing month.

## 5. Why the edge should persist
- Session-open momentum has a mechanism. Information and orders that build up while a major centre is closed (Asian/overnight flow into London, Europe into the COMEX open) are executed gradually after that centre opens: institutional order splitting, hedging demand, and the Baltussen gamma/hedging story. This is documented in many futures markets and in gold futures specifically.
- It is symmetric, and both sides pay in dev and in the final check. Shorts beat longs during a +100% gold rally, which a long-bias artefact would not do.
- The high win rate is *engineered*, not bought. Target 0.5–0.7× the stop plus a break-even rule gives about 70% wins. Unlike random_gold, which has the same geometry (57–59% wins, about 0R), the average R stays positive. The gap over random is about 12–15pp of win rate and +0.07–0.10R, on the same exits.
- It is cost-robust. 2× spread costs about 0.01R and pass rates stay at 38–45%. It had no daily-limit breaches in any run.
- It keeps adapting. Stop width, target, lookback and break-even timing re-fit weekly to the trailing 12 weeks. In the final check the selected lookback drifted to 24h without my intervention.

## 6. Known weaknesses (attack here)
1. **The session hours are hand-picked from dev and fragile.** Shifting both decision times by an hour (7/13 or 9/14) cuts dev avg R from +0.075 to about +0.01 and makes shorts negative. DST-aware local hours give +0.03 to +0.04R. Letting the bot learn the hours gives +0.038R. The 08/13 UTC pair came from a 50-cell dev table. The honest expectation for the edge is +0.02–0.05R, not +0.07. The final check (+0.055R) is encouraging but covers only 5 months and 183 trades.
2. **The edge per trade is thin.** About +0.06R; the PF of 1.2–1.4 comes with a 70% win rate. One bad month (Nov 2025: −0.13R over 34 trades) eats about 4% of the account.
3. **Pass rate depends on 1.5% risk.** At 1% risk, bootstrap pass_both was about 27%. The edge is shown separately in the avg R and PF columns.
4. **Learning warm-up.** The first 12 weeks of any data set are flat. If the judge starts the walk-forward cold on April 2026 data, the bot trades only from about July. It needs ≥12 weeks of prior hourly bars to trade from day one.
5. **The trades/day minimum is barely met.** The CLI reports 1.28–1.32 over runs that include the flat weeks; traded weeks average 1.46–1.54. If the hold-out includes a 12-week cold start, trades/day could fall below 1.2.
6. **The break-even exit is approximate.** It assumes the latest signal is the open position (true under the current config). Exits fire at the next bar's open, not intrabar, so the realised "break-even" can slip below +0.1R.
7. **Not modelled:**
   - news spikes at the 12:30/13:30 UTC US data releases (the 13:00 decision sits right after them; real spreads widen there);
   - swap (positions are flat by 20:00 UTC, so swap is negligible);
   - the futures-vs-spot basis.
8. **Short history.** About 22 months of hourly data with one dominant regime (a gold bull run with high volatility). A low-vol, range-bound gold market has not been tested.

Files: `prop_fx/strategies/gold_trend.py`. Scratch work, logs, trades and JSONs are in `tournament_gold/runs/gold_trend/`.

---

## Round 3: revision and rebuttal

### The one revision: warm-up prior (borrowed from gold_prop)
`STRATEGY` is now `PriorWalkForward`, a thin dataclass subclass of `prop_fx.adaptive.WalkForward` defined in `gold_trend.py`. The refit mechanics are unchanged: weekly refits, trailing 12 weeks, Sharpe objective, the same 48-set grid. The only change is what happens in **weeks where the learner has no fitted set**: the first 12 weeks of any data file, or a week where no candidate has ≥15 trades.
- **Before:** the bot sat flat in those weeks.
- **After:** it trades a fixed **prior**: `mom_hours=12, stop_atr=2.5, target_r=0.7, max_hold=8, be_after=1`.

The prior is the modal choice of each grid axis in the **dev-only** walk-forward log (`runs/gold_trend/log_C5_grid_be12.csv`, ≤ 2025-10). `be_after` was a 31/31 tie, broken towards 1. The prior was not tuned on any result.

Everything else is frozen from Round 1: 08/13 UTC decisions, `max_trades_per_day=2`, `max_positions=1`, 1.5% risk, 2.5% daily stop.

### Revisions I tested and rejected
All are logged in `runs/gold_trend/r3/r3_log.jsonl`. Every run used the same evaluator.

| variant | full win / R / boot | final R | summer (BST weeks) R / boot pass_both / P1 fail | cold start Apr–Oct 2025: trades/day / R / boot |
|---|---|---|---|---|
| Round-2 original (flat warm-up) | 71.9 / +0.070 / 52.8 | +0.055 | +0.044 / 25.9* / 5.9 | **0.94** / +0.067 / 31.9 |
| **A: 08/13 + warm-up prior (FINAL)** | **72.5 / +0.067 / 57.2** | **+0.055** | **+0.044 / 39.2 / 8.3** | **1.54 / +0.064 / 55.6** |
| B: learn the hours {07/12, 08/13, 09/14} + prior (48 sets) | 70.8 / +0.031 / 31.4 | +0.037 | **−0.006** / 11.1 / 30.4 | 1.52 / +0.014 / 18.0 |
| C: same as B, `train_weeks=26` | 71.8 / +0.034 / 31.1 | +0.040 | +0.013 / 16.9 / 16.6 | 1.52 / +0.044 / 39.2 |

\* The Round-2 summer bootstrap is depressed by the flat June–August 2024 warm-up weeks.

**Why I did *not* make the hours learnable or DST-aware, as critics suggested.** The critics' own seasonal analysis decides it:
- **Fixed 08/13 UTC is positive in both clock seasons:** winter +0.079R, summer +0.044R.
- **The DST-aware "08:00 local" clock is −0.061R in summer** (gold_session's table). The hold-out is summer, so the local-clock fix would move me onto the bad clock.
- **Letting the walk-forward choose among neighbouring hours is worse everywhere.** It picks noise: summer −0.006R and cold start +0.014R (B).

Fixed 08/13 UTC is therefore the only clock with **direct in-sample evidence for the hold-out's own season**: 53 BST weeks, 459 trades, +0.044R, 72.1% win, both sides positive. That makes it the robust choice, not the peak-chasing one.

### Final numbers (CLI, `python -m prop_fx.backtest --strategy gold_trend --data-dir data/gold`)

| run | trades | trades/day | win % | avg R | PF | net % | max DD | boot pass_both | boot P1 fail | hist pass_both | breaches | worst week |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 836 | **1.51** | **72.5** | **+0.067** | 1.33 | +83.0 | −10.0 | **57.2** | 4.2 | 47.1 | 0 | −4.3 |
| dev (`--end 2025-10-31`) | 653 | 1.53 | 73.4 | +0.070 | 1.36 | +68.3 | −10.0 | 60.0 | 3.0 | 48.5 | 0 | −4.0 |
| final check (`--trade-from 2025-11-01`) | 183 | 1.46 | 69.4 | +0.055 | 1.23 | +14.7 | −9.1 | 41.9 | 7.0 | 63.6 | 0 | −4.3 |
| full, 2× spread | 836 | 1.51 | 72.1 | +0.056 | 1.27 | +70.1 | −10.5 | 48.8 | 5.8 | 44.7 | 0 | −4.4 |
| final, 2× spread | 183 | 1.46 | 69.4 | +0.048 | 1.20 | +13.0 | −9.1 | 37.6 | 7.5 | 63.6 | 0 | −4.4 |
| **cold start**, Apr–Oct 2025 file only | 271 | **1.54** | 73.8 | +0.064 | 1.31 | +25.9 | −9.0 | 55.6 | 1.8 | 45.8 | 0 | −3.1 |
| **double risk** (`--risk-mult 2`), full | 786 | 1.42 | 72.1 | +0.057 | 1.28 | +133.9 | −15.7 | 60.8 | **23.9** | 55.4 | 0 | −8.8 |
| double risk, final | 170 | 1.36 | 68.8 | +0.021 | 1.08 | +10.7 | −16.2 | 41.0 | 36.2 | 50.0 | 0 | −7.4 |

The final-check rows are identical to Round 2. The prior only acts in the first 12 weeks of a file, so the final check, which has full history behind it, is untouched.

**Summer (BST) weeks only.** These are 53 weeks of the full run whose Monday falls in British Summer Time. The bootstrap is built only from those weeks.

| | trades | win % | avg R | long n / win / R | short n / win / R | boot pass_both | P1 fail |
|---|---|---|---|---|---|---|---|
| normal risk | 459 | 72.1 | +0.044 | 270 / 75.2 / +0.064 | 189 / 67.7 / +0.016 | **39.2%** | 8.3% |
| double risk | 434 | 70.7 | +0.033 | 256 / 73.8 / +0.062 | 178 / 66.3 / −0.009 | 48.2% | 31.8% |

**Daily stop at double risk.** `daily_stop_pct` stays at 2.5%.
- At 1.5% risk, the worst normal day is one full stop (−1.5%) plus the second trade flattened when the day reaches −2.5%.
- At 3.0% risk, one full stop already trips the daily stop. The worst normal day is therefore about one stop (−3%) plus slippage, with about 2% of headroom under FTMO's 5%.
- There were 0 daily-limit breaches in every run, including double risk (worst week −8.8%).
- Double risk raises the bootstrap pass rate only slightly (57 → 61%) but raises Phase 1 fails about sixfold (4 → 24%). **I recommend the normal 1.5%.**

### Point-by-point rebuttal
1. **"08/13 is a peak; the ±1h neighbours average +0.019R. The −1h shift funds only 18%, worse than random."** *Partly conceded.* Expect less than +0.07R on the hold-out. Three points against the strong version:
   - The −1h shift (07/12 UTC) is, in summer, *exactly* the DST-aware "08:00 local" clock, which is negative in summer data. It is a different, worse strategy, not a neighbour of mine on the hold-out clock.
   - The hold-out's clock was *tested* in-sample: 53 summer weeks at 08/13 UTC gave +0.044R and a 39% summer-only pass rate. That beats every rival's full-sample headline (+0.011 to +0.023R, 18–24%).
   - Making the hours learnable (B/C) did not add robustness. It lowered every column, so I kept the hours fixed rather than chase the critics' remedy.
2. **"The edge is seasonal; summer is weaker."** *Conceded on magnitude, rejected on sign.* Summer gives +0.044R (PF about 1.2), 72% win, longs +0.064R, shorts +0.016R. The edge is weaker in summer but still positive on both sides. The honest hold-out expectation is the summer row (39% pass_both, 8% P1 fail), not the 57% headline.
3. **"Cold start trades 0.84–0.94/day."** *Fixed.* With the warm-up prior, a cold Apr–Oct 2025 file trades **1.54/day** at 73.8% win and +0.064R, with a 55.6% pass rate (was 0.94/day, 31.9%). The prior was taken from dev-period choices, not tuned.
4. **"The 13 UTC slot sits in US-data spread spikes."** *Partly conceded.* 2× spread costs about 0.01R (+0.056R full). A 5–10× spike lasting a few minutes is not modelled. The fill is at the 13:00 bar open, 30 minutes after an 08:30 ET release in summer, not on the release minute.
5. **"The win rate comes from the break-even exit."** *True, and by design.* Coin flips with the same exits lose money (−0.007R on average over 5 seeds). The always-long version loses (−0.013R). The 72% win rate is paid for by a direction signal worth about +0.08R over drift. That is the largest real-minus-always-long gap in the field.

**Status.** The strategy is final and frozen in `prop_fx/strategies/gold_trend.py`, with the Round-2 version preserved at commit 4b25161.
- Truncation test: 0 mismatches.
- `pytest`: 37 passed.
- Scratch files: `tournament_gold/runs/gold_trend/r3/`.
