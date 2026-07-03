"""Minimal Tradier market-data client for TSUNAMI.

Self-contained replacement for AlphaGEX's ``data.tradier_data_fetcher``:
TSUNAMI only needs quotes and a greeks-enabled option chain for the
nearest expiration, so this speaks to the Tradier REST API directly
instead of dragging the full AlphaGEX fetcher (and its config machinery)
into SpreadWorks.

Auth follows the SpreadWorks convention (``TRADIER_TOKEN``), falling back
to the AlphaGEX name (``TRADIER_API_KEY``) so either env var works.
Production endpoint only — TSUNAMI is paper-traded from real market data.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

TRADIER_BASE = "https://api.tradier.com/v1"
_TIMEOUT = 30


def _token() -> str:
    return (
        os.environ.get("TRADIER_TOKEN", "").strip()
        or os.environ.get("TRADIER_API_KEY", "").strip()
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}


def get_quote(symbol: str) -> Optional[dict[str, Any]]:
    """Return the Tradier quote dict for ``symbol`` (keys incl. last/close),
    or None on any failure."""
    if not _token():
        logger.warning("[tradier_client] no TRADIER_TOKEN/TRADIER_API_KEY set")
        return None
    try:
        resp = requests.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": symbol},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[tradier_client] quote %s http %s", symbol, resp.status_code)
            return None
        quote = (resp.json().get("quotes") or {}).get("quote")
        if isinstance(quote, list):
            quote = quote[0] if quote else None
        return quote if isinstance(quote, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tradier_client] quote %s failed: %r", symbol, exc)
        return None


def get_daily_history(symbol: str, days: int = 130) -> list[dict[str, Any]]:
    """Daily OHLC bars for the last ``days`` calendar days, ascending by date.
    Empty list on failure (TSUNAMI-TREND treats that as no-signal)."""
    from datetime import timedelta
    end = date.today()
    start = end - timedelta(days=int(days * 1.6) + 10)  # calendar slack for ~days bars
    try:
        resp = requests.get(
            f"{TRADIER_BASE}/markets/history",
            params={"symbol": symbol, "interval": "daily",
                    "start": start.isoformat(), "end": end.isoformat()},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[tradier_client] history %s http %s", symbol, resp.status_code)
            return []
        rows = (resp.json().get("history") or {}).get("day") or []
        if isinstance(rows, dict):
            rows = [rows]
        out = [r for r in rows if r.get("date") and r.get("close")]
        out.sort(key=lambda r: str(r["date"]))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tradier_client] history %s failed: %r", symbol, exc)
        return []


def get_nearest_expiration(symbol: str, today: Optional[date] = None) -> Optional[str]:
    """Return the nearest option expiration date string (YYYY-MM-DD) on or
    after ``today``, or None on failure."""
    try:
        resp = requests.get(
            f"{TRADIER_BASE}/markets/options/expirations",
            params={"symbol": symbol},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[tradier_client] expirations %s http %s", symbol, resp.status_code)
            return None
        dates = (resp.json().get("expirations") or {}).get("date") or []
        if isinstance(dates, str):
            dates = [dates]
        floor = (today or date.today()).isoformat()
        for d in sorted(dates):
            if d >= floor:
                return d
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tradier_client] expirations %s failed: %r", symbol, exc)
        return None


def get_chain_contracts(symbol: str, expiration: Optional[str] = None) -> list[dict[str, Any]]:
    """Return greeks-enabled option contracts for one expiration.

    Each contract dict has: strike, bid, ask, open_interest, option_type,
    gamma. Expiration defaults to the nearest one. Empty list on failure.
    """
    exp = expiration or get_nearest_expiration(symbol)
    if not exp:
        return []
    try:
        resp = requests.get(
            f"{TRADIER_BASE}/markets/options/chains",
            params={"symbol": symbol, "expiration": exp, "greeks": "true"},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[tradier_client] chain %s %s http %s", symbol, exp, resp.status_code)
            return []
        options = (resp.json().get("options") or {}).get("option") or []
        if isinstance(options, dict):
            options = [options]
        out: list[dict[str, Any]] = []
        for c in options:
            try:
                greeks = c.get("greeks") or {}
                out.append({
                    "strike": float(c["strike"]),
                    "bid": float(c.get("bid") or 0),
                    "ask": float(c.get("ask") or 0),
                    "open_interest": int(c.get("open_interest") or 0),
                    "option_type": str(c.get("option_type") or "").lower(),
                    "gamma": float(greeks.get("gamma") or 0),
                })
            except (TypeError, ValueError, KeyError):
                continue
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tradier_client] chain %s failed: %r", symbol, exc)
        return []
