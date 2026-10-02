from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import valor_microstructure_routes as routes


def client():
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_status_route_returns_sanitized_read_only_state(monkeypatch):
    monkeypatch.setattr(routes, "_read_status", lambda: {
        "configured": True,
        "state": "healthy",
        "read_only": True,
        "orders_enabled": False,
        "source": "TASTYTRADE_DXLINK",
        "contract_symbol": "/MESZ6",
    })

    response = client().get("/api/valor/research/mes-microstructure/status")

    assert response.status_code == 200
    assert response.json()["read_only"] is True
    assert response.json()["orders_enabled"] is False
    assert "account" not in response.text.lower()
    assert "token" not in response.text.lower()


def test_status_route_sanitizes_database_failure(monkeypatch):
    def fail():
        raise RuntimeError("postgresql://user:secret@private-host/account")

    monkeypatch.setattr(routes, "_read_status", fail)
    response = client().get("/api/valor/research/mes-microstructure/status")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "MES microstructure collector status unavailable."
    }
    assert "secret" not in response.text
    assert "private-host" not in response.text

