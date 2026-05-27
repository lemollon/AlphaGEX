from core.gex_profile_metrics import (
    calculate_positioning_pressure,
    calculate_structure_balance,
    aggregate_net_gamma_by_strike,
)


# ---------------------------------------------------------------------------
# calculate_positioning_pressure
# ---------------------------------------------------------------------------
def test_positioning_pressure_neutral_when_all_zero():
    out = calculate_positioning_pressure(
        volume_pressure=0.0, net_gex=0.0, skew_ratio=1.0, net_score=0
    )
    assert out["regime_label"] == "Neutral"
    assert out["pressure_score"] == 0
    assert out["call_vs_put_pressure"] == 0.0


def test_positioning_pressure_bullish_and_bounded():
    out = calculate_positioning_pressure(
        volume_pressure=0.5, net_gex=5e9, skew_ratio=1.4, net_score=3
    )
    assert out["regime_label"] == "Bullish"
    assert 0 <= out["pressure_score"] <= 100
    assert out["pressure_score"] > 0


def test_positioning_pressure_bearish_sign_from_net_score():
    out = calculate_positioning_pressure(
        volume_pressure=-0.4, net_gex=-2e9, skew_ratio=0.8, net_score=-2
    )
    assert out["regime_label"] == "Bearish"


def test_positioning_pressure_score_caps_at_100():
    out = calculate_positioning_pressure(
        volume_pressure=1.0, net_gex=1e12, skew_ratio=5.0, net_score=10
    )
    assert out["pressure_score"] == 100


# ---------------------------------------------------------------------------
# calculate_structure_balance
# ---------------------------------------------------------------------------
def test_structure_balance_balanced_when_symmetric():
    # equal gamma above and below spot within band -> ~0
    strikes = [
        {"strike": 95.0, "net_gamma": -10.0},
        {"strike": 105.0, "net_gamma": 10.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert out["label"] == "Balanced"
    assert abs(out["balance"]) < 0.15
    assert out["horizon_days"] == 7


def test_structure_balance_resistance_heavy():
    strikes = [
        {"strike": 95.0, "net_gamma": -1.0},
        {"strike": 105.0, "net_gamma": 30.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert out["balance"] > 0.15
    assert out["label"] == "Resistance-heavy"


def test_structure_balance_support_heavy():
    strikes = [
        {"strike": 95.0, "net_gamma": -30.0},
        {"strike": 105.0, "net_gamma": 1.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert out["balance"] < -0.15
    assert out["label"] == "Support-heavy"


def test_structure_balance_empty_is_balanced_zero():
    out = calculate_structure_balance([], spot_price=100.0, expected_move=10.0)
    assert out["balance"] == 0.0
    assert out["label"] == "Balanced"


def test_structure_balance_ignores_strikes_outside_band():
    # strike far above the +1sigma band is excluded
    strikes = [
        {"strike": 105.0, "net_gamma": 5.0},
        {"strike": 200.0, "net_gamma": 999.0},
        {"strike": 95.0, "net_gamma": -5.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert abs(out["balance"]) < 0.15  # the 200 strike is ignored


# ---------------------------------------------------------------------------
# aggregate_net_gamma_by_strike
# ---------------------------------------------------------------------------
def test_aggregate_sums_net_gamma_across_expirations():
    exp_a = [{"strike": 100.0, "net_gamma": 5.0}, {"strike": 101.0, "net_gamma": -2.0}]
    exp_b = [{"strike": 100.0, "net_gamma": 3.0}, {"strike": 102.0, "net_gamma": 7.0}]
    out = aggregate_net_gamma_by_strike([exp_a, exp_b])
    by_strike = {row["strike"]: row["net_gamma"] for row in out}
    assert by_strike[100.0] == 8.0
    assert by_strike[101.0] == -2.0
    assert by_strike[102.0] == 7.0


def test_aggregate_sorted_by_strike():
    out = aggregate_net_gamma_by_strike([
        [{"strike": 102.0, "net_gamma": 1.0}, {"strike": 100.0, "net_gamma": 1.0}],
    ])
    assert [r["strike"] for r in out] == [100.0, 102.0]


def test_aggregate_empty_returns_empty():
    assert aggregate_net_gamma_by_strike([]) == []
    assert aggregate_net_gamma_by_strike([[]]) == []
