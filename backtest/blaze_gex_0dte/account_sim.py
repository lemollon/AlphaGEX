"""Account-level simulation over the ACTUAL full-board PT20/SL100 trade sequence.

Each trade deploys `risk_frac` of the current balance as the spread debit; since
SL=100 means a trade can lose the full debit, the per-trade account multiplier is
(1 + risk_frac * realized_pct/100). Compounds chronologically over the real trades
(both setups, one-position-at-a-time as the dispatcher produced them) and reports
ending balance + max drawdown + whether the account was effectively wiped.
"""
from __future__ import annotations
import datetime as dt
import os
from dataclasses import replace
from trading.helios.models import JoshuaConfig
from .fullboard import run_fullboard_backtest


def simulate(outcomes, starting: float = 5000.0, risk_frac: float = 0.25):
    ocs = sorted(outcomes, key=lambda o: (o.trade_date, o.entry_minute))
    bal = starting
    peak = starting
    max_dd = 0.0
    min_bal = starting
    for o in ocs:
        bal *= 1.0 + risk_frac * (o.realized_pct / 100.0)
        if bal < min_bal:
            min_bal = bal
        if bal > peak:
            peak = bal
        dd = (bal - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
    return {
        "trades": len(ocs),
        "ending": bal,
        "max_dd_pct": max_dd * 100.0,
        "min_bal": min_bal,
        "mult": bal / starting if starting else 0.0,
    }


def simulate_capped(outcomes, starting: float = 5000.0, risk_frac: float = 0.0425,
                    max_contracts: int = 50):
    """Realistic sizing: deploy `risk_frac` of balance as debit, but never more
    than `max_contracts` (a capacity ceiling on 0DTE SPY ATM spreads). Once the
    cap binds, growth turns linear instead of exponential. Real $ P&L per trade."""
    ocs = sorted(outcomes, key=lambda o: (o.trade_date, o.entry_minute))
    bal = starting
    peak = starting
    max_dd = 0.0
    min_bal = starting
    capped = 0
    for o in ocs:
        cost = o.debit * 100.0
        if cost <= 0:
            continue
        target = int((risk_frac * bal) / cost)
        contracts = max(1, min(target, max_contracts))
        if target > max_contracts:
            capped += 1
        bal += (o.realized_pct / 100.0) * cost * contracts
        if bal <= 0:
            bal = 0.0
            break
        min_bal = min(min_bal, bal)
        peak = max(peak, bal)
        dd = (bal - peak) / peak
        max_dd = min(max_dd, dd)
    yrs = 2.92  # 2023-01-03 -> 2025-12-05
    cagr = (bal / starting) ** (1 / yrs) - 1 if bal > 0 else -1.0
    return {"ending": bal, "max_dd_pct": max_dd * 100, "min_bal": min_bal,
            "cagr_pct": cagr * 100, "capped_pct": 100.0 * capped / max(1, len(ocs))}


def main():
    db = os.environ["DATABASE_URL"]
    orat = os.environ["ORAT_DATABASE_URL"]
    cfg = replace(JoshuaConfig(), profit_target_pct=20.0, stop_loss_pct=100.0)
    start, end = dt.date(2023, 1, 3), dt.date(2025, 12, 5)
    outcomes = run_fullboard_backtest(db, orat, cfg, start, end, dte=0)
    print(f"PT20/SL100 full-board trades: {len(outcomes)} (2023-01-03 -> 2025-12-05)")
    print("--- Uncapped fixed-fractional (compounding illusion) ---")
    for f in (0.02, 0.05, 0.10, 0.25):
        r = simulate(outcomes, 5000.0, f)
        print(f"risk={f:>4.0%}/trade: $5,000 -> ${r['ending']:>14,.2e}  maxDD={r['max_dd_pct']:>5.0f}%")
    print("--- Realistic: 4.25%/trade, capped at N contracts (capacity ceiling) ---")
    for cap in (10, 25, 50, 100):
        r = simulate_capped(outcomes, 5000.0, 0.0425, cap)
        print(f"cap={cap:>4} ct: $5,000 -> ${r['ending']:>12,.0f}  CAGR={r['cagr_pct']:>5.0f}%/yr  "
              f"maxDD={r['max_dd_pct']:>4.0f}%  trough=${r['min_bal']:,.0f}  capped_trades={r['capped_pct']:.0f}%")


if __name__ == "__main__":
    main()
