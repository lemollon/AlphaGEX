from scripts.valor_mes_v31_edge_map import (
    FEE,
    TICK,
    launch_if_enabled,
    net_dollars,
    select_non_overlapping,
    time_bucket,
)


def test_time_bucket_boundaries_are_explicit_and_gap_free():
    assert time_bucket(524) is None
    assert time_bucket(525) == "opening_morning"
    assert time_bucket(629) == "opening_morning"
    assert time_bucket(630) == "late_morning"
    assert time_bucket(689) == "late_morning"
    assert time_bucket(690) == "midday"
    assert time_bucket(749) == "midday"
    assert time_bucket(750) == "afternoon"
    assert time_bucket(839) == "afternoon"
    assert time_bucket(840) == "late_session"
    assert time_bucket(899) == "late_session"
    assert time_bucket(900) is None


def test_cost_cases_charge_both_sides_and_fee_once():
    gross = net_dollars(TICK, 1, None, 0.0)
    assert gross == 1.25
    assert net_dollars(TICK, 1, 0, FEE) == -1.75
    assert net_dollars(TICK, 1, 1, FEE) == -4.25
    assert net_dollars(TICK, -1, 1, FEE) == -6.75


def test_non_overlap_allows_next_entry_only_after_prior_exit_minute():
    boundaries = [
        {"entry_index": 10, "exit_index": 24},
        {"entry_index": 20, "exit_index": 34},
        {"entry_index": 25, "exit_index": 39},
    ]
    selected = select_non_overlapping(boundaries)
    assert [(r["entry_index"], r["exit_index"]) for r in selected] == [(10, 24), (25, 39)]


def test_v31_never_inherits_a_legacy_autorun_flag(monkeypatch):
    monkeypatch.delenv("VALOR_MES_V31_AUTORUN", raising=False)
    monkeypatch.setenv("VALOR_MES_CHOPGUARD_V10_AUTORUN", "true")
    assert launch_if_enabled() is False
