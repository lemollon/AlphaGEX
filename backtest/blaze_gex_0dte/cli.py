from __future__ import annotations
import argparse, csv, datetime as dt, os
from dataclasses import replace
from typing import List
from trading.helios.models import JoshuaConfig
from .runner import run_backtest
from .metrics import summarize, go_no_go

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BLAZE GEX-on-0DTE backtest grid sweep.")
    p.add_argument("--start", type=lambda s: dt.date.fromisoformat(s), default=dt.date(2023,1,3))
    p.add_argument("--end", type=lambda s: dt.date.fromisoformat(s), default=dt.date(2026,5,22))
    p.add_argument("--pts", type=int, nargs="+", default=[20, 30, 50])
    p.add_argument("--sls", type=int, nargs="+", default=[30, 50, 100])
    p.add_argument("--out", default="backtest/blaze_gex_0dte/output/results.csv")
    return p.parse_args(argv)

def build_grid(pts: List[int], sls: List[int]) -> List[JoshuaConfig]:
    base = JoshuaConfig()
    return [replace(base, profit_target_pct=float(pt), stop_loss_pct=float(sl))
            for pt in pts for sl in sls]

def main(argv=None) -> int:
    args = parse_args(argv)
    db_url = os.environ["DATABASE_URL"]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    rows = []
    for cfg in build_grid(args.pts, args.sls):
        outcomes = run_backtest(db_url, cfg, args.start, args.end)
        for setup, s in summarize(outcomes).items():
            verdict = go_no_go(s)
            rows.append({
                "pt": cfg.profit_target_pct, "sl": cfg.stop_loss_pct, "setup": setup,
                "trades": s.trades, "win_rate": round(s.win_rate, 4),
                "ev_per_contract": round(s.ev_per_contract, 4),
                "total_pnl": round(s.total_pnl, 2), "max_dd": round(s.max_drawdown, 2),
                "profit_factor": round(s.profit_factor, 3),
                "pnl_by_year": s.pnl_by_year, "verdict": verdict,
            })
            print(f"PT{cfg.profit_target_pct:.0f}/SL{cfg.stop_loss_pct:.0f} {setup}: "
                  f"n={s.trades} wr={s.win_rate:.1%} ev=${s.ev_per_contract:.2f} "
                  f"pf={s.profit_factor:.2f} {verdict}")
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["verdict"])
        w.writeheader(); w.writerows(rows)
    return 0
