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


def _seed_bot_position(engine, bot: str, position_id: str, strategy: str, legs: list, entry_price: float):
    """Insert a synthetic OPEN position into {bot}_positions for payoff tests."""
    import json
    from datetime import datetime
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {bot}_positions ("
            "position_id, ticker, strategy, legs, entry_price, contracts, entry_time, "
            "status, mtm_value, mtm_pnl, mtm_updated_at, pt_target_pnl, sl_target_pnl, "
            "max_profit, max_loss, account_label"
            ") VALUES ("
            ":pid, 'SPY', :st, :legs, :ep, 1, :et, 'OPEN', :mv, 0, :et, "
            "10, -50, 100, -200, 'paper')"
        ), {
            "pid": position_id, "st": strategy, "legs": json.dumps(legs),
            "ep": entry_price, "et": datetime.now(), "mv": entry_price,
        })


@pytest.mark.parametrize("bot,strategy,legs,entry", [
    (
        "breeze", "iron_butterfly",
        [
            {"side": "short", "type": "call", "strike": 500, "expiration": "2099-01-15"},
            {"side": "short", "type": "put",  "strike": 500, "expiration": "2099-01-15"},
            {"side": "long",  "type": "call", "strike": 505, "expiration": "2099-01-15"},
            {"side": "long",  "type": "put",  "strike": 495, "expiration": "2099-01-15"},
        ],
        2.0,  # credit
    ),
    (
        "tide", "double_calendar",
        [
            {"side": "short", "type": "call", "strike": 505, "expiration": "2099-01-16"},
            {"side": "short", "type": "put",  "strike": 495, "expiration": "2099-01-16"},
            {"side": "long",  "type": "call", "strike": 505, "expiration": "2099-01-30"},
            {"side": "long",  "type": "put",  "strike": 495, "expiration": "2099-01-30"},
        ],
        1.5,  # debit
    ),
    (
        "drift", "double_diagonal",
        [
            {"side": "short", "type": "call", "strike": 505, "expiration": "2099-01-16"},
            {"side": "short", "type": "put",  "strike": 495, "expiration": "2099-01-16"},
            {"side": "long",  "type": "call", "strike": 506, "expiration": "2099-01-30"},
            {"side": "long",  "type": "put",  "strike": 494, "expiration": "2099-01-30"},
        ],
        2.0,  # debit
    ),
])
def test_position_payoff_returns_curve(client, bot, strategy, legs, entry):
    from backend import routes_bots
    pid = f"{bot}-test-001"
    _seed_bot_position(routes_bots.ENGINE, bot, pid, strategy, legs, entry)

    r = client.get(f"/api/spreadworks/bots/{bot}/positions/{pid}/payoff")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["position_id"] == pid
    assert d["strategy"] == strategy
    assert isinstance(d["pnl_curve"], list) and len(d["pnl_curve"]) > 0
    sample = d["pnl_curve"][0]
    assert "price" in sample and "pnl" in sample
    assert "breakevens" in d


def test_position_payoff_404_on_unknown_position(client):
    r = client.get("/api/spreadworks/bots/breeze/positions/does-not-exist/payoff")
    assert r.status_code == 404
