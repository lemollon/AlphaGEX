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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, timedelta
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

# 2026-09-28 fix (see spike-data-fix-result-9-28.md): the underlying
# ThetaData client is a single long-lived, lru_cache'd connection reused for
# every request. A wedged session there (the same class of issue as the
# workstation ThetaData keep-alive wedge -- see the "ThetaData keep-alive
# session wedges bulk calls" memory note) used to hang under CLIENT_LOCK
# forever, blocking every OTHER symbol/endpoint behind it too -- turning one
# bad connection into a total proxy outage. _CALL_EXECUTOR runs each call on
# a bounded timeout so a wedge can never hang the lock past
# THETA_CALL_TIMEOUT_SECONDS; _client.cache_clear() on that timeout (or any
# other failure) evicts the stuck client so the NEXT call gets a fresh
# connection instead of the same wedged one.
_CALL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="theta-call")
THETA_CALL_TIMEOUT_SECONDS = float(os.getenv("THETADATA_CALL_TIMEOUT_SECONDS", "25"))
RELOGIN_MIN_SECONDS = float(os.getenv("THETADATA_RELOGIN_MIN_SECONDS", "30"))
RELOGIN_MAX_SECONDS = float(os.getenv("THETADATA_RELOGIN_MAX_SECONDS", "300"))

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


class _ClientHolder:
    """A failed session cannot cause a login storm across endpoint callers."""
    def __init__(self):
        self._client = None
        self._next_build_at = 0.0
        self._streak = 0
        self.logins = 0
        self._lock = threading.RLock()

    def __call__(self):
        with self._lock:
            if self._client is not None:
                return self._client
            if time.monotonic() < self._next_build_at:
                raise HTTPException(status_code=503, detail="ThetaData session recovery cooldown")
            api_key = os.getenv("THETADATA_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("THETADATA_API_KEY is not configured")
            from thetadata import ThetaClient
            try:
                self._client = ThetaClient(api_key=api_key, dataframe_type="pandas")
            except Exception:
                self.cache_clear()
                raise
            self.logins += 1
            return self._client

    def cache_clear(self):
        with self._lock:
            self._client = None
            self._streak += 1
            delay = min(RELOGIN_MAX_SECONDS, RELOGIN_MIN_SECONDS * 2 ** min(self._streak - 1, 20))
            self._next_build_at = max(self._next_build_at, time.monotonic() + delay)

    def mark_success(self):
        with self._lock:
            self._streak = 0
            self._next_build_at = 0.0


_client = _ClientHolder()


def _csv(frame: Any) -> str:
    if frame is None:
        return ""
    if hasattr(frame, "to_csv"):
        return str(frame.to_csv(index=False))
    if hasattr(frame, "write_csv"):
        return str(frame.write_csv())
    raise RuntimeError("ThetaData returned an unsupported frame")


def _call(method: str, **kwargs: Any) -> str:
    low_priority = kwargs.pop("_low_priority", False)
    if low_priority and not CLIENT_LOCK.acquire(blocking=False):
        raise HTTPException(429, detail="Report history deferred while live data client is busy")
    try:
        with CLIENT_LOCK:
            future = _CALL_EXECUTOR.submit(lambda: getattr(_client(), method)(**kwargs))
            try:
                frame = future.result(timeout=THETA_CALL_TIMEOUT_SECONDS)
            except FutureTimeoutError as exc:
                LOGGER.error(
                    "ThetaData request timed out method=%s timeout=%ss -- evicting cached client",
                    method, THETA_CALL_TIMEOUT_SECONDS,
                )
                _client.cache_clear()
                raise HTTPException(status_code=504, detail="ThetaData request timed out") from exc
        if callable(getattr(_client, "mark_success", None)):
            _client.mark_success()
        return _csv(frame)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - provider failures must become a closed 502
        if type(exc).__name__ == "NoDataFoundError":
            raise HTTPException(status_code=404, detail="ThetaData returned no historical observations") from exc
        code = str(exc.code()) if callable(getattr(exc, "code", None)) else "n/a"
        LOGGER.error("ThetaData request failed method=%s error_type=%s grpc_code=%s",
                     method, type(exc).__name__, code)
        if code not in {"StatusCode.PERMISSION_DENIED", "StatusCode.INVALID_ARGUMENT"}:
            _client.cache_clear()
        status, detail = {
            "StatusCode.UNAUTHENTICATED": (401, "ThetaData authentication rejected"),
            "StatusCode.PERMISSION_DENIED": (403, "ThetaData entitlement denied"),
            "StatusCode.INVALID_ARGUMENT": (422, "ThetaData request arguments rejected"),
        }.get(code, (502, "ThetaData request failed"))
        raise HTTPException(status_code=status, detail=detail) from exc
    finally:
        if low_priority:
            CLIENT_LOCK.release()


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
            if _health_cache[1].get("status") == "unavailable":
                raise HTTPException(status_code=503, detail="ThetaData unavailable")
            return _health_cache[1]
        end = date.today()
        start = end - timedelta(days=10)
        try:
            frame = _call("stock_history_eod", symbol="SPY", start_date=start, end_date=end)
            if frame is None or len(frame) == 0:
                raise RuntimeError("ThetaData health probe returned no rows")
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("ThetaData health probe failed error_type=%s", type(exc).__name__)
            _health_cache = (now, {"status": "unavailable", "provider": "thetadata", "authenticated": False})
            raise HTTPException(status_code=503, detail="ThetaData unavailable") from exc
        payload = {"status": "ok", "provider": "thetadata", "authenticated": True}
        _health_cache = (now, payload)
        return payload


@app.get("/live")
def liveness():
    return {"status": "alive"}


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


@app.get("/v3/option/snapshot/greeks/all")
def option_snapshot_greeks_all(
    symbol: str = Query(...), expiration: str = Query("*"),
    max_dte: int = Query(365, ge=0, le=365),
    strike_range: int = Query(60, ge=1, le=150),
) -> PlainTextResponse:
    """Bounded live chain; source timestamps remain in ThetaData's CSV."""
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    response = _csv_response(_call(
        "option_snapshot_greeks_all", symbol=_symbol(symbol), expiration=expiry,
        max_dte=max_dte, strike_range=strike_range,
    ))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v3/option/snapshot/greeks/second_order")
def option_snapshot_greeks_second_order(
    symbol: str = Query(...), expiration: str = Query("*"),
    max_dte: int = Query(365, ge=0, le=365),
    strike_range: int = Query(60, ge=1, le=150),
) -> PlainTextResponse:
    """Pro-tier only: vanna, charm, vomma (volga), veta. 403s on Standard —
    same entitlement shape as greeks/all; callers already handle that."""
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    response = _csv_response(_call(
        "option_snapshot_greeks_second_order", symbol=_symbol(symbol), expiration=expiry,
        max_dte=max_dte, strike_range=strike_range,
    ))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v3/option/snapshot/greeks/third_order")
def option_snapshot_greeks_third_order(
    symbol: str = Query(...), expiration: str = Query("*"),
    max_dte: int = Query(365, ge=0, le=365),
    strike_range: int = Query(60, ge=1, le=150),
) -> PlainTextResponse:
    """Pro-tier only: speed, zomma, color. Same entitlement shape as
    greeks/all and greeks/second_order."""
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    response = _csv_response(_call(
        "option_snapshot_greeks_third_order", symbol=_symbol(symbol), expiration=expiry,
        max_dte=max_dte, strike_range=strike_range,
    ))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v3/option/snapshot/greeks/implied_volatility")
def option_snapshot_implied_volatility(
    symbol: str = Query(...), expiration: str = Query("*"),
    max_dte: int = Query(365, ge=0, le=365),
    strike_range: int = Query(60, ge=1, le=150),
    background: bool = False,
) -> PlainTextResponse:
    """Standard-tier IV data for a local gamma calculation when Pro is absent."""
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    response = _csv_response(_call(
        "option_snapshot_greeks_implied_volatility", symbol=_symbol(symbol),
        expiration=expiry, max_dte=max_dte, strike_range=strike_range, _low_priority=background,
    ))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v3/option/snapshot/open_interest")
def option_snapshot_open_interest(
    symbol: str = Query(...), expiration: str = Query("*"),
    max_dte: int = Query(365, ge=0, le=365),
    strike_range: int = Query(60, ge=1, le=150),
) -> PlainTextResponse:
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    response = _csv_response(_call(
        "option_snapshot_open_interest", symbol=_symbol(symbol), expiration=expiry,
        max_dte=max_dte, strike_range=strike_range,
    ))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v3/index/snapshot/price")
def index_snapshot_price(symbol: str = Query(...)) -> PlainTextResponse:
    response = _csv_response(_call("index_snapshot_price", symbol=_symbols(symbol)))
    response.headers["Cache-Control"] = "no-store"
    return response


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


@app.get("/v3/option/history/trade_quote")
def option_history_trade_quote(
    symbol: str = Query(...),
    expiration: str = Query("*"),
    strike: str = Query("*"),
    right: str = Query("both", pattern="^(call|put|both)$"),
    date_value: str = Query(..., alias="date"),
    start_time: str = "09:30:00",
    end_time: str = "16:00:00",
    max_dte: int = Query(60, ge=0, le=365),
    strike_range: int = Query(12, ge=1, le=60),
    exclusive: bool = True,
) -> PlainTextResponse:
    """OPRA trades paired with the NBBO available at each trade.

    This is the required evidence for an at-bid / at-ask initiation read.  It
    is deliberately separate from chain volume: the latter cannot establish
    who initiated the trade.  No caller may infer opening/closing inventory or
    a multi-leg structure from these prints.
    """
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    return _csv_response(_call(
        "option_history_trade_quote", symbol=_symbol(symbol), expiration=expiry,
        strike=strike, right=right, date=_date(date_value, "date"),
        start_time=start_time, end_time=end_time, max_dte=max_dte,
        strike_range=strike_range, exclusive=exclusive, _low_priority=True,
    ))


@app.get("/v3/stock/history/ohlc")
def stock_history_ohlc(
    symbol: str = Query(...),
    date_value: str | None = Query(None, alias="date"),
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = Query("1m", pattern="^(1s|1m|5m|10m|15m|30m|1h)$"),
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


@app.get("/v3/stock/history/trade")
def stock_history_trade(symbol: str = Query(...), date_value: str = Query(..., alias="date"),
                        start_time: str = "09:30:00", end_time: str = "10:00:00",
                        venue: str = Query("utp_cta", pattern="^(nqb|utp_cta)$")):
    """Bounded consolidated tape for observed volume-at-price; no bar approximation."""
    from datetime import time as clock
    try:
        start, end = clock.fromisoformat(start_time), clock.fromisoformat(end_time)
        span = (end.hour-start.hour)*3600+(end.minute-start.minute)*60+end.second-start.second
        if start.tzinfo or end.tzinfo or not 0 <= span <= 1800:
            raise ValueError("trade window must be <=30 minutes")
    except ValueError as exc:
        raise HTTPException(422, detail="trade window must be 0-30 minutes") from exc
    return _csv_response(_call("stock_history_trade", symbol=_symbol(symbol),
                         date=_date(date_value, "date"), start_time=start_time,
                         end_time=end_time, venue=venue, _low_priority=True))


@app.get("/v3/index/history/ohlc")
def index_history_ohlc(symbol: str = Query(...), start_date: str = Query(...),
                       end_date: str = Query(...), interval: str = Query("1m", pattern="^(1m|5m|10m|15m|30m|1h)$"),
                       start_time: str = "09:30:00", end_time: str = "16:00:00"):
    from datetime import time as clock_time
    start, end = _date_range(start_date, end_date, max_days=31)
    try:
        lo, hi = clock_time.fromisoformat(start_time), clock_time.fromisoformat(end_time)
        if lo.tzinfo or hi.tzinfo or hi < lo:
            raise ValueError("invalid clock range")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid time range") from exc
    response = _csv_response(_call("index_history_ohlc", symbol=_symbol(symbol),
        start_date=start, end_date=end, interval=interval, start_time=start_time, end_time=end_time))
    response.headers["X-Bar-Timestamp"] = "interval-start"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v3/stock/history/quote")
def stock_history_quote(
    symbol: str = Query(...),
    date_value: str | None = Query(None, alias="date"),
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = Query("1s"),
    start_time: str = "09:30:00",
    end_time: str = "16:00:00",
    venue: str = Query("utp_cta", pattern="^(nqb|utp_cta)$"),
) -> PlainTextResponse:
    """Bounded, read-only stock NBBO quote history -- the bid/ask counterpart
    to `/v3/stock/history/ohlc` (which is TRADES only). Added for the
    premarket squeeze scanner's live entry-price recommendation: per the
    standing fill-discipline rule, a "buy at the open" call needs a real
    NBBO ask, never a trade print or a mark (see squeeze_premarket_cron's
    fetch_entry_ask()). Same param conventions as stock_history_ohlc;
    `venue` defaults to utp_cta to match that route's proven entitlement."""
    if interval not in INTERVALS:
        raise HTTPException(status_code=422, detail="invalid interval")
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
    response = _csv_response(_call("stock_history_quote", **kwargs))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/v3/option/history/eod")
def option_history_eod_research(
    symbol: str, date_value: str = Query(..., alias="date"),
    expiration: str = "*", max_dte: int = Query(60, ge=0, le=61),
):
    """One session of closing chains for historical IV reconstruction."""
    day = _date(date_value, "date")
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    return _csv_response(_call("option_history_eod", symbol=_symbol(symbol),
        expiration=expiry, start_date=day, end_date=day,
        strike="*", right="both", max_dte=max_dte))


@app.get("/v3/option/history/open_interest")
def option_history_open_interest_research(
    symbol: str, date_value: str = Query(..., alias="date"),
    expiration: str = "*", max_dte: int = Query(60, ge=0, le=61),
):
    """Historical morning OI, representing the prior session's closing OI."""
    day = _date(date_value, "date")
    expiry = "*" if expiration == "*" else _date(expiration, "expiration")
    return _csv_response(_call("option_history_open_interest", symbol=_symbol(symbol),
        expiration=expiry, date=day, strike="*", right="both", max_dte=max_dte))
