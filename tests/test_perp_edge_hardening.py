import importlib

import pytest


CASES = [
    ("trading.agape_btc_perp.models", "AgapeBtcPerpConfig", "trading.agape_btc_perp.signals", "AgapeBtcPerpSignalGenerator"),
    ("trading.agape_eth_perp.models", "AgapeEthPerpConfig", "trading.agape_eth_perp.signals", "AgapeEthPerpSignalGenerator"),
    ("trading.agape_sol_perp.models", "AgapeSolPerpConfig", "trading.agape_sol_perp.signals", "AgapeSolPerpSignalGenerator"),
    ("trading.agape_avax_perp.models", "AgapeAvaxPerpConfig", "trading.agape_avax_perp.signals", "AgapeAvaxPerpSignalGenerator"),
    ("trading.agape_xrp_perp.models", "AgapeXrpPerpConfig", "trading.agape_xrp_perp.signals", "AgapeXrpPerpSignalGenerator"),
    ("trading.agape_doge_perp.models", "AgapeDogePerpConfig", "trading.agape_doge_perp.signals", "AgapeDogePerpSignalGenerator"),
    ("trading.agape_shib_perp.models", "AgapeShibPerpConfig", "trading.agape_shib_perp.signals", "AgapeShibPerpSignalGenerator"),
]


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_hardened_defaults(model_mod, config_name, signal_mod, generator_name):
    config_cls = getattr(importlib.import_module(model_mod), config_name)
    cfg = config_cls()
    assert cfg.risk_per_trade_pct == 1.0
    assert cfg.min_confidence == "MEDIUM"
    assert cfg.use_sar is False
    assert cfg.allow_range_bound_entries is False
    assert cfg.allow_wait_fallback_entries is False


@pytest.mark.parametrize("model_mod,config_name,signal_mod,generator_name", CASES)
def test_wait_and_range_do_not_manufacture_entries(model_mod, config_name, signal_mod, generator_name):
    config_cls = getattr(importlib.import_module(model_mod), config_name)
    generator_cls = getattr(importlib.import_module(signal_mod), generator_name)
    cfg = config_cls()
    gen = generator_cls(cfg)
    md = {
        "spot_price": 100.0,
        "funding_rate": -0.05,
        "funding_regime": "EXTREME_SHORT",
        "squeeze_risk": "HIGH",
        "ls_ratio": 0.5,
        "ls_bias": "EXTREME_SHORT",
        "crypto_gex": 1.0,
        "crypto_gex_regime": "NEGATIVE",
        "max_pain": 105.0,
    }

    wait_action = gen._determine_action("WAIT", "HIGH", md)
    range_action = gen._determine_action("RANGE_BOUND", "HIGH", md)

    assert wait_action[0].value == "WAIT"
    assert range_action[0].value == "WAIT"
