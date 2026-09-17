"""Dedicated Render background worker for the QQQ retest watch.

The worker maintains one authenticated Tradier WebSocket for QQQ/SPY market
events and runs the existing completed-one-minute-bar classifier every ten
seconds.  REST bars remain authoritative for classification; the stream gives
an independent live-feed heartbeat and reconnects automatically.

This process is advisory only.  It imports no order routes and cannot preview,
place, modify, or cancel a trade.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import websockets

from .db import Base, SessionLocal, engine
from .models import QQQWatchRuntimeStatus
from .qqq_retest_watch import load_settings, run_watch_cycle


UTC = timezone.utc
TRADIER_BASE = "https://api.tradier.com/v1"
TRADIER_STREAM = "wss://ws.tradier.com/v1/markets/events"
WATCHER_ID = "qqq-retest"
logger = logging.getLogger("spreadworks.qqq_retest_worker")

_STOP = asyncio.Event()
_STREAM: dict[str, Any] = {
    "connected": False,
    "connected_at": None,
    "last_event_at": None,
    "last_exchange_timestamp": None,
    "event_count": 0,
    "last_error": None,
    "reconnect_count": 0,
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _stream_public() -> dict[str, Any]:
    return {
        key: (_iso(value) if isinstance(value, datetime) else value)
        for key, value in _STREAM.items()
    }


def _parse_exchange_timestamp(event: dict[str, Any]) -> datetime | None:
    raw = event.get("date") or event.get("biddate") or event.get("askdate")
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(float(raw) / 1000.0, UTC)
    except (TypeError, ValueError, OSError):
        return None


def _record_stream_message(message: str, received_at: datetime) -> None:
    """Record real feed liveness; never infer a missing market-data field."""
    for raw_line in message.splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.warning("[QQQWorker] ignored non-JSON stream payload")
            continue
        if event.get("error"):
            raise RuntimeError(f"Tradier stream error: {event['error']}")
        if str(event.get("symbol", "")).upper() not in {"QQQ", "SPY"}:
            continue
        _STREAM["last_event_at"] = received_at
        exchange_at = _parse_exchange_timestamp(event)
        if exchange_at is not None:
            _STREAM["last_exchange_timestamp"] = exchange_at
        _STREAM["event_count"] = int(_STREAM["event_count"]) + 1
        _STREAM["last_error"] = None


async def _create_stream_session(client: httpx.AsyncClient) -> str:
    token = os.getenv("TRADIER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TRADIER_TOKEN is not configured on Render")
    response = await client.post(
        f"{TRADIER_BASE}/markets/events/session",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/json"},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Tradier stream session returned {response.status_code}: "
            f"{response.text[:160]}"
        )
    session_id = ((response.json().get("stream") or {}).get("sessionid"))
    if not session_id:
        raise RuntimeError("Tradier stream session response had no sessionid")
    return str(session_id)


async def _stream_forever(client: httpx.AsyncClient) -> None:
    backoff = 1
    while not _STOP.is_set():
        try:
            session_id = await _create_stream_session(client)
            async with websockets.connect(
                TRADIER_STREAM, compression=None, open_timeout=15,
                close_timeout=5, ping_interval=20, ping_timeout=20,
            ) as websocket:
                await websocket.send(json.dumps({
                    "symbols": ["QQQ", "SPY"],
                    "filter": ["quote", "timesale"],
                    "sessionid": session_id,
                    "linebreak": True,
                    "validOnly": True,
                    "advancedDetails": False,
                }))
                now = datetime.now(UTC)
                _STREAM.update(connected=True, connected_at=now,
                               last_error=None)
                logger.info("[QQQWorker] Tradier stream connected")
                backoff = 1
                async for message in websocket:
                    _record_stream_message(str(message), datetime.now(UTC))
                    if _STOP.is_set():
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _STREAM.update(connected=False, last_error=str(exc))
            _STREAM["reconnect_count"] = int(_STREAM["reconnect_count"]) + 1
            logger.warning("[QQQWorker] stream disconnected: %r", exc)
            try:
                await asyncio.wait_for(_STOP.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, 30)
    _STREAM["connected"] = False


def _write_status(payload: dict[str, Any], heartbeat_at: datetime) -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured on Render")
    db = SessionLocal()
    try:
        row = db.get(QQQWatchRuntimeStatus, WATCHER_ID)
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        if row is None:
            row = QQQWatchRuntimeStatus(
                watcher_id=WATCHER_ID,
                payload_json=encoded,
                heartbeat_at=heartbeat_at,
            )
            db.add(row)
        else:
            row.payload_json = encoded
            row.heartbeat_at = heartbeat_at
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _run_worker() -> None:
    settings = load_settings()
    if not settings.enabled:
        raise RuntimeError("QQQ_RETEST_WATCH_ENABLED must be true on the worker")
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured on Render")
    Base.metadata.create_all(
        bind=engine, tables=[QQQWatchRuntimeStatus.__table__]
    )
    timeout = httpx.Timeout(15.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        app = SimpleNamespace(state=SimpleNamespace(http=client))
        stream_task = asyncio.create_task(_stream_forever(client))
        try:
            while not _STOP.is_set():
                started_at = datetime.now(UTC)
                status = await run_watch_cycle(app, now=started_at)
                next_cycle = started_at + timedelta(seconds=settings.poll_seconds)
                status.update(
                    runtime="render-background-worker",
                    worker_started=True,
                    stream=_stream_public(),
                    next_cycle_at=next_cycle.isoformat(),
                )
                await asyncio.to_thread(_write_status, status, started_at)
                delay = max(
                    0.0, (next_cycle - datetime.now(UTC)).total_seconds()
                )
                try:
                    await asyncio.wait_for(_STOP.wait(), timeout=delay)
                except TimeoutError:
                    pass
        finally:
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)


def _request_stop() -> None:
    _STOP.set()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(_request_stop))
    try:
        loop.run_until_complete(_run_worker())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
