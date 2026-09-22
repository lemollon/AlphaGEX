from trading.shared.perp_realism import (
    MarginTier,
    PerpVenueRules,
    estimate_margin,
    funding_cashflow,
    net_realized_pnl,
    simulate_taker_fill,
)


def _rules():
    return PerpVenueRules(
        symbol="BTC-PERP",
        default_leverage=10.0,
        max_leverage=50.0,
        taker_fee_bps=6.0,
        maker_fee_bps=2.0,
        funding_interval_hours=8.0,
        fallback_maintenance_margin_rate=0.005,
        impact_bps=2.0,
        fallback_slippage_bps=10.0,
        tiers=(
            MarginTier(max_notional=10000, maintenance_margin_rate=0.005),
            MarginTier(max_notional=20000, maintenance_margin_rate=0.01),
        ),
    )


def test_taker_fill_uses_executable_side():
    fill = simulate_taker_fill(
        "long", 1.0, _rules(), bid=99.0, ask=101.0, mark=100.0
    )
    assert fill.used_executable_quote is True
    assert fill.fill_price > 101.0
    assert fill.fee_usd > 0


def test_fallback_fill_is_adverse():
    long_fill = simulate_taker_fill("long", 1.0, _rules(), fallback_price=100.0)
    short_fill = simulate_taker_fill("short", 1.0, _rules(), fallback_price=100.0)
    assert long_fill.fill_price > 100.0
    assert short_fill.fill_price < 100.0


def test_margin_burden_moves_with_mark_price():
    low = estimate_margin(
        side="long",
        entry_price=100.0,
        mark_price=100.0,
        quantity=100.0,
        leverage=10.0,
        rules=_rules(),
    )
    high = estimate_margin(
        side="long",
        entry_price=100.0,
        mark_price=150.0,
        quantity=100.0,
        leverage=10.0,
        rules=_rules(),
    )
    assert high.initial_margin > low.initial_margin
    assert high.maintenance_margin > low.maintenance_margin


def test_mark_move_can_cross_risk_tier():
    below = estimate_margin(
        side="long",
        entry_price=100.0,
        mark_price=99.0,
        quantity=100.0,
        leverage=10.0,
        rules=_rules(),
    )
    above = estimate_margin(
        side="long",
        entry_price=100.0,
        mark_price=101.0,
        quantity=100.0,
        leverage=10.0,
        rules=_rules(),
    )
    assert below.maintenance_margin_rate == 0.005
    assert above.maintenance_margin_rate == 0.01


def test_positive_funding_long_pays_short_receives():
    assert funding_cashflow(notional=10000, side="long", funding_rate=0.0001) < 0
    assert funding_cashflow(notional=10000, side="short", funding_rate=0.0001) > 0


def test_net_pnl_deducts_fees_and_applies_funding():
    pnl = net_realized_pnl(
        side="long",
        quantity=1.0,
        entry_fill_price=100.0,
        exit_fill_price=110.0,
        entry_fee_usd=1.0,
        exit_fee_usd=1.0,
        funding_cashflow_usd=-0.5,
    )
    assert pnl == 7.5
