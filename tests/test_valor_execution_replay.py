"""Regression checks for actual-method replay, overnight boundaries and SAR guards."""
import csv
import gzip
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / "scripts/replay_valor_execution.py"
spec = importlib.util.spec_from_file_location("valor_execution_replay", path)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
m = replay.models


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=replay.CT)


def signal(time, direction="LONG", price=7800, scan_id="a"):
    return dict(scan_id=scan_id, scan_time=time.isoformat(), underlying_symbol="MES",
                signal_direction=direction, underlying_price=str(price), signal_confidence="0.7",
                signal_source="GEX_MOMENTUM", gamma_regime="NEGATIVE", signal_win_probability="0.6")


def engine(time="2026-09-15T09:00", sar=True, slip=0):
    e = replay.make_engine(m.ValorConfig(), slip, 3, sar)
    e.clock.current = at(time)
    e.price = 7800
    e.enter_recorded_signal(signal(e.clock.current - timedelta(seconds=30)))
    return e


@pytest.mark.parametrize("time,overnight,stop", [
    ("2026-09-15T07:59", True, 8), ("2026-09-15T08:01", False, 15),
    ("2026-09-15T14:59", False, 15), ("2026-09-15T15:01", True, 8),
])
def test_actual_overnight_stop_builder(time, overnight, stop):
    e = engine(time)
    assert e._is_overnight_session() is overnight
    assert e.position.entry_price - e.position.initial_stop == stop
    assert e.position.stop_type == ("NL_OVERNIGHT" if overnight else "NO_LOSS_TRAIL")


@pytest.mark.parametrize("hour,expected", [(8, False), (15, True)])
def test_exact_session_boundary(hour, expected):
    e = engine()
    e.clock.current = e.clock.current.replace(hour=hour, minute=0)
    assert e._is_overnight_session() is expected


def test_sar_closes_but_cannot_bypass_production_cooldown():
    e = engine()
    e.clock.current += timedelta(seconds=15)
    e.price = 7798
    assert e._manage_position(e.position, e.price)
    assert e.position is None
    assert e.trades[0]["status"] == "sar_closed"
    assert e.trades[0]["net_pnl"] == -13
    assert e.counts["sar_blocked_cooldown"] == 1
    e.clock.current += timedelta(seconds=59)
    assert e.entry_block() == "cooldown"
    e.clock.current += timedelta(seconds=1)
    assert e.entry_block() is None


def test_future_high_is_not_used_to_suppress_sar():
    bars = {at("2026-09-15T09:00"): (7800, 7804, 7796, 7800)}
    signals = {next(iter(bars)): [signal(at("2026-09-15T08:59:30"))]}
    reports = {}
    for path in ("OHLC", "OLHC"):
        report, trades, _ = replay.run_scenario(bars, signals, m.ValorConfig(), path, 15, 0, 3, True)
        reports[path] = report
    assert reports["OLHC"]["counts"]["sar_blocked_cooldown"] == 1
    assert reports["OHLC"]["counts"].get("sar_blocked_cooldown", 0) == 0


def test_gap_fills_at_observed_price_and_costs_are_not_double_charged():
    e = engine(sar=False, slip=1)
    assert e.position.entry_price == 7800.25
    e.price = 7790
    e.clock.current += timedelta(hours=1)
    e._manage_position(e.position, e.price)
    trade = e.trades[0]
    assert trade["exit_price"] == 7789.75
    assert trade["requested_exit_price"] == 7795.25
    assert trade["net_pnl"] == -55.5


def test_trailing_activation_and_ratchet_reuse_production_methods():
    e = engine(sar=False)
    for price in (7801, 7804, 7802):
        e.price = price
        e.clock.current += timedelta(seconds=15)
        e._manage_position(e.position, price)
    assert e.position is None
    assert e.trades[0]["status"] == "trailed"
    assert e.trades[0]["requested_exit_price"] == 7802.5
    assert e.trades[0]["exit_price"] == 7802


def test_watchdog_precedes_sar_and_open_position_remains_marked():
    e = engine()
    e.clock.current += timedelta(hours=24)
    e.price = 7790
    e._manage_position(e.position, e.price)
    assert e.trades[0]["reason"] == "STALE_WATCHDOG_24H"
    assert e.counts["sar_blocked_cooldown"] == 0
    bars = {at("2026-09-15T09:00"): (7800, 7800, 7800, 7800)}
    rows = {next(iter(bars)): [signal(at("2026-09-15T08:59:30"))]}
    report, trades, _ = replay.run_scenario(bars, rows, m.ValorConfig(), "OHLC", 15, 0, 3, True)
    assert not trades
    assert report["unresolved_end_position"]["entry_price"] == 7800


def test_three_losses_pause_normal_entries():
    e = engine(sar=False)
    for i in range(3):
        e.price = 7795
        e.clock.current += timedelta(seconds=15)
        e._manage_position(e.position, e.price)
        e.clock.current += timedelta(seconds=60)
        if i < 2:
            e.price = 7800
            e.enter_recorded_signal(signal(e.clock.current, scan_id=str(i)))
    assert e.entry_block() == "loss_streak_pause"
    e.clock.current = e.pause_until
    assert e.entry_block() is None


def test_loader_rejects_missing_minutes_and_does_not_use_signal_minute(tmp_path):
    start = at("2026-09-15T09:00")
    with gzip.open(tmp_path / "MESZ6_1m.csv.gz", "wt") as handle:
        writer = csv.DictWriter(handle, fieldnames=["contract", "time_utc", "open", "high", "low", "close"])
        writer.writeheader()
        for i in (0, 1):
            writer.writerow(dict(contract="/MESZ6", time_utc=(start + timedelta(minutes=i)).isoformat(),
                                 open=7800, high=7801, low=7799, close=7800))
    with gzip.open(tmp_path / "mes_scan_inputs.jsonl.gz", "wt") as handle:
        handle.write(json.dumps(signal(start + timedelta(seconds=1))) + "\n")
    _, signals, _ = replay.load_inputs(tmp_path, start, start + timedelta(minutes=2))
    assert start not in signals
    assert start + timedelta(minutes=1) in signals
    with pytest.raises(ValueError, match="missing open-market"):
        replay.load_inputs(tmp_path, start, start + timedelta(minutes=3))


def test_calendar_closures_and_weekend():
    assert not replay.market_open(at("2026-09-15T16:00"))
    assert replay.market_open(at("2026-09-15T17:00"))
    assert not replay.market_open(at("2026-09-19T10:00"))
    assert not replay.market_open(at("2026-09-20T16:59"))
    assert replay.market_open(at("2026-09-20T17:00"))


def test_cli_writes_twelve_labeled_scenarios_without_service_imports(tmp_path, monkeypatch):
    start = at("2026-09-15T09:00")
    with gzip.open(tmp_path / "MESZ6_1m.csv.gz", "wt") as handle:
        writer = csv.DictWriter(handle, fieldnames=["contract", "time_utc", "open", "high", "low", "close"])
        writer.writeheader()
        for i in range(3):
            writer.writerow(dict(contract="MESZ6", time_utc=(start + timedelta(minutes=i)).isoformat(),
                                 open=7800, high=7804, low=7796, close=7800))
    with gzip.open(tmp_path / "mes_scan_inputs.jsonl.gz", "wt") as handle:
        handle.write(json.dumps(signal(start + timedelta(seconds=1))) + "\n")
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(path), "--data-dir", str(tmp_path),
                             "--start", start.isoformat(), "--end", (start + timedelta(minutes=3)).isoformat(),
                             "--round-trip-fee", "3", "--fee-source", "assumed"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(next(tmp_path.glob("valor_execution_*/summary.json")).read_text())
    assert len(report["scenarios"]) == 12
    assert report["production_ready"] is False
    assert report["fee_source"] == "assumed"
    assert report["source_sha256"]["trader.py"]
