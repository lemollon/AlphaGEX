"""Unit tests for the live chain provider's pure helpers (no network)."""
from backend.bots.routes_helpers import LiveTradierChainProvider


class _Response:
    status_code = 200

    def __init__(self, quotes):
        self._quotes = quotes

    def json(self):
        return {"quotes": {"quote": self._quotes}}


class _Client:
    def __init__(self, quotes):
        self._quotes = quotes

    def get(self, *args, **kwargs):
        return _Response(self._quotes)


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


def test_exit_prices_use_long_bid_and_short_ask_from_one_snapshot():
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    p._client = _Client([
        {"symbol": "SPY260918C00763000", "bid": 0.38, "ask": 0.39},
        {"symbol": "SPY260918C00764000", "bid": 0.21, "ask": 0.22},
    ])
    legs = [
        {"side": "long", "type": "call", "strike": 763,
         "expiration": "2026-09-18"},
        {"side": "short", "type": "call", "strike": 764,
         "expiration": "2026-09-18"},
    ]
    assert p.get_leg_exit_prices(ticker="SPY", legs=legs) == [0.38, 0.22]


def test_exit_prices_distinguish_missing_bid_from_displayed_zero():
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    legs = [{"side": "long", "type": "call", "strike": 763,
             "expiration": "2026-09-18"}]
    p._client = _Client([
        {"symbol": "SPY260918C00763000", "bid": None, "ask": 0.01},
    ])
    assert p.get_leg_exit_prices(ticker="SPY", legs=legs) == [None]

    p._client = _Client([
        {"symbol": "SPY260918C00763000", "bid": 0.0, "ask": 0.01},
    ])
    assert p.get_leg_exit_prices(ticker="SPY", legs=legs) == [0.0]
