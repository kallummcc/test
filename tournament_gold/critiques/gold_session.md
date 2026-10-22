# Round 2 cross-examination — gold_session (FX Bot 3, session / time-of-day lane)

## Method
- Every number below was re-run by me on the **current engine** (with the >6h data-gap close).
  I loaded patched *copies* of each rival file from `tournament_gold/runs/gold_session/rivals/`;
  no rival file was edited.
- The harness and raw outputs are in `tournament_gold/runs/gold_session/`:
  - `atk.py`, `atk_*.py`, `atk2_*.py`
  - `atk_*.out`, `atk2_*.out`
- Standard tests applied to every bot:
  - **Always-long control:** same timing, exits, walk-forward and risk; only the side forced to +1.
  - **Drop the top-10 trades** by dollar P&L.
  - **2× spread.**
  - **Long/short split.**
  - **Cold start:** 2025-04-01 → 2025-10-31 with no prior data, i.e. a hold-out-length run
    with the walk-forward warm-up inside it.

**The session test (my lane).**
- The judge's hold-out is **Apr–Oct 2026**. That is almost entirely **"summer" clock time**:
  US DST runs from 8 Mar to 1 Nov and UK DST from 29 Mar to 25 Oct.
- So I split every bot's in-sample trades by DST regime:
  - **summer** — UK and US both on DST;
  - **winter** — both on standard time;
  - **mismatch** — the 2–3 weeks each spring/autumn when only one clock has moved.
- I also ran a **summer-weeks-only bootstrap**: FTMO challenges built only from traded weeks
  whose Monday falls in summer time. This is the closest in-sample proxy for the hold-out clock.
- **Caveat that applies to everything below:** in-sample, the regime split is also a calendar
  split. Summer means Jun–Oct 2024 and Apr–Oct 2025; winter means Nov 2024–Mar 2025 and the whole
  final-check window, Nov 2025–Mar 2026. Season and market regime are confounded, with about 40
  summer and 36 winter weeks.

**Summer vs winter, all bots (same engine and costs):**

| Bot | Summer avg R / WR | Winter avg R / WR | Summer bootstrap pass_both / P1 fail | Winter pass_both / P1 fail | Cold start (Apr–Oct 2025) trades/day, WR, R |
|---|---|---|---|---|---|
| gold_trend | +0.044 / 70.8% | +0.079 / 72.2% | **39.1% / 7.2%** | 64.2% / 2.9% | not run |
| gold_prop | **+0.058 / 62.9%** | −0.036 / 57.0% | **52.9% / 9.4%** | 4.3% / 47.8% | 1.48, 65.4%, +0.089 |
| gold_xasset | −0.011 / 63.3% | +0.046 / 63.5% | 14.6% / 46.0% | 45.9% / 3.8% | 1.24, 59.4%, **−0.056** |
| gold_mean_reversion | **−0.027 / 57.4%** | +0.105 / 66.5% | **6.8% / 41.5%** | 72.2% / 1.9% | **0.78**, 60.6%, −0.018 |
| gold_session (me) | +0.032 / 64.3% | −0.004 / 59.6% | 38.3% / 16.6% | 13.1% / 31.1% | **0.94**, 63.6%, 0.000 |

---

## gold_trend (the leader: 71.9% WR, +0.070R, 52.8% bootstrap)

I reproduced its headline exactly on the current engine:

| Metric | Value |
|---|---|
| Trades | 730 |
| Trades/day | 1.32 |
| WR | 71.9% |
| Avg R | +0.070 |
| PF | 1.34 |
| Bootstrap pass_both | 52.8% |
| 2× spread | +0.060R, 45.1% |

What survived my tests, credited fairly:

- **Always-long control.** Same timing, exits and walk-forward, side forced long: **−0.013R,
  PF 0.95, 6.0% pass**. gold_trend's direction signal is worth about **+0.08R per trade** over
  "buy gold". That is the only bot of the five, mine included, with a clearly non-trivial
  directional edge over its own always-long control.
- **Drop the top-10 trades:** +0.061R, PF 1.29.
- **Walk-forward truncation test** (cuts at 2025-03-14 and 2025-09-19): **0** mismatched
  entry/exit rows out of 4,375 and 7,281. I found no look-ahead.

**Objection 1 — the edge is not a London-open or NY-open effect, so its own narrative is wrong,
and the 08/13 UTC choice looks like a narrow data-mined peak.**

If the edge belonged to the London and New York opens, it would follow the *local* clock. It
doesn't:

| Decision times (UTC) | Local clock in that regime | Avg R |
|---|---|---|
| 08/13, winter | 08:00 London / 08:00 ET | **+0.079** |
| 07/12, summer | 08:00 London / 08:00 ET (same local times) | **−0.061** (shorts −0.116, PF 0.67) |
| 08/13, summer | 09:00 London / 09:00 ET | **+0.044** |
| 09/14, winter | 09:00 local | **+0.012** |

So the 08:00-local London/NY open is great in winter and loses in summer, and the 09:00-local
open is the reverse. Only the fixed **UTC** pair 08/13 works in both regimes.

- No London or New York institution runs on UTC. The plausible fixed-UTC anchors are
  Asian/Chinese sessions, which have no DST: for example Shanghai's 20:00 Beijing night-session
  open is 12:00 UTC.
- The more parsimonious reading is a hand-picked peak from a 50-cell table. gold_trend itself
  reports that ±1h shifts lose most of the edge, and I confirm it per regime:
  - (7,12) gives −0.015R and 8.0% pass overall.
  - (9,14) gives +0.016R and 13.2% pass overall.
- The "session-open momentum" mechanism in their §5 is therefore not what the backtest
  measures.

**Objection 2 — DST will not break it, but the hold-out clock is its weaker half.**

- Because it ignores DST, its Apr–Oct 2026 clock is the same as its in-sample summer clock. So
  the honest hold-out expectation is the **summer** sub-sample, not the full-sample headline.
- In summer, avg R is **+0.044** (PF 1.21) vs +0.079 in winter, and the summer-only bootstrap
  is **39.1%** vs 64.2% in winter.
- The **13:00 UTC slot in summer** (09:00 ET, 30 minutes after the 08:30 ET data) has **65.9%
  WR, +0.025R, PF 1.10**.
- **Summer shorts make +0.014R** (PF 1.06). The "shorts beat longs" defence (+0.083 vs +0.060
  overall) comes from **winter shorts (+0.121R)** and **mismatch weeks (+0.155R overall, shorts
  +0.227R, on only 75 trades)**.
- Strip out the mismatch weeks, about 10% of trades with roughly 2× the average R, and its
  headline shrinks.

**Objection 3 — the 52.8% pass rate is regime-weighted.** The 3.6% Phase 1 fail rate comes
mostly from winter weeks (2.9%). In summer weeks Phase 1 fails are 7.2%. That is still the best
or second-best of the field, but it is half the advertised pass rate. **I expect ≈ 35–40%, not
53%.**

## gold_prop (60.6% WR, +0.019R, 23.9%)

Reproduced exactly: 782 trades, 60.6% WR, +0.019R, PF 1.07, 23.9% bootstrap.

1. **Hour fragility.** It is a knife-edge on UTC hours. Its fixed fill hours (01, 10, 16 UTC)
   shifted by one hour:
   - −1h: **−0.006R, WR 56.6%**
   - +1h: **−0.010R, shorts −0.058R**

   Bootstrap pass falls from 23.9% to **12.5–13.1%**. The 10:00-UTC choice came from dev
   diagnostics, as they themselves admit.
2. **Fails the stress tests.**
   - **2× spread:** −0.004R, WR 59.2%. That misses both the WR and expectancy hard requirements.
   - **Drop top-10:** PF 1.03, +0.010R.
   - **Final check:** −0.043R, WR 57.7%.
3. **Strongly season-dependent, and the season favours it.**
   - Summer: **+0.058R, WR 62.9%, bootstrap 52.9%, P1 fail 9.4%**.
   - Winter: **−0.036R, WR 57.0%, 4.3%, P1 fail 47.8%**.

   Its "failed final check" is exactly a winter window. This is not a defence of gold_prop's
   *edge*: the sign flip by season, combined with ±1h fragility, says the signal is noise
   aligned with the summer 2024/2025 rallies. Its own always-long control is +0.013R and
   20.9%. But if the judge's summer hold-out rallies again, gold_prop is the bot most likely to
   look good *for the wrong reason*.
4. **Warm-up fix: credit.** The `prior` set means a cold start trades from day one. Cold
   Apr–Oct 2025 gives 1.48 trades/day, 65.4% WR, +0.089R. It is the only rival that handles the
   hold-out warm-up properly, and I'd steal it.

## gold_xasset (claimed 64.1% WR, +0.022R, 30.1%)

1. **It does not reproduce on the current engine.**

   | Version | WR | Avg R | PF | Bootstrap | Shorts |
   |---|---|---|---|---|---|
   | Write-up claim | 64.1% | +0.022 | 1.09 | 30.1% | −0.000R |
   | Current engine | **63.4%** | **+0.014** | **1.05** | **23.9%** | **−0.010R** |

   Drop top-10 gives **+0.007R** (PF 1.03).
2. **Its signal is worse than buying gold.** The always-long control, with the same residual
   trigger, timing, exits, walk-forward and 2% risk, gives:

   | | WR | Avg R | PF | Bootstrap pass_both |
   |---|---|---|---|---|
   | Always-long control | **67.0%** | **+0.037** | **1.15** | **41.5%** |
   | gold_xasset | 63.4% | +0.014 | 1.05 | 23.9% |

   Using the residual's *sign* costs **−0.023R per trade and −17.6pp of pass rate**. The cross-asset
   information is only used as a trigger. The direction it adds is negative value in-sample.
3. **Summer, the hold-out clock, is its bad half.** Summer: **−0.011R**, shorts **−0.061R**
   (PF 0.81), bootstrap **14.6%** with **46.0% P1 fail**. Winter: +0.046R, 45.9%.
4. **Cold start loses.** Apr–Oct 2025 cold: 1.24 trades/day, **59.4% WR, −0.056R**. This
   confirms their own warning that the 500-bar beta/z warm-up plus 4-week scoring is immature for
   the first months of a 7-month hold-out.

## gold_mean_reversion (61.3% WR, +0.023R, 18.9%, 1.11/day)

Reproduced exactly: 615 trades, 61.3% WR, +0.023R, 18.9% bootstrap.

1. **Fails a hard requirement today.**
   - Trades/day is **1.11** on the full run, below 1.2.
   - Cold Apr–Oct 2025 gives **0.78/day**.
   - On a stand-alone hold-out it cannot win, by the brief's rule 1.
2. **The edge lives entirely in winter.**
   - Summer: **−0.027R, WR 57.4%**, shorts **−0.072R**, summer bootstrap **6.8% with 41.5% P1
     fail**, which is about the random_gold line.
   - Winter: +0.105R, WR 66.5%, 72.2%.
   - The final check passing (+0.018R) is consistent with this, since it is a winter window.
3. **Always-long control:** −0.017R (summer +0.031R). So its direction logic adds about +0.04R
   over buying gold. Credit for that: it's real but small.
4. **Cost-fragile.** 2× spread gives **+0.006R** and 11.8% pass. Drop top-10 gives +0.010R.

---

## My own numbers under the same tests (defence, honestly)

**Headline** (current engine, unchanged): 757 trades, 1.37/day, 61.6% WR, +0.011R, PF 1.04,
18.5% bootstrap. Drop top-10 gives **+0.000R**. 2× spread gives −0.005R.

**Always-long control: +0.003R, 13.2% pass.** My direction logic adds only **+0.008R** over
buying gold. That is less than gold_trend (+0.083) and gold_mean_reversion (+0.040), and
gold_xasset's is negative.

**Season and slot split.**

| Regime | Avg R | WR | Bootstrap pass_both / P1 fail |
|---|---|---|---|
| Summer | +0.032 | 64.3% | **38.3% / 16.6%** |
| Winter | −0.004 | 59.6% | 13.1% / 31.1% |

| Slot | Summer | Winter |
|---|---|---|
| NY | **+0.080R, PF 1.30** | −0.070R |
| London | −0.018R | +0.064R |

Like everyone else, the split is confounded with the calendar. My failed final check is a
winter window.

**Cold start fails frequency:** 0.94/day, because of the 12 flat warm-up weeks. On a stand-alone
hold-out I'd miss the 1.2/day rule.

**Honest conclusion.** I have no meaningful directional edge over always-long, and my 60% WR
comes from the bail-out exit. My only claim:
- I am the one bot whose clocks are DST-correct by construction.
- In-sample summer, my NY slot is the strongest single summer slot measured in this review, and
  my summer bootstrap (38.3%) is level with the leader's (39.1%).

That isn't enough to call it skill.

## Closing argument

**gold_trend** is the only strategy whose direction clearly beats its own always-long control
(by about +0.08R), and it survives truncation, 2× spread and drop-top-10. It should be the
favourite, at a realistic **≈ 39% summer pass rate, not 53%**. Its edge is a narrow fixed-UTC
peak: shift ±1h, or align to local London/NY time, and it vanishes. Its stated mechanism,
session-open momentum, is not what it trades.

The rest of the field, including me, is mostly gold drift plus exit geometry:
- gold_xasset is *worse* than its always-long control.
- gold_mean_reversion fails the frequency rule and loses in summer.
- gold_prop has a strong summer number but flips sign by season and dies at ±1h.

## Ideas I'd steal for my one Round-3 revision
1. **gold_prop's `prior` warm-up set.** Trade a fixed in-sample default until 12 weeks of
   history exist. This fixes my 0.94/day cold-start frequency failure.
2. **gold_trend's direction rule:** the sign of the trailing 12–24h move at the session
   decision, not the Asian/London-session move. Its always-long gap (+0.08R) is the only proven
   directional value in the field. I would test it on my **DST-correct NY slot**, which was my
   best summer slot (+0.080R). The test is local-clock vs UTC, so the DST question gets answered
   on my side too.
3. **gold_trend's `be_after` as a learned grid axis** instead of my fixed bail 0.25. That is how
   it moved from +0.063 to +0.075R in its cycle 5.
4. **Drop the London slot in summer, or let the learner switch slots off.** It is −0.018R in
   summer. To keep 1.2/day, this would need a second NY-session entry (e.g. 10:00 and 13:00 ET)
   rather than an empty slot.
