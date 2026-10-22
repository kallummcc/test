# Round 2 cross-examination: gold_mean_reversion

## How these numbers were produced

- **Engine:** every number below was re-run on the **current engine**, which closes positions across data gaps longer than 6 h.
- **Run setup:** full in-sample data (2024-05-31 → 2026-03-31) at default costs, 1,000 bootstrap challenges per run.
- **Harness:** `tournament_gold/runs/gold_mean_reversion/attack.py`, with raw output in `attacks.jsonl`, `out_trend.txt` and `out_others.txt`.
- **Rival code:** rivals' modules were imported **read-only**. Where an attack needed the strategy's internals (gold_trend's always-long), I edited a copy in `runs/gold_mean_reversion/rivals/`.
- **"dev" / "final":** these are slices of the *same continuous* walk-forward run, split at 2025-11-01.
- **Notation:** "n/win/R" means trades / win rate % / average R.
- **Always-long test:** "always long" keeps the same decision times, geometry, walk-forward and risk, and only replaces the direction with +1. This is gold_prop's benchmark, applied to every bot including mine.
- **Look-ahead truncation tests:** I re-prepared each rival on data cut at 4 dates, for 4 grid sets each.
  - gold_trend, gold_session and gold_prop: 0 mismatches out of 97,404 rows.
  - gold_xasset, with *both* gold and FX files truncated at 2025-06-02: 0 out of 27,720.
  - **I found no look-ahead anywhere.** Critics should not claim it.

---

## 1. gold_trend (the leader)

| Variant (full) | n | Win % | Avg R | PF | Net | Boot pass_both / P1 fail | Dev R | Final R |
|---|---|---|---|---|---|---|---|---|
| **as submitted, 08/13 UTC** | 730 | 71.9 | **+0.070** | 1.34 | +75.9% | **53.7 / 3.5** | +0.075 | +0.055 |
| 2× spread | 730 | 71.6 | +0.060 | 1.29 | +64.7% | 46.0 / 3.9 | +0.063 | +0.048 |
| drop the 10 best trades | 720 | 71.5 | +0.061 | – | +65.5% | – | – | – |
| **always long**, same times | 701 | 70.0 | **−0.013** | 0.95 | −13.1% | 6.3 / 27.0 | −0.013 | −0.014 |
| always short | 705 | 61.8 | −0.044 | 0.85 | −46.5% | 4.8 / 48.9 | – | – |
| hours 07/13 | 720 | 66.7 | +0.014 | 1.06 | +14.8% | 14.6 / 11.8 | +0.002 | +0.050 |
| hours 09/13 | 669 | 69.7 | +0.036 | 1.17 | +36.4% | 25.3 / 8.0 | +0.054 | −0.014 |
| hours 08/12 | 683 | 67.5 | +0.014 | 1.06 | +14.3% | 12.1 / 12.8 | +0.004 | +0.045 |
| hours 08/14 | 770 | 63.6 | +0.026 | 1.13 | +29.9% | 22.9 / 13.7 | +0.029 | +0.018 |
| hours 09/14 | 749 | 64.8 | +0.016 | 1.08 | +17.1% | 13.2 / 10.4 | +0.011 | +0.029 |
| hours 07/12 | 713 | 64.5 | **−0.015** | 0.94 | −15.5% | 8.0 / 29.1 | −0.025 | +0.017 |

**Objection 1: 08/13 is the single peak of a fragile ridge. The honest number is about +0.015R, not +0.070R.**
- Every one of the six ±1-hour neighbours is worse. Their average is **+0.015R, PF ≈ 1.07, bootstrap pass_both ≈ 16% and Phase 1 fail ≈ 14%.** That is roughly my own strategy's level, not 54%.
- 07/12 loses money outright. The submitted pair is at least 2× better than any neighbour.
- gold_trend's own write-up admits the hours came from a 50-cell dev table. With 50 cells, the best cell's expected out-of-sample decay is exactly this large.
- **The final check does not rescue the choice of hours.** Five of the six shifted pairs were also positive in the final check (+0.017 to +0.050R). So the *broad* effect (intraday momentum at the European/US opens) is probably real. The *magnitude* that drives the 54% pass rate belongs to one hand-picked pair.

**Objection 2: the DST problem, unresolved.**
- The 08/13 UTC times move by an hour relative to both London and New York twice a year.
- gold_trend's own DST-aware version (its cycle C6a) made +0.039R and 35% pass_both. Its "learn the hours" version (C7) made +0.038R.
- Together with Objection 1, this means the hold-out (Apr–Oct, all BST/EDT) sits on a different local-time alignment than about 5 of the 22 in-sample months.

**Objection 3: concession. The direction signal is real, not drift.**
- Always-long at the same times loses −0.013R with 6.3% passes. Always-short loses −0.044R.
- 2× spread and dropping the top 10 trades barely dent it, and both sides pay.
- I can't break gold_trend on bias, costs or luck. Its vulnerability is the hours, and the judge should haircut its 52.8% pass rate toward the 15–25% that the neighbours imply.

## 2. gold_xasset

| Variant (full) | n | Win % | Avg R | PF | Boot pass_both / P1 fail | Final R | Long R / Short R |
|---|---|---|---|---|---|---|---|
| **as submitted** (current engine) | 719 | 63.4 | **+0.014** | 1.05 | 23.7 / 27.5 | +0.035 | +0.034 / −0.010 |
| 2× spread | 718 | 61.8 | **−0.002** | 0.99 | 16.5 / 37.0 | +0.033 | – |
| **always long**, same times | 696 | **67.0** | **+0.037** | **1.15** | **42.8** / 21.9 | +0.052 | +0.037 / – |
| z grid +1 step {0.75, 1.0, 1.25} | 604 | 63.1 | +0.018 | 1.07 | 22.6 / 20.9 | +0.003 | – |
| train_weeks 8 (instead of 4) | 678 | 61.7 | +0.006 | 1.02 | 19.8 / 31.5 | +0.035 | – |
| drop the 10 best trades | 709 | 62.9 | +0.007 | – | – | – | – |

**Objection 1: the FX signal destroys value relative to just buying gold.**
- At the same entry times and geometry, *always long* beats the submitted strategy:
  - win rate 67.0% vs 63.4%;
  - avg R +0.037 vs +0.014;
  - bootstrap pass_both 42.8% vs 23.7%.
- The residual signal's only effect is to turn about 45% of trades into shorts, and those break even or lose (−0.010R).
- The cross-asset idea adds negative information in-sample.

**Objection 2: the submitted numbers no longer reproduce.**
- On the current engine, the as-submitted run gives +0.014R and 23.7% pass_both, versus the claimed +0.022R and 30.1%.
- At 2× spread it is **negative (−0.002R)**, so it fails the brief's cost test.

**Objection 3: it is fragile to its own learning window.**
- train_weeks 8 instead of 4 gives +0.006R, and its own cycle c2 (6 weeks) gave +0.014R.
- The 4-week window that "works" is a noise-selected choice.
- At 2.0% risk, the Phase 1 fail rate is 27.5%, the highest in the field.

## 3. gold_prop

| Variant (full) | n | Win % | Avg R | PF | Boot pass_both / P1 fail | Dev R | Final R |
|---|---|---|---|---|---|---|---|
| **as submitted** | 782 | 60.6 | +0.019 | 1.07 | 22.7 / 19.0 | +0.036 | **−0.043** |
| always long | 782 | 59.3 | +0.013 | 1.05 | 21.2 / 27.1 | +0.013 | +0.012 |
| London fill 09 instead of 10 | 782 | 59.5 | +0.005 | 1.02 | 16.1 / 25.9 | +0.022 | −0.054 |
| London fill 11 instead of 10 | 781 | **58.8** | +0.011 | 1.04 | 19.7 / 24.2 | +0.025 | −0.042 |
| drop the 10 best trades | 772 | 60.1 | +0.010 | – | – | – | – |

**Objection 1: the edge is drift plus a dev-picked hour.**
- Always-long is within +0.006R of the strategy.
- The 08→10 UTC hour change (its cycle 2) came from dev. Moving it ±1 h drops avg R to +0.005/+0.011 and the win rate **below 60%** (59.5% and 58.8%).

**Objection 2: it fails the hard requirements out of sample.**
- In the final check it made −0.043R with a 57.7% win rate. Shorts there made −0.084R.
- The full-period 60.6% win rate is 0.6 points above the floor, and the 10 best trades are worth half of its avg R.

**Objection 3: the "prior" set is in-sample knowledge.**
- Trading the dev-chosen 2.0/0.6 set during warm-up is a sensible idea for frequency (see §6).
- But it means the first 12 hold-out weeks run on a fixed, in-sample-tuned set, not on learning.

## 4. gold_session

| Variant (full) | n | Win % | Avg R | PF | Boot pass_both / P1 fail | Dev R | Final R |
|---|---|---|---|---|---|---|---|
| **as submitted** | 757 | 61.6 | +0.011 | 1.04 | 18.3 / 20.8 | +0.026 | **−0.034** |
| always long (both slots fixed long) | 757 | 62.5 | +0.003 | 1.01 | 11.8 / 24.6 | +0.029 | −0.074 |
| London entry 07 instead of 08 | 756 | 61.2 | **−0.009** | 0.97 | 12.9 / 32.5 | +0.013 | −0.071 |
| London entry 09 instead of 08 | 758 | 62.4 | +0.026 | 1.11 | 22.5 / 12.5 | +0.047 | −0.036 |
| drop the 10 best trades | 747 | 61.0 | **+0.000** | – | – | – | – |

**Objection 1: there is no edge left once the 10 best trades are removed.**
- Without them, avg R is +0.000.
- It is negative at 2× spread (its own figure was −0.005R) and negative in the final check (−0.034R, 56.5% win rate, below the hard floor).

**Objection 2: the London hour is arbitrary.**
- 07:00 loses money (−0.009R), and 09:00 is better than the submitted 08:00.
- The slot structure has no stable optimum.
- In dev, profit came from longs (+0.044R) while shorts lost (−0.028R). In the final check, the always-long version loses −0.074R.

## 5. My defence: gold_mean_reversion under the same attacks

| Variant (full) | n | Win % | Avg R | PF | Boot pass_both / P1 fail | Dev R | Final R | Long R / Short R |
|---|---|---|---|---|---|---|---|---|
| **as submitted** | 615 | 61.3 | **+0.023** | 1.08 | 18.4 / 14.3 | +0.024 | +0.018 | +0.024 / +0.020 |
| **always long**, same times | 567 | 60.3 | **−0.017** | 0.95 | 6.1 / 30.6 | −0.000 | −0.069 | – |
| always short | 605 | 60.2 | −0.035 | 0.88 | 4.7 / 36.4 | −0.052 | +0.010 | – |
| trend_thr grid +1 step {0.6, 0.8, 1.0} | 555 | 61.3 | **+0.036** | 1.13 | 21.7 / 12.9 | +0.042 | +0.018 | +0.031 / +0.043 |
| trend_thr grid −1 step {0.2, 0.4, 0.6} | 662 | 62.2 | +0.027 | 1.09 | 21.0 / 13.3 | +0.026 | +0.031 | +0.029 / +0.025 |
| no daily-regime filter | 680 | 62.1 | +0.012 | 1.04 | 11.5 / 12.7 | +0.023 | −0.019 | +0.030 / −0.012 |
| drop the 10 best trades | 605 | 60.7 | +0.010 | – | – | – | – | – |
| 2× spread (Round 1) | 615 | 60.2 | +0.006 | 1.02 | 12.3 / 20.6 | – | – | – |

**What survives.**
- **It beats its own always-long version by +0.040R and 12 points of pass rate.** Of the five bots, only gold_trend and I pass this test; gold_xasset fails it badly and gold_prop barely clears it.
- **Both sides contribute.** Longs made +0.024R and shorts +0.020R. In the final check, longs lost and shorts carried (+0.158R), which is the opposite of a long-bias artefact.
- **Parameter neighbours are equal or better** (+0.027R and +0.036R). This is the reverse of gold_trend's hour ridge. My grid has no hand-picked clock hour, and the regime filter is doing real work: removing it halves avg R and makes shorts negative.
- **The final check stayed positive**, and I looked at it only after freezing the design.

**What I concede.**
- **Thin edge:** about 0.8 standard errors. Dropping the top 10 trades leaves +0.010R, and 2× spread leaves +0.006R. A critic can fairly call it fragile.
- **Frequency: the JSON shows 1.11 trades/day,** below the 1.2 floor. The shortfall comes from the 12 flat warm-up weeks and Sunday-stub dates; it is 1.28/day after warm-up and about 1.5 per weekday.
  - On a cold hidden-only run, it would fail this requirement, and so would likely every bot on the stock WalkForward, since all of them sit flat for 12 weeks (not measured).
  - The −1-step grid reaches 1.20/day *including* warm-up (1.38 after) with *better* avg R (+0.027R) and pass rate (21.0%). That is my Round-3 fix candidate.
- **Pass rate:** at 18.4% I am mid-table on pass rate, because my edge is per-trade and small. gold_trend's real advantage is higher expectancy, at least at its chosen hours.

## 6. Ideas I would steal for my one Round-3 revision

1. **Frequency without new parameters:** shift the trend_thr grid down one step to {0.2, 0.4, 0.6}. This was measured above, so choosing it now is a disclosed in-sample choice.
2. **gold_trend's break-even exit.** Bank any close of at least +0.1× the stop after 1–2 bars. It raised gold_trend's win rate by 8 points at unchanged expectancy (its C1/C5). My time exits average −0.12R, which is exactly the leak this fixes.
3. **gold_prop's "prior" set during warm-up,** so a cold-start hold-out trades from day 1. The prior would be the median-chosen set, not a tuned one.
4. **Sharpe objective** (gold_trend C2b): it chooses stabler sets than total R. My cycle c6 showed Sharpe at +0.042R vs +0.039R for expectancy, but with lower frequency. I would only adopt it together with idea 1.

## Closing argument

**gold_trend** has the best numbers, and its direction signal survives the always-long test, costs and outlier removal. But its 54% pass rate sits on one clock pair, and every ±1-hour neighbour gives +0.015R and about 16%. **gold_xasset** is beaten by an always-long version of itself. **gold_prop** and **gold_session** fail their final checks and lose their edge under ±1-hour shifts or top-10 removal.

**gold_mean_reversion** has a small edge, but it is the only one that is:
- symmetric across longs and shorts;
- robust to parameter shifts (neighbours equal or better);
- clearly better than always-long;
- positive in a final check looked at only after the design was frozen.

On a hold-out that doesn't trend like 2024–25, I would expect robustness to matter more than a dev-optimised peak.
