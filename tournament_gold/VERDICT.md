# Gold Tournament: Final Verdict (hidden hold-out, 2026-04-01 → 2026-10-21)

The hold-out is about 30 trading weeks that no bot ever saw. Each strategy's walk-forward
optimiser kept re-tuning itself week by week through these weeks, using only past data,
exactly as it would live. Costs: $0.30 spread + $5/lot commission + slippage. Account:
FTMO 2-Step, $100k.
Scored by `judge_final.py` (judge only) using `prop_fx.backtest` and `prop_fx.challenge_timing`.

## Winner: **gold_trend**
It is the only strategy that met every hard requirement on the hold-out (win rate ≥ 60%,
≥ 1.2 trades/day, avg R > 0, no daily-limit breaches at normal risk). It also beat the
coin-flip benchmark by a wide margin.

## Normal risk (as each bot designed it)
| Strategy | Net | Win % | Trades/day | Avg R | PF | Max DD | Pass both (12 wk/phase) | Funded (no time limit) | Median days to funded | Hard requirements |
|---|---|---|---|---|---|---|---|---|---|---|
| **gold_trend** | **+7.1%** | **66.2** | 1.64 | +0.017 | 1.07 | −12.1% | **23.0%** | 51.4% | 91 | **all met** |
| gold_session | +12.3% | 57.5 | 1.65 | +0.030 | 1.12 | −11.6% | 32.9% | 59.1% | 73 | fails win rate (57.5%, same as coin flips) |
| gold_xasset | +6.0% | 74.4 | 0.78 | +0.030 | 1.15 | −4.6% | 4.0% | 59.6% | 191 | fails frequency (0.78/day) |
| gold_mean_reversion | −3.4% | 58.0 | 1.43 | −0.010 | 0.97 | −10.2% | 7.0% | 21.8% | 120 | loses money; fails win rate |
| gold_prop | −7.7% | 62.6 | 1.64 | −0.018 | 0.93 | −14.2% | 3.9% | 12.1% | 116 | loses money |
| random_gold (coin flips) | −1.7% | 57.5 | 1.34 | −0.008 | 0.98 | −10.3% | 1.2% | 12.6% | 206 | benchmark |

## Double risk (risk per trade × 2; daily stop unchanged)
| Strategy | Risk/trade | Net | Win % | Avg R | Max DD | Daily-limit breaches | Pass both (12 wk) | Phase 1 fail (12 wk) | Median days to funded |
|---|---|---|---|---|---|---|---|---|---|
| **gold_trend** | 3.0% | **+29.6%** | 66.8 | +0.039 | −13.7% | **1** ❌ | 46.6% | 35.6% | 25 |
| **gold_trend + 4.5% risk budget** | 3.0% | +27.7% | 66.9 | +0.037 | −12.3% | **0** ✅ | **54.0%** | **28.4%** | — |
| gold_session | 3.0% | +38.1% | 58.5 | +0.049 | −14.1% | 0 | 58.3% | 24.9% | 26 |
| gold_xasset | 3.0% | +20.9% | 75.7 | +0.065 | −7.3% | 0 | 44.7% | 7.3% | 77 |
| gold_mean_reversion | 3.0% | −3.0% | 56.9 | −0.004 | −25.2% | 0 | 27.0% | 49.2% | 31 |
| gold_prop | 3.0% | −8.2% | 60.7 | −0.012 | −23.3% | 0 | 26.4% | 51.1% | 31 |
| random_gold | 2.0% | −1.6% | 57.1 | −0.003 | −18.3% | 0 | 16.8% | 38.2% | 66 |

**The breach:** on 2026-09-04 gold_trend's first trade lost 2.05% (under its 2.5% daily stop),
so the second trade was allowed, lost its full 3%, and the day closed at −5.03%. That breaches
FTMO's limit. **Fix (now in the engine and the MT5 trader):** a daily *risk budget* skips any
trade whose risk, added to today's loss and the open risk, could push the day past 4.5%.
With it, gold_trend at double risk had 0 breaches and a *better* pass rate.

## Stress test: 2× spread at normal risk
- gold_trend: +2.7% net, +0.007R, pass 17.4%. Still positive, but thin.
- gold_session: +0.015R.
- gold_xasset: +0.026R.
- gold_mean_reversion and gold_prop: negative.

## Did the Round 3 revisions help? (normal risk, hold-out)
| Strategy | Round 2 avg R / pass | Round 3 avg R / pass |
|---|---|---|
| gold_trend | +0.017 / 23.0% | +0.017 / 23.0% (the warm-up change only affects the first 12 weeks, which the hold-out never reaches) |
| gold_session | −0.043 / 1.6% | **+0.030 / 32.9%** (the biggest improvement) |
| gold_mean_reversion | −0.015 / 3.9% | −0.010 / 7.0% |
| gold_xasset | +0.038 / 41.6% (at 2% risk, 1.18/day) | +0.030 / 4.0% (0.78/day: the revision cut frequency too far) |
| gold_prop | −0.028 / 3.8% | −0.018 / 3.9% |

## Honest assessment of the winner
- **The edge shrank by about 4× out of sample:** +0.067R in-sample → **+0.017R** on the hold-out.
  That is close to the "typical neighbour" estimate the critics made in Round 2 (+0.019R).
  Their hour-sensitivity attack was right.
- **Shorts carried it.** Shorts made +0.053R; longs made −0.024R. Monthly R:
  Apr +4.5, May +4.9, Jun −2.7, Jul +3.7, Aug +1.1, **Sep −4.2, Oct −2.5**. The last two months were losing.
- **The win rate held up** (66.2%), there were no breaches at normal risk, and it beat coin flips on
  every measure (funded 51% vs 13%; 12-week pass 23% vs 1.2%).
- **A 30-week hold-out is a small sample.** Treat these numbers as "plausibly positive, small
  edge", not as a reliable money machine.

## Normal vs double risk for an FTMO attempt (gold_trend)
- **Normal risk (1.5%):**
  - Slow: median 91 trading days to funded.
  - Only 23% pass within 12 weeks per phase; 51% eventually with no time limit.
  - Phase 1 fails 16% (12 wk) / 32% (no limit).
- **Double risk (3%) + 4.5% risk budget:**
  - 54% pass within 12 weeks per phase, about 25 trading days median to funded.
  - Phase 1 fails 28%.
  - **Faster and more likely to pass in a fixed window, but more attempts end in failure.**
    With a refundable fee and unlimited retries, double risk + risk budget is the better choice
    for passing. On a funded account, use normal risk.

## Recommended live configuration (MT5)
```
FX_STRATEGY=gold_trend
FX_RISK_MULT=2            # challenge phase; set 1 once funded
DAILY_RISK_BUDGET_PCT=4.5 # required at double risk
DAILY_GUARD_PCT=4.0
MAX_GUARD_PCT=9.0
PHASE_TARGET_PCT=10       # 5 for phase 2, 0 when funded
DRY_RUN=true              # then an FTMO free trial / demo before a paid challenge
```
