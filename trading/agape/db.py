"""
AGAPE Database Layer - PostgreSQL persistence for the ETH bot.

Mirrors FORTRESS V2 db.py pattern: config loading, position management,
logging, and scan activity tracking.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Graceful import of database adapter
get_connection = None
try:
    from database_adapter import get_connection
except ImportError:
    logger.warning("AGAPE DB: database_adapter not available")


def _now_ct() -> datetime:
    return datetime.now(CENTRAL_TZ)


class AgapeDatabase:
    """Database operations for AGAPE bot.

    Tables:
      - agape_positions: Open and closed positions
      - agape_equity_snapshots: Equity curve data points
      - agape_scan_activity: Every scan cycle logged
      - agape_activity_log: General activity/event log
      - autonomous_config: Shared config table (bot_name='AGAPE')
    """

    def __init__(self, bot_name: str = "AGAPE"):
        self.bot_name = bot_name
        self._ensure_tables()

    def _get_conn(self):
        if get_connection is None:
            return None
        return get_connection()

    def _execute(self, sql: str, params=None) -> bool:
        """Execute a raw SQL statement (used for trailing stop updates)."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"AGAPE DB: Execute failed: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        if not conn:
            logger.warning("AGAPE DB: No database connection, skipping table creation")
            return
        try:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(100) UNIQUE NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    contracts INTEGER NOT NULL,
                    entry_price FLOAT NOT NULL,
                    stop_loss FLOAT,
                    take_profit FLOAT,
                    max_risk_usd FLOAT,

                    underlying_at_entry FLOAT,
                    funding_rate_at_entry FLOAT,
                    funding_regime_at_entry VARCHAR(50),
                    ls_ratio_at_entry FLOAT,
                    squeeze_risk_at_entry VARCHAR(20),
                    max_pain_at_entry FLOAT,
                    crypto_gex_at_entry FLOAT,
                    crypto_gex_regime_at_entry VARCHAR(20),

                    oracle_advice VARCHAR(50),
                    oracle_win_probability FLOAT,
                    oracle_confidence FLOAT,
                    oracle_top_factors TEXT,

                    signal_action VARCHAR(20),
                    signal_confidence VARCHAR(20),
                    signal_reasoning TEXT,

                    status VARCHAR(20) DEFAULT 'open',
                    open_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    close_time TIMESTAMP WITH TIME ZONE,
                    close_price FLOAT,
                    close_reason VARCHAR(100),
                    realized_pnl FLOAT,

                    high_water_mark FLOAT DEFAULT 0,
                    oracle_prediction_id INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_equity_snapshots (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    equity FLOAT NOT NULL,
                    unrealized_pnl FLOAT DEFAULT 0,
                    realized_pnl_cumulative FLOAT DEFAULT 0,
                    open_positions INTEGER DEFAULT 0,
                    eth_price FLOAT,
                    funding_rate FLOAT,
                    note VARCHAR(200)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_scan_activity (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    outcome VARCHAR(50) NOT NULL,
                    eth_price FLOAT,
                    funding_rate FLOAT,
                    funding_regime VARCHAR(50),
                    ls_ratio FLOAT,
                    ls_bias VARCHAR(30),
                    squeeze_risk VARCHAR(20),
                    leverage_regime VARCHAR(30),
                    max_pain FLOAT,
                    crypto_gex FLOAT,
                    crypto_gex_regime VARCHAR(20),
                    combined_signal VARCHAR(30),
                    combined_confidence VARCHAR(20),
                    oracle_advice VARCHAR(50),
                    oracle_win_prob FLOAT,
                    signal_action VARCHAR(20),
                    signal_reasoning TEXT,
                    position_id VARCHAR(100),
                    error_message TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_activity_log (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    level VARCHAR(20) DEFAULT 'INFO',
                    action VARCHAR(100),
                    message TEXT,
                    details JSONB
                )
            """)

            # Add trailing columns for no-loss trailing strategy
            for col_sql in [
                "ALTER TABLE agape_positions ADD COLUMN IF NOT EXISTS trailing_active BOOLEAN DEFAULT FALSE",
                "ALTER TABLE agape_positions ADD COLUMN IF NOT EXISTS current_stop FLOAT",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            # Indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agape_positions_status
                ON agape_positions(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agape_positions_open_time
                ON agape_positions(open_time DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agape_equity_snapshots_ts
                ON agape_equity_snapshots(timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agape_scan_activity_ts
                ON agape_scan_activity(timestamp DESC)
            """)

            conn.commit()
            logger.info("AGAPE DB: Tables ensured")
        except Exception as e:
            logger.error(f"AGAPE DB: Table creation failed: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def load_config(self) -> Optional[Dict[str, str]]:
        """Load bot config from autonomous_config table.

        Uses GIDEON-style key/value schema with 'agape_' prefix:
          key='agape_starting_capital', value='5000.0'
        """
        conn = self._get_conn()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            prefix = f"{self.bot_name.lower()}_"
            cursor.execute(
                "SELECT key, value FROM autonomous_config WHERE key LIKE %s",
                (f"{prefix}%",),
            )
            rows = cursor.fetchall()
            if rows:
                return {row[0].replace(prefix, ""): row[1] for row in rows}
            return None
        except Exception as e:
            logger.debug(f"AGAPE DB: Config load failed (table may not exist): {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_starting_capital(self) -> float:
        """Get starting capital from config or default."""
        config = self.load_config()
        if config and "starting_capital" in config:
            return float(config["starting_capital"])
        return 5000.0

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def save_position(self, pos) -> bool:
        """Save a new position to the database."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_positions (
                    position_id, side, contracts, entry_price,
                    stop_loss, take_profit, max_risk_usd,
                    underlying_at_entry, funding_rate_at_entry,
                    funding_regime_at_entry, ls_ratio_at_entry,
                    squeeze_risk_at_entry, max_pain_at_entry,
                    crypto_gex_at_entry, crypto_gex_regime_at_entry,
                    oracle_advice, oracle_win_probability, oracle_confidence,
                    oracle_top_factors,
                    signal_action, signal_confidence, signal_reasoning,
                    status, open_time, high_water_mark
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
            """, (
                pos.position_id, pos.side.value, pos.contracts, pos.entry_price,
                pos.stop_loss, pos.take_profit, pos.max_risk_usd,
                pos.underlying_at_entry, pos.funding_rate_at_entry,
                pos.funding_regime_at_entry, pos.ls_ratio_at_entry,
                pos.squeeze_risk_at_entry, pos.max_pain_at_entry,
                pos.crypto_gex_at_entry, pos.crypto_gex_regime_at_entry,
                pos.oracle_advice, pos.oracle_win_probability, pos.oracle_confidence,
                json.dumps(pos.oracle_top_factors),
                pos.signal_action, pos.signal_confidence, pos.signal_reasoning,
                pos.status.value, pos.open_time or _now_ct(),
                pos.entry_price,  # high_water_mark starts at entry price, NOT 0
            ))
            conn.commit()
            logger.info(f"AGAPE DB: Saved position {pos.position_id}")
            return True
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to save position: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def close_position(
        self,
        position_id: str,
        close_price: float,
        realized_pnl: float,
        reason: str,
    ) -> bool:
        """Close a position with P&L."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agape_positions
                SET status = 'closed',
                    close_time = NOW(),
                    close_price = %s,
                    realized_pnl = %s,
                    close_reason = %s
                WHERE position_id = %s AND status = 'open'
            """, (close_price, realized_pnl, reason, position_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to close position {position_id}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def expire_position(
        self, position_id: str, realized_pnl: float, close_price: float
    ) -> bool:
        """Expire a position (max hold time reached)."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agape_positions
                SET status = 'expired',
                    close_time = NOW(),
                    close_price = %s,
                    realized_pnl = %s,
                    close_reason = 'MAX_HOLD_TIME'
                WHERE position_id = %s AND status = 'open'
            """, (close_price, realized_pnl, position_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to expire position: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def get_open_positions(self) -> List[Dict]:
        """Get all open positions."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT position_id, side, contracts, entry_price,
                       stop_loss, take_profit, max_risk_usd,
                       underlying_at_entry, funding_rate_at_entry,
                       funding_regime_at_entry, ls_ratio_at_entry,
                       squeeze_risk_at_entry, max_pain_at_entry,
                       crypto_gex_at_entry, crypto_gex_regime_at_entry,
                       oracle_advice, oracle_win_probability, oracle_confidence,
                       oracle_top_factors,
                       signal_action, signal_confidence, signal_reasoning,
                       status, open_time, high_water_mark,
                       COALESCE(trailing_active, FALSE), current_stop
                FROM agape_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            """)
            rows = cursor.fetchall()
            positions = []
            for row in rows:
                positions.append({
                    "position_id": row[0],
                    "side": row[1],
                    "contracts": row[2],
                    "entry_price": float(row[3]),
                    "stop_loss": float(row[4]) if row[4] else None,
                    "take_profit": float(row[5]) if row[5] else None,
                    "max_risk_usd": float(row[6]) if row[6] else None,
                    "underlying_at_entry": float(row[7]) if row[7] else None,
                    "funding_rate_at_entry": float(row[8]) if row[8] else None,
                    "funding_regime_at_entry": row[9],
                    "ls_ratio_at_entry": float(row[10]) if row[10] else None,
                    "squeeze_risk_at_entry": row[11],
                    "max_pain_at_entry": float(row[12]) if row[12] else None,
                    "crypto_gex_at_entry": float(row[13]) if row[13] else None,
                    "crypto_gex_regime_at_entry": row[14],
                    "oracle_advice": row[15],
                    "oracle_win_probability": float(row[16]) if row[16] else None,
                    "oracle_confidence": float(row[17]) if row[17] else None,
                    "oracle_top_factors": json.loads(row[18]) if row[18] else [],
                    "signal_action": row[19],
                    "signal_confidence": row[20],
                    "signal_reasoning": row[21],
                    "status": row[22],
                    "open_time": row[23].isoformat() if row[23] else None,
                    "high_water_mark": float(row[24]) if row[24] and float(row[24]) > 0 else float(row[3]),  # Fall back to entry_price if 0/NULL
                    "trailing_active": bool(row[25]),
                    "current_stop": float(row[26]) if row[26] else None,
                })
            return positions
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to get open positions: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_closed_trades(self, limit: int = 100) -> List[Dict]:
        """Get closed/expired trades for equity curve and performance."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT position_id, side, contracts, entry_price,
                       close_price, realized_pnl, close_reason,
                       open_time, close_time,
                       funding_regime_at_entry, squeeze_risk_at_entry,
                       oracle_advice, oracle_win_probability,
                       signal_action, signal_confidence
                FROM agape_positions
                WHERE status IN ('closed', 'expired', 'stopped')
                ORDER BY close_time DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            trades = []
            for row in rows:
                trades.append({
                    "position_id": row[0],
                    "side": row[1],
                    "contracts": row[2],
                    "entry_price": float(row[3]),
                    "close_price": float(row[4]) if row[4] else None,
                    "realized_pnl": float(row[5]) if row[5] else 0,
                    "close_reason": row[6],
                    "open_time": row[7].isoformat() if row[7] else None,
                    "close_time": row[8].isoformat() if row[8] else None,
                    "funding_regime_at_entry": row[9],
                    "squeeze_risk_at_entry": row[10],
                    "oracle_advice": row[11],
                    "oracle_win_probability": float(row[12]) if row[12] else None,
                    "signal_action": row[13],
                    "signal_confidence": row[14],
                })
            return trades
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to get closed trades: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_position_count(self) -> int:
        """Quick count of open positions."""
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM agape_positions WHERE status = 'open'"
            )
            return cursor.fetchone()[0]
        except Exception:
            return 0
        finally:
            cursor.close()
            conn.close()

    def has_traded_recently(self, cooldown_minutes: int = 5) -> bool:
        """Check if we opened a new position within cooldown period."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM agape_positions
                WHERE open_time > NOW() - INTERVAL '%s minutes'
            """, (cooldown_minutes,))
            return cursor.fetchone()[0] > 0
        except Exception:
            return False
        finally:
            cursor.close()
            conn.close()

    def update_high_water_mark(self, position_id: str, hwm: float) -> bool:
        """Update trailing stop high water mark."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agape_positions
                SET high_water_mark = %s
                WHERE position_id = %s AND status = 'open'
            """, (hwm, position_id))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Equity Snapshots
    # ------------------------------------------------------------------

    def save_equity_snapshot(
        self,
        equity: float,
        unrealized_pnl: float,
        realized_cumulative: float,
        open_positions: int,
        eth_price: Optional[float] = None,
        funding_rate: Optional[float] = None,
    ) -> bool:
        """Save an equity snapshot for intraday curve."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_equity_snapshots
                (equity, unrealized_pnl, realized_pnl_cumulative,
                 open_positions, eth_price, funding_rate)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (equity, unrealized_pnl, realized_cumulative,
                  open_positions, eth_price, funding_rate))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to save equity snapshot: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Scan Activity
    # ------------------------------------------------------------------

    def log_scan(self, scan_data: Dict) -> bool:
        """Log a scan cycle for full visibility."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_scan_activity (
                    outcome, eth_price, funding_rate, funding_regime,
                    ls_ratio, ls_bias, squeeze_risk, leverage_regime,
                    max_pain, crypto_gex, crypto_gex_regime,
                    combined_signal, combined_confidence,
                    oracle_advice, oracle_win_prob,
                    signal_action, signal_reasoning,
                    position_id, error_message
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                scan_data.get("outcome", "UNKNOWN"),
                scan_data.get("eth_price"),
                scan_data.get("funding_rate"),
                scan_data.get("funding_regime"),
                scan_data.get("ls_ratio"),
                scan_data.get("ls_bias"),
                scan_data.get("squeeze_risk"),
                scan_data.get("leverage_regime"),
                scan_data.get("max_pain"),
                scan_data.get("crypto_gex"),
                scan_data.get("crypto_gex_regime"),
                scan_data.get("combined_signal"),
                scan_data.get("combined_confidence"),
                scan_data.get("oracle_advice"),
                scan_data.get("oracle_win_prob"),
                scan_data.get("signal_action"),
                scan_data.get("signal_reasoning"),
                scan_data.get("position_id"),
                scan_data.get("error_message"),
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to log scan: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Activity Log
    # ------------------------------------------------------------------

    def log(self, level: str, action: str, message: str, details: Optional[Dict] = None):
        """Log an activity event."""
        conn = self._get_conn()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_activity_log (level, action, message, details)
                VALUES (%s, %s, %s, %s)
            """, (level, action, message, json.dumps(details) if details else None))
            conn.commit()
        except Exception as e:
            logger.error(f"AGAPE DB: Log failed: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def get_logs(self, limit: int = 50) -> List[Dict]:
        """Get recent activity logs."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, level, action, message, details
                FROM agape_activity_log
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "level": row[1],
                    "action": row[2],
                    "message": row[3],
                    "details": row[4],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to get logs: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_scan_activity(self, limit: int = 50) -> List[Dict]:
        """Get recent scan activity."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, outcome, eth_price, funding_rate,
                       funding_regime, ls_ratio, squeeze_risk,
                       combined_signal, combined_confidence,
                       oracle_advice, oracle_win_prob,
                       signal_action, signal_reasoning, position_id
                FROM agape_scan_activity
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "outcome": row[1],
                    "eth_price": float(row[2]) if row[2] else None,
                    "funding_rate": float(row[3]) if row[3] else None,
                    "funding_regime": row[4],
                    "ls_ratio": float(row[5]) if row[5] else None,
                    "squeeze_risk": row[6],
                    "combined_signal": row[7],
                    "combined_confidence": row[8],
                    "oracle_advice": row[9],
                    "oracle_win_prob": float(row[10]) if row[10] else None,
                    "signal_action": row[11],
                    "signal_reasoning": row[12],
                    "position_id": row[13],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"AGAPE DB: Failed to get scan activity: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
