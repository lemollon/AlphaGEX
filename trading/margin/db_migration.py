"""
Database migration for margin management tables.

Creates the following tables:
  - margin_snapshots: Historical account-level margin metrics
  - margin_position_details: Per-position margin details
  - margin_alerts: Margin alert history
  - margin_bot_config: Per-bot margin configuration overrides

Safe to run multiple times (uses IF NOT EXISTS).
"""

import logging

logger = logging.getLogger(__name__)


def create_margin_tables(conn=None):
    """Create all margin management tables.

    Args:
        conn: Optional database connection. If None, creates one.

    Safe to run multiple times - uses CREATE TABLE IF NOT EXISTS.
    """
    close_conn = False
    if conn is None:
        try:
            from database_adapter import get_connection
            conn = get_connection()
            close_conn = True
        except Exception as e:
            logger.error(f"Cannot create margin tables - no database connection: {e}")
            return False

    try:
        cursor = conn.cursor()

        # 1. Account-level margin snapshots (time-series)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS margin_snapshots (
                id BIGSERIAL PRIMARY KEY,
                bot_name VARCHAR(50) NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                account_equity NUMERIC(18, 2),
                margin_used NUMERIC(18, 2),
                margin_available NUMERIC(18, 2),
                margin_usage_pct NUMERIC(8, 2),
                margin_ratio NUMERIC(12, 4),
                effective_leverage NUMERIC(12, 4),
                total_notional NUMERIC(18, 2),
                total_unrealized_pnl NUMERIC(18, 2),
                position_count INTEGER DEFAULT 0,
                health_status VARCHAR(20),
                market_type VARCHAR(30),
                total_funding_cost_daily NUMERIC(12, 4)
            )
        """)

        # Index for efficient querying by bot and time
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_margin_snapshots_bot_time
            ON margin_snapshots (bot_name, timestamp DESC)
        """)

        # Index for health status monitoring
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_margin_snapshots_health
            ON margin_snapshots (health_status, timestamp DESC)
        """)

        # 2. Per-position margin details
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS margin_position_details (
                id BIGSERIAL PRIMARY KEY,
                bot_name VARCHAR(50) NOT NULL,
                position_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(30),
                side VARCHAR(10),
                entry_price NUMERIC(18, 8),
                current_price NUMERIC(18, 8),
                quantity NUMERIC(18, 8),
                notional_value NUMERIC(18, 2),
                margin_required NUMERIC(18, 2),
                liquidation_price NUMERIC(18, 8),
                distance_to_liq_pct NUMERIC(10, 4),
                unrealized_pnl NUMERIC(18, 2),
                funding_rate NUMERIC(12, 8),
                funding_cost_daily NUMERIC(12, 4),
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_margin_pos_bot_time
            ON margin_position_details (bot_name, timestamp DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_margin_pos_position
            ON margin_position_details (position_id, timestamp DESC)
        """)

        # 3. Margin alerts history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS margin_alerts (
                id BIGSERIAL PRIMARY KEY,
                bot_name VARCHAR(50) NOT NULL,
                alert_level VARCHAR(20) NOT NULL,
                message TEXT NOT NULL,
                details JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                acknowledged BOOLEAN DEFAULT FALSE,
                acknowledged_at TIMESTAMP WITH TIME ZONE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_margin_alerts_bot_time
            ON margin_alerts (bot_name, created_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_margin_alerts_level
            ON margin_alerts (alert_level, created_at DESC)
        """)

        # 4. Per-bot margin configuration overrides
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS margin_bot_config (
                id SERIAL PRIMARY KEY,
                bot_name VARCHAR(50) NOT NULL,
                config_key VARCHAR(100) NOT NULL,
                config_value VARCHAR(500) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(bot_name, config_key)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_margin_config_bot
            ON margin_bot_config (bot_name, is_active)
        """)

        conn.commit()
        cursor.close()
        logger.info("Margin management tables created successfully")

        if close_conn:
            conn.close()

        return True

    except Exception as e:
        logger.error(f"Error creating margin tables: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass
        return False


def cleanup_old_snapshots(days_to_keep: int = 30, conn=None):
    """Remove margin snapshots older than the specified number of days.

    Keeps the database from growing unboundedly.
    Call this from a scheduled daily cleanup job.
    """
    close_conn = False
    if conn is None:
        try:
            from database_adapter import get_connection
            conn = get_connection()
            close_conn = True
        except Exception:
            return 0

    try:
        cursor = conn.cursor()
        cutoff = f"NOW() - INTERVAL '{days_to_keep} days'"

        cursor.execute(f"""
            DELETE FROM margin_snapshots
            WHERE timestamp < {cutoff}
        """)
        snapshot_count = cursor.rowcount

        cursor.execute(f"""
            DELETE FROM margin_position_details
            WHERE timestamp < {cutoff}
        """)
        detail_count = cursor.rowcount

        conn.commit()
        cursor.close()

        if close_conn:
            conn.close()

        total = snapshot_count + detail_count
        if total > 0:
            logger.info(f"Cleaned up {total} old margin records ({snapshot_count} snapshots, {detail_count} details)")
        return total

    except Exception as e:
        logger.error(f"Error cleaning up margin snapshots: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass
        return 0
