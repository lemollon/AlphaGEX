"""Tests for /api/agape-perpetuals/trades aggregator route."""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import agape_perpetuals_trades_routes


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(agape_perpetuals_trades_routes.router)
    return TestClient(app)


def _fake_trade(bot_id, position_id, close_time, pnl=10.0, max_risk=100.0):
    return {
        "position_id": position_id,
        "side": "long",
        "quantity": 1.0,
        "entry_price": 100.0,
        "close_price": 110.0,
        "realized_pnl": pnl,
        "close_reason": "PROFIT",
        "open_time": "2026-05-01T00:00:00+00:00",
        "close_time": close_time,
        "max_risk_usd": max_risk,
    }


def _patch_registry(trades_by_bot):
    """Mimic the real per-bot db: apply since/until/before keyset filters and limit.

    trades_by_bot: {bot_id: [trade dicts]}
    """
    def fetch(bot_id, *, limit, since, until, before_close_time, before_position_id):
        rows = [dict(t) for t in trades_by_bot.get(bot_id, [])]
        if since:
            rows = [r for r in rows if (r.get("close_time") or "") >= since]
        if until:
            rows = [r for r in rows if (r.get("close_time") or "") <= until]
        if before_close_time:
            if before_position_id:
                rows = [
                    r for r in rows
                    if (r.get("close_time") or "") < before_close_time
                    or (
                        (r.get("close_time") or "") == before_close_time
                        and (r.get("position_id") or "") > before_position_id
                    )
                ]
            else:
                rows = [r for r in rows if (r.get("close_time") or "") < before_close_time]
        rows.sort(key=lambda r: (r.get("position_id") or ""))
        rows.sort(key=lambda r: (r.get("close_time") or ""), reverse=True)
        return rows[:limit]

    return patch.object(
        agape_perpetuals_trades_routes,
        "_fetch_bot_trades",
        side_effect=lambda bot_id, **kw: fetch(bot_id, **kw),
    )


def test_unknown_bot_returns_400(client):
    r = client.get("/api/agape-perpetuals/trades?bots=xxx&limit=10")
    assert r.status_code == 400


def test_filters_to_requested_bots(client):
    trades = {
        "btc": [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00")],
        "eth": [_fake_trade("eth", "e1", "2026-05-05T11:00:00+00:00")],
        "sol": [_fake_trade("sol", "s1", "2026-05-05T12:00:00+00:00")],
    }
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=btc,eth&limit=10")
    assert r.status_code == 200
    body = r.json()
    bot_ids = sorted({t["bot_id"] for t in body["trades"]})
    assert bot_ids == ["btc", "eth"]


def test_merges_descending_by_close_time(client):
    trades = {
        "btc": [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00")],
        "eth": [_fake_trade("eth", "e1", "2026-05-05T12:00:00+00:00")],
    }
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=btc,eth&limit=10")
    body = r.json()
    times = [t["close_time"] for t in body["trades"]]
    assert times == sorted(times, reverse=True)


def test_cursor_round_trip(client):
    trades = {
        "btc": [
            _fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00"),
            _fake_trade("btc", "b2", "2026-05-05T09:00:00+00:00"),
            _fake_trade("btc", "b3", "2026-05-05T08:00:00+00:00"),
        ],
    }
    with _patch_registry(trades):
        page1 = client.get("/api/agape-perpetuals/trades?bots=btc&limit=2").json()
    assert len(page1["trades"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"]

    with _patch_registry(trades):
        page2 = client.get(
            f"/api/agape-perpetuals/trades?bots=btc&limit=2&before={page1['next_cursor']}"
        ).json()
    seen = {t["position_id"] for t in page1["trades"]} | {t["position_id"] for t in page2["trades"]}
    assert seen == {"b1", "b2", "b3"}
    assert page2["has_more"] is False


def test_realized_pnl_pct_computed(client):
    trades = {"btc": [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00", pnl=25.0, max_risk=100.0)]}
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=btc&limit=10")
    t = r.json()["trades"][0]
    assert t["realized_pnl_pct"] == pytest.approx(25.0)


def test_star_expands_to_all_active(client):
    trades = {b: [] for b in [
        "eth", "sol", "avax", "btc", "xrp", "doge",
        "shib_futures", "link_futures", "ltc_futures", "bch_futures",
    ]}
    trades["btc"] = [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00")]
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=*&limit=50")
    assert r.status_code == 200
    assert len(r.json()["trades"]) == 1


def test_cursor_decode_invalid_does_not_crash(client):
    with _patch_registry({}):
        r = client.get("/api/agape-perpetuals/trades?bots=btc&before=garbage&limit=10")
    assert r.status_code == 200
