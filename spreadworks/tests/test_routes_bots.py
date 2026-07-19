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
    # FLOW ships disabled (SURGE and SURGE are enabled by default).
    r = client.get("/api/spreadworks/bots/flow/status")
    assert r.status_code == 200
    d = r.json()
    assert d["bot"] == "flow"
    assert d["enabled"] is False
    assert d["open_positions"] == 0


def test_unknown_bot_returns_404(client):
    r = client.get("/api/spreadworks/bots/notabot/status")
    assert r.status_code == 404


def test_toggle_flips_enabled(client):
    # Start from FLOW (disabled by default) so the first toggle -> True.
    r = client.post("/api/spreadworks/bots/flow/toggle")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    r2 = client.post("/api/spreadworks/bots/flow/toggle")
    assert r2.json()["enabled"] is False


def test_config_get_and_post(client):
    r = client.get("/api/spreadworks/bots/surge/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["pt_pct"] == 0.50 or float(cfg["pt_pct"]) == 0.50
    # drift_offset rides the same config row (added 2026-07-03 for SURGE)
    assert int(cfg["drift_offset"]) == 2

    r2 = client.post("/api/spreadworks/bots/surge/config", json={"pt_pct": 0.40, "drift_offset": 3})
    assert r2.status_code == 200
    assert int(client.get("/api/spreadworks/bots/surge/config").json()["drift_offset"]) == 3

    r2 = client.post("/api/spreadworks/bots/surge/config", json={"pt_pct": 0.40})
    assert r2.status_code == 200
    r3 = client.get("/api/spreadworks/bots/surge/config")
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
        "surge", "iron_butterfly",
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
    (
        "meadow", "double_diagonal_credit",
        [
            {"side": "short", "type": "call", "strike": 506, "expiration": "2099-01-16"},
            {"side": "short", "type": "put",  "strike": 494, "expiration": "2099-01-16"},
            {"side": "long",  "type": "call", "strike": 511, "expiration": "2099-01-19"},
            {"side": "long",  "type": "put",  "strike": 489, "expiration": "2099-01-19"},
        ],
        1.6,  # credit
    ),
    (
        # SURGE long butterfly: single-type 1-2-1 with the body sold twice.
        # The payoff branch must resolve lower/upper by strike ordering.
        "surge", "long_butterfly",
        [
            {"side": "long",  "type": "call", "strike": 498, "expiration": "2099-01-15"},
            {"side": "short", "type": "call", "strike": 501, "expiration": "2099-01-15"},
            {"side": "short", "type": "call", "strike": 501, "expiration": "2099-01-15"},
            {"side": "long",  "type": "call", "strike": 504, "expiration": "2099-01-15"},
        ],
        0.75,  # debit
    ),
    (
        # SURGE pin+drift combo: 8 legs in build order (fly 1-2-1, then
        # call calendar @503, then put calendar @499) across two expirations.
        "surge", "pin_drift_combo",
        [
            {"side": "long",  "type": "call", "strike": 498, "expiration": "2099-01-15"},
            {"side": "short", "type": "call", "strike": 501, "expiration": "2099-01-15"},
            {"side": "short", "type": "call", "strike": 501, "expiration": "2099-01-15"},
            {"side": "long",  "type": "call", "strike": 504, "expiration": "2099-01-15"},
            {"side": "short", "type": "call", "strike": 503, "expiration": "2099-01-15"},
            {"side": "long",  "type": "call", "strike": 503, "expiration": "2099-01-16"},
            {"side": "short", "type": "put",  "strike": 499, "expiration": "2099-01-15"},
            {"side": "long",  "type": "put",  "strike": 499, "expiration": "2099-01-16"},
        ],
        1.75,  # debit
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
    r = client.get("/api/spreadworks/bots/surge/positions/does-not-exist/payoff")
    assert r.status_code == 404


def test_adjust_updates_pt_and_flips_override(client):
    from backend import routes_bots
    pid = "surge-adj-001"
    _seed_bot_position(
        routes_bots.ENGINE, "surge", pid, "iron_butterfly",
        [
            {"side": "short", "type": "call", "strike": 500, "expiration": "2099-01-15"},
            {"side": "short", "type": "put",  "strike": 500, "expiration": "2099-01-15"},
            {"side": "long",  "type": "call", "strike": 505, "expiration": "2099-01-15"},
            {"side": "long",  "type": "put",  "strike": 495, "expiration": "2099-01-15"},
        ],
        2.0,
    )
    r = client.post(
        f"/api/spreadworks/bots/surge/positions/{pid}/adjust",
        json={"pt_target_pnl": 75.0},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pt_target_pnl"] == pytest.approx(75.0)
    assert d["pt_override"] is True


def test_adjust_normalizes_sl_to_magnitude(client):
    from backend import routes_bots
    pid = "tide-adj-001"
    _seed_bot_position(
        routes_bots.ENGINE, "tide", pid, "double_calendar",
        [
            {"side": "short", "type": "call", "strike": 505, "expiration": "2099-01-16"},
            {"side": "short", "type": "put",  "strike": 495, "expiration": "2099-01-16"},
            {"side": "long",  "type": "call", "strike": 505, "expiration": "2099-01-30"},
            {"side": "long",  "type": "put",  "strike": 495, "expiration": "2099-01-30"},
        ],
        1.5,
    )
    # Sending a negative SL is interpreted as a magnitude — decide_exit uses
    # -abs(sl) internally, so the sign on the wire shouldn't matter.
    r = client.post(
        f"/api/spreadworks/bots/tide/positions/{pid}/adjust",
        json={"sl_target_pnl": -250.0},
    )
    assert r.status_code == 200
    assert r.json()["sl_target_pnl"] == pytest.approx(250.0)


def test_adjust_400_when_no_fields(client):
    r = client.post(
        "/api/spreadworks/bots/surge/positions/anything/adjust",
        json={},
    )
    assert r.status_code == 400


def test_adjust_404_on_unknown_position(client):
    r = client.post(
        "/api/spreadworks/bots/surge/positions/does-not-exist/adjust",
        json={"pt_target_pnl": 50.0},
    )
    assert r.status_code == 404


def _seed_closed_trade(engine, bot: str, position_id: str, realized_pnl: float):
    """Insert one realized trade into {bot}_closed_trades."""
    import json
    from datetime import datetime
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {bot}_closed_trades ("
            "position_id, close_price, close_time, close_reason, realized_pnl, "
            "contracts, legs, entry_price, entry_time, ticker, strategy"
            ") VALUES ("
            ":pid, 1.0, :ct, 'PT', :pnl, 1, :legs, 0.75, :et, 'SPY', 'long_butterfly')"
        ), {
            "pid": position_id, "ct": datetime.now(), "pnl": realized_pnl,
            "legs": json.dumps([]), "et": datetime.now(),
        })


def _seed_snapshot(engine, bot: str, age_days: float, equity: float):
    """Insert one equity snapshot `age_days` before now into {bot}_equity_snapshots."""
    from datetime import datetime, timedelta
    from sqlalchemy import text
    ts = datetime.now() - timedelta(days=age_days)
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {bot}_equity_snapshots ("
            "snapshot_time, equity, unrealized_pnl, realized_pnl_today, "
            "cumulative_pnl, open_positions"
            ") VALUES (:t, :e, 0, 0, 0, 0)"
        ), {"t": ts, "e": equity})


def test_equity_curve_windows_from_snapshots_without_closed_trades(client):
    """The non-intraday windows must populate from the dense equity_snapshots series
    even when a bot has closed ZERO trades — this is the bug that left daily/weekly/
    monthly blank for every bot (they used to read the empty closed_trades ledger)."""
    from backend import routes_bots
    eng = routes_bots.ENGINE
    # Snapshots at 40d, 20d, 5d, and 12h old — NO closed trades seeded.
    _seed_snapshot(eng, "surge", 40, 1000.0)
    _seed_snapshot(eng, "surge", 20, 1100.0)
    _seed_snapshot(eng, "surge", 5, 1200.0)
    _seed_snapshot(eng, "surge", 0.5, 1250.0)

    def resp(window):
        return client.get(f"/api/spreadworks/bots/surge/equity-curve?window={window}").json()

    # 1W keeps only the 5d + 12h points; 1M adds the 20d; ALL includes the 40d.
    assert len(resp("1w")["curve"]) == 2
    assert len(resp("1m")["curve"]) == 3
    assert len(resp("all")["curve"]) == 4
    # Populated despite zero closed trades, and pnl is mark-to-market (equity - start).
    all_resp = resp("all")
    sc = all_resp["starting_capital"]
    latest = all_resp["curve"][-1]
    assert latest["equity"] == pytest.approx(1250.0)
    assert latest["pnl"] == pytest.approx(1250.0 - sc)


def test_reset_requires_confirm(client):
    r = client.post("/api/spreadworks/bots/surge/reset")
    assert r.status_code == 400
    assert "confirm" in r.text.lower()


def test_reset_404_on_unknown_bot(client):
    r = client.post("/api/spreadworks/bots/notabot/reset?confirm=true")
    assert r.status_code == 404


def test_reset_wipes_data_and_restores_starting_capital(client):
    from backend import routes_bots
    eng = routes_bots.ENGINE
    # Seed an open position AND a couple of closed trades so equity is moved.
    _seed_bot_position(
        eng, "surge", "surge-reset-open", "long_butterfly",
        [{"side": "long", "type": "call", "strike": 498, "expiration": "2099-01-15"}],
        0.75,
    )
    _seed_closed_trade(eng, "surge", "surge-reset-c1", 120.0)
    _seed_closed_trade(eng, "surge", "surge-reset-c2", -45.0)

    before = client.get("/api/spreadworks/bots/surge/status").json()
    assert before["open_positions"] == 1
    assert before["equity"] != before["starting_capital"]

    r = client.post("/api/spreadworks/bots/surge/reset?confirm=true")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["reset"] is True
    assert d["deleted"]["positions"] == 1
    assert d["deleted"]["closed_trades"] == 2
    assert d["equity"] == pytest.approx(d["starting_capital"])

    after = client.get("/api/spreadworks/bots/surge/status").json()
    assert after["open_positions"] == 0
    assert after["equity"] == pytest.approx(after["starting_capital"])
    # Trade history and equity curve are empty after the wipe.
    assert client.get("/api/spreadworks/bots/surge/trades").json()["trades"] == []
    assert client.get("/api/spreadworks/bots/surge/equity-curve").json()["curve"] == []


# ---------------------------------------------------------------------------
# Watchlist endpoint tests
# ---------------------------------------------------------------------------

class _WatchlistFakeProvider:
    """Minimal ChainProvider for the watchlist endpoint test."""
    def __init__(self, chains, history):
        self._chains = chains
        self._history = history
    def get_chain(self, *, ticker, dte, today):
        return self._chains.get(ticker)
    def get_leg_mids(self, *, ticker, legs):
        return [leg["entry_price"] for leg in legs]
    def get_daily_history(self, *, ticker, days):
        return list(self._history.get(ticker, []))


def _wl_chain(ticker, spot):
    # Synthetic option chain priced so a name at this spot yields a buildable
    # bull-call debit spread (mids well above min_option_price, tight b/a).
    # Names with no chain entry resolve to None -> WATCHING.
    opts = []
    for s in range(100, 201, 5):
        call_mid = max(0.30, (spot - s) * 0.4 + 6.0)
        put_mid = max(0.30, (s - spot) * 0.4 + 6.0)
        opts.append({"strike": s, "type": "call", "bid": round(call_mid - 0.05, 2), "ask": round(call_mid + 0.05, 2)})
        opts.append({"strike": s, "type": "put", "bid": round(put_mid - 0.05, 2), "ask": round(put_mid + 0.05, 2)})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker, "options": opts}


def _wl_history():
    from datetime import date, timedelta
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        p = 101 + i
        bars.append({"date": (base + timedelta(days=i)).isoformat(),
                     "open": p, "high": p, "low": p, "close": p})
    bars += [
        {"date": (base + timedelta(days=36)).isoformat(), "open": 144, "high": 150, "low": 143, "close": 145},
        {"date": (base + timedelta(days=37)).isoformat(), "open": 145, "high": 146, "low": 142, "close": 143},
        {"date": (base + timedelta(days=38)).isoformat(), "open": 143, "high": 143, "low": 140, "close": 141},
        {"date": (base + timedelta(days=39)).isoformat(), "open": 141, "high": 141, "low": 139, "close": 140},
    ]
    return bars


def test_watchlist_returns_rows_for_universe_bot(client, monkeypatch):
    from backend.bots import routes_helpers
    provider = _WatchlistFakeProvider(
        chains={"QQQ": _wl_chain("QQQ", 140.0)},
        history={"QQQ": _wl_history()},
    )
    monkeypatch.setattr(routes_helpers, "build_live_chain_provider", lambda: provider)
    r = client.get("/api/spreadworks/bots/undertow/watchlist")
    assert r.status_code == 200
    d = r.json()
    assert d["bot"] == "undertow"
    assert d["mode"] == "debit"
    assert isinstance(d["universe"], list) and "QQQ" in d["universe"]
    assert len(d["rows"]) == len(d["universe"])
    by_ticker = {row["ticker"]: row for row in d["rows"]}
    assert by_ticker["QQQ"]["status"] == "SIGNAL"
    assert by_ticker["QQQ"]["candidate"]["kind"] == "bull_call_spread"
    assert by_ticker["SPY"]["status"] == "WATCHING"
    # QQQ is the only SIGNAL -> it is the one the live scanner would open.
    assert by_ticker["QQQ"]["would_open"] is True
    assert by_ticker["SPY"]["would_open"] is False
    assert sum(1 for row in d["rows"] if row["would_open"]) == 1


def test_watchlist_400_for_non_universe_bot(client):
    r = client.get("/api/spreadworks/bots/flow/watchlist")
    assert r.status_code == 400


def test_watchlist_404_for_unknown_bot(client):
    r = client.get("/api/spreadworks/bots/notabot/watchlist")
    assert r.status_code == 404
