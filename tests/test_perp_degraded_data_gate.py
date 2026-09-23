"""Degraded-data (CoinGlass outage) paper-trading gate.

When CoinGlass is down, CryptoDataProvider forces funding_regime to
"UNKNOWN" but the combined signal can still carry a LOW-confidence
LONG/SHORT call derived from Deribit GEX or price momentum (see
data/crypto_data_provider.py _calculate_combined_signal). Each perp
bot's own min_confidence gate (default MEDIUM) then WAITs on that call.

allow_degraded_data_trades (default True) lets the PAPER path trade
that LOW-confidence call instead of sitting out entirely, without
inflating the confidence label, and tags the reasoning with
DEGRADED_NO_COINGLASS so those scans/positions can be excluded from
live-data stats. It must never relax the gate in LIVE mode.
"""
import importlib

import pytest


CASES = [
    ("trading.agape_btc_perp.models", "AgapeBtcPerpConfig", "trading.agape_btc_perp.signals", "AgapeBtcPerpSignalGenerator"),
    ("trading.agape_eth_perp.models", "AgapeEthPerpConfig", "trading.agape_eth_perp.signals", "AgapeEthPerpSignalGenerator"),
    ("trading.agape_sol_perp.models", "AgapeSolPerpConfig", "trading.agape_sol_perp.signals", "AgapeSolPerpSignalGenerator"),
    ("trading.agape_avax_perp.models", "AgapeAvaxPerpConfig", "trading.agape_avax_perp.signals", "AgapeAvaxPerpSignalGenerator"),
    ("trading.agape_xrp_perp.models", "AgapeXrpPerpConfig", "trading.agape_xrp_perp.signals", "AgapeXrpPerpSignalGenerator"),
    ("trading.agape_doge_perp.models", "AgapeDogePerpConfig", "trading.agape_doge_perp.signals", "AgapeDogePerpSignalGenerator"),
]

DEGRADED_MARKET_DATA = {
    "spot_price": 100.0,
    "funding_rate": 0.0,
    "funding_regime": "UNKNOWN",  # CoinGlass dead
    "squeeze_risk": "LOW",
    "ls_ratio": 1.0,
    "ls_bias": "NEUTRAL",
    "crypto_gex": 0.0,
    "crypto_gex_regime": "NEUTRAL",
    "max_pain": None,
}

LIVE_MARKET_DATA = {
    "spot_price": 100.0,
    "funding_rate": 0.02,
    "funding_regime": "BALANCED",  # CoinGlass healthy
    "squeeze_risk": "LOW",
    "ls_ratio": 1.0,
    "ls_bias": "NEUTRAL",
    "crypto_gex": 0.0,
    "crypto_gex_regime": "NEUTRAL",
    "max_pain": None,
}


def _make_generator(model_mod, config_name, signal_mod, generator_name, **cfg_overrides):
    models = importlib.import_module(model_mod)
    config_cls = getattr(models, config_name)
    generator_cls = getattr(importlib.import_module(signal_mod), generator_name)
    cfg = config_cls(**cfg_overrides)
    return cfg, generator_cls(cfg), models.TradingMode


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_degraded_data_flag_defaults_on_for_paper(model_mod, config_name, signal_mod, generator_name):
    cfg, _gen, TradingMode = _make_generator(model_mod, config_name, signal_mod, generator_name)
    assert cfg.allow_degraded_data_trades is True
    assert cfg.mode == TradingMode.PAPER


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_degraded_paper_allows_low_confidence_signal(model_mod, config_name, signal_mod, generator_name, direction):
    """CoinGlass outage + LOW-confidence directional call still trades in PAPER."""
    cfg, gen, _TradingMode = _make_generator(model_mod, config_name, signal_mod, generator_name)
    action, side, reasoning = gen._determine_action(direction, "LOW", DEGRADED_MARKET_DATA)

    assert action.value == direction
    assert side == direction.lower()
    assert "DEGRADED_NO_COINGLASS" in reasoning


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_degraded_paper_never_inflates_confidence_label(model_mod, config_name, signal_mod, generator_name):
    """End-to-end: generate_signal() must still stamp the signal with the
    combiner's real LOW confidence, not a manufactured MEDIUM/HIGH, even
    though the degraded relief valve let it through."""
    cfg, gen, _TradingMode = _make_generator(model_mod, config_name, signal_mod, generator_name)
    full_market_data = dict(DEGRADED_MARKET_DATA, combined_signal="LONG", combined_confidence="LOW")
    gen.get_market_data = lambda: full_market_data

    signal = gen.generate_signal(
        prophet_data={"advice": "UNAVAILABLE", "win_probability": 0.5, "confidence": 0.0, "top_factors": []}
    )

    assert signal.action.value == "LONG"
    assert signal.confidence == "LOW"
    assert "DEGRADED_NO_COINGLASS" in signal.reasoning


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_degraded_flag_off_still_blocks(model_mod, config_name, signal_mod, generator_name):
    """Operator can disable the relief valve; LOW confidence WAITs as before."""
    cfg, gen, _TradingMode = _make_generator(
        model_mod, config_name, signal_mod, generator_name,
        allow_degraded_data_trades=False,
    )
    action, side, reasoning = gen._determine_action("LONG", "LOW", DEGRADED_MARKET_DATA)
    assert action.value == "WAIT"
    assert side is None
    assert reasoning == "LOW_CONFIDENCE_LOW"


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_live_mode_never_relaxes_the_gate(model_mod, config_name, signal_mod, generator_name):
    """CRITICAL: the relief valve must never fire outside PAPER, even if the
    flag is left on. Live execution keeps the original LOW_CONFIDENCE WAIT."""
    live_mode = importlib.import_module(model_mod).TradingMode.LIVE
    cfg, gen, _TradingMode = _make_generator(
        model_mod, config_name, signal_mod, generator_name,
        mode=live_mode,
        allow_degraded_data_trades=True,
    )
    action, side, reasoning = gen._determine_action("LONG", "LOW", DEGRADED_MARKET_DATA)
    assert action.value == "WAIT"
    assert side is None
    assert reasoning == "LOW_CONFIDENCE_LOW"


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_healthy_coinglass_low_confidence_still_blocked(model_mod, config_name, signal_mod, generator_name):
    """The relief valve is scoped to a real CoinGlass outage only -- a
    LOW-confidence call while funding_regime is a real (non-UNKNOWN) value
    must still WAIT, same as before this change."""
    cfg, gen, _TradingMode = _make_generator(model_mod, config_name, signal_mod, generator_name)
    action, side, reasoning = gen._determine_action("LONG", "LOW", LIVE_MARKET_DATA)
    assert action.value == "WAIT"
    assert side is None
    assert reasoning == "LOW_CONFIDENCE_LOW"


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_high_confidence_path_still_tagged_while_degraded(model_mod, config_name, signal_mod, generator_name):
    """A HIGH-confidence signal already clears the gate on its own -- the
    relief valve doesn't need to fire for it to trade. It still gets the
    DEGRADED_NO_COINGLASS tag, though: the tag marks "CoinGlass was down for
    this scan" for stats-exclusion purposes, independent of whether the
    confidence gate itself needed relaxing."""
    cfg, gen, _TradingMode = _make_generator(model_mod, config_name, signal_mod, generator_name)
    action, side, reasoning = gen._determine_action("LONG", "HIGH", DEGRADED_MARKET_DATA)
    assert action.value == "LONG"
    assert "DEGRADED_NO_COINGLASS" in reasoning
