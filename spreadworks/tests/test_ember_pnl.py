import json

from backend.ember import astra_live, pnl
from backend.ember import runtime as xsp_runtime
from backend.ember.legacy import call_diag, divhike, night_shift


def _write_ledger(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(row.get(col, "")) for col in header))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_csv_ledger_sums_real_trades_and_excludes_dry_run(tmp_path, monkeypatch):
    path = tmp_path / "ledger.csv"
    _write_ledger(
        path,
        ["trade_date", "pnl_fill_to_fill", "dry_run"],
        [
            {"trade_date": "2026-09-10", "pnl_fill_to_fill": "12.50", "dry_run": "0"},
            {"trade_date": "2026-09-11", "pnl_fill_to_fill": "-4.00", "dry_run": "0"},
            {"trade_date": "2026-09-12", "pnl_fill_to_fill": "999.00", "dry_run": "1"},
        ],
    )
    result = pnl._read_csv_ledger(
        path, pnl_col="pnl_fill_to_fill", date_col="trade_date", prefix="CALLDIAG"
    )
    assert result["available"] is True
    assert result["total_pnl"] == 8.50
    assert result["trade_count"] == 2
    assert result["trades"] == [
        {"date": "2026-09-10", "pnl": 12.50},
        {"date": "2026-09-11", "pnl": -4.00},
    ]


def test_csv_ledger_missing_file_reports_unavailable_not_zero(tmp_path):
    result = pnl._read_csv_ledger(
        tmp_path / "missing.csv", pnl_col="pnl_usd", date_col="date", prefix="NIGHT"
    )
    assert result["available"] is False
    assert result["total_pnl"] is None
    assert result["trades"] == []


def test_xsp_flow_reads_the_postgres_mirror_not_the_paper_ledger(monkeypatch):
    state = {
        "realized_pnl": 42.75,
        "positions": [
            {"state": "closed"},
            {"state": "closed"},
            {"state": "open"},
        ],
    }
    store = {pnl.XSP_STATE_KEY: json.dumps(state)}
    monkeypatch.setattr(xsp_runtime, "_config_get", store.get)
    result = pnl._read_xsp_flow()
    assert result["source"] == "postgres_mirror"
    assert result["available"] is True
    assert result["total_pnl"] == 42.75
    assert result["trade_count"] == 2
    # Per-trade breakdown is intentionally not fabricated for xsp_flow.
    assert result["trades"] == []


def test_xsp_flow_missing_mirror_is_unavailable_not_zero(monkeypatch):
    monkeypatch.setattr(xsp_runtime, "_config_get", lambda key: None)
    result = pnl._read_xsp_flow()
    assert result["available"] is False
    assert result["total_pnl"] is None


def test_astra3_reads_sleeve_realized_pnl_and_capped_history(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "sleeve": {"realized_pnl": 103.50, "completed_trades": 3},
        "history": [
            {"closed_at_ct": "2026-09-20T10:00:00", "pnl": 50.0},
            {"closed_at_ct": "2026-09-21T10:00:00", "pnl": -10.0},
            {"closed_at_ct": "2026-09-22T10:00:00", "pnl": 63.50},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(astra_live, "STATE_PATH", state_path)
    result = pnl._read_astra3()
    assert result["available"] is True
    assert result["total_pnl"] == 103.50
    assert result["trade_count"] == 3
    assert len(result["trades"]) == 3
    assert "NOT mirrored to Postgres" in result["caveat"]


def test_astra3_missing_state_is_unavailable_not_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(astra_live, "STATE_PATH", tmp_path / "missing-state.json")
    result = pnl._read_astra3()
    assert result["available"] is False
    assert result["total_pnl"] is None


def test_aggregate_pnl_never_fabricates_tv_book_or_spike(monkeypatch):
    # Force every real source to "no data" so the aggregate is driven purely
    # by tv_book/spike's explicit no-ledger-exists branches.
    monkeypatch.setattr(call_diag, "LEDGER_CSV", call_diag.LEDGER_CSV.parent / "does-not-exist.csv")
    monkeypatch.setattr(night_shift, "LEDGER_CSV", night_shift.LEDGER_CSV.parent / "does-not-exist.csv")
    monkeypatch.setattr(divhike, "LEDGER_CSV", divhike.LEDGER_CSV.parent / "does-not-exist.csv")
    monkeypatch.setattr(xsp_runtime, "_config_get", lambda key: None)
    monkeypatch.setattr(astra_live, "STATE_PATH", astra_live.STATE_PATH.parent / "does-not-exist.json")

    result = pnl.aggregate_pnl()
    assert result["total_realized_pnl"] == 0.0
    assert result["strategies_with_data"] == []
    assert set(result["strategies_without_data"]) == {
        "call_diag", "night_shift", "divhike", "xsp_flow", "astra3_live",
        "tv_book", "spike",
    }
    assert result["by_strategy"]["tv_book"]["total_pnl"] is None
    assert result["by_strategy"]["spike"]["total_pnl"] is None
    assert result["trade_series"] == []


def test_aggregate_pnl_sums_only_strategies_with_real_data(tmp_path, monkeypatch):
    call_diag_csv = tmp_path / "call_diag_ledger.csv"
    _write_ledger(
        call_diag_csv,
        ["trade_date", "pnl_fill_to_fill", "dry_run"],
        [{"trade_date": "2026-09-01", "pnl_fill_to_fill": "10.00", "dry_run": "0"}],
    )
    night_csv = tmp_path / "night_ledger.csv"
    _write_ledger(
        night_csv,
        ["date", "pnl_usd", "dry_run"],
        [{"date": "2026-09-02", "pnl_usd": "5.00", "dry_run": "0"}],
    )
    divhike_csv = tmp_path / "divhike_ledger.csv"
    _write_ledger(divhike_csv, ["exit_date", "pnl_usd", "dry_run"], [])

    monkeypatch.setattr(call_diag, "LEDGER_CSV", call_diag_csv)
    monkeypatch.setattr(night_shift, "LEDGER_CSV", night_csv)
    monkeypatch.setattr(divhike, "LEDGER_CSV", divhike_csv)
    monkeypatch.setattr(xsp_runtime, "_config_get", lambda key: json.dumps({"realized_pnl": 7.25, "positions": []}))
    monkeypatch.setattr(astra_live, "STATE_PATH", tmp_path / "does-not-exist.json")

    result = pnl.aggregate_pnl()
    assert result["total_realized_pnl"] == 22.25  # 10.00 + 5.00 + 0.00 (empty) + 7.25
    assert set(result["strategies_with_data"]) == {"call_diag", "night_shift", "divhike", "xsp_flow"}
    assert result["trade_series"] == [
        {"strategy": "call_diag", "date": "2026-09-01", "pnl": 10.00},
        {"strategy": "night_shift", "date": "2026-09-02", "pnl": 5.00},
    ]
