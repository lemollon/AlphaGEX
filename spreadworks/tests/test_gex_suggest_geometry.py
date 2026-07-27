"""GEX Suggest must place strikes the way the live bots do.

Before this suite, gex-suggest anchored shorts on the raw GEX walls and sized
wings with a hardcoded $3/$5 constant. No bot does that — all 11 ship
`use_gex_walls: False` and derive placement from a swept multiple of the ATM
straddle. The concrete symptom was a double calendar at ~0.55 straddles, inside
the k=1.0 that TIDE's warehouse backtest showed was the loss engine.
"""
import pytest

from backend import routes

# Live SPY snapshot, 2026-07-27.
SPOT = 738.93
STRADDLE = 13.125
CALL_WALL = 746.3193
PUT_WALL = 731.5407
FLIP = 740.58
STRIKES = [float(s) for s in range(690, 790)]  # SPY $1 grid


def _legs(strategy, spec, gex=None, straddle=STRADDLE,
          call_wall=CALL_WALL, put_wall=PUT_WALL):
    return routes._build_legs_for_variant(
        strategy, spec, spot=SPOT, flip=FLIP,
        call_wall=call_wall, put_wall=put_wall,
        atm_straddle=straddle, regime="NEGATIVE",
        gex=gex if gex is not None else {"flip_point": FLIP},
        front_strikes_call=STRIKES, front_strikes_put=STRIKES,
        front_exp="2026-07-31", back_exp="2026-08-07", credit_exp="2026-07-28",
    )


def _spec(strategy, name="Standard"):
    return next(s for s in routes._variant_specs(strategy) if s["name"] == name)


def _straddles_from_spot(strike):
    return abs(strike - SPOT) / STRADDLE


# --- baselines track the live registry, not local constants ----------------

@pytest.mark.parametrize("strategy,bot,knob", [
    ("iron_condor", "FLOW", "sd_mult"),
    ("double_calendar", "TIDE", "strike_mult"),
    ("double_diagonal", "DRIFT", "sd_mult"),
    ("butterfly", "RIPPLE", "sd_mult"),
])
def test_baseline_resolves_from_owning_bot(strategy, bot, knob):
    mult, label = routes._baseline_strike_mult(strategy)
    assert mult > 0
    assert label.startswith(f"{bot}.{knob}")


def test_double_calendar_reads_strike_mult_not_sd_mult():
    """TIDE carries sd_mult 1.0 AND strike_mult 1.5. The DC builder uses
    strike_mult — reading sd_mult would silently reinstate the placement the
    backtest rejected."""
    mult, _ = routes._baseline_strike_mult("double_calendar")
    assert mult == 1.5


# --- placement geometry mirrors the bot modules ----------------------------

def test_double_calendar_strikes_clear_the_proven_bad_distance():
    legs = _legs("double_calendar", _spec("double_calendar"))
    put_sd = _straddles_from_spot(legs["put_strike"])
    call_sd = _straddles_from_spot(legs["call_strike"])
    # The old wall-anchored build produced 0.60 / 0.54 here.
    assert put_sd > 1.0 and call_sd > 1.0
    assert put_sd == pytest.approx(1.5, abs=0.1)
    assert call_sd == pytest.approx(1.5, abs=0.1)
    assert legs["put_strike"] < SPOT < legs["call_strike"]


def test_iron_condor_shorts_match_flow_formula():
    """iron_condor.py:123-124 — round(spot +/- sd_mult * atm_straddle)."""
    mult, _ = routes._baseline_strike_mult("iron_condor")
    legs = _legs("iron_condor", _spec("iron_condor"))
    assert legs["short_put_strike"] == round(SPOT - mult * STRADDLE)
    assert legs["short_call_strike"] == round(SPOT + mult * STRADDLE)


def test_iron_condor_longs_sit_one_spread_width_beyond():
    legs = _legs("iron_condor", _spec("iron_condor"))
    assert legs["short_put_strike"] - legs["long_put_strike"] == routes._IC_SPREAD_WIDTH
    assert legs["long_call_strike"] - legs["short_call_strike"] == routes._IC_SPREAD_WIDTH


def test_double_diagonal_longs_are_one_strike_beyond_shorts():
    """double_diagonal.py:103-104 with delta_skew 0."""
    legs = _legs("double_diagonal", _spec("double_diagonal"))
    assert legs["short_put_strike"] - legs["long_put_strike"] == 1
    assert legs["long_call_strike"] - legs["short_call_strike"] == 1


# --- the fly body: the "always at the money" complaint ---------------------

def test_fly_body_uses_gamma_weighted_magnet_midpoint():
    gex = {"flip_point": FLIP, "magnets": [
        {"strike": 745.0, "net_gamma": 1.0e9},
        {"strike": 735.0, "net_gamma": 0.8e9},
    ]}
    legs = _legs("butterfly", _spec("butterfly"), gex=gex)
    # (745*1.0 + 735*0.8) / 1.8 = 740.56 -> nearest listed strike 741
    assert legs["middle_strike"] == 741
    assert legs["middle_strike"] != round(SPOT)


def test_fly_body_falls_back_to_spot_without_magnets():
    """Documented degrade — and the reason gex_suggest emits a warning."""
    legs = _legs("butterfly", _spec("butterfly"), gex={"flip_point": FLIP})
    assert legs["middle_strike"] == pytest.approx(SPOT, abs=1.0)


def test_fly_body_prefers_magnets_over_flip():
    """Flip is the unreliable field; a magnet-derived body must win."""
    gex = {"flip_point": 700.0, "magnets": [{"strike": 750.0, "net_gamma": 1e9}]}
    legs = _legs("butterfly", _spec("butterfly"), gex=gex)
    assert legs["middle_strike"] == 750


def test_fly_wing_matches_ripple_haircut():
    """long_butterfly.py:240 — max(1, round(sd_mult * straddle * 0.85))."""
    mult, _ = routes._baseline_strike_mult("butterfly")
    legs = _legs("butterfly", _spec("butterfly"))
    expected = max(1, round(mult * STRADDLE * routes._FLY_WING_HAIRCUT))
    assert legs["upper_strike"] - legs["middle_strike"] == expected
    assert legs["middle_strike"] - legs["lower_strike"] == expected


# --- walls are context only ------------------------------------------------

@pytest.mark.parametrize("strategy", [
    "iron_condor", "double_calendar", "double_diagonal", "butterfly",
])
def test_gex_walls_cannot_move_strikes(strategy):
    """Every bot ships use_gex_walls: False. A garbage wall — like the $540
    flip that squashed the builder chart on 2026-07-27 — must not reach the
    strikes."""
    spec = _spec(strategy)
    sane = _legs(strategy, spec)
    garbage = _legs(strategy, spec, call_wall=9999.0, put_wall=1.0)
    assert sane == garbage


# --- variant tiers ---------------------------------------------------------

@pytest.mark.parametrize("strategy", [
    "iron_condor", "double_calendar", "double_diagonal",
    "butterfly", "iron_butterfly",
])
def test_variants_bracket_the_bot_baseline(strategy):
    specs = routes._variant_specs(strategy)
    by_name = {s["name"]: s["strike_mult"] for s in specs}
    baseline, _ = routes._baseline_strike_mult(strategy)
    assert by_name["Standard"] == pytest.approx(baseline)
    assert by_name["Conservative"] > by_name["Standard"] > by_name["Aggressive"]


@pytest.mark.parametrize("strategy", [
    "iron_condor", "double_calendar", "double_diagonal",
])
def test_conservative_is_farther_out_than_aggressive(strategy):
    cons = _legs(strategy, _spec(strategy, "Conservative"))
    aggr = _legs(strategy, _spec(strategy, "Aggressive"))
    key = "put_strike" if strategy == "double_calendar" else "short_put_strike"
    assert cons[key] < aggr[key]


# --- degrade paths ---------------------------------------------------------

def test_missing_straddle_still_yields_bracketing_strikes():
    legs = _legs("double_calendar", _spec("double_calendar"), straddle=None)
    assert legs["put_strike"] < SPOT < legs["call_strike"]


def test_strikes_snap_to_listed_chain_only():
    for strategy in ("iron_condor", "double_calendar", "double_diagonal"):
        legs = _legs(strategy, _spec(strategy))
        for key, value in legs.items():
            if key.endswith("_strike"):
                assert value in STRIKES, f"{strategy}.{key}={value} not listed"
