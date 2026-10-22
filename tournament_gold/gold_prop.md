# gold_prop: the prop-firm specialist (XAUUSD)

**Thesis.** You pass FTMO through trade geometry and risk engineering, laid on a modest,
simple edge. The geometry is the target/stop ratio, volatility-scaled stops, the session
calendar and the daily stop. The edge is to trade in the direction of the hourly trend
at fixed session times. A walk-forward re-picks the geometry every week, by an objective
built for the prop rules.

**Verdict up front:**
- On development data (2024-06 → 2025-10) it meets every hard requirement: win 61.4%,
  1.44 trades/day, avg R +0.036, no daily-limit breaches. It passes both phases 32.4% of
  the time, against 2.8% for `random_gold`.
- On the final check (2025-11 → 2026-03), looked at once, it **fails**: win 57.7%,
  avg R −0.043, both phases 4.5% (random_gold 2.4%).
- Over the full period it scrapes in: win 60.6%, avg R +0.019, PF 1.07, both phases 23.9%.
- Even there it fails the 2× spread test (avg R −0.004).

The direction signal clearly beats coin flips at the same timing and geometry. It beats
plain "buy gold" only slightly. Details below. I'd rather you read that here than from a
critic.

---

## 1. Research

**Prop-firm statistics.** FTMO does not publish an audited pass rate. The figures below
are third-party.
- Commonly cited: about 10–12% for both phases, and about 9–10% for phase 1 alone.
- About 70% of failures come from breaching a loss limit, mostly the daily limit.
  A Traders Union survey (self-selected) found 67% of failures were risk-rule breaches
  and 18% were "never reached the target".
- FTMO's rule page (on OANDA's domain) confirms the Maximum Daily Loss is 5% of the
  *initial* balance, including floating P&L.
- FTMO's own blog ("less is sometimes more") features successful traders with modest
  win rates (35–52%) and RRR > 2. These are curated success stories, not representative.

**Lesson for the design:** the first job is never to touch the daily limit, so two full
losses must sit well under 5%. The second is enough expectancy × frequency to beat the
timeout. Phase-1 timeouts, not fails, are the main failure mode of a low-variance
high-win-rate bot.

Sources:
- https://ftmo.oanda.com/how-to-pass-ftmo-challenge/ (FTMO rules: 5% MDL incl. floating)
- https://ftmo.com/en/blog/ftmo-traders-analysis-less-is-sometimes-more/ (FTMO trader case studies)
- https://tradersunion.com/news/financial-news/show/2656095-traders-fail-challenges/ (67% rule breaches)
- https://hackernoon.com/the-real-reason-traders-blow-prop-firm-evaluations (~70% loss-limit breaches; unsourced)
- https://backtrex.com/en/blog/prop-firm-challenge-success-rate and https://traderssecondbrain.com/guides/prop-firm-pass-rate (pass-rate aggregators, 8–15%)
- https://www.luxalgo.com/mcp/prop-firm-sim/ftmo-100k-2step/ (simulated: 67% of fails are daily-loss breaches)

**Gold intraday evidence.**
- Blose, Gondhalekar & Kort: gold overnight returns are significantly positive and
  daytime returns negative — https://ideas.repec.org/a/spr/jecfin/v42y2018i3d10.1007_s12197-017-9403-0.html
  **I checked this on our dev data and it is absent.** In 2024–25 every session was
  positive (bull market), so I don't use it.
- Batten et al. (PLoS ONE 2017): strong intraday periodicity in precious-metal volatility
  and spreads — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5407636/
  This matches what I see: the 12–15 UTC bars have about 1.7× the range of other hours
  ($14–17 vs $7–10 on dev). That's why those fill hours are blocked.
- UZH study on the London PM fix (short London-open→PM-fix, long otherwise; weak after
  costs) — https://www.merlin.uzh.ch/publication/show/11299
  CBS thesis (hat-shaped intraday pattern) — https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/
- Short-term reversal in gold/silver futures, linked to news flow and volume —
  https://scholar.kyobobook.co.kr/article/detail/4010023856344
  Practitioner gold mean-reversion results (self-reported) —
  https://blog2.ungeracademy.com/exploring-gold-futures-with-trend-following-and-mean-reverting-strategies/
- Time-series momentum (Moskowitz, Ooi & Pedersen 2012, JFE), which is the edge used
  here — https://papers.ssrn.com/abstract=2089463

**My own pre-tests (dev only, ≤ 2025-10-31):**
- Detrended rank-IC of 10 hourly features on 2/4/8h forward returns, in three dev thirds:
  nothing above |0.03| with a stable sign. Gold's hourly drift (0.23 ATR per 8h on dev)
  swamps everything.
- 2000–2024 daily history: shorting in a gold downtrend (10–200-day SMA rules) lost money
  in almost every 5-year block. Shorts in gold are structurally hard, and that's a caveat
  for every bot here.

## 2. Exact rules (`prop_fx/strategies/gold_prop.py`)

Base `GoldTrendSession`. Decisions are made at the close of bar t and fill at bar t+1's
open.

| Piece | Rule |
|---|---|
| Direction | sign(EMA100(close) − EMA100 24 bars ago). Long if rising, short if falling (symmetric). |
| Entry times | Fill bar at 01, 10 or 16 UTC only. Never 12–15 UTC (US data) or 21–22 UTC (break). |
| Regime filter | No entry if ATR(24) > 1.5 × its 20-day rolling median. |
| Stop / target | Stop = `stop_atr` × ATR(24). Target = `target_r` × stop. |
| Session exit | Flatten at 00, 09 and 15 UTC (1h before the next session), so the single slot is free. |
| Account | `risk_pct=1.5`, `max_positions=1`, `max_trades_per_day=2`, `daily_stop_pct=3.0`. |

Learner `PropWalkForward` subclasses `adaptive.WalkForward` and keeps the same mechanics.
- **Grid:** `stop_atr ∈ {1.5, 2.0, 2.5, 3.0}` × `target_r ∈ {0.4, 0.5, 0.6, 0.7}`, 16 sets.
- **Refits:** `train_weeks=12`, `refit_weeks=1`, `min_trades=10`.
- **Objective `prop`:** sets with trailing win ≥ 60% **and** avg R > 0 rank above all
  others. Within a tier the score is `pass_score` (total R + 2 × worst day).
- **Prior:** until 12 weeks of history exist, it trades the prior set (2.0 ATR / 0.6R)
  instead of sitting flat. This matters on a short hold-out file. With the stock
  WalkForward, 12 of ~28 hidden weeks would be flat and trades/day would fall far below 1.2.

**Why these risk numbers:**
- Max 2 trades/day × 1.5% = 3.0% worst day, and the 3% daily stop is the backstop.
  That leaves a 2% buffer under FTMO's 5% for gaps and slippage. The worst trade
  in-sample was −1.006R and the worst day −3.00%.
- 1.5% won on dev against the alternatives (both phases / P1 fail):

| risk | 1.0 | 1.25 | 1.5 | 1.75 | 2.0 |
|---|---|---|---|---|---|
| both phases / P1 fail | 23.4 / 4.2* | 23.2 / 8.3 | 32.4 / 13.2 | 39.2 / 17.9 | 43.8 / 22.4 |

\*1.0 is from the cycle-7 config.

- Above 1.5% the pass rate keeps rising, but the P1 fail rate rises faster. At 2.0% two
  losses = 4% leaves only a 1% buffer. `random_gold` at the same 1.5%/3% passes 12.1% on
  dev and 12.8% on full, so the extra risk is not the edge.

## 3. Learning journal (all cycles diagnosed on dev ≤ 2025-10-31 only)

**Engine change mid-way.** The engine was changed to "close positions across >6h data
gaps" while I worked. I replayed every cycle on the current engine
(`runs/gold_prop/replay.py`). The table shows the replay numbers; decisions were made
on the original numbers, and both are in `variants.jsonl`. Cycles 0–6 run at 1.0% risk.
Columns: win %, avg R, trades/day (CLI formula, warm-up included), both-phase bootstrap %,
P1 fail %.

| # | Diagnosis → one change | win | avg R | t/d | both | P1 fail | Decision |
|---|---|---|---|---|---|---|---|
| 0 | Baseline: sessions 01/08/16, grid stop{1.5–3} × target{0.5–0.8}, pass_score | 61.4 | .056 | 1.05 | 19.8 | 8.0 | – |
| 1 | Want ≥60% enforced → objective `prop` | 61.9 | .059 | 1.06 | 20.6 | 7.8 | Reverted (originally win 60.3 / R .045 / 14.8%). Re-added in cycle 12. |
| 2 | 08 UTC entries lose (−0.012R; London-open whipsaw) → move to 10 UTC | 63.0 | .077 | 1.10 | 28.9 | 5.2 | **Kept.** Shorts went from +0.009 to +0.046R. |
| 3 | Top-quartile ATR regime (> 1.24× median) R ≈ 0, win 58% → vol filter 1.25 | 64.2 | .095 | 0.93 | 24.4 | 1.4 | Kept for quality, but frequency fell. |
| 4 | Restore frequency → add 18 UTC session | 63.5 | .080 | 0.93 | 19.0 | 1.7 | Reverted (slot still occupied). |
| 5 | Restore frequency → max_hold {0, 6} grid axis | 62.9 | .096 | 0.94 | 26.4 | 1.6 | Reverted (no frequency gain). |
| 6 | Compromise → vol filter 1.5 | 63.4 | .084 | 1.00 | 25.1 | 3.8 | **Kept.** |
| 7 | 60% timeouts → risk 1.5%, daily stop 3% (tested 1.0–2.0 × stop after 1 or 2 losses) | 63.7 | .085 | 0.99 | 48.0 | 11.8 | **Kept.** |
| 8 | trades_per_day counts every data day incl. Sundays and warm-up: below 1.2 → session exit | 57.6 | .070 | 1.21 | 47.1 | 8.1 | Kept for frequency, but win < 60. |
| 9 | Win < 60 → targets {0.4–0.7} | 60.3 | .047 | 1.21 | 32.4 | 10.8 | **Kept.** |
| 10 | 12 flat warm-up weeks → prior set 2.0/0.6 | 60.3 | .036 | 1.44 | 33.4 | 14.1 | **Kept.** |
| 11 | Win margin thin → wider stops {2–3.5} | 59.1 | .040 | 1.44 | 33.8 | 8.4 | Reverted (win < 60). |
| 12 | Win margin thin → objective `prop` | 61.4 | .036 | 1.44 | 32.4 | 13.2 | **Kept = final.** |

**What the learning shows:**
- The pass rate is gated by **frequency vs expectancy**. Cycle 7 (no session exit) has
  avg R +0.085 and 48% both-phase passes, but only 0.99 trades/day.
- Forcing about 2 trades/day (cycles 8–10) cut the expectancy by more than half. Session
  exits are the culprit: those trades average −0.17R with 35% wins.
- The user's frequency requirement costs this design real edge.

The walk-forward mostly picked 2.0/0.6 (28 of 97 weeks), 1.5/0.6 (18) and 2.0/0.7 (10).
On the final check it moved to the tighter 1.5/0.6.

**Looks at the final check (2025-11 → 2026-03): 2.** The first was the final run below.
The second was the controls and diagnosis on the full period. No change was made after
either look.

## 4. Results (current engine, `python -m prop_fx.backtest`)

| Period | net % | trades | t/day | win % | avg R | PF | max DD | boot both | boot P1 fail | hist both | hist P1 fail | breaches |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Dev ≤ 2025-10-31 | +32.6 | 614 | 1.44 | 61.4 | +0.036 | 1.13 | −17.4 | 32.4 | 13.2 | 38.0 | 11.3 | 0 |
| Dev, 2× spread | +10.4 | 614 | 1.44 | 59.9 | +0.011 | 1.04 | −31.6 | 20.1 | 22.0 | 35.2 | 38.0 | 0 |
| **Final check** 2025-11→2026-03 (`--trade-from`) | −10.7 | 168 | 1.34 | **57.7** | **−0.043** | 0.87 | −18.3 | 4.5 | 48.0 | 15.8 | 52.6 | 0 |
| Final check, 2× spread | −14.6 | 168 | 1.34 | 56.5 | −0.059 | 0.83 | −19.0 | 1.9 | 55.1 | 0.0 | 57.9 | 0 |
| **Full** 2024-05→2026-03 | +21.9 | 782 | 1.42 | 60.6 | +0.019 | 1.07 | −17.4 | **23.9** | 20.2 | 32.3 | 18.3 | 0 |
| Full, 2× spread | −4.2 | 782 | 1.42 | 59.2 | −0.004 | 0.99 | −31.6 | 13.5 | 31.4 | 26.9 | 40.9 | 0 |

**Long vs short:**

| Period | Long: n / win / avg R | Short: n / win / avg R |
|---|---|---|
| Dev | 373 / 64.1% / +0.049 | 241 / 57.3% / +0.015 |
| Final check | 105 / 61.0% / −0.019 | 63 / 52.4% / −0.084 |
| Full | 478 / 63.4% / +0.034 | 304 / 56.2% / −0.006 |

Shorts don't lose much in a +100% gold market, but they don't contribute either. The
long side carries the strategy.

**Edge vs geometry: same timing, geometry, walk-forward and risk.**

| Full period | win % | avg R | PF | boot both | P1 fail |
|---|---|---|---|---|---|
| **gold_prop** | 60.6 | **+0.019** | 1.07 | **23.9** | 20.2 |
| Coin-flip direction, same everything (8 seeds) | 56.4 ± 0.6 | −0.034 ± 0.016 (max −0.016) | 0.89 | 4.4 ± 2.1 (max 8.5) | 42.5 |
| Always long, same everything | 59.3 | +0.013 | 1.05 | 20.9 | 25.5 |
| random_gold (default, 1%) | 58.2 | −0.005 | 0.99 | 3.5 | 14.2 |
| random_gold at 1.5% / 3% daily stop | 58.1 | −0.005 | 0.98 | 12.8 | 32.9 |

On dev, coin flips give 56.2% win, −0.034R and 5.1% both; always-long gives 58.5%, +0.013R
and 24.6%.

The trend direction beats all 8 coin-flip seeds on win rate (+4pp), avg R (+0.05R) and
pass rate. It beats "always long" only modestly (+1.3pp win, +0.006R, +3pp pass), and
mainly through the short side's smaller losses. So most of the absolute edge is gold's
drift, timed a bit better.

**Win-rate / expectancy frontier.** This is from the static exploration on dev: original
engine, 1% risk, sessions 01/08/16, no vol filter, trend direction vs 6 coin-flip seeds.
`runs/gold_prop/fr0.txt` and `fr8.txt` have the rest.

| stop × target | win | avg R | boot both | coin-flip win / R / both |
|---|---|---|---|---|
| 2.0 ATR × 0.3R | 78.0 | +0.022 | 4.4 | 73.0 / −0.021 / 0.8 |
| 2.0 × 0.45 | 70.4 | +0.033 | 14.3 | 64.5 / −0.022 / 2.1 |
| 2.0 × 0.6 | 65.6 | +0.059 | 29.7 | 58.9 / −0.009 / 6.7 |
| 2.0 × 0.8 | 61.2 | +0.100 | 49.4 | 53.2 / −0.006 / 8.3 |
| 2.0 × 1.0 | 56.7 | +0.113 | 47.2 | 49.7 / −0.007 / 9.9 |
| 3.0 × 0.45 | 70.7 | +0.057 | 16.2 | 60.8 / −0.006 / 2.3 |

Shrinking the target buys win rate at the cost of expectancy and pass rate. The pass-rate
optimum is near a 0.8R target with a ~61% win rate, right at the user's floor. The signal
adds about 6–8pp of win rate over coin flips at every geometry.

## 5. Weaknesses (be my critic)

1. **It failed the final check.** Win 57.7%, avg R −0.043. Both sides lost from Nov 2025
   to Mar 2026, a high-volatility, two-way gold market (spikes and the Jan–Feb crash).
   Nov and Mar were the worst months (−0.18 and −0.21R a trade). That is exactly the
   regime the hold-out might bring.
2. **It fails 2× spread on the full period** (avg R −0.004). With 0.4–0.6R targets and
   session exits, costs are a large share of each trade.
3. **The edge is mostly drift.** It is only +0.006R better than always-long at the same
   timing. If Apr–Oct 2026 has no up-drift, expect something near the coin-flip line
   (avg R ≈ −0.03, both phases ≈ 5%).
4. **The frequency requirement hurts.** Session exits push trades/day to 1.42 but cut
   avg R from 0.085 to 0.036 on dev. Without the prior set, a hold-out file with no
   warm-up would be flat for 12 weeks. With it, those weeks trade a fixed set chosen
   in-sample.
5. **Snooping.** The hour change (08 → 10) and both vol thresholds came straight from dev
   diagnostics. About 75 distinct configurations, 113 logged runs (`variants.jsonl`).
   The cycle-1 and cycle-5 keep/revert calls would flip on the current engine (margins
   ≤ 2pp).
6. **Bootstrap optimism.** In-sample weeks are from a historic bull run. The historical
   (sequential) pass rates are similar, but over only 93 overlapping starts.
7. **Engine notes.** `trades_per_day` divides by every UTC date with data, including
   Sunday-evening stubs and walk-forward warm-up, so it understates true weekday
   frequency (my active-weekday rate is 1.68). The engine also allows only one position
   per symbol, so `max_positions > 1` cannot add XAUUSD frequency. Not bugs, but they
   shape every gold bot.

Files:
- Strategy: `prop_fx/strategies/gold_prop.py`
- Scratch: `tournament_gold/runs/gold_prop/` (harness `h.py`, `replay.py`, `controls.py`,
  `variants.jsonl`, per-run JSON and trades)
