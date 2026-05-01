"""GOLIATH dashboard routes tests.

Direct-router tests (not via main.py app) so the suite stays light and
doesn't require the full FastAPI app to import. Each test patches
``_safe_query`` to return canned rows, then hits the route function
directly via FastAPI's TestClient against a minimal ``APIRouter``-only
app. This mirrors how trading.goliath unit tests inject fakes -- no DB
required.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes import goliath_routes  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(goliath_routes.router)
    return TestClient(app)


# ---- /status -------------------------------------------------------------

class TestStatus:
    def test_returns_5_instances_with_no_db_data(self, client):
        with patch.object(goliath_routes, "_safe_query", return_value=[]):
            r = client.get("/api/goliath/status")
        assert r.status_code == 200
        data = r.json()
        assert data["instance_count"] == 5
        assert len(data["instances"]) == 5
        assert data["platform_killed"] is False
        assert data["platform_cap"] == 750.0
        assert data["account_capital"] == 5000.0
        # Every instance has the standard keys, even with no DB data.
        for inst in data["instances"]:
            assert "name" in inst and "letf_ticker" in inst
            assert inst["killed"] is False
            assert inst["open_position_count"] == 0
            assert inst["trades_today"] == 0

    def test_marks_platform_killed_when_platform_kill_row_present(self, client):
        ts = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)
        # Order matches the 4 sequential _safe_query calls in goliath_status:
        #   heartbeats, open_counts, active_kills, platform_kill_rows
        with patch.object(
            goliath_routes, "_safe_query",
            side_effect=[
                [],              # heartbeats
                [],              # open_counts
                [],              # active_kills
                [("PK1", "drawdown breach", ts)],  # platform_kill_rows
            ],
        ):
            r = client.get("/api/goliath/status")
        assert r.status_code == 200
        data = r.json()
        assert data["platform_killed"] is True
        assert data["platform_kill_info"]["trigger_id"] == "PK1"
        assert data["platform_kill_info"]["reason"] == "drawdown breach"

    def test_marks_individual_instance_killed(self, client):
        ts = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)
        with patch.object(
            goliath_routes, "_safe_query",
            side_effect=[
                [],   # heartbeats
                [],   # open_counts
                [("GOLIATH-MSTU", "I3", "stop-out chain", ts)],  # active_kills
                [],   # platform_kill_rows
            ],
        ):
            r = client.get("/api/goliath/status")
        data = r.json()
        mstu = next(i for i in data["instances"] if i["name"] == "GOLIATH-MSTU")
        assert mstu["killed"] is True
        assert mstu["kill_info"]["trigger_id"] == "I3"


# ---- /instances ----------------------------------------------------------

class TestInstances:
    def test_returns_5_letf_instances(self, client):
        r = client.get("/api/goliath/instances")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 5
        tickers = {i["letf_ticker"] for i in data["instances"]}
        assert tickers == {"MSTU", "TSLL", "NVDL", "CONL", "AMDL"}


# ---- /positions ----------------------------------------------------------

class TestPositions:
    def test_empty_when_no_open(self, client):
        with patch.object(goliath_routes, "_safe_query", return_value=[]):
            r = client.get("/api/goliath/positions")
        assert r.status_code == 200
        data = r.json()
        assert data == {"positions": [], "count": 0}

    def test_renders_position_row(self, client):
        ts = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        from datetime import date
        row = (
            "goliath-paper-abc123",       # position_id
            "GOLIATH-MSTU",               # instance_name
            "MSTU", "MSTR",
            "OPEN", ts, None, date(2026, 5, 8),
            9.0, 8.5, 12.0, 2,            # strikes, contracts
            0.50, 0.20, 0.30,             # entry mids
            0.30, 0.30, 0.0,              # credit, cost, net
            50.0, None, None,             # max_loss, realized_pnl, close_trigger
        )
        with patch.object(goliath_routes, "_safe_query", return_value=[row]):
            r = client.get("/api/goliath/positions")
        data = r.json()
        assert data["count"] == 1
        p = data["positions"][0]
        assert p["position_id"] == "goliath-paper-abc123"
        assert p["state"] == "OPEN"
        assert p["short_put_strike"] == 9.0
        assert p["contracts"] == 2

    def test_state_filter_uppercased(self, client):
        captured = {}

        def fake_query(sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return []

        with patch.object(goliath_routes, "_safe_query", side_effect=fake_query):
            r = client.get("/api/goliath/positions?state=closed")
        assert r.status_code == 200
        assert captured["params"] == ("CLOSED",)


# ---- /positions/{id} -----------------------------------------------------

class TestPositionDetail:
    def test_404_when_missing(self, client):
        with patch.object(goliath_routes, "_safe_query", return_value=[]):
            r = client.get("/api/goliath/positions/does-not-exist")
        assert r.status_code == 404

    def test_returns_position_plus_audit_chain(self, client):
        ts = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        pos_row = (
            "goliath-paper-x", "GOLIATH-MSTU", "OPEN", ts, None,
            9.0, 8.5, 12.0, 2, 0.0, 50.0, None, None,
        )
        audit_rows = [
            (1, ts, "ENTRY_EVAL", {"gates_passed": ["G01"]}),
            (2, ts, "ENTRY_FILLED", {"contracts": 2}),
        ]
        with patch.object(
            goliath_routes, "_safe_query",
            side_effect=[[pos_row], audit_rows],
        ):
            r = client.get("/api/goliath/positions/goliath-paper-x")
        data = r.json()
        assert data["position"]["position_id"] == "goliath-paper-x"
        assert len(data["audit_chain"]) == 2
        assert data["audit_chain"][0]["event_type"] == "ENTRY_EVAL"


# ---- /equity-curve + /equity-curve/intraday ------------------------------

class TestEquityCurve:
    def test_platform_returns_empty_when_no_snapshots(self, client):
        with patch.object(goliath_routes, "_safe_query", return_value=[]):
            r = client.get("/api/goliath/equity-curve")
        assert r.status_code == 200
        data = r.json()
        assert data["scope"] == "PLATFORM"
        assert data["count"] == 0

    def test_instance_requires_instance_param(self, client):
        r = client.get("/api/goliath/equity-curve?scope=INSTANCE")
        assert r.status_code == 400

    def test_intraday_falls_back_to_prior_day_when_only_one_today(self, client):
        ts_today = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)
        ts_yesterday = datetime(2026, 4, 30, 20, 0, tzinfo=timezone.utc)
        # Two queries: today rows, then prior-day fallback rows.
        with patch.object(
            goliath_routes, "_safe_query",
            side_effect=[
                [(ts_today, 5050.0, 50.0, 1)],  # only 1 today -> fallback fires
                [(ts_yesterday, 5000.0, 0.0, 0)],  # prior day single
            ],
        ):
            r = client.get("/api/goliath/equity-curve/intraday")
        data = r.json()
        assert data["fallback_used"] is True
        assert data["count"] == 2  # 1 prior + 1 today => line render OK


# ---- /performance --------------------------------------------------------

class TestPerformance:
    def test_zero_trades_returns_skeleton(self, client):
        with patch.object(goliath_routes, "_safe_query", return_value=[]):
            r = client.get("/api/goliath/performance")
        data = r.json()
        assert data["platform"]["trades"] == 0
        assert data["platform"]["total_pnl"] == 0.0
        assert data["platform"]["win_rate"] is None
        assert len(data["instances"]) == 5

    def test_aggregates_wins_losses(self, client):
        rows = [
            ("GOLIATH-MSTU", 25.0, "T2"),
            ("GOLIATH-MSTU", -10.0, "T1"),
            ("GOLIATH-MSTU", 5.0, "T2"),
            ("GOLIATH-TSLL", -3.0, "T7"),
        ]
        with patch.object(goliath_routes, "_safe_query", return_value=rows):
            r = client.get("/api/goliath/performance")
        data = r.json()
        mstu = next(i for i in data["instances"] if i["instance_name"] == "GOLIATH-MSTU")
        assert mstu["trades"] == 3
        assert mstu["wins"] == 2
        assert mstu["losses"] == 1
        assert mstu["total_pnl"] == 20.0
        assert mstu["win_rate"] == pytest.approx(2 / 3)
        assert mstu["trigger_breakdown"]["T2"] == 2


# ---- /gate-failures ------------------------------------------------------

class TestGateFailures:
    def test_empty(self, client):
        with patch.object(goliath_routes, "_safe_query", return_value=[]):
            r = client.get("/api/goliath/gate-failures")
        assert r.json() == {"failures": [], "count": 0}

    def test_renders_failure_with_jsonb_dict_safety(self, client):
        ts = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        rows = [
            (1, ts, "MSTU", "MSTR", "G03", "FAIL",
             ["G01", "G02"], None, "no wall present", {"spot": 9.5}),
        ]
        with patch.object(goliath_routes, "_safe_query", return_value=rows):
            r = client.get("/api/goliath/gate-failures?letf=MSTU&gate=G03")
        data = r.json()
        assert data["count"] == 1
        f = data["failures"][0]
        assert f["failed_gate"] == "G03"
        assert f["gates_passed_before_failure"] == ["G01", "G02"]
        assert f["context"] == {"spot": 9.5}


# ---- /scan-activity / /logs ----------------------------------------------

class TestScanActivityAndLogs:
    def test_scan_activity_filters_to_eval_events(self, client):
        captured = {}

        def fake_query(sql, params):
            captured["sql"] = sql
            return []

        with patch.object(goliath_routes, "_safe_query", side_effect=fake_query):
            r = client.get("/api/goliath/scan-activity")
        assert r.status_code == 200
        assert "ENTRY_EVAL" in captured["sql"]
        assert "MANAGEMENT_EVAL" in captured["sql"]

    def test_logs_passes_event_type_filter(self, client):
        captured = {}

        def fake_query(sql, params):
            captured["params"] = params
            return []

        with patch.object(goliath_routes, "_safe_query", side_effect=fake_query):
            r = client.get("/api/goliath/logs?event_type=entry_filled&instance=GOLIATH-MSTU")
        assert r.status_code == 200
        # Uppercased + appears in params before LIMIT
        assert "ENTRY_FILLED" in captured["params"]
        assert "GOLIATH-MSTU" in captured["params"]


# ---- /calibration / /kill-state / /config --------------------------------

class TestStaticEndpoints:
    def test_calibration_lists_4_parameters_with_tags(self, client):
        r = client.get("/api/goliath/calibration")
        assert r.status_code == 200
        data = r.json()
        assert data["phase"] == "1.5"
        params = data["parameters"]
        assert set(params.keys()) == {
            "wall_concentration_threshold",
            "tracking_error_fudge",
            "drag_coefficient",
            "realized_vol_window_days",
        }
        # vol_window was the one Phase-1.5-step-9 adjustment.
        assert params["realized_vol_window_days"]["value"] == 20
        assert params["realized_vol_window_days"]["spec_default"] == 30
        assert params["realized_vol_window_days"]["tag"] == "CALIB-ADJUST"

    def test_kill_state_no_active_no_history(self, client):
        with patch.object(goliath_routes, "_safe_query", return_value=[]):
            r = client.get("/api/goliath/kill-state")
        data = r.json()
        assert data["active_count"] == 0
        assert data["platform_killed"] is False
        assert data["killed_instances"] == []
        assert data["history"] == []

    def test_kill_state_active_platform_kill(self, client):
        ts = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)
        with patch.object(
            goliath_routes, "_safe_query",
            side_effect=[
                [("PLATFORM", None, "P1", "max DD", {}, ts)],  # active
                [],   # history
            ],
        ):
            r = client.get("/api/goliath/kill-state")
        data = r.json()
        assert data["active_count"] == 1
        assert data["platform_killed"] is True

    def test_config_returns_global_plus_instance_defaults(self, client):
        r = client.get("/api/goliath/config")
        data = r.json()
        assert data["global"]["paper_only"] is True
        assert data["global"]["account_capital"] == 5000.0
        assert data["instance_defaults"]["realized_vol_window_days"] == 20
        assert len(data["instances"]) == 5
