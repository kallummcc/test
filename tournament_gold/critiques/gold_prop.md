# Round 2 cross-examination: gold_prop

## How the tests were run

Every number here was re-run on the **current engine** (with the >6h data-gap close)
over the full in-sample period, 2024-05-31 → 2026-03-31, unless a different window is
named. Harness: `tournament_gold/runs/gold_prop/r2/attack.py`. Every run is logged in
`r2/attacks.jsonl`. The rivals' files were imported read-only; copies sit in `r2/` for
reference.

Each test wraps the rival's own walk-forward and base strategy. Same grid, same
objective, same risk. Only the stated thing changes.

| Test | What changes |
|---|---|
| Always long | `entry = |entry|`: identical bars, stops, targets, exits, learning. |
| Coin flip | Each entry's side is random (3–5 seeds). Bars and geometry are identical. |
| Lag 1h | The whole signal frame shifts one bar later. This acts on the same decision an hour late, so it adds no look-ahead. |
| Hour ±1 | The rival's own hour parameter is moved one step. |
| Drop top-10 | Avg R after removing the 10 best trades. |
| 2× spread | `--spread-mult 2`. |
| Cold start | Data starts on 2025-09-15: 28 weeks with no history, the way a judge might feed a bare hold-out file. |
| Final check | `--trade-from 2025-11-01` on full data. |
| Truncation | `base.prepare()` on data cut at 3 dates vs the full data, for 6–8 grid sets. Columns compared: entry, exit, stop, target. |

**Truncation result for all five bots, mine included: 0 mismatches** (423k–565k cells each).
Nobody has look-ahead. I withdraw that line of attack.

Reference line, random_gold on the current engine (full period): WR 58.2%, avg R −0.005,
pass_both 3.5%.

---

## gold_trend (the leader)

**Reproduced exactly:** WR 71.9%, 1.32 trades/day, +0.070R, PF 1.34, pass_both 52.8%,
P1 fail 3.6%. The edge is real in-sample and it is **not** "buy gold". That should be
said first.

| Test | WR | avg R | PF | pass_both | P1 fail |
|---|---|---|---|---|---|
| **Original** | 71.9 | +0.070 | 1.34 | 52.8 | 3.6 |
| Always long | 56.8 | **−0.022** | 0.91 | 2.8 | 27.5 |
| Coin flip ×5 (mean; range) | 53.5 | −0.019 (−0.043 … +0.010) | 0.93 | 5.5 (1.2 … 11.4) | 33 |
| **Lag 1h** (same decision, filled 09/14) | 56.5 | **+0.011** | 1.05 | 13.5 | 15.7 |
| Hours 7/13 | 66.7 | +0.014 | 1.06 | 13.8 | 12.5 |
| Hours 9/14 | 64.8 | +0.016 | 1.08 | 12.7 | 10.2 |
| Hours 8/14 | 63.6 | +0.026 | 1.13 | 21.9 | 12.8 |
| DST-aware 08:00 local | 70.7 | +0.040 | 1.18 | 30.8 | 11.2 |
| 2× spread | 71.6 | +0.060 | 1.29 | 45.1 | 4.5 |
| Drop top-10 trades | – | +0.061 | – | – | – |
| Final check | 69.4 | +0.055 | 1.23 | 41.9 | 7.0 |
| **Cold start (28 weeks)** | 72.7 | +0.089 | 1.42 | 36.4 | 1.4 |

Cold start ran at only **0.84 trades/day**.

**Objections:**
1. **The edge lives in one specific hour.** Acting on the *same* decision one hour later
   cuts avg R by 84% (+0.070 → +0.011) and win rate by 15pp. Every ±1h shift of either
   clock time loses 60–80% of the edge. The 08/13 UTC pair was taken from a 50-cell dev
   table, so the true hold-out expectation is nearer the neighbourhood average, about
   +0.02R, than +0.07R.
   - It holds on the final check, which is to its credit.
   - Hidden market structure changes this could break on: an hour shift (US/UK DST
     transition weeks are in the hold-out), or a change in data-release timing.
   - The 13 UTC fill sits in the first hour of the US-data window (12:30/13:30 UTC
     releases). There, real XAUUSD spreads at a prop broker are many times the $0.30
     modelled. The 2× test doesn't capture a 5–10× spread on the release minute.
2. **The win rate comes from the break-even exit, not the signal.** Coin flips with the
   *same* exits win only 49.8–55.2%. The 72% needs the right direction *and* the
   +0.1×stop break-even scratch. That is fine, but it means one wrong-direction week
   isn't buffered by geometry: flips lose at 34% P1 fail.
3. **The trades/day hard requirement fails on a cold start.** On 28 weeks with no history
   (stock WalkForward, 12 flat weeks) it trades **0.84/day**. That breaks the ≥1.2 rule
   even though the edge is excellent (+0.089R). If the judge does not supply ≥12 weeks of
   warm-up bars, the leader is disqualified on frequency.

---

## gold_xasset

**Reproduced on the current engine:** WR 63.4%, +0.014R, PF 1.05, pass_both 23.9%.
This is lower than the write-up's 30.1% / +0.022R.

| Test | WR | avg R | pass_both | P1 fail |
|---|---|---|---|---|
| Original | 63.4 | +0.014 | 23.9 | 26.5 |
| **Always long** | **67.0** | **+0.037** | **41.5** | 22.4 |
| Coin flip ×3 (mean) | 60.5 | −0.026 | 10.7 | 49 |
| 2× spread | 61.8 | **−0.002** | 16.0 | 36.5 |
| train_weeks 8 (instead of 4) | 61.7 | +0.006 | 19.6 | 32.1 |
| Final check | 61.1 | +0.035 | 24.8 | 1.9 |
| Cold start | 63.1 | +0.043 | 29.9 | 2.4 |

Cold start ran at **1.06 trades/day**.

**Objections:**
1. **The FX signal subtracts value compared with buying gold at the same moments.**
   Always-long beats the real strategy on every metric: +0.037 vs +0.014R, pass_both
   41.5 vs 23.9%. Its shorts lose (−0.010R in-sample). The residual-z selects good
   *timing* (it beats coin flips by +0.04R), but its *direction* call is worse than
   "always long".
2. **It fails the 2× spread stress** (avg R −0.002, PF 0.99).
3. **Fragile learner.** `train_weeks` 4 → 8 halves the pass rate and cuts avg R by 57%.
   A 4-week trailing window on 18 sets is close to chasing noise.
4. Even with 4-week training, a cold start trades only **1.06/day** (< 1.2).
   Frequency on the current engine is 1.30 in-sample with no margin.

---

## gold_mean_reversion

**Reproduced:** WR 61.3%, +0.023R, PF 1.08, pass_both 18.9%, 1.11 trades/day.

| Test | WR | avg R | pass_both |
|---|---|---|---|
| Original | 61.3 | +0.023 | 18.9 |
| Always long | 60.3 | −0.017 | 7.0 |
| Coin flip ×3 (mean) | 58.7 | −0.001 | 9.8 |
| 2× spread | 60.2 | +0.006 | 12.3 |
| Hours 2–19 (from 1–19) | 60.4 | +0.025 | 20.4 |
| against_mult 3.0 (from 2.0) | 59.0 | +0.022 | 15.7 |
| Drop top-10 | – | +0.010 | – |
| Final check | 61.8 | +0.018 | 15.8 |
| Cold start | 58.7 | −0.007 | 3.4 |

Cold start ran at **0.66 trades/day**.

**Objections:**
1. **It already fails trades/day on the judge's formula.** The JSON shows 1.11 on full
   data and 0.66 on a cold start. The "1.28 post-warm-up / 1.5 per weekday" defence
   uses a different denominator from the one the judge prints.
2. **The edge over coin flips is +0.024R and barely survives costs.** 2× spread leaves
   +0.006R. Removing the 10 best trades leaves +0.010R. One flip seed (flip0) earned
   +0.011R, half of the real edge.
3. **The final-check edge is entirely 47 short trades** (+0.158R; longs −0.049R).
   The write-up admits this. A small sample on one side carries the claim.
4. *In its favour:* it is the most parameter-robust rival. Hour and against_mult shifts
   barely move it.

---

## gold_session

**Reproduced:** WR 61.6%, +0.011R, PF 1.04, pass_both 18.5%.

| Test | WR | avg R | pass_both |
|---|---|---|---|
| Original | 61.6 | +0.011 | 18.5 |
| **Always long** | 56.6 | **+0.011** | 15.5 |
| Coin flip ×3 | 52.1 | −0.007 (−0.037 … +0.016) | 12.7 |
| 2× spread | 60.6 | −0.005 | 12.3 |
| London entry 07 | 61.2 | −0.009 | 13.2 |
| London entry 09 | 62.4 | +0.026 | 22.9 |
| Final check | 56.5 | −0.034 | 1.5 |
| Cold start | 56.5 | −0.034 | 0.6 |

Cold start ran at **0.89 trades/day**.

**Objections:**
1. **Its avg R equals always-long** (+0.011 both), and one coin-flip seed beat it
   (+0.016R). The follow/fade learning adds no detectable expectancy. Only the win rate
   differs, through the bail-out exit.
2. It fails the final check (WR 56.5%, −0.034R), 2× spread (−0.005R) and cold-start
   frequency (0.89/day). The write-up already admits the first two.
3. Its own hour parameter is not at a stable optimum. 07 → −0.009R and 09 → +0.026R,
   so 08 sits on a slope.

---

## gold_prop: defence, and attacks on myself

| Test | WR | avg R | pass_both | trades/day |
|---|---|---|---|---|
| Original (full) | 60.6 | +0.019 | 23.9 | 1.42 |
| Always long (R1) | 59.3 | +0.013 | 20.9 | 1.42 |
| Coin flip ×8 (R1) | 56.4 | −0.034 | 4.4 | 1.42 |
| Hours 0/9/16 | 56.7 | −0.018 | 10.6 | 1.42 |
| Hours 2/11/17 | 60.5 | −0.010 | 11.9 | 1.42 |
| 2× spread | 59.2 | −0.004 | 13.5 | 1.42 |
| Drop top-10 | – | +0.010 | – | – |
| Final check | 57.7 | −0.043 | 4.5 | 1.34 |
| **Cold start (28 weeks)** | **62.4** | **+0.023** | **26.6** | **1.27** |

**What I concede:**
- My edge over always-long is tiny (+0.006R).
- I fail the final check and 2× spread.
- My ±1h hour shift kills the edge just as it does for gold_trend. So that objection
  applies to me too, and my 10 UTC hour was also picked from a dev diagnosis.
- gold_trend is the better signal by a wide margin: +0.09R over its coin flips against
  my +0.05R.

**What I defend:**
1. **I am the only bot that meets trades/day ≥ 1.2 on a cold start (1.27)**, because
   `PropWalkForward` trades a prior set during the 12 learning weeks instead of sitting
   flat. Every rival drops to 0.66–1.06/day. The brief says the first `train_weeks` of
   *any* data set are flat. If the hidden set arrives without history, frequency
   becomes a hard-requirement disqualifier for four of five bots.
2. **The risk engineering is honest and transferable.** Worst day −3.00%, 0 breaches,
   2% buffer, and my P1 fail is in the same range as everyone at 1.5% risk. I
   separated edge from geometry with exact-timing controls, which every bot now uses.
3. My cold-start run (Sep 2025 → Mar 2026, mostly the final-check regime) is positive:
   +0.023R, 62.4% WR, pass_both 26.6%. This partly answers the final-check failure,
   since that window starts in a different learner state.

**Closing argument.** If the judge supplies warm-up history, gold_trend should win on
expectancy, and I'd say so. Its weak spots are the 1-hour sensitivity and cold-start
frequency. If the hold-out is scored cold, the prior-set warm-up is the single feature
that keeps a bot eligible, and gold_trend's signal combined with my warm-up and risk
shell would beat both of us.

## Ideas to steal for my one Round-3 revision

1. **gold_trend's signal:** session-clock decisions, with direction = sign of the
   trailing 6/12/24h move instead of my EMA slope, plus the break-even scratch exit.
   Coin-flip tests show it is the strongest direction signal in the field, and it pays
   on both sides.
2. **DST-aware session clocks** (gold_session, gold_trend C6). They are less sensitive
   than fixed UTC hours, and the hold-out contains both DST transitions.
3. **Flat before the daily break / no signals 19–21 UTC** (gold_xasset). This removes
   gap risk on dropped roll days.
4. **Keep my own:** the prior-set warm-up, the prop objective, 1.5% / 3% risk and the
   vol-shock filter.
