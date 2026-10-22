# trend_1h — First-hour channel breakout on "stocks in play" (1h bars)

**Bot 4, lane: higher-timeframe intraday trend following.**
**Short version: in-sample, this strategy loses money at the default GBP costs.**
Full period: −13.1%, 460 trades, PF 0.73. The development period has no gross edge,
about +0.02% per trade. A USD account (fx 0) would have made +4.9%.
I'm publishing these numbers as they are, not dressing them up.

## 1. Research

| Source | Finding | Caveat for us |
|---|---|---|
| Zarattini, Barbon & Aziz (2024), *A Profitable Day Trading Strategy for the U.S. Equity Market*, SFI WP 24‑98 — [IDEAS](https://ideas.repec.org/p/chf/rpseri/rp2498.html), [replication on QuantConnect](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/), [CXO summary](https://www.cxoadvisory.com/individual-investing/intraday-trading-of-overactive-stocks-via-opening-range-breakout/) | Opening-range breakout pays off **only on "Stocks in Play"**, meaning names with abnormal relative volume (top 20 out of about 7,000 stocks). The paper also tests 15/30/60-minute ranges. | Their universe is far wider than the Nasdaq-100. Costs are per share for a USD account. The paper is an unreviewed working paper. |
| Gao, Han, Li & Zhou (2018), *Market intraday momentum*, JFE 129 — [WUSTL](https://profiles.wustl.edu/en/publications/market-intraday-momentum/) | On SPY, the first half-hour return predicts the last half-hour return. The effect is stronger on high-volume and high-volatility days. | It is a market-level (ETF) result, and the predicted window is only the final 30 minutes. |
| Baltussen, Da, Lammers & Martens (2021), *Hedging demand and market intraday momentum*, JFE — [Tinbergen](https://tinbergen.nl/publication/168044/hedging-demand-and-market-intraday-momentum) | Intraday momentum holds across 60+ futures and is explained by gamma hedging. | Index level, not single stocks. |
| Barbon, Aziz & Zarattini (2024), *Beat the Market* (SPY noise-area breakout) — [SFI](https://www.sfi.ch/de/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy) | Intraday trend following on SPY, with breakouts beyond the "noise area" and VWAP trailing stops. The paper reports Sharpe 1.33 net. | Independent replications report much weaker results. It is an ETF strategy, and UK retail can't trade US ETFs. |
| Zarattini, Pagani & Wilcox (2025), *Does trend following work on stocks?* — [CXO](https://cxoadvisory.com/momentum-investing/all-time-high-trend-following) | Long-only breakouts to all-time highs on US stocks work. Fewer than 7% of trades produce most of the profit. | The trades are multi-week holds. We can't hold overnight, so the fat right tail gets cut off every day. |
| Lou, Polk & Skouras (2019), *A tug of war: overnight vs intraday expected returns*, JFE 134 — [LSE](https://personal.lse.ac.uk/polk/research/TugOfWar.pdf) | **All of the momentum premium is earned overnight.** Intraday, momentum tends to reverse, and more so in large, high-priced stocks. | This is the main reason multi-day trend filters fail inside a flat-every-night constraint (see the Donchian results below). |
| Marshall, Cahan & Cahan (2008), 7,846 intraday technical rules on SPDR — [via CXO](https://www.cxoadvisory.com/?p=1253) | After a data-snooping correction, **none** of the intraday rules is significant. | A warning about how many variants anyone (including me) tries. |
| Intraday momentum in single stocks: the evidence conflicts — [Notre Dame end-of-day reversal](https://www3.nd.edu/~zda/EOD.pdf) vs [Hull](https://hull-repository.worktribe.com/OutputFile/3016448) | One paper finds reversal at the stock level, the other finds momentum. | The sign is not settled. |

**What I took from the research.** Plain channel and MA trend following on hourly bars has
no documented intraday edge in large caps. Lou, Polk & Skouras even argue the sign is negative. The one
version with credible evidence for single stocks is **opening-range breakout limited to stocks
with abnormal volume**, so that is what I built. On 1h bars the "opening range" is the first bar (09:30–10:30).

My own data agreed. A Donchian 7/21/35/70-bar breakout held to the close had a gross edge between −0.03% and
+0.04% per trade in both periods, with or without a 50-day trend filter
(`runs/trend_1h/explore5_out.txt`). A daily trend filter also did not help the in-play signal
(`explore2_out.txt`).

## 2. Exact rules (`t212_agent/strategies/trend_1h.py`)

All daily statistics are computed from **completed prior sessions only** (`.shift(1)`).

1. **In play:** the first-hour (09:30 bar) volume is at least **3×** the mean first-hour volume of the prior **20** sessions.
2. **Trend:** the first-hour close minus the first-hour open is at least **0.5 × ATR14**. ATR14 is the 14-session ATR of daily bars from prior sessions.
3. **Entry:** the signal is decided at the 10:30 close of the first bar and fills at the **10:30 open**. One entry per symbol per day. When more than 3 names qualify, they are ranked by relative volume.
4. **Stop:** a catastrophe stop at **3 × daily ATR** below entry. It fired once in 460 trades.
5. **Exit:** hold to the session close. With hourly bars, the engine closes at the 15:30 bar's close, which is 16:00.
6. **Overrides:** `risk_per_trade_pct` 1.0, `max_position_pct` 33, `max_open_positions` 3, `max_daily_loss_pct` 5.
   Sizing is 1% risk per 3 ATR, which works out to an average position of about £142 (about 14% of equity).
   The session settings stay at their defaults. With hourly bars, skip-first-15 lets the 10:30 fill through, and the
   30-minutes-before-close rule makes 14:30 the last possible fill. Only 10:30 fills are used.

There are 4 tuned parameters: rv threshold, move threshold, stop multiple, and the risk and position caps.
The 20- and 14-session lookbacks are textbook defaults and were not tuned.

**Look-ahead check:** I ran `prepare()` on 40 random truncations of NVDA and compared the last bar with the
full-sample output. There were 0 mismatches.

## 3. Results

Dev = 2023‑11‑24 → 2025‑10‑31 (about 2/3). Val = 2025‑11‑01 → 2026‑09‑23 (warm-up via `--trade-from`).
All 100 symbols, £1,000 start. GBP = 2 bps + 0.15% FX per side. USD = `--fx-fee-pct 0`.
Gross = 0 bps and 0 FX.

| Period | Costs | Net return | Trades | Win % | PF | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| Dev | GBP | **−13.4%** | 314 | 40.8 | 0.65 | −13.6% | −1.85 |
| Dev | USD | −0.6% | 314 | 46.8 | 0.98 | −3.9% | −0.06 |
| Val | GBP | **+0.4%** | 146 | 47.3 | 1.03 | −3.2% | 0.24 |
| Val | USD | +5.6% | 146 | 55.5 | 1.53 | −1.5% | 2.08 |
| Full | GBP | **−13.1%** | 460 | 42.8 | 0.73 | −14.1% | −1.33 |
| Full | USD | +4.9% | 460 | 49.6 | 1.11 | −3.9% | 0.47 |
| Full | gross | +7.6% | 460 | 51.1 | 1.17 | −3.5% | 0.70 |

**Per year, net return (trades):**

| Year | GBP | USD | Gross |
|---|---|---|---|
| 2024 | −6.1% (183) | +2.1% | +3.3% |
| 2025 | −6.1% (155) | +0.3% | +1.1% |
| 2026 to Sep 23 | −1.5% (122) | +2.5% | +3.1% |

Over the same window, buy & hold of the universe returned +86% on 1h data. This strategy is in the market
for only about 5.5 hours on about 43% of days (302 of 709), at roughly 14–40% of equity.

**Gross vs net:** the average gross trade is **+0.16%**, against a round-trip cost of 0.34%.
That is +0.02% in dev and +0.45% in val. FX fees cost about 18 points of return over the full period.
The strategy is cost-dominated.

## 4. Variants tried (full disclosure)

- **89 conditional-mean slices** of panel data. These were vectorised "enter at 10:30, hold to the close" tests of first-hour return, gap, relative volume, ATR-scaled move, a 50-day trend filter, market-wide first-hour return, and Donchian 7/21/35/70. Scripts and outputs are in `tournament/runs/trend_1h/explore*`.
- **14 engine variants (V1–V13 plus V7b)**, each run on dev, val and full at both cost settings. Logs: `engine_variants_v1.txt` and `engine_variants_v5_v13.txt`.
  - I changed the stop type (first-hour low vs ATR catastrophe), the stop width (1, 1.5, 2 and 3 ATR), rv (1.5/2/3), the move threshold (0.25/0.5/1.0 ATR), a VWAP exit, confirmed-later-breakout entry, and a single concentrated position.
  - V7 turned out to be a no-op and was identical to V2.
- **Selection rule:** I picked the best **dev** result at GBP costs (V12). Val was not used to choose.
  - Most of V12's advantage over V5 comes from smaller positions: a wider stop under risk-based sizing means less exposure. Its PF is the same as V5's (0.65 vs 0.64 in dev).
- **No variant was profitable in dev at GBP costs.** The best was −13.4% and the worst −56%. Every variant was positive in val at USD costs. The dev/val disagreement is the main finding, not a detail.

## 5. Why the edge could persist (the case for it)

- Abnormal first-hour volume marks information arriving: earnings, news, upgrades. Institutions take hours to work large orders, so the price drifts in the direction of the first hour. This is the mechanism Zarattini et al. describe, and the late-informed-trading story in Gao et al.
- It trades **less often** than any 5-minute system: about 160 trades a year, one round trip each, with no stop-outs that cut winners. Against a 0.34% cost floor, low turnover is the only lever that works.
- The signal is not fitted to a regime. In val, at USD costs, it was positive under every rv/move/stop setting I tried.

## 6. Known weaknesses (please attack these; I already have)

1. **There is no net edge at the judge's costs.** The full period is −13.1% and dev is −13.4%. Val at +0.4% is a rounding error. On the hold-out, my central expectation is a small loss.
2. **The dev period has no gross edge** (+0.02% per trade over 314 trades). All of the gross profit comes from the final 11 months. That looks like a regime effect (the 2025–26 momentum and AI-beta tape) or luck. It is not a demonstrated persistent edge.
3. **The research is against intraday momentum.** Lou, Polk & Skouras find the momentum premium is earned overnight and reverses intraday, especially in large caps. The Nasdaq-100 is the opposite of the 7,000-stock "in play" universe in the Zarattini paper.
4. **Small sample at the stock level.** Some names, such as ARM, CRWD, AXON and APP, account for many of the trades. About 160 trades a year is low for a cross-section of 100 names.
5. **Hourly granularity is coarse.** We enter a full hour after the open, so most of the opening range move is already gone. Real ORB uses 5-minute entries and tight stops. I tested tight first-hour-low stops on hourly bars, and they cut too many winners (V1, V3, V13).
6. **About 103 things tried in total** (89 panel slices plus 14 engine runs). Given the Marshall et al. result, a good-looking val number after this many tries should be discounted heavily.
7. A market-wide first-hour filter showed something in the panel: rv>2, move>0.5 ATR, universe first hour >0 gave +0.25% dev and +0.36% val gross. I could not use it, because `prepare()` sees only one symbol. Even so, it is below the 0.34% cost.

**Bottom line for the judge:** this is the best-evidenced version of 1h intraday trend following I could find,
and it is the least-bad version I tested. It roughly breaks even before FX and loses money after it.
It would beat the `ema_vwap` baseline (−21%) in-sample, but that is a low bar.
