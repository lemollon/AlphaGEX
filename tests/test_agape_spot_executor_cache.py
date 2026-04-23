"""
AGAPE-SPOT Executor — Price Cache Tests

Verifies the 5s TTL cache on AgapeSpotExecutor.get_current_price collapses
rapid-fire calls into a single underlying client hit. This is the optimization
that backs the dashboard refresh rate without hammering Coinbase.

Run:  pytest tests/test_agape_spot_executor_cache.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

from trading.agape_spot.executor import AgapeSpotExecutor


@pytest.fixture
def executor():
    """Build an executor with Coinbase init skipped (no real keys needed)."""
    config = MagicMock()
    config.tickers = ["ETH-USD"]
    config.live_tickers = []
    # Skip _init_coinbase; we'll inject a fake client via _get_client.
    with patch("trading.agape_spot.executor.coinbase_available", False):
        ex = AgapeSpotExecutor(config=config, db=None)
    return ex


def _fake_product(price: float):
    """Match the shape AgapeSpotExecutor._resp(...) reads from."""
    product = MagicMock()
    product.price = str(price)
    return product


def test_cache_collapses_repeat_calls(executor):
    """10 calls in 1s should hit the underlying client exactly once."""
    fake_client = MagicMock()
    fake_client.get_product.return_value = _fake_product(3500.0)

    with patch.object(executor, "_get_client", return_value=fake_client):
        prices = [executor.get_current_price("ETH-USD") for _ in range(10)]

    assert prices == [3500.0] * 10
    assert fake_client.get_product.call_count == 1


def test_cache_isolates_per_ticker(executor):
    """Each ticker has its own cache slot."""
    eth_product = _fake_product(3500.0)
    btc_product = _fake_product(65000.0)

    def routing_get_product(ticker):
        return eth_product if ticker == "ETH-USD" else btc_product

    fake_client = MagicMock()
    fake_client.get_product.side_effect = routing_get_product

    with patch.object(executor, "_get_client", return_value=fake_client):
        p1 = executor.get_current_price("ETH-USD")
        p2 = executor.get_current_price("BTC-USD")
        # Repeat both — should hit cache, not the client.
        p1b = executor.get_current_price("ETH-USD")
        p2b = executor.get_current_price("BTC-USD")

    assert p1 == p1b == 3500.0
    assert p2 == p2b == 65000.0
    # Exactly one call per ticker.
    assert fake_client.get_product.call_count == 2


def test_cache_expires_after_ttl(executor, monkeypatch):
    """After TTL elapses, the next call re-hits the underlying client."""
    fake_client = MagicMock()
    fake_client.get_product.return_value = _fake_product(3500.0)

    # Freeze time so we can step past the TTL deterministically.
    t = [1_000_000.0]
    monkeypatch.setattr("trading.agape_spot.executor.time.time", lambda: t[0])

    with patch.object(executor, "_get_client", return_value=fake_client):
        executor.get_current_price("ETH-USD")
        # Still inside TTL: no new call
        t[0] += executor._PRICE_CACHE_TTL - 0.5
        executor.get_current_price("ETH-USD")
        # Step past TTL: new call
        t[0] += 1.0
        executor.get_current_price("ETH-USD")

    assert fake_client.get_product.call_count == 2


def test_cache_does_not_store_none(executor):
    """A failed fetch (None) must not pollute the cache — the next call retries."""
    fake_client = MagicMock()
    fake_client.get_product.side_effect = Exception("coinbase down")

    # Force both fallback paths (urllib + crypto provider) to fail.
    with (
        patch.object(executor, "_get_client", return_value=fake_client),
        patch("urllib.request.urlopen", side_effect=Exception("network down")),
    ):
        first = executor.get_current_price("ETH-USD")

    assert first is None
    # Cache should NOT have stored the None result.
    assert "ETH-USD" not in executor._price_cache

    # Next call with a working primary client returns the real price.
    fake_client.get_product.side_effect = None
    fake_client.get_product.return_value = _fake_product(3500.0)
    with patch.object(executor, "_get_client", return_value=fake_client):
        second = executor.get_current_price("ETH-USD")

    assert second == 3500.0
