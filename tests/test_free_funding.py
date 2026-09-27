"""Free keyless funding fallback (Hyperliquid -> OKX) for when CoinGlass is down."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import data.free_funding as ff
from data.crypto_data_provider import CryptoDataProvider


def _okx_response(rate, funding_ms, next_ms):
    resp = MagicMock()
    resp.json.return_value = {
        "code": "0",
        "data": [{"fundingRate": rate, "fundingTime": str(funding_ms), "nextFundingTime": str(next_ms)}],
    }
    return resp


def test_hyperliquid_hourly_rate_converted_to_pct_per_8h():
    market = SimpleNamespace(funding_rate=0.0000125)  # 0.00125%/h
    with patch("data.hyperliquid_perp_provider.get_hyperliquid_perp_provider") as get:
        get.return_value.get_market.return_value = market
        fr = ff.get_free_funding_rate("BTC")
    assert fr.exchange == "hyperliquid"
    assert abs(fr.rate - 0.01) < 1e-12  # 0.00125% * 8 = 0.01% per 8h
    assert fr.regime == "MILD_LONG_BIAS"  # > 0.005%


def test_falls_back_to_okx_and_normalizes_interval(monkeypatch):
    monkeypatch.setattr(ff, "_hyperliquid_pct_8h", lambda s: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(ff, "SOURCES", [("hyperliquid", ff._hyperliquid_pct_8h), ("okx", ff._okx_pct_8h)])
    four_h = 4 * 3_600_000
    with patch("data.free_funding.requests.get", return_value=_okx_response("0.0001", 0, four_h)):
        fr = ff.get_free_funding_rate("SOL")
    assert fr.exchange == "okx"
    assert abs(fr.rate - 0.02) < 1e-12  # 0.01% per 4h -> 0.02% per 8h
    assert fr.regime == "OVERLEVERAGED_LONG"


def test_none_when_every_source_fails(monkeypatch):
    def boom(_symbol):
        raise RuntimeError("down")
    monkeypatch.setattr(ff, "SOURCES", [("a", boom), ("b", lambda s: None)])
    assert ff.get_free_funding_rate("ETH") is None


def test_provider_uses_free_funding_when_coinglass_returns_nothing(monkeypatch):
    provider = CryptoDataProvider.__new__(CryptoDataProvider)
    provider._coinglass = SimpleNamespace(get_funding_rate=lambda s: None)
    sentinel = object()
    monkeypatch.setattr("data.crypto_data_provider.get_free_funding_rate", lambda s: sentinel)
    assert provider.get_funding_rate("BTC") is sentinel


def test_provider_prefers_coinglass_when_available(monkeypatch):
    provider = CryptoDataProvider.__new__(CryptoDataProvider)
    cg = object()
    provider._coinglass = SimpleNamespace(get_funding_rate=lambda s: cg)
    monkeypatch.setattr("data.crypto_data_provider.get_free_funding_rate", lambda s: (_ for _ in ()).throw(AssertionError))
    assert provider.get_funding_rate("BTC") is cg
