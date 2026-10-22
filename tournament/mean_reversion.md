# Bot 2 — Intraday Mean Reversion ("mean_reversion")

**One line:** on hourly bars, buy a Nasdaq-100 stock that is in an uptrend (yesterday's close above its 50-day SMA) and was oversold at yesterday's close (daily RSI(2) < 5), on the first bar where it trades at least 2% below yesterday's close. Hold it to the close, with a 3×ATR(14, hourly) catastrophe stop.

File: `t212_agent/strategies/mean_reversion.py` (interval `1h`). Scratch output, logs and exploration scripts are in `tournament/runs/mean_reversion/`.

---

## 1. Research

| Source | What it found | Relevance / caveat |
|---|---|---|
| Connors & Alvarez, RSI(2) rules (summaries: [LuxAlgo](https://www.luxalgo.com/library/concept/rsi-2/), [Quantified Strategies QQQ RSI(2)](https://quantifiedstrategies.substack.com/p/rsi-mean-reversion-trading-strategy), [QS RSI QQQ](https://quantifiedstrategies.substack.com/p/rsi-trading-strategy-for-qqqrsi-qqq)) | Buying a 2-period RSI below 10 (below 5 is stronger) only when price is above a long moving average, then exiting on the first bounce, has been profitable in US indices and large caps. QS reports a 75% win rate and PF of about 3 on QQQ. Connors found stops hurt the results. | This is the most widely documented short-term mean-reversion rule, but it uses **daily** bars and holds positions **overnight** for 1–5 days. The sources are practitioners, not peer-reviewed. |
| Heston, Korajczyk & Sadka (2010), *Intraday Patterns in the Cross-Section of Stock Returns*, J. Finance ([PDF](https://www.bauer.uh.edu/departments/finance/documents/Heston_Korajczyk_Sadka_paper_UH.pdf), [Kellogg](https://www.kellogg.northwestern.edu/academics-research/research/detail/2010/intraday-patterns-in-the-cross-section-of-stock-returns/)) | Short-horizon returns reverse. The reversal comes from temporary liquidity imbalances lasting under an hour, plus bid-ask bounce. | This is the academic basis for "intraday selling pressure reverses". The reversal is small (a few bps per half hour), far below our 0.34% round-trip cost. |
| Lou, Polk & Skouras (2019), *A Tug of War: Overnight versus Intraday Expected Returns*, JFE ([PDF](https://personal.lse.ac.uk/polk/research/TugOfWar.pdf), [LSE](https://researchonline.lse.ac.uk/id/eprint/87481)) | Overnight and intraday returns are opposite clienteles. Institutions trade intraday against momentum. Momentum profits come overnight, and intraday returns tend to reverse them. | Supports buying an intraday dip. **Caveat:** they find the classic (monthly) *reversal* strategy earns its profits **overnight**, which a flat-every-night account cannot capture. |
| Baltussen, Da & Soebhag, *End-of-Day Reversal* ([PDF](https://www3.nd.edu/~zda/EOD.pdf)) | The day's losers rebound sharply in the cross-section during the last 30 minutes. The authors attribute this to retail attention and short-seller risk management, not to liquidity. | Holding to the close captures that final half hour. It is a cross-sectional effect; we can't rank cross-sectionally because `prepare()` sees only one symbol. |
| QuantConnect reproduction of a VWAP intraday strategy on QQQ ([link](https://www.quantconnect.com/terminal/cache/embedded_backtest_b115d0894231d55994b1068202f6c0ae.html)); [QuantRocket gap-down study](https://www.quantrocket.com/blog/buy-or-sell-down-gaps/) | The VWAP edge disappears at roughly 1 bp of round-trip cost. Buying liquid gap-downs **lost** money; fading the gap was the profitable side. | These are warnings. Fast VWAP-touch mean reversion is a high-frequency liquidity-provision trade that retail costs destroy. |

**What the research implies for us.** With a 0.34% round trip, the classic intraday fade (buy far below VWAP, sell on the VWAP reclaim) can't work: its gross edge is a few bps. The only way to clear the cost is an event with a **large expected rebound per trade**. A multi-day oversold condition (Connors) plus a fresh capitulation today (a liquidity shock, per HKS) supplies that, and holding to the close also captures the end-of-day reversal. I built the rule on that combination.

## 2. Exact rules (final, as submitted)

These rules use hourly bars of the regular session (America/New_York). Bar t uses only data up to and including bar t.

1. **Trend:** yesterday's daily close is above the SMA of the last 50 completed daily closes. At least 10 sessions of history are required; until 50 sessions exist, the SMA uses whatever days are available.
2. **Oversold:** the Wilder RSI(2) of daily closes, as of yesterday's close, is below 5.
3. **Capitulation:** the latest closed hourly bar's close is at least 2.0% below yesterday's close.
4. **Entry:** on the first bar of the session where conditions 1–3 all hold. The engine fills at the next bar's open. The engine's window allows decisions from the 09:30 bar through the 13:30 bar, so fills happen 10:30–14:30. There is one signal per symbol per day.
5. **Exit:** none from the strategy. The position is held to the session close; the engine closes it at the 16:00 close. A stop sits at 3 × ATR(14) of hourly bars below the entry.
6. **Ranking:** the biggest drop today goes first. The engine's limit of 3 positions applies.
7. **Sizing overrides:** `risk_per_trade_pct=2.0` and `max_position_pct=33`, so the 33% cap binds and each trade is about a third of equity. `max_daily_loss_pct=5`.

There are 4 signal parameters (trend 50, RSI < 5, drop 2%, stop 3 ATR) plus the sizing overrides.

Look-ahead check: running `prepare()` on truncated data gives identical signals over the shared prefix for all 100 symbols (0 mismatches).

## 3. Results (in-sample, 100 symbols, 1h, `--symbols all`)

Dev runs 2023-11-24 → 2025-09-30. Validation runs 2025-10-01 → 2026-09-23, with earlier bars used as warm-up through `--trade-from`. Full covers the whole range.

| Period | Costs | Net return | Trades | Win % | PF | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| Dev | default (GBP, 0.34% RT) | **+5.85%** | 53 | 58.5 | 1.90 | −2.38% | 1.02 |
| Validation | default | **+3.37%** | 55 | 52.7 | 1.27 | −4.12% | 0.65 |
| Full | default | **+9.43%** (£1,094) | 108 | 55.6 | 1.48 | −4.12% | 0.81 |
| Dev | `--fx-fee-pct 0` (0.04% RT) | +11.34% | 53 | 66.0 | 3.46 | −2.00% | 1.75 |
| Validation | `--fx-fee-pct 0` | +9.01% | 55 | 56.4 | 1.89 | −3.36% | 1.65 |
| Full | `--fx-fee-pct 0` | +21.39% | 108 | 61.1 | 2.35 | −3.36% | 1.66 |

**Gross vs net, full period at default costs:** the gross price P&L is +£215. The average gross move per trade is +0.73% (median +0.53%), and the average position is £329. The 0.34% round trip takes about £121, roughly 56% of the gross. The net is +£94.

**Benchmark:** equal-weight buy and hold made +86% over the full period and +21% in validation. The strategy is invested only on about 78 of 709 days and is flat overnight, so it is a low-exposure overlay, not a substitute for buy and hold.

**By calendar year (net P&L in £):** 2024 −14.7 (25 trades), 2025 +92.0 (38 trades), 2026 to date +16.9 (45 trades).

## 4. Variants tried (full disclosure)

**Event studies:** about 110 signal/condition cells, in `an*.py`. These measured the forward return from the next bar's open to the close, split by dev and validation, on 1h data, plus about 17 cells on 5m data. The tests covered:
- the intraday drop versus yesterday's close, the drop from today's open, the distance below VWAP, and hourly RSI(2), each with and without 20/50/100/200-day trend filters;
- the drop scaled by volatility, gap-downs with and without a green first bar, 20/60-day momentum filters, and results by hour of day;
- daily RSI(2), yesterday's return, and combinations of these.

**Result:** none of the purely intraday conditions had a gross edge above about 0.1% that held in both halves. In the dev period, deep intraday drops actually *continued* lower. The only family that was positive in both halves and grew stronger as the condition got deeper was a daily RSI(2) oversold reading in an uptrend, combined with a further drop today.

**Engine backtests, each run on both dev and validation:**
- **VWAP-fade version** (hourly RSI(2) < 10, ≥ k×ATR below VWAP, exit on VWAP reclaim or RSI > 70, or hold to the close): 7 variants. The default k=1 lost −56% in dev with 1,133 trades, and k=1.5 lost −28% to −29%. Turnover destroyed it. **Rejected.**
- **Capitulation version:** RSI < 5 or < 10, drop 1% or 2%, trend 50 or 200 days, at default sizing: 6 variants. Then sizing and stop: 33% positions at stop 3 or 5, and drop 1% at 33%: 3 variants. **I picked RSI < 5, drop 2%, trend 50, stop 3, 33% sizing.**
- **Sensitivity check after selection** (in `sensitivity.log`): 9 neighbours of the final choice, listed below.

| Neighbour | Dev net | Val net |
|---|---|---|
| **final** (drop 2, RSI 5, SMA 50, stop 3) | +5.9% | +3.4% |
| drop 1.5% | +4.3% | +3.7% |
| drop 2.5% | +4.8% | +0.6% |
| drop 3.0% | +6.8% | +1.0% |
| RSI < 3 | +4.3% | +2.4% |
| RSI < 7.5 | +5.0% | +1.1% |
| RSI < 10 | +5.2% | **−4.3%** |
| SMA 100 | +1.1% | **−2.1%** |
| SMA 200 | **−3.3%** | +1.6% |
| stop 2 ATR | +7.4% | +5.3% (not adopted: chosen after the fact) |

**Total:** about 25 engine configurations and about 125 event-study cells. **Gross P&L was positive in every one of the capitulation variants**, but the **net** result depends on the parameters chosen. Loosening the filters (RSI 10, a 1% drop) adds trades whose gross edge is smaller than the cost.

## 5. Why this edge should persist

- **The mechanism is a forced-liquidity trade.** A stock that has fallen hard for several days and gaps or slides another 2% or more is being hit by stop-outs, de-risking and attention-driven selling. Someone supplying liquidity to that flow earns a premium (HKS 2010). The end-of-day reversal (Baltussen, Da & Soebhag) adds to it in the final half hour, and we hold through it.
- **The trend filter limits trades to strong large caps,** where a dip is more likely to be a temporary liquidity event than a re-rating. That is the core of Connors' rule.
- **The effect is monotone and sensible.** A deeper oversold reading and a bigger drop today both raise the gross rebound per trade in both halves. For example, in the event study, the first trigger of the day with RSI < 5 and a 2% drop gave +0.81% gross in dev and +0.62% in validation. That pattern looks like a real effect rather than a lucky threshold.
- **It is capacity-irrelevant at £1,000.** It doesn't compete with HFT on speed, because it holds for hours, not minutes.

## 6. Known weaknesses (honest list)

1. **The edge is thin relative to costs.** About 56% of the gross P&L goes to FX fees and slippage, and net expectancy is about +0.29% per trade. A small rise in slippage, or a worse fill at the open of the bar after the signal, could erase it.
2. **The profit is concentrated on a few days.** The 108 trades fall on 78 days. **Removing the 5 best days takes full-period net P&L from +£94 to about −£4**, and removing the 10 best days gives about −£65. This is a right-tail strategy with a modest win rate.
3. **The most recent period is negative.** In the 39 sessions covered by the 5m file (2026-07-30 → 2026-09-23), the rule made 11 trades and lost about £32. Calendar 2024 was also negative (−£15). Validation was positive overall, but the latest months haven't been.
4. **The sample is small.** 108 trades over 2.8 years is about 3 per month. A hold-out window of a month or two will hold perhaps 2–10 trades, so the hold-out result is largely luck. With few or no signals the result can also be roughly flat. The strategy needs at least 10 sessions of 1h history before it can trade; it works best with 50 or more.
5. **The parameters are fragile.** RSI < 10, SMA 100 and SMA 200 each turn one half negative. I picked the final values from 6 or more candidates, so some selection bias is built in.
6. **The research doesn't fully support intraday-only holding.** Connors' edge, and the reversal profits in Lou-Polk-Skouras, are partly or mostly **overnight**, and we give that up. The large gross edge per trade in the published RSI(2) rules shouldn't be read as ours.
7. **There are no cross-sectional or market filters.** `prepare()` sees one symbol, so we can't tell an idiosyncratic dip from a market crash. On sell-off days, several positions fill together and are correlated; the worst day was 2025-11-20 at −£25. The 3-slot limit and the 5% daily halt cap the damage.
8. **There is a bull-market regime dependence.** The data window had strong buy-the-dip rewards. In a bear market the trend filter switches most names off, which is protective but means few trades.
9. **The strategy underperforms buy and hold by a wide margin** (+9% versus +86% over the full period), because it is in the market less than 11% of days.
