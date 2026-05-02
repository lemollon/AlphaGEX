#!/usr/bin/env python3
"""End-to-end signal verification for all 5 perp tickers.

Run on Render after deploy from project root:
    python scripts/verify_perp_signals.py
"""
import os
import sys
import time

# Ensure project root is importable when run from /tmp or as a script
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.crypto_data_provider import get_crypto_data_provider

p = get_crypto_data_provider()
print(f"{'SYM':5s} {'SIGNAL':12s} {'CONF':6s} {'FUNDING':22s} {'OI_USD':>10s} {'TAKER_BUY%':>11s}  notes")
print("-" * 100)
for sym in ["BTC", "ETH", "XRP", "DOGE", "SHIB"]:
    # Each snapshot does ~5 CoinGlass calls (funding, OI, taker, L/S, liq).
    # Pause between symbols to stay under the 30 req/min rate limit.
    s = p.get_snapshot(sym)
    if not s:
        print(f"{sym:5s} (no snapshot)")
        continue
    oi_str = f"${s.oi_snapshot.total_usd/1e6:.0f}M" if s.oi_snapshot else "NONE"
    tv_str = f"{s.taker_volume.buy_ratio*100:.1f}%" if s.taker_volume else "NONE"
    notes = []
    if s.crypto_gex:
        notes.append(f"GEX={s.crypto_gex.gamma_regime}")
    if s.ls_ratio:
        notes.append(f"L/S={s.ls_ratio.ratio:.2f}")
    if s.liquidation_clusters:
        notes.append(f"liq={len(s.liquidation_clusters)}")
    note_str = " ".join(notes)
    print(f"{sym:5s} {s.combined_signal:12s} {s.combined_confidence:6s} {s.funding_regime:22s} {oi_str:>10s} {tv_str:>11s}  {note_str}")
    # Client now self-paces at 2.5s/call; brief 2s gap between symbols
    # is enough cushion. Total runtime ~70s for all 5 perps.
    time.sleep(2)
