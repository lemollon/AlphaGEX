from datetime import datetime, timezone
from types import SimpleNamespace

import yfinance

from backend import report_producers as rp

UTC = timezone.utc


class _DeadTicker:
    """yfinance stand-in so the per-symbol fallback loop never makes a real network call --
    each symbol's own try/except catches this and reports unavailable, same as a live outage."""
    def __init__(self, *a, **k):
        pass

    def history(self, *a, **k):
        raise RuntimeError("no network in tests")


def test_collect_macro_computes_day_over_day_yield_change_from_the_same_fred_window(monkeypatch):
    """Leron, 2026-10-13: "what is the yield on treasury how has it changed... what does it
    mean for today and the future" -- the FRED window collect_macro() already fetches 14 days
    of history; this reuses the second-to-last valid row instead of calling out again."""
    csv_text = (
        "DATE,DGS2,DGS5,DGS10,DGS30\n"
        "2026-10-09,3.60,3.80,4.09,4.40\n"
        "2026-10-10,3.61,3.81,4.12,4.41\n"
    )

    def fake_get(url, params=None, timeout=None):
        assert "fredgraph.csv" in url
        return SimpleNamespace(status_code=200, text=csv_text, raise_for_status=lambda: None)

    monkeypatch.setattr(rp.requests, "get", fake_get)
    monkeypatch.setattr(yfinance, "Ticker", _DeadTicker)

    data = rp.collect_macro(datetime(2026, 10, 10, 20, 0, tzinfo=UTC))
    row10 = data["rates_10y"]["value"]
    assert row10["price"] == 4.12
    assert row10["change_1day_bp"] == 3.0
    assert row10["prior_observation_date"] == "2026-10-09"

    row2 = data["rates_2y"]["value"]
    assert row2["change_1day_bp"] == 1.0


def test_collect_macro_omits_change_when_only_one_day_of_history_available(monkeypatch):
    csv_text = "DATE,DGS2,DGS5,DGS10,DGS30\n2026-10-10,3.61,3.81,4.12,4.41\n"

    def fake_get(url, params=None, timeout=None):
        return SimpleNamespace(status_code=200, text=csv_text, raise_for_status=lambda: None)

    monkeypatch.setattr(rp.requests, "get", fake_get)
    monkeypatch.setattr(yfinance, "Ticker", _DeadTicker)

    data = rp.collect_macro(datetime(2026, 10, 10, 20, 0, tzinfo=UTC))
    row10 = data["rates_10y"]["value"]
    assert row10["price"] == 4.12
    assert "change_1day_bp" not in row10
