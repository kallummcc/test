# Bot 1: Opening Range Breakout on "stocks in play" (`orb`)

## Summary
Buy a Nasdaq-100 stock at 10:30 ET when its first trading hour has at least 5x its normal
first-hour volume and closed 0.5% to 4% above the open. The stop sits at the first-hour low,
there is no target, and the position is sold at the close. Hourly bars, long only.
In-sample (2023-11-24 to 2026-09-23, 100 stocks, GBP account costs): **£1,000 to £1,090.57
(+9.06%)**, 180 trades, PF 1.24, max DD −5.68%, Sharpe 0.68. The edge is small and thin,
and I say so below.

## 1. Research

| Source | What it found | Caveats |
|---|---|---|
| Zarattini, Barbon & Aziz (2024), *A Profitable Day Trading Strategy For The U.S. Equity Market*, SSRN 4729284 / Swiss Finance Inst. RP 24-98. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284), [Concretum summary](https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/), [author page](https://abarbon.com/papers/a-profitable-day-trading-strategy-for-the-u-s-equity-market), [RePEc](https://ideas.repec.org/p/chf/rpseri/rp2498.html) | 5-min ORB on 7,000+ US stocks, 2016–2023. Stocks are filtered to price > $5, 14-day average volume ≥ 1M and ATR > $0.50, and must be "in play": relative volume (RV) is the first 5-min volume / its 14-day average, keep RV ≥ 1 and take the top 20. Direction comes from the first candle. Stop is 10% of the 14-day ATR, exit at the close. The top-20 portfolio made **>1,600% net, Sharpe 2.81, alpha 36%/yr**. **The plain ORB on all stocks had Sharpe ~0.48, so almost all of the edge comes from picking stocks in play.** The paper also tested 15/30/60-min ranges, which did worse than 5-min. | Long + short combined, leveraged (up to 4x), commission only (no spread/slippage), no true out-of-sample period. The edge sits in small/mid-cap names with news, not mega caps. |
| Zarattini & Aziz (2023), *Can Day Trading Really Be Profitable?*, [SSRN 4416622](https://papers.ssrn.com/abstract=4416622), [Concretum](https://concretumgroup.com/can-day-trading-really-be-profitable/) | 5-min ORB on QQQ, 2016–2023. Trade in the direction of the first candle, enter at the next candle's open, stop at the other side of the range, target 10R or the close. About 24% hit rate, about +0.13R/trade, 33% alpha with 4x leverage. | Index ETF, not stocks; leverage is needed; costs are commission only. |
| Independent replication, [MQL5 blog "gross reproduced, net zero"](https://www.mql5.com/en/blogs/post/776235) | The QQQ-ORB gross result reproduced on NQ. **Net of spread and slippage, no market was distinguishable from zero, and 4 of 5 were negative.** | Blog, CFDs, not peer reviewed. It is still the strongest warning that costs kill ORB. |
| [QuantConnect recreation of the stocks-in-play ORB](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/) | Reproduces the high Sharpe (~2.4) with beta near 0. | Same universe and cost caveats. |
| [GitHub replication PR (POB-CL-DT #12)](https://github.com/patrickobirmingham-eng/POB-CL-DT/pull/12) | Reports negative expectancy for its own ORB variants over the most recent 5–9 months. | One user. |

(WebFetch could not reach most of these hosts from the sandbox. The details above come from
search-result summaries of these pages plus my own knowledge of the papers.)

**What carries over to this tournament:** (a) the selection rule (abnormal relative volume),
not the breakout itself, is where the documented edge is; (b) long-only cuts away half the
paper's trades; (c) 0.34% per round trip is about 10x the paper's commission, so the gross move
per trade has to be large. I tested the paper's rules first and then adjusted only along those
three lines.

## 2. Exact rules (submitted `STRATEGY`, `t212_agent/strategies/orb.py`)

- **Bars:** 1h (`interval="1h"`). Opening range (OR) = the 09:30–10:30 bar.
- **In play:** RV = first-hour volume / mean first-hour volume of the **prior** 14 sessions
  (at least 5 prior sessions, then `.shift(1)`). Need **RV ≥ 5**.
- **Direction:** OR candle bullish, with return `close/open − 1` in **[0.5%, 4%]**.
- **Entry:** market buy at the next bar's open (10:30). If several signal together, the highest RV goes first.
- **Stop:** OR low, i.e. `stop_dist = OR close − OR low`, floored at 0.1 × prior-day 14-day ATR. **No target.**
- **Exit:** end of day by the engine (16:00 close on hourly bars).
- **Risk overrides:** `risk_per_trade_pct=1.0` (the paper's 1%), `max_position_pct=40`,
  `skip_first_minutes=5`. Defaults kept: 3 positions, 10 trades a day, 2% daily loss halt.
- **Free parameters:** 4 (RV threshold, OR-return min, OR-return max, stop rule). The 14-day lookback comes from the paper.
- **No look-ahead:** the OR values are used only from the bar that completes the OR. RV and ATR use
  shifted daily aggregates. Test: for 30 symbols × 5 random truncation points, `prepare()` on the
  truncated data gives entry/stop/score identical to `prepare()` on the full data (150/150 matched).

## 3. Results (100 stocks, `data/insample`, £1,000)

Dev = 2023-11-24 → 2025-09-30 (~2/3). Validation = 2025-10-01 → 2026-09-23 (`--trade-from`,
so the RV and ATR history warms up beforehand).

| Period | Costs | Net return | Trades | Win % | PF | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| Dev | GBP (0.34% RT) | **+3.98%** | 129 | 48.1 | 1.14 | −5.68% | 0.45 |
| Dev | fx 0 (0.04% RT) | +18.57% | 129 | 55.0 | 1.75 | −2.76% | 1.81 |
| Validation | GBP | **+4.86%** | 51 | 54.9 | 1.59 | −2.13% | 1.19 |
| Validation | fx 0 | +9.97% | 51 | 62.7 | 2.51 | −1.95% | 2.21 |
| Full | GBP | **+9.06%** | 180 | 50.0 | 1.24 | −5.68% | 0.68 |
| Full | fx 0 | +30.39% | 180 | 57.2 | 1.93 | −2.76% | 1.93 |

Equal-weight buy & hold of the universe: +86% over the full period (+21% in validation).
ORB is market-neutral-ish and sits flat about 75% of days, so it does not try to beat that.

**Gross vs net (full period):** gross P&L before fees is about £294. Costs at 0.34%/RT take
about £204, leaving £90 net. **Costs eat about 70% of the gross edge.** At fx 0, net is £304.

**Exit mix:** 159 trades close at the end of day (+£256), 21 hit the OR-low stop (−£166).
**By year (GBP):** 2023 (Dec only) +£7.6, 2024 +£58.6, **2025 −£7.2**, 2026 +£31.6.
Over the last 39 sessions (the 5m window, 2026-07-30 → 09-23), the strategy took 13 trades for +0.7%.

## 4. Variants tried: 32 full backtests (+ 1 event study)

All variants are logged in `tournament/runs/orb/variants.jsonl` (dev / val / full × both cost settings),
with the harness in `tournament/runs/orb/sweep.py`. Full-period GBP-cost returns:

| # | Variant | Full net | Trades | Notes |
|---|---|---|---|---|
| 1 | **Paper-faithful** 5m: 5-min OR, RV ≥ 1, close > OR high, 10% ATR stop | −6.75% | 181 | gross +£49, costs kill it (fx 0: +3.9%) |
| 2–10 | 5m grid: RV ∈ {1.5, 2, 3} × stop ∈ {0.1, 0.25, 0.5} ATR | −5.0% … +0.8% | 38–140 | **every 5m variant loses on dev**; 39 sessions is too short anyway |
| 11–14 | 1h, 60-min OR, 0.1 ATR stop, breakout or enter-at-10:30, RV 1–2 | −35% … −76% | 670–2,250 | gross positive, turnover suicide |
| 15–19 | 1h, OR-low or 1-ATR stop, RV 2/3/5 | −2.8% … −44% | 294–1,406 | gross positive in every one; only RV 5 nears breakeven |
| — | Event study (`event_study.py`): 10:30-open → close return by RV bucket × OR body | — | — | bullish & RV>5: mean +0.31%, bearish & RV>5: −0.15% (continuation is real, gross); OR body < 0.5% or > 4% was negative |
| 20–23 | add OR-body filters (min 0.5%, ± max 4%) at RV 3 / 5 | −18.7% … +4.4% | 180–648 | #23 = chosen rules at default sizing (+4.4%, PF 1.24) |
| **24** | **#23 + paper's 1% risk, 40% cap (submitted)** | **+9.06%** | 180 | same trades, about 2x the size |
| 25 | #23 with a 2-ATR (catastrophe) stop | +5.23% | 180 | dev better, val worse; kept the paper's OR-low stop |
| 26, 30 | RV 4 / RV 6 | −4.09% / −0.50% | 275 / 114 | **sensitivity: the edge is not robust to the RV threshold** |
| 27–29 | OR-body max 3% / min 0.3% / max 5% | +1.22% / +3.32% / +2.90% | 144–204 | positive across neighbours |
| 31 | #23 but wait for a 1h close above OR high | −1.93% | 67 | hourly confirmation enters too late |
| 32 | final rules on 5m bars (60-min OR) | +0.31% | 9 | cross-check on the 39-day 5m window |

**Selection honesty:** I chose the RV ≥ 5 threshold and the 0.5–4% body band after seeing the
event study, which covered the **whole** sample including validation. So the validation period
is **not** a clean out-of-sample test of those two choices. Only the judge's hold-out is clean.

## 5. Why this edge should persist
- **Mechanism:** abnormal opening volume marks news-driven repricing (earnings, guidance, M&A,
  index events). Information is absorbed slowly over the session, so the first hour's direction
  tends to continue. This is the effect Zarattini et al. document across 7,000 stocks and 8 years.
  My data shows the same asymmetry before costs: bullish high-RV first hours drift up, bearish ones drift down.
- **Few, large trades:** about 1 trade every 4 sessions, each held about 5.5 hours, so the
  0.34% fee is paid rarely and only on days with the largest expected moves.
- **No fitted price levels:** the rules use ratios (RV, % body) and the OR's own low, so they scale across prices and regimes.
- **Hold-out timing:** the hold-out after 2026-09-23 covers the October earnings season, when
  RV ≥ 5 days are most frequent.

## 6. Known weaknesses (attack these; I would)
1. **Thin edge, fat-tail dependent.** Without the 5 best trades the full-period net P&L is about −£2. AXON alone made £72 of the £91.
2. **Threshold-sensitive.** RV 4 → −4.1%, RV 6 → −0.5%, RV 5 → +9.1%. The ridge is narrow, and the RV/body filters were chosen with knowledge of the whole sample (see §4).
3. **2025 was negative** (−£7), so the edge has had full losing years.
4. **Small sample:** 180 trades over 2.8 years and 51 in validation. On a 1–2 month hold-out expect only about 5–15 trades, so luck dominates and a loss is quite possible.
5. **Costs:** about 70% of gross goes to fees. Slippage above 2 bps on gap/news stocks would erase the remainder. The 10:30 fill is the hourly bar's open, a liquid time, but news names spread wider.
6. **Not the paper's strategy.** It uses a 60-min OR, not 5-min (the paper says longer ranges are worse), long side only, and a 100 mega-cap universe instead of 7,000 stocks. The paper-faithful 5-min version (#1) **lost 6.75%** here. I am trading the paper's selection insight, not its exact rules.
7. **Hold-out warm-up:** RV needs at least 5 prior sessions. If the judge's data has no history before the hold-out, the first week cannot trade.
8. **Lags buy & hold badly** in a bull market (+9% vs +86%). It wins only on risk (DD −5.7%, flat most days).
9. **Hourly stop handling:** an intrabar stop on 1h bars is coarse. A gap through the OR low fills at the open, which the engine models, but real fills could be worse.
