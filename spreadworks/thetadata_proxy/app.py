"""Private, read-only ThetaData v3 compatibility service for Render.

ThetaData's Python library connects directly to ThetaData over gRPC, so this
service does not depend on a workstation Theta Terminal.  It intentionally
exposes only the stock and option endpoints used by EMBER/SPIKE and is meant
to run as a Render private service.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

LOGGER = logging.getLogger("thetadata_proxy")
SYMBOL_RE = re.compile(r"^[A-Z0-9._-]{1,16}$")
INTERVALS = {
    "tick", "10ms", "100ms", "500ms", "1s", "5s", "10s", "15s", "30s",
    "1m", "5m", "10m", "15m", "30m", "1h",
}
CLIENT_LOCK = threading.RLock()
HEALTH_LOCK = threading.Lock()
HEALTH_TTL_SECONDS = 60.0
_health_cache: tuple[float, dict[str, Any]] | None = None

app = FastAPI(title="ThetaData Private Proxy", docs_url=None, redoc_url=None)


def _symbols(raw: str) -> str | list[str]:
    values = [value.strip().upper() for value in raw.split(",") if value.strip()]
    if not values or len(values) > 500 or any(not SYMBOL_RE.fullmatch(value) for value in values):
        raise HTTPException(status_code=422, detail="invalid symbol list")
    return values[0] if len(values) == 1 else values


def _symbol(raw: str) -> str:
    value = raw.strip().upper()
    if not SYMBOL_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail="invalid symbol")
    return value


def _date(raw: str, field: str) -> date:
    value = raw.strip()
    try:
        if len(value) == 8 and value.isdigit():
            return date(int(value[:4]), int(value[4:6]), int(value[6:]))
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid {field}") from exc


def _date_range(start_raw: str, end_raw: str, *, max_days: int = 31) -> tuple[date, date]:
    start = _date(start_raw, "start_date")
    end = _date(end_raw, "end_date")
    if end < start or (end - start).days > max_days:
        raise HTTPException(status_code=422, detail=f"date range must be 0-{max_days} days")
    return start, end


@lru_cache(maxsize=1)
def _client():
    api_key = os.getenv("THETADATA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("THETADATA_API_KEY is not configured")
    from thetadata import ThetaClient

    return ThetaClient(api_key=api_key, dataframe_type="pandas")


def _csv(frame: Any) -> str:
    if frame is None:
        return ""
    if hasattr(frame, "to_csv"):
        return str(frame.to_csv(index=False))
    if hasattr(frame, "write_csv"):
        return str(frame.write_csv())
    raise RuntimeError("ThetaData returned an unsupported frame")


def _call(method: str, **kwargs: Any) -> str:
    try:
        with CLIENT_LOCK:
            frame = getattr(_client(), method)(**kwargs)
        return _csv(frame)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - provider failures must become a closed 502
        LOGGER.error("ThetaData request failed method=%s error_type=%s", method, type(exc).__name__)
        raise HTTPException(status_code=502, detail="ThetaData request failed") from exc


def _csv_response(body: str) -> PlainTextResponse:
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={"X-Market-Data-Provider": "thetadata"},
    )


@app.get("/health")
def health() -> dict[str, Any]:
    global _health_cache
    now = time.monotonic()
    with HEALTH_LOCK:
        if _health_cache and now - _health_cache[0] < HEALTH_TTL_SECONDS:
            return _health_cache[1]
        end = date.today()
        start = end - timedelta(days=10)
        try:
            with CLIENT_LOCK:
                frame = _client().stock_history_eod(
                    symbol="SPY", start_date=start, end_date=end,
                )
            if frame is None or len(frame) == 0:
                raise RuntimeError("ThetaData health probe returned no rows")
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("ThetaData health probe failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="ThetaData unavailable") from exc
        payload = {"status": "ok", "provider": "thetadata", "authenticated": True}
        _health_cache = (now, payload)
        return payload


@app.get("/v3/stock/snapshot/ohlc")
def stock_snapshot_ohlc(
    symbol: str = Query(...),
    venue: str = Query("nqb", pattern="^(nqb|utp_cta)$"),
    min_time: str | None = None,
) -> PlainTextResponse:
    kwargs: dict[str, Any] = {"symbol": _symbols(symbol), "venue": venue}
    if min_time:
        kwargs["min_time"] = min_time
    return _csv_response(_call("stock_snapshot_ohlc", **kwargs))


@app.get("/v3/stock/history/eod")
def stock_history_eod(
    symbol: str = Query(...), start_date: str = Query(...), end_date: str = Query(...),
) -> PlainTextResponse:
    start, end = _date_range(start_date, end_date, max_days=370)
    return _csv_response(_call(
        "stock_history_eod", symbol=_symbol(symbol), start_date=start, end_date=end,
    ))


@app.get("/v3/option/list/expirations")
def option_list_expirations(symbol: str = Query(...)) -> PlainTextResponse:
    return _csv_response(_call("option_list_expirations", symbol=_symbols(symbol)))


@app.get("/v3/option/history/quote")
def option_history_quote(
    symbol: str = Query(...),
    expiration: str = Query(...),
    strike: str = Query("*"),
    right: str = Query("both", pattern="^(call|put|both)$"),
    interval: str = Query("1s"),
    date_value: str | None = Query(None, alias="date"),
    start_date: str | None = None,
    end_date: str | None = None,
    start_time: str = "09:30:00",
    end_time: str = "16:00:00",
) -> PlainTextResponse:
    if interval not in INTERVALS:
        raise HTTPException(status_code=422, detail="invalid interval")
    expiry = _date(expiration, "expiration")
    kwargs: dict[str, Any] = {
        "symbol": _symbol(symbol),
        "expiration": expiry,
        "strike": strike,
        "right": right,
        "interval": interval,
        "start_time": start_time,
        "end_time": end_time,
    }
    if date_value:
        kwargs["date"] = _date(date_value, "date")
    elif start_date and end_date:
        start, end = _date_range(start_date, end_date)
        kwargs.update(start_date=start, end_date=end)
    else:
        raise HTTPException(status_code=422, detail="date or start_date/end_date required")
    return _csv_response(_call("option_history_quote", **kwargs))


@app.get("/v3/stock/history/ohlc")
def stock_history_ohlc(
    symbol: str = Query(...),
    date_value: str | None = Query(None, alias="date"),
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = Query("1m", pattern="^(1m|5m|10m|15m|30m|1h)$"),
    start_time: str = "09:30:00",
    end_time: str = "16:00:00",
    venue: str = Query("utp_cta", pattern="^(nqb|utp_cta)$"),
) -> PlainTextResponse:
    """Bounded, read-only stock intraday history; timestamps mark bar starts."""
    from datetime import time as clock_time

    try:
        start_clock = clock_time.fromisoformat(start_time)
        end_clock = clock_time.fromisoformat(end_time)
        if start_clock.tzinfo or end_clock.tzinfo or end_clock < start_clock:
            raise ValueError("invalid clock range")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid time range") from exc
    kwargs: dict[str, Any] = {
        "symbol": _symbol(symbol), "interval": interval,
        "start_time": start_time, "end_time": end_time, "venue": venue,
    }
    if date_value:
        kwargs["date"] = _date(date_value, "date")
    elif start_date and end_date:
        start, end = _date_range(start_date, end_date, max_days=30)
        kwargs.update(start_date=start, end_date=end)
    else:
        raise HTTPException(status_code=422, detail="date or start_date/end_date required")
    response = _csv_response(_call("stock_history_ohlc", **kwargs))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Bar-Timestamp"] = "interval-start"
    return response
