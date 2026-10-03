from datetime import datetime, timedelta, timezone
import json

from backend import market_structure as ms
from backend.report_contract import REQUIREMENTS, validate_rendered_report


def test_flow_midpoint_locked_crossed_and_nonfinite_are_unclassified():
    assert ms._classify_trade_side(1.005, 1.00, 1.01) == "mid"
    for price, bid, ask in ((1, 1, 1), (1, 1.1, 1), (float("nan"), 1, 1.1)):
        assert ms._classify_trade_side(price, bid, ask) == "unclassified"


def test_flow_evidence_reconciles_categories_and_exact_prints():
    now = datetime(2026, 10, 2, 15, 0, 30, tzinfo=timezone.utc)
    base = {"expiration": "2026-10-16", "strike": "770", "right": "call",
            "timestamp": "2026-10-02T11:00:20", "bid": "1.00", "ask": "1.10", "size": "10"}
    rows = [{**base, "price": "1.10"}, {**base, "price": "1.00"},
            {**base, "price": "1.05"}, {**base, "price": "1.10", "quote_timestamp": "2026-10-02T10:59:00"},
            {**base, "price": "nan"}, {**base, "price": "1.10", "timestamp": "2026-10-02T11:01:00"}]
    result = ms.summarize_flow_evidence(rows, now.astimezone(ms.ET), now)
    bucket = result["buckets"]["6_20dte"]
    assert result["total_contracts"] == 40
    assert result["classified_contracts"] == 20
    assert result["unclassified_contracts"] == 20
    assert result["rejected_rows"] == 2
    assert sum(x["contracts"] for x in bucket.values()) == 40
    assert sum(x["premium"] for x in bucket.values()) == result["total_premium"] == 4250
    assert result["classified_contract_fraction"] == .5
    assert {x["strike"] for x in result["concentrations"]} == {770}
    assert all(x["latest_print"]["bid"] == 1 for x in result["concentrations"])


def test_surface_and_flow_persistence_preserve_detail(monkeypatch):
    calls = []
    class Connection:
        def execute(self, sql, params=None):
            calls.append((str(sql), params))
        def __enter__(self): return self
        def __exit__(self, *args): return False
    class Engine:
        def begin(self): return Connection()
    monkeypatch.setattr(ms, "engine", Engine())
    monkeypatch.setattr(ms, "ensure_tables", lambda: None)
    stamp = "2026-10-02T15:00:00+00:00"
    smile = {"available": True, "put_25d_iv": .15, "atm_iv": .12, "call_25d_iv": .13}
    ms.persist_surface({"symbol": "SPY", "captured_at": stamp, "smile": smile,
                        "surface_points": [{"strike": 770, "iv": .12}]})
    assert json.loads(calls[-1][1]["surface_json"])["smile"] == smile
    evidence = {"total_contracts": 100, "concentrations": [{"strike": 770}]}
    ms.persist_trade_quote_flow({"symbol": "SPY", "captured_at": stamp, "evidence": evidence})
    assert json.loads(calls[-1][1]["evidence"]) == evidence


def test_medium_confidence_surface_is_usable_only_when_fresh(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(ms, "_latest_surface", lambda s: {
        "confidence": "MEDIUM", "source_timestamp": (now - timedelta(seconds=30)).isoformat()})
    assert ms._cached_surface_payload("SPY", now)["available"]
    assert not ms._cached_surface_payload("SPY", now + timedelta(seconds=91))["available"]


def test_png_filename_text_does_not_satisfy_image_embedding():
    now = datetime.now(timezone.utc)
    blocks = {name: {field: {"status": "unavailable", "reason": "test"} for field in fields}
              for name, fields in REQUIREMENTS.items()}
    blocks["visuals"]["market_map_png"] = {"status": "historical", "value": "map.png",
        "source_timestamp": now.isoformat(), "age_seconds": 0}
    markdown = "\n".join("## " + name.replace("_", " ") + "\n" + "\n".join(fields)
                          for name, fields in REQUIREMENTS.items()) + "\nmap.png"
    payload = {"report_blocks": blocks, "report_markdown": markdown}
    assert "market_map_png: PNG not embedded" in validate_rendered_report(payload)["errors"]
    payload["report_markdown"] += "\n![Market map](map.png)"
    assert validate_rendered_report(payload)["publishable"]


def test_readiness_uses_persisted_smile_instead_of_hardcoded_failure(monkeypatch):
    surface = {"available": True, "smile": {"available": True, "put_25d_iv": .15,
        "atm_iv": .12, "call_25d_iv": .13, "put_strike": 760, "atm_strike": 770, "call_strike": 780}}
    monkeypatch.setattr(ms, "_cached_surface_payload", lambda *a: surface)
    monkeypatch.setattr(ms, "_cached_gamma_payload", lambda *a: {"available": False})
    monkeypatch.setattr(ms, "_cached_vol_payload", lambda *a: {})
    monkeypatch.setattr(ms, "fetch_cross_asset", lambda *a: {})
    monkeypatch.setattr(ms, "_latest_trade_quote_flow", lambda *a: None)
    result = ms.report_readiness()
    assert result["required_checks"]["smile_wings"]
    assert "smile_wings" not in result["outstanding_producers"]
    assert not result["all_requested_ready"]
