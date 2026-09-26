"""Opt-in, read-only MES/ES historical-candle coverage probe.

The probe authenticates only to Tastytrade's DXLink market-data streamer.  It
does not import any account, position, or order module.  Validated candles are
written to dedicated research tables so we can measure the provider's actual
history window before preregistering another MES strategy.  The approved ES
continuous product is data-only: it may serve as a lead-market signal for MES,
but it cannot change the traded instrument or the paper-only boundary.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import math
import os
import re
import threading
import uuid
from typing import Any, Callable, Iterable, Optional


logger = logging.getLogger(__name__)

UTC = timezone.utc
SOURCE = "TASTYTRADE_DXLINK_CANDLE"
TICK_SIZE = 0.25
ALLOWED_INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
TERMINAL_STATES = {"COMPLETE", "CAP_TRUNCATED"}
DEFAULT_CONTRACT = "/MESZ3"
DEFAULT_STREAMER = "/MESZ23:XCME"
DEFAULT_FROM = "2023-09-18T00:00:00+00:00"

try:
    from tastytrade import DXLinkStreamer, Session
    from tastytrade.dxfeed import Candle

    STREAMING_AVAILABLE = True
except ImportError:  # pragma: no cover - local research runtimes may be minimal
    DXLinkStreamer = Session = Candle = None
    STREAMING_AVAILABLE = False


class InvalidProbeConfiguration(ValueError):
    """The requested market-data probe is outside the fixed safety boundary."""


def _aware(value: Any) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if result.tzinfo is None or result.utcoffset() is None:
        raise InvalidProbeConfiguration("timezone-aware timestamp required")
    return result.astimezone(UTC)


def _finite(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _tick_valid(value: float) -> bool:
    return abs(value / TICK_SIZE - round(value / TICK_SIZE)) <= 1e-6


def validate_symbols(contract_symbol: str, streamer_symbol: str) -> None:
    if (contract_symbol, streamer_symbol) in {
        ("/MES", "/MES:XCME"),
        ("/ES", "/ES:XCME"),
    }:
        return
    if not re.fullmatch(r"/MES[HMUZ]\d", contract_symbol or ""):
        raise InvalidProbeConfiguration(
            "exact quarterly MES or approved continuous MES/ES contract required"
        )
    if not re.fullmatch(r"/MES[HMUZ]\d{2}:XCME", streamer_symbol or ""):
        raise InvalidProbeConfiguration("exact XCME DXLink symbol required")
    if contract_symbol[:5] != streamer_symbol[:5]:
        raise InvalidProbeConfiguration("contract and streamer month disagree")
    if contract_symbol[-1] != streamer_symbol[-6]:
        raise InvalidProbeConfiguration("contract and streamer year disagree")


def candle_identity(event: Any, spec: "ProbeSpec") -> tuple[datetime, int]:
    """Return provider identity fields, including for removal tombstones."""
    event_symbol = str(getattr(event, "event_symbol", ""))
    # dxFeed normalizes a one-minute period from the requested ``1m`` to ``m``
    # in returned Candle event symbols.  Keep identity validation exact while
    # accepting only those two provider-equivalent spellings.
    periods = {spec.interval}
    if spec.interval == "1m":
        periods.add("m")
    elif spec.interval == "1h":
        periods.add("h")
    expected_symbols = {
        f"{spec.streamer_symbol}{{={period}}}" for period in periods
    }
    if event_symbol not in expected_symbols:
        raise ValueError("unexpected candle symbol")
    timestamp_ms = int(getattr(event, "time"))
    event_time = datetime.fromtimestamp(timestamp_ms / 1000.0, UTC)
    event_flags = int(getattr(event, "event_flags", 0) or 0)
    return event_time, event_flags


@dataclass(frozen=True)
class ProbeSpec:
    contract_symbol: str
    streamer_symbol: str
    interval: str
    requested_from: datetime
    extended_hours: bool = True
    quiet_seconds: float = 4.0
    first_event_timeout_seconds: float = 20.0
    max_messages: int = 12_000

    def __post_init__(self) -> None:
        validate_symbols(self.contract_symbol, self.streamer_symbol)
        if self.interval not in ALLOWED_INTERVALS:
            raise InvalidProbeConfiguration("interval outside frozen probe set")
        object.__setattr__(self, "requested_from", _aware(self.requested_from))
        if not 1.0 <= float(self.quiet_seconds) <= 20.0:
            raise InvalidProbeConfiguration("quiet timeout outside safety range")
        if not 5.0 <= float(self.first_event_timeout_seconds) <= 60.0:
            raise InvalidProbeConfiguration("first-event timeout outside safety range")
        if not 100 <= int(self.max_messages) <= 20_000:
            raise InvalidProbeConfiguration("message cap outside safety range")


def candle_to_row(event: Any, spec: ProbeSpec) -> dict[str, Any]:
    """Validate one provider candle without inventing or repairing values."""
    event_time, event_flags = candle_identity(event, spec)
    values = {name: _finite(getattr(event, name, None)) for name in (
        "open", "high", "low", "close", "volume", "vwap",
        "bid_volume", "ask_volume",
    )}
    prices = [values[name] for name in ("open", "high", "low", "close")]
    if any(value is None or value <= 0 for value in prices):
        raise ValueError("missing or nonpositive OHLC")
    open_, high, low, close = (float(value) for value in prices)
    if not low <= min(open_, close) <= max(open_, close) <= high:
        raise ValueError("invalid candle geometry")
    if not all(_tick_valid(value) for value in (open_, high, low, close)):
        raise ValueError("off-tick CME equity-index candle")
    for name in ("volume", "bid_volume", "ask_volume"):
        if values[name] is not None and values[name] < 0:
            raise ValueError(f"negative {name}")

    count = int(getattr(event, "count", 0) or 0)
    if count < 0:
        raise ValueError("negative candle count")
    return {
        "contract_symbol": spec.contract_symbol,
        "streamer_symbol": spec.streamer_symbol,
        "interval": spec.interval,
        "extended_hours": spec.extended_hours,
        "event_time": event_time,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": values["volume"],
        "vwap": values["vwap"],
        "bid_volume": values["bid_volume"],
        "ask_volume": values["ask_volume"],
        "event_count": count,
        "event_index": int(getattr(event, "index", 0) or 0),
        "sequence": int(getattr(event, "sequence", 0) or 0),
        "event_flags": event_flags,
        "source": SOURCE,
    }


def classify_snapshot(
    spec: ProbeSpec,
    rows: Iterable[dict[str, Any]],
    invalid_messages: int,
    message_limit_hit: bool,
) -> dict[str, Any]:
    items = list(rows)
    if not items:
        return {
            "state": "NO_DATA",
            "earliest_event": None,
            "latest_event": None,
            "reached_start": False,
            "cap_suspected": False,
            "valid_rows": 0,
            "invalid_messages": int(invalid_messages),
        }
    earliest = min(item["event_time"] for item in items)
    latest = max(item["event_time"] for item in items)
    tolerance = timedelta(minutes=ALLOWED_INTERVALS[spec.interval])
    reached_start = earliest <= spec.requested_from + tolerance
    cap_suspected = bool(message_limit_hit or (
        not reached_start and len(items) >= 7_900
    ))
    state = "COMPLETE" if reached_start else (
        "CAP_TRUNCATED" if cap_suspected else "PARTIAL_WINDOW"
    )
    return {
        "state": state,
        "earliest_event": earliest,
        "latest_event": latest,
        "reached_start": reached_start,
        "cap_suspected": cap_suspected,
        "valid_rows": len(items),
        "invalid_messages": int(invalid_messages),
    }


class MESCandleProbeStore:
    """Dedicated research-only persistence for probe data and coverage facts."""

    def __init__(self, connection_factory: Optional[Callable[[], Any]] = None):
        self.connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        from database_adapter import get_connection

        return get_connection()

    def _run(self, operation: Callable[[Any], Any]) -> Any:
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            result = operation(cursor)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        def create(cursor):
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS valor_mes_dxlink_candles (
                    contract_symbol TEXT NOT NULL,
                    streamer_symbol TEXT NOT NULL,
                    interval TEXT NOT NULL CHECK (interval IN ('1m','5m','15m','1h')),
                    extended_hours BOOLEAN NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL,
                    open DOUBLE PRECISION NOT NULL,
                    high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL,
                    close DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION,
                    vwap DOUBLE PRECISION,
                    bid_volume DOUBLE PRECISION,
                    ask_volume DOUBLE PRECISION,
                    event_count BIGINT NOT NULL,
                    event_index BIGINT NOT NULL,
                    sequence BIGINT NOT NULL,
                    event_flags INTEGER NOT NULL,
                    source TEXT NOT NULL CHECK (source='TASTYTRADE_DXLINK_CANDLE'),
                    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (streamer_symbol, interval, extended_hours, event_time)
                )
            """)
            cursor.execute("""
                ALTER TABLE valor_mes_dxlink_candles
                DROP CONSTRAINT IF EXISTS valor_mes_dxlink_candles_interval_check
            """)
            cursor.execute("""
                ALTER TABLE valor_mes_dxlink_candles
                ADD CONSTRAINT valor_mes_dxlink_candles_interval_check
                CHECK (interval IN ('1m','5m','15m','1h'))
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_valor_mes_dxlink_candles_time
                ON valor_mes_dxlink_candles (interval, event_time)
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS valor_mes_dxlink_candle_probe_runs (
                    run_id TEXT PRIMARY KEY,
                    contract_symbol TEXT NOT NULL,
                    streamer_symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    extended_hours BOOLEAN NOT NULL,
                    requested_from TIMESTAMPTZ NOT NULL,
                    source TEXT NOT NULL,
                    read_only BOOLEAN NOT NULL DEFAULT TRUE,
                    state TEXT NOT NULL,
                    messages_received INTEGER NOT NULL DEFAULT 0,
                    valid_rows INTEGER NOT NULL DEFAULT 0,
                    invalid_messages INTEGER NOT NULL DEFAULT 0,
                    earliest_event TIMESTAMPTZ,
                    latest_event TIMESTAMPTZ,
                    reached_start BOOLEAN NOT NULL DEFAULT FALSE,
                    cap_suspected BOOLEAN NOT NULL DEFAULT FALSE,
                    error_code TEXT,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_valor_mes_dxlink_probe_lookup
                ON valor_mes_dxlink_candle_probe_runs
                (streamer_symbol, interval, requested_from, updated_at DESC)
            """)
        self._run(create)

    def has_terminal_run(self, spec: ProbeSpec) -> bool:
        def query(cursor):
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM valor_mes_dxlink_candle_probe_runs
                    WHERE streamer_symbol=%s AND interval=%s
                      AND extended_hours=%s AND requested_from=%s
                      AND state IN ('COMPLETE','CAP_TRUNCATED')
                )
            """, (
                spec.streamer_symbol, spec.interval, spec.extended_hours,
                spec.requested_from,
            ))
            return bool(cursor.fetchone()[0])
        return self._run(query)

    def start_run(self, run_id: str, spec: ProbeSpec) -> None:
        self._run(lambda cursor: cursor.execute("""
            INSERT INTO valor_mes_dxlink_candle_probe_runs (
                run_id, contract_symbol, streamer_symbol, interval,
                extended_hours, requested_from, source, read_only, state
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,'RUNNING')
        """, (
            run_id, spec.contract_symbol, spec.streamer_symbol, spec.interval,
            spec.extended_hours, spec.requested_from, SOURCE,
        )))

    def finish_run(self, run_id: str, messages_received: int,
                   summary: dict[str, Any], error_code: Optional[str] = None) -> None:
        self._run(lambda cursor: cursor.execute("""
            UPDATE valor_mes_dxlink_candle_probe_runs
            SET state=%s, messages_received=%s, valid_rows=%s,
                invalid_messages=%s, earliest_event=%s, latest_event=%s,
                reached_start=%s, cap_suspected=%s, error_code=%s,
                completed_at=NOW(), updated_at=NOW()
            WHERE run_id=%s
        """, (
            summary["state"], messages_received, summary["valid_rows"],
            summary["invalid_messages"], summary["earliest_event"],
            summary["latest_event"], summary["reached_start"],
            summary["cap_suspected"], error_code, run_id,
        )))

    def fail_run(self, run_id: str, error_code: str) -> None:
        self._run(lambda cursor: cursor.execute("""
            UPDATE valor_mes_dxlink_candle_probe_runs
            SET state='ERROR', error_code=%s, completed_at=NOW(), updated_at=NOW()
            WHERE run_id=%s
        """, (error_code, run_id)))

    def upsert_rows(self, rows: Iterable[dict[str, Any]]) -> None:
        items = list(rows)
        if not items:
            return
        columns = (
            "contract_symbol", "streamer_symbol", "interval", "extended_hours",
            "event_time", "open", "high", "low", "close", "volume", "vwap",
            "bid_volume", "ask_volume", "event_count", "event_index", "sequence",
            "event_flags", "source",
        )
        placeholders = ",".join(["%s"] * len(columns))
        updates = ",".join(
            f"{name}=EXCLUDED.{name}" for name in columns
            if name not in {"streamer_symbol", "interval", "extended_hours", "event_time"}
        )
        sql = (
            f"INSERT INTO valor_mes_dxlink_candles ({','.join(columns)}) "
            f"VALUES ({placeholders}) ON CONFLICT "
            f"(streamer_symbol,interval,extended_hours,event_time) "
            f"DO UPDATE SET {updates}, recorded_at=NOW()"
        )
        values = [tuple(row[name] for name in columns) for row in items]
        self._run(lambda cursor: cursor.executemany(sql, values))


async def collect_snapshot(
    spec: ProbeSpec,
    session: Any,
    streamer_factory: Callable[[Any], Any],
    candle_class: Any,
) -> tuple[list[dict[str, Any]], int, int, bool]:
    """Collect one bounded provider snapshot; never requests account data."""
    rows: dict[datetime, dict[str, Any]] = {}
    invalid_messages = 0
    messages_received = 0
    message_limit_hit = False
    async with streamer_factory(session) as streamer:
        await streamer.subscribe_candle(
            [spec.streamer_symbol], spec.interval, spec.requested_from,
            extended_trading_hours=spec.extended_hours,
        )
        while messages_received < spec.max_messages:
            timeout = (
                spec.first_event_timeout_seconds if messages_received == 0
                else spec.quiet_seconds
            )
            try:
                event = await asyncio.wait_for(
                    streamer.get_event(candle_class), timeout=timeout
                )
            except asyncio.TimeoutError:
                break
            messages_received += 1
            try:
                event_time, event_flags = candle_identity(event, spec)
                if event_flags & 2:  # dxFeed REMOVE_EVENT tombstone
                    rows.pop(event_time, None)
                    continue
                row = candle_to_row(event, spec)
            except (AttributeError, TypeError, ValueError, OverflowError):
                invalid_messages += 1
                continue
            rows[row["event_time"]] = row
        else:
            message_limit_hit = True
    return (
        [rows[key] for key in sorted(rows)], messages_received,
        invalid_messages, message_limit_hit,
    )


async def run_spec(
    spec: ProbeSpec,
    store: MESCandleProbeStore,
    session_factory: Callable[[str, str], Any],
    streamer_factory: Callable[[Any], Any],
    candle_class: Any,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    if store.has_terminal_run(spec):
        return {"state": "ALREADY_TERMINAL", "interval": spec.interval}
    run_id = str(uuid.uuid4())
    store.start_run(run_id, spec)
    try:
        session = session_factory(client_secret, refresh_token)
        rows, messages, invalid, limit_hit = await collect_snapshot(
            spec, session, streamer_factory, candle_class
        )
        summary = classify_snapshot(spec, rows, invalid, limit_hit)
        store.upsert_rows(rows)
        store.finish_run(run_id, messages, summary)
        return {"run_id": run_id, "messages_received": messages, **summary}
    except Exception as exc:
        error_code = type(exc).__name__
        store.fail_run(run_id, error_code)
        raise


def _specs_from_env() -> list[ProbeSpec]:
    contract = os.getenv("VALOR_MES_DXLINK_PROBE_CONTRACT", DEFAULT_CONTRACT)
    streamer = os.getenv("VALOR_MES_DXLINK_PROBE_STREAMER", DEFAULT_STREAMER)
    requested_from = _aware(os.getenv("VALOR_MES_DXLINK_PROBE_FROM", DEFAULT_FROM))
    raw_intervals = os.getenv("VALOR_MES_DXLINK_PROBE_INTERVALS", "1m,15m")
    intervals = [item.strip() for item in raw_intervals.split(",") if item.strip()]
    if not intervals or len(intervals) != len(set(intervals)):
        raise InvalidProbeConfiguration("unique nonempty intervals required")
    return [ProbeSpec(contract, streamer, interval, requested_from) for interval in intervals]


async def _run_from_env() -> list[dict[str, Any]]:
    if not STREAMING_AVAILABLE:
        raise RuntimeError("TastytradeStreamingUnavailable")
    client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
    refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")
    if not client_secret or not refresh_token:
        raise RuntimeError("TastytradeOAuthMissing")
    store = MESCandleProbeStore()
    await asyncio.to_thread(store.ensure_schema)
    results = []
    for spec in _specs_from_env():
        result = await run_spec(
            spec, store, Session, DXLinkStreamer, Candle,
            client_secret, refresh_token,
        )
        results.append(result)
    return results


_launch_lock = threading.Lock()
_probe_thread: Optional[threading.Thread] = None


def launch_if_enabled() -> bool:
    """Launch one daemon probe only when explicitly enabled on the service."""
    enabled = os.getenv(
        "VALOR_MES_DXLINK_CANDLE_PROBE_AUTORUN", "false"
    ).lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return False
    global _probe_thread
    with _launch_lock:
        if _probe_thread and _probe_thread.is_alive():
            return True

        def target() -> None:
            try:
                results = asyncio.run(_run_from_env())
                logger.info("MES DXLink candle probe finished: %s", results)
            except Exception as exc:  # research failure must not stop the API
                logger.exception("MES DXLink candle probe failed: %s", type(exc).__name__)

        _probe_thread = threading.Thread(
            target=target, name="mes-dxlink-candle-probe", daemon=True
        )
        _probe_thread.start()
        return True


if __name__ == "__main__":  # manual read-only research invocation
    print(asyncio.run(_run_from_env()))
