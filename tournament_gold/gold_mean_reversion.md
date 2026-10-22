# Gold Bot: Mean reversion ("gold_mean_reversion")

**One line:** when today's gold session (opened 23:00 UTC) has moved more than *k* hourly ATRs in one direction and an hourly bar closes *against* it, fade that pullback by trading *with* the session. A 20-day daily regime makes trades against the multi-day trend need a 2× bigger session move. Exits are a target of 0.6–1.0 ATR, a stop of 1.25–2.0 ATR, or a 3–5 h time exit. A walk-forward re-picks (k, target, stop, hold) every Monday from the trailing 12 weeks.

- **Code:** `prop_fx/strategies/gold_mean_reversion.py`, which exports `STRATEGY = WalkForward(...)`.
- **Scratch work:** event studies, the harness, `variants.csv`, trade files and `final_looks.txt` are in `tournament_gold/runs/gold_mean_reversion/`.

## 1. Research

| Source | Finding | Use / caveat |
|---|---|---|
| Caminschi & Heaney (2014), *J. Futures Markets*, gold fix and GC futures ([IDEAS](https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html)) | Volume and volatility jump at the London PM fix, and early-fix trades predict the fix direction. | Gold intraday flows are information-driven, and order flow moves price in one direction. This is a warning against naive fades. |
| Donati & Jung, *Gold price dynamics around the clock* (CBS thesis) ([PDF](https://research-api.cbs.dk/ws/portalfiles/portal/59803241/651553_Thesis_Contract_13383.pdf)) | Gold shows a hat-shaped intraday pattern: gains in Asian hours, losses in the rest of the day. | It's an unreviewed thesis. My dev data didn't show a fadeable Asian move: fading it lost about −0.4 ATR per trade (§6, es4). |
| Abrantes-Metz on the PM fix ([LBMA Alchemist](https://www.lbma.org.uk/alchemist/issue-73/has-there-been-a-decade-of-london-pm-gold-fixing-manipulation)) | There were systematic moves around the fix from 2004 to 2013. | The finding is contested and the period is old. I treat it as context only. |
| Quantified Strategies gold/silver RSI note ([link](https://quantifiedstrategies.substack.com/p/gold-silver-chart-ratio-strategy)) | Their GLD rule *buys* RSI(5) > 75, which is a momentum rule, not a fade. | At the daily scale gold behaves like momentum. That's consistent with my finding that you shouldn't fade gold's trend. |
| Connors-style RSI(2) pullback-in-trend (summary: [Backtrex RSI(2) FX test](https://backtrex.com/en/backtests/connors-rsi-2-eur-usd)) | Buying short-term weakness inside a trend works on indices but failed on EURUSD daily. | The general template, "fade the pullback, not the trend," is the one I adopted, on the intraday session trend instead of a 200-day MA. |
| Vendor/TradingView gold MR claims ([MQL5 Zenith](https://www.mql5.com/en/market/product/176897), [TV XAUUSD 10-min](https://jp.tradingview.com/script/LxrgnsTO-XAUUSD-10-Minute-Strategy), [TV 1-min RSI template](https://jp.tradingview.com/script/braXKo74-Gold-Spread-Algo/)) | They claim 54–90% win rates, but the samples are tiny, costs are unverified, and one tests a different symbol. | **Disregarded** as evidence. They mainly show that a high win rate is easy to advertise. |
| Last round's FX work ([`tournament_fx/fx_mean_reversion.md`](../tournament_fx/fx_mean_reversion.md)) | Fading stretches of 1.25 daily ATR from the pivot worked on FX (PF 1.37). | On gold the same idea is the wrong sign. In dev, fades of hourly stretches and pivot distances lost after removing drift (§6). |

**The research led to my key empirical finding, on dev data only:** gold *hourly* is momentum, not mean-reverting.
- **Fading strength loses heavily.** Fading Bollinger(20, 2σ) stretches upward cost −0.2 to −0.5 ATR over 2–8 h.
- **Fading the Asian-session move loses on both sides,** from −0.2 to −0.9 ATR.
- **What does revert is the pullback inside a trending session.** With the session up at least 0.5–1.5 ATR, a down-close bar is followed by a bounce over the next 2 h of +0.10 to +0.21 ATR after removing drift, on both longs and shorts (es5).

So the "mean" this bot reverts to is the session's own direction. It never fades the session trend, and that's how it avoids the main risk in this lane.

## 2. Exact rules

These are evaluated on hourly bars; signals are decided at a bar's close and fill at the next open.

1. **Session move:** st = (close − first open of the session that started at 23:00 UTC) / ATR(24, hourly).
2. **Pullback:** the bar closed against the session move. For longs, close < previous close and st > trend_thr; shorts are the mirror image. Every qualifying bar may signal (`refire=True`), but the engine holds at most one gold position.
3. **Daily regime:** compare the last closed UTC daily close with the SMA of the last 20 closed daily closes. A long against a down regime, or a short against an up regime, requires st beyond 2 × trend_thr.
4. **Hours:** signal bars must open between 01:00 and 19:00 UTC. The engine also blocks Friday-afternoon entries and closes everything before the weekend.
5. **Exits:**
   - target at target_atr × ATR;
   - stop at stop_atr × ATR;
   - time exit max_hold_h hours after the signal.
6. **Walk-forward:** the grid is `trend_thr ∈ {0.4, 0.6, 0.8}` × `target_atr ∈ {0.6, 0.8, 1.0}` × `stop_atr ∈ {1.25, 1.5, 2.0}` × `max_hold_h ∈ {3, 5}`, which is **54 sets**. Settings: `train_weeks=12`, `refit_weeks=1`, `objective="expectancy"` (total R in the window), `min_trades=10`. If no candidate qualifies, the bot sits out that week.
7. **Account settings:** `risk_pct=1.5`, `max_trades_per_day=2`, `max_positions=1`, `daily_stop_pct=3.0`.
   - The worst ordinary day is two full stops, which is 3.0%. That leaves 2 percentage points of headroom under the 5% daily limit for gap slippage.
   - The worst realised day was −3.0%, with no breaches.
   - 1.5% risk was chosen on **dev only**, from {1.0, 1.5, 1.75, 2.0}. I chose 1.5% over 1.75–2.0% because the Phase 1 fail rate climbs from 13% to 19–26% (§4, cycle 7).

**Look-ahead check:** running the base strategy on data cut at 3 dates, for 6 grid sets, gives 0 mismatched rows out of 103,488.

## 3. Walk-forward setup and how the bot "learns"

Every Monday the bot re-runs all 54 candidates over the trailing 12 weeks and trades the one with the highest total R. Live, the same `prepare()` runs on recent MT5 bars, so it re-tunes weekly.

In dev it mostly chose low thresholds (trend_thr 0.4), wide targets (1.0 ATR) and stops of 1.5–2.0 ATR, but it rotated often. The parameters it actually used are recorded in `STRATEGY.log`.

The first 12 weeks of any data set are flat while it learns. In-sample, the first trade is on 2024-08-26.

## 4. Learning journal

Each cycle is one change followed by a walk-forward re-run on **dev (2024-05-31 → 2025-10-31) only**.

| # | Diagnosis (on dev WF OOS trades) | Change | Result (dev WF) | Decision |
|---|---|---|---|---|
| pre | Seven plain hourly Bollinger fades, with trend alignment, "both", and stop/target/hold variants (b1–b7), lost with PF 0.59–0.95. The event studies showed hourly momentum. | Switched to the pullback-in-session-trend base rule (pb0–5, pc0–4 fixed-param runs). | Fixed pull=1, thr=1.0: 1.22/day, 63.8% win, +0.052 R, both sides positive. | New base. |
| c0 | — | Walk-forward over a 54-set grid (thr {0.75, 1, 1.25}, target {0.5, 0.75, 1}, stop {1.25, 1.5, 2}, hold {4, 6}). | 418 trades, 62.2% win, **+0.019 R**, PF 1.07; shorts −0.01 R. | Baseline. |
| c1 | WF churns between sets; a 12-week window looks noisy. | train_weeks 12 → 26. | On the same OOS window: +0.017 R and 59.3% win, vs c0's +0.020 R and 62.0%. | **Reverted.** |
| c2 | Stops hit −1 R on 94 trades. Losers concentrate on days when the session move fights the multi-day trend. | Hard daily filter: trade only when the session direction agrees with close vs 20-day SMA. | **+0.080 R**, 64.3% win, PF 1.26, shorts +0.11 R, but only **0.55 trades/day**. | The edge improved but the frequency requirement failed. Kept the idea. |
| c3 | Frequency too low. | Lower thresholds {0.25, 0.5, 0.75} with the hard filter (c3); then re-entry on every qualifying bar (c3b). | c3: 0.66/day, +0.062 R. c3b: 0.55/day, +0.093 R. | Frequency still failed. Kept `refire`. |
| c4 | The hard filter blocks most days. | Soft filter: trading against the daily trend needs a 2× session move. | 0.83/day, 62.1% win, +0.048 R, PF 1.16. Both sides positive (L +0.063, S +0.020). | **Kept.** |
| c5 | Still under 1.2/day. | Grid moved toward frequency: thr {0.4, 0.6, 0.8}, target {0.6, 0.8, 1.0}, hold {3, 5}. | 471 trades, **1.52 per weekday out-of-sample**, 62.0% win, +0.039 R, PF 1.14. | **Kept.** This is the final grid. |
| c6 | Expectancy may not be the best selection rule for a win-rate goal. | Objective: win_rate / pass_score / sharpe. | win_rate gave 71.9% win but +0.017 R. pass_score gave +0.028 R. Sharpe gave +0.042 R but 1.00/day. | **Kept expectancy.** The win_rate objective buys win rate with expectancy, the brief's trap. |
| c7 | Edge is fixed; size for the challenge. | risk 1.0 / 1.5 / 1.75 / 2.0, with daily stop = 2 × risk. | Bootstrap pass_both 6.7 / 24.9 / 33.4 / 37.1%; Phase 1 fail 3.2 / 13.3 / 18.6 / 25.7%. | **1.5%.** |

**Final-check discipline.** The final-check window (2025-11 → 2026-03) was looked at **twice**, both after the configuration was frozen (`final_looks.txt`):
- **Look 1** was the planned final run.
- **Look 2** re-ran the identical config because the shared engine changed (gap-close fix).

No strategy change was made after either look.

The harness refuses that period unless `FINAL=1` is set. The FX-round mistake (tuning risk after seeing validation) was not repeated.

## 5. Results

**Engine change.** All numbers below come from the **current** engine. Commit d98c340 at 19:39 UTC closed positions across data gaps longer than 6 h. It landed after my first final run (19:37), so I re-ran the *same frozen config* (look 2 in `final_looks.txt`).
- The learning-journal numbers in §4 were produced on the earlier engine; relative comparisons between cycles are unaffected.
- The gap fix cut dev avg R from +0.035 to +0.024.
- random_gold also changed: it now passes 3.5% on the full run, versus 7.0% in the brief.

**Trades per day.** The judge's `trades_per_day` counts every data date, including Sunday-evening stubs and the 12-week warm-up.
- Excluding the warm-up gives **1.28/day** on the same definition.
- Out of sample the rate is **1.36–1.53 per weekday**.

| | Dev (WF OOS, ≤2025-10) | Final check (2025-11→03) | Full | random_gold (full, same engine) |
|---|---|---|---|---|
| Net return | +16.6% | +3.8% | **+20.4%** | −3.3% |
| Trades | 471 | 144 | 615 | 720 |
| Trades/day (JSON, incl. warm-up) | 1.10 | — | 1.11 (**1.28** post-warm-up) | 1.30 |
| Trades per weekday | 1.53 | 1.36 | ~1.5 | — |
| **Win rate** | 61.1% | 61.8% | **61.3%** | 58.2% |
| **Avg R** | +0.024 | +0.018 | **+0.023** | −0.005 |
| **Profit factor** | 1.08 | 1.06 | **1.08** | 0.99 |
| Max DD (equity) | −15.6% | — | −15.6% | −19.3% |
| Worst day / worst week | −3.0% / −6.6% | — | −3.0% / −6.6% | — / −4.9% |
| 5% daily-limit breach weeks | 0 | — | **0** | 0 |
| **Bootstrap pass_both** | 19.1% | — | **18.9%** | 3.5% |
| Bootstrap Phase 1 fail | 15.6% | — | 15.9% | 14.2% |
| Historical pass_both | 30.8% | — | 32.6% | 1.2% |
| Historical Phase 1 fail | 13.8% | — | 15.2% | 16.3% |
| By year | 2024 +13.1%, 2025 +3.4% (to Oct) | 2026 YTD **−3.8%** | | |

**2× spread stress.**

| | Dev | Full |
|---|---|---|
| Win rate | 59.9% | 60.2% |
| Avg R | +0.004 | +0.006 |
| PF | 1.01 | 1.02 |
| Net | +2.5% | +5.6% |
| Bootstrap pass_both / Phase 1 fail | 11.2% / 21.7% | 12.3% / 20.6% |
| Historical pass_both | — | 31.5% |

At 2× spread the edge is **nearly gone** (§7).

**Long vs short, and is it just "buy gold"?** "Drift" is gold's average rise per hour over the period ($0.23/h), multiplied by each trade's hold time and divided by its stop distance.

| | Long | Short |
|---|---|---|
| Full: trades / win / avg R | 376 / 61.7% / +0.024 | 239 / 60.7% / +0.020 |
| Full: drift part of avg R | +0.038 | −0.037 |
| Full: **de-drifted avg R** | −0.014 | **+0.057** |
| Dev OOS avg R | +0.050 | −0.013 |
| Final check avg R | **−0.049** (97 trades) | **+0.158** (47 trades) |
| random_gold full, de-drifted (earlier engine) | +0.010 | −0.004 |

Both sides make money over the full period. After removing gold's upward drift, the **edge sits on the short side**. In the final-check window the long side lost and the short side carried the result.

So the bot is not just a long-gold bet. The cost of that is that its long trades basically earned the drift and nothing more.

## 6. Variants tried (complete)

- **Event studies, dev only, no engine.** These are the scripts `es.py`, `es2.py`, `es3.py`, `es4.py` and `es5.py`, in that order:
  - 7 fade signals × 3 holds × side × regime (84 cells);
  - 3 signals × 3 sessions × 2 sides × 2 holds (36);
  - failed breakouts of the prior-day and Asian ranges, 12 variants × 3 holds × 2 sides (72);
  - hour-of-day returns, plus the Asian-move fade at 5 entry × 3 exit × 3 thresholds (36);
  - pullback-in-session-trend, 3 thresholds × 4 pullback definitions × 3 holds × 2 sides (72).
  - In total that is about 300 cells.
- **Engine runs, all logged in `variants.csv`: 32 in total.**
  - 18 fixed-parameter base runs: b1–b7, pb0–5 and pc0–4.
  - 10 walk-forward runs: c0, c1, c2, c3, c3b, c4, c5 and three c6 runs.
  - 4 risk runs.
- **Grid search:** each walk-forward run internally scores 54 candidate sets.
- **Selection-bias caveat:** the grid ranges were designed after seeing dev's fixed-parameter runs. The walk-forward's out-of-sample result on dev is therefore *not* a clean out-of-sample test of the design. Only the final-check window is clean.

## 7. Known weaknesses

1. **The edge is thin.**
   - Full avg R is +0.023 and PF 1.08. Final check was only +0.018 R, PF 1.06, and 2026 YTD is −3.8%.
   - With 615 trades and an R standard deviation of about 0.68, the standard error of mean R is 0.027, so the edge is **under 1 standard error** from zero.
   - Much of the pass-rate advantage over random_gold (18.9% vs 3.5%) comes from 1.5% risk combined with a slightly positive expectancy. Random entries at 1% risk can't reach that pass rate.
2. **Cost-sensitive.** Targets are 0.6–1.0 hourly ATR, about $10–25. Doubling the spread leaves almost no edge: +0.006 R, PF 1.02. Real XAUUSD spreads widen at the 22:00 UTC rollover and around US data. The 01–19 UTC window avoids the rollover, but news widening is not modelled.
3. **The 60% win rate has a thin margin.** It is 61.3% at normal costs and 59.9–60.2% at 2× spread. A slightly worse fill model could push it under the hard 60% requirement.
4. **The trades-per-day metric depends on warm-up.** On a fresh hidden-only run, the first 12 weeks are flat, and the JSON figure would fall below 1.2. With continuous history the post-warm-up rate is 1.28/day, or about 1.4–1.5 per weekday.
5. **The long side added nothing beyond drift.** After removing drift, longs were slightly negative over the full period. If gold falls in the hold-out, the regime logic should shift trades to the short side, as it did in the final check. A choppy hold-out with no session trends would starve the signal instead.
6. **Fat tails are bounded but real.**
   - Stops are rarely gapped; the worst trade was −1.008 R. Worst day −3.0%, worst week −6.6%.
   - Two consecutive −3% days plus a bad week can still fail Phase 1. That happened in 13–15% of bootstrap challenges.
   - A gap through the stop at news time is possible, and hourly bars can't model it.
7. **Walk-forward churn.** It switches sets often. Cycle c1 suggests this neither helps nor hurts much, so "learning" here mostly adapts geometry to volatility; it does not discover new edges.
8. **Futures basis and data.** GC=F is used as a proxy for spot. Ten roll days were dropped. Daily SMA regimes computed from the hourly file are unaffected by the daily file's roll jumps.
