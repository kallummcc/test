"""Multi-pair forex backtest engine with prop-firm style fixed-dollar risk.

Execution model:
* Prices are treated as mid; buys pay +spread/2, sells receive -spread/2.
* Signals decided at a bar's close fill at the next bar's open.
* Stops / targets are checked intrabar on the bid (longs) / ask (shorts) side.
  A gap through a level fills at the open; if one bar touches both, the stop wins.
* Commission is charged per lot round turn.
* Position size = risk_pct of the INITIAL balance / stop distance, in 0.01 lots,
  capped by account leverage. Because size never depends on running equity, the
  P&L path does not depend on when a challenge starts, which lets `ftmo.py`
  evaluate many challenge start dates from a single run.
* Weekend: everything is closed by Friday 20:00 UTC and nothing opens after
  Friday 16:00 UTC (FTMO Standard accounts may not hold over the weekend).
  Any position left open across a data gap of more than 36h is closed at the last
  price before the gap.
* Overnight swap is not modelled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .instruments import PAIRS, notional_usd, pip_value_usd, usd_per_unit
from .strategies import Strategy

REQUIRED = {"entry", "exit", "stop_dist", "target_dist", "score"}
DAY_TZ = "Europe/Prague"  # FTMO resets the daily loss limit at midnight CE(S)T


@dataclass
class EngineConfig:
    initial_balance: float = 100_000.0
    commission_per_lot: float = 5.0  # USD per standard lot, round turn
    leverage: float = 100.0
    spread_mult: float = 1.0  # scale every pair's spread (stress test)
    slippage_pips: float = 0.1  # extra adverse slippage on market fills and stops


@dataclass
class Trade:
    pair: str
    side: int
    lots: float
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    pnl: float
    r_multiple: float
    reason: str


@dataclass
class EngineResult:
    times: pd.DatetimeIndex
    realized: np.ndarray  # cumulative closed P&L (USD) after each bar
    floating_close: np.ndarray  # open P&L at each bar's close
    floating_worst: np.ndarray  # open P&L at each bar's adverse extreme (conservative)
    flat: np.ndarray  # True when no position is open at the bar's close
    opened: np.ndarray  # number of positions opened in each bar
    trades: list[Trade] = field(default_factory=list)


@dataclass
class _Pos:
    side: int
    lots: float
    entry: float
    stop: float
    target: float
    risk_usd: float
    time: pd.Timestamp


def run(strategy: Strategy, bars: dict[str, pd.DataFrame], cfg: EngineConfig | None = None,
        trade_from: pd.Timestamp | None = None) -> EngineResult:
    cfg = cfg or EngineConfig()
    pairs = [p for p in bars if strategy.pairs is None or p in strategy.pairs]
    frames = {}
    for p in pairs:
        if bars[p].empty:
            continue
        out = strategy.prepare(bars[p], p)
        missing = REQUIRED - set(out.columns)
        if missing:
            raise ValueError(f"{strategy.name}.prepare() missing {missing}")
        frames[p] = out
    if not frames:
        raise ValueError("no data")
    pairs = list(frames)
    timeline = pd.DatetimeIndex(sorted(set().union(*(f.index for f in frames.values()))))

    def wide(col, fill=np.nan):
        return pd.DataFrame({p: frames[p][col] for p in pairs}).reindex(timeline).to_numpy(
            dtype=float, na_value=fill)

    O, H, L, C = wide("open"), wide("high"), wide("low"), wide("close")
    ENTRY, EXIT = wide("entry", 0.0), wide("exit", 0.0)
    SD, TD, SCORE = wide("stop_dist"), wide("target_dist"), wide("score")
    specs = [PAIRS[p] for p in pairs]
    half = np.array([s.spread_pips * cfg.spread_mult / 2 + cfg.slippage_pips for s in specs])
    half *= np.array([s.pip for s in specs])
    last = {p: np.nan for p in pairs}  # latest close per pair, for USD conversion

    n = len(timeline)
    realized = np.zeros(n)
    f_close = np.zeros(n)
    f_worst = np.zeros(n)
    flat = np.ones(n, dtype=bool)
    opened = np.zeros(n, dtype=int)
    trades: list[Trade] = []
    positions: dict[int, _Pos] = {}
    pending: dict[int, tuple] = {}  # j -> ("open", side, stop_dist, target_dist) | ("close", reason)
    cum = 0.0
    risk_usd = strategy.risk_pct / 100 * cfg.initial_balance
    day_keys = timeline.tz_convert(DAY_TZ).normalize()
    day_start_cum = 0.0
    halted_day = None

    def prices():
        return {p: v for p, v in last.items() if not math.isnan(v)}

    def pnl_usd(j, pos, price):
        quote_ccy = specs[j].quote
        return (pos.side * (price - pos.entry) * pos.lots * specs[j].contract
                * usd_per_unit(quote_ccy, prices()))

    def close(j, price, when, reason):
        nonlocal cum
        pos = positions.pop(j)
        pnl = pnl_usd(j, pos, price) - cfg.commission_per_lot * pos.lots
        cum += pnl
        trades.append(Trade(pairs[j], pos.side, pos.lots, str(pos.time), str(when),
                            round(pos.entry, 6), round(price, 6), round(pnl, 2),
                            round(pnl / pos.risk_usd, 3) if pos.risk_usd else 0.0, reason))

    for i, ts in enumerate(timeline):
        # Data gap (weekend or missing data): close at the last known price.
        if i and positions and (ts - timeline[i - 1]) > pd.Timedelta(hours=36):
            for j in list(positions):
                side = positions[j].side
                close(j, C[i - 1, j] - side * half[j], timeline[i - 1], "data gap")
            pending.clear()
        if i == 0 or day_keys[i] != day_keys[i - 1]:
            day_start_cum = cum

        # 1) fills at the open
        for j, order in list(pending.items()):
            o = O[i, j]
            if math.isnan(o):
                continue
            del pending[j]
            if order[0] == "close":
                if j in positions:
                    close(j, o - positions[j].side * half[j], ts, order[1])
                continue
            _, side, sdist, tdist = order
            if j in positions:
                if positions[j].side == side:
                    continue
                close(j, o - positions[j].side * half[j], ts, "reverse")
            if len(positions) >= strategy.max_positions:
                continue
            entry = o + side * half[j]
            px = prices()
            pv = pip_value_usd(specs[j], px)
            stop_pips = sdist / specs[j].pip
            lots = math.floor(risk_usd / (stop_pips * pv) * 100) / 100 if stop_pips > 0 else 0
            equity = cfg.initial_balance + cum
            used = sum(notional_usd(specs[k], p.lots, px) for k, p in positions.items())
            leverage = min(cfg.leverage, specs[j].leverage)
            max_lots = (equity * leverage - used) / notional_usd(specs[j], 1.0, px)
            lots = min(lots, math.floor(max_lots * 100) / 100)
            if lots < 0.01:
                continue
            target = entry + side * tdist if np.isfinite(tdist) and tdist > 0 else (
                math.inf if side > 0 else -math.inf)
            positions[j] = _Pos(side, lots, entry, entry - side * sdist, target,
                                stop_pips * pv * lots, ts)
            opened[i] += 1

        # 2) intrabar stops / targets (bid for longs, ask for shorts)
        for j, pos in list(positions.items()):
            if math.isnan(O[i, j]):
                continue
            o = O[i, j] - pos.side * half[j]  # exit-side open
            hi, lo = H[i, j] - pos.side * half[j], L[i, j] - pos.side * half[j]
            if pos.side > 0:
                if lo <= pos.stop:
                    close(j, min(o, pos.stop), ts, "stop")
                elif hi >= pos.target:
                    close(j, max(o, pos.target), ts, "target")
            else:
                if hi >= pos.stop:
                    close(j, max(o, pos.stop), ts, "stop")
                elif lo <= pos.target:
                    close(j, min(o, pos.target), ts, "target")

        for j, p in enumerate(pairs):
            if not math.isnan(C[i, j]):
                last[p] = C[i, j]

        # 3) mark to market
        fc = fw = 0.0
        for j, pos in positions.items():
            c = C[i, j] if not math.isnan(C[i, j]) else last[pairs[j]]
            fc += pnl_usd(j, pos, c - pos.side * half[j])
            adverse = (L[i, j] if pos.side > 0 else H[i, j])
            adverse = c if math.isnan(adverse) else adverse
            fw += pnl_usd(j, pos, adverse - pos.side * half[j])
        realized[i], f_close[i], f_worst[i] = cum, fc, min(fw, fc)
        flat[i] = not positions

        # 4) decisions at the close -> next open
        nxt = ts + pd.Timedelta(hours=1)
        friday_cutoff = nxt.weekday() == 4 and nxt.hour >= 20 or nxt.weekday() >= 5
        if friday_cutoff:
            for j in positions:
                pending[j] = ("close", "weekend")
            continue
        no_new = (nxt.weekday() == 4 and nxt.hour >= 16) or (
            trade_from is not None and ts < trade_from)
        day_loss = cum + fc - day_start_cum
        if strategy.daily_stop_pct and day_loss <= -strategy.daily_stop_pct / 100 * cfg.initial_balance:
            if halted_day != day_keys[i]:
                halted_day = day_keys[i]
                for j in positions:
                    pending[j] = ("close", "daily stop")
        if halted_day == day_keys[i]:
            continue
        for j, pos in positions.items():
            if EXIT[i, j] == 1 and j not in pending:
                pending[j] = ("close", "strategy exit")
        if no_new:
            continue
        cands = [j for j in range(len(pairs))
                 if ENTRY[i, j] != 0 and not math.isnan(C[i, j]) and SD[i, j] > 0
                 and not (j in positions and positions[j].side == ENTRY[i, j])]
        cands.sort(key=lambda j: -(SCORE[i, j] if not math.isnan(SCORE[i, j]) else -math.inf))
        slots = strategy.max_positions - len(positions) - sum(
            1 for v in pending.values() if v[0] == "open")
        for j in cands:
            reversing = j in positions
            if not reversing and slots <= 0:
                break
            pending[j] = ("open", int(ENTRY[i, j]), SD[i, j], TD[i, j])
            if not reversing:
                slots -= 1

    for j in list(positions):
        close(j, last[pairs[j]] - positions[j].side * half[j], timeline[-1], "end of data")
    realized[-1], f_close[-1], f_worst[-1], flat[-1] = cum, 0.0, min(f_worst[-1], 0.0), True
    return EngineResult(timeline, realized, f_close, f_worst, flat, opened, trades)
