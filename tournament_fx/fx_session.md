# fx_session: London-morning → New York continuation, with the daily trend (FX Bot 3)

**Bottom line first:** I tested 28 signal variants from the session family. None shows a net-of-cost
edge that I can tell apart from zero. The final rule's gross edge is small and positive in both dev
and validation, at **+0.039R per trade** over the full period. Costs take almost all of it, leaving
**+0.003R net (t ≈ 0.1)**. Its bootstrap pass_both of **13.2%** beats the published random_entry line
(7.8%). But random_entry re-run on the **same 7 pairs with the same risk settings** gives 8–23%
across four seeds, so the pass rate is **inside the luck band**. I am not claiming an edge I
couldn't show.

## 1. Research

| Claim | Source | How I used it |
|---|---|---|
| The USD rises into the Tokyo (00:55 UTC), ECB (14:15 CET) and London WM/R (16:00 London) fixes and falls after them, a "W" shape. Pervasive across G9 currencies, 1999–2019, linked to dealer hedging of USD demand at the fix. | Krohn, Mueller & Whelan, *J. Finance* 2024 — https://onlinelibrary.wiley.com/doi/10.1111/jofi.13306 ; WP: https://www.bankofcanada.ca/wp-content/uploads/2021/10/swp2021-48.pdf | Variant V03 (fade the run-up into the 4pm fix). Hour-of-day check below. |
| Returns from being long foreign currency vs USD come almost entirely during **US trading hours**. | Krohn, Mueller & Whelan, "FX Premia Around the Clock" (2018) — https://acfr.aut.ac.nz/__data/assets/pdf_file/0007/190753/Krohn_Mueller_Whelan_Jun2018_FXPremiaAroundTheClock.pdf | Motivates trading the NY session. |
| Currencies tend to weaken during their own local hours. EURUSD falls in the European morning and rises in US hours. The pattern shows up in order flow, and for EURUSD it gives a "simple, profitable" rule. | Breedon & Ranaldo, SNB WP 2011-04 — https://www.snb.ch/en/publications/research/working-papers/2011/working_paper_2011_04 | Considered. Hourly means here are ~1 bp, below the ~1 pip round-trip cost (see EDA). |
| Price changes before and after the 4pm fix are very volatile and negatively autocorrelated, but small except at month-end. | Evans, "Forex Trading and the WMR Fix", JBF — https://mpra.ub.uni-muenchen.de/81583 ; Norges Bank / Panagiotou — https://www.norges-bank.no/contentassets/619c8b75e1ed4ba691e8ad6a006855e6/39-panagiotou---the-wmr-fix-and-its-impact-on-currency-markets-.pdf | V03. The reversal mostly happens within minutes, which hourly bars can't capture. |
| Month-end equity-hedge rebalancing at the 4pm fix: equity gains over the month predict currency weakness into the fix. | Melvin & Prins, *J. Fin. Markets* 2015 — https://ideas.repec.org/a/eee/finmar/v22y2015icp50-72.html | Not tradeable here: it needs equity data, and there are only ~27 month-ends. |
| FX activity and volatility are U-shaped within each session and peak in the London–NY overlap. | Ito & Hashimoto, NBER w12413 — https://www.nber.org/papers/w12413.pdf | Why entry is at the NY open (13:00 London) and exit is before the late-NY lull. |
| Intraday momentum: the first session's return predicts the last session's return (equities, then FX). | Gao, Han, Li & Zhou, *JFE* 2018 (doi 10.1016/j.jfineco.2018.05.009); Elaut, Frömmel & Lampaert 2018 (FX, RUB/USD), cited via secondary sources | Basis for "London move continues into NY" (mode `nycont`). |
| Time-series momentum in FX futures (12-month lookback, also shorter). | Moskowitz, Ooi & Pedersen, *JFE* 2012 (doi 10.1016/j.jfineco.2011.11.003) | The daily-trend filter. |
| **Practitioner London breakout of the Asian range loses after costs.** GBPUSD 15m (2016–26): PF 0.72, −60%. EURUSD 1h: PF 0.87, −28%. Gross is roughly break-even and commission tips it negative. | Backtrex (vendor) — https://backtrex.com/en/backtests/london-breakout-gbp-usd , https://backtrex.com/en/backtests/london-breakout-eur-usd ; BabyPips thread — https://forums.babypips.com/t/london-breakout-strategy-1h-timeframe-modified/326993 | Matches my V01/V05 (gross ≈ 0, net PF 0.92). |
| Session windows are often wrong because MT5 charts run on broker server time, and spreads widen at rollover and in thin hours. | MQL5 blog — https://www.mql5.com/en/blogs/post/774527 | I use Europe/London clock times, and flatten at 20:00 London, before the rollover. |
| Prop-firm sizing guidance: 1–1.5% per trade, and the 5% daily loss is measured from the day-start balance. | FTMO/OANDA — https://ftmo.oanda.com/?p=2463 ; https://traderssecondbrain.com/guides/how-to-pass-ftmo | Risk choice, section 2. |

**Research caveats.** WebFetch failed with DNS errors on most academic PDFs: the BoC, INSEAD, WU,
AUT and NBER hosts. So the paper summaries above come from search-engine abstracts and snippets,
not from my own reading of the tables. The academic effects are measured with minute data and
interbank costs. The practitioner evidence for London-breakout and liquidity-sweep systems is
anecdotal or comes from vendors, and the best vendor test I found is negative after costs.

**Hour-of-day check (exploratory, 7 USD pairs, USD-strength bps per London hour).** Average hourly
USD returns are about 1 bp. Costs are about 1 pip round trip on EURUSD (0.3 spread + 0.2
slippage + ~0.5 commission) and more elsewhere. The KMW ECB-fix shape is visible in both periods:
USD strong in the 12:00 London hour (+0.54 / +0.33 bp) and weak in the 13:00 hour (−0.82 /
−0.74 bp). The 4pm-fix shape is not stable: the 16:00 hour is +1.04 bp in dev and −0.65 bp in val.
London-morning vs NY-session return correlations are about 0 and change sign between periods. My
conclusion: **plain clock-direction trades cannot pay retail costs on hourly bars.** A session
rule needs a conditional, larger move per trade.

## 2. Exact rules (final, `prop_fx/strategies/fx_session.py`, mode `nycont`)

All clock times are **Europe/London** local time, so UK DST is handled. A bar is labelled by its
open time.

1. **Universe:** EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD (the 7 USD majors).
2. **London-morning move** M = close of the 12:00 bar (the price at 13:00 London ≈ 08:00 New
   York) − open of the 07:00 bar (the London open).
3. **Filter:** |M| ≥ 1.0 × ATR(24) on hourly bars, and sign(M) = sign(last completed UTC daily
   close − SMA20 of daily closes). The daily trend uses only closed days, aligned with merge_asof
   on the bar's close time, so there is no look-ahead.
4. **Entry:** in the direction of M, filled at the 13:00 London open. At most one signal per pair
   per day.
5. **Stop:** 3.0 × ATR(24). **No take-profit.** **Time exit** at the 20:00 London open. The engine's
   Friday 20:00 UTC weekend flatten also applies. **No overnight holds, so no swap.**
6. **Ranking** when more than three pairs signal: |M|/ATR, strongest first.
7. **Risk:** `risk_pct=1.0`, `max_positions=3`, `daily_stop_pct=4.0`.
   * All entries happen in the same hour and close the same day. The worst same-day outcome is
     therefore 3 full stops ≈ 3% plus gap slippage. That is 2% of headroom under FTMO's 5% daily
     limit, and there were **0 daily-limit breach weeks** in every run.
   * The 4.0% daily stop is a guard against gaps through stops. It never binds in normal operation.
   * I didn't choose risk to maximise pass rate. Pass rate rises steadily with risk while the
     phase-1 fail rate rises faster, which is what you'd expect from a near-zero-edge signal.
     * 1.5% × 3: bootstrap pass 20% / 25%, phase-1 fail 47% / 45% (dev / val).
     * 2.0% × 2: bootstrap pass 19% / 27%, phase-1 fail 55% / 44% (dev / val).
   * 1.0% × 3 is the low end of FTMO's own 1–1.5% guidance. It keeps phase-1 fails around 27%,
     against 62% for random_entry.

## 3. Results (default costs, 2,000 bootstrap challenges)

| Period | Net % | Trades | PF | Avg R | Max DD % | Win % | Boot pass_both | Boot P1 fail | Hist pass_both | Hist P1 fail (n) |
|---|---|---|---|---|---|---|---|---|---|---|
| Dev 2024-01→2025-06 | +0.51 | 553 | 1.00 | +0.001 | −28.3 | 48.6 | 12.6% | 28.3% | 14.1% | 39.1% (64) |
| Val 2025-07→2026-03 | +2.30 | 283 | 1.03 | +0.008 | −10.2 | 47.3 | 15.8% | 26.4% | 0.0% | 6.5% (31)* |
| **Full** | **+2.81** | **836** | **1.01** | **+0.003** | −28.3 | 48.2 | **13.2%** | 27.8% | 8.3% | 26.6% (109) |
| Full, gross (zero costs) | +32.8 | 836 | 1.13 | +0.039 | −20.2 | — | 20.6% | 17.6% | 17.3% | 17.3% |
| Dev, 2× spread | −7.29 | 553 | 0.96 | −0.013 | −30.7 | 47.6 | 9.6% | 33.3% | 10.8% | 40.0% |
| Val, 2× spread | −1.21 | 283 | 0.99 | −0.004 | −11.6 | 47.0 | 13.0% | 29.8% | 0.0% | 9.7% |
| Full, 2× spread | −8.50 | 836 | 0.97 | −0.010 | −30.7 | 47.4 | 10.2% | 31.1% | 6.4% | 29.4% |

\*The validation period has only 39 weeks, so the historical windows are few and most end in a
timeout.

* Full-period R statistics: mean +0.0034R, standard deviation 0.80, **t = 0.12**.
* By year: 2024 −1.7%, 2025 −2.7%, 2026 Q1 +7.2%.
* Quarterly average R: −0.22, −0.09, +0.07, +0.11, −0.05, +0.07, +0.04, −0.08, +0.08.
* Exits: 626 time exits, 161 stops, 49 weekend flattens.
* Long trades +0.010R, short trades −0.003R.
* By pair (avg R): USDJPY +0.12, GBPUSD +0.04, USDCHF +0.03, NZDUSD −0.02, EURUSD −0.03, AUDUSD −0.08, USDCAD −0.09.

Run outputs are in `tournament_fx/runs/fx_session/*.json`, with `trades.csv` in each subfolder.

### Comparison with random_entry

| | Net % | PF | Avg R | Boot pass_both | Boot P1 fail | Hist pass_both |
|---|---|---|---|---|---|---|
| random_entry, 12 pairs (benchmark), full | −53.2 | 0.91 | −0.043 | 7.8% | 61.9% | 7.1% |
| random_entry, dev | −30.4 | 0.92 | −0.037 | 5.5% | 56.5% | 0.0% |
| random_entry, **val** | **+23.4** | **1.14** | **+0.059** | **37.0%** | 19.5% | 28.6% |
| random_entry on **my 7 pairs, 1%×3, daily stop 4**, seeds 1–4, full | −35.0 / −4.2 / −7.6 / +29.6 | 0.94–1.06 | −0.031…+0.026 | **8.0 / 16.9 / 18.2 / 22.9%** | 28–52% | 4–26% |
| **fx_session, full** | +2.8 | 1.01 | +0.003 | 13.2% | 27.8% | 8.3% |

**Honest reading.** fx_session beats the published luck line (7.8%) and has a much lower phase-1
fail rate (28% vs 62%). But a fair luck line uses the same universe and the same concurrency, and
on that line random seeds span 8–23%. **random_entry beat fx_session in validation.** The
defensible claims are narrower:

* Gross expectancy was positive in both dev (+0.032R) and validation (+0.042R).
* Drawdowns and fail rates were controlled.
* There were no daily-limit breaches.

## 4. Variants tried (28 signal variants + 7 risk configurations)

There were also two exploratory analyses run on all data: hour-of-day mean returns and
session-to-session correlations. I count these as researcher degrees of freedom. dev/val values
are net avg R at 1% risk × 3 positions unless marked.

| # | Variant | Dev avg R (gross) | Val avg R (gross) | Verdict |
|---|---|---|---|---|
| V01 | London breakout of Asian range (00–07), entry 07–10, stop at mid-range, 1.5R target, exit 16:00 | −0.041 (+0.025) | (−0.032) | gross ≈ 0 |
| V02 | Asian-range liquidity sweep fade, target the opposite side, exit 16:00 | −0.082 (0.000) | (+0.002) | no edge |
| V03 | Fade the 13–16h run-up into the 4pm fix, exit 20:00 | −0.040 (−0.009) | (+0.001) | no edge |
| V04 | NY continuation of the London move, 1R target, exit 17:00 | −0.035 (−0.004) | (+0.072) | unstable |
| V05 | Breakout, stop at the opposite side, no target, exit 20:00 | −0.033 | — | |
| V06 | V05 + 20-day trend | −0.015 (+0.033) | −0.028 (+0.016) | gross > 0 both, net < 0 |
| V07 | V01 + 20-day trend | −0.050 | — | |
| V08 | V02 + 20-day trend | −0.104 | — | worst |
| V09 | V04 no target, exit 20:00, + 20-day trend | −0.010 (+0.022) | −0.005 (+0.027) | gross > 0 both |
| V10 | V06 on the 4 lowest-spread pairs | +0.069 | not run | rejected: pair luck (EURUSD loses) |
| V11 | V06, minimum stop 2 ATR | −0.005 | — | |
| V12 | V09 on the 4 lowest-spread pairs | −0.007 | — | |
| V13 | V06 with 50-day trend | +0.036 | −0.055 (−0.011) | **failed validation** |
| V14 | V13 on USD majors | +0.060 | −0.031 (+0.004) | **failed validation** |
| V15 | V06 + narrow Asian range (≤ 3 ATR) | −0.026 (+0.025) | — | compression filter hurts |
| V16 | V05 + narrow range | −0.035 | — | |
| V17 | V06 + wide range (3–8 ATR) | +0.015 (169 trades) | — | too few trades |
| V18 | **V09 on USD majors** | 0.000 (+0.032) | +0.012 (+0.042) | **selected** |
| V19 | V06 on USD majors | +0.037 (+0.086) | −0.051 (−0.016) | failed validation |
| S1 | V18, threshold 0.5 ATR | −0.001 | −0.001 | sensitivity |
| S2 | V18, threshold 1.5 ATR | +0.006 | −0.013 | |
| S3 | V18, stop 2 ATR | +0.006 | +0.024 | |
| S4 | V18, stop 4 ATR | −0.003 | +0.011 | |
| S5 | V18, exit 17:00 | +0.002 | −0.035 | |
| S6 | V18, 50-day trend | −0.007 | +0.063 | |
| S7 | V18, 10-day trend | −0.006 | +0.019 | |
| S8 | V18 without the trend filter | −0.032 | **+0.067** | the filter helps in dev and hurts in val |
| V20 | V18 with ranking by \|M\|/ATR instead of pair order (**final**) | +0.001 | +0.008 | final |

**Risk grid on V18** (dev / val bootstrap pass_both, P1 fail):

| Config | Pass | P1 fail |
|---|---|---|
| 0.5% × 3 | 0.6 / 1.0 | 1.6 / 1.3 |
| 1.0% × 2 | 7.1 / 8.6 | 23.5 / 14.8 |
| **1.0% × 3 (chosen)** | 11.9 / 16.0 | 27.4 / 23.0 |
| 1.0% × 4 | 12.2 / 18.9 | 34.6 / 35.7 |
| 1.5% × 2 | 16.5 / 21.2 | 42.7 / 32.0 |
| 1.5% × 3 | 20.3 / 25.1 | 47.0 / 44.6 |
| 2.0% × 2 | 19.0 / 27.1 | 55.1 / 43.8 |

All risk configurations used daily stop 4.0.

**Selection bias I introduced:**

* I chose the USD-majors universe after seeing dev per-pair results: crosses were about 0 gross,
  majors positive. The a-priori story is real: the fix and session literature is USD-centric, and
  crosses carry wider spreads. But the choice was informed by the data.
* I saw validation for V06, V09, V13, V14, V18 and V19 before freezing V18. Validation is
  therefore partly used up as a selection set. The hidden Apr–Oct 2026 data is the only clean
  test.

## 5. Why the edge *might* persist (weakly argued)

* **Structural flows at the NY open.** US participants arrive at 13:00 London and execute
  against an already-established London direction. Real-money USD demand is concentrated in US
  hours (KMW 2018, 2024; Breedon & Ranaldo). Intraday momentum, where informed early flow is
  followed by late flow, is documented in equities and in FX (Gao et al. 2018; Elaut et al. 2018).
* **Trend agreement.** Requiring agreement with the daily trend ties the intraday flow to TSMOM,
  the best-documented FX return premium (Moskowitz et al. 2012).
* **Positive gross edge out of sample.** Gross expectancy was positive in dev (+0.032R), was
  *larger* in the unseen-at-design validation (+0.042R), and is +0.039R across 836 trades. The
  neighbourhood (S1–S7) is flat around zero net, not a sharp peak.
* **Mechanically prop-safe.** The strategy is flat every night, so there is no swap, no gap
  risk and no weekend exposure. A worst day is about −3%. It had 0 daily-limit breaches, and the
  phase-1 fail rate is less than half of random_entry's.

## 6. Known weaknesses (attack these; most are already true)

1. **No statistically significant net edge.** t ≈ 0.1 net. The gross t is about 1.4 (0.039 / 0.80 × √836) and misses
   conventional significance. PF 1.01. At 2× spread it is negative in every period (−0.010R
   full).
2. **The pass rate is inside the same-universe random band** (8–23% over four random seeds).
   random_entry beat it in validation (+23% vs +2.3%). Any pass-rate edge over the 7.8% headline
   comes mostly from lower trade count and lower cost drag. Signal is not shown to be the source.
3. **Selection bias.** There were 28 signal variants. The universe was picked after dev per-pair
   results, and validation was looked at for 6 candidates before selection.
4. **The trend filter is unstable.** It helps in dev and hurts in val (S8). The neighbouring trend
   lengths (10, 50) rank differently in dev and val.
5. **Pair concentration.** Results lean on USDJPY (+0.12R) and GBPUSD. AUDUSD and USDCAD lose.
6. **The cost model probably flatters it.** Constant spreads are used, but real spreads at 13:00
   London are tight, and US data at 13:30 London can cause stop slippage. A 3-ATR stop is hit on
   only 19% of trades, so gaps matter less.
7. **DST mismatch weeks.** In the 2–3 weeks each spring and autumn when US and UK DST differ,
   "13:00 London" is 09:00 NY, not 08:00. I didn't model this separately.
8. **Hourly bars miss the precise fix effects.** The KMW and Evans reversals happen within
   minutes of 13:15 and 16:00 London. The cleanest academic effect is therefore untestable here,
   and V03 only approximates it.
9. **Regime dependence.** Quarterly average R ranges from −0.22 (2024 Q1) to +0.11. A choppy
   Apr–Oct 2026 hold-out could easily be negative.
10. **Phase timeouts.** At 1% risk with roughly zero drift, many challenges time out instead of
    passing (historical validation windows: 0% pass, mostly timeouts).
