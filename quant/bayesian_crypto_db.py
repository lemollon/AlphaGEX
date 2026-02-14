"""
Bayesian Crypto Tracker - Database Layer.

Persists Bayesian tracker state, trade outcomes, and regime performance
to PostgreSQL for survival across restarts.

Tables:
  - bayesian_crypto_trackers: Tracker state (alpha, beta, P&L, streaks)
  - bayesian_crypto_trades: Individual trade outcomes with regime context
  - bayesian_crypto_snapshots: Periodic equity snapshots for charting
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
    logger.warning("BayesianCryptoDB: database_adapter not available")


def _now_ct() -> datetime:
    return datetime.now(CENTRAL_TZ)


class BayesianCryptoDatabase:
    """Database operations for the Bayesian Crypto Performance Tracker.

    Tables:
      - bayesian_crypto_trackers: Tracker state per strategy
      - bayesian_crypto_trades: Trade outcomes with market context
      - bayesian_crypto_snapshots: Equity curve data points
    """

    def __init__(self):
        self._ensure_tables()

    def _get_conn(self):
        if get_connection is None:
            return None
        return get_connection()

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        if not conn:
            logger.warning("BayesianCryptoDB: No database connection, skipping table creation")
            return
        try:
            cursor = conn.cursor()

            # Tracker state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bayesian_crypto_trackers (
                    id SERIAL PRIMARY KEY,
                    strategy_name VARCHAR(100) UNIQUE NOT NULL,
                    starting_capital FLOAT DEFAULT 10.0,
                    breakeven_win_rate FLOAT DEFAULT 0.50,
                    alpha FLOAT DEFAULT 1.0,
                    beta FLOAT DEFAULT 1.0,
                    total_wins INTEGER DEFAULT 0,
                    total_losses INTEGER DEFAULT 0,
                    cumulative_pnl FLOAT DEFAULT 0.0,
                    equity_high_water_mark FLOAT DEFAULT 10.0,
                    max_drawdown FLOAT DEFAULT 0.0,
                    max_win_streak INTEGER DEFAULT 0,
                    max_loss_streak INTEGER DEFAULT 0,
                    current_streak INTEGER DEFAULT 0,
                    regime_stats JSONB DEFAULT '{}',
                    volatility_stats JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Trade outcomes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bayesian_crypto_trades (
                    id SERIAL PRIMARY KEY,
                    strategy_name VARCHAR(100) NOT NULL,
                    trade_id VARCHAR(100) UNIQUE NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    entry_price FLOAT NOT NULL,
                    exit_price FLOAT NOT NULL,
                    pnl FLOAT NOT NULL,
                    contracts INTEGER DEFAULT 1,
                    entry_time TIMESTAMPTZ NOT NULL,
                    exit_time TIMESTAMPTZ NOT NULL,
                    hold_duration_minutes FLOAT,
                    is_win BOOLEAN NOT NULL,
                    return_pct FLOAT,
                    funding_regime VARCHAR(50) DEFAULT 'UNKNOWN',
                    leverage_regime VARCHAR(50) DEFAULT 'UNKNOWN',
                    volatility_state VARCHAR(20) DEFAULT 'NORMAL',
                    ls_bias VARCHAR(30) DEFAULT 'NEUTRAL',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Index for time-based queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bct_strategy_exit
                ON bayesian_crypto_trades(strategy_name, exit_time DESC)
            """)

            # Equity snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bayesian_crypto_snapshots (
                    id SERIAL PRIMARY KEY,
                    strategy_name VARCHAR(100) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    equity FLOAT NOT NULL,
                    cumulative_pnl FLOAT NOT NULL,
                    unrealized_pnl FLOAT DEFAULT 0.0,
                    bayesian_win_rate FLOAT,
                    edge_probability FLOAT,
                    total_trades INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_bcs_strategy_time
                ON bayesian_crypto_snapshots(strategy_name, timestamp DESC)
            """)

            conn.commit()
            logger.info("BayesianCryptoDB: Tables ensured")
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Table creation failed: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Tracker State CRUD
    # ------------------------------------------------------------------

    def save_tracker_state(self, tracker) -> bool:
        """Persist a BayesianCryptoTracker's state to the database."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            data = tracker.to_dict()

            # Serialize regime stats
            regime_json = json.dumps({
                k: v.to_dict() for k, v in tracker.regime_stats.items()
            })
            vol_json = json.dumps({
                k: v.to_dict() for k, v in tracker.volatility_stats.items()
            })

            cursor.execute("""
                INSERT INTO bayesian_crypto_trackers
                    (strategy_name, starting_capital, breakeven_win_rate,
                     alpha, beta, total_wins, total_losses,
                     cumulative_pnl, equity_high_water_mark, max_drawdown,
                     max_win_streak, max_loss_streak, current_streak,
                     regime_stats, volatility_stats, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (strategy_name) DO UPDATE SET
                    alpha = EXCLUDED.alpha,
                    beta = EXCLUDED.beta,
                    total_wins = EXCLUDED.total_wins,
                    total_losses = EXCLUDED.total_losses,
                    cumulative_pnl = EXCLUDED.cumulative_pnl,
                    equity_high_water_mark = EXCLUDED.equity_high_water_mark,
                    max_drawdown = EXCLUDED.max_drawdown,
                    max_win_streak = EXCLUDED.max_win_streak,
                    max_loss_streak = EXCLUDED.max_loss_streak,
                    current_streak = EXCLUDED.current_streak,
                    regime_stats = EXCLUDED.regime_stats,
                    volatility_stats = EXCLUDED.volatility_stats,
                    updated_at = NOW()
            """, (
                data["strategy_name"],
                data["starting_capital"],
                data["breakeven_win_rate"],
                data["alpha"],
                data["beta"],
                data["total_wins"],
                data["total_losses"],
                data["cumulative_pnl"],
                data["equity_high_water_mark"],
                data["max_drawdown"],
                data["max_win_streak"],
                data["max_loss_streak"],
                data["current_streak"],
                regime_json,
                vol_json,
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to save tracker: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def load_tracker_state(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Load tracker state from database."""
        conn = self._get_conn()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT strategy_name, starting_capital, breakeven_win_rate,
                       alpha, beta, total_wins, total_losses,
                       cumulative_pnl, equity_high_water_mark, max_drawdown,
                       max_win_streak, max_loss_streak, current_streak,
                       regime_stats, volatility_stats,
                       created_at, updated_at
                FROM bayesian_crypto_trackers
                WHERE strategy_name = %s
            """, (strategy_name,))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "strategy_name": row[0],
                "starting_capital": row[1],
                "breakeven_win_rate": row[2],
                "alpha": row[3],
                "beta": row[4],
                "total_wins": row[5],
                "total_losses": row[6],
                "cumulative_pnl": row[7],
                "equity_high_water_mark": row[8],
                "max_drawdown": row[9],
                "max_win_streak": row[10],
                "max_loss_streak": row[11],
                "current_streak": row[12],
                "regime_stats": row[13] if isinstance(row[13], dict) else {},
                "volatility_stats": row[14] if isinstance(row[14], dict) else {},
                "created_at": row[15].isoformat() if row[15] else None,
                "last_updated": row[16].isoformat() if row[16] else None,
            }
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to load tracker: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def list_trackers(self) -> List[Dict[str, Any]]:
        """List all tracker strategies."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT strategy_name, starting_capital,
                       alpha, beta, total_wins, total_losses,
                       cumulative_pnl, max_drawdown,
                       created_at, updated_at
                FROM bayesian_crypto_trackers
                ORDER BY updated_at DESC
            """)
            rows = cursor.fetchall()
            result = []
            for row in rows:
                total = row[4] + row[5]
                win_rate = row[2] / (row[2] + row[3]) if (row[2] + row[3]) > 0 else 0.5
                result.append({
                    "strategy_name": row[0],
                    "starting_capital": row[1],
                    "bayesian_win_rate": round(win_rate, 4),
                    "total_trades": total,
                    "cumulative_pnl": round(row[6], 2),
                    "max_drawdown": round(row[7], 2),
                    "created_at": row[8].isoformat() if row[8] else None,
                    "updated_at": row[9].isoformat() if row[9] else None,
                })
            return result
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to list trackers: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Trade CRUD
    # ------------------------------------------------------------------

    def save_trade(self, strategy_name: str, outcome) -> bool:
        """Save a trade outcome to the database."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bayesian_crypto_trades
                    (strategy_name, trade_id, symbol, side,
                     entry_price, exit_price, pnl, contracts,
                     entry_time, exit_time, hold_duration_minutes,
                     is_win, return_pct,
                     funding_regime, leverage_regime, volatility_state, ls_bias)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_id) DO NOTHING
            """, (
                strategy_name,
                outcome.trade_id,
                outcome.symbol,
                outcome.side,
                outcome.entry_price,
                outcome.exit_price,
                outcome.pnl,
                outcome.contracts,
                outcome.entry_time,
                outcome.exit_time,
                outcome.hold_duration_minutes,
                outcome.is_win,
                outcome.return_pct,
                outcome.funding_regime,
                outcome.leverage_regime,
                outcome.volatility_state,
                outcome.ls_bias,
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to save trade: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def get_trades(
        self,
        strategy_name: str,
        limit: int = 100,
        offset: int = 0,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch trades for a strategy."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()

            if since:
                cursor.execute("""
                    SELECT trade_id, symbol, side, entry_price, exit_price,
                           pnl, contracts, entry_time, exit_time,
                           hold_duration_minutes, is_win, return_pct,
                           funding_regime, leverage_regime, volatility_state, ls_bias
                    FROM bayesian_crypto_trades
                    WHERE strategy_name = %s AND exit_time >= %s
                    ORDER BY exit_time DESC
                    LIMIT %s OFFSET %s
                """, (strategy_name, since, limit, offset))
            else:
                cursor.execute("""
                    SELECT trade_id, symbol, side, entry_price, exit_price,
                           pnl, contracts, entry_time, exit_time,
                           hold_duration_minutes, is_win, return_pct,
                           funding_regime, leverage_regime, volatility_state, ls_bias
                    FROM bayesian_crypto_trades
                    WHERE strategy_name = %s
                    ORDER BY exit_time DESC
                    LIMIT %s OFFSET %s
                """, (strategy_name, limit, offset))

            rows = cursor.fetchall()
            result = []
            for row in rows:
                result.append({
                    "trade_id": row[0],
                    "symbol": row[1],
                    "side": row[2],
                    "entry_price": row[3],
                    "exit_price": row[4],
                    "pnl": round(row[5], 4),
                    "contracts": row[6],
                    "entry_time": row[7].isoformat() if row[7] else None,
                    "exit_time": row[8].isoformat() if row[8] else None,
                    "hold_duration_minutes": round(row[9], 1) if row[9] else None,
                    "is_win": row[10],
                    "return_pct": round(row[11], 4) if row[11] else None,
                    "funding_regime": row[12],
                    "leverage_regime": row[13],
                    "volatility_state": row[14],
                    "ls_bias": row[15],
                })
            return result
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to get trades: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_trade_count(self, strategy_name: str) -> int:
        """Get total trade count for a strategy."""
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM bayesian_crypto_trades
                WHERE strategy_name = %s
            """, (strategy_name,))
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to count trades: {e}")
            return 0
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Equity Snapshots
    # ------------------------------------------------------------------

    def save_equity_snapshot(
        self,
        strategy_name: str,
        equity: float,
        cumulative_pnl: float,
        unrealized_pnl: float = 0.0,
        bayesian_win_rate: float = 0.5,
        edge_probability: float = 0.5,
        total_trades: int = 0,
    ) -> bool:
        """Save an equity snapshot for charting."""
        conn = self._get_conn()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bayesian_crypto_snapshots
                    (strategy_name, timestamp, equity, cumulative_pnl,
                     unrealized_pnl, bayesian_win_rate, edge_probability, total_trades)
                VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s)
            """, (
                strategy_name, equity, cumulative_pnl,
                unrealized_pnl, bayesian_win_rate, edge_probability, total_trades,
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to save snapshot: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def get_equity_curve(
        self,
        strategy_name: str,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get equity curve data for charting."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, equity, cumulative_pnl, unrealized_pnl,
                       bayesian_win_rate, edge_probability, total_trades
                FROM bayesian_crypto_snapshots
                WHERE strategy_name = %s
                  AND timestamp >= NOW() - INTERVAL '%s days'
                ORDER BY timestamp ASC
            """, (strategy_name, days))

            rows = cursor.fetchall()
            return [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "equity": round(row[1], 2),
                    "cumulative_pnl": round(row[2], 2),
                    "unrealized_pnl": round(row[3], 2) if row[3] else 0.0,
                    "bayesian_win_rate": round(row[4], 4) if row[4] else None,
                    "edge_probability": round(row[5], 4) if row[5] else None,
                    "total_trades": row[6],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to get equity curve: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_daily_summary(self, strategy_name: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily aggregated performance."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    DATE(exit_time AT TIME ZONE 'America/Chicago') as trade_date,
                    COUNT(*) as trades,
                    SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                    SUM(pnl) as daily_pnl,
                    AVG(pnl) as avg_pnl,
                    MAX(pnl) as best_trade,
                    MIN(pnl) as worst_trade,
                    AVG(hold_duration_minutes) as avg_hold_minutes
                FROM bayesian_crypto_trades
                WHERE strategy_name = %s
                  AND exit_time >= NOW() - INTERVAL '%s days'
                GROUP BY DATE(exit_time AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date DESC
            """, (strategy_name, days))

            rows = cursor.fetchall()
            return [
                {
                    "date": row[0].isoformat() if row[0] else None,
                    "trades": row[1],
                    "wins": row[2],
                    "win_rate": round(row[2] / max(1, row[1]), 4),
                    "daily_pnl": round(row[3], 2),
                    "avg_pnl": round(row[4], 4),
                    "best_trade": round(row[5], 4),
                    "worst_trade": round(row[6], 4),
                    "avg_hold_minutes": round(row[7], 1) if row[7] else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"BayesianCryptoDB: Failed to get daily summary: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
