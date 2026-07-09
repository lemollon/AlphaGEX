"""Unit tests for the live chain provider's pure helpers (no network)."""
from backend.bots.routes_helpers import LiveTradierChainProvider


def test_occ_symbol_spy():
    p = LiveTradierChainProvider()
    leg = {"type": "call", "strike": 500, "expiration": "2026-05-20"}
    assert p._occ("SPY", leg) == "SPY260520C00500000"


def test_occ_symbol_spx_uses_spxw_root():
    # SPX dailies/weeklies trade under the SPXW root. Building "SPX..." would
    # find no quote — every scan would see a stale mark and the EOD close
    # would fall back to the entry mark. SPLASH v2 trades SPX, so this
    # mapping is load-bearing.
    p = LiveTradierChainProvider()
    call = {"type": "call", "strike": 5035, "expiration": "2026-07-09"}
    put = {"type": "put", "strike": 4965, "expiration": "2026-07-09"}
    assert p._occ("SPX", call) == "SPXW260709C05035000"
    assert p._occ("SPX", put) == "SPXW260709P04965000"
