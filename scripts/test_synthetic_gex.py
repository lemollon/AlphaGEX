"""Smoke test for the synthetic crypto GEX fallback.

Verifies that _build_synthetic_crypto_gex produces sensible output for
coins without a Deribit options market (AVAX, XRP, DOGE, SHIB).

Doesn't hit live APIs — uses fabricated liquidation/L-S data so the test
is deterministic.
"""

from datetime import datetime
from data.crypto_data_provider import (
    CryptoDataProvider, LiquidationCluster, LongShortRatio,
)


def _make_liq(price: float, long_usd: float, short_usd: float) -> LiquidationCluster:
    return LiquidationCluster(
        price_level=price,
        long_liquidation_usd=long_usd,
        short_liquidation_usd=short_usd,
        net_liquidation_usd=short_usd - long_usd,
        intensity="MEDIUM",
        distance_pct=0.0,
    )


def main() -> int:
    provider = CryptoDataProvider()

    # Scenario 1: AVAX, long-heavy, liquidation clusters around spot
    print("=" * 70)
    print("Scenario 1: AVAX long-heavy (LS=1.4)")
    print("=" * 70)
    avax_liqs = [
        _make_liq(33.0, long_usd=5_000_000, short_usd=1_000_000),
        _make_liq(37.0, long_usd=500_000, short_usd=8_000_000),
        _make_liq(34.5, long_usd=2_000_000, short_usd=1_500_000),
    ]
    avax_ls = LongShortRatio(
        symbol="AVAX",
        long_pct=58.3, short_pct=41.7, ratio=1.4,
        exchange="Binance",
        timestamp=datetime.now(),
    )
    synth = provider._build_synthetic_crypto_gex(
        symbol="AVAX", spot=35.0, liquidations=avax_liqs, ls_ratio=avax_ls,
    )
    assert synth is not None, "AVAX synthesis returned None"
    assert synth.source == "synthetic_perp_oi", f"wrong source: {synth.source}"
    assert synth.gamma_regime == "NEGATIVE", f"expected NEGATIVE for long-heavy, got {synth.gamma_regime}"
    assert synth.net_gex < 0, f"expected negative net_gex for NEGATIVE regime, got {synth.net_gex}"
    assert synth.max_pain is not None and 33.0 <= synth.max_pain <= 37.0, \
        f"max_pain out of bounds: {synth.max_pain}"
    print(f"  source={synth.source}")
    print(f"  regime={synth.gamma_regime}")
    print(f"  net_gex={synth.net_gex:,.0f}")
    print(f"  max_pain=${synth.max_pain:.2f}  (spot=$35.00)")
    print(f"  pseudo-strikes={len(synth.strikes)}")
    print("  PASS")

    # Scenario 2: XRP, short-heavy → squeeze setup
    print()
    print("=" * 70)
    print("Scenario 2: XRP short-heavy (LS=0.6)")
    print("=" * 70)
    xrp_liqs = [
        _make_liq(2.30, long_usd=200_000, short_usd=8_000_000),
        _make_liq(2.50, long_usd=100_000, short_usd=4_000_000),
    ]
    xrp_ls = LongShortRatio(
        symbol="XRP",
        long_pct=37.5, short_pct=62.5, ratio=0.6,
        exchange="Binance",
        timestamp=datetime.now(),
    )
    synth = provider._build_synthetic_crypto_gex(
        symbol="XRP", spot=2.20, liquidations=xrp_liqs, ls_ratio=xrp_ls,
    )
    assert synth is not None, "XRP synthesis returned None"
    assert synth.gamma_regime == "POSITIVE", f"expected POSITIVE for short-heavy, got {synth.gamma_regime}"
    assert synth.net_gex > 0, f"expected positive net_gex for POSITIVE regime, got {synth.net_gex}"
    print(f"  source={synth.source}")
    print(f"  regime={synth.gamma_regime}")
    print(f"  net_gex={synth.net_gex:,.0f}")
    print(f"  max_pain=${synth.max_pain:.4f}  (spot=$2.20)")
    print("  PASS")

    # Scenario 3: balanced LS, should produce NEUTRAL regime
    print()
    print("=" * 70)
    print("Scenario 3: SHIB balanced LS (1.05)")
    print("=" * 70)
    shib_liqs = [_make_liq(0.0000020, long_usd=300_000, short_usd=350_000)]
    shib_ls = LongShortRatio(
        symbol="SHIB", long_pct=51.2, short_pct=48.8, ratio=1.05,
        exchange="Binance",
        timestamp=datetime.now(),
    )
    synth = provider._build_synthetic_crypto_gex(
        symbol="SHIB", spot=0.0000019, liquidations=shib_liqs, ls_ratio=shib_ls,
    )
    assert synth is not None, "SHIB synthesis returned None"
    assert synth.gamma_regime == "NEUTRAL", f"expected NEUTRAL for balanced, got {synth.gamma_regime}"
    assert synth.net_gex == 0.0, f"expected zero net_gex for NEUTRAL, got {synth.net_gex}"
    print(f"  source={synth.source}")
    print(f"  regime={synth.gamma_regime}")
    print(f"  net_gex={synth.net_gex:,.0f}")
    print("  PASS")

    # Scenario 4: no liquidations and no L/S — should return None
    print()
    print("=" * 70)
    print("Scenario 4: no data → None")
    print("=" * 70)
    synth = provider._build_synthetic_crypto_gex(
        symbol="DOGE", spot=0.10, liquidations=[], ls_ratio=None,
    )
    assert synth is None, f"expected None when no data, got {synth}"
    print("  returned None  PASS")

    # Scenario 5: liquidations only (no L/S) — should still produce max_pain
    print()
    print("=" * 70)
    print("Scenario 5: liquidations only (no L/S)")
    print("=" * 70)
    doge_liqs = [_make_liq(0.105, long_usd=2_000_000, short_usd=500_000)]
    synth = provider._build_synthetic_crypto_gex(
        symbol="DOGE", spot=0.10, liquidations=doge_liqs, ls_ratio=None,
    )
    assert synth is not None, "DOGE synthesis returned None despite liquidations"
    assert synth.gamma_regime == "NEUTRAL", "no L/S should mean NEUTRAL regime"
    assert synth.max_pain is not None and synth.max_pain > 0, "max_pain should still derive from liqs"
    print(f"  regime={synth.gamma_regime} (no L/S → NEUTRAL)")
    print(f"  max_pain=${synth.max_pain:.5f}  (from liquidations)")
    print("  PASS")

    print()
    print("All scenarios PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
