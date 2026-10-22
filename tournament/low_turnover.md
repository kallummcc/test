# low_turnover: gap-and-hold breakouts, at most one trade a day

**Lane:** the skeptic's strategy, built for the most edge per trade and the least turnover.
**File:** `t212_agent/strategies/low_turnover.py` (`name="low_turnover"`, `interval="1h"`)

**In one line:** buy a stock that has gapped up at least 2% on at least 3x normal opening volume, whose first hour closes green and above its highest high of the last 120 sessions. Take one name a day at the 10:30 open and hold it to the close.

---

## 1. Research: what survives a 0.34% round trip?

The starting point is skeptical. Most retail day traders lose money, and costs explain much of it. In Taiwan, Barber, Lee, Liu and Odean found that most heavy day traders traded profitably before costs and lost after them. Trading costs (commissions plus taxes) were about two thirds of what individual investors lost ([Haas WP](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/Day%20Trading%20Skill%20110523.pdf), [CXO summary](https://www.cxoadvisory.com/individual-investing/do-day-traders-make-money/)). For a long-only, intraday-only account there is a second problem: US stock returns are earned mostly overnight, not intraday. Lou, Polk and Skouras show that momentum profits come almost entirely overnight and partly reverse during the day ([JFE 2019 / LSE](https://personal.lse.ac.uk/polk/research/TugOfWar.pdf)). Bogousslavsky finds that mispricing factors do badly at the end of the day ([JFE 2021](https://ideas.repec.org/a/eee/jfinec/v141y2021i1p172-194.html)). So the average intraday drift we can capture is about zero, and each trade has to overcome 34 bps.

These are the candidate effects I checked, first in the literature and then in the in-sample data (dev period only unless noted):

| Effect | Literature | Our data, dev (gross) | Verdict |
|---|---|---|---|
| Market intraday momentum: the first half hour predicts the last half hour | Gao, Han, Li & Zhou, JFE 2018 ([summary](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/)). Baltussen et al. JFE 2021 attribute it to gamma hedging ([pdf](https://www3.nd.edu/~zda/intramom.pdf)). The independent replication for 2012–14 was weak ([CXO](https://cxoadvisory.com/calendar-effects/first-and-last-half-hours-of-trading-linked)) | corr(first hour, last 30 min) = **−0.04**. The last 30 minutes average about 1 bp | Dead, and it could never pay 34 bps anyway |
| Daily-lag half-hour periodicity | Heston, Korajczyk & Sadka, JF 2010 ([pdf](https://www.bauer.uh.edu/departments/finance/documents/Heston_Korajczyk_Sadka_paper_UH.pdf)) | The effect is a few bps per half hour | Far too small after costs |
| Turn of the month | McConnell & Xu, FAJ 2008 ([abstract](https://rpc.cfainstitute.org/research/financial-analysts-journal/2008/equity-returns-at-the-turn-of-the-month)) | TOM days 4.5 bps vs other days 1.1 bps (10:30 to close) | Real but about 1/10 of the cost |
| Pre-FOMC drift and pre-holiday days | Lucca & Moench 2015. Later work says the drift faded | FOMC days **−30 bps** (dev) and −37 bps (val). Pre-holiday days −8 bps | Dead |
| Buying the strongest few names after the first hour, held to the close | Intraday momentum / ORB folklore | Top 3 by first-hour return: +11 bps | Below cost |
| **"Stocks in play" continuation**: a gap up on abnormal volume with a green first hour | Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy for the U.S. Equity Market" (2024) ([SSRN 4729284 / HSG](https://alexandria.unisg.ch/handle/20.500.14171/122125), [CXO review](https://www.cxoadvisory.com/individual-investing/intraday-trading-of-overactive-stocks-via-opening-range-breakout/)). Their key finding is that ORB only works on stocks with abnormal volume caused by news. An independent ORB replication on indices found gross ≈ paper and net ≈ zero ([mql5](https://www.mql5.com/en/blogs/post/776235)) | +25 bps per day (1 a day). At 4 bps costs it makes money, at 34 bps it loses (variant v1) | The gross edge is real but it does not clear the cost on its own |
| **+ breakout to a multi-month high** | George & Hwang, "The 52-Week High and Momentum Investing", JF 2004 ([summary](https://www.cxoadvisory.com/1284/technical-trading/the-52-week-high-as-a-momentum-indicator-for-individual-stocks/)): investors anchor on the high and underreact to news that pushes price through it. Post-earnings drift is linked to 52-week-high anchoring ([review](https://behaviouralfinance.jasoncollins.blog/lagged-reactions-to-announcements); [Alpha Architect](https://alphaarchitect.com/2014/09/new-facts-for-post-earnings-announcement-drift/)) | The edge rises steadily with lookback: 20 days 25 bps, 60 days 50 bps, **120 days 78 bps** (n=45). Gappers not at a high: −5 bps | **This is the only setup with a gross edge clearly above 34 bps** |

Caveats from the literature:
- Zarattini et al. is co-written by a day-trading educator and uses commission-only costs.
- The Taiwan evidence on post-earnings drift near the 52-week high points the opposite way ([Lin & Wu](https://jem.fcu.edu.tw/assets/jem/past_issues/vol.17_no.1/Abstract/vol.17_no.1_01_Abstract.html)).
- 52-week-high momentum is a *monthly* effect. My use of it as a one-day continuation filter is an extrapolation.

## 2. Exact rules

Bars are 1h, regular session only. Every quantity comes from the 09:30–10:30 bar or from earlier sessions (shifted), so there is no look-ahead.

1. **Gap:** today's open / yesterday's close − 1 > **2%**.
2. **Relative volume:** first-hour volume / mean first-hour volume of the previous 20 sessions > **3**.
3. **First hour green:** the first-hour close is above today's open.
4. **Breakout:** the first-hour close is above the highest high of the previous **120** sessions. With a short history this falls back to whatever exists, with a minimum of 20 sessions.
5. **Entry:** a market buy at the 10:30 bar open. If several names qualify, take only the one whose first hour closed highest in its own range (CLV).
6. **Exit:** hold to the close. The engine flattens at the last bar, so the fill is at the 16:00 close. A protective stop sits at first-hour low − 0.25 × first-hour range, and it was hit on 2 of 94 trades.
7. **Risk overrides:** `max_open_positions=1`, `max_trades_per_day=1`, `risk_per_trade_pct=2.0`, `max_position_pct=50`. The average position was about 41% of equity.

**Turnover:** 94 trades in about 700 sessions, roughly 33 a year. The account is in cash on 87% of days.

Tunable parameters: gap 2%, rvol 3×, rvol window 20, high lookback 120, stop buffer 0.25, plus the sizing settings. The 2% / 3× thresholds were set before testing, as conventional "stock in play" cut-offs, and were never optimised. The 120-day lookback **was** picked on dev from {20, 60, 120} (see variants).

## 3. Results (£1,000 start, all 100 symbols, 1h bars)

Splits:
- **Dev:** 2023-11-24 → 2025-10-10, about 2/3 of the data.
- **Validation:** 2025-10-13 → 2026-09-23. It is run with `--start 2025-03-01 --trade-from 2025-10-13` so the 120-day high is warmed up.
- **Full:** 2023-11-24 → 2026-09-23.

Costs:
- Default: 2 bps slippage + 0.15% FX per side.
- `fx0`: 2 bps slippage only.
- Gross: zero cost.

| Period | Costs | Return | Trades | Win % | PF | Max DD | Sharpe | Buy & hold |
|---|---|---|---|---|---|---|---|---|
| Dev | default (GBP) | **+7.63%** | 65 | 53.8 | 1.43 | −3.78% | 0.78 | +59.4% |
| Dev | fx 0 | +16.24% | 65 | 56.9 | 2.07 | −2.96% | 1.53 | |
| Validation | default (GBP) | **+2.27%** | 29 | 51.7 | 1.32 | −2.09% | 0.62 | +19.3% |
| Validation | fx 0 | +6.04% | 29 | 65.5 | 2.04 | −1.96% | 1.52 | |
| **Full** | **default (GBP)** | **+10.06%** | **94** | 53.2 | **1.39** | **−3.78%** | 0.73 | +86.4% |
| Full | fx 0 | +23.25% | 94 | 59.6 | 2.06 | −2.96% | 1.51 | |
| Full | gross (0 cost) | +25.13% | 94 | 60.6 | 2.16 | −2.91% | 1.61 | |
| Val, no warm-up (`--start 2025-10-13`) | default | +4.32% | 24 | – | 1.88 | −2.10% | 1.24 | |

**Gross vs net:**
- The average trade makes +0.74% gross and +0.40% net. Costs take 46% of the gross edge.
- Of the gross +25%, about 15 points go to the FX fee.
- Without the breakout filter (v1), the same setup makes +0.30% gross and −0.04% net per trade, which is the cost trap in miniature.

By year (default costs): 2024: 42 trades, +£85. 2025: 29 trades, **−£5**. 2026 YTD: 23 trades, +£20.

## 4. Variants tried (being transparent)

**About 55 exploratory cuts** were run on daily summary tables, all on dev except one validation peek at the calendar effects (they failed there too):
- market intraday momentum (3)
- top/bottom-k by first hour (7)
- rvol × gap grids (9 + 10)
- ranking keys (5)
- CLV and market filters (6)
- turn of the month (2)
- FOMC, pre-holiday and weekday (3)
- breakout / SMA / 20-day return filters (10)

**17 engine backtests** (each dev, val and full):

| # | Change from v1 | Full net (default) |
|---|---|---|
| v1 | base: gap>2%, rvol>3, first hour green, no breakout filter | −6.60% (fx0: +8.19%) |
| v2 | stop buffer 3 | −1.96% |
| v3 | gap>3% | −7.90% |
| v4 | gap>4% | −3.07% |
| v5 | rvol>5 | −2.11% |
| v6 | CLV≥0.5 | −4.88% |
| v7 | first hour >1% | −4.59% |
| **v8** | **+ 120-day-high breakout** | **+6.01%** (dev +4.78 / val +1.18) |
| v9 | 60-day high | +1.25% (dev +0.65 / val +0.60) |
| v10 | 90-day high | +5.04% (dev +3.34 / val +1.64) |
| v11 | 150-day high | +4.29% (dev +4.12 / val +0.15) |
| v12 | 252-day high | +4.37% (dev +4.64 / val +0.08) |
| v13 | v8, gap>1.5% | +3.69% (dev +2.02 / val +1.62) |
| v14 | v8, rvol>2.5 | +5.65% (dev +4.26 / val +1.36) |
| v15 | v8, stop buffer 3 (smaller positions) | +2.01% (PF 1.56, DD −0.53%) |
| **v16** | **v8, risk 2% per trade (final)** | **+10.06%** |
| v17 | v16 + stop buffer 3 | +3.73% (PF 1.51, DD −1.08%) |

All 9 breakout variants (v8–v17) are positive in both dev and validation at default costs. The neighbours of the chosen point do not fall off a cliff. Sizing (v16) only scales the result: the PF and Sharpe of v8 and v16 are the same within noise. Scripts are in `tournament/runs/low_turnover/lt_*.py`.

**Look-ahead check:** on 40 symbols, I recomputed `prepare()` on data truncated at each of 50 signal bars. 0 mismatches.

## 5. Why this edge should persist

- It does not rely on a fragile timing quirk. It trades a *news shock plus an anchor break*: a catalyst (usually earnings) that pushes price through a level many holders anchored on. The underreaction to such news (post-earnings drift and 52-week-high effects) is among the most replicated anomalies.
- Those papers document it over decades and out of sample, including in large caps.
- The economics suit a small account. The edge per event is large (about 0.7% gross) compared with the fixed 0.34% cost, so the strategy only needs about 30 good days a year. Capacity is irrelevant at £1,000.
- Being in cash on 87% of days means low exposure to the zero-mean intraday drift and to tail days, giving a max DD under 4%.
- The gross edge scales up steadily with the lookback (20 → 60 → 120 days) rather than peaking at one value. That is more consistent with a real effect than with a fitted spike.

## 6. Known weaknesses (honest list)

1. **The sample is small.** There are 94 trades in total and only 29 in validation. The standard error of the mean trade is about ±0.3%, so the net edge (+0.40%) is roughly 1.3 SE. That is suggestive, not proof.
2. **Profits are concentrated.** The 5 best trades (ARM +14%, AXON +10%, AXON +7%, MRVL +7%, ISRG +4%) produce 110% of the net P&L. Without them the strategy is about flat. Right-tail dependence is inherent to "stock in play" strategies.
3. **2025 was flat (−£5).** Most of the profit came in 2024. Validation is positive but weaker than dev (PF 1.32 vs 1.43).
4. **The 120-day lookback was chosen on dev** from 3 tried values (later 90/150/252 were checked as sensitivity). Data snooping across about 72 total looks is real. The 60-day variant is much weaker (+1.25% full).
5. **It lags the market badly.** It made +10% against +86% for buy-and-hold over a bull market. It is a low-exposure absolute-return sleeve, not a market beater. Long-only intraday cannot capture the overnight premium.
6. **Hold-out risk from few trades.** On a 1–2 month hold-out it may take only 3–6 trades. One bad earnings fade (e.g. SNPS −4.3%) could make the hold-out negative. With no warm-up history, the breakout filter falls back to about 20–120 sessions and the rvol filter to ≥10 sessions. The no-warm-up validation run was still +4.3% on 24 trades.
7. **Execution assumptions.** Entry is assumed at the 10:30 bar open and exit at the official 16:00 close. A real T212 market order near the close (the engine nominally flattens at 15:50) will get a slightly different price. Opening-volatility slippage on gappers is likely above 2 bps.
8. **Timing.** Waiting until 10:30 (a 1h bar constraint) gives up the opening-range part of the move. That is safer but captures less.
9. **Stops are nearly cosmetic** (2 hits). The real risk control is position size: 50% max of equity, the 2% daily loss halt, and one position at a time.
