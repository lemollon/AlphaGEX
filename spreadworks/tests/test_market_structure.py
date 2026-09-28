from datetime import datetime, timezone

import backend.market_structure as market_structure
from backend.market_structure import compute_gamma_map, _confidence


def test_compute_gamma_map_builds_buckets_and_walls():
    rows = [
        {"strike": "99", "dte": "0", "gamma": "0.02",
         "callOpenInterest": "200", "putOpenInterest": "50",
         "callMidIv": "0.20", "putMidIv": "0.21", "smvVol": "0.205",
         "residualRate": "0.04"},
        {"strike": "100", "dte": "0", "gamma": "0.03",
         "callOpenInterest": "500", "putOpenInterest": "100",
         "callMidIv": "0.20", "putMidIv": "0.21", "smvVol": "0.205",
         "residualRate": "0.04"},
        {"strike": "101", "dte": "2", "gamma": "0.025",
         "callOpenInterest": "400", "putOpenInterest": "800",
         "callMidIv": "0.22", "putMidIv": "0.23", "smvVol": "0.225",
         "residualRate": "0.04"},
        {"strike": "95", "dte": "30", "gamma": "0.01",
         "callOpenInterest": "100", "putOpenInterest": "1200",
         "callMidIv": "0.25", "putMidIv": "0.27", "smvVol": "0.26",
         "residualRate": "0.04"},
    ]
    out = compute_gamma_map(rows, 100.0)
    assert out["reason"] is None
    assert out["n_rows"] == 4
    assert out["call_wall"] == 100.0
    assert out["put_wall"] == 95.0
    assert "0dte" in out["buckets"]
    assert "1_5dte" in out["buckets"]
    assert "21_365dte" in out["buckets"]
    assert out["gamma_regime"] in {"positive", "negative", "flat"}


def test_compute_gamma_map_rejects_empty_chain():
    out = compute_gamma_map([], 100.0)
    assert out["net_gex_b"] is None
    assert out["reason"] == "no_usable_chain"


def test_confidence_fails_closed_on_stale_chain():
    now = datetime(2026, 9, 24, 19, 0, tzinfo=timezone.utc)
    old = datetime(2026, 9, 24, 18, 57, tzinfo=timezone.utc)
    confidence, age, reason = _confidence(old, now, 500, True)
    assert confidence == "LOW"
    assert age == 180
    assert reason == "stale_or_thin_chain"


def test_confidence_requires_fresh_spot():
    now = datetime(2026, 9, 24, 19, 0, tzinfo=timezone.utc)
    confidence, _, reason = _confidence(now, now, 500, False)
    assert confidence == "LOW"
    assert reason == "stale_or_missing_spot"



def test_register_arms_minute_capture_and_initializes_tables(monkeypatch):
    calls = []
    jobs = []

    class Scheduler:
        def add_job(self, func, trigger, **kwargs):
            jobs.append((func, trigger, kwargs))

    monkeypatch.setattr(market_structure, "ensure_tables", lambda: calls.append("tables"))
    monkeypatch.setattr(
        market_structure,
        "capture_all",
        lambda: {"captured": True, "volatility": {"available": True},
                 "gamma": {"SPY": {"available": True}}},
    )

    assert market_structure.register(Scheduler()) is True
    assert calls == ["tables"]
    assert len(jobs) == 1
    func, trigger, kwargs = jobs[0]
    assert trigger == "cron"
    assert kwargs["id"] == "market_structure_capture"
    assert kwargs["day_of_week"] == "mon-fri"
    assert kwargs["hour"] == "8-15"
    assert kwargs["minute"] == "*"
    assert kwargs["max_instances"] == 1
    assert kwargs["coalesce"] is True
    assert kwargs["next_run_time"] is not None

    func()



def test_capture_all_parallel_persists_failed_snapshots(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(market_structure, "fetch_vol_indices",
                        lambda current: {"available": True, "indices": {}})
    monkeypatch.setattr(market_structure, "persist_vol", lambda vol, current: None)

    def fake_snapshot(symbol, current):
        return {
            "symbol": symbol,
            "available": symbol == "SPY",
            "confidence": "HIGH" if symbol == "SPY" else "LOW",
            "reason": None if symbol == "SPY" else "ORATS_API_TOKEN missing",
            "captured_at": current.isoformat(),
            "net_gex_b": 1.0 if symbol == "SPY" else None,
        }

    persisted = []
    monkeypatch.setattr(market_structure, "build_gamma_snapshot", fake_snapshot)
    monkeypatch.setattr(market_structure, "persist_snapshot",
                        lambda snapshot: persisted.append(snapshot))

    # Force market-hours regardless of the actual test clock.
    class FixedDateTime:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(market_structure, "datetime", FixedDateTime)
    out = market_structure.capture_all()
    assert out["captured"] is True
    assert set(out["gamma"]) == set(market_structure.SYMBOLS)
    assert len(persisted) == len(market_structure.SYMBOLS)
    assert any(item["reason"] == "ORATS_API_TOKEN missing" for item in persisted)
