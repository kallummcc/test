# FX Bot 2: Mean reversion ("fx_mean_reversion")

**Rule in one line:** between 07:00 and 16:59 UTC, when an hourly close is more than **1.25 daily ATR(20)** away from **yesterday's pivot (H+L+C)/3**, fade the move at the next open. Use a 1.25-ATR stop, take profit back at the pivot, and exit after 48 h or at the Friday flatten. Risk is **1.5%** per trade, with **5** positions at most and a **3.0%** daily stop.

Code: `prop_fx/strategies/fx_mean_reversion.py`. Scratch scripts, the variant log (`variants.csv`), the final JSONs and `full/trades.csv` are in `tournament_fx/runs/fx_mean_reversion/`.

---

## 1. Research

| Source | What it says | How I used it / caveat |
|---|---|---|
| Krohn, Mueller & Whelan, *Foreign Exchange Fixings and Returns around the Clock*, J. Finance 79(1) 2024 ([WRAP](https://wrap.warwick.ac.uk/id/eprint/177333), [AEA working paper](https://topcat.aeaweb.org/conference/2020/preliminary/paper/2dedYfDH), [Bank of Canada SWP 2021-48](https://www.bankofcanada.ca/wp-content/uploads/2021/10/swp2021-48.pdf)) | The USD appreciates into the Tokyo, ECB and London fixes and reverses afterwards. The pattern holds across 9 currencies over 21 years, and the authors attribute it to dealer inventory hedging. | This is the best-documented *intraday reversal* mechanism in FX: dealers who absorb one-sided flow later unwind it. The effect is a few bp, too small to trade at a fixed clock time on our costs (my hour-of-day scan agrees, §6). I use it only as the mechanism for why **large** liquidity-driven moves partly revert. |
| Osler, *Currency Orders and Exchange-Rate Dynamics*, NY Fed Staff Report 125 ([PDF](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf)) | Take-profit orders cluster at round numbers and prominent levels, which produces reversals. Stop-loss orders sit just beyond those levels, which produces cascades. | This supports fading moves that are stretched far from a reference level, with a reference level as the target. The caveat: Osler's data come from one bank in the 1990s. |
| Dao, McGroarty & Urquhart (2016), weekend-gap overreaction in FX ([Southampton](https://eprints.soton.ac.uk/402301)) | After a large Friday-to-Monday gap, most FX markets tend to reverse over the following week. | This is evidence of overreaction after **large** moves specifically, not after ordinary noise. |
| EURUSD 1-minute mean reversion, *Folia Oeconomica Stetinensia* 2015 ([link](https://reference-global.com/article/10.1515/foli-2015-0014)) | The study finds statistically significant intraday mean reversion in EURUSD. | It says nothing about costs. At 1-minute horizons the effect would not survive our spreads. |
| Connors RSI(2) on EURUSD daily ([Backtrex](https://backtrex.com/en/backtests/connors-rsi-2-eur-usd)) | The rule made a PF of 0.78 over about 75 trades from 2016 to 2026. | **Negative evidence.** Classic equity mean-reversion rules don't port to FX. My own RSI(2)-hourly and daily tests agree (§6). |
| Heston, Korajczyk & Sadka, intraday reversal patterns ([arXiv](https://arxiv.org/pdf/1005.3535)) | Half-hour reversals of a few bp exist, but they are not profitable after costs. | This is the warning that small-move fades get eaten by the spread. So I fade only **≥1.25 daily ATR** stretches, where the expected snap-back is several times the cost. |
| Asian-range fade / breakout practitioner material ([babypips thread](https://forums.babypips.com/t/london-daybreak-strategy-a-few-questions/474405), [opper.ai EURGBP note](https://opper.ai/ai-roundtable/questions/london-liquidity-bot-final-stress-test-strategy-asian-range-3e7dc182)) | Practitioners report no verifiable edge. Live spreads at 07:00–08:00 UTC run well above demo spreads, and live results diverge from backtests. | I tested the Asian-range fade myself and it was ≤0 net (§6), so I rejected it. |
| Prop-firm risk guidance ([Backtrex: prop rules backtesting](https://backtrex.com/en/blog/backtesting-prop-firm-rules), [Backtrex FTMO guide](https://backtrex.com/en/blog/ftmo-challenge-strategy-guide), [LuxAlgo FTMO review](https://www.luxalgo.com/blog/ftmo-prop-firm-review-how-to-pass-in-2025/)) | Risk 0.5–1.5% per trade. Simulate the **daily** limit, because floating P&L counts. Mean reversion carries fat-tail risk when a level breaks. | I sized the daily stop at two full losers, and I report the weeks where the 5% daily limit was breached. |

**Caveats on the research.** I read several of these sources only through search summaries, not in full. I found no peer-reviewed study of an hourly FX fade *net of retail/prop costs*. The academic support is for the *mechanism* (dealer inventory and order clustering produce partial reversal after large moves), not for this exact rule.

**Data caveat found during research.** On the Yahoo **daily** files (2003–2023), internal-bar-strength fades show an absurd +0.3 to +0.6 ATR per trade on all 12 pairs. The same signal built from the hourly bars is close to zero. The daily highs, lows and closes are not consistent intraday prints, so I used the daily files only for sign checks and never for parameter choice.

## 2. Exact rules

All times are UTC. Daily bars are built from the pair's own hourly bars on UTC-midnight boundaries, with Sunday stubs dropped. A daily feature becomes visible only once that day has fully closed, using the same alignment as `higher_tf`. Truncation test: running `prepare()` on data cut at 4 dates gives **0 mismatched rows out of 423,564**.

1. **Reference:** yesterday's pivot P = (H + L + C) / 3 of the last closed UTC day.
2. **Scale:** ATR(20) of daily bars.
3. **Stretch:** s = (hourly close − P) / ATR.
4. **Entry:** on an hourly bar opening between 07:00 and 16:00 UTC, go **short if s > 1.25** or **long if s < −1.25**. The signal fires only on the first bar of an excursion, at most once per pair per UTC day, and fills at the next bar's open.
5. **Stop:** 1.25 × ATR from entry.
6. **Target:** |close − P| measured at the signal bar, so the take-profit sits roughly back at yesterday's pivot. That works out to about 1.25+ ATR, so R:R is ≥ 1:1.
7. **Time exit:** 48 h after the signal. The engine also closes everything at Friday 20:00 UTC and opens nothing after Friday 16:00.
8. **Ranking:** when slots are scarce, the largest |s| goes first.
9. **Sizing:** `risk_pct=1.5`, `max_positions=5`, `daily_stop_pct=3.0`. The strategy trades all 12 pairs.

**Why this sizing.**
- **Daily stop:** the 3.0% daily stop equals two full-stop losers. It halts the day with 2 percentage points of headroom to FTMO's 5%.
- **Positions:** with 5 slots, the worst case (all five stopped in the same hour) is 7.5%. That can breach the 5% daily limit, and it happened in 2 of 107 weeks (see §7).
- **Risk per trade:** 1.5% was chosen because the strategy's weekly drift (~0.5%/week) at 1.25% risk reaches +10% too slowly for the 12-week cap. In validation, 1.25% gave 6.6% pass_both with 87% timeouts. **Disclosure:** I moved from 1.25% to 1.5% *after* seeing the validation results (§5), so validation is not clean for the risk parameter. The signal parameters were frozen on dev before validation was run.

## 3. Results (final configuration, default costs; `--spread-mult 2` in brackets)

Dev runs 2024-01-05 → 2025-06-30. Validation runs 2025-07-01 → 2026-03-31, with earlier bars as warm-up via `--trade-from`. Full covers the whole range. All bootstraps use 2,000 challenges.

| | Dev | Validation | Full |
|---|---|---|---|
| Net return | +47.4% [+45.8%] | +12.0% [+10.7%] | **+59.4%** [+56.4%] |
| Trades (per week) | 311 (4.0) | 148 (3.8) | 459 (3.9) |
| Profit factor | 1.41 [1.39] | 1.26 [1.23] | **1.37** [1.35] |
| Avg R | +0.102 [+0.099] | +0.054 [+0.048] | **+0.086** [+0.083] |
| Win rate | 48.9% | 54.1% | 50.5% |
| Max DD (equity) | −18.2% | −9.1% | −18.2% |
| Avg week / worst week | +0.60% / −8.25% | +0.30% / −3.75% | +0.50% / −8.25% |
| Weeks breaching 5% daily limit | 2 | 0 | 2 / 107 |
| **Bootstrap pass_both** | 29.9% [29.2%] | 12.7% [10.9%] | **25.1%** [24.8%] |
| Bootstrap phase1_fail | 27.6% | 6.8% | 22.8% |
| Historical pass_both | 32.8% (n=67) | 10.3% (n=29) | 29.9% (n=107) |
| Historical phase1_fail | 38.8% | 3.4% | 25.2% |
| Median weeks to pass both (bootstrap) | 11 | 15 | 11 |

Long and short both contribute over the full period: shorts are 217 trades at +0.10 R and longs are 242 trades at +0.07 R. Ten of 12 pairs are positive over the full period. USDCHF lost 3.7% and GBPUSD was flat; the best pair was AUDUSD at +10.1%. The 2× spread stress test costs about 0.003–0.006 R per trade, because the stops are wide (about 1.25 daily ATR ≈ 80–130 pips on majors), which keeps the strategy cost-robust.

Edge by quarter (avg R per trade):

| 24Q1 | 24Q2 | 24Q3 | 24Q4 | 25Q1 | 25Q2 | 25Q3 | 25Q4 | 26Q1 |
|---|---|---|---|---|---|---|---|---|
| +0.12 | +0.07 | **−0.15** | +0.20 | +0.25 | +0.17 | +0.11 | +0.02 | +0.04 |

## 4. Comparison with random_entry

| | random_entry (1.0% risk, 3 pos) | random_entry at **my** sizing (1.5%/5/3.0) | fx_mean_reversion |
|---|---|---|---|
| Full: net / PF / avg R | −53.2% / 0.91 / −0.043 | −35.6% / 0.97 / −0.013 | **+59.4% / 1.37 / +0.086** |
| Full: bootstrap pass_both / p1 fail | 7.8% / 61.9% | 11.4% / 71.9% (seeds 2–4: 1.9%, 11.7%, 12.9%) | **25.1% / 22.8%** |
| Dev: bootstrap pass_both / p1 fail | 5.5% / 56.5% | – | 29.9% / 27.6% |
| Val: bootstrap pass_both / p1 fail | 11.2% / 48.0% | 11.1% / 69.8% | 12.7% / 6.8% |

The edge is visible separately from sizing:
- **Coin flips:** at identical sizing, coin flips pass about 11% and blow up in about 70% of challenges.
- **Inverted signal:** flipping the signal to trend-following with the same stops gives −64.6% net, PF 0.70, and a 2.4% pass rate. The sign of the edge matters.
- **Validation caveat:** in validation the pass-rate advantage over random is small (12.7% vs 11.1–11.2%). The real difference there is the **phase-1 fail rate of 6.8% vs about 70%**. Most of my non-passes in validation are timeouts, because the edge was weaker (+0.054 R), not because the account blew up.

## 5. Variants tried (complete count)

**Exploratory event studies.** These are raw forward returns net of costs, with no engine. Scripts are in the runs folder, and none of these cells were used directly as a parameter choice.

| Study | Cells | Result |
|---|---|---|
| Hourly z-score of the 24h/48h SMA, fade, hold 6/12/24h (`explore.py`) | 12 configs × 12 pairs | ≈ 0 net. **Rejected.** |
| Daily signals on Yahoo daily 2004–2015 and 2016–2023 (`daily_explore.py`) | 7 signals × 3 horizons × 2 eras | IBS result was a data artifact. z5 and fading a big 1-day move were weakly positive. |
| The same daily signals built from hourly bars (`h_daily.py`) | 4 × 3 | z5 slightly positive, RSI(2) negative. |
| Hour-of-day × lookback × threshold × hold fade (`intraday.py`) | 216 | Dev/val correlation −0.05, so it is noise. **Rejected.** |
| Families (`families.py`): turtle soup, Asian-range fade, hourly RSI(2), RSI(2) + low-ER, pivot stretch, big-bar fade, prior-close stretch | 7 × 3 holds | Only the **pivot stretch** was positive in both dev and val. |
| Pivot / SMA5 stretch scan (`pivot_scan.py`) | 96 | Pivot ≥1.25 ATR with no ER filter was positive in dev and val. The ER filter and the SMA5 reference hurt. |

**Engine variants** (logged in `variants.csv`): **35 signal variants + 47 sizing variants = 82 runs**, 78 unique parameter sets after removing exact duplicates.

Signal variants:
- **v1–v6:** 5-day-SMA z-fade at 07:00 entry with an ER filter. Variations were entry hour, no filter, stop/target and z 1.5. All were negative except z 1.5, which had 74 trades. That family was abandoned.
- **Time-exit bug:** v1–v6, v7 and v11 ran with a bug where the time exit never fired, because pandas 3 microsecond `asi8` was used. They effectively held until Friday. The bug was fixed at v12.
- **v7–v14:** pivot stretch, testing z 1.25/1.5, target at the pivot, stop 1.0/1.5, and hold 12/24/48/Friday.
- **grid1 (16 runs):** z {1.25, 1.5} × hold {24, 48} × stop {1.0, 1.5} × target {none, pivot}. **All 16 were positive in dev, with PF 1.03–1.29.** The pivot target beat no target in 8 of 8 pairings.
- **v31–v35:** stop 1.25, hold 72, ER < 0.3 filter (PF 1.01, rejected), London+NY hours 07–16 (adopted), and SMA5 reference (PF 0.90, rejected).

Sizing variants:
- **grid_risk (30):** risk {0.75, 1, 1.25, 1.5, 2} × max_pos {2, 3, 4} × daily stop {2.5, 4}.
- **grid_risk2/3 (10):** more slots and other daily stops.
- **grid_risk4 (7):** risk scan on dev, val and full. **This is the step where validation was peeked at for sizing.**

Selection: the signal was picked from a plateau, not a peak. z 1.25, hold 48 and the pivot target were the consistent winners; stop 1.25 was taken as the middle of 1.0–1.5. The sizing went 1.25/5/2.5 on dev, then 1.5/5/3.0 after the validation scan.

## 6. Why the edge should persist

1. **Mechanism, not a pattern hunt.** A move of more than 1.25 daily ATRs away from yesterday's typical price within a session is usually a liquidity event: a fix-related flow, a stop cascade, or a data surprise. Dealers who absorbed the flow lay it off later (Krohn et al.), and take-profit orders resting at levels slow and reverse the move (Osler). Neither is arbitraged away by retail, because the trade requires holding against momentum for 1–2 days, which most short-term traders won't do.
2. **Plateau robustness.** All 16 cells of the dev signal grid were positive. Neighbouring stops and holds give similar PF.
3. **Breadth.** The edge shows up in both directions and in 10 of 12 pairs. It is not one pair's trend.
4. **Cost robustness.** The trade has a wide stop and a wide target, so costs are about 1–2% of the stop distance and 2× spread barely moves the result. It does not depend on optimistic fills.
5. **Inversion test.** Trading the same signal in the opposite direction loses heavily (PF 0.70), so the result is not a stops-and-sizing artifact.

## 7. Known weaknesses (please attack these, and here is what I already know)

1. **The edge is thin and decaying in-sample.**
   - Average R was +0.10 in dev and only +0.054 in validation, and 25Q4–26Q1 were barely positive (+0.02/+0.04 R).
   - With about 460 trades, the standard error of mean R is roughly 0.05 R, so the full-period edge is only about 1.7 standard errors from zero.
   - The validation pass rate (12.7%) only just beats random_entry (11.2%).
2. **Validation was used to choose risk.** The signal was frozen on dev, but the risk bump from 1.25% to 1.5% and the daily stop from 2.5% to 3.0% were chosen after seeing validation. With dev-only sizing (1.25/5/2.5), the results were:
   - full: 20.6% pass_both, 9.1% phase-1 fail;
   - val: 6.6% pass_both, 3.0% phase-1 fail. That validation figure is **below** random_entry's 11.2%.
3. **Correlated positions in shock days.**
   - Fading a broad USD move means up to 5 near-identical USD bets. The engine has no currency-exposure cap, and `prepare()` sees one pair at a time.
   - This breached the 5% daily limit twice: on 2024-06-04, and on 2025-04-03 after the tariff announcement. The 3% daily stop is checked at bar closes, so a single hour can blow through it.
   - 2024Q3, which included the August yen-carry unwind, was the worst quarter at −0.15 R and −12.9%.
   - **Mean reversion's classic failure is a persistent, news-driven trend, and the hidden Apr–Oct 2026 window may contain one.**
4. **Slow.** Median time to pass both phases is 11 weeks in-sample and 15 in validation. Many non-passes are 12-week timeouts, and a weaker hold-out period turns into timeouts.
5. **Costs not modelled.**
   - The trades hold overnight for a median of 27 h (about one night). **Swap is not modelled**, and it is roughly symmetric across longs and shorts here.
   - Entries are restricted to 07–16 UTC partly to avoid rollover-hour spread widening, which the engine also does not model.
   - News-time slippage on stops is not modelled either.
6. **The research supports the mechanism, not this rule.** No source tests "fade 1.25 ATR from yesterday's pivot." The academic reversal effects are measured in basis points, and the rule depends on the larger, rarer stretches behaving the same way.
7. **Phase-1 fail rate is not small.** It was 22.8% bootstrap over the full period and 27.6% in dev. The 1.5% risk is a deliberate trade of blow-up risk for speed. At 1.25% the fail rate halves, but the pass rate drops by about 4–5 points.
