from trading.valor.research_profiles import (
    RESEARCH_PROFILES,
    fee_aware_breakeven_stop,
    round_trip_cost_points,
)


def test_contract_profiles_are_explicit():
    assert set(RESEARCH_PROFILES) == {"MES", "MNQ", "MGC", "NG", "RTY", "CL"}
    assert RESEARCH_PROFILES["MES"].use_gex_direction is False
    assert RESEARCH_PROFILES["MNQ"].use_gex_direction is True
    assert RESEARCH_PROFILES["MGC"].entry_mode == "CONTROL_CURRENT_GEX"
    assert RESEARCH_PROFILES["NG"].entry_mode == "GEX_REGIME_ONLY"
    assert RESEARCH_PROFILES["CL"].entry_mode == "QUARANTINED_RESEARCH"


def test_current_paper_cost_breakevens():
    assert round(round_trip_cost_points("MES"), 4) == 1.1000
    assert round(round_trip_cost_points("MNQ"), 4) == 2.0000
    assert round(round_trip_cost_points("MGC"), 4) == 0.5000
    assert round(round_trip_cost_points("NG"), 4) == 0.0320
    assert round(round_trip_cost_points("RTY"), 4) == 0.8000
    assert round(round_trip_cost_points("CL"), 4) == 0.0500


def test_fee_aware_breakeven_direction():
    assert fee_aware_breakeven_stop("MES", 7000.0, "LONG") == 7001.1
    assert fee_aware_breakeven_stop("MES", 7000.0, "SHORT") == 6998.9
