"""Fail-closed tests for the TradingVolatility watcher enrichment."""
from datetime import datetime, timezone

import pytest

from backend import trading_volatility_context as tv


UTC = timezone.utc


@pytest.mark.asyncio
async def test_missing_credentials_returns_unavailable_without_network(monkeypatch) -> None:
    monkeypatch.delenv("TRADING_VOLATILITY_API_TOKEN", raising=False)
    monkeypatch.delenv("TRADING_VOLATILITY_API_KEY", raising=False)

    result = await tv.get_trading_volatility_context(
        object(),
        symbol="QQQ",
        retrieved_at=datetime(2026, 9, 17, 20, 0, tzinfo=UTC),
        refresh_seconds=300,
        max_age_seconds=129600,
        universe_limit=200,
    )

    assert result["configured"] is False
    assert result["available"] is False
    assert result["symbols"] == []
    assert result["symbol_context"] is None
    assert "not configured" in result["last_error"]


def test_invalid_vendor_timestamp_is_rejected() -> None:
    assert tv._parse_timestamp(None) is None
    assert tv._parse_timestamp("") is None
    assert tv._parse_timestamp("not-a-timestamp") is None
