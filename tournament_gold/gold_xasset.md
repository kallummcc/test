# gold_xasset: XAUUSD traded on its dollar-adjusted residual, with walk-forward learning

**File:** `prop_fx/strategies/gold_xasset.py`, which exports `STRATEGY = WalkForward(...)`.
**FX inputs:** read from `os.environ.get("FX_DATA_DIR", "data/fx")`, clipped to the gold data's
date window. If the directory has no FX files, the strategy raises an error rather than trading
blind.

**Headline (full in-sample, 2024-05-31 → 2026-03-31, default costs):**

| Metric | Value |
|---|---|
| Net return | **+31.9%** |
| Trades | 722 |
| Trades per day | **1.31** |
| Win rate | **64.1%** |
| Avg R | **+0.022** |
| Profit factor | **1.09** |
| Max drawdown | −21.3% |
| Bootstrap pass_both | **30.1%** |
| Phase 1 fail | 22.9% |
| Daily-limit breaches | 0 |

The final-check window (2025-11 → 2026-03, looked at twice) returned **+5.5%**, with a 59.9% win
rate and +0.019 avg R. Both long and short positions were positive there.

**Honest summary.** The edge is thin. Avg R is about +0.02, which is roughly the size of one extra
spread, so the 2× spread test takes it to +0.006. In-sample, the short side is flat (−0.000R).
Most of the profit comes from four months.

---

## 1. Research

| Source | Finding | Use / caveat |
|---|---|---|
| Capie, Mills & Wood (2005), *Gold as a hedge against the dollar*, JIFMIM 15(4). [Scholarhub](https://scholarhub.vn/publication/:slug/aac67375-1d43-4a64-a15f-569408dca663) | Gold has acted as a hedge against the dollar. The relationship is negative but time-varying. | This motivates splitting gold's move into a dollar-explained part and a residual. |
| Joy (2011), *Gold and the US dollar: hedge or haven?*, FRL 8(3). [RePEc](https://ideas.repec.org/a/eee/finlet/v8y2011i3p120-131.html); Reboredo (2013), JBF 37(8) | Gold has increasingly behaved as a dollar hedge. Gold–USD dependence is negative and present in the tails. | Our data shows the same: the hourly correlation between gold and my USD index is **−0.37** (dev), with beta ≈ −1.1. |
| Baur & Lucey (2010), *Is gold a hedge or a safe haven?*, Financial Review 45(2); Ranaldo & Söderlind (2010), *Safe haven currencies*. [SNB WP](https://www.snb.ch/en/publications/research/working-papers/2007/working_paper_2007_17) | Gold, JPY and CHF all rally in risk-off episodes. | I tested a JPY/CHF haven confirmation (cycle 9). It helped longs a little but cut trading frequency too much. |
| Multifractal gold/DXY 5-minute study, [AIMS Press](https://aimspress.com/article/id/1644); stylized facts of intraday precious metals, [PLoS ONE / PMC5407636](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5407636/) | Gold and dollar-index components are cross-correlated intraday. Gold acts as a safe haven against extreme currency moves. | Neither study documents a tradable **lead-lag**. My own check agrees: the hourly cross-correlation is −0.375 at lag 0 and \|ρ\| < 0.011 at lags ±1 to ±3, so **the USD does not lead gold**. A "gold lags the dollar, so catch up" trade has nothing to work with. |
| Zhang (2022), *Dissecting currency momentum*, JFE (from the FX round) | Momentum in a common factor persists. | This is the analogy for gold's **idiosyncratic (non-dollar) flow** persisting for a few hours. |

WebFetch could not reach most of these sites (DNS was blocked in the sandbox). The summaries come
from search abstracts.

### My dev-only research (2024-06 → 2025-10, before writing the strategy)
- **Linear lead-lag.** Past USD moves (1–24 h) predict gold over the next 1–12 h with |t| ≤ 2.2,
  which is noise. The gold residual (gold − β·USD) shows mild **continuation**, not reversal.
- **Event simulator** with stop/target geometry, split long/short, 6 signal families × 3 look-backs
  × 2 thresholds × 3 geometries = **108 cells**.
  - Only "**follow the residual**" (L = 6–12 h) was positive on both sides at a 2-ATR stop and
    1-ATR target. For example, L=6, |z|>1.5 gave a 61.6% win rate and +0.023R, with shorts at +0.048R.
  - Fading the residual and the USD "catch-up" trade were negative.
  - All effects were within about ±1.5 standard errors.

## 2. Exact rules (final)
1. **USD index.** The 12 FX pairs are decomposed hourly by least squares into 8 currency strength
   indices (`fx_strength.currency_index`). The indices are aligned to gold bars by a backward
   as-of join on the bar label; both bar series close at the same time. Gold has 24 bars at :30
   past the hour, and these take the last FX close.
2. **Rolling beta.** β_t is the OLS slope of hourly gold log-returns on USD-index returns over the
   trailing 500 bars.
3. **Residual.** `resid = Δlog(gold)_L − β_t·ΔUSD_L`, and `z = resid / rolling std(resid, 500)`.
4. **Entry.** Enter on the bar where |z| first crosses `z_th`, in the direction of sign(z) (follow
   the residual). The fill is at the next open. An opposite fresh signal reverses the position.
5. **Exits.** The stop is 2.0 × ATR(24 h), the target is `target_atr` × ATR, and there is a time
   exit 8 bars after the signal.
6. **Flat before the daily break.** The position exits at the close of the 19:00 UTC bar, and no
   signals are taken from 19:00 to 21:00 UTC. The engine adds the Friday 20:00 close and no
   entries after Friday 16:00.
7. **Account settings:**
   - `max_positions=1` and `max_trades_per_day=2`.
   - `risk_pct=2.0`. At 1% risk, the bootstrap pass rate was only 3.7%, with 76% timeouts; see the
     risk table below.
   - `daily_stop_pct=4.0`. Two full losers lose 4%, which stays under the 5% limit. A position
     carried over from the previous Prague day, plus one new loser, also halts trading at 4%.
     No week breached the daily limit.

### Walk-forward setup
- `WalkForward(train_weeks=4, refit_weeks=1, objective="expectancy", min_trades=10)`.
- Grid: `lookback ∈ {3, 6, 12}` × `z_th ∈ {0.5, 0.75, 1.0}` × `target_atr ∈ {0.8, 1.0}`, which is
  **18 sets**.
- Every Monday, the bot replays each set over the trailing 4 weeks and trades the set with the most
  total R over the next week.
- On the full run there were 92 refits, and every set was picked at least once. The most common was
  lookback 6 / z 0.5 / target 1.0 (16 times). The latest pick is lookback 6 / z 0.75 / target 1.0.
- So the bot learns, but it mostly **re-weights between similar sets**. It does not find a stable
  optimum.

## 3. Learning journal
Cycles 1–10 used 1% risk, 3% daily stop and dev data only (`--end 2025-10-31`). Every run is in
`tournament_gold/runs/gold_xasset/journal.log`.

| # | Diagnosis (from walk-forward OOS trades, dev only) | One change | Result (dev) | Decision |
|---|---|---|---|---|
| c0 | Baseline: grid L{6,12} × z{1.5,2} × target{0.8,1,1.2}, train 12 weeks | — | 0.41/day, win 63.8%, R +0.070, PF 1.26; long +0.064, short +0.078 | Edge is fine, but frequency is far below 1.2/day |
| c1 | Too few signals | z grid → {0.75, 1, 1.25}, L → {3, 6, 12} | 0.86/day, win 65.2%, R +0.057, PF 1.23; **short −0.015** | **Keep** (frequency is a hard requirement) |
| c2 | The 12-week warm-up wastes about 45% of a 6-month hold-out | train_weeks 12 → 6 | Same window: R +0.057 → +0.014 | **Revert** |
| c3 | Trades where gold's raw move disagrees with the residual: shorts −0.10R vs +0.01R | `confirm=True` | R +0.050, frequency unchanged | **Revert** (no gain) |
| c4 | Frequency still low | Enter on the z level, not only fresh crosses | 1.05/day, but R → +0.012 | **Revert** |
| c5 | Time exits average −0.2R | hold axis {4, 8} | R +0.035, win 62.8% | **Revert** |
| c6 | Frequency | z grid {0.5, 0.75, 1.0} (train 12) | 1.21/day, R +0.014 | Revert for now; came back in c11 |
| c7 | Warm-up again | train_weeks 12 → 4 | Same window: R +0.046 vs c1 +0.057; more active days; **one −6.1R trade and one daily-limit breach** | **Keep** (needed for frequency on the hold-out) |
| c8 | The −6.1R loss was a short held through a **missing roll day**: 2024-07-30 is dropped, and the next bar opens $77 higher | Flat by 20:00 UTC, no signals 19–21 UTC | Breach gone, P1 fail 15.8% → 1.7%, R +0.029, DD −10.2% → −8.2% | **Keep** |
| c9 | Shorts still negative. Safe-haven hypothesis: gold up together with JPY/CHF | Longs need the haven index up over 24 h, shorts need it down | R +0.034, but 0.70/day | **Revert** (fails frequency) |
| c10 | Prop-friendlier objective | objective → `pass_score` | R +0.026, 1.02/day | **Revert** |
| risk | Bootstrap pass is only 3.7% at 1% risk; 76% of challenges time out | risk 1.5% / 3.5% stop; 2.0% / 4.0% stop | Boot pass 17.1% / **30.6%**, P1 fail 9.9% / 19.4%, 0 breaches | **2.0 / 4.0** |
| check 1 | First look at the final check (c8 at 2% risk) | — | Final check: win 58.2%, R −0.015 (fails); full: 1.10/day (fails) | — |
| c11 | Frequency is still below 1.2/day (dev, 2% risk) | z grid → {0.5, 0.75, 1.0} | Dev: 1.35/day, win 65.2%, R +0.023, boot 31.9% | **Keep** |
| c12 | Reverse exits average −0.54R (38 trades). Do flips hurt? | Diagnosis only: the trades opened by a reversal averaged +0.105R with a 74% win rate | — | No change |
| check 2 | Second and **last** look at the final check | — | Final check: win 59.9%, R +0.019, PF 1.08, +5.5%; long +0.012R, short +0.027R | Stop here |

**Count:**
- 13 dev runs of the walk-forward: c0–c11 plus two risk runs, each one walk-forward over the
  18-set grid.
- Each full or final-check pass was also run with 2× spreads.
- 108 research cells in the event simulator.
- The final check was **looked at twice**.

## 4. Results

### Final strategy (2% risk)
| Period | Net | Trades | /day | Win % | Avg R | PF | Max DD | Boot both | Boot P1 fail | Hist both | Hist P1 fail |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev (→2025-10-31) | +26.4% | 575 | 1.35 | 65.2 | +0.023 | 1.09 | −21.3% | 31.9% | 26.1% | 38.6% | 35.7% |
| final check (2025-11→2026-03, trades only) | +5.5% | 147 | ~1.4 | 59.9 | +0.019 | 1.08 | — | — | — | — | — |
| **full** | **+31.9%** | 722 | **1.31** | **64.1** | **+0.022** | **1.09** | −21.3% | **30.1%** | 22.9% | 39.2% | 31.6% |
| full, **2× spread** | +8.8% | 721 | 1.31 | 62.6 | +0.006 | 1.02 | −26.3% | 21.6% | 32.8% | 32.9% | 38.0% |
| dev, 2× spread | +3.8% | 574 | 1.34 | 63.4 | +0.003 | 1.01 | −26.3% | 21.6% | 37.6% | 30.9% | 44.1% |

There were no daily-limit breaches in any run of the final configuration. The worst week was −8.6%.

### Long vs short (don't mistake the gold bull run for an edge)
| Side | Full: n / win / R | Dev: R | Final check: n / win / R | 2× spread (full): R |
|---|---|---|---|---|
| Long | 394 / 65.5% / **+0.041** (+32.2%) | +0.048 | 78 / 59.0% / +0.012 | +0.021 |
| Short | 328 / 62.5% / **−0.000** (−0.3%) | −0.007 | 69 / 60.9% / +0.027 | −0.011 |

In-sample, **all of the net profit is on the long side.** Shorts break even, with a high win rate
and zero expectancy. Only in the final check are both sides positive. So the critic's point stands:
part of the "edge" is plausibly the gold uptrend. The rule itself is symmetric (it follows the
residual's sign), but its long trades rode the trend.

### vs `random_gold`
| | Win % | Avg R | PF | /day | Boot both | Boot P1 fail | Hist both / P1 fail |
|---|---|---|---|---|---|---|---|
| random_gold (default 1% risk), full | 58.9 | +0.009 | 1.03 | 1.30 | 7.0% | 12.2% | 1.2% / 8.1% |
| random_gold **at 2% risk**, full (same sizing as mine) | 58.8 | +0.009 | 1.03 | 1.30 | 27.6% | 40.6% | 24.4% / 43.0% |
| random_gold at 2% risk, dev | 57.1 | −0.023 | 0.93 | 1.31 | 18.1% | 53.1% | 14.9% / 55.2% |
| **gold_xasset**, full | **64.1** | **+0.022** | **1.09** | 1.31 | **30.1%** | **22.9%** | **39.2% / 31.6%** |
| **gold_xasset**, dev | 65.2 | +0.023 | 1.09 | 1.35 | 31.9% | 26.1% | 38.6% / 35.7% |

- At equal 2% risk, my strategy beats random on win rate, expectancy and Phase 1 fail rate (about
  half of random's) in both dev and full.
- On bootstrap pass_both, the gap is large in dev (31.9 vs 18.1) and small in full (30.1 vs 27.6).
  The gold bull run in the final-check months also lifted random.
- Against the default random_gold (1% risk), most of my 30% pass rate comes from **risk sizing**,
  not edge.

### Breakdown
- **Session (full, R long / short):**
  - Asia (00–06 UTC): +0.050 / −0.010
  - London (07–11): +0.046 / −0.003
  - NY (12–16): +0.070 / +0.018
  - Late (17–23): −0.139 / +0.014, on only 49 trades
- **Month:** P&L is lumpy. Jan, Feb, Apr, Jul and Oct 2025 made +8% to +16% each. Jun, Aug and Sep
  2025 lost −5% to −14%.
- **Exits (full):** 429 at the target (+0.455R), 126 at the stop (−1.0R), 106 time or 19:00 exits
  (−0.22R), and 49 reversals (−0.52R; the trades they opened did well).

## 5. Mechanics and tests
- **FX directory.** The default run, a run with `FX_DATA_DIR` pointing at a truncated scratch copy,
  and a `--start 2025-04-01 --end 2025-10-31` window all gave identical results. With
  `FX_DATA_DIR=/nonexistent` the strategy raises a clear error.
- **No look-ahead.** `entry`, `exit`, `stop_dist` and `target_dist` computed on gold data truncated
  at 2025-06-15 match the full-data values on every shared bar, for three parameter sets
  (0 mismatches).
- **Cold-start sensitivity.** Run fresh on Apr–Oct 2025 alone, it made −21.9% (win 60.3%,
  R −0.05, 1.24/day). Trades in the same window of the full run made −3.7%. The difference comes
  from the 500-bar beta and z warm-ups and the trailing 4-week scoring, which converge only after
  about 2–3 months. On a 7-month hold-out, the first quarter runs on immature estimates.

## 6. Known weaknesses
1. **The edge is small and fragile.** Avg R is about +0.02. A 2× spread leaves +0.006, and the dev
   PF falls to 1.01. A slightly wider real spread during news would erase it.
2. **The short side has no in-sample edge** (−0.000R). Profit is long-side and plausibly trend
   beta. Only the 147 trades in the final check show positive shorts.
3. **The walk-forward mostly chases noise.** Every one of the 18 sets was picked at some point.
   Shortening the training window from 12 to 6 weeks hurt (c2), but 4 weeks was fine (c7). That
   pattern is itself a sign of noise.
4. **Frequency versus edge is a direct trade-off.** The edge was +0.07R at 0.4 trades a day, and
   +0.02R at 1.3 a day. Hitting the user's 1.2/day minimum dilutes the signal. On the hold-out, the
   first 4 weeks are flat, so the realised rate will be about 1.1–1.2 a day. That is borderline
   against the hard requirement.
5. **The pass rate comes mostly from 2% risk.** The worst week was −8.6% and the max drawdown −21%.
   The Phase 1 fail rate is 23%, lower than random's 41% at the same risk, but not low.
6. **The win rate is close to the 60% line.** It was 59.9% on the final check, and target
   geometry (0.4–0.5R targets) does most of the work. Breakeven at this geometry is about 67–71% on
   pure stop/target outcomes. Profit depends on time exits that lose less than 1R.
7. **Data artifacts.** Futures roll holes (10 dropped days, with jumps up to $77) and futures basis
   are not spot XAUUSD. The flat-by-19:00-UTC rule removes overnight exposure to these holes, but
   real MT5 spot has no roll jumps. This is an engine/data issue I am reporting, not a bug fix.
8. **Swap is not modelled.** It barely matters here: positions are closed daily.

---

## Round 3: revision and rebuttal (final, frozen)

**The Round-2 version is preserved at git `4b25161`.** All numbers below come from the current engine (gap-close fix), using `tournament_gold/runs/gold_xasset/attack/harness.py` (raw results in `attack/results.jsonl`, tags `F_*` = final and `R2_*` = Round-2).

**Summer/winter definition (gold_session's):**
- Summer = UK and US both on DST.
- Summer bootstrap = 1,000 challenges drawn only from traded summer weeks.
- In-sample, season is confounded with calendar. The final-check window (Nov–Mar) is almost entirely winter.

### The one revision: direction from gold, the dollar as a veto
| Piece | Round 2 | Round 3 | Where the idea came from |
|---|---|---|---|
| Direction | sign of gold's ex-USD residual | **sign of gold's own L-hour move** (raw momentum) | gold_trend: the only edge that survived every Round-2 attack, and 88% of its P&L is ex-USD |
| Cross-asset role | the signal | **a veto**: trade only if ≥ 50% of the move is gold's own, i.e. sign(pg)·resid ≥ 0.5·\|pg\| | my Round-2 idea |
| Exit | stop / target / 8-bar time exit / 19:00 UTC flat | the same, **plus break-even**: from 1 bar after the fill, exit at the first close ≥ +0.1× stop | gold_trend C5 |
| Warm-up | flat for 4 weeks | **trades a prior set** (lookback 6, z 1.0, target 1.0) until 8 weeks of history exist | gold_prop |
| Walk-forward | train 4 weeks, expectancy | train **8** weeks, **Sharpe** objective, same 18-set grid shape (lookback {3,6,12} × z {0.75,1,1.25} × target {0.8,1.0}) | gold_trend C2b |
| Risk | 2.0% risk / 4.0% daily stop | **1.5% / 2.5%** | see the double-risk check below |

**Why the daily stop is 2.5% and not 3%.** The first frozen run used 1.5% risk with a 3.0% daily stop, and at the judge's double risk (3%/trade) it **breached the 5% daily limit in 4 weeks**.
- The mechanism: a stop filled at −1.002R left the day at −2.99%, just inside a 3.0% stop. The second trade then also lost.
- With a 2.5% daily stop, one full loss at double risk halts the day: **0 breaches**.
- At normal risk, a second trade is cut at about −2.5% on the day.
- For comparison, the Round-2 settings at double risk (4%/trade, 4% stop) **breached in 20 weeks**.

### Before vs after (full in-sample, 1× risk unless stated)
| | R2 (current engine) | **R3 final** |
|---|---|---|
| Trades / trades per day | 719 / **1.30** | 520 / **0.94** |
| Win % | 63.4 | **71.5** |
| Avg R / PF | +0.014 / 1.05 | **+0.024 / 1.12** |
| Net / max DD | +19.7% / −25.8% | +18.2% / **−12.8%** |
| Long R / short R | +0.034 / **−0.010** | +0.025 / **+0.021** |
| **Always-long control** (same entries, side forced long) | +0.037R, 41.5% pass, **beats the bot** | −0.024R, 0.8% pass, **the bot beats it by +0.048R** |
| Drop top-10 trades | +0.007R | +0.014R |
| **2× spread** | **−0.002R** | +0.005R (PF 1.03) |
| Bootstrap pass_both / P1 fail | **23.9 / 26.5** | 9.6 / **7.3** |
| Historical pass_both | 40.0 | 12.8 |
| Daily-limit breaches | 0 | 0 |
| **Double risk** (R2: 4%/4%; R3: 3%/2.5%): pass / P1 fail / **breach weeks** | 15.1 / 68.8 / **20** | 24.9 / 38.2 / **0** |

### Dev, final check, summer
| Window | n | trades/day | Win % | Avg R | PF | Long R | Short R | Bootstrap pass / P1 fail |
|---|---|---|---|---|---|---|---|---|
| Dev (≤2025-10) | 405 | 0.95 | 72.3 | +0.032 | 1.16 | +0.030 | +0.035 | 12.2 / 6.5 |
| Dev, 2× spread | 405 | 0.95 | 70.6 | +0.011 | 1.05 | +0.013 | +0.008 | 6.5 / 11.4 |
| **Final check** (`--trade-from 2025-11-01`) | 115 | 0.92 | 68.7 | **−0.008** | 0.97 | +0.007 | −0.028 | 1.5 / 12.7 |
| Final check, R2 for comparison | 149 | — | 61.1 | +0.035 | 1.14 | — | — | — |
| **Summer weeks** (full) | 278 | — | 70.5 | +0.006 | 1.02 | **+0.023** | **−0.022** | 5.5 / 10.3 (52 weeks) |
| Summer, R2 | 390 | — | 63.3 | −0.011 | 0.96 | +0.029 | −0.061 | 14.1 / 46.4 |
| Winter weeks (full) | 196 | — | 70.9 | +0.027 | 1.13 | — | — | 12.4 / 8.6 |
| **Cold start**, 7-month file 2025-04→10 | 182 | **1.03** | 70.3 | **−0.005** | 0.98 | +0.020 | −0.043 | 8.6 / 21.7 |
| Cold start, R2 | 219 | 1.24 | 59.4 | −0.056 | 0.82 | — | — | 6.8 / 68.4 |

### Summer-weeks bootstrap
- The revision makes summer *less bad*: +0.006R vs −0.011R, and the P1 fail rate drops from 46% to 10%.
- But **summer pass_both falls from 14.1% to 5.5%**: lower variance and fewer trades mean most summer challenges time out.
- Summer shorts are still negative (−0.022R). The long side carries summer.

### Checks
- The CLI (`python -m prop_fx.backtest --strategy gold_xasset --data-dir data/gold`) reproduces the harness exactly: 520 trades, 71.5%, +0.024R.
- **Look-ahead truncation:** 32 cuts × 5 parameter sets gave 0 mismatches. This includes the break-even rule, which reads the fill bar's open only when age ≥ 1.

**Variants this round:**
- 19 dev walk-forward runs: final; 3 ablations (no veto, no break-even, always long); 2 lower-z grids; a share-0.25 version; a 2/3/6 lookback grid; 2 level-entry versions; 2 hold-4 versions; 2 expectancy-objective versions; a 3/6 lookback grid; a share axis; 2 alternative lookback grids; min_trades 30 and 40.
- Then one risk fix (daily stop 3.0 → 2.5) after the double-risk breach.
- **The final check was looked at twice this round:** the first frozen run, and the rerun after the daily-stop fix. Four looks in total across rounds.

### Point-by-point rebuttal
1. **"Your always-long copy beats you" (gold_trend, gold_prop, gold_session, gold_mean_reversion).**
   - True for Round 2, and fixed.
   - The direction now adds value: real +0.024R vs always-long −0.024R (full); dev +0.032R vs −0.015R.
   - Both sides are positive in-sample (L +0.025, S +0.021).
2. **"Fails 2× spread."**
   - Now positive but thin: +0.005R full, +0.011R dev.
   - I won't claim it is robust. Costs eat about 80% of the edge.
3. **"Cold start loses."**
   - Improved from −0.056R (P1 fail 68%) to −0.005R (P1 fail 22%), with 1.03 trades/day from week 1 thanks to the prior set.
   - Still not profitable on a cold summer file.
4. **"Round-1 claims don't reproduce on the current engine" (gold_session).**
   - Correct. The gap-close fix lowered my numbers to +0.014R and 23.9%. I re-reported them in Round 2.
   - Every number in this section is from the current engine.
5. **"Summer is your bad half" (gold_session).**
   - Partly fixed: summer is now +0.006R (from −0.011R) with a 10% P1 fail rate (from 46%).
   - But the summer pass rate is lower: 5.5% vs 14.1%.
6. **"Small parameter changes flip the sign" (gold_trend: train_weeks 6 → −0.007R).**
   - In the revised design, the ablations behave as expected: removing the veto drops dev to +0.009R, and removing break-even lowers win rate by 7 points at similar R.
   - But my grid sweeps show the same frequency/expectancy frontier as Round 1: every change that raised trades/day to ≥ 1.1 cut avg R to ≤ +0.018.

### What I concede (final)
- **Trades/day is 0.94** on the judge's formula, below the 1.2 hard requirement. Round 2 met it (1.30) only with a negative-value direction.
- I could not find a configuration of this design with ≥ 1.2/day and avg R clearly above 0 (19 tries). **By the rules, this bot cannot win.**
- The final check is −0.008R. Bootstrap pass_both is 9.6% at 1× risk and 24.9% at double risk. Both are below gold_trend, and the 1× figure is close to random_gold's.
- **What it offers instead:**
  - the cleanest risk profile in the field: max DD −12.8%, P1 fail 7.3%, 0 breaches at both 1× and 2× risk;
  - a direction that beats its own always-long control;
  - the cross-asset finding that the dollar explains about 10% of gold-trade variance and none of the leader's edge.

**Final settings:** `risk_pct=1.5`, `daily_stop_pct=2.5`, `max_positions=1`, `max_trades_per_day=2`. The walk-forward is `PriorWalkForward(train_weeks=8, refit_weeks=1, objective="sharpe", min_trades=10, prior=lookback6/z1.0/target1.0)` over 18 sets. FX is read from `os.environ.get("FX_DATA_DIR", "data/fx")`. Frozen.
