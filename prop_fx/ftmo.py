"""FTMO 2-Step challenge simulator.

Rules modelled (FTMO 2-Step, 2026, per FTMO's public rules summaries):
* Phase 1 target +10%, Phase 2 target +5% of the initial balance, reached on
  closed balance with no open positions.
* Maximum Daily Loss 5% of the initial balance, measured against the balance at
  the start of the day (midnight Europe/Prague), including floating losses.
* Maximum Loss 10% of the initial balance (equity, including floating losses).
* At least 4 trading days per phase.
* No time limit at FTMO; we cap each phase at `max_weeks` so a strategy that
  never gets there counts as a timeout rather than a pass.

Because the engine sizes every trade from the initial balance, each trading
week (flat at both ends — positions are closed before the weekend) is an exact,
start-independent block of P&L. Two estimates are produced:
* historical: a challenge started at the beginning of every week in the data;
* bootstrap: Monte Carlo challenges built from randomly drawn weeks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import DAY_TZ, EngineResult


@dataclass
class Rules:
    initial_balance: float = 100_000.0
    phase_targets: tuple[float, ...] = (10.0, 5.0)
    max_daily_loss_pct: float = 5.0
    max_loss_pct: float = 10.0
    min_trading_days: int = 4
    max_weeks: int = 12


@dataclass
class Week:
    bal: np.ndarray  # closed P&L relative to the week start, after each bar
    worst: np.ndarray  # bal + worst floating P&L in the bar
    flat: np.ndarray
    daily_fail: int  # first bar index breaching the daily limit, or -1
    new_trading_day: np.ndarray  # 1 on the first bar of a day with a new position opened
    end_bal: float
    day_no: np.ndarray | None = None  # 0-based market-day index within the week, per bar

    @property
    def n_days(self) -> int:
        return 5  # Mon-Fri; Sunday-evening bars count as Friday (they are always flat)


def weeks_from(res: EngineResult, rules: Rules) -> list[Week]:
    times = res.times
    week_key = (times.tz_convert("UTC") - pd.to_timedelta(times.tz_convert("UTC").weekday, "D")
                ).normalize()
    day_key = times.tz_convert(DAY_TZ).normalize()
    out = []
    limit = -rules.max_daily_loss_pct / 100 * rules.initial_balance
    starts = np.flatnonzero(np.r_[True, week_key[1:] != week_key[:-1]])
    ends = np.r_[starts[1:], len(times)]
    for s, e in zip(starts, ends):
        base = res.realized[s - 1] if s else 0.0
        bal = res.realized[s:e] - base
        worst = bal + res.floating_worst[s:e]
        days = day_key[s:e]
        first_of_day = np.r_[True, days[1:] != days[:-1]]
        day_start_bal = np.maximum.accumulate(np.where(first_of_day, np.arange(e - s), 0))
        prev_bal = np.r_[0.0, bal[:-1]]
        dsb = prev_bal[day_start_bal]
        breach = np.flatnonzero(worst - dsb < limit)
        opened = pd.Series(res.opened[s:e] > 0)
        per_day = opened.astype(int).groupby(np.asarray(days)).cumsum()
        opened_days = (opened & (per_day == 1)).astype(int).to_numpy()
        out.append(Week(bal, worst, res.flat[s:e].copy(), int(breach[0]) if len(breach) else -1,
                        opened_days, float(bal[-1]),
                        np.clip(np.asarray(times[s:e].tz_convert("UTC").weekday), 0, 4)))
    return out


def run_phase(weeks: list[Week], target_pct: float, rules: Rules
              ) -> tuple[str, int, float, int]:
    """Run one phase over a sequence of weeks.

    Returns (outcome, weeks_used, final_pnl, market_days_used).
    """
    b0 = rules.initial_balance
    target = target_pct / 100 * b0
    floor = -rules.max_loss_pct / 100 * b0
    base, tdays, mdays = 0.0, 0, 0
    for k, w in enumerate(weeks[: rules.max_weeks]):
        n = len(w.bal)
        max_fail = np.flatnonzero(base + w.worst < floor)
        fail_at = min([x for x in (w.daily_fail, max_fail[0] if len(max_fail) else -1) if x >= 0],
                      default=n)
        days = tdays + np.cumsum(w.new_trading_day)
        ok = np.flatnonzero(w.flat & (base + w.bal >= target) & (days >= rules.min_trading_days))
        pass_at = ok[0] if len(ok) else n
        if pass_at < fail_at:
            return "pass", k + 1, base + w.bal[pass_at], mdays + _day(w, pass_at)
        if fail_at < n:
            return "fail", k + 1, base + w.worst[fail_at], mdays + _day(w, fail_at)
        base += w.end_bal
        tdays = int(days[-1]) if n else tdays
        mdays += w.n_days
    outcome = "timeout" if len(weeks) >= rules.max_weeks else "incomplete"
    return outcome, min(len(weeks), rules.max_weeks), base, mdays


def _day(w: Week, bar: int) -> int:
    return int(w.day_no[bar]) + 1 if w.day_no is not None else 5


def run_challenge(weeks_iter, rules: Rules) -> dict:
    """weeks_iter yields weeks; phase 2 continues from the week after phase 1 passed."""
    seq = list(weeks_iter)
    result = {"phase1": None, "phase2": None, "weeks": 0, "days": 0}
    pos = 0
    for phase, target in enumerate(rules.phase_targets, start=1):
        outcome, used, _, mdays = run_phase(seq[pos:], target, rules)
        result[f"phase{phase}"] = outcome
        result[f"phase{phase}_days"] = mdays
        result["weeks"] += used
        result["days"] += mdays
        pos += used
        if outcome != "pass":
            break
    return result


def _rates(results: list[dict]) -> dict:
    n = len(results)
    if not n:
        return {"n": 0}
    p1 = [r["phase1"] for r in results]
    both = [r["phase1"] == "pass" and r["phase2"] == "pass" for r in results]
    weeks_to_pass = [r["weeks"] for r, b in zip(results, both) if b]
    return {
        "n": n,
        "pass_both_pct": round(100 * sum(both) / n, 1),
        "phase1_pass_pct": round(100 * p1.count("pass") / n, 1),
        "phase1_fail_pct": round(100 * p1.count("fail") / n, 1),
        "phase1_timeout_pct": round(100 * (p1.count("timeout") + p1.count("incomplete")) / n, 1),
        "median_weeks_to_pass_both": float(np.median(weeks_to_pass)) if weeks_to_pass else None,
    }


def evaluate(res: EngineResult, rules: Rules | None = None, n_boot: int = 2000,
             seed: int = 7) -> dict:
    rules = rules or Rules()
    weeks = weeks_from(res, rules)
    horizon = rules.max_weeks * len(rules.phase_targets)
    # Historical: start at every week that leaves enough data for both phases.
    hist = []
    for s in range(len(weeks)):
        r = run_challenge(weeks[s:], rules)
        if "incomplete" in (r["phase1"], r["phase2"]):
            continue  # ran out of data before an outcome, not a real result
        hist.append(r)
    rng = np.random.default_rng(seed)
    boot = [run_challenge((weeks[k] for k in rng.integers(0, len(weeks), horizon)), rules)
            for _ in range(n_boot)] if weeks else []
    weekly = np.array([w.end_bal for w in weeks]) / rules.initial_balance * 100
    return {
        "weeks": len(weeks),
        "avg_week_pct": round(float(weekly.mean()), 3) if len(weekly) else None,
        "worst_week_pct": round(float(weekly.min()), 2) if len(weekly) else None,
        "daily_limit_breach_weeks": sum(w.daily_fail >= 0 for w in weeks),
        "historical": _rates(hist),
        "bootstrap": _rates(boot),
    }
