# fx_trend: within-week time-series momentum, 3-day breakout entry (FX Bot 1)

**One line:** trade only in the direction of the daily trend (20-day momentum and price vs 50-day SMA must agree). Enter on a 1h close beyond the prior 72h high or low, 07–17 UTC. Stop at 5×ATR(24h), with no target. Exit on a trend flip or the Friday flat. Risk 1% per trade, max 4 positions, 3% daily stop, 10 pairs (no EURGBP or EURCHF).

## 1. Research

### Evidence for the family
- **Time-series momentum (TSMOM).** Moskowitz, Ooi & Pedersen (2012, JFE) find that an instrument's own past 1–12 month return predicts its next-month return, in currency futures and in all 58 instruments they test. The effect partly reverses after a year. https://papers.ssrn.com/abstract=2089463
- **A century of trend.** Hurst, Ooi & Pedersen (2017) find TSMOM profitable on average since 1985 in "nearly all … currency forwards", and positive in every decade since 1880 for the diversified portfolio. https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
- **Technical rules in FX.** Menkhoff & Taylor (2007, JEL) survey FX technical analysis. Profits from MA and channel rules declined after the 1990s (Marsh 2000; LeBaron 2002; Olson 2004). O'Brien et al. report that TSMOM fully accounts for the historical profits of those rules. Zarrabi, Snaith & Coakley (7,650 rules, 1994–2014) find that only a few rules are profitable out of sample. The breakout rule is therefore just a way to time entries into TSMOM, not a separate edge. https://wifo.ac.at/wp-content/uploads/upload-8775/WP_2007_323.pdf , https://ideas.repec.org:443/a/eee/jbfina/v28y2004i1p85-105.html , https://repository.essex.ac.uk/18805/1/1-s2.0-S1057521916301958-main.pdf
- **Momentum in FX is hard to monetise.** Menkhoff, Sarno, Schmeling & Schrimpf (Currency momentum strategies, JFE 2012) find cross-sectional currency momentum stronger than time-series momentum. Returns are concentrated in high-cost, less liquid currencies and swing over time ("limits to arbitrage"). https://cepr.org/voxeu/columns/limits-currency-momentum-trading , https://faculty.washington.edu/ss1110/IF/Sarno%20Currency%20Momentum%20JFE%20%281%29.pdf . The BIS working paper adds that low FX costs make it a demanding test for momentum. https://www.bis.org/publ/work366.pdf
- **Intraday momentum.** Gao, Han, Li & Zhou (first half-hour predicts last half-hour, equities). Baltussen, Da, Lammers & Martens (2021 JFE) report "market intraday momentum" in 60+ futures, including currencies. Elaut, Frömmel & Lampaert (2018, JFM) study intraday momentum in FX. https://www3.nd.edu/~zda/intramom.pdf , https://ideas.repec.org/a/eee/jfinec/v142y2021i1p377-403.html
- **Session/Asian-range breakouts.** I found no rigorous out-of-sample study, only vendor backtests. One 10-year EURUSD test reports a 36% win rate and weak results at a 2:1 target. https://backtrex.com/en/backtests/london-breakout-eur-usd
- **Prop-firm practice** (blogs and vendors, unverified). The usual advice is 0.5–1% risk per trade, a personal daily stop at 2–3%, well inside the 5% limit, trading in the higher-timeframe trend direction, and capping simultaneous trades. https://www.tradezella.com/blog/pass-prop-firm-challenge , https://www.luxalgo.com/blog/ftmo-prop-firm-review-how-to-pass-in-2025/ , https://backtrex.com/en/blog/how-to-pass-ftmo-challenge-guide-2026

### My own pre-test on 23 years of daily closes (`runs/fx_trend/daily_tsmom.py`, `daily_research2.py`)
The FTMO weekend rule caps every hold at under one week. I therefore measured the payoff of the TSMOM sign over the **next week** on the 12 pairs. Units are % of one weekly volatility, gross.

| lookback | 2003–13 | 2014–23 | 2024–26 |
|---|---|---|---|
| 20d | +1.0 | +0.7 | −4.5 |
| 60d | +1.0 | +0.7 | −4.4 |
| 120d | +3.0 | +0.8 | −9.9 |
| 250d | +0.5 | +1.2 | −2.8 |

At a 5-day lookback the payoff is negative (short-term reversal). The 20- and 55-day Donchian "breakout last week" signals were negative in all three eras. **Main caveat:** at a one-week horizon, G10 TSMOM is positive but tiny, roughly 0.05–0.2 annual Sharpe per pair, and it was negative in 2024–26. The documented edge lives at 1–12 month holds, which FTMO Standard does not allow. Note also that Yahoo's daily *open* is unreliable after about 2014 (open ≈ close). I discarded an intraday vol-breakout test built on daily OHLC for that reason.

## 2. Exact rules (`prop_fx/strategies/fx_trend.py`, `STRATEGY`)
1. **Daily trend.** Built from completed UTC daily closes, which are derived from the hourly bars and pass a truncation test with no look-ahead. `trend = +1` when close > close 20 days ago **and** close > SMA50. `trend = −1` when both conditions are reversed. Otherwise `trend = 0`.
2. **Entry** (signal at a 1h close, fill at the next open). Go long when `trend = +1` and close > highest high of the prior 72 hourly bars. Go short when `trend = −1` and close < lowest low of the prior 72 bars. Signals count only on bars opening 07:00–16:00 UTC.
3. **Stop:** 5 × ATR(24 hourly bars), which is about one average daily range. There is **no take-profit**.
4. **Exit:** the daily trend flips or turns neutral (next open). Otherwise the engine flattens everything at Friday 20:00 UTC. The protective stop also applies, and the daily stop flattens and halts trading for the rest of that day.
5. **Ranking:** when signals compete for slots, the larger breakout distance relative to ATR goes first.
6. **Risk:** `risk_pct=1.0`, `max_positions=4`, `daily_stop_pct=3.0`. Pairs: EURUSD GBPUSD USDJPY AUDUSD USDCAD USDCHF NZDUSD EURJPY GBPJPY AUDJPY.

**Why these risk settings**
- **4 positions × 1% risk.** All four stops can be hit on the same day, which loses about 4% plus slippage. That stays under the 5% daily limit with no breach. In the backtest, `daily_limit_breach_weeks = 0` in every split and the worst week was −5.8%.
- **3% daily stop.** It keeps a gap or correlated USD move from turning a bad day into a 5% breach.
- **1% risk.** It roughly doubled the pass rate over 0.5%: with wide stops, 0.5% is too slow to reach +10% in 12 weeks, and most runs time out. Raising risk to 1.5–2% raised Phase 1 failures to 44–64% and pushed full-period PF toward 1.0, because the daily stop interacts with larger sizes (V19, V21). So 1% is the knee of the curve, not the top of a pass-rate scan.
- **No EURGBP or EURCHF.** These are the two lowest-volatility crosses. EURCHF is shaped by SNB policy and both are known for range-bound behaviour. Both lost in dev for V05 (avg R −0.19 and −0.18). This choice was made after val had been viewed, so treat it as partly in-sample.

**Holding period and swap.** Trades are held overnight Monday to Friday, about 1–4 nights. Swap is not modelled. Short JPY-funded longs (e.g. long USDJPY) would *earn* carry, and longs in low-yielders pay it. The net effect at these holds is about ±0.01–0.03R per trade.

## 3. Results (final config; `prop_fx.backtest`, 2,000 bootstrap challenges)

| split | net % | trades | PF | avg R | max DD % | win % | boot pass_both | boot P1 fail | hist pass_both | hist P1 fail |
|---|---|---|---|---|---|---|---|---|---|---|
| dev 2024-01→2025-06 | **+49.5** | 323 | 1.41 | +0.154 | −15.5 | 49.5 | **34.9%** | 18.8% | 45.1% (n=71) | 19.7% |
| validation 2025-07→2026-03 | **−4.1** | 181 | 0.94 | −0.023 | −22.9 | 46.4 | **4.6%** | 25.6% | 0.0% (n=26) | 38.5% |
| full 2024-01→2026-03 | **+47.6** | 498 | 1.26 | +0.096 | −23.2 | 48.4 | **23.6%** | 18.6% | 30.8% (n=104) | 25.0% |
| full, 2× spread | +43.5 | 498 | 1.23 | +0.087 | −24.1 | 47.4 | 22.6% | 19.6% | 29.8% | 25.0% |
| dev, 2× spread | +46.5 | 323 | 1.38 | +0.144 | −16.0 | 48.6 | 33.8% | 19.9% | 43.7% | 19.7% |
| val, 2× spread | −5.2 | 181 | 0.92 | −0.029 | −23.3 | 45.3 | 4.0% | 26.6% | 0.0% | 38.5% |

Validation uses `--trade-from 2025-07-01` so the indicators can warm up. Dev uses `--end 2025-06-30`. Raw JSON is in `tournament_fx/runs/fx_trend/*.json` and trades are in `runs/fx_trend/full/trades.csv`.

**Other full-period stats**
- Sharpe 0.93; 4.3 trades per week.
- By year: 2024 **+60.9%**, 2025 **−18.1%**, 2026 Q1 +4.7%.
- Shorts +0.13R (169 trades), longs +0.08R (329 trades).
- Exits: 313 weekend exits at +0.65R; 140 stops at −1.01R.
- By quarter (avg R): 24Q2 +0.17, 24Q3 +0.44, 24Q4 +0.44, 25Q1 0.00, 25Q2 −0.23, 25Q3 −0.12, 25Q4 +0.04, 26Q1 +0.08.
- Trade-level avg R t-stat 1.94. The bootstrap 95% CI of mean R is [−0.001, +0.196].

### Comparison with random_entry (1% risk, same splits)

| split | random net % | random avg R | random PF | random boot pass_both | random boot P1 fail | fx_trend boot pass_both |
|---|---|---|---|---|---|---|
| dev | −30.4 | −0.037 | 0.92 | 5.5% | 56.5% | **34.9%** |
| validation | −10.0 | −0.025 | 0.95 | **11.2%** | 48.0% | 4.6% |
| full | −53.2 | −0.043 | 0.91 | 7.8% | 61.9% | **23.6%** |

On the full sample, fx_trend triples the luck line and cuts Phase 1 failures from 62% to 19%. On validation alone it **loses to random_entry** on bootstrap pass rate. Its expectancy per trade is similar to random (−0.023R vs −0.025R). Random's higher pass rate there comes from greater variance (2.2× the trades) during a period when coin flips happened to run well. fx_trend still has far fewer Phase 1 failures (26% vs 48%).

## 4. Variants tried: 27 engine backtests, plus about 40 research cells
All 27 engine variants were run on dev, val and full. They are logged in `runs/fx_trend/variants.jsonl` and listed below as net% / avg R / PF / boot pass_both, using 1,000 bootstrap runs, so values differ slightly from the CLI.

Settings for V01–V17 unless stated: 0.5% risk, 4 positions, 3% daily stop, all 12 pairs, 3×ATR stop, 24h breakout, 24h channel exit.

| # | change | dev | val | full |
|---|---|---|---|---|
| V01 | base breakout 24h | +15.6/.055/1.12/13.2 | −16.5/−.094/0.81/2.4 | +0.6/.001/1.00/9.0 |
| V02 | daily entry at 07 UTC in 20d trend (pure TSMOM) | +8.7/.029/1.05/16.6 | −19.4/−.116/0.81/2.5 | −10.7/−.023/0.96/12.0 |
| V03 | same, 60d/100d | −14.6/−.054/0.92/12.5 | −12.2/−.074/0.88/4.5 | −27.4/−.063/0.90/9.8 |
| V04 | V01 + 2R target | +14.5/.043/1.09/12.3 | −9.8/−.048/0.91/2.4 | +5.5/.010/1.02/7.3 |
| V05 | 72h breakout, 48h exit | +17.2/.081/1.15/15.3 | −11.4/−.095/0.82/0.2 | +7.5/.023/1.04/9.9 |
| V06 | intraday momentum: move 00→08 > 0.5 dvol, hold to 20 UTC | −6.2/−.013/0.97/6.1 | −3.0/−.011/0.97/4.3 | −9.2/−.012/0.97/6.2 |
| V07 | V06 + must agree with daily trend | −2.3/−.010/0.98/1.5 | +0.5/.003/1.01/0.9 | −1.8/−.005/0.99/1.7 |
| V08 | V06, threshold 0.25 | −7.4/−.011/0.97/8.5 | −3.7/−.010/0.97/8.2 | −11.1/−.010/0.97/9.7 |
| V09 | V06, decide at 12 UTC | −0.5/−.001/1.00/5.7 | −3.1/−.009/0.97/9.8 | −3.6/−.004/0.99/7.4 |
| V10 | pullback: buy 24h low in uptrend | −7.3/−.019/0.96/1.5 | −20.3/−.086/0.80/0.2 | −27.5/−.044/0.90/1.3 |
| V11 | pullback 48h | +1.2/.004/1.01/2.3 | −10.1/−.060/0.86/0.1 | −8.6/−.020/0.96/1.4 |
| V12 | V05 with 60d/100d trend | +13.4/.074/1.13/11.3 | −5.2/−.045/0.91/1.6 | +8.0/.027/1.05/8.3 |
| V13 | 120h breakout | −0.6/−.003/1.00/6.9 | −17.7/−.164/0.70/0.1 | −16.5/−.055/0.90/3.9 |
| V14 | V05, 5×ATR stop | +10.6/.058/1.15/4.2 | −3.5/−.032/0.91/0.0 | +8.9/.031/1.09/2.1 |
| V15 | V05, 8×ATR stop | +1.8/.010/1.04/0.2 | −2.5/−.024/0.89/0.0 | +0.8/.003/1.01/0.0 |
| V16 | V14, no channel exit | +15.6/.089/1.22/5.8 | −3.3/−.033/0.91/0.0 | +14.5/.054/1.14/2.9 |
| V17 | 24h breakout, 5×ATR stop | +3.9/.015/1.05/2.2 | −5.8/−.037/0.89/0.3 | +0.1/.000/1.00/1.1 |
| V18 | V16 at 1.0% risk | +28.0/.079/1.20/22.5 | −7.8/−.040/0.89/1.8 | +24.6/.045/1.12/16.8 |
| V19 | V16 at 1.5% | +48.5/.089/1.24/25.5 | −18.6/−.061/0.83/5.7 | +35.0/.042/1.11/20.0 |
| V20 | V18, 6 positions | +33.3/.072/1.19/26.1 | −18.4/−.071/0.80/2.1 | +17.0/.024/1.06/17.7 |
| V21 | V16 at 2.0% | +32.3/.042/1.12/13.9 | −40.3/−.096/0.74/4.4 | −1.1/−.001/1.00/13.6 |
| **V22** | **V18 without EURGBP and EURCHF (FINAL)** | **+49.5/.154/1.41/34.2** | **−4.1/−.023/0.94/4.7** | **+47.6/.096/1.26/25.2** |
| V23 | V18 with 60d/100d trend | +27.7/.094/1.24/22.1 | −5.0/−.026/0.93/4.8 | +24.9/.051/1.13/18.7 |
| V24 | final, 48h breakout | +44.5/.129/1.33/31.2 | −3.1/−.016/0.96/8.3 | +43.4/.081/1.21/25.7 |
| V25 | final, 96h breakout | +38.7/.125/1.33/29.0 | −6.1/−.037/0.90/2.0 | +34.8/.074/1.20/20.5 |
| V26 | final, 4×ATR stop | +49.0/.140/1.31/32.2 | −7.0/−.038/0.92/7.5 | +44.2/.083/1.18/25.7 |
| V27 | final, 6×ATR stop | +38.2/.122/1.37/28.0 | −1.5/−.009/0.97/2.8 | +39.7/.083/1.25/20.6 |

V24–V27 are neighbourhood checks run *after* choosing V22. In every neighbour, full-period avg R is +0.07 to +0.10 and validation is between −0.04 and −0.01. The result is a plateau, not a spike.

The research scans were not engine backtests. They cover:
- 6 weekly-TSMOM lookbacks × 3 eras;
- 2 Donchian states, 6 TSMOM × efficiency-ratio filters, and 3 cross-sectional momentum lookbacks;
- 8 vol-breakout cells, discarded because of the bad daily open data;
- 20 intraday-momentum cells (`hourly_research.py`).

**Disclosure:** I looked at validation for every variant. Validation is therefore not a clean hold-out for the choices of V16 (wider stop, no channel exit), V18 (1% risk) and V22 (pair drop). Each of those choices was also the best or near-best on dev.

## 5. Why the edge should persist (the argument for)
- TSMOM is one of the most replicated return anomalies: more than 100 years, many asset classes, and currency forwards in particular. The usual explanations are behavioural (under-reaction, then herding) and structural (central-bank smoothing, hedging flows, risk-premium trends). None of these is arbitraged away by retail prop traders.
- The strategy trades **only in the direction of the multi-week trend**, and the breakout timing makes it skip trend months that have stalled. All of its expectancy comes from the right tail: weekend exits average +0.65R and stops are capped at −1R. That is the classic trend-following payoff shape.
- The edge is **cost-robust**. A 5×ATR stop is about one daily range, so a round trip costs about 0.01R. Doubling spreads moves avg R only from 0.096 to 0.087 and bootstrap pass rate only from 23.6% to 22.6%.
- Prop fit: Phase 1 failure is 18.6% on the full sample vs random's 62%, there are 0 daily-limit breach weeks, and the worst week was −5.8%.
- **When it should work out of sample:** periods with a persistent macro driver, such as rate divergence, a USD trend or a JPY intervention cycle. 2024 had those (USDJPY to 160 and back, the Q4 USD rally).

## 6. Known weaknesses (please attack these; I've already found them)
1. **Validation is negative.** Jul-2025 → Mar-2026: −4.1%, PF 0.94, avg R −0.023, bootstrap pass_both 4.6%, *below* random_entry's 11.2% on the same window. Every one of the 27 variants lost money in validation except V07 (+0.5%, which is essentially zero).
2. **Profits are concentrated in time.** 2024 Q2–Q4 produced about +64% while 2025 lost 18%. Trade-level significance is marginal (t ≈ 1.9, CI touches 0), and after 27 variants the multiple-testing-adjusted p-value is not significant. The 34.9% dev pass rate is very likely optimistic.
3. **The within-week horizon is wrong for TSMOM.** The academic edge is at 1–12 month holds. My 23-year daily check shows the one-week payoff is tiny (about 1% of weekly vol) and was negative in 2024–26. The weekend rule cuts off the fat right tail that trend following lives on.
4. **Correlated bets.** Six of the ten pairs are USD pairs and three are JPY crosses, so four open positions are often one USD or JPY bet. With max_positions=4 at 1%, a single USD shock can hit all four stops (−4%). The 3% daily stop limits but does not prevent this.
5. **Selection with val visible.** The pair exclusion, the 1% risk choice and the no-channel-exit choice were all made with validation results in view.
6. **Warm-up.** The strategy needs about 50 daily bars of hourly history. If the hidden-data run starts cold in April 2026, it cannot trade until about mid-June.
7. **Regime dependence.** A choppy, range-bound hold-out (Apr–Oct 2026) would look like validation: slow bleed, timeouts, and a pass rate around or below the luck line. The approach is *not* robust to that regime, and I cannot claim it is.
8. **Not modelled:** swap; slippage beyond 0.1 pip on stops (stops are market orders in fast markets); news gaps outside the Friday flat.
