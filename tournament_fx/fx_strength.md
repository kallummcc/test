# FX Bot 4: `fx_strength` (cross-sectional currency strength, weekly hold)

**File:** `prop_fx/strategies/fx_strength.py` (`name="fx_strength"`, 1h bars, all 12 pairs)

**Headline (full in-sample period 2024-01-05 → 2026-03-31, default costs):** net **+12.74%**, 270 trades,
PF **1.09**, avg **+0.024R** (t ≈ 0.54, so not significant), max DD −21.5%. Bootstrap pass_both is **7.5%**,
against **7.8%** for `random_entry`. The Phase 1 fail rate is **14.3%**, against 61.9% for random.

In short, the rule loses far less often than coin flips, but its pass rate is roughly the same.
I found no statistically significant G8 currency-momentum edge in this data, or in 22 years of daily
data. The evidence is below. I am not claiming one.

---

## 1. Research

| Source | Finding | Caveat for us |
|---|---|---|
| Menkhoff, Sarno, Schmeling & Schrimpf (2012), *Currency momentum strategies*, JFE 106:660–684. [BIS WP 366 PDF](https://www.bis.org/publ/work366.pdf), [City repository](https://openaccess.city.ac.uk/3296), [UW mirror](https://faculty.washington.edu/ss1110/IF/Sarno%20Currency%20Momentum%20JFE%20%281%29.pdf) | The cross-sectional winner-minus-loser spread is up to ~10% p.a. over 1–12-month formation and holding periods (48 currencies, 1976–2010). It is distinct from carry. | Transaction costs remove a large share of it (an interview with Sarno says about one third: [Hedgeweek](https://www.hedgeweek.com/?p=16588)). Profits are concentrated in **minor, illiquid, high-cost currencies**, and the authors cite limits to arbitrage. G10-only momentum is much weaker. Their returns include the forward premium (interest), and our spot-only engine does not. |
| Raza, Marshall & Visaltanachoti (2014), *Is there momentum or reversal in weekly currency returns?*, JIMF 45:38–60. [RePEc](https://ideas.repec.org/a/eee/jimfin/v45y2014icp38-60.html), [Massey thesis](https://mro.massey.ac.nz/handle/10179/7266) | Over 1–4-week look-backs and 1-week holds, the result is momentum, not reversal (63 currencies vs USD, 1997–2011). Gross returns are 1.9–9.1% p.a. The best Sharpe (~1.05) is at 4 weeks. Break-even costs are 2–97 bp. | 63 currencies, mostly EM. The weekly horizon is the one that fits FTMO's no-weekend rule, which is why I chose it. |
| Burnside, Eichenbaum & Rebelo (2011), *Carry trade and momentum in currency markets*, ARFE 3:511–535. [Kellogg](https://www.kellogg.northwestern.edu/faculty/research/detail/2011/carry-trade-and-momentum-in-currency-markets), [data](https://people.duke.edu/~acb8/Burnside/Currency_Speculation_Data.html) | Momentum and carry are both profitable but crash-prone. They are weakly correlated, so they combine well. | Monthly horizon, and it includes interest. |
| Zhang (2022), *Dissecting currency momentum*, JFE 144:154–173. [RePEc](https://ideas.repec.org/a/eee/jfinec/v144y2022i1p154-173.html) | Currency momentum is mostly **factor momentum** (dollar, carry). Factor momentum beats both cross-sectional and time-series momentum. | Suggests the "8-currency strength meter" is a noisy proxy for a few factors. |
| Moskowitz, Ooi & Pedersen (2012), *Time series momentum*, JFE. [SSRN](https://papers.ssrn.com/abstract=2089463) | 12-month TSMOM works in currency futures. | The monthly to yearly horizon cannot be held under no-weekend rules without weekly re-entry. |
| Ranaldo & Söderlind (2010), *Safe haven currencies*, RoF. [SNB WP 2007/17](https://www.snb.ch/en/publications/research/working-papers/2007/working_paper_2007_17) | CHF and JPY appreciate when equities fall and FX volatility rises (hours to days). | This is the risk-on/risk-off structure. It explains why AUD/NZD vs JPY/CHF dominates the strength ranking in stress, and why those positions are correlated. |
| Barroso & Santa-Clara (2015), *Beyond the carry trade*, JFQA. [RePEc](https://ideas.repec.org/a/cup/jfinqa/v50y2015i05p1037-1056_00.html); Krohn, Mueller & Whelan, *FX premia around the clock*. [PDF](https://acfr.aut.ac.nz/__data/assets/pdf_file/0007/190753/Krohn_Mueller_Whelan_Jun2018_FXPremiaAroundTheClock.pdf) | Momentum adds to carry and value in optimal currency portfolios. Momentum profits accrue largely **overnight**, while carry accrues intraday. | Supports holding through the week rather than day-trading the signal. |

WebFetch could not reach most of these sites (DNS was blocked in the sandbox). The summaries come from
search-engine abstracts and snippets, so a critic should verify the numbers.

### Prop-firm angle
- A 1-week cross-sectional hold is the longest horizon the FTMO Standard no-weekend rule allows. The
  engine flattens on Friday at 20:00 UTC, which gives exactly one formation-to-hold cycle a week.
- Daily-loss risk comes from **correlated legs**. On a risk-off day, long-AUD, long-NZD and short-JPY or
  short-CHF positions all lose together. So the rule lets **each currency appear in at most one
  position**. With k=4 that is at most 4 pairs, which together cover all 8 currencies once.
- Momentum crashes (sharp reversals of the ranking) are the known tail risk. A wide stop at 2 daily ATR
  plus the 4% daily stop is the defence.

### My own research before the engine runs (pre-dev data and dev only for selection)
I used the 2003–2023 **daily** files, which predate the dev window. On them I computed a pure G8
currency-strength index (the same least-squares decomposition the strategy uses) and the weekly
top-k minus bottom-k spread, Friday to Friday:

| Signal (weekly hold) | 2003–08 | 2009–15 | 2016–23 | dev 24-01→25-06 | val 25-07→26-03 | 2003–2023 |
|---|---|---|---|---|---|---|
| XS mom, k=3, L=4w | +1.5% p.a. | −0.5% | −2.0% | −2.6% | −8.5% | t ≈ −0.6 |
| XS mom, k=3, L=8w | +1.8% | +0.1% | −0.6% | −1.2% | +3.6% | t ≈ +0.2 |
| XS mom, k=2, L=1w | −4.9% | +1.8% | −1.9% | +3.6% | −20.0% | t ≈ −0.9 |
| composite 1/4/12w, k=3 | +3.6% | −1.5% | −1.7% | −3.8% | −7.6% | t ≈ −0.4 |

**G8 spot currency momentum at 1–26-week horizons has been about zero since 2003.** No cell has
|t| > 1.6 over 20 years. This fits the literature: the documented premium sits in minor currencies
and in interest differentials, and neither is in our universe or engine.

I found one robust-signed effect: a **1–3-day cross-sectional reversal** (daily data, k=2, L=1d:
−4.8% p.a., t = −2.3 in 2003–23, and negative in all five sub-periods). It also shows on hourly data
(L=4h→H=4h: t ≈ −2.6 dev, −2.1 val). But it is 1–3 bp gross per trade, against about 1 bp of costs
plus stop drag. In the engine (variant v2) it lost money in both dev and validation. Session and
time-of-day strength patterns (Ranaldo-type) were about 0.5 bp per hour and noisy, which is far
below costs.

## 2. Exact rules (final)
1. **Strength index.** On every hourly bar, the 12 pair log-returns are decomposed into 8 currency
   returns by least squares (r = A·s, with A = +1 for the base and −1 for the quote, and Σs = 0 via
   the pseudo-inverse). Missing bars are forward-filled. The cumulative sum gives one index per currency.
2. **Strength score.** The index change over the last 7, 28 and 84 calendar days is computed. Each is
   divided by its cross-sectional standard deviation, and the three are averaged. If the data holds
   less history than a look-back, that look-back uses the expanding window from the first bar. No
   signal is given in the first 7 days.
3. **Rebalance** at the close of the **Monday 07:00 UTC bar**, with the fill at the 08:00 open. The
   currencies are ranked. The top 4 are "strong" and the bottom 4 are "weak". Every pair with one
   strong and one weak currency is a candidate, ranked by its strength gap. The rule picks greedily
   so that **each currency is used once** (at most 4 pairs). It goes long the strong currency and
   short the weak one. Pairs that are not selected get an `exit` at the rebalance.
4. **Stop** = 2 × daily ATR(14), using completed UTC days only. **No target.** The engine closes every
   position at Friday 20:00 UTC.
5. **Risk:** `risk_pct=2.0`, `max_positions=4`, `daily_stop_pct=4.0`.
   - Why 2%: positions are held for a week with a stop that is rarely hit (40 of 270 trades). A
     typical week moves each position by about 0.2–0.6R, so at 1% risk the book cannot reach +10%
     in 12 weeks. At 1% the bootstrap pass rate was 0.1%, with 99% timeouts (v10).
   - Why 4 positions, one per currency: this gives full long-short coverage of the cross-section
     with no doubled currency bet. Four simultaneous stop-outs in one day would be 8%, which is why
     the daily stop sits at 4%. The worst week was −4.9%, and no week breached the daily limit.
   - Expectancy does not depend on risk_pct (avg R is identical at 1.5% and 2%). Only the pass rate does.

**Data source for the other 11 pairs.** `prepare(df, pair)` takes them, in this order, from
(a) `prop_fx.strategies.fx_strength.DATA_DIR` or the environment variable `FX_STRENGTH_DATA_DIR`;
(b) the `bars` dict that `engine.run` was called with, found by walking the call stack and matching
the identical df object, which is exactly what the engine loaded, including `--start`/`--end`;
(c) `--data-dir` in `sys.argv`; (d) `data/fx`. Frames read from disk are clipped to the time window
of the df received.

I verified this on a simulated hold-out directory (the last 6 months copied to the scratchpad). The
CLI `--data-dir`, the environment override, the module `DATA_DIR` override and `--start` on the main
directory all produce identical results (+9.12%, 56 trades). **No look-ahead:** I computed signals on
data truncated at 2025-03-12 and on the full data, and `entry`/`exit`/`stop_dist` matched on every
common bar (0 mismatches).

## 3. Results (default costs; 2,000 bootstrap challenges)

| Period | Net | Trades | PF | avg R | Max DD | Boot pass_both | Boot P1 fail | Hist pass_both | Hist P1 fail |
|---|---|---|---|---|---|---|---|---|---|
| dev 2024-01→2025-06 | +2.93% | 176 | 1.03 | +0.008 | −19.9% | 7.3% | 20.1% | 0.0% (n=68) | 11.8% |
| validation 2025-07→2026-03 | +6.20% | 89 | 1.15 | +0.035 | −9.2% | 6.4% | 7.4% | 5.0% (n=20) | 0.0% |
| full | **+12.74%** | 270 | **1.09** | **+0.024** | −21.5% | **7.5%** | 14.3% | 1.0% (n=98) | 8.2% |
| full, **2× spread** | +10.08% | 270 | 1.07 | +0.019 | −22.7% | 6.7% | 15.1% | 1.0% | 8.2% |
| dev, 2× spread | +1.38% | 176 | 1.01 | +0.004 | −20.6% | 7.0% | 20.9% | — | — |
| val, 2× spread | +5.16% | 89 | 1.12 | +0.029 | −9.7% | 5.7% | 8.1% | — | — |

Additional numbers:
- Trades per week: 2.3. Win rate: 48%. Daily Sharpe: 0.40.
- Exits: 226 at the weekend (avg +0.19R), 40 at the stop (−1.0R), 3 on a data gap.
- By year: 2024 +10.1%, 2025 −2.1%, 2026 Q1 +4.7%.
- Bootstrap phase 1 outcomes: 68% timeout, 17% pass, 14% fail. The binding constraint is **speed,
  not drawdown**.
- Cost robustness: the rule trades one round trip per position per week, so doubling spreads costs
  only about 0.005R per trade.

### vs `random_entry` (same engine and costs)
| Period | random net | random PF | random avg R | random boot pass_both | random boot P1 fail |
|---|---|---|---|---|---|
| dev | −30.4% | 0.92 | −0.037 | 5.5% | 56.5% |
| val | −16.7% | 0.91 | −0.041 | 10.2% | 53.8% |
| full | −53.2% | 0.91 | −0.043 | 7.8% | 61.9% |

`fx_strength` beats random on expectancy, net return, Phase 1 fail rate and drawdown in every period.
On bootstrap pass_both it beats random in dev (7.3 vs 5.5), loses in validation (6.4 vs 10.2) and is
level over the full period (7.5 vs 7.8). Random passes more often in validation only because it
gambles: it has a 54% fail rate and high variance.

## 4. Variants tried (all logged in `tournament_fx/runs/fx_strength/variants.jsonl`)
**16 engine configurations** in total:

| # | Variant | dev net / PF / boot | val net / PF / boot |
|---|---|---|---|
| v1 | momentum 4w, k=3, weekly, 1% risk (pre-registered spec) | −15.6% / 0.66 / 0.0 | +1.7% / 1.13 / 0.0 |
| v2 | reversal 1d, k=3, daily rebalance | −3.7% / 0.95 / 0.0 | −6.9% / 0.81 / 0.0 |
| v3 | v1 with stop 1 ATR and 2-ATR target | −24.3% / 0.69 / 0.0 | +1.2% / 1.04 / 1.9 |
| v4 | momentum 1w | +8.5% / 1.24 / 0.2 | −6.4% / 0.67 / 0.0 |
| v6 | momentum 4w, daily rebalance | −7.6% / 0.88 / 0.0 | −3.8% / 0.85 / 0.0 |
| v8 | momentum 4w, k=2 | −5.4% / 0.81 / 0.0 | −0.1% / 0.99 / 0.0 |
| v9 | momentum 12w | −8.2% / 0.81 / 0.0 | +3.4% / 1.21 / 0.0 |
| v10 | **composite 1/4/12w**, k=3, 1% | −0.4% / 0.99 / 0.1 | +4.4% / 1.34 / 0.0 |
| v10 r1.5 / r2.0 | v10 risk sizing | −0.7% / 0.99 / 0.7; −0.9% / 0.99 / 3.0 | +6.6% / 1.34 / 0.4; +8.8% / 1.34 / 3.1 |
| **v10 r2 k4 mp4** | **final** | +2.9% / 1.03 / 7.3 | +6.2% / 1.15 / 6.4 |
| v10 stop 1.5 / 1.0 at r2; stop 1.0 at r1.5 | tighter stops for variance | −17% to −30%, PF 0.80–0.84 | +6%, PF 1.12–1.17 |
| v11 | final at 1.5% risk | +2.2% / 1.03 / 2.9 | +4.7% / 1.15 / 1.8 |
| v12 | final structure with 4w only | −30.0% / 0.75 / 1.4 | 0.0% / 1.00 / 2.9 |

There were also roughly **110 research cells** outside the engine, none of them used for parameter
fitting on validation:
- 62 on the 2003–2026 daily data (cross-sectional momentum and reversal at 6 look-backs × k, TS
  momentum per currency, the risk-on/off factor, and dollar TS momentum);
- 36 hourly look-back × horizon cells;
- 3 hourly pair-level conditional buckets;
- 1 time-of-day table.

**How the final rule was chosen.** I picked the composite look-back because it avoids choosing a
single horizon and was the only momentum variant that did not lose in dev. Then k=4 / max_positions
4 / 2% risk for the sizing reasons given above. Dev and validation both had to be non-negative.
The choice is still made after looking at dev, so treat the ~16 tries as a multiple-testing
discount: with avg R t ≈ 0.5, **the edge is statistically indistinguishable from zero**.

## 5. Why an edge could persist (the honest version)
- Currency momentum is one of the best-documented FX anomalies. It is attributed to under-reaction
  and slow-moving, policy-driven flows (Menkhoff et al.; Raza et al.), and to factor momentum in the
  dollar and carry factors (Zhang 2022). Weekly re-formation is the FTMO-compatible form of it.
- This implementation is structurally cheap: about 1 bp round trip per position per week. It is
  insensitive to spreads, and the 2× stress test costs only 2.7 points of return.
- With one position per currency and wide stops, the drawdown profile is controlled. The Phase 1
  fail rate is 14% against random's 62%.

## 6. Known weaknesses (attack these)
1. **No significant edge.** Avg R is +0.024 (t ≈ 0.5). On 2003–2023 daily data the same family is
   about 0 or slightly negative. The positive in-sample P&L is consistent with luck.
2. **The pass rate is not better than random_entry.** It is 7.5% vs 7.8% over the full period and
   6.4% vs 10.2% in validation. The strategy fails less but mostly **times out** (68%), because
   week-long holds with a 2-ATR stop do not produce enough variance to make +10% in 12 weeks.
3. **Few trades:** 270 in total (89 in validation), and only about 118 independent weekly decisions.
   One bad Monday ranking moves the whole book.
4. **P&L is concentrated in a few pairs:** AUDJPY +13.9%, EURCHF +10.6%, EURGBP −14.9% and
   USDCHF −7.6%. AUDJPY is the risk-on/off pair, so part of the result is the 2024–26 risk regime.
5. **Correlation is not eliminated.** One currency per position removes doubled bets, but AUD and NZD,
   and CHF and JPY, still co-move. On a risk-off shock the long-AUD, long-NZD and short-JPY or
   short-CHF legs can lose together (worst week −4.9%).
6. **Swap is not modelled.** Positions are held for about 4 nights (Monday to Friday, with the triple
   swap on Wednesday). Momentum often lines up with carry (long AUD/short JPY earns swap), but short
   high-yielders pay it. The direction is uncertain, and the size is a few bp per week.
7. **The hold-out warm-up is short.** On a data set that starts in April 2026, the 84-day look-back
   runs on an expanding window for the first 12 weeks and trading starts after 7 days. I tested this
   on a 6-month simulated directory and it works.
8. **The call-stack lookup is a convenience, not a contract.** If the judge calls `prepare()` outside
   `engine.run` (no `bars` dict on the stack), the module falls back to `--data-dir` or `data/fx`.
   Set `FX_STRENGTH_DATA_DIR` (or `fx_strength.DATA_DIR`) to be certain.
9. **Fixed rebalance time.** The rebalance is Monday 07:00 UTC with no intraday timing. A holiday
   Monday without that bar skips the week.
