import base64
import gzip
import json
import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from backend.ember import fleet_runtime as fleet
from backend.ember import astra_live, astra_runtime
from backend.ember import xsp_flow_live
from backend.ember.legacy import divhike, night_shift, spike


def test_night_uses_its_own_envelope_and_fails_closed():
    assert night_shift.buy_dollar_amount(150.0, 500.0, 20.0)[0] == 150.0
    assert night_shift.buy_dollar_amount(150.0, 120.0, 20.0)[0] == 100.0
    assert night_shift.buy_dollar_amount(None, 500.0, 20.0)[0] == 0.0
    assert night_shift.buy_dollar_amount(150.0, None, 20.0)[0] == 0.0


def test_seed_decoder_requires_a_json_object():
    spec = fleet.SPECS["night_shift"]
    encoded = base64.b64encode(json.dumps({"position": None}).encode()).decode()
    assert fleet._decode_seed(encoded, spec) == {"position": None}
    compressed = base64.b64encode(gzip.compress(json.dumps({"position": None}).encode())).decode()
    assert fleet._decode_seed(compressed, spec) == {"position": None}
    bad = base64.b64encode(json.dumps([1, 2]).encode()).decode()
    with pytest.raises(fleet.xsp_runtime.EmberRuntimeError):
        fleet._decode_seed(bad, spec)


def test_live_refuses_an_unmigrated_empty_state(monkeypatch):
    spec = fleet.SPECS["call_diag"]
    monkeypatch.setattr(fleet.xsp_runtime, "_validate_runtime", lambda live: None)
    with pytest.raises(fleet.xsp_runtime.EmberRuntimeError, match="migrated"):
        fleet._validate_live(spec, True, "fresh_empty")


def test_seed_replaces_earlier_empty_boot_once(monkeypatch, tmp_path):
    original = fleet.SPECS["call_diag"]
    spec = replace(original, state_path=tmp_path / "state.json")
    post_boot = {
        **spec.default_state,
        "2026-09-21": {"ref_ids": {"reconcile": "dry-run-only"}},
    }
    spec.state_path.write_text(json.dumps(post_boot), encoding="utf-8")
    seed = {"positions": [{"id": "owned-1", "state": "open"}], "legs": {}}
    encoded = base64.b64encode(json.dumps(seed).encode()).decode()
    monkeypatch.setenv(spec.seed_env, encoded)
    store = {spec.state_key: json.dumps(post_boot)}
    monkeypatch.setattr(fleet.xsp_runtime, "_config_get", store.get)
    monkeypatch.setattr(fleet.xsp_runtime, "_config_put", store.__setitem__)

    assert fleet._hydrate(spec) == "seed"
    hydrated = json.loads(spec.state_path.read_text(encoding="utf-8"))
    assert hydrated["positions"] == seed["positions"]
    assert hydrated["2026-09-21"] == post_boot["2026-09-21"]
    assert json.loads(store[spec.state_key]) == hydrated
    assert store[spec.seed_key]
    assert fleet._hydrate(spec) == "disk"


def test_seed_refuses_to_overwrite_nonempty_runtime_state(monkeypatch, tmp_path):
    original = fleet.SPECS["call_diag"]
    spec = replace(original, state_path=tmp_path / "state.json")
    current = {"positions": [{"id": "current", "state": "open"}], "legs": {}}
    seed = {"positions": [{"id": "old", "state": "open"}], "legs": {}}
    spec.state_path.write_text(json.dumps(current), encoding="utf-8")
    monkeypatch.setenv(
        spec.seed_env,
        base64.b64encode(json.dumps(seed).encode()).decode(),
    )
    monkeypatch.setattr(fleet.xsp_runtime, "_config_get", lambda key: None)

    with pytest.raises(fleet.xsp_runtime.EmberRuntimeError, match="conflicts"):
        fleet._hydrate(spec)


def test_status_expands_tv_book_into_rr_and_bounce_and_redacts(monkeypatch):
    monkeypatch.setattr(fleet, "_env_bool", lambda name, default=False: True)

    def fake_get(key):
        if key.endswith(".status"):
            return json.dumps({
                "updated_at": "2026-09-21T10:00:00-05:00",
                "mode": "RECONCILE", "return_code": 0,
                "last_log": "account=570892331 order_id=secret filled",
                "hydrate_source": "seed", "dependency_gaps": [],
            })
        return json.dumps({"positions": []})

    monkeypatch.setattr(fleet.xsp_runtime, "_config_get", fake_get)
    rows = fleet.read_status()
    assert {row["strategy"] for row in rows} == {
        "call_diag", "night_shift", "divhike", "rr", "bounce", "spike"
    }
    assert all("570892331" not in row["last_result"] for row in rows)
    assert all("secret" not in row["last_result"] for row in rows)


def test_all_enabled_jobs_are_registered(monkeypatch):
    for spec in fleet.SPECS.values():
        monkeypatch.setenv(spec.enabled_env, "1")

    class Scheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))

    scheduler = Scheduler()
    fleet.register(scheduler)
    ids = {kwargs["id"] for _, _, kwargs in scheduler.jobs}
    assert "ember_fleet_preflight" in ids
    assert not any(job_id.endswith("_preflight") for job_id in ids - {"ember_fleet_preflight"})
    assert {
        "ember_call_diag_cycle", "ember_night_shift_cycle", "ember_divhike_cycle",
        "ember_tv_book_cycle", "ember_spike_enter_cycle", "ember_spike_manage_cycle",
    }.issubset(ids)


def test_headless_claude_command_accepts_only_allowlisted_tools():
    tools = ["Read", "Write", "mcp__robinhood-trading__get_accounts"]
    command = xsp_flow_live.build_claude_command("claude", tools)
    assert command == [
        "claude", "-p",
        "--permission-mode", "acceptEdits",
        "--permission-prompts", "none",
        "--allowedTools", *tools,
    ]


def test_oauth_token_takes_precedence_over_legacy_api_key(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "depleted-api-key")
    child = xsp_flow_live.read_secret_environment()
    assert child["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-test-token"
    assert "ANTHROPIC_API_KEY" not in child


def test_xsp_stale_lock_recovers_when_scheduler_pid_is_still_alive(monkeypatch, tmp_path):
    lock = tmp_path / "xsp-flow.lock"
    lock.write_text(json.dumps({
        "pid": os.getpid(),
        "started_at": (datetime.now(UTC) - timedelta(minutes=13)).isoformat(),
    }))
    with xsp_flow_live.single_instance_lock(lock):
        assert json.loads(lock.read_text())["pid"] == os.getpid()
    assert not lock.exists()


def test_astra_live_requires_migrated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(astra_live, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setenv("ASTRA_LIVE_ARMED", "1")
    monkeypatch.setenv("ASTRA_LIVE_DRY_RUN", "0")
    monkeypatch.setenv("ASTRA_LIVE_FORWARD_GATE_OVERRIDE", "1")
    monkeypatch.delenv("ASTRA_LIVE_STATE_B64", raising=False)
    with pytest.raises(fleet.xsp_runtime.EmberRuntimeError, match="not migrated"):
        astra_runtime._hydrate_state()


def test_astra_state_seed_is_account_bound(monkeypatch, tmp_path):
    monkeypatch.setattr(astra_live, "STATE_PATH", tmp_path / "state.json")
    state = astra_live._default_state(astra_live.Config.load())
    monkeypatch.setenv(
        "ASTRA_LIVE_STATE_B64",
        base64.b64encode(json.dumps(state).encode()).decode(),
    )
    assert astra_runtime._hydrate_state() == "seed"
    assert json.loads(astra_live.STATE_PATH.read_text())["account"] == astra_live.ACCOUNT


def test_astra_jobs_are_registered_when_enabled(monkeypatch):
    monkeypatch.setenv("ASTRA_LIVE_ENABLED", "1")

    class Scheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))

    scheduler = Scheduler()
    astra_runtime.register(scheduler)
    ids = {kwargs["id"] for _, _, kwargs in scheduler.jobs}
    assert ids == {"ember_astra3_live_preflight", "ember_astra3_live_cycle"}


def test_cloud_status_redacts_provider_credentials():
    message = "403 for https://data.example.test/path?apiKey=secret-value&tickers=SPY"
    redacted = fleet._redact(message)
    assert "secret-value" not in redacted
    assert "apiKey=[redacted]&tickers=SPY" in redacted


def test_divhike_entry_eligibility_requires_today_bar(monkeypatch):
    today = date(2026, 9, 21)
    bars = []
    for i in range(63):
        stamp = datetime(2026, 6, 21, 12, tzinfo=divhike.CT).timestamp() + i * 86400
        bars.append({"t": stamp * 1000, "c": 5.0, "v": 1_000_000})
    bars[-1]["t"] = datetime(2026, 9, 21, 12, tzinfo=divhike.CT).timestamp() * 1000
    monkeypatch.setattr(divhike, "_polygon_get", lambda *a, **k: {"results": bars})
    ok, reason, metrics = divhike._entry_eligibility("TEST", today)
    assert ok, reason
    assert metrics["entry_close"] == 5.0
    assert metrics["trailing_dolvol_median"] == 5_000_000.0


def test_spike_cloud_snapshot_stays_on_curated_universe(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "not-a-real-key")
    monkeypatch.setenv("SPIKE_UNIVERSE", "AAA,BBB")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"tickers": [
                {"ticker": "AAA", "lastTrade": {"p": 0.5}, "day": {"v": 1_000_000},
                 "prevDay": {"c": 0.4}},
                {"ticker": "OUTSIDE", "lastTrade": {"p": 0.6}, "day": {"v": 2_000_000},
                 "prevDay": {"c": 0.5}},
            ]}

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    monkeypatch.setattr(spike, "_load_cloud_history", lambda symbols, today: {
        symbol: ([], "broker") for symbol in symbols
    })
    universe, history = spike._load_polygon_enter_market_data()
    assert [row["symbol"] for row in universe] == ["AAA"]
    assert set(history) == {"AAA", "BBB"}


def test_spike_cloud_prefers_complete_theta_feed(monkeypatch):
    monkeypatch.setenv("THETADATA_BASE_URL", "thetadata-proxy:10000")
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-fallback")
    monkeypatch.setenv("SPIKE_UNIVERSE", "AAA,BBB")
    theta_rows = [
        {"symbol": "AAA", "price": 1.0, "vol": 2_000_000, "provider": "theta"},
        {"symbol": "BBB", "price": 2.0, "vol": 2_000_000, "provider": "theta"},
    ]
    theta_history = {
        symbol: ([{"date": "2026-09-18", "close": 1.0, "volume": 1_000_000}], "theta")
        for symbol in ("AAA", "BBB")
    }
    monkeypatch.setattr(
        spike, "_load_theta_enter_market_data",
        lambda today, symbols: (theta_rows, theta_history),
    )
    monkeypatch.setattr(
        spike, "_load_polygon_enter_market_data",
        lambda *args, **kwargs: pytest.fail("Polygon must not run when Theta covers the universe"),
    )

    universe, history = spike._load_cloud_enter_market_data(date(2026, 9, 21))
    assert {row["provider"] for row in universe} == {"theta"}
    assert set(history) == {"AAA", "BBB"}


def test_spike_cloud_uses_polygon_only_for_theta_gaps(monkeypatch):
    monkeypatch.setenv("THETADATA_BASE_URL", "http://thetadata-proxy:10000")
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-fallback")
    monkeypatch.setenv("SPIKE_UNIVERSE", "AAA,BBB")
    monkeypatch.setattr(
        spike, "_load_theta_enter_market_data",
        lambda today, symbols: (
            [{"symbol": "AAA", "price": 1.0, "vol": 2_000_000, "provider": "theta"}],
            {"AAA": ([], "broker"), "BBB": ([], "broker")},
        ),
    )

    def polygon(symbols=None, today=None):
        assert symbols == ["BBB"]
        return ([{"symbol": "BBB", "price": 2.0, "vol": 3_000_000,
                  "provider": "polygon"}], {"BBB": ([], "broker")})

    monkeypatch.setattr(spike, "_load_polygon_enter_market_data", polygon)
    universe, _ = spike._load_cloud_enter_market_data(date(2026, 9, 21))
    assert {row["symbol"]: row["provider"] for row in universe} == {
        "AAA": "theta", "BBB": "polygon",
    }


def test_spike_dependency_accepts_theta_without_polygon(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.setenv("THETADATA_BASE_URL", "thetadata-proxy:10000")
    monkeypatch.setenv("SPIKE_UNIVERSE", "AAA")
    assert fleet._dependency_gaps(fleet.SPECS["spike"]) == []
