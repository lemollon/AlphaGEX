import csv
import io
from datetime import datetime

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
