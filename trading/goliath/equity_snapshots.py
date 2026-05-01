"""GOLIATH equity snapshot writer.

Per migration 033 + master spec section 9.2: every management cycle
records an equity snapshot per instance plus one platform-aggregate row.
The dashboard equity-curve endpoints (PR-β) read from this table.

equity = starting_capital + cumulative_realized_pnl + unrealized_pnl

starting_capital comes from configs/global_config.py (account_capital
divided by instance count for per-instance, or full account_capital
for the platform aggregate).

Best-effort persistence -- DB failure logs and returns False; never raises.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .configs import GLOBAL, GOLIATH_INSTANCES
from .instance import GoliathInstance

logger = logging.getLogger(__name__)


def _connect():
    try:
        from database_adapter import get_connection, is_database_available  # type: ignore
    except ImportError:
        return None, False
    if not is_database_available():
        return None, False
    try:
        return get_connection(), True
    except Exception as exc:  # noqa: BLE001
        logger.warning("equity_snapshots DB connect failed: %r", exc)
        return None, False


def _instance_starting_capital(instance_name: str) -> float:
    """Per-instance starting capital = allocation_cap from InstanceConfig."""
    cfg = GOLIATH_INSTANCES.get(instance_name)
    if cfg is None:
        return 0.0
    return float(cfg.allocation_cap)


def _instance_realized_pnl(conn, instance_name: str) -> float:
    """Sum realized_pnl across all closed positions for this instance."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0) FROM goliath_paper_positions "
            "WHERE instance_name = %s AND state = 'CLOSED'",
            (instance_name,),
        )
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    finally:
        cur.close()


def _instance_unrealized_pnl(instance: GoliathInstance) -> float:
    """Mark-to-market across open positions for this instance.

    Uses Position.current_total_pnl which is computed from cached mids.
    Multiplied by contracts (default 1) and the option multiplier (100).
    """
    total = 0.0
    for pos in instance.open_positions:
        contracts = int(getattr(pos, "contracts", 1))
        total += contracts * float(pos.current_total_pnl) * 100.0
    return total


def _record_one(
    conn,
    scope: str,
    instance_name: Optional[str],
    starting_capital: float,
    cumulative_pnl: float,
    unrealized: float,
    open_count: int,
) -> bool:
    """Single snapshot INSERT. Caller manages connection lifecycle."""
    equity = starting_capital + cumulative_pnl + unrealized
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO goliath_equity_snapshots (
                snapshot_at, scope, instance_name,
                starting_capital, cumulative_realized_pnl,
                unrealized_pnl, open_position_count, equity
            ) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)
            """,
            (scope, instance_name, starting_capital, cumulative_pnl,
             unrealized, open_count, equity),
        )
        return True
    finally:
        cur.close()


def write_snapshots(instances: dict[str, GoliathInstance]) -> int:
    """Write per-instance + platform-aggregate equity snapshots.

    Returns count of rows written (0 on DB-unavailable or full failure).
    Never raises.
    """
    conn, ok = _connect()
    if not ok or conn is None:
        return 0

    rows_written = 0
    platform_starting = float(GLOBAL.account_capital)
    platform_realized = 0.0
    platform_unrealized = 0.0
    platform_open_count = 0

    try:
        for name, inst in instances.items():
            try:
                starting = _instance_starting_capital(name)
                realized = _instance_realized_pnl(conn, name)
                unrealized = _instance_unrealized_pnl(inst)
                open_count = inst.open_count

                if _record_one(conn, "INSTANCE", name, starting, realized,
                               unrealized, open_count):
                    rows_written += 1

                platform_realized += realized
                platform_unrealized += unrealized
                platform_open_count += open_count
            except Exception as exc:  # noqa: BLE001
                logger.warning("equity_snapshots %s failed: %r", name, exc)

        # Platform aggregate row.
        try:
            if _record_one(conn, "PLATFORM", None, platform_starting,
                           platform_realized, platform_unrealized,
                           platform_open_count):
                rows_written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("equity_snapshots platform failed: %r", exc)

        conn.commit()
    finally:
        conn.close()

    return rows_written
