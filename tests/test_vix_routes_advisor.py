# tests/test_vix_routes_advisor.py
from fastapi.testclient import TestClient
import backend.api.routes.vix_routes as vr


def _app():
    from fastapi import FastAPI
    app = FastAPI(); app.include_router(vr.router); return app


def test_regime_advisor_returns_report(monkeypatch):
    monkeypatch.setattr(vr, "_advisor_report", lambda: {"ok": True, "regime_label": "exhaustion",
        "recommendation": {"stance": "buy_the_bounce"}, "timing": {"suggested_dte": 13},
        "outlook": {}, "signals": {}, "inputs": {}})
    monkeypatch.setattr(vr, "_advisor_live_record", lambda: {"overall_accuracy": None, "n_scored": 0})
    c = TestClient(_app())
    r = c.get("/api/vix/regime-advisor")
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["regime_label"] == "exhaustion"
    assert "evidence" in body and "live_record" in body
