# Bot 3 — Intraday Momentum ("stocks in play" first-hour breakout)

**Strategy file:** `t212_agent/strategies/momentum.py` (`name="momentum"`, `interval="1h"`)
**Headline (in-sample full period, 2023-11-24 → 2026-09-23, 100 stocks, default GBP costs):
£1,000 → £896.52 (−10.35%), 390 trades, PF 0.73.** With `--fx-fee-pct 0` it is +4.12% (PF 1.12).
That is better than the `ema_vwap` baseline (−21.4%), but it still loses money at the cost the judge
uses. I report it as it is and don't dress it up.

---

## 1. Research

| Source | What it found | Caveat for us |
|---|---|---|
| Gao, Han, Li & Zhou (2018), *Market Intraday Momentum*, JFE. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351), [working paper](https://assets.super.so/e46b77e7-ee08-445e-b43f-4ffd88ae0a0e/files/ee7dac49-530b-4950-b5d0-e0b5eee08f2e.pdf), [SSRN 2440866 mirror](https://www.smallake.kr/wp-content/uploads/2015/01/SSRN-id2440866.pdf) | On SPY (1993–2013), the return from the previous close to 10:00 predicts the last half hour's return. R² is about 1.6%, and about 6.7% a year from timing the last 30 minutes. The effect is stronger on volatile, high-volume and recession days. | It is a market (ETF) effect. The edge per trade is a few bps, far below our 34 bp round trip. **I tested it on single Nasdaq-100 stocks (hourly): prev-close→first-hour quintiles do not predict the last bar (spread under ±2 bps, not monotonic).** |
| Baltussen, Da, Lammers & Martens (2021), *Hedging Demand and Market Intraday Momentum*, JFE. [EUR repository](https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/), [PDF](https://www3.nd.edu/~zda/intramom.pdf) | Across 60+ futures (1974–2020), the rest-of-day return predicts the last 30 minutes. The authors attribute this to gamma hedging by option and leveraged-ETF dealers, and it reverts over the next days. | Index level again. A single-stock analogue, Beckmeyer & Moerke ([EFMA 2021 WP](https://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2021-Leeds/papers/EFMA%202021_stage-2049_question-Full%20Paper_id-237.pdf)), finds about 18 bp per 1% move, but its sign depends on dealer gamma, which we cannot observe. |
| Zarattini, Aziz & Barbon (2024), *Beat the Market: An Effective Intraday Momentum Strategy for SPY*. [SFI WP 24-97](https://www.sfi.ch/de/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy) | "Noise area" = the average absolute move from the open at each time of day over the prior 14 days. A break outside it signals an imbalance that persists. The authors report 19.6% a year net with Sharpe 1.33 (2007–2024), using VWAP and band trailing stops. | SPY only. A [community port](https://ar.tradingview.com/script/CUpWCZhe-Concretum-Bands) warns that it is not evidence for other tickers. **My faithful single-stock port (v1) lost 85% net and 29% at zero FX. The VWAP trailing exit whipsaws, and the forward return after a breakout is about 1–3 bps.** |
| Zarattini, Barbon & Aziz (2024), *A Profitable Day Trading Strategy for the U.S. Equity Market* (ORB on "stocks in play"). [QuantConnect replication](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/) | Opening-range momentum works on single US stocks **only when they are "in play"** (abnormally high relative volume in the opening bars). The replication reports Sharpe of about 2.4 and beta near 0, and 17 of 25 parameter sets beat the benchmark. | It uses a 5-minute opening range, a tiny stop, and $0.0035/share costs, which are far cheaper than 0.34% per round trip. The ORB lane belongs to another bot, so I used the *first-hour* version on hourly bars. |
| Heston, Korajczyk & Sadka (2010); Lou, Polk & Skouras (2019) (cited via the SSRN mirror above) | Single-stock intraday patterns exist, but cross-sectional momentum profits are mostly earned *overnight*. | Being flat every night throws away most of classic momentum. That is the main structural headwind for this lane. |

(Note: WebFetch could not reach any of the PDFs, because DNS was blocked in this sandbox. The summaries
above come from search-engine abstracts and snippets plus my knowledge of the papers. A critic should
check the numbers against the originals.)

**What my own event study showed (hourly, dev and val):** the only momentum signal that was positive
in *both* halves was **relative volume**. A stock up ≥2σ (its own noise) in the first hour *on
abnormal volume* drifts further into the close. Without the volume condition it does not.

| first-hour condition (z ≥ 2) | dev mean 10:30→close | val mean |
|---|---|---|
| rvol 1.0–1.5 | −5.2 bp (n=827) | −1.4 bp (n=559) |
| rvol 1.5–2 | +7.6 bp | +29.6 bp |
| rvol 2–3 | +22.4 bp | +22.9 bp |
| rvol 3–5 | +33.5 bp | +23.6 bp |
| rvol ≥2, first hour *down* (control) | −13.0 bp | −7.6 bp |

The relationship holds in both halves and is roughly monotonic, which fits the stocks-in-play
literature. **But the edge is about 15–35 bp gross per trade, against a 34 bp round trip.** That gap
is the whole story of this strategy.

## 2. Exact rules

Hourly bars, regular session. Every rolling statistic uses *previous sessions only*
(`.rolling().mean().shift(1)` on a day×slot grid), so there is no look-ahead.

1. `move = close(first hourly bar) / open(day) − 1`
2. `sigma` = mean |move at the same slot| over the previous **14** sessions (the Beat-the-Market noise area)
3. `z = move / sigma`
4. `rvol` = first-hour volume / mean first-hour volume over the previous **20** sessions
5. **Entry:** at the close of the 09:30–10:30 bar, if `rvol ≥ 3` **and** `z ≥ 2`, buy at the 10:30 bar's open.
6. **Exit:** none intraday. Hold to the engine's end-of-day exit (the edge builds into the close).
7. **Stop:** a catastrophic stop 3 × ATR(14, hourly) below the fill. This also sets the size through
   RiskManager (0.5% risk). Only 19 of 390 trades were stopped.
8. **Score:** `z`. When several stocks signal, the engine buys the strongest relative-to-noise move first.
9. **Risk:** engine defaults (3 positions, 20% cap; the average position was about £120, or 12% of equity).
   No overrides.

Five free parameters: 14, 20, rvol 3, z 2, stop 3 ATR. The 14 comes from the paper, 20 is a standard
volume window, and the stop mostly just sizes the trade.

## 3. Results (engine CLI, `--symbols all`, 1h)

Dev = 2023-11-24 → 2025-09-19. Val = 2025-09-22 → 2026-09-23 (data from 2025-07-01 for warm-up, then `--trade-from`).
Full = the whole in-sample period. Raw JSON is in `tournament/runs/momentum/{dev,val,full}_{gbp,usd}.json`.

| Period | Costs | Return | Trades | Win % | PF | Max DD | Sharpe | B&H |
|---|---|---|---|---|---|---|---|---|
| Dev | GBP (0.34% RT) | **−10.58%** | 258 | 42.2 | 0.62 | −10.95% | −2.02 | +63.7% |
| Dev | USD (fx 0) | −0.79% | 258 | 48.1 | 0.97 | −3.45% | −0.13 | +63.9% |
| Val | GBP | **+0.23%** | 132 | 46.2 | 1.02 | −2.71% | 0.11 | +22.4% |
| Val | USD | +4.92% | 132 | 56.1 | 1.48 | −1.24% | 1.88 | +22.6% |
| Full | GBP | **−10.35%** | 390 | 43.6 | 0.73 | −11.12% | −1.36 | +86.4% |
| Full | USD | +4.12% | 390 | 50.8 | 1.12 | −3.45% | 0.51 | +86.7% |

**Gross vs net:** the mean trade is **+0.126%** at fx 0 (net of 2 bp slippage each side, so about +0.17%
before slippage). At GBP costs it is **−0.174%**. The 0.30% FX round trip turns a small positive edge
into a loss. By year (GBP P&L): 2024 −£56 (159 trades), 2025 −£35 (134), 2026 −£12 (97). The loss
shrinks over time; at fx 0 every year is positive (+£8, +£15, +£18).

## 4. Variants tried (full disclosure)

Seven engine variants were tried. All are logged in `tournament/runs/momentum/variants.jsonl`, and each
was run on dev, val and full at both cost settings.

| # | Variant | Full GBP | Full USD |
|---|---|---|---|
| v1 | Faithful noise-area breakout (14d, ×1, gap-adjusted, close>VWAP, trail max(UB,VWAP)), all slots | −85.4% (2,960 trades) | −29.4% |
| v2 | First-hour stocks-in-play, rvol≥2, z≥2, hold to close | −26.2% (743) | −0.5% |
| v3 | v2 with 3×33% sizing | −48.8% | +5.2% |
| **v4** | **v2 with rvol≥3 (final)** | **−10.35% (390)** | **+4.1%** |
| v5 | v2 with z≥1 | −33.0% | +3.8% |
| v6 | v2 with stop 10 ATR (smaller positions through risk sizing) | −8.3% | +0.9% |
| v7 | Same rule on 5m bars (first 5-minute bar, 14d windows, skip_first=0) | −0.8% (22 trades; sample too small) | +0.4% |

I also ran about 90 exploratory event-study slices (forward 10:30→close returns by gap, first-hour
return, rvol, z, close location, trailing intraday and daily momentum, and stops at the first-hour low
or k·ATR). **These looked at both dev and val**, so the validation split is *not* clean for the choice
of the rvol filter. I chose rvol≥3 over 2 because it is better on **dev** (−10.6% vs −21.4%) and
halves turnover, but the critics should know I had seen val by then. Stops at the first-hour low or
1–3 ATR lowered the mean in every slice, and trailing-momentum filters were noise (sign flips between
halves). I rejected both.

## 5. Why the edge should persist

- **Volume is the economic mechanism, not price alone.** A large first-hour move on 3× normal volume
  marks news or institutional demand. Large orders get worked across the day (VWAP/TWAP execution),
  and late-day hedging (Baltussen et al.) pushes in the same direction. Without volume the move is
  noise, and my data shows that (rvol 1–1.5: negative).
- The result matches published single-stock evidence (Zarattini et al., stocks in play). It is
  monotonic in rvol and positive gross in both halves and in all three calendar years at fx 0.
- It makes one decision per stock per day and one round trip per trade, about 0.55 trades a day. That
  is low turnover for an intraday strategy.

## 6. Known weaknesses (please attack these; they are real)

1. **It loses money at the judge's cost (−10.35% full, −10.58% dev).** The gross edge (about 13–17 bp
   per trade) is smaller than the 34 bp GBP round trip. Only validation (+0.23%) is flat or positive.
   Unless the hold-out looks like the last year, the expected hold-out result is a small loss.
2. **The validation split is contaminated.** My event studies looked at val before I picked rvol≥3.
3. **Selection by `z` may be wrong.** The study found that the *top-ranked* candidates on busy days
   did worse in dev than the rest. Market-wide breakout days are the best (the Gao market effect), but
   `prepare()` cannot see breadth. The engine's top-3 cap therefore skews the trades toward
   idiosyncratic news days.
4. **Hourly granularity is generous at the close:** the last hourly bar ends at 16:00, so trades exit
   at the official close rather than 15:50. Entries are at 10:30, so the first hour of the move is
   missed by construction.
5. **It sits well below buy and hold** (+86%) and is in cash about 90% of the time.
   It is a low-exposure overlay, not a standalone return engine.
6. **The noise-area port fails on single stocks.** The published SPY strategy did not transfer (v1: −85%).
   That is evidence against the "Beat the Market" paper being general.
7. Twelve-percent average positions keep the drawdown small (−11%), but raising the size only scales
   the loss (v3).
