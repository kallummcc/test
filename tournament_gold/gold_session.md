# gold_session: London-open and NY-open session slots on XAUUSD, re-learned weekly (FX Bot 3)

**Bottom line first.** Over the full in-sample period, `gold_session` meets the user's hard
requirements, but only just:

- **WR 61.6%**, **avg R +0.011**, **PF 1.04**
- **1.37 trades/day**
- **0 daily-limit breaches**
- **bootstrap pass_both 18.5%**, against 7.0% for `random_gold`

**It failed my final check.** On 2025-11 → 2026-03 (193 trades) it had WR 56.5%, avg R −0.034
and PF 0.88. At 2× spread it is negative over the full period (−0.005R).

On dev the walk-forward clearly beat every static candidate (+0.026R vs at best +0.003R). But
the final check, the train_weeks sensitivity and the cost stress all suggest the dev edge was
mostly selection plus gold's 2024–25 rally. I report it as it is.

## 1. Research

| Claim | Source | Use |
|---|---|---|
| Gold shows a "hat-shaped" intraday pattern. It rises robustly during eastern (Asian) hours and falls for the rest of the day, linked to Eastern physical demand. Prices also fell around the London fix in the years of alleged manipulation. | Donati & Jung, CBS MSc thesis "Gold Price Dynamics Around the Clock" — https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/ (a student thesis, not peer-reviewed) | London slot: follow vs fade the Asian move |
| Around the London PM fixing, volume and volatility jump in GC futures and GLD right after the fix starts. The first minutes predict the fix direction, and there were economic returns to trading the leak. | Caminschi & Heaney, *J. Futures Markets* 2014 — https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html ; PDF https://api.research-repository.uwa.edu.au/ws/files/4725264/A0205_use_this.pdf | Fix windows (10:30 / 15:00 London) tested in the event study. The effect is minute-scale, so hourly bars can't trade it. |
| Intraday momentum: the early-session return predicts the late-session return. | Gao, Han, Li & Zhou, *JFE* 2018 (doi 10.1016/j.jfineco.2018.05.009). Extensions to other assets via secondary citations. | NY slot: follow vs fade |
| Asian-range breakout on gold with real ticks over 2023–26 (vendor/blogger): PF ≈ 1.38, about 49% winners, 17% max DD. | MQL5 blog — https://www.mql5.com/en/blogs/post/777540 | Shows that a session breakout is a *low*-WR system. A high WR has to come from the geometry. |
| Tokyo-range sweep fade on XAUUSD, claimed 76% WR, targeting the range middle, 0.7×ATR penetration filter. | QuantConnect forum — https://www.quantconnect.com/forum/discussion/20960/institutional-xauusd-tokyo-range-liquidity-sweep-engine-76-wr-1-dd/ | An unverified claim. My fades lost (cycle 0 landscape). |
| Session time is a common source of backtest errors (broker server time, DST). | MQL5 — https://www.mql5.com/en/blogs/post/774527 (FX round) | All clocks here are Europe/London and America/New_York. |
| FTMO sizing: 1–1.5% per trade. The daily loss is measured from the day-start balance. | https://ftmo.oanda.com/?p=2463 | Risk choice |

**Contamination disclosure.** Two search-result snippets contained commentary dated after
2026-03-31: a July 2026 FXStreet/MoneyMetals piece on 2026 session returns, and an October 2026
MQL5 post that mentions its "2026" results. I did not open those pages. I did not use their
numbers, and nothing in the design depends on them. I did not fetch any gold or FX prices.
WebFetch failed with DNS errors on most PDFs, so the academic summaries come from search
abstracts.

**My own dev-only analysis** (2024-05-31 → 2025-10-31; the final-check period was excluded):

- **Hour of day.** Mean hourly returns are about 1 bp (≈ $0.30, the size of the round-trip cost)
  and positive in almost every London hour, which is the bull trend. A clock-direction bias is
  not usable.
- **Event study, 8 theory-motivated windows.** Correlation between a window's move and the next
  window's move, first half / second half of dev. Every window shows positive continuation, but
  it is weak.

| Window | Correlation H1 / H2 |
|---|---|
| NY 08–10 → 10–13 | +0.10 / +0.21 |
| PM fix 13–15 → 15–17 London | +0.04 / +0.15 |
| Asia → London AM | +0.02 / +0.07 |

  Follow-direction hit rates are only 45–54%.

## 2. Exact rules

`prop_fx/strategies/gold_session.py`, `STRATEGY = WalkForward(...)`.

**Base `GoldSession`** (bars are labelled by their open time; a decision at a bar's close fills
at the next bar's open):

- **London slot.** At **08:00 London** (Europe/London clock), take M₁ = price now − the London
  00:00 open (the Asian-session move).
  - `follow` goes in the direction of M₁; `fade` goes against it.
  - The trade is flattened at **12:00 London**.
- **NY slot.** At **09:00 or 10:00 New York** (America/New_York clock), take M₂ = price now − the
  London 07:00 open (the London-session move).
  - `follow` or `fade`, as above.
  - The trade is flattened at **entry + 3h, NY clock** (12:00 or 13:00 ET). That is before the
    17:00 ET daily break.
- **Bracket.** Stop = 1.5 × ATR(24h). Target = `tgt_r` × stop.
- **Bail-out exit (learning cycle 6).** The trade exits at the first hourly close that is
  ≥ 0.25 × ATR in profit relative to the fill (the next bar's open). That exit is executed at the
  next open.
- **Schedule.** Weekdays only. The engine also enforces no new trades after Friday 16:00 UTC and
  flattens everything by Friday 20:00 UTC.
- **DST.** Each slot uses its own city's clock. In the 2–3 spring/autumn weeks when US and UK DST
  differ, the NY slot still enters at 09:00/10:00 ET, i.e. 13:00/14:00 London instead of
  14:00/15:00. The London exit flag only applies before the NY entry hour, so it can never close
  a fresh NY trade.

**Walk-forward:**

- **Grid**, 16 sets: `lon_mode ∈ {follow, fade}` × `ny_mode ∈ {follow, fade}` ×
  `ny_entry ∈ {9, 10}` × `tgt_r ∈ {0.6, 0.8}`.
- **Schedule:** `train_weeks=12`, `refit_weeks=1` (every Monday), objective `expectancy` (total R
  in the trailing window), `min_trades=10`. The first 12 weeks of any dataset are flat.

**Account settings:**

- `risk_pct=1.5`, `max_positions=1`, `max_trades_per_day=2`, `daily_stop_pct=3.5`.
- With one position at a time and 2 trades a day, the worst day is two full stops = 3.0%. The
  3.5% daily stop leaves 1.5% of headroom for gaps through stops under FTMO's 5% limit.
- 2.0% risk would raise dev bootstrap pass to 37%, but Phase 1 fails rise to 28% and a worst day
  would reach 4%+, too close to 5% for gold news gaps. 1.0% gives 9.6% pass. 1.5% is also the top
  of FTMO's own 1–1.5% guidance.

## 3. Learning journal

Every cycle looked **only at walk-forward out-of-sample trades on dev (2024-05-31 → 2025-10-31)**.
The final-check period (2025-11 → 2026-03) was opened **once**, after the design was frozen, in a
single batch: full run, full 2× spread, random_gold full, and the learner's log. Nothing was
changed afterwards.

| Cycle | Diagnosis (dev WF out-of-sample trades) | One change | WR | Avg R | PF | Trades/day | Boot pass_both | Decision |
|---|---|---|---|---|---|---|---|---|
| 0 | — (baseline, risk 1%) | 16-set grid, expectancy | 56.1 | +0.044 | 1.15 | 1.32 | 20.0 | baseline |
| 1 | 133/277 London trades end at the time exit with 44% winners | Longer holds (London exit 14:00, NY exit 15:00 ET) | 53.9 | −0.021 | 0.94 | 1.29 | 4.1 | **revert** (time exits protect) |
| 2 | Shorts lose in both slots (−0.042 / −0.021R) | 20-day daily-trend filter | 57.7 | +0.061 | 1.22 | **0.69** | 4.2 | **revert** (fails frequency, shorts still < 0) |
| 3 | Event study: NY 08–10 move continues (corr +0.10 / +0.21) | NY reference = NY 08:00 open, entry 10/11 ET | 51.2 | −0.009 | 0.97 | 1.31 | 2.8 | **revert** |
| 4 | The learner always picks tgt 0.8, so WR stays at 56% | `objective="win_rate"` (needs R > 0), add tgt 0.4 | 64.0 | −0.025 | 0.91 | 1.32 | 0.7 | **revert** (buys WR, loses money: the brief's trap) |
| 5 | Whichever slot is long makes money | Let the learner choose fixed long/short per slot | 58.0 | +0.011 | 1.04 | 1.32 | 4.4 | **revert** |
| 6 | Brackets that resolve already win ~62%; time exits drag WR down | **Bail-out exit at first close ≥ 0.25 ATR in profit** (0.1 also tried: 66.3% / +0.020) | **63.3** | +0.026 | 1.10 | 1.32 | 9.6 (1% risk) | **keep** (only change meeting WR ≥ 60 with R > 0) |
| risk | — | risk 1.0 / **1.5** / 2.0% (daily stop 2.5 / **3.5** / 4.5) | 63.3 | +0.026 | 1.10 | 1.32 | 9.6 / **27.4** / 37.0 (P1 fail 6.8 / **19.1** / 28.3) | 1.5% |
| 7 | Shorts lose only in rally quarters (2025Q1 −0.21R, Q3 −0.11R) | `trend_n ∈ {0, 20}` as a learned grid axis | 64.0 | +0.024 | 1.09 | **1.15** | 23.8 | **revert** (fails frequency) |
| 8 | Prop-firm fit | `objective="pass_score"` | 62.9 | +0.023 | 1.08 | 1.32 | 26.4 | **revert** (slightly worse) |

**Robustness checks** (not kept, counted as variants):

- **train_weeks 8:** WR 61.5%, R +0.002, bootstrap 16.3%.
- **train_weeks 26:** WR 59.8%, R −0.014, 1.01 trades/day. Its out-of-sample span is shorter, so
  it isn't like-for-like.
- **Static candidates vs the walk-forward,** same span, final settings. The walk-forward's
  +0.026R beats all four statics:

| Static candidate (London / NY, target) | Avg R | WR |
|---|---|---|
| follow / follow, 0.8 | +0.003 | 62.3% |
| follow / fade, 0.8 | −0.010 | — |
| follow / follow, 0.6 | −0.008 | — |
| fade / follow, 0.8 | −0.060 | — |

**What the bot learned.**

- **Dev:** 62 weekly refits. London `follow` was chosen in about 80% of weeks. The NY logic
  flipped between follow and fade, and tgt 0.8 dominated.
- **Final check:** 22 refits, almost all London follow + NY follow. The latest parameters are
  London follow, NY fade, NY entry 09:00, tgt 0.6.

**Variant count.**

- 31 fixed-parameter dev runs: 8 slot-logic combinations, 9 stop/target geometries, 10
  time-stop geometries, 4 statics.
- 16 walk-forward configurations: cycles 0–8 including the two bail values and the extra
  expectancy rerun, 3 risk levels, 2 train_weeks.
- Plus the hour-of-day table and the 8-window event study.
- Grid size is 16.

## 4. Results (default costs, 2,000 bootstrap challenges)

| Run | Net % | Trades | Trades/day | WR % | Avg R | PF | Max DD % | Boot pass_both | Boot P1 fail | Hist pass_both | Hist P1 fail (n) | Daily breaches |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **gold_session dev** (→2025-10-31) | +22.3 | 564 | 1.32 | 63.3 | +0.026 | 1.10 | −13.3 | 26.2 | 16.9 | 21.3 | 9.8 (61) | 0 |
| gold_session dev, 2× spread | +8.7 | 564 | 1.32 | 62.2 | +0.010 | 1.04 | −15.3 | 18.2 | 22.3 | 17.5 | 15.9 | 0 |
| **gold_session full** | **+12.5** | 757 | **1.37** | **61.6** | **+0.011** | **1.04** | −13.3 | **18.5** | 23.2 | 14.9 | 10.3 (87) | 0 |
| gold_session full, 2× spread | −5.0 | 757 | 1.37 | 60.6 | −0.005 | 0.98 | −21.1 | 12.3 | 31.2 | 12.4 | 20.2 | 0 |
| **Final check only** (2025-11→2026-03, from the full run) | −9.8 | 193 | — | **56.5** | **−0.034** | **0.88** | — | — | — | — | — | 0 |
| random_gold dev | −12.8 | 560 | 1.31 | 57.1 | −0.023 | 0.93 | −21.1 | 2.5 | 30.1 | 0.0 | 32.8 | 1 |
| random_gold full | +6.8 | 720 | 1.30 | 58.9 | +0.009 | 1.03 | −13.7 | 7.0 | 12.2 | 1.2 | 8.1 | 0 |

By year, full run: 2024 +16.2%, 2025 +6.0%, 2026 Q1 −9.7%.

**Long vs short** (n, WR, avg R, $ P&L):

| | Dev longs | Dev shorts | Final-check longs | Final-check shorts |
|---|---|---|---|---|
| gold_session | 303, 69.0%, **+0.080R**, +$36.1k | 261, 56.7%, **−0.035R**, −$13.8k | 105, 56.2%, −0.058R, −$9.0k | 88, 56.8%, −0.006R, −$0.9k |
| random_gold | 276, 63.4%, +0.063R | 284, 51.1%, −0.106R | 76, 55.3%, −0.039R | 84, 63.1%, −0.010R |

**Reading.** On dev, the whole profit is longs and shorts subtract. random_gold shows the same
asymmetry: coin-flip longs earned +0.063R in dev. So a large part of the dev "edge" is simply
gold's rally, and the brief's gold trap applies to this strategy. Relative to random_gold, the
strategy's shorts are less bad (−0.035 vs −0.106R) and its longs slightly better (+0.080 vs
+0.063R). That margin is the only evidence of session skill, and it vanished in the final check.

## 5. Why it might still hold up (weak case)

- **Gold-specific basis.** The London slot's choice to follow the Asian move matches the
  documented Asian-hours demand pattern (Donati & Jung). The learner chose it in about 80% of
  dev weeks and almost all final-check weeks.
- **Learning beat static on dev.** Weekly re-selection beat every fixed candidate on dev, by
  +0.023R or more.
- **Prop-safe structure.** Losses are bounded and frequent small wins come from the bail-out
  exit. One position, flat every night, no swap, 0 daily-limit breaches, and Phase 1 fails at
  17–23% in bootstrap.
- **Better than random on pass rate.** Pass rates beat random_gold on dev (26.2 vs 2.5%), full
  (18.5 vs 7.0%) and at 2× spread (12.3% vs 7.0% for random at 1× spread).

## 6. Known weaknesses (most of these are already demonstrated)

1. **The final check failed:** WR 56.5% and avg R −0.034, below the 60% WR and R > 0
   requirements. If the hold-out looks like Nov 2025–Mar 2026, this bot misses the hard
   requirements.
2. **Long bias.** Dev profit is entirely longs. Shorts are negative on dev, and both sides are
   negative in the final check.
3. **The 2× spread test fails** over the full period (−0.005R, PF 0.98). The edge is about one
   cost unit.
4. **Fragile learning window.** train_weeks 8 or 26 instead of 12 gives roughly zero or
   negative R.
5. **The WR is manufactured by the exit.** The bail-out exit takes WR from 56% to 63% and halves
   expectancy (+0.044 → +0.026R). The win rate comes from geometry, not prediction, and this is
   exactly what a critic will say.
6. **Researcher degrees of freedom.** About 47 configurations were tried on 74 weeks of dev, so
   the dev numbers carry selection bias. The final check was looked at once.
7. **Warm-up.** The walk-forward is flat for its first 12 weeks on any dataset. If the hold-out
   is run on its own, about 12 of its ~30 weeks are flat, which lowers trades/day toward ~0.8.
   The judge should warm up on in-sample data.
8. **Data.** GC=F futures stand in for spot. The $0.30 spread is constant, while the real spread
   at the NY open and at 13:30 London data releases is wider and stops can slip. Hourly bars
   can't see the minute-scale fix effects in the literature.
9. **Trades/day definition.** The engine divides by every UTC date with bars, Sundays included,
   so 1.37/day is about 1.6 per weekday. The 2-trade cap and one-position limit bind on most
   days.

---

## Round 3: revision & rebuttal (final, frozen)

### The one revision (a package of related changes aimed at the attacks and the summer hold-out)

1. **Direction = gold_trend's trailing-momentum sign, on DST-correct local clocks.**
   Each slot goes with sign(close − close 12 or 24 bars ago). The lookback is a learned axis.
   This replaces my session-move follow/fade, which added only +0.008R over always-long.
   - The **London slot fills at 09:00 London**; the **NY slot at 09:00 or 10:00 New York**
     (learned).
   - In BST/EDT weeks, which is the whole Apr–Oct hold-out, that is 08:00 / 13:00 UTC. That is
     exactly gold_trend's summer clock. My Round-2 critique showed its edge does not follow the
     08:00-local clock.
   - Fades are removed.
2. **The bail-out delay is learned.** The bail-out exit (bank the first close ≥ 0.25 ATR in
   profit) may wait 1 or 2 bars (`bail_after ∈ {1, 2}`). This adapts gold_trend's `be_after`.
3. **Prior warm-up set**, stolen from gold_prop. `PriorWalkForward` trades a fixed default
   candidate (12h momentum, NY 09:00, target 0.6, bail after 1 bar) in weeks where it can't
   learn yet. It is no longer flat for the first 12 weeks.
4. **`daily_stop_pct` 3.5 → 2.0, for the judge's double-risk scoring.** The daily stop counts
   realised plus floating losses.
   - My first Round-3 build used 3.0. At 2× risk (3%/trade) it produced **12 daily-limit breach
     weeks**. A first trade that time-exited just under −3% didn't halt the day, so a second
     full 3% loser followed.
   - At 2.0%, any trade is cut once the day reaches −2% and the day halts. Worst Prague day:
     −3.0% at 1× and −4.6% at 2×. **0 breaches at either.**
   - Risk stays at 1.5%/trade, with `max_trades_per_day=2`, `max_positions=1`, and the
     WalkForward wrapper. The grid has 16 sets: mom_hours {12, 24} × ny_entry {9, 10} ×
     tgt_r {0.6, 0.8} × bail_after {1, 2}, with train 12 weeks, weekly refit and the
     expectancy objective.

**Data-use disclosure.**
- The final-check window is no longer clean. I looked at it in Round 1. Round 2 critiques of
  every bot, including the season split, used the full sample. The Round-3 design borrows
  choices validated on full data (London 09:00 from critics' ±1h tests, gold_trend's
  momentum).
- **Treat every number below as in-sample.** The only clean test is the judge's hold-out.

**Round-3 variants tried (6), all full-sample:**
- R3 with daily stop 3.0 (1× and 2× risk);
- its London-entry neighbours 08 and 10, and no bail-out;
- **R3a = R3 + daily stop 2.0 (chosen)**;
- R3b, where the learner also chooses between momentum and my Round-2 follow/fade per slot
  (24 sets), at 1× and 2×.

Before seeing R3a vs R3b, I fixed the selection rule: (1) hard requirements, (2) summer-week
bootstrap, (3) 2× spread, (4) edge over always-long.

| | R3a | R3b |
|---|---|---|
| Summer bootstrap | 29.5% | 30.8% (tie) |
| 2× spread | **+0.007R** | −0.009R |
| Real − always-long | **+0.028R** | +0.006R |

So R3a was chosen.

### Before → after (current engine, default costs, 2,000 bootstrap challenges)

| Run | Version | Trades | Trades/day | WR % | Avg R | PF | Max DD | Boot pass_both / P1 fail | Hist pass_both / P1 fail | Breaches |
|---|---|---|---|---|---|---|---|---|---|---|
| **Full** | R2 | 757 | 1.37 | 61.6 | +0.011 | 1.04 | −13.3 | 18.5 / 23.2 | 14.9 / 10.3 | 0 |
| | **R3** | 891 | **1.61** | **60.8** | **+0.028** | **1.11** | −20.5 | **32.4 / 18.8** | 29.4 / 17.6 | 0 |
| Dev (→2025-10-31) | R2 | 564 | 1.32 | 63.3 | +0.026 | 1.10 | −13.3 | 26.2 / 16.9 | 21.3 / 9.8 | 0 |
| | R3 | 692 | 1.62 | 60.4 | +0.020 | 1.07 | −20.5 | 28.0 / 22.4 | 23.9 / 22.4 | 0 |
| Final check (from 2025-11) | R2 | 193 | — | 56.5 | −0.034 | 0.88 | — | 1.5 | — | 0 |
| | R3 | 199 | 1.59 | 62.3 | +0.057 | 1.27 | −8.2 | 49.2 / 7.2 | 36.4 / 0.0 (n=11) | 0 |
| **Full, 2× spread** | R2 | 757 | 1.37 | 60.6 | −0.005 | 0.98 | −21.1 | 12.3 / 31.2 | 12.4 / 20.2 | 0 |
| | **R3** | 891 | 1.61 | 59.8 | **+0.007** | 1.02 | −29.0 | 19.7 / 28.6 | 12.8 / 29.1 | 0 |
| Dev, 2× spread | R3 | 692 | 1.62 | 59.2 | −0.002 | 0.99 | −29.0 | 17.2 / 33.0 | 12.3 / 38.5 | 0 |
| Final, 2× spread | R3 | 199 | 1.59 | 61.8 | +0.040 | 1.18 | −8.7 | 34.3 / 10.8 | — | 0 |
| Cold start (Apr–Oct 2025 file only) | R2 | 165 | **0.94** | 63.6 | 0.000 | — | — | 8.2 | — | — |
| | **R3** | — | **1.67** | 62.2 | **+0.035** | 1.14 | — | **38.2 / 9.3** | — | — |
| **Double risk (3%/trade, daily stop 2.0)** | R3 | 816 | 1.48 | 60.7 | +0.025 | 1.10 | — | **42.5 / 38.4** | 35.1 | **0** (worst day −4.6%) |
| random_gold | — | 720 | 1.30 | 58.9 | +0.009 | 1.03 | −13.7 | 7.0 / 12.2 | 1.2 / 8.1 | 0 |

**Summer-time weeks only** (UK and US both on DST, the hold-out clock; 52 traded weeks):

| Version | Trades | WR % | Avg R | PF | Long R | Short R | Summer-only bootstrap pass_both / P1 fail |
|---|---|---|---|---|---|---|---|
| R2 | 367 | 64.3 | +0.032 | 1.12 | +0.070 | −0.017 | 38.3 / 16.6 (40 weeks) |
| **R3** | 489 | 61.1 | +0.027 | 1.10 | +0.070 | **−0.037** | **29.5 / 20.2** |
| R3, 2× spread | — | — | — | — | — | — | 17.8 / 33.1 |
| R3 at double risk | 444 | 60.8 | +0.015 | 1.06 | +0.049 | −0.038 | 37.8 / 41.6 |
| (gold_trend, Round-2 measurement) | 353 | 70.8 | +0.044 | 1.21 | +0.065 | +0.014 | 39.1 / 7.2 |

**Long / short, R3:**

| Period | Longs (n / WR / avg R) | Shorts (n / WR / avg R) |
|---|---|---|
| Full | 524 / 63.0% / +0.035 | 367 / 57.8% / **+0.019** |
| Dev | 404 / 63.9% / +0.048 | 288 / 55.6% / −0.019 |
| Final | 120 / 60.0% / −0.008 | 79 / 65.8% / +0.155 |

Shorts now contribute over the full period, but not in dev or in summer weeks.

**Edge vs drift.**
- **R3 −** its own always-long version (same clocks, exits, learner, daily stop 2.0) =
  **+0.028 − 0.000 = +0.028R**, and 32.4% vs 14.2% bootstrap.
- Round 2 was +0.008R.
- Drop the top-10 trades: **+0.019R** (PF 1.07). Round 2 was 0.000.

### Point-by-point rebuttal

| Attack (who) | Round-2 fact | Round-3 answer |
|---|---|---|
| "Barely beats always-long, +0.008R" (gold_trend, gold_prop, gold_mr) | True | Now **+0.028R** over its own always-long (32.4% vs 14.2% pass). The direction signal is gold_trend's, which my critique identified as the only one that survives this test. **Conceded:** the gain comes from adopting a rival's signal, not from my session logic. |
| "Zero edge without the top-10 trades" (gold_xasset, gold_mr) | 0.000R | **+0.019R**, PF 1.07 |
| "Failed the final check" (all) | 56.5%, −0.034R | 62.3%, +0.057R, 49.2%. **But this window is now contaminated** (see disclosure). I don't count it as evidence. |
| "Cold start 0.94/day" (gold_prop, gold_xasset) | True | **1.67/day**, 62.2%, +0.035R on a cold Apr–Oct 2025 file (prior warm-up set) |
| "Bail-out buys WR at half the expectancy" (gold_trend) | True: no bail gave 54.9%, +0.029R | Still partly true. Without the bail, R3 makes +0.003R at 56.0% WR; with it, 60.8% and +0.028R. In R3 the bail now *adds* expectancy, because momentum trades that go green early tend to give it back by the time exit. The WR and expectancy now move together, which is the opposite of the brief's trap. |
| "London hour 08 sits on a slope" (gold_prop, gold_xasset, gold_mr) | 07 −0.009R, 09 +0.026R | London is now **09:00 local**. Neighbours (measured on the daily-stop-3.0 build): 08 +0.025R, 10 +0.011R. Positive on both sides, so not a knife-edge, although 08 is fractionally better overall. In summer, 08 local gives −0.000R and 10 gives +0.017R. |
| "2× spread negative" (all) | −0.005R | +0.007R, PF 1.02 full. Dev at 2× is still −0.002R. **Conceded:** the edge is about one spread-unit. |

### What is still weak (honest)
1. **Summer is not better than Round 2.**
   - R3's summer-only bootstrap is 29.5%, vs 38.3% for R2. Summer shorts lose −0.037R.
   - The full-sample improvement came mostly from winter and the (contaminated) final check.
   - I chose R3 anyway: it beats R2 on every full-sample test (2× spread, top-10, always-long
     gap, cold start, double-risk safety), while R2's summer number rests on a NY slot whose
     follow/fade choice adds nothing over always-long.
2. **The edge is about +0.03R, roughly one spread unit.** Phase-1 fails are 19% at 1× and 38% at
   2× risk.
3. **Expected hold-out result** (summer clock): about 60% WR, +0.02–0.03R, and a pass_both of
   about 25–30% at 1×. That is clearly above random_gold (7%) and well below gold_trend's
   summer ~39%.
4. **Double risk: pass up, safety down.** It raises bootstrap pass_both to 42.5% (summer
   37.8%) but **Phase-1 fails to 38–42%**. The 2.0% daily stop keeps every day under the 5%
   limit in-sample; the worst was −4.6%. Only 0.4% of headroom is left for a gap through a stop.

Files:
- `prop_fx/strategies/gold_session.py` (final; Round 2 is at git 4b25161)
- `tournament_gold/runs/gold_session/r3/`
- `tournament_gold/runs/gold_session/r3f/` (final CLI JSONs and trades)
