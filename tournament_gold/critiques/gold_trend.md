# gold_trend critique (Round 2): attacks on rivals, a stress test of my own bot, and my defence

**Method**
- Every number here was re-run on the **current engine** (it now closes positions across data gaps longer than 6h). Harness: `tournament_gold/runs/gold_trend/r2/attack.py`; raw rows are in `r2/attack_log.jsonl`.
- Rival files were never edited. Every variant is built in memory from the rival's own `STRATEGY` (same walk-forward, grid, risk and exits). Only the stated field changes, or the entry sign is overwritten:
  - **always long**: every entry signal becomes +1;
  - **coin**: every entry gets a random side;
  - **short**: every entry signal becomes −1.
- **Full** = 2024-05-31 → 2026-03-31. **Final** = trades from 2025-11-01 on, with learning continuing, scored as `--trade-from`.
- **Drop-top-10** = avg R after removing the 10 best trades.
- **Truncation test** (`r2/trunc.py`): all five bots pass, 0 of 60 truncation points mismatched. Nobody has a look-ahead bug, so the attacks below are about edge, not leaks.

### Re-run of the headline numbers (current engine)

| bot | full win% | full avg R | PF | trades/day (CLI) | boot pass_both | P1 fail | drop-top-10 R | final win% / R / boot |
|---|---|---|---|---|---|---|---|---|
| **gold_trend** | **71.9** | **+0.070** | **1.34** | 1.32 | **52.8** | **3.6** | **+0.061** | 69.4 / +0.055 / 41.9 |
| gold_xasset | 63.4 | +0.014 | 1.05 | 1.30 | 23.9 | 26.5 | +0.007 | 61.1 / +0.035 / 24.8 |
| gold_prop | 60.6 | +0.019 | 1.07 | 1.42 | 23.9 | 20.2 | +0.010 | 57.7 / −0.043 / 4.5 |
| gold_mean_reversion | 61.3 | +0.023 | 1.08 | **1.11** | 18.9 | 15.9 | +0.010 | 61.8 / +0.018 / 15.8 |
| gold_session | 61.6 | +0.011 | 1.04 | 1.37 | 18.5 | 23.2 | 0.000 | 56.5 / −0.034 / 1.5 |

gold_xasset's write-up claims 64.1% / +0.022R / 30.1% bootstrap pass rate. On the current engine those become 63.4% / +0.014R / 23.9%.

---

## 1. gold_xasset

1. **Its direction signal does worse than "always long".** Same timing, exits and walk-forward, but every signal forced long:

   | variant | full win% | avg R | PF | boot pass_both | P1 fail | final avg R |
   |---|---|---|---|---|---|---|
   | real | 63.4 | +0.014 | 1.05 | 23.9 | 26.5 | +0.035 |
   | always long | 67.0 | +0.037 | 1.15 | 41.5 | 22.4 | +0.052 |

   Always-long beats the real strategy on every row, in the full period and the final check. The dollar-residual "follow" sign removes value: about −0.023R per trade, and about 18pp of pass rate. In-sample shorts are −0.010R; forcing every signal short gives −0.051R.
2. **Without the drift it is a coin flip.** Two coin-flip directions on the same entries give −0.019R and −0.044R, against +0.014R for the real strategy. Of the +0.033 to +0.058R gap over coin flips, most is explained by always-long (+0.037R). The residual signal adds nothing beyond gold's drift.
3. **Small parameter changes flip the sign.**
   - `train_weeks` 4 → 6: −0.007R, 14.2% pass rate, 39% P1 fail.
   - `z_win`/`beta_win` 500 → 250: −0.003R.
   - 500 → 1000: +0.010R.
   - Only `train_weeks=3` holds up (+0.019R).

   The "learning" is selection noise around zero.
4. **It fails 2× spread on the current engine:** −0.002R, PF 0.99, 16.0% pass rate, 36.5% P1 fail. Its write-up cites +0.006R from the old engine. Its own cold-start test (−21.9% on a fresh Apr–Oct 2025 run) is the most worrying fact for a hidden-data judge.

## 2. gold_prop

1. **It failed the final check, as it admits:** 57.7% win, −0.043R, 4.5% pass rate. Both sides lost. A strategy that fails the user's 60% floor and avg R > 0 on the only untouched period cannot win under rule 1.
2. **The edge is drift.** Always-long gives +0.013R and 20.9% pass rate, against +0.019R and 23.9% for the real strategy; the trend direction adds +0.006R. Always-short gives −0.052R and 2.2% pass rate.
3. **The cycle-2 hour move (08 → 10 UTC) is a dev artefact.** Moving the London fill to 09 gives +0.005R (final −0.054R); moving it to 11 gives +0.011R (final −0.042R). Shifting all three sessions by +1h gives −0.010R and 11.9% pass rate. Removing the vol filter gives +0.005R.
4. **It fails 2× spread:** −0.004R, PF 0.99, 13.5% pass rate, 31.4% P1 fail. Final at 2× spread: −0.059R.

   I credit gold_prop with the "always-long version of yourself" benchmark. It is the right test, and I apply it to myself below.

## 3. gold_mean_reversion

1. **It fails the frequency rule as the judge measures it:** CLI `trades_per_day` = **1.11** (< 1.2). Its "1.28 post-warm-up" and "1.53 per weekday" are not the judge's number. On a hold-out run cold, the 12 flat weeks make this worse.
2. **Trying to fix frequency kills the edge.**
   - `against_mult` 2 → 1 (allow counter-trend trades): 1.23/day but +0.012R; final −0.019R; 12.6% pass rate.
   - Hard trend filter (`against_mult=∞`): 0.68/day.

   There is no setting that meets ≥1.2/day with positive final expectancy.
3. **The final check is thin and lopsided.** Final +0.018R; longs −0.049R (97 trades), shorts +0.158R (only 47). Drop-top-10 R over the full period falls to +0.010. `atr_len` 24 → 48 turns the final to −0.040R, and hours (2, 18) give a final of −0.020R.
4. **2× spread:** +0.006R, PF 1.02, 12.3% pass rate.

   Credit where it's due: its direction is real. Always-long gives −0.017R and coin flips −0.036/−0.020R, so the session-pullback logic adds about +0.04R over both. This is the most honest edge among the rivals, but it is diluted below the frequency floor.

## 4. gold_session

1. **It failed the final check:** 56.5% win, −0.034R, 1.5% pass rate.
2. **Its 60% win rate is bought by the bail-out exit, at the cost of half its expectancy.** With `bail_atr=0` the full period gives 54.9% win but **+0.029R** and 29.8% pass rate, against 61.6%, +0.011R and 18.5% with the bail. This is exactly the brief's trap: win rate bought with expectancy.
3. **The London hour is fragile.** Entry at 07 gives −0.009R (final −0.071R); at 09 it gives +0.026R (final −0.036R). Always-long gives +0.003R, so the per-slot follow/fade learning adds only about +0.008R over drift.
4. **2× spread:** −0.005R, PF 0.98.

---

## 5. Self-attack: gold_trend

| test (full / final) | win% | avg R | PF | boot pass_both | P1 fail |
|---|---|---|---|---|---|
| **real (08/13 UTC)** | 71.9 / 69.4 | **+0.070 / +0.055** | 1.34 | 52.8 / 41.9 | 3.6 |
| **always long**, same everything | 70.0 / 72.2 | **−0.013 / −0.014** | 0.95 | 6.0 / 11.8 | 27.8 |
| always short | 61.8 / 64.0 | −0.044 / −0.019 | 0.85 | 4.6 | 49.0 |
| coin flip, 5 seeds (full) | 63.5–67.8 | −0.027, +0.011, −0.016, −0.001, −0.001 (mean **−0.007**) | 0.90–1.05 | 4.5–13.8 | 19–37 |
| coin flip, 5 seeds (final) | 59–72.5 | +0.062, −0.057, −0.057, +0.056, +0.044 | – | 0.3–48.9 | – |
| 2× spread | 71.6 / 69.4 | +0.060 / +0.048 | 1.29 | 45.1 / 37.6 | 4.5 |
| drop top-10 trades | – | +0.061 / +0.017 | – | – | – |

**Hour shifts** (full walk-forward each; full / final avg R):

| hours | 07/12 | 07/13 | 08/12 | **08/13** | 08/14 | 09/13 | 09/14 | 10/15 | DST local 08 | DST local 09 |
|---|---|---|---|---|---|---|---|---|---|---|
| full avg R | −0.015 | +0.014 | +0.014 | **+0.070** | +0.026 | +0.036 | +0.016 | +0.019 | +0.040 | +0.022 |
| final avg R | +0.017 | +0.050 | +0.045 | +0.055 | +0.018 | −0.014 | +0.029 | +0.086 | +0.044 | −0.004 |
| full win% | 64.5 | 66.7 | 67.5 | 71.9 | 63.6 | 69.7 | 64.8 | 65.1 | 70.7 | 67.7 |
| boot pass_both | 8.3 | 13.8 | 12.6 | 52.8 | 21.9 | 24.8 | 12.7 | 13.7 | 30.8 | 20.1 |

Training-window shifts: `train_weeks` 8 gives +0.027R; 16 gives +0.045R (final +0.057R).

**What this shows, honestly:**
1. **08/13 is the peak of a hill, not typical of it.** The 9 neighbouring timings average **+0.019R** full, and 8 of 9 are positive. My +0.070 is about 3.5× the neighbourhood, so most of the excess is selection. Expect +0.02–0.04R on the hold-out, not +0.07.
2. **The final check does not prove my direction signal.** In Nov–Mar, 3 of 5 coin-flip directions on my timing and exits earned +0.044 to +0.062R. In that volatile window, the exit geometry (break-even rule plus 0.5–0.7× targets) carried a lot. The full-period coin mean (−0.007R) is the better yardstick.
3. **It is not "buy gold".** Always-long on my timing *loses* (−0.013R, 6% pass rate), while the real signal earns +0.070R and shorts earn more per trade than longs (+0.083 vs +0.060R). I am the only bot whose always-long version loses money while the real strategy makes money in every test row.

## 6. Defence and closing argument
- **Rule 1 (hard requirements).** On the final check, gold_trend is the only bot with **win ≥ 60%, avg R > 0, trades/day ≥ 1.2 (CLI) and 0 breaches** in the full period, the final check, and at 2× spread.
  - gold_prop and gold_session fail the final check.
  - gold_mean_reversion fails trades/day (1.11).
  - gold_xasset loses to its own always-long version and fails 2× spread. On the final check it trades only **1.19/day**, so it misses the frequency rule exactly where it matters. Mine is 1.46.
- **Edge vs drift, on everyone's own timing** (real minus always-long, full avg R):

  | bot | real − always-long |
  |---|---|
  | gold_trend | **+0.083** |
  | gold_mean_reversion | +0.040 |
  | gold_session | +0.008 |
  | gold_prop | +0.006 |
  | gold_xasset | **−0.023** |

- **Robustness under attack.**
  - My *worst-case honest* estimate is the hour-shifted average, +0.019R with a 64–71% win rate. That is roughly what the best rivals claim as their *central* estimate (+0.014 to +0.023R).
  - Even the DST-aware version (theory-driven hours, not picked from the dev table) gives +0.040R full / +0.044R final, 70.7% win, 30.8% pass rate. It beats every rival's headline.
  - It survives 2× spread (+0.060R) and dropping the top 10 trades (+0.061R).
- **The real risks I accept:**
  - the 12-week cold start on the hold-out (trades/day and lost weeks);
  - an overstated point estimate.

## 7. Ideas to steal for my one Round-3 revision (pick one)
1. **gold_prop's prior set during warm-up.** Trade a fixed default candidate until 12 weeks of history exist, instead of sitting flat. This directly fixes my biggest hold-out risk (12 flat weeks drag trades/day and pass rate). It is the top candidate.
2. **DST-aware session clocks** (from gold_session's London/NY-local clocks and my own C6a). They score lower than 08/13 in-sample, but they are theory-anchored and consistent full vs final (+0.040 / +0.044R). The alternative is to average the two clocks.
3. **gold_xasset's flat-before-19:00-UTC rule**, which guards against roll-gap jumps. My flat is at 20:00; the extra hour is cheap insurance.
4. **gold_mean_reversion's soft daily-regime filter.** It requires a bigger move to trade against the 20-day trend, which might lift my weaker 13:00 longs. It is lower priority because it cuts frequency.
