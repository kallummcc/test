# Round 2 critique by gold_xasset (cross-asset bot)

## How the tests were run
- Every number below was re-run on the **current engine**, which closes positions across data gaps longer than 6 h.
- Harness: `tournament_gold/runs/gold_xasset/attack/harness.py`.
  - It wraps each rival's own `STRATEGY` (same walk-forward class, grid, train window and objective) via `dataclasses.replace`.
  - It never edits their files.
- Outputs:
  - raw results: `attack/results.jsonl`
  - per-run trade lists: `attack/<tag>.csv`
  - gold_trend's patched copy: `attack/gt_patched.py`
- Unless stated otherwise:
  - the period is the full in-sample run (2024-05-31 → 2026-03-31);
  - "FC" means the trades of that run inside the final-check window (2025-11 → 2026-03);
  - bootstrap uses 2,000 challenges.

### Shared tests
- **Always long.** Same timing, geometry, exits and walk-forward, but every entry is a buy.
  - For gold_prop, gold_mean_reversion and mine, entry signs are flipped after `prepare()`. Their exits don't depend on the trade side.
  - For gold_trend the break-even exit *does* depend on the side. I used a patched copy (`sig_src='long'`) so that break-even is computed for the long trade.
  - For gold_session I used its own `"long"` mode on both slots, because its bail-out exit is side-dependent.
- **Hour or parameter shift by ±1 step.**
- **Drop the 10 best trades.**
- **2× spread.**
- **Cold start.** A 7-month file (2025-04-01 → 2025-10-31), started fresh. This mirrors a hold-out of about 7 months with no warm-up data.
- **Look-ahead truncation.** Each base strategy is computed on the full data and on data cut at 32 dates (every 17 days), for 4–5 parameter sets per bot. **0 mismatches for every bot**, so nobody is caught peeking.
- **USD decomposition.**
  - Each trade's log return is split into side × β_t × ΔUSD-index over the holding period, plus an ex-USD residual.
  - β_t is the trailing 500-bar beta of gold on my 12-pair USD index.
  - The "USD-explained" share is an upper bound: it uses the USD index to the close of the exit bar.

---

## 1. gold_trend (leader)

| Test (full period) | Win % | Avg R | PF | Boot both / P1 fail | FC win / R |
|---|---|---|---|---|---|
| As submitted (reproduced) | 71.9 | +0.070 | 1.34 | 52.8 / 3.6 | 69.4 / +0.055 |
| Decision hours 7/13 | 66.7 | +0.014 | 1.06 | 13.8 / 12.5 | 70.5 / +0.050 |
| Decision hours 9/13 | 69.7 | +0.036 | 1.17 | 24.8 / 7.8 | 67.6 / **−0.014** |
| Decision hours 8/12 | 67.5 | +0.014 | 1.06 | 12.6 / 13.1 | 71.3 / +0.045 |
| Decision hours 8/14 | 63.6 | +0.026 | 1.13 | 21.9 / 12.8 | 63.6 / +0.018 |
| Always long (patched, break-even computed for the long) | 70.3 | **−0.012** | 0.95 | 6.0 / 27.4 | 72.2 / −0.014 |
| Signal = −ΔUSD only (pure dollar trade) | 66.3 | +0.005 | 1.02 | 21.1 / 27.9 | 67.4 / +0.047 |
| Signal = gold's ex-USD residual only | 67.9 | +0.022 | 1.10 | 19.9 / 11.7 | 70.1 / +0.065 |
| Drop top-10 trades | 71.5 | +0.061 | 1.29 | — | — |
| 2× spread | 71.6 | +0.060 | 1.29 | 45.1 / 4.5 | 69.4 / +0.048 |
| **Cold start**, 7-month file | 72.7 | +0.067 | 1.28 | 30.8 / 1.8 | **0.94 trades/day** |

**Objections**

1. **The edge lives on two hand-picked clock hours.**
   - Moving *either* decision by one hour cuts avg R from +0.070 to +0.014–0.036, and the bootstrap pass rate from 52.8% to 12.6–24.8%.
   - The average of the four neighbours is +0.023R and about 18% pass. That is roughly where gold_mean_reversion and I sit.
   - The 08/13 pair was picked from a 50-cell dev table, as gold_trend admits. Its four neighbours suggest the honest hold-out expectation is **about 18–25% pass_both, not 53%**.
2. **It fails the frequency requirement on a cold hold-out.**
   - Started fresh on a 7-month file, the 12 flat learning weeks leave **0.94 trades/day**, below the 1.2 hard requirement.
   - If the judge runs the hidden Apr–Oct 2026 file without prior bars, gold_trend is disqualified on rule 1, whatever its win rate.
   - Its own write-up flags this (weakness 4/5). The number shows it is not borderline but clearly below.
3. **Shorts are regime-dependent.**
   - On the 7-month cold run, shorts made −0.037R over 68 trades, while longs made +0.140R.
   - The full-period "shorts beat longs" claim rests largely on the 2025-H2 and 2026 two-way months.

**What I could not break, conceded with evidence**
- **The direction signal is genuine.** Always long at the same times and with the same geometry *loses* (−0.012R, 6% pass).
- **It is not a USD trade.**
  - By decomposition, only +0.64 bp of its +5.20 bp mean trade return is dollar-explained. The ex-USD residual is +4.56 bp, t = 2.7, R² = 0.10.
  - Replacing its signal with the pure dollar move collapses it to +0.005R.
  - Replacing it with gold's ex-USD residual gives +0.022R.
  - So the signal needs gold's *own raw* momentum. Neither component alone reproduces it.
- **It is robust to dropping the top 10 trades (+0.061R) and to 2× spread (+0.060R).**

## 2. gold_prop

| Test | Win % | Avg R | PF | Boot both / P1 fail | FC win / R |
|---|---|---|---|---|---|
| As submitted | 60.6 | +0.019 | 1.07 | 23.9 / 20.2 | 57.7 / −0.043 |
| Entry hours −1 (00/09/15) | 56.6 | −0.006 | 0.98 | 13.5 / 32.1 | 49.7 / −0.070 |
| Entry hours +1 (02/11/17) | 60.5 | −0.010 | 0.97 | 11.9 / 34.0 | 62.1 / +0.008 |
| Always long | 59.3 | +0.013 | 1.05 | 20.9 / 25.5 | 62.5 / +0.012 |
| Drop top-10 | 60.1 | +0.010 | 1.03 | — | — |
| 2× spread | 59.2 | −0.004 | 0.99 | 13.5 / 31.4 | 56.5 / −0.059 |
| Cold start, 7-month file | 65.4 | +0.089 | 1.35 | 74.0 / 2.4 | 1.48/day |

**Objections**

1. **Its whole gross return is the dollar plus drift.**
   - Mean trade return is +0.98 bp, and **+1.05 bp of it is USD-explained**. The ex-USD residual is −0.07 bp (t ≈ 0).
   - Its "EMA trend" is, in effect, a slow dollar-trend trade on gold.
2. **The timing is a knife-edge.**
   - Shifting all three entry hours by one hour, in either direction, turns avg R negative (−0.006 / −0.010) and halves the pass rate (12–14%).
3. **The edge is not separable from beta.**
   - Always long is within 0.006R and 3 points of pass rate of the submitted strategy.
   - It fails 2× spread (−0.004R) and failed its own final check (−0.043R).
4. **The cold-start result is in-sample.**
   - The prior set (2.0 ATR / 0.6R) was chosen on dev, which contains this window. So the 74% is not evidence about a cold hold-out.
   - The *mechanism*, trading a prior set while warming up, is still the right answer to the frequency rule (see "steal" below).

## 3. gold_mean_reversion

| Test | Win % | Avg R | PF | Boot both / P1 fail | FC win / R |
|---|---|---|---|---|---|
| As submitted | 61.3 | +0.023 | 1.08 | 18.9 / 15.9 | 61.8 / +0.018 |
| daily_align 10 (vs 20) | 61.7 | +0.016 | 1.06 | 13.8 / 15.4 | 59.6 / +0.011 |
| daily_align 40 | 61.9 | +0.025 | 1.09 | 22.1 / 15.8 | 57.7 / **−0.036** |
| Signal hours 02–18 (vs 01–19) | 60.8 | +0.021 | 1.07 | 16.6 / 13.1 | 59.6 / **−0.020** |
| Always long | 60.3 | −0.017 | 0.95 | 7.0 / 28.9 | 55.9 / −0.069 |
| Drop top-10 | 60.7 | +0.010 | 1.03 | — | — |
| 2× spread | 60.2 | +0.006 | 1.02 | 12.3 / 20.6 | 61.1 / +0.015 |
| Cold start, 7-month file | 60.6 | −0.018 | 0.93 | 4.4 / 22.4 | **0.78 trades/day** |

**Objections**

1. **It fails the frequency requirement twice.**
   - On the judge's own formula it trades 1.11/day over the full period, and **0.78/day** on a cold 7-month file.
   - Over that cold window it also loses (−0.018R, 4.4% pass).
2. **The final-check result is fragile.**
   - Its positive final check (+0.018R) turns negative under one-step neighbours: SMA40 gives −0.036, and hours 02–18 give −0.020.
3. **The edge is thin.**
   - Dropping the top 10 trades halves avg R, to +0.010.
   - 2× spread leaves +0.006R, and the pass rate falls to 12%.

**Concession:** its direction logic is real. Always long loses (−0.017R, 7% pass), and its ex-USD residual is positive (+1.39 bp, t = 0.8).

## 4. gold_session

| Test | Win % | Avg R | PF | Boot both / P1 fail | FC win / R |
|---|---|---|---|---|---|
| As submitted | 61.6 | +0.011 | 1.04 | 18.5 / 23.2 | 56.5 / −0.034 |
| Always long (its own `"long"` mode) | 62.5 | +0.003 | 1.01 | 13.2 / 24.6 | 58.0 / −0.074 |
| London entry 07 (vs 08) | 61.2 | −0.009 | 0.97 | 13.2 / 32.9 | 56.2 / −0.071 |
| London entry 09 | 62.4 | +0.026 | 1.11 | 22.9 / 12.2 | 58.2 / −0.036 |
| Drop top-10 | 61.0 | **0.000** | 1.00 | — | — |
| 2× spread | 60.6 | −0.005 | 0.98 | 12.3 / 31.2 | 56.0 / −0.048 |
| Cold start, 7-month file | 63.6 | 0.000 | 1.00 | 8.2 / 14.6 | **0.94 trades/day** |

**Objections**

1. **The edge comes from about ten trades.** Its entire avg R disappears when the 10 best trades are removed (+0.011 → 0.000).
2. **Its losses are on the short side.** Longs made +0.044R and shorts −0.028R (−14.6% net).
3. **It failed every robustness test.**
   - 2× spread is negative.
   - The final check is negative.
   - Its London-hour neighbour 07 is negative.
   - A cold start gives 0.94/day and 0.000R.

---

## 5. Defence of gold_xasset (re-run on the current engine)

The gap-close fix changed my numbers, so all figures below are new.

| Test | Win % | Avg R | PF | Boot both / P1 fail | FC win / R |
|---|---|---|---|---|---|
| **As submitted, current engine** | 63.4 | +0.014 | 1.05 | 23.9 / 26.5 | 61.1 / +0.035 |
| Previously reported (old engine) | 64.1 | +0.022 | 1.09 | 30.1 / 22.9 | 59.9 / +0.019 |
| **Always long, same timing and geometry** | **67.0** | **+0.037** | **1.15** | **41.5 / 22.4** | 69.1 / +0.052 |
| Drop top-10 | 62.9 | +0.007 | 1.03 | — | — |
| 2× spread | 61.8 | **−0.002** | 0.99 | 16.0 / 36.5 | 60.4 / +0.033 |
| Cold start, 7-month file | 59.4 | **−0.056** | 0.82 | 6.8 / **68.4** | 1.24/day |
| Long / short (full) | L 64.9 / +0.034 | S 61.7 / **−0.010** | | | |

### The honest verdict on my own bot
1. **My direction logic is worse than buying gold at my entry times.**
   - The always-long version of my bot beats the real one on every metric: +0.037R vs +0.014R, and 41.5% vs 23.9% pass.
   - My residual signal adds no value. It just puts about 45% of trades on the short side, and those shorts lose in a bull market.
   - What remains positive in my bot is my *timing and geometry*, plus gold's drift. That is beta, not an edge.
2. **My signal is not what my P&L is made of.**
   - The decomposition says +1.36 bp of my +2.13 bp mean trade return is USD-explained. The ex-USD residual is only +0.77 bp (t = 0.45).
   - My signal is built on the ex-USD residual, yet that is not where my money comes from.
3. **It is fragile.**
   - It fails 2× spread (−0.002R) and loses most of its edge without its top 10 trades.
   - On a cold 7-month file it loses 24%, with a 68% Phase 1 fail rate.
   - Its one strength is the frequency rule: train_weeks = 4 still gives 1.24/day cold. But a cold start costs edge.

**What still stands:**
- It meets the hard requirements on the full period: 63.4% win, +0.014R, 1.30/day, no daily-limit breaches.
- The final check was positive on both sides: 61.1% win, +0.035R.
- It reported the futures-roll data-gap bug, which the engine fixed and which changed everyone's numbers.
- It was the only bot to test whether the leader is "just a USD trade". It is not.

### Closing argument
- The cross-asset question has a clean answer now.
  - The dollar explains about 10% of the variance of gold trade returns.
  - It explains **none of gold_trend's edge**.
  - It explains **all of gold_prop's gross return**.
- On the evidence, gold_trend has the only edge that survives:
  - always-long (it loses);
  - USD-stripping (88% of its P&L is ex-USD);
  - top-10 removal;
  - 2× spread.
- But its pass rate is inflated by the 08/13 choice. The neighbouring hours suggest about 20%, not 53%. It also fails the 1.2/day rule on a cold 7-month hold-out (0.94).
- The judge should therefore score everyone on the cold hidden file, and discount gold_trend's in-sample pass rate by its hour sensitivity.
- My own bot, honestly, is a timing-and-geometry shell with a direction signal that hurts. I would not rank it above gold_trend.

## 6. Ideas to steal for my one Round-3 revision
1. **Make gold's own raw momentum the direction and the USD residual a filter.**
   - My one revision would follow gold_trend's evidence and use gold's raw momentum as the direction.
   - The USD component would become a *veto*, not the signal: for example, skip a short when gold's move is fully dollar-explained.
   - My always-long result shows my residual direction is negative-value.
2. **gold_trend's break-even exit.** Bank +0.1× stop from bar 1–2. It added +8 points of win rate at unchanged expectancy, and my time exits average −0.2R.
3. **gold_prop's prior set during warm-up.** Trading a fixed default set instead of sitting flat removes the cold-start frequency failure while keeping a longer, less noisy training window (12 weeks).
4. **The Sharpe objective** (gold_trend C2b) instead of total-R expectancy. It picked steadier sets in their tests.
5. **Session-anchored decisions** (gold_trend and gold_prop) instead of signals at any hour. This gives fewer, better-timed trades. The hour-shift results say not to over-trust a single hour, so I would let the walk-forward choose among 2–3 session pairs.
