"""Fail-closed tests for the TradingVolatility watcher enrichment."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import trading_volatility_context as tv


UTC = timezone.utc


@pytest.mark.asyncio
async def test_429_stops_extra_requests_and_respects_retry_after(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_VOLATILITY_API_TOKEN", "test-token")
    monkeypatch.setattr(tv, "_CACHE", {
        "checked_at": None, "last_success_at": None, "payload": None,
        "retry_at": None, "rate_limit_strikes": 0,
    })

    class Client:
        calls = 0

        async def get(self, *_args, **_kwargs):
            self.calls += 1
            return SimpleNamespace(status_code=429, headers={"Retry-After": "900"})

    client = Client()
    start = datetime(2026, 9, 29, 14, 0, tzinfo=UTC)

    async def context(at):
        return await tv.get_trading_volatility_context(
            client, symbol="QQQ", retrieved_at=at, refresh_seconds=300,
            max_age_seconds=90, universe_limit=200,
        )

    first = await context(start)
    assert first["available"] is False
    assert first["next_retry_at"] == "2026-09-29T14:15:00+00:00"
    assert client.calls == 1
    second = await context(datetime(2026, 9, 29, 14, 10, tzinfo=UTC))
    assert second["available"] is False
    assert "cooldown" in second["last_error"]
    assert client.calls == 1
    await context(datetime(2026, 9, 29, 14, 15, tzinfo=UTC))
    assert client.calls == 2
    assert tv._CACHE["rate_limit_strikes"] == 2


def test_retry_delay_parses_http_date_and_caps_wait() -> None:
    now = datetime(2026, 9, 29, 14, 0, tzinfo=UTC)
    assert tv._retry_delay("Tue, 29 Sep 2026 14:10:00 GMT", now, 1) == 600
    assert tv._retry_delay(None, now, 2) == 600
    assert tv._retry_delay("99999", now, 1) == 99999


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


def test_normalize_top_setup_preserves_ranking_fields() -> None:
    item = {
        "ticker": "meta",
        "opportunity_score": "8.7",
        "opportunity_tier": "A",
        "trade_bias": "bullish",
        "trade_type": "breakout",
        "direction": "long",
        "structures": ["call", "call_debit_spread"],
        "entry_trigger": "hold above 680",
        "stop_description": "lose 668.80",
        "target_description": "690 then 700",
        "risk": "event volatility",
        "caution_flags": ["event_risk"],
        "agent_summary": "Bullish catalyst setup",
    }

    result = tv._normalize_top_setup(item)

    assert result["ticker"] == "META"
    assert result["opportunity_score"] == 8.7
    assert result["opportunity_tier"] == "A"
    assert result["trade_bias"] == "bullish"
    assert result["direction"] == "long"
    assert result["structures"] == ["call", "call_debit_spread"]
    assert result["entry_trigger"] == "hold above 680"
    assert result["stop_description"] == "lose 668.80"
    assert result["target_description"] == "690 then 700"


def test_build_payload_exposes_ranked_top_setups() -> None:
    retrieved_at = datetime(2026, 9, 18, 19, 0, tzinfo=UTC)
    universe_payload = {
        "data": {
            "items": [
                {"ticker": "LOW", "opportunity_score": 6.1, "trade_bias": "bearish"},
                {"ticker": "META", "opportunity_score": 8.7, "trade_bias": "bullish"},
            ]
        }
    }
    curve_payload = {
        "data": {
            "price": 720.0,
            "asof": "2026-09-18T18:59:30Z",
            "points": [
                {"strike": 725, "net": 10},
                {"strike": 715, "net": -8},
            ],
            "totals": {"gex_flip_price": 719.5},
        }
    }
    levels_payload = {
        "data": {
            "levels": [
                {"name": "plus_1s_1d", "price": 730},
                {"name": "minus_1s_1d", "price": 710},
            ]
        }
    }

    result = tv._build_payload(
        universe_payload,
        curve_payload,
        levels_payload,
        symbol="QQQ",
        retrieved_at=retrieved_at,
        max_age_seconds=120,
    )

    assert result["top_setup_count"] == 2
    assert result["top_setups"][0]["ticker"] == "META"
    assert result["top_setups"][0]["rank"] == 1
    assert result["top_setups"][0]["opportunity_score"] == 8.7
    assert result["top_setups"][1]["ticker"] == "LOW"
    assert result["symbols"] == ["LOW", "META"]
