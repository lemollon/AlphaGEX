"""Tests for the GexClient — pure transport + parse layer."""
import datetime as dt
import pytest

from trading.helios.gex_client import GexClient, GexSnapshot, GexStaleError


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(self, payload, status=200):
        self.response = FakeResponse(payload, status)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        return self.response


def _payload(net_gex=2.0e9, spot=500.0, flip=499.0, call_wall=502.0, put_wall=496.0, vix=18.0, ts=None):
    if ts is None:
        ts = dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "success": True,
        "data": {
            "symbol": "SPY",
            "net_gex": net_gex,
            "flip_point": flip,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "spot_price": spot,
            "vix": vix,
            "regime": "HIGH_POSITIVE",
            "timestamp": ts,
        },
    }


def test_gex_client_parses_snapshot():
    http = FakeHttp(_payload())
    client = GexClient(base_url="http://test", http=http, stale_max_seconds=90)
    snap = client.get_spy(now=dt.datetime.now(dt.timezone.utc))
    assert isinstance(snap, GexSnapshot)
    assert snap.symbol == "SPY"
    assert snap.net_gex == 2.0e9
    assert snap.spot == 500.0
    assert snap.call_wall == 502.0
    assert snap.put_wall == 496.0
    assert snap.flip_point == 499.0
    assert snap.regime == "HIGH_POSITIVE"


def test_gex_client_rejects_stale_snapshot():
    old_ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)).isoformat()
    http = FakeHttp(_payload(ts=old_ts))
    client = GexClient(base_url="http://test", http=http, stale_max_seconds=90)
    with pytest.raises(GexStaleError):
        client.get_spy(now=dt.datetime.now(dt.timezone.utc))


def test_gex_client_sigma_1d_band_width_derived_from_vix_and_spot():
    http = FakeHttp(_payload(vix=20.0, spot=500.0))
    client = GexClient(base_url="http://test", http=http, stale_max_seconds=90)
    snap = client.get_spy(now=dt.datetime.now(dt.timezone.utc))
    # sigma_1d = spot * vix/100 * sqrt(1/252) — for vix=20 spot=500: 500*0.20*0.063 ~ 6.30
    assert 5.5 <= snap.sigma_1d_band_width <= 7.0


def test_gex_client_retries_on_5xx_once():
    pl = _payload()
    bad = FakeResponse({}, status=502)
    good = FakeResponse(pl)
    calls = {"n": 0}

    class FakeHttpRetry:
        def get(self, url, timeout=None):
            calls["n"] += 1
            return bad if calls["n"] == 1 else good

    client = GexClient(base_url="http://test", http=FakeHttpRetry(), stale_max_seconds=90, retry_backoff=0.0)
    snap = client.get_spy(now=dt.datetime.now(dt.timezone.utc))
    assert calls["n"] == 2
    assert snap.symbol == "SPY"
