import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend import models  # noqa: F401 — register models
from backend.bots.db import create_bot_tables


@pytest.fixture
def client(monkeypatch):
    """Build a FastAPI app instance wired to a thread-safe in-memory test DB."""
    # StaticPool shares a single connection across threads — required for
    # SQLite :memory: when TestClient runs requests on a worker thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    create_bot_tables(engine)

    Session = sessionmaker(bind=engine, expire_on_commit=False)

    from backend import app as backend_app
    from backend.db import get_db

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    backend_app.dependency_overrides[get_db] = override_get_db

    # Override the engine used by routes_bots
    from backend import routes_bots
    monkeypatch.setattr(routes_bots, "ENGINE", engine)

    with TestClient(backend_app) as c:
        yield c

    backend_app.dependency_overrides.clear()
    engine.dispose()


def test_status_returns_basic_fields(client):
    r = client.get("/api/spreadworks/bots/breeze/status")
    assert r.status_code == 200
    d = r.json()
    assert d["bot"] == "breeze"
    assert d["enabled"] is False
    assert d["open_positions"] == 0


def test_unknown_bot_returns_404(client):
    r = client.get("/api/spreadworks/bots/notabot/status")
    assert r.status_code == 404


def test_toggle_flips_enabled(client):
    r = client.post("/api/spreadworks/bots/breeze/toggle")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    r2 = client.post("/api/spreadworks/bots/breeze/toggle")
    assert r2.json()["enabled"] is False


def test_config_get_and_post(client):
    r = client.get("/api/spreadworks/bots/breeze/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["pt_pct"] == 0.30 or float(cfg["pt_pct"]) == 0.30

    r2 = client.post("/api/spreadworks/bots/breeze/config", json={"pt_pct": 0.40})
    assert r2.status_code == 200
    r3 = client.get("/api/spreadworks/bots/breeze/config")
    assert float(r3.json()["pt_pct"]) == 0.40
