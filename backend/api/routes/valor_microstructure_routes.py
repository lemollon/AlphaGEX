"""Read-only health and coverage metadata for the MES forward collector."""

import asyncio
import os

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/valor/research/mes-microstructure",
    tags=["valor-research"],
)


def _read_status():
    from database_adapter import get_connection

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT read_only, enabled, connected, contract_symbol,
                   streamer_symbol, connection_id, last_connect_at,
                   last_disconnect_at, last_quote_at, last_sale_at,
                   last_flush_at, last_error_code, reconnect_count,
                   last_sale_index, updated_at,
                   EXTRACT(EPOCH FROM (NOW() - updated_at))
            FROM valor_mes_collector_status
            WHERE root_symbol = 'MES'
        """)
        status = cursor.fetchone()
        cursor.execute("""
            SELECT bucket_start, contract_symbol, source, quote_event_count,
                   valid_quote_count, invalid_quote_count,
                   quote_exchange_time_count, trade_message_count, trade_count,
                   invalid_trade_count, duplicate_trade_count, correction_count,
                   cancellation_count, late_adjustment_count, trade_volume,
                   quality_complete, partial_minute, flushed_at
            FROM valor_mes_microstructure_minute_segments
            WHERE root_symbol = 'MES'
            ORDER BY bucket_start DESC, flushed_at DESC
            LIMIT 1
        """)
        latest = cursor.fetchone()
        cursor.execute("""
            SELECT COUNT(*), MIN(started_at)
            FROM valor_mes_collection_gaps
            WHERE ended_at IS NULL
        """)
        gaps = cursor.fetchone()
    finally:
        conn.close()

    if status is None:
        return {
            "configured": os.getenv(
                "MES_MICROSTRUCTURE_COLLECTOR_ENABLED", "false"
            ).lower() in {"1", "true", "yes"},
            "state": "not_started",
            "read_only": True,
            "orders_enabled": False,
            "source": "TASTYTRADE_DXLINK",
            "latest_minute": None,
            "open_gaps": 0,
        }

    status_keys = (
        "read_only", "enabled", "connected", "contract_symbol",
        "streamer_symbol", "connection_id", "last_connect_at",
        "last_disconnect_at", "last_quote_at", "last_sale_at",
        "last_flush_at", "last_error_code", "reconnect_count",
        "last_sale_index", "updated_at", "heartbeat_age_seconds",
    )
    latest_keys = (
        "bucket_start", "contract_symbol", "source", "quote_event_count",
        "valid_quote_count", "invalid_quote_count",
        "quote_exchange_time_count", "trade_message_count", "trade_count",
        "invalid_trade_count", "duplicate_trade_count", "correction_count",
        "cancellation_count", "late_adjustment_count", "trade_volume",
        "quality_complete", "partial_minute", "flushed_at",
    )
    payload = dict(zip(status_keys, status))
    age = float(payload.pop("heartbeat_age_seconds") or 0.0)
    payload.update({
        "configured": True,
        "state": "healthy" if payload["connected"] and age <= 90 else "degraded",
        "collector_heartbeat_age_seconds": round(age, 3),
        "orders_enabled": False,
        "source": "TASTYTRADE_DXLINK",
        "event_types": ["Quote", "TimeAndSale"],
        "aggregation": "one_minute_connection_segments",
        "timestamp_basis": {
            "quotes": "collector_received_minute_with_broker_side_times_retained",
            "trades": "provider_event_time_fallback_collector_received",
        },
        "quote_averages": "event_weighted",
        "latest_minute": dict(zip(latest_keys, latest)) if latest else None,
        "open_gaps": int(gaps[0] or 0) if gaps else 0,
        "oldest_open_gap_at": gaps[1] if gaps else None,
    })
    return payload


@router.get("/status")
async def mes_microstructure_status():
    """Report collector liveness without exposing credentials or account data."""
    try:
        return await asyncio.to_thread(_read_status)
    except Exception as exc:
        raise HTTPException(
            503, "MES microstructure collector status unavailable."
        ) from exc
