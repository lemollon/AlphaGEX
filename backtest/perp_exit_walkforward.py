"""Walk-forward PROOF that reshaping ETH/DOGE/SHIB-FUT exits toward SOL's
balanced ride-the-winner profile improves out-of-sample profitability.

Reuses the verified replay engine in backtest/perp_exit_optimizer.py
(load_entries / load_price_stream / evaluate / ExitConfig). The ONLY thing
added here is an honest train/test split so we are NOT re-overfitting:

  TRAIN  = entries opened BEFORE the split date (what the live configs were
           tuned on)  -> used to SELECT candidate configs
  TEST   = entries opened ON/AFTER the split date (the forward period that
           actually played out)  -> used only to REPORT, never to select

Same real entries, same real price paths; only the exit rules differ.

Run:
    PYTHONIOENCODING=utf-8 python -m backtest.perp_exit_walkforward
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

from backtest.perp_exit_optimizer import (
    ExitConfig, CURRENT_DEFAULTS, _grid, load_entries, load_price_stream, evaluate,
)
from database_adapter import get_connection

SPLIT = datetime(2026, 5, 9, tzinfo=timezone.utc)

# Live configs actually running now (from autonomous_config 2026-05-29).
LIVE = {
    "AGAPE_ETH_PERP":     ExitConfig(0.3, 0.05, 2.5, 2.0, 5.0, 24, True, 1.5, 0.3),
    "AGAPE_DOGE_PERP":    ExitConfig(0.8, 0.5,  2.5, 3.0, 5.0,  8, False, 0.0, 0.0),
    "AGAPE_SHIB_FUTURES": ExitConfig(0.5, 0.1,  1.0, 3.0, 5.0, 24, False, 0.0, 0.0),
    "AGAPE_SOL_PERP":     ExitConfig(1.5, 0.75, 0.0, 3.0, 5.0, 16, True, 1.5, 0.3),
}

BOTS = {
    "AGAPE_ETH_PERP":     ("agape_eth_perp",     "eth_price"),
    "AGAPE_DOGE_PERP":    ("agape_doge_perp",    "doge_price"),
    "AGAPE_SHIB_FUTURES": ("agape_shib_futures", "shib_price"),
    "AGAPE_SOL_PERP":     ("agape_sol_perp",     "sol_price"),  # control: already balanced
}


def payoff(m):
    return (m["avg_win"] / m["avg_loss"]) if m["avg_loss"] else 0.0


def candidate_configs():
    """Balanced (SOL-style) grid: high-ish activation, wider trail, NO hard PT
    (ride winners), sane max loss. Deliberately the OPPOSITE of the tight-trail
    archetype. SAR both on and off."""
    acts   = [0.8, 1.0, 1.5]
    trails = [0.5, 0.75, 1.0, 1.25]
    pts    = [0.0]              # ride winners — the SOL lever
    maxls  = [2.0, 3.0]
    holds  = [16, 24]
    sars   = [(False, 0.0, 0.0), (True, 1.5, 0.3)]
    out = []
    for a, tr, pt, ml, h, (se, st, sm) in itertools.product(acts, trails, pts, maxls, holds, sars):
        if tr >= a:   # trail must be tighter than activation or it never arms sensibly
            continue
        out.append(ExitConfig(a, tr, pt, ml, 5.0, h, se, st, sm))
    return out


def tighten_configs():
    """Opposite lever from candidate_configs(): KEEP ETH's working tight trail
    (it banks small mean-reversion wins) but TIGHTEN the loss side to shrink the
    ~-1.5% avg loss. Vary sar_trigger + max_loss down; keep activation/trail tight."""
    acts   = [0.3, 0.5]
    trails = [0.05, 0.1, 0.15]
    pts    = [1.0, 1.5, 2.5]
    maxls  = [0.5, 0.75, 1.0, 1.5]
    holds  = [12, 24]
    # SAR off, or SAR on with a TIGHTER trigger than the current 1.5
    sars   = [(False, 0.0, 0.0), (True, 0.5, 0.3), (True, 0.75, 0.3), (True, 1.0, 0.3)]
    out = []
    for a, tr, pt, ml, h, (se, st, sm) in itertools.product(acts, trails, pts, maxls, holds, sars):
        out.append(ExitConfig(a, tr, pt, ml, 5.0, h, se, st, sm))
    return out


def fmt(label, m):
    return (f"  {label:<26} pnl=${m['total_pnl']:>9.2f}  n={m['trades_evaluated']:>4}  "
            f"WR={m['win_rate_pct']:>5.1f}%  win=${m['avg_win']:>7.2f}  loss=${m['avg_loss']:>7.2f}  "
            f"payoff={payoff(m):>4.2f}  PF={m['profit_factor']}")


def cfgstr(c):
    return (f"act={c.activation_pct} trail={c.trail_pct} pt={c.profit_target_pct} "
            f"maxL={c.max_loss_pct} hold={c.max_hold_hours}h sar={c.sar_enabled}")


def run_bot(name, table, price_col):
    conn = get_connection()
    try:
        entries = load_entries(conn, table)
        ts_arr, px_arr = load_price_stream(conn, table, price_col)
    finally:
        conn.close()

    train = [e for e in entries if e["open_time"] and e["open_time"] < SPLIT]
    test  = [e for e in entries if e["open_time"] and e["open_time"] >= SPLIT]

    print(f"\n{'='*100}\n{name}   train={len(train)} entries (<{SPLIT.date()})   test={len(test)} entries (>={SPLIT.date()})\n{'='*100}")
    if not test:
        print("  no out-of-sample entries — skip"); return

    live = LIVE[name]
    live_train = evaluate(train, ts_arr, px_arr, live)
    live_test  = evaluate(test,  ts_arr, px_arr, live)
    print(f"\n  LIVE CONFIG ({cfgstr(live)}):")
    print(fmt("  in-sample (train)",  live_train))
    print(fmt("  OUT-OF-SAMPLE (test)", live_test))

    # Selection happens on TRAIN ONLY.
    cands = candidate_configs()
    scored = []
    for c in cands:
        m = evaluate(train, ts_arr, px_arr, c)
        if m["trades_evaluated"] < max(20, 0.4 * len(train)):
            continue
        scored.append((c, m))
    if not scored:
        print("  no candidate had enough train trades"); return

    # Naive argmax train P&L (shows re-optimization can still overfit).
    naive = max(scored, key=lambda x: x[1]["total_pnl"])
    # Robust balanced pick: positive train pnl, payoff>=0.8, then best profit factor.
    balanced_pool = [s for s in scored if s[1]["total_pnl"] > 0 and payoff(s[1]) >= 0.8]
    balanced = max(balanced_pool, key=lambda x: x[1]["profit_factor"]) if balanced_pool else naive

    for tag, (c, mtr) in [("TRAIN-ARGMAX-PnL", naive), ("BALANCED pick (payoff>=0.8)", balanced)]:
        mte = evaluate(test, ts_arr, px_arr, c)
        print(f"\n  {tag}: {cfgstr(c)}")
        print(fmt("  in-sample (train)", mtr))
        print(fmt("  OUT-OF-SAMPLE (test)", mte))

    # --- TIGHTEN-STOPS pool (keep tight trail, cut the loss side) --- ETH only
    tscored = []
    for c in (tighten_configs() if name == "AGAPE_ETH_PERP" else []):
        m = evaluate(train, ts_arr, px_arr, c)
        if m["trades_evaluated"] < max(20, 0.4 * len(train)):
            continue
        tscored.append((c, m))
    if tscored:
        t_argmax = max(tscored, key=lambda x: x[1]["total_pnl"])
        ct, mtr = t_argmax
        mte = evaluate(test, ts_arr, px_arr, ct)
        print(f"\n  TIGHTEN-STOPS best-on-train: {cfgstr(ct)}")
        print(fmt("  in-sample (train)", mtr))
        print(fmt("  OUT-OF-SAMPLE (test)", mte))
        # also report the tighten config with best OUT-OF-SAMPLE (diagnostic only — peeks at test)
        t_best_oos = max(tscored, key=lambda x: evaluate(test, ts_arr, px_arr, x[0])["total_pnl"])
        cb = t_best_oos[0]; mbe = evaluate(test, ts_arr, px_arr, cb)
        print(f"  [diag] best tighten cfg ON TEST (peeks): {cfgstr(cb)}  -> test pnl=${mbe['total_pnl']:.2f} WR={mbe['win_rate_pct']}% payoff={payoff(mbe):.2f}")

    # Verdict line
    bal_test = evaluate(test, ts_arr, px_arr, balanced[0])
    delta = bal_test["total_pnl"] - live_test["total_pnl"]
    print(f"\n  >>> OUT-OF-SAMPLE verdict: balanced ${bal_test['total_pnl']:.2f} vs live ${live_test['total_pnl']:.2f}  "
          f"=> delta ${delta:+.2f}  ({'BETTER' if delta>0 else 'NOT better'})")


if __name__ == "__main__":
    for name, (table, price_col) in BOTS.items():
        try:
            run_bot(name, table, price_col)
        except Exception as e:
            import traceback; print(f"\n{name} FAILED: {e}"); traceback.print_exc()
    print("\nDONE")
