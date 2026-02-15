"""
AGAPE-BTC Database Layer - PostgreSQL persistence for the BTC bot.

Mirrors AGAPE (ETH) db.py pattern with BTC-specific table names.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

get_connection = None
try:
    from database_adapter import get_connection
except ImportError:
    logger.warning("AGAPE-BTC DB: database_adapter not available")


def _now_ct() -> datetime:
    return datetime.now(CENTRAL_TZ)


class AgapeBtcDatabase:
    """Database operations for AGAPE-BTC bot.

    Tables:
      - agape_btc_positions: Open and closed positions
      - agape_btc_equity_snapshots: Equity curve data points
      - agape_btc_scan_activity: Every scan cycle logged
      - agape_btc_activity_log: General activity/event log
      - autonomous_config: Shared config table (bot_name='AGAPE_BTC')
    """

    def __init__(self, bot_name: str = "AGAPE_BTC"):
        self.bot_name = bot_name
        self._ensure_tables()

    def _get_conn(self):
        if get_connection is None:
            return None
        return get_connection()

    def _execute(self, sql: str, params=None) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Execute failed: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def _ensure_tables(self):
        conn = self._get_conn()
        if not conn:
            logger.warning("AGAPE-BTC DB: No database connection, skipping table creation")
            return
        try:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_btc_positions (
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
                CREATE TABLE IF NOT EXISTS agape_btc_equity_snapshots (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    equity FLOAT NOT NULL,
                    unrealized_pnl FLOAT DEFAULT 0,
                    realized_pnl_cumulative FLOAT DEFAULT 0,
                    open_positions INTEGER DEFAULT 0,
                    btc_price FLOAT,
                    funding_rate FLOAT,
                    note VARCHAR(200)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_btc_scan_activity (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    outcome VARCHAR(50) NOT NULL,
                    btc_price FLOAT,
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
                CREATE TABLE IF NOT EXISTS agape_btc_activity_log (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    level VARCHAR(20) DEFAULT 'INFO',
                    action VARCHAR(100),
                    message TEXT,
                    details JSONB
                )
            """)

            # Add trailing + margin columns
            for col_sql in [
                "ALTER TABLE agape_btc_positions ADD COLUMN IF NOT EXISTS trailing_active BOOLEAN DEFAULT FALSE",
                "ALTER TABLE agape_btc_positions ADD COLUMN IF NOT EXISTS current_stop FLOAT",
                "ALTER TABLE agape_btc_positions ADD COLUMN IF NOT EXISTS margin_required FLOAT DEFAULT 0",
                "ALTER TABLE agape_btc_positions ADD COLUMN IF NOT EXISTS liquidation_price FLOAT",
                "ALTER TABLE agape_btc_positions ADD COLUMN IF NOT EXISTS leverage_at_entry FLOAT DEFAULT 0",
                "ALTER TABLE agape_btc_equity_snapshots ADD COLUMN IF NOT EXISTS margin_used FLOAT DEFAULT 0",
                "ALTER TABLE agape_btc_equity_snapshots ADD COLUMN IF NOT EXISTS margin_available FLOAT DEFAULT 0",
                "ALTER TABLE agape_btc_equity_snapshots ADD COLUMN IF NOT EXISTS margin_ratio FLOAT",
            ]:
                try:
                    cursor.execute(col_sql)
                except Exception:
                    pass

            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_btc_positions_status ON agape_btc_positions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_btc_positions_open_time ON agape_btc_positions(open_time DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_btc_equity_snapshots_ts ON agape_btc_equity_snapshots(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_btc_scan_activity_ts ON agape_btc_scan_activity(timestamp DESC)")

            conn.commit()
            logger.info("AGAPE-BTC DB: Tables ensured")
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Table creation failed: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def load_config(self) -> Optional[Dict[str, str]]:
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
            logger.debug(f"AGAPE-BTC DB: Config load failed: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_starting_capital(self) -> float:
        config = self.load_config()
        if config and "starting_capital" in config:
            return float(config["starting_capital"])
        return 5000.0

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def save_position(self, pos) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_btc_positions (
                    position_id, side, contracts, entry_price,
                    stop_loss, take_profit, max_risk_usd,
                    underlying_at_entry, funding_rate_at_entry,
                    funding_regime_at_entry, ls_ratio_at_entry,
                    squeeze_risk_at_entry, max_pain_at_entry,
                    crypto_gex_at_entry, crypto_gex_regime_at_entry,
                    oracle_advice, oracle_win_probability, oracle_confidence,
                    oracle_top_factors,
                    signal_action, signal_confidence, signal_reasoning,
                    status, open_time, high_water_mark,
                    margin_required, liquidation_price, leverage_at_entry
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
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
                pos.entry_price,
                getattr(pos, 'margin_required', 0),
                getattr(pos, 'liquidation_price', None),
                getattr(pos, 'leverage_at_entry', 0),
            ))
            conn.commit()
            logger.info(f"AGAPE-BTC DB: Saved position {pos.position_id}")
            return True
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Failed to save position: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def close_position(self, position_id: str, close_price: float, realized_pnl: float, reason: str) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agape_btc_positions
                SET status = 'closed', close_time = NOW(), close_price = %s,
                    realized_pnl = %s, close_reason = %s
                WHERE position_id = %s AND status = 'open'
            """, (close_price, realized_pnl, reason, position_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Failed to close position {position_id}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def expire_position(self, position_id: str, realized_pnl: float, close_price: float) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agape_btc_positions
                SET status = 'expired', close_time = NOW(), close_price = %s,
                    realized_pnl = %s, close_reason = 'MAX_HOLD_TIME'
                WHERE position_id = %s AND status = 'open'
            """, (close_price, realized_pnl, position_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Failed to expire position: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def get_open_positions(self) -> List[Dict]:
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
                       COALESCE(trailing_active, FALSE), current_stop,
                       COALESCE(margin_required, 0), liquidation_price,
                       COALESCE(leverage_at_entry, 0)
                FROM agape_btc_positions
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
                    "high_water_mark": float(row[24]) if row[24] and float(row[24]) > 0 else float(row[3]),
                    "trailing_active": bool(row[25]),
                    "current_stop": float(row[26]) if row[26] else None,
                    "margin_required": float(row[27]) if row[27] else 0,
                    "liquidation_price": float(row[28]) if row[28] else None,
                    "leverage_at_entry": float(row[29]) if row[29] else 0,
                })
            return positions
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Failed to get open positions: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_closed_trades(self, limit: int = 100) -> List[Dict]:
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
                FROM agape_btc_positions
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
            logger.error(f"AGAPE-BTC DB: Failed to get closed trades: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_position_count(self) -> int:
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM agape_btc_positions WHERE status = 'open'")
            return cursor.fetchone()[0]
        except Exception:
            return 0
        finally:
            cursor.close()
            conn.close()

    def update_high_water_mark(self, position_id: str, hwm: float) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agape_btc_positions SET high_water_mark = %s
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

    def save_equity_snapshot(self, equity: float, unrealized_pnl: float,
                            realized_cumulative: float, open_positions: int,
                            btc_price: Optional[float] = None,
                            funding_rate: Optional[float] = None,
                            margin_used: float = 0, margin_available: float = 0,
                            margin_ratio: Optional[float] = None) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_btc_equity_snapshots
                (equity, unrealized_pnl, realized_pnl_cumulative,
                 open_positions, btc_price, funding_rate,
                 margin_used, margin_available, margin_ratio)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (equity, unrealized_pnl, realized_cumulative,
                  open_positions, btc_price, funding_rate,
                  margin_used, margin_available, margin_ratio))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Failed to save equity snapshot: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Scan Activity
    # ------------------------------------------------------------------

    def log_scan(self, scan_data: Dict) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_btc_scan_activity (
                    outcome, btc_price, funding_rate, funding_regime,
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
                scan_data.get("btc_price"),
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
            logger.error(f"AGAPE-BTC DB: Failed to log scan: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Activity Log
    # ------------------------------------------------------------------

    def log(self, level: str, action: str, message: str, details: Optional[Dict] = None):
        conn = self._get_conn()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_btc_activity_log (level, action, message, details)
                VALUES (%s, %s, %s, %s)
            """, (level, action, message, json.dumps(details) if details else None))
            conn.commit()
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Log failed: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def get_logs(self, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, level, action, message, details
                FROM agape_btc_activity_log ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "level": row[1], "action": row[2],
                    "message": row[3], "details": row[4],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"AGAPE-BTC DB: Failed to get logs: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_scan_activity(self, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, outcome, btc_price, funding_rate,
                       funding_regime, ls_ratio, squeeze_risk,
                       combined_signal, combined_confidence,
                       oracle_advice, oracle_win_prob,
                       signal_action, signal_reasoning, position_id
                FROM agape_btc_scan_activity ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "outcome": row[1],
                    "btc_price": float(row[2]) if row[2] else None,
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
            logger.error(f"AGAPE-BTC DB: Failed to get scan activity: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
