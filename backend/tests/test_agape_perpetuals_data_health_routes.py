"""Tests for /api/agape-perpetuals/data-health."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import agape_perpetuals_data_health_routes as dh


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(dh.router)
    return TestClient(app)


def _scan(minutes_ago=1, funding_regime="POSITIVE"):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"timestamp": ts, "funding_regime": funding_regime}


def _patch_scans(scans_by_bot):
    def fetch(bot_id):
        return scans_by_bot.get(bot_id)

    return patch.object(dh, "_fetch_latest_scan", side_effect=fetch)


def test_healthy_when_all_bots_fresh_and_known(client):
    scans = {bid: _scan() for bid in dh.ALL_BOT_IDS}
    with _patch_scans(scans):
        r = client.get("/api/agape-perpetuals/data-health")
    assert r.status_code == 200
    body = r.json()
    assert body["healthy"] is True
    assert body["unknown_count"] == 0
    assert body["stale_count"] == 0
    assert len(body["bots"]) == len(dh.ALL_BOT_IDS)


def test_unhealthy_when_funding_regime_unknown(client):
    scans = {bid: _scan() for bid in dh.ALL_BOT_IDS}
    scans["btc"] = _scan(funding_regime="UNKNOWN")
    with _patch_scans(scans):
        r = client.get("/api/agape-perpetuals/data-health")
    body = r.json()
    assert body["healthy"] is False
    assert body["unknown_count"] == 1
    btc = next(b for b in body["bots"] if b["bot_id"] == "btc")
    assert btc["funding_unknown"] is True
    assert btc["healthy"] is False


def test_unhealthy_when_scan_is_stale(client):
    scans = {bid: _scan() for bid in dh.ALL_BOT_IDS}
    scans["shib"] = _scan(minutes_ago=999)
    with _patch_scans(scans):
        r = client.get("/api/agape-perpetuals/data-health")
    body = r.json()
    assert body["healthy"] is False
    assert body["stale_count"] == 1
    shib = next(b for b in body["bots"] if b["bot_id"] == "shib")
    assert shib["stale"] is True


def test_missing_scan_counts_as_stale_and_unhealthy(client):
    scans = {bid: _scan() for bid in dh.ALL_BOT_IDS if bid != "eth"}
    with _patch_scans(scans):
        r = client.get("/api/agape-perpetuals/data-health")
    body = r.json()
    assert body["healthy"] is False
    eth = next(b for b in body["bots"] if b["bot_id"] == "eth")
    assert eth["last_scan"] is None
    assert eth["stale"] is True
    assert eth["healthy"] is False
