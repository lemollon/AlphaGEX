from datetime import datetime, timedelta, timezone
import requests

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


def test_theta_chain_joins_by_contract_and_rejects_stale_greeks(monkeypatch):
    now = datetime(2026, 9, 29, 14, 45, tzinfo=timezone.utc)
    greeks = []
    oi = []
    for strike in range(720, 780):
        for right in ("call", "put"):
            contract = {"symbol": "SPY", "expiration": "2026-10-02",
                        "strike": str(strike), "right": right}
            greeks.append({**contract, "timestamp": "2026-09-29T10:44:30",
                           "gamma": "0.02", "implied_vol": "0.20"})
            oi.append({**contract, "timestamp": "2026-09-29T06:30:00",
                       "open_interest": "100"})
    greeks[0]["timestamp"] = "2026-09-29T10:40:00"
    oi = list(reversed(oi))
    monkeypatch.setattr(market_structure, "_OI_CACHE", {})
    paths = []
    def rows(path, params):
        paths.append(path)
        return greeks if "greeks" in path else oi
    monkeypatch.setattr(market_structure, "_theta_rows", rows)
    result = market_structure.fetch_theta_chain("SPY", now)
    assert result["reason"] is None
    assert len(result["rows"]) == 119
    assert result["rows"][0]["callOpenInterest"] == 0
    assert result["rows"][0]["putOpenInterest"] == 100
    assert result["source_timestamp"].isoformat() == "2026-09-29T14:44:30+00:00"
    assert result["oi_timestamp"].isoformat() == "2026-09-29T10:30:00+00:00"
    again = market_structure.fetch_theta_chain("SPY", now)
    assert again["reason"] is None
    assert paths.count("/v3/option/snapshot/open_interest") == 1


def test_theta_chain_rejects_previous_day_oi(monkeypatch):
    monkeypatch.setattr(market_structure, "_OI_CACHE", {})
    monkeypatch.setattr(market_structure, "_theta_rows", lambda path, params: [
        {"symbol": "XSP", "expiration": "2026-09-29", "strike": "765",
         "right": "call", "timestamp": "2026-09-29T10:00:00", "gamma": "0.01"}
    ] if "greeks" in path else [
        {"symbol": "XSP", "expiration": "2026-09-29", "strike": "765",
         "right": "call", "timestamp": "2026-09-28T06:30:00",
         "open_interest": "100"}
    ])
    result = market_structure.fetch_theta_chain(
        "XSP", datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc))
    assert result["reason"] == "stale_or_missing_theta_open_interest"


def test_theta_standard_iv_calculates_gamma_when_pro_unavailable(monkeypatch):
    now = datetime(2026, 9, 29, 14, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(market_structure, "_OI_CACHE", {})
    def rows(path, params):
        if path.endswith("/all"):
            raise requests.HTTPError("Pro entitlement unavailable")
        items = []
        for strike in range(720, 780):
            for right in ("call", "put"):
                row = {"expiration": "2026-10-02", "strike": str(strike),
                       "right": right}
                if "open_interest" in path:
                    row.update(timestamp="2026-09-29T06:30:00",
                               open_interest="100")
                else:
                    row.update(timestamp="2026-09-29T10:44:30",
                               implied_vol="0.20", underlying_price="750")
                items.append(row)
        return items
    monkeypatch.setattr(market_structure, "_theta_rows", rows)
    result = market_structure.fetch_theta_chain("SPY", now)
    assert result["reason"] is None
    assert result["gamma_source"] == "ThetaData Standard IV, locally calculated gamma"
    assert len(result["rows"]) == 120
    assert all(row["gamma"] > 0 for row in result["rows"])


def test_theta_index_timestamp_is_eastern(monkeypatch):
    monkeypatch.setattr(market_structure, "_index_prices", lambda symbols: {
        "SPX": {"timestamp": "2026-09-29T10:00:00", "price": "7700.5"}})
    spot = market_structure.fetch_spot(
        "SPX", datetime(2026, 9, 29, 14, 0, 10, tzinfo=timezone.utc))
    assert spot["fresh"] is True
    assert spot["age_seconds"] == 10


def test_index_permission_denial_preserves_fresh_tradier_vix(monkeypatch):
    now = datetime.now(timezone.utc)
    denied = requests.Response()
    denied.status_code = 403
    def forbidden(_symbols):
        raise requests.HTTPError("forbidden", response=denied)
    monkeypatch.setattr(market_structure, "_index_prices", forbidden)
    monkeypatch.setattr(market_structure, "_token", lambda name: "test-token")

    class QuoteResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {"quotes": {"quote": {"symbol": "VIX", "last": 16.2,
                                          "trade_date": int(now.timestamp() * 1000)}}}

    monkeypatch.setattr(market_structure.requests, "get",
                        lambda *args, **kwargs: QuoteResponse())
    result = market_structure.fetch_vol_indices(now)
    assert result["available"] is True
    assert result["source"] == "Tradier VIX quote"
    assert result["provider_error"] == "ThetaData index permission denied"
    assert result["indices"]["VIX"]["price"] == 16.2
    assert "VIX9D" not in result["indices"]
    assert market_structure.fetch_spot("SPX", now)["reason"] == (
        "ThetaData index permission denied")


def test_index_gamma_can_use_fresh_theta_option_underlying(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [{"underlying_price": 7700.0, "timestamp": now,
             "strike": 7700.0, "dte": 0, "gamma": 0.01,
             "callOpenInterest": 100, "putOpenInterest": 0}
            for _ in range(100)]
    chain = {"rows": rows, "source_timestamp": now, "oi_timestamp": now,
             "matched_rows": 100, "recent_greeks_rows": 100,
             "gamma_source": "ThetaData Standard IV, locally calculated gamma"}
    monkeypatch.setattr(market_structure, "fetch_spot", lambda s, n: {
        "fresh": False, "reason": "ThetaData index permission denied"})
    monkeypatch.setattr(market_structure, "fetch_theta_chain", lambda s, n: chain)
    result = market_structure.build_gamma_snapshot("SPX", now)
    assert result["available"] is True
    assert result["spot"] == 7700.0
    assert result["spot_source"] == "ThetaData option-chain underlying price"

    rows[0]["underlying_price"] = 8000.0
    rejected = market_structure.build_gamma_snapshot("SPX", now)
    assert rejected["available"] is False
    assert rejected["reason"] == "ThetaData index permission denied"


def test_iv_only_surface_builds_term_skew_and_expected_move(monkeypatch):
    now = datetime(2026, 10, 2, 14, 45, tzinfo=timezone.utc)
    payload = []
    # A small, realistic IV-only grid.  No vendor delta or gamma fields are
    # required; the surface code calculates the 25-delta selection locally.
    for expiry, dte, base_iv in (
        ("2026-10-02", 0, 0.15),
        ("2026-10-05", 3, 0.16),
        ("2026-10-16", 14, 0.18),
        ("2026-11-02", 31, 0.20),
    ):
        for strike in range(735, 767, 2):
            for right in ("call", "put"):
                payload.append({
                    "expiration": expiry, "strike": str(strike), "right": right,
                    "timestamp": "2026-10-02T10:44:30",
                    "implied_vol": str(base_iv + (0.015 if right == "put" else 0.0)),
                })
    monkeypatch.setattr(market_structure, "fetch_spot", lambda symbol, current: {
        "price": 750.0, "fresh": True, "source_timestamp": now,
        "source": "Tradier ETF quote",
    })
    monkeypatch.setattr(market_structure, "_theta_rows", lambda path, params: payload)
    monkeypatch.setattr(market_structure, "fetch_intraday_realized_volatility",
                        lambda symbol, current: {"available": True,
                                                 "realized_vol_60m": 0.12,
                                                 "bars": 60,
                                                 "source_timestamp": current.isoformat(),
                                                 "bar_timestamp": current.isoformat(),
                                                 "method": "test", "source": "test"})
    result = market_structure.build_volatility_surface("SPY", now)
    assert result["available"] is True
    assert result["confidence"] == "HIGH"
    assert result["atm_iv"] == 0.1675
    assert result["iv_0dte"] == 0.1575
    assert result["iv_1_5dte"] == 0.1675
    assert result["iv_6_20dte"] == 0.1875
    assert result["iv_21_365dte"] == 0.2075
    assert result["skew_25d"] is not None
    assert result["skew_25d"] > 0
    assert result["expected_move_dollars_1d"] > 0
    assert result["expected_move_low"] < 750 < result["expected_move_high"]
    assert result["realized_vol_60m"] == 0.12
    assert result["iv_minus_realized_vol"] == result["atm_iv"] - 0.12


def test_iv_snapshot_without_provider_timestamp_uses_fresh_receipt_time(monkeypatch):
    now = datetime(2026, 10, 2, 14, 45, tzinfo=timezone.utc)
    payload = []
    for strike in range(735, 767, 2):
        for right in ("call", "put"):
            payload.append({
                "expiration": "2026-10-16", "strike": str(strike),
                "right": right, "implied_vol": "0.18",
            })
    monkeypatch.setattr(market_structure, "fetch_spot", lambda symbol, current: {
        "price": 750.0, "fresh": True, "source_timestamp": now,
    })
    monkeypatch.setattr(market_structure, "_theta_rows", lambda path, params: payload)
    monkeypatch.setattr(market_structure, "fetch_intraday_realized_volatility",
                        lambda symbol, current: {"available": False,
                                                 "reason": "insufficient_intraday_bars"})
    result = market_structure.build_volatility_surface("SPY", now)
    assert result["available"] is True
    assert result["n_rows"] == len(payload)


def test_realized_volatility_uses_fresh_rth_one_minute_tape():
    now = datetime(2026, 10, 2, 15, 31, 20, tzinfo=timezone.utc)  # 10:31:20 ET
    start = now - timedelta(minutes=60)
    bars = []
    for i in range(61):
        stamp = start + timedelta(minutes=i)
        bars.append({"time": stamp.astimezone(market_structure.ET).replace(tzinfo=None).isoformat(),
                     "close": 750.0 * (1.0001 ** i)})
    result = market_structure._realized_volatility_from_bars(bars, now)
    assert result["available"] is True
    assert result["bars"] == 60
    assert result["realized_vol_60m"] > 0
    assert result["bar_age_seconds"] == 20


def test_realized_volatility_rejects_stale_tape():
    now = datetime(2026, 10, 2, 15, 35, tzinfo=timezone.utc)
    bars = [{"time": "2026-10-02T10:30:00", "close": 750.0}]
    result = market_structure._realized_volatility_from_bars(bars, now)
    assert result["available"] is False
    assert result["reason"] == "stale_timesales_bar"


def test_surface_read_explains_day_and_forward_volatility_pricing():
    read = market_structure._surface_read(
        atm_iv=0.12, realized_vol=0.09, skew=0.04,
        iv_0dte=0.19, iv_1_5dte=0.13, iv_6_20dte=0.16,
        iv_21_365dte=0.20,
    )
    assert read["available"] is True
    assert read["day_state"] == "PREMIUM_RICH"
    assert read["skew_state"] == "DOWNSIDE_HEDGE_PREMIUM"
    assert "6–20DTE volatility is elevated" in read["forward_meaning"]
    assert "not proof" in read["forward_meaning"]



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
            "reason": None if symbol == "SPY" else "ThetaData chain failure",
            "captured_at": current.isoformat(),
            "net_gex_b": 1.0 if symbol == "SPY" else None,
        }

    persisted = []
    monkeypatch.setattr(market_structure, "build_gamma_snapshot", fake_snapshot)
    monkeypatch.setattr(market_structure, "persist_snapshot",
                        lambda snapshot: persisted.append(snapshot))
    surfaces = []
    monkeypatch.setattr(market_structure, "build_volatility_surface", lambda symbol, current: {
        "symbol": symbol, "available": True, "confidence": "HIGH",
        "captured_at": current.isoformat(), "atm_iv": 0.2,
    })
    monkeypatch.setattr(market_structure, "persist_surface",
                        lambda surface: surfaces.append(surface))

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
    assert any(item["reason"] == "ThetaData chain failure" for item in persisted)
    assert set(out["surface"]) == {"SPY", "QQQ"}
    assert len(surfaces) == 2
