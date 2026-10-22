# How long it takes to pass or fail the FTMO challenge (in-sample, gold)

Generated with `python -m prop_fx.challenge_timing <strategies> --data-dir data/gold`.
- **Simulation:** 2,000 bootstrap challenges per strategy, built from random in-sample
  weeks (Jun 2024 → Mar 2026). Each phase may run up to 52 weeks; FTMO itself has no time limit.
- **Day counts** are trading days (Mon–Fri). About 21 trading days make a month.
- **Rules:** FTMO 2-Step at $100k (+10%, then +5%; 5% daily loss limit; 10% maximum loss;
  at least 4 trading days per phase).
- **Caveat:** these are in-sample numbers. The hidden Apr–Oct 2026 hold-out hasn't been used yet.

| Strategy | Funded | Phase 1 fail | Days to funded: median (25–75%, 90%) | Days to a fail: median | Funded within 60d / 120d | Failed within 60d / 120d |
|---|---|---|---|---|---|---|
| gold_trend | **90.2%** | 5.3% | **78** (53–114, 159) | 77 | 28.8% / 70.6% | 3.5% / 7.7% |
| gold_trend, entries +1h (09/14) | 48.1% | 29.6% | 137 (90–199, 259) | 103 | 3.8% / 20.4% | 11.3% / 25.6% |
| gold_trend, entries −1h (07/12) | 18.4% | 64.3% | 104 (67–162, 206) | 73 | 3.9% / 11.0% | 32.5% / 58.1% |
| gold_mean_reversion | 52.1% | 30.7% | 105 (71–153, 211) | 79 | 9.3% / 31.4% | 16.6% / 31.1% |
| gold_prop | 50.0% | 34.9% | 86 (55–124, 185) | 62 | 14.7% / 36.6% | 23.6% / 39.5% |
| gold_xasset | 43.6% | 39.6% | 75 (49–113, 156) | 58 | 16.2% / 34.5% | 29.1% / 47.2% |
| gold_session | 42.0% | 40.2% | 93 (62–136, 190) | 67 | 10.2% / 28.2% | 25.4% / 43.6% |
| random_gold (no edge) | 21.2% | 49.2% | 161 (111–236, 290) | 111 | 0.9% / 6.2% | 14.8% / 33.1% |

**Phase by phase (median trading days):**

| Strategy | Phase 1: days to pass / to fail | Phase 2: pass rate after Phase 1 | Phase 2: days to pass / to fail |
|---|---|---|---|
| gold_trend | 49 / 54 | 95.5% | 21 / 42 |
| gold_xasset | 48 / 43 | 72.8% | 18 / 34 |
| gold_prop | 54 / 48 | 78.4% | 20 / 36 |
| gold_mean_reversion | 67 / 60 | 79.1% | 25 / 46 |
| gold_session | 58 / 51 | 72.1% | 23 / 40 |
| random_gold | 105 / 92 | 62.4% | 46 / 85 |

**Findings:**
- **Without a time limit, luck alone funds 21%.** A zero-edge strategy at this risk passes
  about 1 in 5 challenges, but it needs a median of about 161 trading days (7–8 months), and it
  fails about half the time first. "Did it pass" means little unless you also ask "how fast"
  and "how often it fails".
- **Funding takes months, not weeks.** Even the best case (gold_trend) takes a median
  of 78 trading days, about 3.7 months: about 49 days for Phase 1 and 21 for Phase 2.
  Almost nothing gets funded inside 20 trading days. At about 1–1.5% risk and 2 trades a
  day, a +10% target needs about 70–140 trades.
- **Failures arrive about as fast as passes** for every strategy except gold_trend. A strategy
  either drifts to +10% or bleeds to −10% over similar timescales; a quick daily-limit
  blow-up is rare because every bot uses a ≤3.5% daily stop.
- **gold_trend's lead depends on its exact entry hours.** Shift both entries one hour
  later and funding falls to 48% (137 days). Shift them one hour earlier and it falls to 18%,
  *worse than random*. The 90% headline is a best case picked in-sample; its real timing is
  probably between these rows. The hidden hold-out will show which.
