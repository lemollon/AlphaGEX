"""Verify the line 1434 priority fix in _calculate_combined_signal.

XRP-shaped input (BALANCED leverage, LOW squeeze, BEARISH bias from L/S
extreme-long crowding) used to return RANGE_BOUND/MEDIUM because the
catch-all fired before the bias check. After the fix it should return
SHORT/LOW.

DOGE-shaped input is unchanged: it has MILD_IMBALANCE leverage so it
never hit the catch-all.

NEUTRAL-bias case stays RANGE_BOUND/MEDIUM.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.crypto_data_provider import (
    CryptoDataProvider,
    CryptoMarketSnapshot,
    LongShortRatio,
    CryptoGEX,
)


def make_snapshot(
    symbol,
    spot,
    funding_regime,
    leverage_regime,
    directional_bias,
    squeeze_risk,
    ls_ratio_value=None,
    has_synthetic_gex=False,
):
    snap = CryptoMarketSnapshot(
        symbol=symbol,
        spot_price=spot,
        timestamp=datetime.now(timezone.utc),
    )
    snap.funding_regime = funding_regime
    snap.leverage_regime = leverage_regime
    snap.directional_bias = directional_bias
    snap.squeeze_risk = squeeze_risk
    if ls_ratio_value is not None:
        snap.ls_ratio = LongShortRatio(
            symbol=symbol,
            ratio=ls_ratio_value,
            long_pct=ls_ratio_value / (1 + ls_ratio_value) * 100,
            short_pct=100 / (1 + ls_ratio_value),
            exchange="binance",
            timestamp=datetime.now(timezone.utc),
        )
    if has_synthetic_gex:
        snap.crypto_gex = CryptoGEX(
            symbol=symbol,
            net_gex=-1_000_000.0,
            flip_point=spot,
            call_gex=0.0,
            put_gex=-1_000_000.0,
            gamma_regime="NEGATIVE",
            max_pain=spot,
            strikes=[],
            timestamp=datetime.now(timezone.utc),
        )
    return snap


def run(label, snap, expected):
    p = CryptoDataProvider.__new__(CryptoDataProvider)
    p._snapshot_cache = {}
    sig, conf = p._calculate_combined_signal(snap)
    status = "PASS" if (sig, conf) == expected else "FAIL"
    print(f"  [{status}] {label}: got ({sig}, {conf}), expected {expected}")
    return (sig, conf) == expected


print("=" * 70)
print("Verifying _calculate_combined_signal priority fix")
print("=" * 70)

ok = []

ok.append(run(
    "XRP-now: bias=BEARISH, leverage=BALANCED, squeeze=LOW + synthetic GEX (max_pain==spot)",
    make_snapshot(
        symbol="XRP",
        spot=1.40745,
        funding_regime="BALANCED",
        leverage_regime="BALANCED",
        directional_bias="BEARISH",
        squeeze_risk="LOW",
        ls_ratio_value=2.37,
        has_synthetic_gex=True,
    ),
    expected=("SHORT", "LOW"),
))

ok.append(run(
    "DOGE-now: bias=BEARISH, leverage=MILD_IMBALANCE (unchanged path)",
    make_snapshot(
        symbol="DOGE",
        spot=0.11062,
        funding_regime="MILD_LONG_BIAS",
        leverage_regime="MILD_IMBALANCE",
        directional_bias="BEARISH",
        squeeze_risk="LOW",
        ls_ratio_value=2.15,
        has_synthetic_gex=True,
    ),
    expected=("SHORT", "LOW"),
))

ok.append(run(
    "Neutral case: bias=NEUTRAL, leverage=BALANCED, squeeze=LOW (still RANGE_BOUND/MEDIUM)",
    make_snapshot(
        symbol="XRP",
        spot=1.40745,
        funding_regime="BALANCED",
        leverage_regime="BALANCED",
        directional_bias="NEUTRAL",
        squeeze_risk="LOW",
        ls_ratio_value=1.0,
    ),
    expected=("RANGE_BOUND", "MEDIUM"),
))

ok.append(run(
    "Bullish bias case: bias=BULLISH, leverage=BALANCED, squeeze=LOW (now LONG/LOW)",
    make_snapshot(
        symbol="XRP",
        spot=1.40745,
        funding_regime="BALANCED",
        leverage_regime="BALANCED",
        directional_bias="BULLISH",
        squeeze_risk="LOW",
        ls_ratio_value=0.42,
    ),
    expected=("LONG", "LOW"),
))

print()
print("=" * 70)
if all(ok):
    print(f"ALL {len(ok)}/{len(ok)} CHECKS PASSED")
    sys.exit(0)
else:
    print(f"{sum(ok)}/{len(ok)} passed - fix is broken")
    sys.exit(1)
