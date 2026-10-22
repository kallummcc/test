"""How long does a strategy take to pass or fail the FTMO challenge?

Runs a strategy once, then simulates thousands of challenges (weekly bootstrap)
and every historical start week, recording the number of trading days until
each phase is passed or failed. FTMO has no time limit, so phases are allowed
up to `--max-weeks` (default 52) before counting as "still running".

    python -m prop_fx.challenge_timing gold_trend random_gold --data-dir data/gold
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from . import engine, ftmo, strategies
from .backtest import load_dir


def _dist(days: list[int]) -> dict:
    if not days:
        return {"n": 0}
    a = np.array(days)
    return {"n": len(a), "median": float(np.median(a)), "p25": float(np.percentile(a, 25)),
            "p75": float(np.percentile(a, 75)), "p90": float(np.percentile(a, 90)),
            "min": int(a.min()), "max": int(a.max())}


def summarize(results: list[dict]) -> dict:
    n = len(results)
    p1 = [r["phase1"] for r in results]
    p1_pass = [r["phase1_days"] for r in results if r["phase1"] == "pass"]
    p1_fail = [r["phase1_days"] for r in results if r["phase1"] == "fail"]
    p2 = [r for r in results if r["phase1"] == "pass"]
    p2_pass = [r["phase2_days"] for r in p2 if r["phase2"] == "pass"]
    p2_fail = [r["phase2_days"] for r in p2 if r["phase2"] == "fail"]
    funded = [r["days"] for r in p2 if r["phase2"] == "pass"]
    failed_any = [r["days"] for r in results
                  if r["phase1"] == "fail" or (r["phase1"] == "pass" and r["phase2"] == "fail")]
    resolved = [(r["days"], r["phase1"] == "pass" and r["phase2"] == "pass")
                for r in results if r["phase1"] == "fail" or r["phase2"] in ("pass", "fail")]

    def within(limit, passed=None):
        hits = [1 for d, ok in resolved if d <= limit and (passed is None or ok == passed)]
        return round(100 * len(hits) / n, 1) if n else 0.0

    return {
        "challenges": n,
        "phase1": {"pass_pct": round(100 * p1.count("pass") / n, 1),
                   "fail_pct": round(100 * p1.count("fail") / n, 1),
                   "still_running_pct": round(100 * (n - p1.count("pass") - p1.count("fail")) / n, 1),
                   "days_to_pass": _dist(p1_pass), "days_to_fail": _dist(p1_fail)},
        "phase2_given_phase1": {"n": len(p2),
                                "pass_pct": round(100 * len(p2_pass) / len(p2), 1) if p2 else None,
                                "fail_pct": round(100 * len(p2_fail) / len(p2), 1) if p2 else None,
                                "days_to_pass": _dist(p2_pass), "days_to_fail": _dist(p2_fail)},
        "funded_pct": round(100 * len(funded) / n, 1),
        "days_to_funded": _dist(funded),
        "days_to_any_fail": _dist(failed_any),
        "resolved_within_days": {f"{d}d": {"funded": within(d, True), "failed": within(d, False)}
                                 for d in (20, 40, 60, 120, 250)},
    }


def analyse(name: str, data_dir: str, max_weeks: int, n_boot: int, seed: int = 7,
            risk_mult: float = 1.0, trade_from: str | None = None, end: str | None = None) -> dict:
    strat = strategies.scale_risk(strategies.load(name), risk_mult)
    bars = load_dir(data_dir, strat.interval, strat.pairs, end=end)
    tf = pd.Timestamp(trade_from, tz="UTC") if trade_from else None
    res = engine.run(strat, bars, trade_from=tf)
    if tf is not None:
        keep = res.times >= tf
        k0 = int(np.flatnonzero(keep)[0])
        base = res.realized[k0 - 1] if k0 else 0.0
        res = engine.EngineResult(res.times[keep], res.realized[keep] - base,
                                  res.floating_close[keep], res.floating_worst[keep],
                                  res.flat[keep], res.opened[keep], res.trades)
    rules = ftmo.Rules(max_weeks=max_weeks)
    weeks = ftmo.weeks_from(res, rules)
    rng = np.random.default_rng(seed)
    horizon = max_weeks * len(rules.phase_targets)
    boot = [ftmo.run_challenge([weeks[k] for k in rng.integers(0, len(weeks), horizon)], rules)
            for _ in range(n_boot)]
    hist = []
    for s in range(len(weeks)):
        r = ftmo.run_challenge(weeks[s:], rules)
        if r["phase1"] == "incomplete" or (r["phase1"] == "pass" and r["phase2"] == "incomplete"):
            continue
        hist.append(r)
    return {"strategy": name, "risk_pct": strat.risk_pct, "max_weeks_per_phase": max_weeks,
            "weeks_of_data": len(weeks),
            "bootstrap": summarize(boot), "historical": summarize(hist) if hist else None}


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("strategies", nargs="+")
    p.add_argument("--data-dir", default="data/gold")
    p.add_argument("--max-weeks", type=int, default=52)
    p.add_argument("--boot", type=int, default=2000)
    p.add_argument("--risk-mult", type=float, default=1.0)
    p.add_argument("--trade-from", default=None, help="earlier bars only warm up / train")
    p.add_argument("--end", default=None)
    args = p.parse_args(argv)
    for name in args.strategies:
        print(json.dumps(analyse(name, args.data_dir, args.max_weeks, args.boot,
                                 risk_mult=args.risk_mult, trade_from=args.trade_from,
                                 end=args.end)), flush=True)


if __name__ == "__main__":
    main()
