import csv
import io
import time as _time
from datetime import datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from thetadata_proxy import app as proxy


class Frame:
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def to_csv(self, index=False):
        assert index is False
        if not self.rows:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(self.rows[0]))
        writer.writeheader()
        writer.writerows(self.rows)
        return output.getvalue()


class FakeThetaClient:
    def __init__(self):
        self.calls = []

    def stock_history_eod(self, **kwargs):
        self.calls.append(("stock_history_eod", kwargs))
        return Frame([{
            "created": datetime(2026, 9, 18, 17, 15),
            "last_trade": datetime(2026, 9, 18, 16, 0),
            "open": 660.0,
            "high": 663.0,
            "low": 659.0,
            "close": 662.0,
            "volume": 10_000_000,
        }])

    def stock_snapshot_ohlc(self, **kwargs):
        self.calls.append(("stock_snapshot_ohlc", kwargs))
        return Frame([{
            "timestamp": datetime(2026, 9, 21, 10, 0),
            "symbol": "SPY",
            "open": 662.0,
            "high": 664.0,
            "low": 661.0,
            "close": 663.0,
            "volume": 1_000_000,
            "count": 100_000,
        }])


    def stock_history_ohlc(self, **kwargs):
        self.calls.append(("stock_history_ohlc", kwargs))
        return Frame([{
            "timestamp": "2025-04-11T15:03:00-04:00", "symbol": "SPY",
            "open": 533.9, "high": 534.0, "low": 533.8, "close": 533.95,
            "volume": 100, "count": 5, "vwap": 533.92,
        }])

    def option_list_expirations(self, **kwargs):
        self.calls.append(("option_list_expirations", kwargs))
        return Frame([{"symbol": "SPY", "expiration": "2026-09-21"}])

    def option_history_quote(self, **kwargs):
        self.calls.append(("option_history_quote", kwargs))
        return Frame([{
            "symbol": "SPY", "expiration": "2026-09-21", "strike": 663.0,
            "right": "call", "timestamp": "2026-09-21T15:59:00",
            "bid": 1.0, "ask": 1.1,
        }])

    def option_snapshot_greeks_all(self, **kwargs):
        self.calls.append(("option_snapshot_greeks_all", kwargs))
        return Frame([{"symbol": "SPX", "expiration": "2026-09-29",
                       "strike": 7700, "right": "call",
                       "timestamp": "2026-09-29T10:00:00", "gamma": 0.002,
                       "implied_vol": 0.18}])

    def option_snapshot_open_interest(self, **kwargs):
        self.calls.append(("option_snapshot_open_interest", kwargs))
        return Frame([{"symbol": "SPX", "expiration": "2026-09-29",
                       "strike": 7700, "right": "call",
                       "timestamp": "2026-09-29T06:30:00",
                       "open_interest": 500}])

    def option_snapshot_greeks_implied_volatility(self, **kwargs):
        self.calls.append(("option_snapshot_greeks_implied_volatility", kwargs))
        return Frame([{"symbol": "SPX", "expiration": "2026-09-29",
                       "strike": 7700, "right": "call",
                       "timestamp": "2026-09-29T10:00:00",
                       "underlying_price": 7700, "implied_vol": 0.18}])

    def index_snapshot_price(self, **kwargs):
        self.calls.append(("index_snapshot_price", kwargs))
        return Frame([{"symbol": "SPX", "timestamp": "2026-09-29T10:00:00",
                       "price": 7700}])

    def index_history_ohlc(self, **kwargs):
        self.calls.append(("index_history_ohlc", kwargs))
        return Frame([{"timestamp": "2026-09-29T10:00:00", "open": 17.0,
                       "high": 17.2, "low": 16.9, "close": 17.1,
                       "volume": 1000, "count": 12, "vwap": 17.05}])


def test_private_proxy_serves_compatible_stock_and_option_csv(monkeypatch):
    fake = FakeThetaClient()
    monkeypatch.setattr(proxy, "_client", lambda: fake)
    monkeypatch.setattr(proxy, "_health_cache", None)
    client = TestClient(proxy.app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok", "provider": "thetadata", "authenticated": True,
    }

    snapshot = client.get("/v3/stock/snapshot/ohlc", params={"symbol": "SPY,QQQ"})
    assert snapshot.status_code == 200
    assert snapshot.headers["x-market-data-provider"] == "thetadata"
    assert list(csv.DictReader(io.StringIO(snapshot.text)))[0]["symbol"] == "SPY"
    assert fake.calls[-1][1]["symbol"] == ["SPY", "QQQ"]

    expirations = client.get("/v3/option/list/expirations", params={"symbol": "SPY"})
    assert expirations.status_code == 200
    assert "2026-09-21" in expirations.text

    quotes = client.get("/v3/option/history/quote", params={
        "symbol": "SPY", "expiration": "20260921", "strike": "*",
        "start_date": "20260921", "end_date": "20260921", "interval": "1m",
        "start_time": "15:59:00", "end_time": "15:59:00",
    })
    assert quotes.status_code == 200
    method, kwargs = fake.calls[-1]
    assert method == "option_history_quote"
    assert kwargs["expiration"].isoformat() == "2026-09-21"
    assert kwargs["start_date"].isoformat() == "2026-09-21"


def test_private_proxy_rejects_unsafe_or_oversized_requests(monkeypatch):
    monkeypatch.setattr(proxy, "_client", lambda: FakeThetaClient())
    client = TestClient(proxy.app)

    assert client.get(
        "/v3/stock/snapshot/ohlc", params={"symbol": "SPY;DROP TABLE"},
    ).status_code == 422
    assert client.get("/v3/stock/history/eod", params={
        "symbol": "SPY", "start_date": "2025-01-01", "end_date": "2026-09-01",
    }).status_code == 422
    assert client.get("/v3/option/history/quote", params={
        "symbol": "SPY", "expiration": "20260921", "date": "20260921",
        "interval": "2m",
    }).status_code == 422


def test_private_proxy_exposes_live_greeks_oi_and_index_prices(monkeypatch):
    fake = FakeThetaClient()
    monkeypatch.setattr(proxy, "_client", lambda: fake)
    client = TestClient(proxy.app)
    for path in ("/v3/option/snapshot/greeks/all",
                 "/v3/option/snapshot/greeks/implied_volatility",
                 "/v3/option/snapshot/open_interest"):
        response = client.get(path, params={"symbol": "SPX", "expiration": "*",
                                            "max_dte": 365, "strike_range": 60})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "2026-09-29" in response.text
        assert fake.calls[-1][1]["expiration"] == "*"
    index = client.get("/v3/index/snapshot/price", params={"symbol": "SPX,NDX"})
    assert index.status_code == 200
    assert fake.calls[-1] == ("index_snapshot_price", {"symbol": ["SPX", "NDX"]})
    assert client.get("/v3/option/snapshot/greeks/all", params={
        "symbol": "SPX", "strike_range": 500,
    }).status_code == 422


def test_private_proxy_serves_bounded_index_history(monkeypatch):
    fake = FakeThetaClient()
    monkeypatch.setattr(proxy, "_client", lambda: fake)
    client = TestClient(proxy.app)
    response = client.get("/v3/index/history/ohlc", params={
        "symbol": "VIX", "start_date": "2026-09-01", "end_date": "2026-09-29",
        "interval": "1m", "start_time": "09:30:00", "end_time": "16:00:00",
    })
    assert response.status_code == 200
    assert response.headers["x-market-data-provider"] == "thetadata"
    assert response.headers["x-bar-timestamp"] == "interval-start"
    method, kwargs = fake.calls[-1]
    assert method == "index_history_ohlc"
    assert kwargs["symbol"] == "VIX"
    assert kwargs["start_date"].isoformat() == "2026-09-01"
    assert client.get("/v3/index/history/ohlc", params={
        "symbol": "VIX", "start_date": "2026-01-01", "end_date": "2026-02-15",
    }).status_code == 422


# ---------------------------------------------------------------- 2026-09-28 wedge/self-heal fix
# See C:\Users\lemol\.claude\handoff\spike-data-fix-result-9-28.md for the root-cause writeup.

def test_call_times_out_and_evicts_the_cached_client(monkeypatch):
    """A wedged ThetaData session must be cut off at THETA_CALL_TIMEOUT_SECONDS
    instead of hanging CLIENT_LOCK (and therefore every OTHER caller) forever,
    and the cached client must be evicted so the NEXT call gets a fresh one."""
    monkeypatch.setattr(proxy, "THETA_CALL_TIMEOUT_SECONDS", 0.05)

    class WedgedClient:
        def stock_snapshot_ohlc(self, **kwargs):
            _time.sleep(1.0)
            return None

    def fake_client():
        return WedgedClient()

    cleared = {"n": 0}
    fake_client.cache_clear = lambda: cleared.__setitem__("n", cleared["n"] + 1)
    monkeypatch.setattr(proxy, "_client", fake_client)

    with pytest.raises(HTTPException) as excinfo:
        proxy._call("stock_snapshot_ohlc", symbol="AAA")
    assert excinfo.value.status_code == 504
    assert cleared["n"] == 1


def test_call_failure_evicts_the_cached_client(monkeypatch):
    """Any provider failure (not just a timeout) must evict the cached
    client too -- never keep reusing a connection that just errored."""
    monkeypatch.setattr(proxy, "THETA_CALL_TIMEOUT_SECONDS", 5)

    class BrokenClient:
        def stock_snapshot_ohlc(self, **kwargs):
            raise RuntimeError("provider error")

    def fake_client():
        return BrokenClient()

    cleared = {"n": 0}
    fake_client.cache_clear = lambda: cleared.__setitem__("n", cleared["n"] + 1)
    monkeypatch.setattr(proxy, "_client", fake_client)

    with pytest.raises(HTTPException) as excinfo:
        proxy._call("stock_snapshot_ohlc", symbol="AAA")
    assert excinfo.value.status_code == 502
    assert cleared["n"] == 1


# --- 2026-10-01 re-login storm fix -------------------------------------------------


class _GrpcError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self._code = code

    def code(self):
        return self._code


def _holder_with(monkeypatch, client_obj):
    """Real _ClientHolder whose ThetaClient constructor returns client_obj, counting logins."""
    import sys
    import types

    holder = proxy._ClientHolder()
    fake_mod = types.SimpleNamespace(ThetaClient=lambda **kw: client_obj)
    monkeypatch.setitem(sys.modules, "thetadata", fake_mod)
    monkeypatch.setenv("THETADATA_API_KEY", "test-key")
    monkeypatch.setattr(proxy, "_client", holder)
    return holder


def test_unauthenticated_failure_starts_cooldown_instead_of_relogin_storm(monkeypatch):
    monkeypatch.setattr(proxy, "RELOGIN_MIN_SECONDS", 60)

    class KickedClient:
        def stock_snapshot_ohlc(self, **kwargs):
            raise _GrpcError("StatusCode.UNAUTHENTICATED")

    holder = _holder_with(monkeypatch, KickedClient())
    with pytest.raises(HTTPException) as first:
        proxy._call("stock_snapshot_ohlc", symbol="AAA")
    assert first.value.status_code == 502
    assert holder.logins == 1

    # 50 more requests inside the cooldown: zero new logins, fast 503s.
    for _ in range(50):
        with pytest.raises(HTTPException) as exc:
            proxy._call("stock_snapshot_ohlc", symbol="AAA")
        assert exc.value.status_code == 503
    assert holder.logins == 1


def test_cooldown_doubles_per_eviction_and_resets_after_success(monkeypatch):
    monkeypatch.setattr(proxy, "RELOGIN_MIN_SECONDS", 10)
    monkeypatch.setattr(proxy, "RELOGIN_MAX_SECONDS", 25)
    clock = {"t": 1000.0}
    monkeypatch.setattr(proxy.time, "monotonic", lambda: clock["t"])
    state = {"fail": True}

    class FlakyClient:
        def stock_snapshot_ohlc(self, **kwargs):
            if state["fail"]:
                raise _GrpcError("StatusCode.UNAVAILABLE")
            return FakeThetaClient().stock_snapshot_ohlc(**kwargs)

    holder = _holder_with(monkeypatch, FlakyClient())
    for expected_wait in (10, 20, 25):          # doubles, capped at max
        with pytest.raises(HTTPException):
            proxy._call("stock_snapshot_ohlc", symbol="AAA")
        assert holder._next_build_at - clock["t"] == expected_wait
        clock["t"] += expected_wait
    state["fail"] = False
    proxy._call("stock_snapshot_ohlc", symbol="SPY")
    assert holder._streak == 0



def test_concurrent_failures_extend_cooldown_after_first_eviction(monkeypatch):
    """A second in-flight failure must not reopen the login gate early."""
    monkeypatch.setattr(proxy, "RELOGIN_MIN_SECONDS", 10)
    monkeypatch.setattr(proxy, "RELOGIN_MAX_SECONDS", 25)
    clock = {"t": 1000.0}
    monkeypatch.setattr(proxy.time, "monotonic", lambda: clock["t"])
    holder = proxy._ClientHolder()
    holder._client = object()

    holder.cache_clear()
    assert holder._streak == 1
    assert holder._next_build_at == 1010.0

    # This represents another request that started before the first request
    # cleared the shared client, then failed afterwards.
    clock["t"] = 1001.0
    holder.cache_clear()
    assert holder._streak == 2
    assert holder._next_build_at == 1021.0

def test_permission_denied_and_no_data_keep_the_client(monkeypatch):
    class EntitlementClient:
        def stock_snapshot_ohlc(self, **kwargs):
            raise _GrpcError("StatusCode.PERMISSION_DENIED")

    holder = _holder_with(monkeypatch, EntitlementClient())
    for _ in range(5):
        with pytest.raises(HTTPException) as exc:
            proxy._call("stock_snapshot_ohlc", symbol="AAA")
        assert exc.value.status_code == 403
    assert holder.logins == 1


def test_live_route_never_touches_thetadata(monkeypatch):
    def boom():
        raise AssertionError("liveness must not call ThetaData")

    monkeypatch.setattr(proxy, "_client", boom)
    assert TestClient(proxy.app).get("/live").json() == {"status": "alive"}


def test_health_failure_is_cached(monkeypatch):
    calls = {"n": 0}

    class DownClient:
        def stock_history_eod(self, **kwargs):
            calls["n"] += 1
            raise _GrpcError("StatusCode.PERMISSION_DENIED")

    monkeypatch.setattr(proxy, "_client", lambda: DownClient())
    monkeypatch.setattr(proxy, "_health_cache", None)
    client = TestClient(proxy.app)
    assert client.get("/health").status_code == 503
    assert client.get("/health").status_code == 503
    assert calls["n"] == 1


def test_private_proxy_allows_bounded_one_second_stock_history(monkeypatch):
    fake = FakeThetaClient()
    monkeypatch.setattr(proxy, "_client", lambda: fake)
    client = TestClient(proxy.app)
    response = client.get("/v3/stock/history/ohlc", params={
        "symbol": "SPY", "date": "2025-04-11", "interval": "1s",
        "start_time": "15:03:00", "end_time": "15:03:59", "venue": "utp_cta",
    })
    assert response.status_code == 200
    assert response.headers["x-bar-timestamp"] == "interval-start"
    assert fake.calls[-1][0] == "stock_history_ohlc"
    assert fake.calls[-1][1]["interval"] == "1s"
