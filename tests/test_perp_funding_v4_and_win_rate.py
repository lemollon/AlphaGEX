"""Funding rate now comes from CoinGlass v4 (v2 is retired), and win rate
excludes trades opened on degraded (no-funding) data."""

from unittest.mock import patch

from data.crypto_data_provider import CoinGlassClient
from trading.agape_perp_stats import is_degraded_trade, scored_win_rate


def _client_with(responses):
    client = CoinGlassClient(api_key="test")

    def fake_request(endpoint, params=None, version="v4"):
        return responses.get((version, endpoint))

    return client, patch.object(client, "_request", side_effect=fake_request)


def test_funding_uses_v4_exchange_list_and_normalizes_interval():
    client, p = _client_with({
        ("v4", "futures/funding-rate/exchange-list"): [
            {"symbol": "ETH", "stablecoin_margin_list": [{"funding_rate": 0.5}]},
            {"symbol": "BTC", "stablecoin_margin_list": [
                {"exchange": "Binance", "funding_rate": 0.01, "funding_rate_interval": 8},
                {"exchange": "Hyperliquid", "funding_rate": 0.0025, "funding_rate_interval": 1},
            ]},
        ],
    })
    with p:
        fr = client.get_funding_rate("BTC")
    assert fr is not None
    assert abs(fr.rate - 0.015) < 1e-12  # (0.01 + 0.0025*8) / 2
    assert fr.regime == "OVERLEVERAGED_LONG"


def test_funding_falls_back_to_oi_weighted_history():
    client, p = _client_with({
        ("v4", "futures/funding-rate/oi-weight-history"): [{"time": 1, "close": "0.002"}],
    })
    with p:
        fr = client.get_funding_rate("SOL")
    assert fr is not None and fr.rate == 0.002 and fr.regime == "BALANCED"


def test_funding_falls_back_to_v2_last():
    client, p = _client_with({
        ("v2", "funding"): [{"symbol": "XRP", "uMarginList": [{"rate": 0.02}, {"rate": 0.04}]}],
    })
    with p:
        fr = client.get_funding_rate("XRP")
    assert fr is not None and abs(fr.rate - 0.03) < 1e-12


def test_funding_none_when_all_sources_empty():
    client, p = _client_with({})
    with p:
        assert client.get_funding_rate("BTC") is None


def test_scored_win_rate_excludes_degraded_trades():
    trades = [
        {"realized_pnl": 10, "funding_regime_at_entry": "BALANCED"},
        {"realized_pnl": -5, "funding_regime_at_entry": "MILD_LONG_BIAS"},
        {"realized_pnl": 3, "funding_regime_at_entry": "UNKNOWN"},
        {"realized_pnl": 4, "funding_regime_at_entry": None},
        {"realized_pnl": 2, "funding_regime_at_entry": ""},
    ]
    assert scored_win_rate(trades) == (50.0, 2, 3)
    assert is_degraded_trade(trades[2]) and not is_degraded_trade(trades[0])


def test_scored_win_rate_all_degraded_or_empty():
    assert scored_win_rate([{"realized_pnl": 1, "funding_regime_at_entry": "UNKNOWN"}]) == (None, 0, 1)
    assert scored_win_rate([]) == (None, 0, 0)
    assert scored_win_rate(None) == (None, 0, 0)
