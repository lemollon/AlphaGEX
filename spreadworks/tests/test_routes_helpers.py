"""Unit tests for the live chain provider's pure helpers (no network)."""
from backend.bots.routes_helpers import LiveTradierChainProvider, _displayed_size


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
        {"symbol": "SPY260918C00763000", "bid": 0.38, "ask": 0.39,
         "bidsize": 7, "asksize": 8},
        {"symbol": "SPY260918C00764000", "bid": 0.21, "ask": 0.22,
         "bidsize": 9, "asksize": 10},
    ])
    legs = [
        {"side": "long", "type": "call", "strike": 763,
         "expiration": "2026-09-18"},
        {"side": "short", "type": "call", "strike": 764,
         "expiration": "2026-09-18"},
    ]
    assert p.get_leg_exit_prices(ticker="SPY", legs=legs) == [0.38, 0.22]
    assert p.get_leg_exit_quotes(ticker="SPY", legs=legs) == [
        {"price": 0.38, "size": 7},
        {"price": 0.22, "size": 10},
    ]


def test_displayed_size_rejects_missing_negative_or_fractional_values():
    assert _displayed_size("3") == 3
    assert _displayed_size(0) == 0
    assert _displayed_size(None) is None
    assert _displayed_size(-1) is None
    assert _displayed_size(2.5) is None


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


def test_fetch_gex_uses_canonical_market_structure(monkeypatch):
    import backend.market_structure as market_structure

    monkeypatch.setattr(
        market_structure,
        "build_gamma_snapshot",
        lambda symbol: {
            "available": True,
            "gamma_flip": 742.86,
            "call_wall": 744.0,
            "put_wall": 737.0,
            "gamma_regime": "negative",
            "net_gex_b": -2.5,
            "confidence": "HIGH",
            "source": "ORATS live one-minute chain + Tradier spot",
            "chain_timestamp": "2026-09-24T19:00:00+00:00",
            "chain_age_seconds": 8.0,
        },
    )
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    out = p._fetch_gex("QQQ", "2026-09-25")
    assert out["flip_point"] == 742.86
    assert out["call_wall"] == 744.0
    assert out["put_wall"] == 737.0
    assert out["gamma_regime"] == "negative"
    assert out["gamma_confidence"] == "HIGH"
    assert out["gamma_expiration_context"] == "full_chain"
    assert out["magnets"] == []


def test_fetch_gex_unsupported_symbol_skips_legacy_network():
    class _ExplodingClient:
        def get(self, *args, **kwargs):
            raise AssertionError("legacy gamma endpoint must not be called")

    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    p._client = _ExplodingClient()
    assert p._fetch_gex("NVDA", "2026-09-25") == {}
