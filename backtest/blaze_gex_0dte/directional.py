"""Directional (BINARY) win-rate backtest for the BLAZE/JOSHUA GEX setups.

WHY THIS EXISTS
---------------
The 2026-05-24 full-board backtest validated these setups as OPTION debit verticals
(PT/SL on the spread mark, PF~3.1). But a Kalshi index binary pays on ONE thing only:
did the index close on the right side? So the only number that ports to Kalshi is the
**directional win-rate** P(close moves in the signal's direction). This script measures
exactly that, on the SAME reconstructed 0DTE GEX stream and the SAME real setups
(`trading.helios.signals.dispatch`) the option backtest used — so it inherits the proven
firing logic and just swaps the P&L definition for the binary outcome.

For each trading day in [start, end]:
  1. load_day -> reconstruct.build_snapshots  (per-minute GexSnapshot: spot, walls, flip,
     net_gex, regime, sigma_1d_band_width).
  2. Walk snapshots in time order, feeding FlipBuffer + dispatch(...) with a DailyState,
     exactly like the live scanner. Each fire -> (setup, direction, entry_spot, regime).
  3. close_spot = last snapshot's spot. A fire WINS if:
       direction 'call' (up)   and close_spot > entry_spot, OR
       direction 'put'  (down) and close_spot < entry_spot.
     (This is precisely the payout of an at-entry-spot binary held to close — the KXINXU
     near-the-money YES/NO and a good proxy for KXINXDUD up/down.)

DEDUP: by default ONE fire per setup per day (the FIRST), so each row is an independent
daily observation — the clean basis for a win-rate confidence interval. Pass
--all-fires to instead keep every fire up to the daily cap (autocorrelated; reported
separately, never mixed into the CI verdict).

OUTPUT: per-setup win-rate with a 95% Wilson interval, per-year and per-regime splits,
the unconditional up-rate baseline, and a GO/NO-GO verdict. The bar for a tradeable
binary edge: the Wilson 95% LOWER bound must clear breakeven. A Kalshi binary priced at
~0.50 with the ~0.017 maker / ~0.035 taker fee breaks even near 0.52-0.54, so we use
--breakeven (default 0.53). GO only if lower_bound > breakeven AND the edge holds (no
losing YEAR) — mirroring the option backtest's "positive every year" rule.

RUN (needs prod DATABASE_URL; reconstruction reads helios_options_intraday + _oi):
  DATABASE_URL=... python -m backtest.blaze_gex_0dte.directional --start 2023-01-03 --end 2026-05-22

Nothing here trades, writes, or deploys. Read-only on the DB.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os
from collections import defaultdict
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from backtest.blaze_gex_0dte.loader import load_day

# --- compat shim ----------------------------------------------------------- #
# The wall math (bs.py: bs_gamma/implied_vol/derive_spot_from_parity) was PROMOTED
# from `backtest/intraday_walls/` to `quant/`, but reconstruct.py (and fullboard.py)
# still import the old, now-deleted path -> the harness is un-runnable on branches
# where that move landed. Alias the old module name to quant.bs in sys.modules BEFORE
# importing reconstruct, so this script runs on any branch without editing their files.
# quant.bs exports the identical functions with compatible signatures.
import sys as _sys
import types as _types

try:  # use the real module if it still exists (e.g. on `main`)
    import backtest.intraday_walls.bs  # noqa: F401
except ModuleNotFoundError:
    import quant.bs as _qbs  # promoted location

    _pkg = _types.ModuleType("backtest.intraday_walls")
    _pkg.__path__ = []  # mark as a package so submodule import resolves
    _sys.modules.setdefault("backtest.intraday_walls", _pkg)
    _sys.modules["backtest.intraday_walls.bs"] = _qbs

from backtest.blaze_gex_0dte.reconstruct import build_snapshots  # noqa: E402
from trading.helios.models import DailyState, JoshuaConfig, SetupType
from trading.helios.setups.flip_cross import FlipBuffer
from trading.helios.signals import dispatch


# --------------------------------------------------------------------------- #
# One directional observation.
# --------------------------------------------------------------------------- #
class Fire:
    __slots__ = ("trade_date", "setup", "direction", "entry_spot", "close_spot",
                 "regime", "entry_minute")

    def __init__(self, trade_date, setup, direction, entry_spot, close_spot, regime, entry_minute):
        self.trade_date = trade_date
        self.setup = setup            # 'wall_fade' | 'wall_break' | 'flip_cross'
        self.direction = direction    # 'call' (up) | 'put' (down)
        self.entry_spot = entry_spot
        self.close_spot = close_spot
        self.regime = regime
        self.entry_minute = entry_minute

    @property
    def win(self) -> Optional[bool]:
        if self.close_spot == self.entry_spot:
            return None  # exact tie -> push, excluded
        up = self.close_spot > self.entry_spot
        return up if self.direction == "call" else (not up)


def _bump(state: DailyState, setup: SetupType) -> DailyState:
    """Increment the per-setup count on the frozen DailyState so caps + dispatch advance."""
    if setup == SetupType.WALL_FADE:
        return replace(state, wall_fade_count=state.wall_fade_count + 1, wall_fade_fired=True)
    if setup == SetupType.WALL_BREAK:
        return replace(state, wall_break_count=state.wall_break_count + 1, wall_break_fired=True)
    return replace(state, flip_cross_count=state.flip_cross_count + 1, flip_cross_fired=True)


def replay_day_directional(day, config: JoshuaConfig, *, first_only: bool) -> List[Fire]:
    """Drive one DayChain through the REAL setups; record directional fires."""
    snaps = build_snapshots(day)
    if len(snaps) < 2:
        return []
    snaps = sorted(snaps, key=lambda s: s.snapshot_at)
    close_spot = snaps[-1].spot
    state = DailyState(trade_date=day.trade_date)
    buffer = FlipBuffer(max_minutes=config.flip_buffer_minutes)
    seen_setups = set()
    out: List[Fire] = []
    for i, snap in enumerate(snaps):
        buffer.add(snap)
        action = dispatch(snap, state=state, buffer=buffer, config=config)
        if action is None:
            continue
        setup_val = action.setup.value if hasattr(action.setup, "value") else str(action.setup)
        if first_only and setup_val in seen_setups:
            # already have this setup's daily observation; still advance count so the cap
            # eventually silences it, but don't record a second (autocorrelated) row.
            state = _bump(state, action.setup)
            continue
        out.append(Fire(
            trade_date=day.trade_date, setup=setup_val, direction=action.direction,
            entry_spot=snap.spot, close_spot=close_spot,
            regime=getattr(snap, "regime", "") or "", entry_minute=i,
        ))
        seen_setups.add(setup_val)
        state = _bump(state, action.setup)
    return out


# --------------------------------------------------------------------------- #
# Stats.
# --------------------------------------------------------------------------- #
def wilson(wins: int, n: int, z: float = 1.96) -> Tuple[float, float, float]:
    """(point, lo, hi) Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def _split(fires: List[Fire], keyfn) -> Dict[str, Tuple[int, int]]:
    d: Dict[str, Tuple[int, int]] = defaultdict(lambda: (0, 0))
    for f in fires:
        w = f.win
        if w is None:
            continue
        n, k = d[keyfn(f)]
        d[keyfn(f)] = (n + 1, k + (1 if w else 0))
    return d


def regime_bucket(r: str) -> str:
    r = (r or "").upper()
    if "NEG" in r:
        return "NEGATIVE"
    if "POS" in r:
        return "POSITIVE"
    return "NEUTRAL"


# --------------------------------------------------------------------------- #
# Report.
# --------------------------------------------------------------------------- #
def report(all_fires: List[Fire], up_rate: float, breakeven: float, first_only: bool) -> None:
    mode = "first-fire-per-setup-per-day (independent obs)" if first_only else "ALL fires (autocorrelated)"
    print("\n" + "=" * 78)
    print(f"DIRECTIONAL (BINARY) WIN-RATE — BLAZE/JOSHUA setups   [{mode}]")
    print("=" * 78)
    print(f"unconditional up-rate baseline (close>entry over all fires): {up_rate:.1%}")
    print(f"breakeven bar for a ~0.50-priced binary after fee:          {breakeven:.1%}")
    print(f"GO rule: Wilson-95% LOWER bound > breakeven AND no losing year.\n")

    by_setup = defaultdict(list)
    for f in all_fires:
        by_setup[f.setup].append(f)

    order = ["wall_fade", "wall_break", "flip_cross"]
    for setup in order + [s for s in by_setup if s not in order]:
        fires = by_setup.get(setup, [])
        usable = [f for f in fires if f.win is not None]
        n = len(usable)
        if n == 0:
            print(f"-- {setup:11s}: 0 fires (never triggered in this window)\n")
            continue
        wins = sum(1 for f in usable if f.win)
        p, lo, hi = wilson(wins, n)
        days = len({f.trade_date for f in usable})
        verdict_n = "PASS" if lo > breakeven else "fail"
        print(f"-- {setup:11s}: n={n}  days={days}  win-rate={p:.1%}  "
              f"95%CI=[{lo:.1%}, {hi:.1%}]  lower>{breakeven:.0%}? {verdict_n}")

        # per year
        yr = _split(usable, lambda f: str(f.trade_date.year))
        ystr = "   ".join(
            f"{y}:{(k/nn):.0%}({k}/{nn})" for y, (nn, k) in sorted(yr.items())
        )
        losing_year = any((k / nn) <= 0.50 for nn, k in yr.values())
        print(f"     by year:   {ystr}")
        # per regime
        rg = _split(usable, lambda f: regime_bucket(f.regime))
        rstr = "   ".join(
            f"{r}:{(k/nn):.0%}({k}/{nn})" for r, (nn, k) in sorted(rg.items())
        )
        print(f"     by regime: {rstr}")

        go = (lo > breakeven) and not losing_year and n >= 30
        flag = "GO" if go else "NO-GO"
        why = []
        if lo <= breakeven:
            why.append("CI lower <= breakeven")
        if losing_year:
            why.append("a losing year")
        if n < 30:
            why.append(f"n<30 ({n})")
        print(f"     VERDICT: {flag}" + (f"  ({'; '.join(why)})" if why else "") + "\n")

    # headline
    print("-" * 78)
    print("If a setup is GO, set vertex.DEFAULT_WIN_PROB[setup] to its win-rate point estimate")
    print("(use the CI LOWER bound for conservative sizing). NO-GO setups stay at their priors")
    print("and do NOT go live. Remember: wall_break/flip_cross need NEGATIVE-gamma days to even")
    print("fire — check their 'days=' is non-trivial before trusting the number.")
    print("=" * 78)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BLAZE/JOSHUA directional (binary) win-rate backtest.")
    p.add_argument("--start", type=lambda s: dt.date.fromisoformat(s), default=dt.date(2023, 1, 3))
    p.add_argument("--end", type=lambda s: dt.date.fromisoformat(s), default=dt.date(2026, 5, 22))
    p.add_argument("--breakeven", type=float, default=0.53,
                   help="win-rate a ~0.50-priced binary must beat after fee (default 0.53)")
    p.add_argument("--cap", type=int, default=3, help="max_trades_per_setup_per_day (firing logic)")
    p.add_argument("--all-fires", action="store_true",
                   help="keep every fire (autocorrelated) instead of first-per-setup-per-day")
    return p.parse_args(argv)


def main(argv=None) -> int:
    import psycopg2

    args = parse_args(argv)
    first_only = not args.all_fires
    config = JoshuaConfig(max_trades_per_setup_per_day=args.cap)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: set DATABASE_URL (prod Postgres) before running.")
        return 2

    conn = psycopg2.connect(db_url)
    all_fires: List[Fire] = []
    up_n = up_k = 0
    n_days = 0
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT trade_date FROM helios_options_intraday "
            "WHERE expiration_date = trade_date AND trade_date BETWEEN %s AND %s "
            "ORDER BY trade_date",
            (args.start, args.end),
        )
        dates = [r[0] for r in cur.fetchall()]
        cur.close()
        print(f"reconstructing {len(dates)} 0DTE sessions {args.start}..{args.end} ...")
        for i, d in enumerate(dates):
            day = load_day(conn, d)
            if day is None:
                continue
            fires = replay_day_directional(day, config, first_only=first_only)
            all_fires.extend(fires)
            for f in fires:
                if f.win is None:
                    continue
                up_n += 1
                up_k += 1 if f.close_spot > f.entry_spot else 0
            n_days += 1
            if (i + 1) % 50 == 0:
                print(f"  ...{i + 1}/{len(dates)} days, {len(all_fires)} fires so far")
    finally:
        conn.close()

    up_rate = (up_k / up_n) if up_n else 0.0
    print(f"\ndone: {n_days} sessions reconstructed, {len(all_fires)} total fires.")
    report(all_fires, up_rate, args.breakeven, first_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
