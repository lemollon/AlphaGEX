"""Read-only MES quote and time-and-sale collection.

This module deliberately has no account, position, or order imports.  It uses
Tastytrade OAuth only to resolve the exact active MES contract and subscribe to
DXLink Quote and TimeAndSale events.  Events are reduced to bounded one-minute
connection segments so the existing Render Postgres plan cannot be flooded by
an unbounded raw tape.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

UTC = timezone.utc
ROOT_SYMBOL = "MES"
SOURCE = "TASTYTRADE_DXLINK"
READ_ONLY_MODE = True
STATUS_HEARTBEAT_SECONDS = 30
CONNECTION_ROTATION_SECONDS = 60 * 60

try:
    from tastytrade import DXLinkStreamer, Session
    from tastytrade.dxfeed import Quote, TimeAndSale
    from tastytrade.instruments import Future

    TASTYTRADE_STREAMING_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on minimal local installs
    DXLinkStreamer = Session = Quote = TimeAndSale = Future = None
    TASTYTRADE_STREAMING_AVAILABLE = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _minute(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(second=0, microsecond=0)


def _finite(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _provider_time(milliseconds: Any) -> Optional[datetime]:
    value = _finite(milliseconds)
    if value is None or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _event_kind(value: Any) -> str:
    text = str(value or "NEW").upper()
    if "CANCEL" in text:
        return "CANCEL"
    if "CORRECT" in text:
        return "CORRECTION"
    return "NEW"


def _aggressor(value: Any) -> str:
    text = str(value or "").upper()
    if "BUY" in text:
        return "BUY"
    if "SELL" in text:
        return "SELL"
    return "UNKNOWN"


@dataclass(frozen=True)
class SaleContribution:
    index: int
    sequence: int
    event_time: datetime
    price: float
    size: int
    aggressor: str
    spread_leg: bool
    extended_hours: bool


@dataclass
class MinuteAggregate:
    bucket_start: datetime
    contract_symbol: str
    streamer_symbol: str
    connection_id: str
    first_received_at: Optional[datetime] = None
    last_received_at: Optional[datetime] = None
    quote_event_count: int = 0
    valid_quote_count: int = 0
    invalid_quote_count: int = 0
    quote_exchange_time_count: int = 0
    first_quote_exchange_at: Optional[datetime] = None
    last_quote_exchange_at: Optional[datetime] = None
    bid_open: Optional[float] = None
    bid_high: Optional[float] = None
    bid_low: Optional[float] = None
    bid_close: Optional[float] = None
    ask_open: Optional[float] = None
    ask_high: Optional[float] = None
    ask_low: Optional[float] = None
    ask_close: Optional[float] = None
    bid_size_sum: float = 0.0
    ask_size_sum: float = 0.0
    bid_size_close: Optional[float] = None
    ask_size_close: Optional[float] = None
    spread_sum: float = 0.0
    spread_min: Optional[float] = None
    spread_max: Optional[float] = None
    spread_close: Optional[float] = None
    trade_message_count: int = 0
    invalid_trade_count: int = 0
    duplicate_trade_count: int = 0
    correction_count: int = 0
    cancellation_count: int = 0
    late_adjustment_count: int = 0
    last_seen_sale_index: Optional[int] = None
    sales: Dict[int, SaleContribution] = field(default_factory=dict)

    def _touch(self, received_at: datetime) -> None:
        if self.first_received_at is None or received_at < self.first_received_at:
            self.first_received_at = received_at
        if self.last_received_at is None or received_at > self.last_received_at:
            self.last_received_at = received_at

    def add_quote(self, quote: Any, received_at: datetime) -> bool:
        self.quote_event_count += 1
        self._touch(received_at)
        if getattr(quote, "event_symbol", None) != self.streamer_symbol:
            self.invalid_quote_count += 1
            return False

        bid = _finite(getattr(quote, "bid_price", None))
        ask = _finite(getattr(quote, "ask_price", None))
        bid_size = _finite(getattr(quote, "bid_size", None))
        ask_size = _finite(getattr(quote, "ask_size", None))
        if (bid is None or ask is None or bid_size is None or ask_size is None
                or bid <= 0 or ask <= 0 or bid > ask
                or bid_size < 0 or ask_size < 0):
            self.invalid_quote_count += 1
            return False

        self.valid_quote_count += 1
        self.bid_open = bid if self.bid_open is None else self.bid_open
        self.ask_open = ask if self.ask_open is None else self.ask_open
        self.bid_high = bid if self.bid_high is None else max(self.bid_high, bid)
        self.bid_low = bid if self.bid_low is None else min(self.bid_low, bid)
        self.ask_high = ask if self.ask_high is None else max(self.ask_high, ask)
        self.ask_low = ask if self.ask_low is None else min(self.ask_low, ask)
        self.bid_close, self.ask_close = bid, ask
        self.bid_size_sum += bid_size
        self.ask_size_sum += ask_size
        self.bid_size_close, self.ask_size_close = bid_size, ask_size

        spread = ask - bid
        self.spread_sum += spread
        self.spread_min = spread if self.spread_min is None else min(self.spread_min, spread)
        self.spread_max = spread if self.spread_max is None else max(self.spread_max, spread)
        self.spread_close = spread

        bid_time = _provider_time(getattr(quote, "bid_time", None))
        ask_time = _provider_time(getattr(quote, "ask_time", None))
        if bid_time is not None and ask_time is not None:
            older, newer = min(bid_time, ask_time), max(bid_time, ask_time)
            self.quote_exchange_time_count += 1
            if self.first_quote_exchange_at is None or older < self.first_quote_exchange_at:
                self.first_quote_exchange_at = older
            if self.last_quote_exchange_at is None or newer > self.last_quote_exchange_at:
                self.last_quote_exchange_at = newer
        return True

    def add_sale(self, sale: SaleContribution, kind: str) -> bool:
        self.trade_message_count += 1
        if kind == "CANCEL":
            self.cancellation_count += 1
            if sale.index not in self.sales:
                self.late_adjustment_count += 1
                return False
            del self.sales[sale.index]
            return True
        if kind == "CORRECTION":
            self.correction_count += 1
            if sale.index not in self.sales:
                self.late_adjustment_count += 1
                return False
            self.sales[sale.index] = sale
            return True
        if sale.index in self.sales:
            self.duplicate_trade_count += 1
            return False
        self.sales[sale.index] = sale
        self.last_seen_sale_index = (
            sale.index if self.last_seen_sale_index is None
            else max(self.last_seen_sale_index, sale.index)
        )
        return True

    def note_duplicate(self, received_at: datetime) -> None:
        self.trade_message_count += 1
        self.duplicate_trade_count += 1
        self._touch(received_at)

    def note_invalid_trade(self, received_at: datetime) -> None:
        self.trade_message_count += 1
        self.invalid_trade_count += 1
        self._touch(received_at)

    def to_row(self, partial_minute: bool = False) -> Dict[str, Any]:
        ordered = sorted(self.sales.values(), key=lambda row: (row.event_time, row.index))
        prices = [row.price for row in ordered]
        volume = sum(row.size for row in ordered)
        buy_volume = sum(row.size for row in ordered if row.aggressor == "BUY")
        sell_volume = sum(row.size for row in ordered if row.aggressor == "SELL")
        unknown_volume = volume - buy_volume - sell_volume
        return {
            "bucket_start": self.bucket_start,
            "root_symbol": ROOT_SYMBOL,
            "contract_symbol": self.contract_symbol,
            "streamer_symbol": self.streamer_symbol,
            "source": SOURCE,
            "connection_id": self.connection_id,
            "first_received_at": self.first_received_at,
            "last_received_at": self.last_received_at,
            "quote_event_count": self.quote_event_count,
            "valid_quote_count": self.valid_quote_count,
            "invalid_quote_count": self.invalid_quote_count,
            "quote_exchange_time_count": self.quote_exchange_time_count,
            "first_quote_exchange_at": self.first_quote_exchange_at,
            "last_quote_exchange_at": self.last_quote_exchange_at,
            "bid_open": self.bid_open,
            "bid_high": self.bid_high,
            "bid_low": self.bid_low,
            "bid_close": self.bid_close,
            "ask_open": self.ask_open,
            "ask_high": self.ask_high,
            "ask_low": self.ask_low,
            "ask_close": self.ask_close,
            "bid_size_avg": (self.bid_size_sum / self.valid_quote_count
                             if self.valid_quote_count else None),
            "ask_size_avg": (self.ask_size_sum / self.valid_quote_count
                             if self.valid_quote_count else None),
            "bid_size_close": self.bid_size_close,
            "ask_size_close": self.ask_size_close,
            "spread_avg": (self.spread_sum / self.valid_quote_count
                           if self.valid_quote_count else None),
            "spread_min": self.spread_min,
            "spread_max": self.spread_max,
            "spread_close": self.spread_close,
            "trade_message_count": self.trade_message_count,
            "trade_count": len(ordered),
            "invalid_trade_count": self.invalid_trade_count,
            "duplicate_trade_count": self.duplicate_trade_count,
            "correction_count": self.correction_count,
            "cancellation_count": self.cancellation_count,
            "late_adjustment_count": self.late_adjustment_count,
            "trade_open": prices[0] if prices else None,
            "trade_high": max(prices) if prices else None,
            "trade_low": min(prices) if prices else None,
            "trade_close": prices[-1] if prices else None,
            "trade_volume": volume,
            "aggressor_buy_volume": buy_volume,
            "aggressor_sell_volume": sell_volume,
            "unknown_aggressor_volume": unknown_volume,
            "spread_leg_volume": sum(row.size for row in ordered if row.spread_leg),
            "extended_hours_volume": sum(
                row.size for row in ordered if row.extended_hours
            ),
            "first_trade_at": ordered[0].event_time if ordered else None,
            "last_trade_at": ordered[-1].event_time if ordered else None,
            "last_sale_index": self.last_seen_sale_index,
            "quality_complete": not (
                self.invalid_quote_count
                or self.invalid_trade_count
                or self.late_adjustment_count
            ),
            "partial_minute": partial_minute,
            "flushed_at": _utc_now(),
        }


class MESMinuteAggregator:
    """Stateful, deterministic reduction of real DXLink events."""

    def __init__(self, contract_symbol: str, streamer_symbol: str,
                 connection_id: str, persisted_last_sale_index: int = 0):
        self.contract_symbol = contract_symbol
        self.streamer_symbol = streamer_symbol
        self.connection_id = connection_id
        self.last_sale_index = int(persisted_last_sale_index or 0)
        self.buckets: Dict[datetime, MinuteAggregate] = {}
        self.index_to_bucket: Dict[int, datetime] = {}
        self.dirty_buckets: set[datetime] = set()
        self.last_quote_received_at: Optional[datetime] = None
        self.last_sale_received_at: Optional[datetime] = None

    def _bucket(self, when: datetime) -> MinuteAggregate:
        key = _minute(when)
        if key not in self.buckets:
            self.buckets[key] = MinuteAggregate(
                bucket_start=key,
                contract_symbol=self.contract_symbol,
                streamer_symbol=self.streamer_symbol,
                connection_id=self.connection_id,
            )
        self.dirty_buckets.add(key)
        return self.buckets[key]

    def add_quote(self, quote: Any, received_at: Optional[datetime] = None) -> bool:
        received_at = received_at or _utc_now()
        self.last_quote_received_at = received_at
        return self._bucket(received_at).add_quote(quote, received_at)

    def add_sale(self, event: Any, received_at: Optional[datetime] = None) -> bool:
        received_at = received_at or _utc_now()
        self.last_sale_received_at = received_at
        event_time = _provider_time(getattr(event, "time", None)) or received_at
        bucket = self._bucket(event_time)
        bucket._touch(received_at)
        if getattr(event, "event_symbol", None) != self.streamer_symbol:
            bucket.note_invalid_trade(received_at)
            return False

        index = getattr(event, "index", None)
        sequence = getattr(event, "sequence", 0)
        price = _finite(getattr(event, "price", None))
        size_value = _finite(getattr(event, "size", None))
        if (not isinstance(index, int) or price is None or size_value is None
                or price <= 0 or size_value <= 0 or not float(size_value).is_integer()
                or getattr(event, "valid_tick", True) is False):
            bucket.note_invalid_trade(received_at)
            return False

        kind = _event_kind(getattr(event, "type", None))
        if kind == "NEW" and index <= self.last_sale_index:
            bucket.note_duplicate(received_at)
            return False

        original_bucket = self.index_to_bucket.get(index)
        if kind != "NEW" and original_bucket is not None:
            bucket = self.buckets[original_bucket]
            self.dirty_buckets.add(original_bucket)

        sale = SaleContribution(
            index=index,
            sequence=int(sequence or 0),
            event_time=event_time,
            price=price,
            size=int(size_value),
            aggressor=_aggressor(getattr(event, "aggressor_side", None)),
            spread_leg=bool(getattr(event, "spread_leg", False)),
            extended_hours=bool(getattr(event, "extended_trading_hours", False)),
        )
        accepted = bucket.add_sale(sale, kind)
        if kind == "NEW" and accepted:
            self.index_to_bucket[index] = bucket.bucket_start
            self.last_sale_index = max(self.last_sale_index, index)
        elif kind == "CANCEL" and accepted:
            self.index_to_bucket.pop(index, None)
        return accepted

    def pop_completed(self, now: Optional[datetime] = None) -> list[Dict[str, Any]]:
        cutoff = _minute(now or _utc_now())
        keys = sorted(key for key in self.dirty_buckets if key < cutoff)
        return self._pop(keys, partial=False)

    def pop_all(self) -> list[Dict[str, Any]]:
        current = _minute(_utc_now())
        rows = []
        for key in sorted(self.dirty_buckets):
            rows.append(self.buckets[key].to_row(partial_minute=key >= current))
        self.dirty_buckets.clear()
        return rows

    def _pop(self, keys: Iterable[datetime], partial: bool) -> list[Dict[str, Any]]:
        rows = []
        for key in keys:
            bucket = self.buckets[key]
            rows.append(bucket.to_row(partial_minute=partial))
            self.dirty_buckets.discard(key)
        return rows


SEGMENT_COLUMNS = (
    "bucket_start", "root_symbol", "contract_symbol", "streamer_symbol",
    "source", "connection_id", "first_received_at", "last_received_at",
    "quote_event_count", "valid_quote_count", "invalid_quote_count",
    "quote_exchange_time_count", "first_quote_exchange_at",
    "last_quote_exchange_at", "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close", "bid_size_avg",
    "ask_size_avg", "bid_size_close", "ask_size_close", "spread_avg",
    "spread_min", "spread_max", "spread_close", "trade_message_count",
    "trade_count", "invalid_trade_count", "duplicate_trade_count",
    "correction_count", "cancellation_count", "late_adjustment_count",
    "trade_open", "trade_high", "trade_low", "trade_close", "trade_volume",
    "aggressor_buy_volume", "aggressor_sell_volume",
    "unknown_aggressor_volume", "spread_leg_volume", "extended_hours_volume",
    "first_trade_at", "last_trade_at", "last_sale_index", "quality_complete",
    "partial_minute", "flushed_at",
)


class MESMicrostructureStore:
    """Small Postgres store for minute segments, gap markers, and liveness."""

    def __init__(self, connection_factory: Optional[Callable[[], Any]] = None):
        self.connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        from database_adapter import get_connection

        return get_connection()

    def _run(self, operation: Callable[[Any], Any]) -> Any:
        conn = self.connection_factory()
        try:
            cursor = conn.cursor()
            result = operation(cursor)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        def create(cursor):
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS valor_mes_microstructure_minute_segments (
                    bucket_start TIMESTAMPTZ NOT NULL,
                    root_symbol TEXT NOT NULL CHECK (root_symbol = 'MES'),
                    contract_symbol TEXT NOT NULL,
                    streamer_symbol TEXT NOT NULL,
                    source TEXT NOT NULL CHECK (source = 'TASTYTRADE_DXLINK'),
                    connection_id TEXT NOT NULL,
                    first_received_at TIMESTAMPTZ,
                    last_received_at TIMESTAMPTZ,
                    quote_event_count INTEGER NOT NULL,
                    valid_quote_count INTEGER NOT NULL,
                    invalid_quote_count INTEGER NOT NULL,
                    quote_exchange_time_count INTEGER NOT NULL,
                    first_quote_exchange_at TIMESTAMPTZ,
                    last_quote_exchange_at TIMESTAMPTZ,
                    bid_open DOUBLE PRECISION, bid_high DOUBLE PRECISION,
                    bid_low DOUBLE PRECISION, bid_close DOUBLE PRECISION,
                    ask_open DOUBLE PRECISION, ask_high DOUBLE PRECISION,
                    ask_low DOUBLE PRECISION, ask_close DOUBLE PRECISION,
                    bid_size_avg DOUBLE PRECISION, ask_size_avg DOUBLE PRECISION,
                    bid_size_close DOUBLE PRECISION, ask_size_close DOUBLE PRECISION,
                    spread_avg DOUBLE PRECISION, spread_min DOUBLE PRECISION,
                    spread_max DOUBLE PRECISION, spread_close DOUBLE PRECISION,
                    trade_message_count INTEGER NOT NULL, trade_count INTEGER NOT NULL,
                    invalid_trade_count INTEGER NOT NULL,
                    duplicate_trade_count INTEGER NOT NULL,
                    correction_count INTEGER NOT NULL, cancellation_count INTEGER NOT NULL,
                    late_adjustment_count INTEGER NOT NULL,
                    trade_open DOUBLE PRECISION, trade_high DOUBLE PRECISION,
                    trade_low DOUBLE PRECISION, trade_close DOUBLE PRECISION,
                    trade_volume BIGINT NOT NULL,
                    aggressor_buy_volume BIGINT NOT NULL,
                    aggressor_sell_volume BIGINT NOT NULL,
                    unknown_aggressor_volume BIGINT NOT NULL,
                    spread_leg_volume BIGINT NOT NULL,
                    extended_hours_volume BIGINT NOT NULL,
                    first_trade_at TIMESTAMPTZ, last_trade_at TIMESTAMPTZ,
                    last_sale_index BIGINT,
                    quality_complete BOOLEAN NOT NULL,
                    partial_minute BOOLEAN NOT NULL,
                    flushed_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (bucket_start, contract_symbol, connection_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_valor_mes_microstructure_recent
                ON valor_mes_microstructure_minute_segments (bucket_start DESC)
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS valor_mes_collection_gaps (
                    gap_id TEXT PRIMARY KEY,
                    started_at TIMESTAMPTZ NOT NULL,
                    ended_at TIMESTAMPTZ,
                    reason_code TEXT NOT NULL,
                    connection_id TEXT,
                    contract_symbol TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_valor_mes_gaps_open
                ON valor_mes_collection_gaps (started_at DESC)
                WHERE ended_at IS NULL
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS valor_mes_collector_status (
                    root_symbol TEXT PRIMARY KEY CHECK (root_symbol = 'MES'),
                    read_only BOOLEAN NOT NULL DEFAULT TRUE,
                    enabled BOOLEAN NOT NULL,
                    connected BOOLEAN NOT NULL,
                    contract_symbol TEXT,
                    streamer_symbol TEXT,
                    connection_id TEXT,
                    last_connect_at TIMESTAMPTZ,
                    last_disconnect_at TIMESTAMPTZ,
                    last_quote_at TIMESTAMPTZ,
                    last_sale_at TIMESTAMPTZ,
                    last_flush_at TIMESTAMPTZ,
                    last_error_code TEXT,
                    reconnect_count INTEGER NOT NULL DEFAULT 0,
                    last_sale_index BIGINT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        self._run(create)

    def upsert_segment(self, row: Dict[str, Any]) -> None:
        columns = ", ".join(SEGMENT_COLUMNS)
        placeholders = ", ".join(["%s"] * len(SEGMENT_COLUMNS))
        updates = ", ".join(
            f"{column}=EXCLUDED.{column}"
            for column in SEGMENT_COLUMNS
            if column not in {"bucket_start", "contract_symbol", "connection_id"}
        )
        sql = (
            f"INSERT INTO valor_mes_microstructure_minute_segments ({columns}) "
            f"VALUES ({placeholders}) ON CONFLICT "
            f"(bucket_start, contract_symbol, connection_id) DO UPDATE SET {updates}"
        )
        values = tuple(row[column] for column in SEGMENT_COLUMNS)
        self._run(lambda cursor: cursor.execute(sql, values))

    def last_sale_index(self, contract_symbol: str) -> int:
        def query(cursor):
            cursor.execute("""
                SELECT COALESCE(MAX(last_sale_index), 0)
                FROM valor_mes_microstructure_minute_segments
                WHERE contract_symbol = %s
            """, (contract_symbol,))
            row = cursor.fetchone()
            return int(row[0] or 0)
        return self._run(query)

    def open_gap(self, reason_code: str, started_at: Optional[datetime] = None) -> str:
        gap_id = str(uuid.uuid4())
        self._run(lambda cursor: cursor.execute("""
            INSERT INTO valor_mes_collection_gaps (gap_id, started_at, reason_code)
            VALUES (%s, %s, %s)
        """, (gap_id, started_at or _utc_now(), reason_code)))
        return gap_id

    def close_gap(self, gap_id: str, connection_id: str,
                  contract_symbol: str, ended_at: Optional[datetime] = None) -> None:
        self._run(lambda cursor: cursor.execute("""
            UPDATE valor_mes_collection_gaps
            SET ended_at=%s, connection_id=%s, contract_symbol=%s
            WHERE gap_id=%s AND ended_at IS NULL
        """, (ended_at or _utc_now(), connection_id, contract_symbol, gap_id)))

    def update_status(self, *, enabled: bool, connected: bool,
                      contract_symbol: Optional[str] = None,
                      streamer_symbol: Optional[str] = None,
                      connection_id: Optional[str] = None,
                      last_connect_at: Optional[datetime] = None,
                      last_disconnect_at: Optional[datetime] = None,
                      last_quote_at: Optional[datetime] = None,
                      last_sale_at: Optional[datetime] = None,
                      last_flush_at: Optional[datetime] = None,
                      last_error_code: Optional[str] = None,
                      reconnect_count: int = 0,
                      last_sale_index: Optional[int] = None) -> None:
        values = (
            ROOT_SYMBOL, enabled, connected, contract_symbol, streamer_symbol,
            connection_id, last_connect_at, last_disconnect_at, last_quote_at,
            last_sale_at, last_flush_at, last_error_code, reconnect_count,
            last_sale_index,
        )
        self._run(lambda cursor: cursor.execute("""
            INSERT INTO valor_mes_collector_status (
                root_symbol, read_only, enabled, connected, contract_symbol,
                streamer_symbol, connection_id, last_connect_at,
                last_disconnect_at, last_quote_at, last_sale_at, last_flush_at,
                last_error_code, reconnect_count, last_sale_index, updated_at
            ) VALUES (%s, TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, NOW())
            ON CONFLICT (root_symbol) DO UPDATE SET
                read_only=TRUE, enabled=EXCLUDED.enabled,
                connected=EXCLUDED.connected,
                contract_symbol=COALESCE(EXCLUDED.contract_symbol,
                                         valor_mes_collector_status.contract_symbol),
                streamer_symbol=COALESCE(EXCLUDED.streamer_symbol,
                                         valor_mes_collector_status.streamer_symbol),
                connection_id=COALESCE(EXCLUDED.connection_id,
                                       valor_mes_collector_status.connection_id),
                last_connect_at=COALESCE(EXCLUDED.last_connect_at,
                                         valor_mes_collector_status.last_connect_at),
                last_disconnect_at=COALESCE(EXCLUDED.last_disconnect_at,
                                            valor_mes_collector_status.last_disconnect_at),
                last_quote_at=COALESCE(EXCLUDED.last_quote_at,
                                       valor_mes_collector_status.last_quote_at),
                last_sale_at=COALESCE(EXCLUDED.last_sale_at,
                                      valor_mes_collector_status.last_sale_at),
                last_flush_at=COALESCE(EXCLUDED.last_flush_at,
                                       valor_mes_collector_status.last_flush_at),
                last_error_code=EXCLUDED.last_error_code,
                reconnect_count=EXCLUDED.reconnect_count,
                last_sale_index=COALESCE(EXCLUDED.last_sale_index,
                                         valor_mes_collector_status.last_sale_index),
                updated_at=NOW()
        """, values))


class MESMicrostructureCollector:
    """Supervised read-only DXLink collector running in one daemon thread."""

    def __init__(self, *, enabled: bool, client_secret: Optional[str],
                 refresh_token: Optional[str],
                 store: Optional[MESMicrostructureStore] = None):
        self.enabled = bool(enabled)
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.store = store or MESMicrostructureStore()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._reconnect_count = 0
        self._attempt_connected = False

    @classmethod
    def from_env(cls) -> "MESMicrostructureCollector":
        enabled = os.getenv("MES_MICROSTRUCTURE_COLLECTOR_ENABLED", "false").lower()
        return cls(
            enabled=enabled in {"1", "true", "yes"},
            client_secret=os.getenv("TASTYTRADE_CLIENT_SECRET"),
            refresh_token=os.getenv("TASTYTRADE_REFRESH_TOKEN"),
        )

    def start(self) -> bool:
        if not self.enabled:
            logger.info("MES microstructure collector disabled")
            return False
        if not TASTYTRADE_STREAMING_AVAILABLE:
            logger.error("MES collector unavailable: tastytrade SDK missing")
            return False
        if not self.client_secret or not self.refresh_token:
            logger.error("MES collector unavailable: OAuth credentials missing")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="mes-microstructure-collector",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 15.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:  # fail closed; scheduler remains available
            logger.exception("MES collector stopped: %s", type(exc).__name__)

    async def _run(self) -> None:
        await asyncio.to_thread(self.store.ensure_schema)
        await asyncio.to_thread(
            self.store.update_status,
            enabled=True,
            connected=False,
            last_error_code=None,
        )
        gap_id = await asyncio.to_thread(self.store.open_gap, "startup")
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._attempt_connected = False
                await self._connection_once(gap_id)
                backoff = 1.0
                if self._stop.is_set():
                    break
                await asyncio.to_thread(
                    self.store.update_status,
                    enabled=True,
                    connected=False,
                    last_disconnect_at=_utc_now(),
                    last_error_code="scheduled_rotation",
                    reconnect_count=self._reconnect_count,
                )
                gap_id = await asyncio.to_thread(
                    self.store.open_gap, "scheduled_rotation"
                )
            except Exception as exc:
                self._reconnect_count += 1
                code = type(exc).__name__
                logger.warning("MES collector reconnect after %s", code)
                await asyncio.to_thread(
                    self.store.update_status,
                    enabled=True,
                    connected=False,
                    last_disconnect_at=_utc_now(),
                    last_error_code=code,
                    reconnect_count=self._reconnect_count,
                )
                if self._attempt_connected:
                    gap_id = await asyncio.to_thread(
                        self.store.open_gap, f"stream_error:{code}"
                    )
                await self._interruptible_sleep(backoff)
                backoff = min(backoff * 2, 60.0)

        await asyncio.to_thread(
            self.store.update_status,
            enabled=True,
            connected=False,
            last_disconnect_at=_utc_now(),
            last_error_code="clean_shutdown",
            reconnect_count=self._reconnect_count,
        )

    async def _interruptible_sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self._stop.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    async def _resolve_contract(self, session: Any) -> tuple[str, str]:
        futures = await asyncio.wait_for(
            Future.get(session, product_codes=[ROOT_SYMBOL]), timeout=15
        )
        now = _utc_now()
        eligible = [
            future for future in futures
            if getattr(future, "product_code", None) == ROOT_SYMBOL
            and getattr(future, "active_month", False)
            and getattr(future, "is_tradeable", False)
            and not getattr(future, "is_closing_only", True)
            and getattr(future, "stops_trading_at", now) > now
            and str(getattr(future, "symbol", "")).startswith("/MES")
            and getattr(future, "streamer_symbol", None)
        ]
        if len(eligible) != 1:
            raise RuntimeError("MESContractResolutionError")
        return eligible[0].symbol, eligible[0].streamer_symbol

    async def _connection_once(self, gap_id: str) -> None:
        session = Session(self.client_secret, self.refresh_token)
        contract_symbol, streamer_symbol = await self._resolve_contract(session)
        connection_id = str(uuid.uuid4())
        persisted_index = await asyncio.to_thread(
            self.store.last_sale_index, contract_symbol
        )
        aggregate = MESMinuteAggregator(
            contract_symbol,
            streamer_symbol,
            connection_id,
            persisted_last_sale_index=persisted_index,
        )

        try:
            async with DXLinkStreamer(session) as streamer:
                await streamer.subscribe(Quote, [streamer_symbol], refresh_interval=0.1)
                await streamer.subscribe(
                    TimeAndSale, [streamer_symbol], refresh_interval=0.1
                )
                connected_at = _utc_now()
                await asyncio.to_thread(
                    self.store.close_gap,
                    gap_id,
                    connection_id,
                    contract_symbol,
                    connected_at,
                )
                self._attempt_connected = True
                await asyncio.to_thread(
                    self.store.update_status,
                    enabled=True,
                    connected=True,
                    contract_symbol=contract_symbol,
                    streamer_symbol=streamer_symbol,
                    connection_id=connection_id,
                    last_connect_at=connected_at,
                    last_error_code=None,
                    reconnect_count=self._reconnect_count,
                    last_sale_index=aggregate.last_sale_index,
                )
                logger.info(
                    "MES read-only collector connected contract=%s source=%s",
                    contract_symbol,
                    SOURCE,
                )

                tasks = [
                    asyncio.create_task(self._consume_quotes(streamer, aggregate)),
                    asyncio.create_task(self._consume_sales(streamer, aggregate)),
                    asyncio.create_task(self._flush_loop(aggregate)),
                    asyncio.create_task(self._rotation_wait()),
                ]
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    error = task.exception()
                    if error is not None:
                        raise error
        finally:
            await self._flush_rows(aggregate.pop_all(), aggregate)

    async def _consume_quotes(self, streamer: Any,
                              aggregate: MESMinuteAggregator) -> None:
        async for event in streamer.listen(Quote):
            aggregate.add_quote(event, _utc_now())

    async def _consume_sales(self, streamer: Any,
                             aggregate: MESMinuteAggregator) -> None:
        async for event in streamer.listen(TimeAndSale):
            aggregate.add_sale(event, _utc_now())

    async def _rotation_wait(self) -> None:
        deadline = time.monotonic() + CONNECTION_ROTATION_SECONDS
        while not self._stop.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(1)

    async def _flush_loop(self, aggregate: MESMinuteAggregator) -> None:
        last_heartbeat = 0.0
        while not self._stop.is_set():
            await asyncio.sleep(1)
            rows = aggregate.pop_completed(_utc_now())
            if rows:
                await self._flush_rows(rows, aggregate)
                last_heartbeat = time.monotonic()
            elif time.monotonic() - last_heartbeat >= STATUS_HEARTBEAT_SECONDS:
                await self._write_status(aggregate, last_flush_at=None)
                last_heartbeat = time.monotonic()

    async def _flush_rows(self, rows: list[Dict[str, Any]],
                          aggregate: MESMinuteAggregator) -> None:
        for row in rows:
            await asyncio.to_thread(self.store.upsert_segment, row)
        await self._write_status(
            aggregate,
            last_flush_at=_utc_now() if rows else None,
        )

    async def _write_status(self, aggregate: MESMinuteAggregator,
                            last_flush_at: Optional[datetime]) -> None:
        await asyncio.to_thread(
            self.store.update_status,
            enabled=True,
            connected=True,
            contract_symbol=aggregate.contract_symbol,
            streamer_symbol=aggregate.streamer_symbol,
            connection_id=aggregate.connection_id,
            last_quote_at=aggregate.last_quote_received_at,
            last_sale_at=aggregate.last_sale_received_at,
            last_flush_at=last_flush_at,
            last_error_code=None,
            reconnect_count=self._reconnect_count,
            last_sale_index=aggregate.last_sale_index,
        )


__all__ = [
    "MESMicrostructureCollector",
    "MESMicrostructureStore",
    "MESMinuteAggregator",
    "MinuteAggregate",
    "READ_ONLY_MODE",
]
