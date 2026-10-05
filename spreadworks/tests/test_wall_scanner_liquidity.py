"""Wall Scanner ThetaData liquidity gate (2026-10-05) -- fetch_universe()
must filter TV's raw roster down to names with real options chain volume,
fail OPEN (unfiltered TV roster) only when ThetaData is unreachable for
every candidate, and fail CLOSED per-ticker (exclude, not fallback) for a
lone unknown amid an otherwise-working batch.
"""
from __future__ import annotations

from backend.bots import wall_scanner


def test_liquidity_gate_filters_liquid_from_illiquid(monkeypatch):
    volumes = {"AAPL": 50_000.0, "SPY": 1_000_000.0, "ILLIQUID": 10.0, "THIN": 0.0}

    def fake_volume(ticker: str):
        return volumes[ticker]

    monkeypatch.setattr(wall_scanner, "_thetadata_chain_volume", fake_volume)
    monkeypatch.setattr(wall_scanner, "_liquidity_cache", {})

    out = wall_scanner._filter_liquid_universe(list(volumes.keys()))

    assert sorted(out) == ["AAPL", "SPY"]


def test_liquidity_gate_falls_back_when_thetadata_fully_unreachable(monkeypatch):
    tickers = ["AAPL", "SPY", "ILLIQUID"]

    monkeypatch.setattr(wall_scanner, "_thetadata_chain_volume", lambda t: None)
    monkeypatch.setattr(wall_scanner, "_liquidity_cache", {})

    out = wall_scanner._filter_liquid_universe(tickers)

    # Infrastructure failure must never blank the scanner -- original,
    # unfiltered list comes back untouched.
    assert sorted(out) == sorted(tickers)


def test_liquidity_gate_excludes_single_unknown_without_triggering_fallback(monkeypatch):
    volumes = {"AAPL": 50_000.0, "SPY": 1_000_000.0, "UNKNOWN": None}

    def fake_volume(ticker: str):
        return volumes[ticker]

    monkeypatch.setattr(wall_scanner, "_thetadata_chain_volume", fake_volume)
    monkeypatch.setattr(wall_scanner, "_liquidity_cache", {})

    out = wall_scanner._filter_liquid_universe(list(volumes.keys()))

    # A lone unknown is excluded (fail closed per-ticker), not treated as
    # grounds to fall back to the unfiltered roster.
    assert sorted(out) == ["AAPL", "SPY"]
    assert "UNKNOWN" not in out
