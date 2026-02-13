"""
AGAPE-SPOT Database Layer - PostgreSQL persistence for the 24/7 Coinbase spot bot.

Multi-ticker, long-only support. Trades ETH-USD, XRP-USD, SHIB-USD, DOGE-USD.
Uses separate tables from AGAPE (futures): agape_spot_positions, agape_spot_equity_snapshots, etc.
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
    logger.warning("AGAPE-SPOT DB: database_adapter not available")


def _now_ct() -> datetime:
    return datetime.now(CENTRAL_TZ)


class AgapeSpotDatabase:
    """Database operations for AGAPE-SPOT bot (multi-ticker, long-only).

    Tables:
      - agape_spot_positions: Open and closed positions (ticker-partitioned)
      - agape_spot_equity_snapshots: Equity curve data points per ticker
      - agape_spot_scan_activity: Every scan cycle logged per ticker
      - agape_spot_activity_log: General activity/event log with ticker
      - autonomous_config: Shared config table (prefix='agape_spot_')
    """

    def __init__(self, bot_name: str = "AGAPE-SPOT"):
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
            logger.error(f"AGAPE-SPOT DB: Execute failed: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Table creation & migration
    # ------------------------------------------------------------------

    def _ensure_tables(self):
        conn = self._get_conn()
        if not conn:
            logger.warning("AGAPE-SPOT DB: No database connection, skipping table creation")
            return
        try:
            cursor = conn.cursor()

            # ----- agape_spot_positions -----
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_spot_positions (
                    id SERIAL PRIMARY KEY,
                    position_id VARCHAR(100) UNIQUE NOT NULL,
                    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
                    side VARCHAR(10) NOT NULL DEFAULT 'long',
                    quantity FLOAT NOT NULL,
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
                    trailing_active BOOLEAN DEFAULT FALSE,
                    current_stop FLOAT,
                    oracle_prediction_id INTEGER,
                    account_label VARCHAR(50) DEFAULT 'default',

                    -- Coinbase execution tracking
                    coinbase_order_id VARCHAR(100),
                    coinbase_sell_order_id VARCHAR(100),
                    entry_slippage_pct FLOAT,
                    exit_slippage_pct FLOAT,
                    entry_fee_usd FLOAT,
                    exit_fee_usd FLOAT,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # ----- agape_spot_equity_snapshots -----
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_spot_equity_snapshots (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
                    equity FLOAT NOT NULL,
                    unrealized_pnl FLOAT DEFAULT 0,
                    realized_pnl_cumulative FLOAT DEFAULT 0,
                    open_positions INTEGER DEFAULT 0,
                    eth_price FLOAT,
                    funding_rate FLOAT,
                    note VARCHAR(200)
                )
            """)

            # ----- agape_spot_scan_activity -----
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_spot_scan_activity (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
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

            # ----- agape_spot_activity_log -----
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_spot_activity_log (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ticker VARCHAR(20),
                    level VARCHAR(20) DEFAULT 'INFO',
                    action VARCHAR(100),
                    message TEXT,
                    details JSONB
                )
            """)

            # ----- agape_spot_win_tracker -----
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agape_spot_win_tracker (
                    id SERIAL PRIMARY KEY,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD',
                    alpha DECIMAL(10, 4) DEFAULT 1.0,
                    beta DECIMAL(10, 4) DEFAULT 1.0,
                    total_trades INTEGER DEFAULT 0,
                    positive_funding_wins INTEGER DEFAULT 0,
                    positive_funding_losses INTEGER DEFAULT 0,
                    negative_funding_wins INTEGER DEFAULT 0,
                    negative_funding_losses INTEGER DEFAULT 0,
                    neutral_funding_wins INTEGER DEFAULT 0,
                    neutral_funding_losses INTEGER DEFAULT 0
                )
            """)

            # ==========================================================
            # MIGRATIONS for existing tables
            # ==========================================================

            # --- positions: add ticker column ---
            cursor.execute("""
                ALTER TABLE agape_spot_positions
                ADD COLUMN IF NOT EXISTS ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD'
            """)

            # --- positions: rename eth_quantity -> quantity ---
            # Uses PL/pgSQL exception handler so failure doesn't rollback
            # the entire Python-level transaction (which would undo all
            # earlier migrations in this block).
            cursor.execute("""
                DO $$
                BEGIN
                    ALTER TABLE agape_spot_positions
                    RENAME COLUMN eth_quantity TO quantity;
                EXCEPTION WHEN undefined_column THEN NULL;
                END $$;
            """)

            # --- positions: add account_label column ---
            cursor.execute("""
                ALTER TABLE agape_spot_positions
                ADD COLUMN IF NOT EXISTS account_label VARCHAR(50) DEFAULT 'default'
            """)

            # --- equity_snapshots: add ticker column ---
            cursor.execute("""
                ALTER TABLE agape_spot_equity_snapshots
                ADD COLUMN IF NOT EXISTS ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD'
            """)

            # --- scan_activity: add ticker column ---
            cursor.execute("""
                ALTER TABLE agape_spot_scan_activity
                ADD COLUMN IF NOT EXISTS ticker VARCHAR(20) NOT NULL DEFAULT 'ETH-USD'
            """)

            # --- activity_log: add ticker column ---
            cursor.execute("""
                ALTER TABLE agape_spot_activity_log
                ADD COLUMN IF NOT EXISTS ticker VARCHAR(20)
            """)

            # --- positions: Coinbase execution tracking columns ---
            for col, typedef in [
                ("coinbase_order_id", "VARCHAR(100)"),
                ("coinbase_sell_order_id", "VARCHAR(100)"),
                ("entry_slippage_pct", "FLOAT"),
                ("exit_slippage_pct", "FLOAT"),
                ("entry_fee_usd", "FLOAT"),
                ("exit_fee_usd", "FLOAT"),
            ]:
                cursor.execute(f"""
                    ALTER TABLE agape_spot_positions
                    ADD COLUMN IF NOT EXISTS {col} {typedef}
                """)

            # ==========================================================
            # Indexes
            # ==========================================================
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_positions_status ON agape_spot_positions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_positions_open_time ON agape_spot_positions(open_time DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_positions_ticker ON agape_spot_positions(ticker)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_positions_ticker_status ON agape_spot_positions(ticker, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_equity_snapshots_ts ON agape_spot_equity_snapshots(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_equity_snapshots_ticker ON agape_spot_equity_snapshots(ticker)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_equity_snapshots_ticker_ts ON agape_spot_equity_snapshots(ticker, timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_scan_activity_ts ON agape_spot_scan_activity(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_scan_activity_ticker ON agape_spot_scan_activity(ticker)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_activity_log_ticker ON agape_spot_activity_log(ticker)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_agape_spot_win_tracker_ticker ON agape_spot_win_tracker(ticker)")

            conn.commit()
            logger.info("AGAPE-SPOT DB: Tables ensured (multi-ticker)")
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Table creation failed: {e}")
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
            prefix = "agape_spot_"
            cursor.execute(
                "SELECT key, value FROM autonomous_config WHERE key LIKE %s",
                (f"{prefix}%",),
            )
            rows = cursor.fetchall()
            if rows:
                return {row[0].replace(prefix, ""): row[1] for row in rows}
            return None
        except Exception as e:
            logger.debug(f"AGAPE-SPOT DB: Config load failed: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_starting_capital(self, ticker: str = "ETH-USD") -> float:
        """Get starting capital for a specific ticker from SPOT_TICKERS config."""
        from trading.agape_spot.models import SPOT_TICKERS
        return SPOT_TICKERS.get(ticker, {}).get("starting_capital", 1000.0)

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def save_position(self, pos) -> bool:
        """Save a new position. pos must have .ticker and .quantity fields."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()

            # Determine ticker: use pos.ticker if available, fall back to 'ETH-USD'
            ticker = getattr(pos, "ticker", "ETH-USD")

            # Determine quantity: prefer .quantity, fall back to .eth_quantity for compat
            quantity = getattr(pos, "quantity", None)
            if quantity is None:
                quantity = getattr(pos, "eth_quantity", 0.0)

            # side: always 'long' for spot, but read from pos if available
            side = "long"
            if hasattr(pos, "side"):
                side_val = pos.side
                side = side_val.value if hasattr(side_val, "value") else str(side_val)

            account_label = getattr(pos, "account_label", "default")

            coinbase_order_id = getattr(pos, "coinbase_order_id", None)
            entry_slippage_pct = getattr(pos, "entry_slippage_pct", None)
            entry_fee_usd = getattr(pos, "entry_fee_usd", None)

            cursor.execute("""
                INSERT INTO agape_spot_positions (
                    position_id, ticker, side, quantity, entry_price,
                    stop_loss, take_profit, max_risk_usd,
                    underlying_at_entry, funding_rate_at_entry,
                    funding_regime_at_entry, ls_ratio_at_entry,
                    squeeze_risk_at_entry, max_pain_at_entry,
                    crypto_gex_at_entry, crypto_gex_regime_at_entry,
                    oracle_advice, oracle_win_probability, oracle_confidence,
                    oracle_top_factors,
                    signal_action, signal_confidence, signal_reasoning,
                    status, open_time, high_water_mark,
                    account_label,
                    coinbase_order_id, entry_slippage_pct, entry_fee_usd
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                pos.position_id, ticker, side, quantity, pos.entry_price,
                pos.stop_loss, pos.take_profit, pos.max_risk_usd,
                pos.underlying_at_entry, pos.funding_rate_at_entry,
                pos.funding_regime_at_entry, pos.ls_ratio_at_entry,
                pos.squeeze_risk_at_entry, pos.max_pain_at_entry,
                pos.crypto_gex_at_entry, pos.crypto_gex_regime_at_entry,
                pos.oracle_advice, pos.oracle_win_probability, pos.oracle_confidence,
                json.dumps(pos.oracle_top_factors),
                pos.signal_action, pos.signal_confidence, pos.signal_reasoning,
                pos.status.value if hasattr(pos.status, "value") else pos.status,
                pos.open_time or _now_ct(),
                pos.entry_price,
                account_label,
                coinbase_order_id, entry_slippage_pct, entry_fee_usd,
            ))
            conn.commit()
            logger.info(f"AGAPE-SPOT DB: Saved position {pos.position_id} ({ticker})")
            return True
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to save position: {e}")
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
        coinbase_sell_order_id: str = None,
        exit_slippage_pct: float = None,
        exit_fee_usd: float = None,
    ) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agape_spot_positions
                SET status = 'closed', close_time = NOW(),
                    close_price = %s, realized_pnl = %s, close_reason = %s,
                    coinbase_sell_order_id = COALESCE(%s, coinbase_sell_order_id),
                    exit_slippage_pct = COALESCE(%s, exit_slippage_pct),
                    exit_fee_usd = COALESCE(%s, exit_fee_usd)
                WHERE position_id = %s AND status = 'open'
            """, (
                close_price, realized_pnl, reason,
                coinbase_sell_order_id, exit_slippage_pct, exit_fee_usd,
                position_id,
            ))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to close position {position_id}: {e}")
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
                UPDATE agape_spot_positions
                SET status = 'expired', close_time = NOW(),
                    close_price = %s, realized_pnl = %s, close_reason = 'MAX_HOLD_TIME'
                WHERE position_id = %s AND status = 'open'
            """, (close_price, realized_pnl, position_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to expire position: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def get_open_positions(self, ticker: Optional[str] = None) -> List[Dict]:
        """Get open positions, optionally filtered by ticker. Returns all tickers if None."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()

            base_sql = """
                SELECT position_id, ticker, side, quantity, entry_price,
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
                       COALESCE(account_label, 'default')
                FROM agape_spot_positions
                WHERE status = 'open'
            """
            if ticker is not None:
                base_sql += " AND ticker = %s"
                base_sql += " ORDER BY open_time DESC"
                cursor.execute(base_sql, (ticker,))
            else:
                base_sql += " ORDER BY open_time DESC"
                cursor.execute(base_sql)

            rows = cursor.fetchall()
            positions = []
            for row in rows:
                positions.append({
                    "position_id": row[0],
                    "ticker": row[1],
                    "side": row[2],
                    "quantity": float(row[3]),
                    "entry_price": float(row[4]),
                    "stop_loss": float(row[5]) if row[5] else None,
                    "take_profit": float(row[6]) if row[6] else None,
                    "max_risk_usd": float(row[7]) if row[7] else None,
                    "underlying_at_entry": float(row[8]) if row[8] else None,
                    "funding_rate_at_entry": float(row[9]) if row[9] else None,
                    "funding_regime_at_entry": row[10],
                    "ls_ratio_at_entry": float(row[11]) if row[11] else None,
                    "squeeze_risk_at_entry": row[12],
                    "max_pain_at_entry": float(row[13]) if row[13] else None,
                    "crypto_gex_at_entry": float(row[14]) if row[14] else None,
                    "crypto_gex_regime_at_entry": row[15],
                    "oracle_advice": row[16],
                    "oracle_win_probability": float(row[17]) if row[17] else None,
                    "oracle_confidence": float(row[18]) if row[18] else None,
                    "oracle_top_factors": json.loads(row[19]) if row[19] else [],
                    "signal_action": row[20],
                    "signal_confidence": row[21],
                    "signal_reasoning": row[22],
                    "status": row[23],
                    "open_time": row[24].isoformat() if row[24] else None,
                    "high_water_mark": float(row[25]) if row[25] and float(row[25]) > 0 else float(row[4]),
                    "trailing_active": bool(row[26]),
                    "current_stop": float(row[27]) if row[27] else None,
                    "account_label": row[28] if len(row) > 28 else "default",
                })
            return positions
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to get open positions: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_closed_trades(self, ticker: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get closed trades, optionally filtered by ticker. Returns all tickers if None."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()

            base_sql = """
                SELECT position_id, ticker, side, quantity, entry_price,
                       close_price, realized_pnl, close_reason,
                       open_time, close_time,
                       funding_regime_at_entry, squeeze_risk_at_entry,
                       oracle_advice, oracle_win_probability,
                       signal_action, signal_confidence,
                       COALESCE(account_label, 'default')
                FROM agape_spot_positions
                WHERE status IN ('closed', 'expired', 'stopped')
            """
            params: list = []
            if ticker is not None:
                base_sql += " AND ticker = %s"
                params.append(ticker)
            base_sql += " ORDER BY close_time DESC LIMIT %s"
            params.append(limit)

            cursor.execute(base_sql, tuple(params))
            rows = cursor.fetchall()
            trades = []
            for row in rows:
                trades.append({
                    "position_id": row[0],
                    "ticker": row[1],
                    "side": row[2],
                    "quantity": float(row[3]),
                    "entry_price": float(row[4]),
                    "close_price": float(row[5]) if row[5] else None,
                    "realized_pnl": float(row[6]) if row[6] else 0,
                    "close_reason": row[7],
                    "open_time": row[8].isoformat() if row[8] else None,
                    "close_time": row[9].isoformat() if row[9] else None,
                    "funding_regime_at_entry": row[10],
                    "squeeze_risk_at_entry": row[11],
                    "oracle_advice": row[12],
                    "oracle_win_probability": float(row[13]) if row[13] else None,
                    "signal_action": row[14],
                    "signal_confidence": row[15],
                    "account_label": row[16] if len(row) > 16 else "default",
                })
            return trades
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to get closed trades: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_position_count(self, ticker: Optional[str] = None) -> int:
        """Count open positions, optionally filtered by ticker."""
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            if ticker is not None:
                cursor.execute(
                    "SELECT COUNT(*) FROM agape_spot_positions WHERE status = 'open' AND ticker = %s",
                    (ticker,),
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM agape_spot_positions WHERE status = 'open'")
            return cursor.fetchone()[0]
        except Exception:
            return 0
        finally:
            cursor.close()
            conn.close()

    def has_traded_recently(self, ticker: Optional[str] = None, cooldown_minutes: int = 5) -> bool:
        """Check if any (or a specific ticker's) trade was opened recently."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            if ticker is not None:
                cursor.execute("""
                    SELECT COUNT(*) FROM agape_spot_positions
                    WHERE open_time > NOW() - INTERVAL '%s minutes'
                      AND ticker = %s
                """, (cooldown_minutes, ticker))
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM agape_spot_positions
                    WHERE open_time > NOW() - INTERVAL '%s minutes'
                """, (cooldown_minutes,))
            return cursor.fetchone()[0] > 0
        except Exception:
            return False
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
                UPDATE agape_spot_positions
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
    # Daily P&L (for portfolio circuit breaker)
    # ------------------------------------------------------------------

    def get_daily_realized_pnl(self, ticker: Optional[str] = None) -> float:
        """Sum of realized P&L for positions closed today (CT)."""
        conn = self._get_conn()
        if not conn:
            return 0.0
        try:
            cursor = conn.cursor()
            sql = """
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM agape_spot_positions
                WHERE status IN ('closed', 'expired', 'stopped')
                  AND DATE(close_time AT TIME ZONE 'America/Chicago')
                      = DATE(NOW() AT TIME ZONE 'America/Chicago')
            """
            params: list = []
            if ticker:
                sql += " AND ticker = %s"
                params.append(ticker)
            cursor.execute(sql, tuple(params) if params else None)
            return float(cursor.fetchone()[0])
        except Exception:
            return 0.0
        finally:
            cursor.close()
            conn.close()

    def get_daily_trade_count(self, ticker: Optional[str] = None) -> int:
        """Count positions closed today (CT)."""
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            sql = """
                SELECT COUNT(*)
                FROM agape_spot_positions
                WHERE status IN ('closed', 'expired', 'stopped')
                  AND DATE(close_time AT TIME ZONE 'America/Chicago')
                      = DATE(NOW() AT TIME ZONE 'America/Chicago')
            """
            params: list = []
            if ticker:
                sql += " AND ticker = %s"
                params.append(ticker)
            cursor.execute(sql, tuple(params) if params else None)
            return cursor.fetchone()[0]
        except Exception:
            return 0
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Equity Snapshots
    # ------------------------------------------------------------------

    def save_equity_snapshot(self, ticker: str, equity: float, unrealized_pnl: float,
                             realized_cumulative: float, open_positions: int,
                             eth_price: Optional[float] = None,
                             funding_rate: Optional[float] = None) -> bool:
        """Save an equity snapshot for a specific ticker."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_spot_equity_snapshots
                (ticker, equity, unrealized_pnl, realized_pnl_cumulative,
                 open_positions, eth_price, funding_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (ticker, equity, unrealized_pnl, realized_cumulative,
                  open_positions, eth_price, funding_rate))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to save equity snapshot ({ticker}): {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def get_equity_snapshots(self, ticker: Optional[str] = None, limit: int = 500) -> List[Dict]:
        """Get equity snapshots, optionally filtered by ticker."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            base_sql = """
                SELECT timestamp, ticker, equity, unrealized_pnl,
                       realized_pnl_cumulative, open_positions, eth_price, funding_rate
                FROM agape_spot_equity_snapshots
            """
            params: list = []
            if ticker is not None:
                base_sql += " WHERE ticker = %s"
                params.append(ticker)
            base_sql += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)

            cursor.execute(base_sql, tuple(params))
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "ticker": row[1],
                    "equity": float(row[2]) if row[2] else None,
                    "unrealized_pnl": float(row[3]) if row[3] else 0,
                    "realized_pnl_cumulative": float(row[4]) if row[4] else 0,
                    "open_positions": row[5],
                    "eth_price": float(row[6]) if row[6] else None,
                    "funding_rate": float(row[7]) if row[7] else None,
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to get equity snapshots: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Scan Activity & Logs
    # ------------------------------------------------------------------

    def log_scan(self, scan_data: Dict) -> bool:
        """Log a scan cycle. scan_data should include 'ticker' key."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_spot_scan_activity (
                    ticker, outcome, eth_price, funding_rate, funding_regime,
                    ls_ratio, ls_bias, squeeze_risk, leverage_regime,
                    max_pain, crypto_gex, crypto_gex_regime,
                    combined_signal, combined_confidence,
                    oracle_advice, oracle_win_prob,
                    signal_action, signal_reasoning,
                    position_id, error_message
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                scan_data.get("ticker", "ETH-USD"),
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
            logger.error(f"AGAPE-SPOT DB: Failed to log scan: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def log(self, level: str, action: str, message: str,
            details: Optional[Dict] = None, ticker: Optional[str] = None):
        """Log an activity event, optionally tagged with a ticker."""
        conn = self._get_conn()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_spot_activity_log (ticker, level, action, message, details)
                VALUES (%s, %s, %s, %s, %s)
            """, (ticker, level, action, message, json.dumps(details) if details else None))
            conn.commit()
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Log failed: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def get_logs(self, ticker: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get activity logs, optionally filtered by ticker."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            base_sql = """
                SELECT timestamp, ticker, level, action, message, details
                FROM agape_spot_activity_log
            """
            params: list = []
            if ticker is not None:
                base_sql += " WHERE ticker = %s"
                params.append(ticker)
            base_sql += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)

            cursor.execute(base_sql, tuple(params))
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "ticker": row[1],
                    "level": row[2],
                    "action": row[3],
                    "message": row[4],
                    "details": row[5],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to get logs: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_scan_activity(self, ticker: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get scan activity, optionally filtered by ticker."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            base_sql = """
                SELECT timestamp, ticker, outcome, eth_price, funding_rate,
                       funding_regime, ls_ratio, squeeze_risk,
                       combined_signal, combined_confidence,
                       oracle_advice, oracle_win_prob,
                       signal_action, signal_reasoning, position_id
                FROM agape_spot_scan_activity
            """
            params: list = []
            if ticker is not None:
                base_sql += " WHERE ticker = %s"
                params.append(ticker)
            base_sql += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)

            cursor.execute(base_sql, tuple(params))
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "ticker": row[1],
                    "outcome": row[2],
                    "eth_price": float(row[3]) if row[3] else None,
                    "funding_rate": float(row[4]) if row[4] else None,
                    "funding_regime": row[5],
                    "ls_ratio": float(row[6]) if row[6] else None,
                    "squeeze_risk": row[7],
                    "combined_signal": row[8],
                    "combined_confidence": row[9],
                    "oracle_advice": row[10],
                    "oracle_win_prob": float(row[11]) if row[11] else None,
                    "signal_action": row[12],
                    "signal_reasoning": row[13],
                    "position_id": row[14],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Failed to get scan activity: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Performance stats for CapitalAllocator (per-ticker ranking)
    # ------------------------------------------------------------------

    def get_ticker_performance_stats(self, tickers: list) -> Dict[str, Dict[str, Any]]:
        """Get per-ticker performance metrics for the CapitalAllocator.

        Returns {ticker: {total_trades, wins, total_pnl, recent_pnl,
                          avg_win, avg_loss}} for ALL provided tickers.
        Missing tickers get zeroed-out entries so the allocator always
        has data for every configured coin.
        """
        result: Dict[str, Dict[str, Any]] = {
            t: {
                "total_trades": 0, "wins": 0, "total_pnl": 0.0,
                "recent_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            }
            for t in tickers
        }
        conn = self._get_conn()
        if not conn:
            return result
        try:
            cursor = conn.cursor()

            # All-time stats grouped by ticker (live accounts only)
            cursor.execute("""
                SELECT
                    ticker,
                    COUNT(*) AS total_trades,
                    COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
                    COALESCE(SUM(realized_pnl), 0) AS total_pnl,
                    COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
                    COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl <= 0), 0) AS avg_loss
                FROM agape_spot_positions
                WHERE status IN ('closed', 'expired', 'stopped')
                  AND account_label != 'paper'
                GROUP BY ticker
            """)
            for row in cursor.fetchall():
                t = row[0]
                if t in result:
                    result[t]["total_trades"] = int(row[1])
                    result[t]["wins"] = int(row[2])
                    result[t]["total_pnl"] = float(row[3])
                    result[t]["avg_win"] = float(row[4])
                    result[t]["avg_loss"] = float(row[5])

            # Recent P&L (last 24h)
            cursor.execute("""
                SELECT
                    ticker,
                    COALESCE(SUM(realized_pnl), 0) AS recent_pnl
                FROM agape_spot_positions
                WHERE status IN ('closed', 'expired', 'stopped')
                  AND account_label != 'paper'
                  AND close_time > NOW() - INTERVAL '24 hours'
                GROUP BY ticker
            """)
            for row in cursor.fetchall():
                t = row[0]
                if t in result:
                    result[t]["recent_pnl"] = float(row[1])

            return result
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Performance stats query failed: {e}")
            return result
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Bayesian Win Tracker (per-ticker)
    # ------------------------------------------------------------------

    def get_win_tracker(self, ticker: str) -> "BayesianWinTracker":
        """Load the latest win tracker state for a ticker from the database.

        Returns a fresh BayesianWinTracker if no record exists yet.
        """
        from trading.agape_spot.models import BayesianWinTracker

        conn = self._get_conn()
        if not conn:
            return BayesianWinTracker(ticker=ticker)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT alpha, beta, total_trades,
                       positive_funding_wins, positive_funding_losses,
                       negative_funding_wins, negative_funding_losses,
                       neutral_funding_wins, neutral_funding_losses
                FROM agape_spot_win_tracker
                WHERE ticker = %s
                ORDER BY id DESC LIMIT 1
            """, (ticker,))
            row = cursor.fetchone()
            if row:
                return BayesianWinTracker(
                    ticker=ticker,
                    alpha=float(row[0]),
                    beta=float(row[1]),
                    total_trades=int(row[2]),
                    positive_funding_wins=int(row[3]),
                    positive_funding_losses=int(row[4]),
                    negative_funding_wins=int(row[5]),
                    negative_funding_losses=int(row[6]),
                    neutral_funding_wins=int(row[7]),
                    neutral_funding_losses=int(row[8]),
                )
            return BayesianWinTracker(ticker=ticker)
        except Exception as e:
            logger.warning(f"AGAPE-SPOT DB: Win tracker load failed for {ticker}: {e}")
            return BayesianWinTracker(ticker=ticker)
        finally:
            cursor.close()
            conn.close()

    def save_win_tracker(self, tracker: "BayesianWinTracker") -> bool:
        """Insert a new win tracker snapshot for audit trail (append-only)."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agape_spot_win_tracker (
                    ticker, alpha, beta, total_trades,
                    positive_funding_wins, positive_funding_losses,
                    negative_funding_wins, negative_funding_losses,
                    neutral_funding_wins, neutral_funding_losses
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                tracker.ticker,
                tracker.alpha,
                tracker.beta,
                tracker.total_trades,
                tracker.positive_funding_wins,
                tracker.positive_funding_losses,
                tracker.negative_funding_wins,
                tracker.negative_funding_losses,
                tracker.neutral_funding_wins,
                tracker.neutral_funding_losses,
            ))
            conn.commit()
            logger.info(
                f"AGAPE-SPOT DB: Win tracker saved for {tracker.ticker} "
                f"(trades={tracker.total_trades}, win_prob={tracker.win_probability:.3f})"
            )
            return True
        except Exception as e:
            logger.error(f"AGAPE-SPOT DB: Win tracker save failed for {tracker.ticker}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
