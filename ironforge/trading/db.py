"""
PostgreSQL Database Layer
==========================

Unified database operations for FLAME and SPARK bots on PostgreSQL (Render).

Key differences from Databricks version:
- Uses psycopg2 (not Databricks SQL connector)
- PostgreSQL tables (not Delta Lake)
- ON CONFLICT for upserts (not MERGE INTO)
- DATE_SUB → CURRENT_DATE - INTERVAL
- DAYOFWEEK → EXTRACT(DOW FROM ...)
- CURRENT_TIMESTAMP() → NOW()
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from .db_adapter import db_connection, _to_python, table
from .models import (
    IronCondorPosition, PositionStatus,
    BotConfig, TradingMode, PaperAccount,
    DailySummary, CENTRAL_TZ
)

logger = logging.getLogger(__name__)


class TradingDatabase:
    """Unified database operations for both FLAME and SPARK on PostgreSQL."""

    def __init__(self, bot_name: str = "FLAME", dte_mode: str = "2DTE"):
        self.bot_name = bot_name
        self.dte_mode = dte_mode
        self._prefix = bot_name.lower().split("_")[0]

    def _t(self, suffix: str) -> str:
        return table(f"{self._prefix}_{suffix}")

    # =========================================================================
    # PAPER ACCOUNT OPERATIONS
    # =========================================================================

    def initialize_paper_account(self, starting_capital: float = 10000.0) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(
                    f"SELECT id FROM {self._t('paper_account')} WHERE is_active = TRUE AND dte_mode = %s LIMIT 1",
                    [self.dte_mode],
                )
                if c.fetchone():
                    logger.info(f"{self.bot_name}: Paper account already exists")
                    return True
                c.execute(f"""
                    INSERT INTO {self._t('paper_account')} (
                        starting_capital, current_balance, cumulative_pnl,
                        buying_power, high_water_mark, dte_mode
                    ) VALUES (%s, %s, 0, %s, %s, %s)
                """, [starting_capital, starting_capital, starting_capital, starting_capital, self.dte_mode])
                logger.info(f"{self.bot_name}: Paper account initialized with ${starting_capital}")
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to initialize paper account: {e}")
            return False

    def get_paper_account(self) -> PaperAccount:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT starting_capital, current_balance, cumulative_pnl,
                           total_trades, collateral_in_use, buying_power,
                           high_water_mark, max_drawdown, is_active
                    FROM {self._t('paper_account')}
                    WHERE is_active = TRUE AND dte_mode = %s
                    ORDER BY id DESC LIMIT 1
                """, [self.dte_mode])
                row = c.fetchone()
                if row:
                    return PaperAccount(
                        starting_balance=float(row[0]),
                        balance=float(row[1]),
                        cumulative_pnl=float(row[2]),
                        total_trades=int(row[3]),
                        collateral_in_use=float(row[4]),
                        buying_power=float(row[5]),
                        high_water_mark=float(row[6]),
                        max_drawdown=float(row[7]),
                        is_active=bool(row[8]),
                    )
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get paper account: {e}")
        return PaperAccount()

    def update_paper_balance(self, realized_pnl: float = 0, collateral_change: float = 0) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT id, current_balance, cumulative_pnl, total_trades,
                           collateral_in_use, high_water_mark, max_drawdown
                    FROM {self._t('paper_account')}
                    WHERE is_active = TRUE AND dte_mode = %s
                    ORDER BY id DESC LIMIT 1
                """, [self.dte_mode])
                row = c.fetchone()
                if not row:
                    return False

                account_id = row[0]
                new_balance = float(row[1]) + realized_pnl
                new_cum_pnl = float(row[2]) + realized_pnl
                new_collateral = max(0, float(row[4]) + collateral_change)
                new_bp = new_balance - new_collateral
                new_trades = int(row[3]) + (1 if realized_pnl != 0 else 0)
                new_hwm = max(float(row[5]), new_balance)
                new_max_dd = max(float(row[6]), new_hwm - new_balance)

                c.execute(f"""
                    UPDATE {self._t('paper_account')}
                    SET current_balance = %s, cumulative_pnl = %s,
                        total_trades = %s, collateral_in_use = %s,
                        buying_power = %s, high_water_mark = %s,
                        max_drawdown = %s, updated_at = NOW()
                    WHERE id = %s
                """, [new_balance, new_cum_pnl, new_trades, new_collateral,
                      new_bp, new_hwm, new_max_dd, account_id])
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update paper balance: {e}")
            return False

    # =========================================================================
    # POSITION OPERATIONS
    # =========================================================================

    def get_open_positions(self) -> List[IronCondorPosition]:
        positions = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike, put_credit,
                        call_short_strike, call_long_strike, call_credit,
                        contracts, spread_width, total_credit, max_loss, max_profit,
                        underlying_at_entry, vix_at_entry, expected_move,
                        call_wall, put_wall, gex_regime,
                        flip_point, net_gex,
                        oracle_confidence, oracle_win_probability, oracle_advice,
                        oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
                        wings_adjusted, original_put_width, original_call_width,
                        put_order_id, call_order_id,
                        status, open_time, close_time, close_price, close_reason,
                        realized_pnl, collateral_required
                    FROM {self._t('positions')}
                    WHERE status = 'open' AND dte_mode = %s
                    ORDER BY open_time DESC
                """, [self.dte_mode])

                for row in c.fetchall():
                    pos = IronCondorPosition(
                        position_id=row[0], ticker=row[1], expiration=str(row[2]),
                        put_short_strike=float(row[3]), put_long_strike=float(row[4]),
                        put_credit=float(row[5]),
                        call_short_strike=float(row[6]), call_long_strike=float(row[7]),
                        call_credit=float(row[8]),
                        contracts=int(row[9]), spread_width=float(row[10]),
                        total_credit=float(row[11]), max_loss=float(row[12]),
                        max_profit=float(row[13]),
                        underlying_at_entry=float(row[14]),
                        vix_at_entry=float(row[15] or 0),
                        expected_move=float(row[16] or 0),
                        call_wall=float(row[17] or 0), put_wall=float(row[18] or 0),
                        gex_regime=row[19] or "",
                        flip_point=float(row[20] or 0), net_gex=float(row[21] or 0),
                        oracle_confidence=float(row[22] or 0),
                        oracle_win_probability=float(row[23] or 0),
                        oracle_advice=row[24] or "",
                        oracle_reasoning=row[25] or "",
                        oracle_top_factors=row[26] or "",
                        oracle_use_gex_walls=bool(row[27]),
                        wings_adjusted=bool(row[28]),
                        original_put_width=float(row[29] or 0),
                        original_call_width=float(row[30] or 0),
                        put_order_id=row[31] or "PAPER",
                        call_order_id=row[32] or "PAPER",
                        status=PositionStatus(row[33]),
                        open_time=row[34], close_time=row[35],
                        close_price=float(row[36] or 0),
                        close_reason=row[37] or "",
                        realized_pnl=float(row[38] or 0),
                        collateral_required=float(row[39] or 0),
                    )
                    positions.append(pos)
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to load positions: {e}")
        return positions

    def save_position(self, pos: IronCondorPosition) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    INSERT INTO {self._t('positions')} (
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike, put_credit,
                        call_short_strike, call_long_strike, call_credit,
                        contracts, spread_width, total_credit, max_loss, max_profit,
                        collateral_required,
                        underlying_at_entry, vix_at_entry, expected_move,
                        call_wall, put_wall, gex_regime,
                        flip_point, net_gex,
                        oracle_confidence, oracle_win_probability, oracle_advice,
                        oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
                        wings_adjusted, original_put_width, original_call_width,
                        put_order_id, call_order_id,
                        status, open_time, open_date, dte_mode
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, [
                    pos.position_id, pos.ticker, pos.expiration,
                    _to_python(pos.put_short_strike), _to_python(pos.put_long_strike),
                    _to_python(pos.put_credit),
                    _to_python(pos.call_short_strike), _to_python(pos.call_long_strike),
                    _to_python(pos.call_credit),
                    _to_python(pos.contracts), _to_python(pos.spread_width),
                    _to_python(pos.total_credit),
                    _to_python(pos.max_loss), _to_python(pos.max_profit),
                    _to_python(pos.collateral_required),
                    _to_python(pos.underlying_at_entry), _to_python(pos.vix_at_entry),
                    _to_python(pos.expected_move),
                    _to_python(pos.call_wall), _to_python(pos.put_wall),
                    pos.gex_regime or None,
                    _to_python(pos.flip_point), _to_python(pos.net_gex),
                    _to_python(pos.oracle_confidence), _to_python(pos.oracle_win_probability),
                    pos.oracle_advice or None,
                    pos.oracle_reasoning or None, pos.oracle_top_factors or None,
                    bool(pos.oracle_use_gex_walls),
                    bool(pos.wings_adjusted),
                    _to_python(pos.original_put_width), _to_python(pos.original_call_width),
                    pos.put_order_id or "PAPER", pos.call_order_id or "PAPER",
                    pos.status.value, pos.open_time,
                    pos.open_time.date() if pos.open_time else datetime.now(CENTRAL_TZ).date(),
                    self.dte_mode,
                ])
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save position: {e}")
            return False

    def close_position(self, position_id: str, close_price: float,
                       realized_pnl: float, close_reason: str) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    UPDATE {self._t('positions')}
                    SET status = 'closed', close_time = NOW(),
                        close_price = %s, realized_pnl = %s,
                        close_reason = %s, updated_at = NOW()
                    WHERE position_id = %s AND status = 'open' AND dte_mode = %s
                """, [close_price, realized_pnl, close_reason, position_id, self.dte_mode])
                if c.rowcount == 0:
                    logger.warning(
                        f"{self.bot_name}: close_position no-op — "
                        f"{position_id} not found or already closed"
                    )
                    return False
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to close position: {e}")
            return False

    def update_position_fill(
        self,
        position_id: str,
        actual_credit: float,
        actual_put_credit: float = 0.0,
        actual_call_credit: float = 0.0,
    ) -> bool:
        """Update a position's credit fields with actual Tradier sandbox fill prices.

        After mirroring to Tradier sandbox, the actual fill price may differ
        from our bid/ask estimate. This updates the position so the frontend
        and P&L calculations use the real fill, not the estimate.

        Also recalculates max_profit, max_loss, and collateral_required
        based on the actual credit.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Read current spread_width and contracts to recalculate derived fields
                c.execute(f"""
                    SELECT spread_width, contracts
                    FROM {self._t('positions')}
                    WHERE position_id = %s AND dte_mode = %s
                """, [position_id, self.dte_mode])
                row = c.fetchone()
                if not row:
                    logger.warning(f"{self.bot_name}: update_position_fill — {position_id} not found")
                    return False

                spread_width = float(row[0])
                contracts = int(row[1])
                max_profit = round(actual_credit * 100 * contracts, 2)
                collateral_per = max(0, (spread_width - actual_credit) * 100)
                collateral_required = round(collateral_per * contracts, 2)
                max_loss = collateral_required

                c.execute(f"""
                    UPDATE {self._t('positions')}
                    SET total_credit = %s,
                        put_credit = %s,
                        call_credit = %s,
                        max_profit = %s,
                        max_loss = %s,
                        collateral_required = %s,
                        updated_at = NOW()
                    WHERE position_id = %s AND dte_mode = %s
                """, [
                    actual_credit,
                    actual_put_credit if actual_put_credit else actual_credit,
                    actual_call_credit if actual_call_credit else 0.0,
                    max_profit, max_loss, collateral_required,
                    position_id, self.dte_mode,
                ])
                logger.info(
                    f"{self.bot_name}: Updated {position_id} with actual fill "
                    f"credit=${actual_credit:.4f} (max_profit=${max_profit:.2f}, "
                    f"collateral=${collateral_required:.2f})"
                )
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update position fill: {e}")
            return False

    def update_sandbox_order_id(self, position_id: str, sandbox_order_id: str) -> bool:
        """Store the Tradier sandbox order ID on a position."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    UPDATE {self._t('positions')}
                    SET sandbox_order_id = %s, updated_at = NOW()
                    WHERE position_id = %s AND dte_mode = %s
                """, [sandbox_order_id, position_id, self.dte_mode])
                return True
        except Exception as e:
            logger.warning(f"{self.bot_name}: Failed to store sandbox order ID: {e}")
            return False

    def update_sandbox_close_order_id(self, position_id: str, sandbox_close_order_id: str) -> bool:
        """Store the Tradier sandbox close order IDs on a position."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    UPDATE {self._t('positions')}
                    SET sandbox_close_order_id = %s, updated_at = NOW()
                    WHERE position_id = %s AND dte_mode = %s
                """, [sandbox_close_order_id, position_id, self.dte_mode])
                return True
        except Exception as e:
            logger.warning(f"{self.bot_name}: Failed to store sandbox close order ID: {e}")
            return False

    def expire_position(self, position_id: str, realized_pnl: float,
                        close_price: float = None) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    UPDATE {self._t('positions')}
                    SET status = 'expired', close_time = NOW(),
                        close_reason = 'EXPIRED',
                        close_price = %s, realized_pnl = %s, updated_at = NOW()
                    WHERE position_id = %s AND status = 'open' AND dte_mode = %s
                """, [_to_python(close_price), _to_python(realized_pnl), position_id, self.dte_mode])
                if c.rowcount == 0:
                    logger.warning(
                        f"{self.bot_name}: expire_position no-op — "
                        f"{position_id} not found or already closed"
                    )
                    return False
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to expire position: {e}")
            return False

    def get_position_count(self) -> int:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(
                    f"SELECT COUNT(*) FROM {self._t('positions')} WHERE status = 'open' AND dte_mode = %s",
                    [self.dte_mode],
                )
                return c.fetchone()[0]
        except Exception:
            return 0

    def has_traded_today(self, date: str) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT COUNT(*) FROM {self._t('positions')}
                    WHERE open_time::date = %s AND dte_mode = %s
                """, [date, self.dte_mode])
                return c.fetchone()[0] > 0
        except Exception:
            return False

    def get_trades_today_count(self, date: str) -> int:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT COUNT(*) FROM {self._t('positions')}
                    WHERE open_time::date = %s AND dte_mode = %s
                """, [date, self.dte_mode])
                return c.fetchone()[0]
        except Exception:
            return 0

    # =========================================================================
    # PDT TRACKING
    # =========================================================================

    def log_pdt_entry(self, position_id: str, symbol: str, opened_at: datetime,
                      contracts: int, entry_credit: float) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    INSERT INTO {self._t('pdt_log')} (
                        trade_date, symbol, position_id, opened_at,
                        contracts, entry_credit, dte_mode
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, [opened_at.date(), symbol, position_id,
                      opened_at, contracts, entry_credit, self.dte_mode])
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to log PDT entry: {e}")
            return False

    def update_pdt_close(self, position_id: str, closed_at: datetime,
                         exit_cost: float, pnl: float, close_reason: str) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT opened_at FROM {self._t('pdt_log')}
                    WHERE position_id = %s AND dte_mode = %s LIMIT 1
                """, [position_id, self.dte_mode])
                row = c.fetchone()
                is_day_trade = False
                if row and row[0]:
                    opened_date = row[0].date() if hasattr(row[0], 'date') else row[0]
                    closed_date = closed_at.date() if hasattr(closed_at, 'date') else closed_at
                    is_day_trade = str(opened_date) == str(closed_date)

                c.execute(f"""
                    UPDATE {self._t('pdt_log')}
                    SET closed_at = %s, exit_cost = %s, pnl = %s,
                        close_reason = %s, is_day_trade = %s
                    WHERE position_id = %s AND dte_mode = %s
                """, [closed_at, exit_cost, pnl, close_reason, is_day_trade,
                      position_id, self.dte_mode])
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update PDT close: {e}")
            return False

    def get_day_trade_count_rolling_5_days(self) -> int:
        """Count day trades in rolling 5 business day window.
        6 calendar days back = exactly 5 business days for any weekday.
        """
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT COUNT(*) FROM {self._t('pdt_log')}
                    WHERE is_day_trade = TRUE
                    AND dte_mode = %s
                    AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
                    AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5
                """, [self.dte_mode])
                result = c.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get PDT count: {e}")
            return 0

    def get_pdt_trigger_trades(self) -> List[Dict[str, Any]]:
        """Return the actual day trades in the rolling 5 biz day window with their dates
        and when each falls off (trade_date + 7 calendar days = exits the window)."""
        trades = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT DISTINCT trade_date FROM {self._t('pdt_log')}
                    WHERE is_day_trade = TRUE
                    AND dte_mode = %s
                    AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
                    AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5
                    ORDER BY trade_date ASC
                """, [self.dte_mode])
                for row in c.fetchall():
                    td = row[0]
                    if isinstance(td, str):
                        from datetime import date
                        td = date.fromisoformat(td)
                    # Trade exits the window when today > trade_date + 6 calendar days
                    # i.e., the first day it's gone is trade_date + 7
                    falls_off = td + timedelta(days=7)
                    # If falls_off lands on weekend, advance to Monday
                    if falls_off.weekday() == 5:  # Saturday
                        falls_off += timedelta(days=2)
                    elif falls_off.weekday() == 6:  # Sunday
                        falls_off += timedelta(days=1)
                    trades.append({
                        'trade_date': str(td),
                        'falls_off': str(falls_off),
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get PDT trigger trades: {e}")
        return trades

    def get_pdt_log(self, days: int = 10) -> List[Dict[str, Any]]:
        entries = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT trade_date, symbol, position_id, opened_at, closed_at,
                           is_day_trade, contracts, entry_credit, exit_cost, pnl, close_reason
                    FROM {self._t('pdt_log')}
                    WHERE trade_date >= CURRENT_DATE - (%s || ' days')::interval AND dte_mode = %s
                    ORDER BY opened_at DESC
                """, [str(days), self.dte_mode])
                for row in c.fetchall():
                    entries.append({
                        'trade_date': str(row[0]),
                        'symbol': row[1],
                        'position_id': row[2],
                        'opened_at': row[3].isoformat() if row[3] else None,
                        'closed_at': row[4].isoformat() if row[4] else None,
                        'is_day_trade': bool(row[5]) if row[5] is not None else False,
                        'contracts': row[6],
                        'entry_credit': float(row[7]) if row[7] else 0,
                        'exit_cost': float(row[8]) if row[8] else 0,
                        'pnl': float(row[9]) if row[9] else 0,
                        'close_reason': row[10],
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get PDT log: {e}")
        return entries

    def get_next_pdt_reset_date(self) -> Optional[str]:
        """When the oldest day trade exits the rolling 5 biz day window.
        A trade on date X exits when today > X + 6 calendar days,
        so the next slot opens on X + 7 calendar days."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT MIN(trade_date) FROM {self._t('pdt_log')}
                    WHERE is_day_trade = TRUE AND dte_mode = %s
                    AND trade_date >= CURRENT_DATE - INTERVAL '6 days'
                    AND EXTRACT(DOW FROM trade_date) BETWEEN 1 AND 5
                """, [self.dte_mode])
                result = c.fetchone()
                if result and result[0]:
                    oldest_date = result[0]
                    if isinstance(oldest_date, str):
                        from datetime import date
                        oldest_date = date.fromisoformat(oldest_date)
                    reset_date = oldest_date + timedelta(days=7)
                    # If lands on weekend, advance to Monday
                    if reset_date.weekday() == 5:
                        reset_date += timedelta(days=2)
                    elif reset_date.weekday() == 6:
                        reset_date += timedelta(days=1)
                    return str(reset_date)
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get PDT reset date: {e}")
        return None

    # =========================================================================
    # SIGNAL LOGGING
    # =========================================================================

    def log_signal(self, spot_price: float, vix: float, expected_move: float,
                   call_wall: float, put_wall: float, gex_regime: str,
                   put_short: float, put_long: float, call_short: float, call_long: float,
                   total_credit: float, confidence: float, was_executed: bool,
                   skip_reason: Optional[str] = None, reasoning: Optional[str] = None,
                   wings_adjusted: bool = False) -> Optional[int]:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    INSERT INTO {self._t('signals')} (
                        spot_price, vix, expected_move, call_wall, put_wall,
                        gex_regime, put_short, put_long, call_short, call_long,
                        total_credit, confidence, was_executed, skip_reason, reasoning,
                        wings_adjusted, dte_mode
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, [
                    _to_python(spot_price), _to_python(vix), _to_python(expected_move),
                    _to_python(call_wall), _to_python(put_wall),
                    gex_regime, _to_python(put_short), _to_python(put_long),
                    _to_python(call_short), _to_python(call_long),
                    _to_python(total_credit), _to_python(confidence),
                    was_executed, skip_reason, reasoning, wings_adjusted,
                    self.dte_mode,
                ])
                row = c.fetchone()
                return row[0] if row else 1
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to log signal: {e}")
            return None

    # =========================================================================
    # BOT TOGGLE
    # =========================================================================

    def set_bot_active(self, active: bool) -> bool:
        """Persist is_active state in the paper_account table."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    UPDATE {self._t('paper_account')}
                    SET is_active = %s, updated_at = NOW()
                    WHERE dte_mode = %s
                """, [active, self.dte_mode])
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to set bot active: {e}")
            return False

    def get_bot_active(self) -> bool:
        """Read persisted is_active state from paper_account."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT is_active FROM {self._t('paper_account')}
                    WHERE dte_mode = %s ORDER BY id DESC LIMIT 1
                """, [self.dte_mode])
                row = c.fetchone()
                if row is not None:
                    return bool(row[0])
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get bot active state: {e}")
        return True  # default to active

    # =========================================================================
    # CONFIG PERSISTENCE
    # =========================================================================

    def save_config(self, overrides: Dict[str, Any]) -> bool:
        """Save config overrides to the config table (upsert by dte_mode)."""
        allowed_fields = {
            'sd_multiplier', 'spread_width', 'min_credit', 'profit_target_pct',
            'stop_loss_pct', 'vix_skip', 'max_contracts', 'max_trades_per_day',
            'buying_power_usage_pct', 'risk_per_trade_pct', 'min_win_probability',
            'entry_start', 'entry_end', 'eod_cutoff_et', 'pdt_max_day_trades',
            'starting_capital',
        }
        filtered = {k: v for k, v in overrides.items() if k in allowed_fields}
        if not filtered:
            return False

        try:
            with db_connection() as conn:
                c = conn.cursor()
                # Build dynamic SET clause for upsert
                columns = ['dte_mode'] + list(filtered.keys())
                values = [self.dte_mode] + list(filtered.values())
                placeholders = ', '.join(f'%s' for _ in values)
                col_names = ', '.join(columns)
                update_clause = ', '.join(
                    f'{k} = EXCLUDED.{k}' for k in filtered.keys()
                )

                c.execute(f"""
                    INSERT INTO {self._t('config')} ({col_names})
                    VALUES ({placeholders})
                    ON CONFLICT (dte_mode) DO UPDATE SET
                        {update_clause}, updated_at = NOW()
                """, values)
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save config: {e}")
            return False

    def load_config(self) -> Optional[Dict[str, Any]]:
        """Load config overrides from the config table."""
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT sd_multiplier, spread_width, min_credit, profit_target_pct,
                           stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
                           buying_power_usage_pct, risk_per_trade_pct, min_win_probability,
                           entry_start, entry_end, eod_cutoff_et, pdt_max_day_trades,
                           starting_capital
                    FROM {self._t('config')}
                    WHERE dte_mode = %s LIMIT 1
                """, [self.dte_mode])
                row = c.fetchone()
                if not row:
                    return None
                keys = [
                    'sd_multiplier', 'spread_width', 'min_credit', 'profit_target_pct',
                    'stop_loss_pct', 'vix_skip', 'max_contracts', 'max_trades_per_day',
                    'buying_power_usage_pct', 'risk_per_trade_pct', 'min_win_probability',
                    'entry_start', 'entry_end', 'eod_cutoff_et', 'pdt_max_day_trades',
                    'starting_capital',
                ]
                result = {}
                for i, key in enumerate(keys):
                    if row[i] is not None:
                        result[key] = float(row[i]) if isinstance(row[i], (int, float, str)) and key not in ('entry_start', 'entry_end', 'eod_cutoff_et') else row[i]
                        # Ensure int fields stay int
                        if key in ('max_contracts', 'max_trades_per_day', 'pdt_max_day_trades'):
                            result[key] = int(result[key])
                return result if result else None
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to load config: {e}")
            return None

    # =========================================================================
    # CONFIG & LOGGING
    # =========================================================================

    def log(self, level: str, message: str, details: Optional[Dict] = None) -> None:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    INSERT INTO {self._t('logs')} (level, message, details, dte_mode)
                    VALUES (%s, %s, %s, %s)
                """, [level, message, json.dumps(details) if details else None, self.dte_mode])
        except Exception as e:
            logger.debug(f"Failed to log to database: {e}")

    def update_heartbeat(self, status: str, action: str) -> None:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
                    VALUES (%s, NOW(), %s, 1, %s)
                    ON CONFLICT (bot_name) DO UPDATE SET
                        last_heartbeat = NOW(),
                        status = EXCLUDED.status,
                        scan_count = bot_heartbeats.scan_count + 1,
                        details = EXCLUDED.details
                """, [self.bot_name, status, json.dumps({"last_action": action})])
        except Exception as e:
            logger.debug(f"Failed to update heartbeat: {e}")

    def get_heartbeat_info(self) -> Optional[Dict[str, Any]]:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT scan_count, last_heartbeat, status, details
                    FROM bot_heartbeats WHERE bot_name = %s
                """, [self.bot_name])
                row = c.fetchone()
                if row:
                    return {
                        'scan_count': row[0] or 0,
                        'last_heartbeat': row[1].isoformat() if row[1] else None,
                        'status': row[2],
                        'details': row[3],
                    }
        except Exception as e:
            logger.debug(f"Failed to get heartbeat info: {e}")
        return None

    def update_daily_performance(self, summary: DailySummary) -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    INSERT INTO {self._t('daily_perf')} (trade_date, trades_executed, positions_closed, realized_pnl)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (trade_date) DO UPDATE SET
                        trades_executed = {self._t('daily_perf')}.trades_executed + EXCLUDED.trades_executed,
                        positions_closed = {self._t('daily_perf')}.positions_closed + EXCLUDED.positions_closed,
                        realized_pnl = {self._t('daily_perf')}.realized_pnl + EXCLUDED.realized_pnl
                """, [summary.date, summary.trades_executed, summary.positions_closed, summary.realized_pnl])
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to update daily perf: {e}")
            return False

    def save_equity_snapshot(self, balance: float, realized_pnl: float = 0,
                             unrealized_pnl: float = 0, open_positions: int = 0,
                             note: str = "") -> bool:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    INSERT INTO {self._t('equity_snapshots')}
                    (snapshot_time, balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
                    VALUES (NOW(), %s, %s, %s, %s, %s, %s)
                """, [balance, realized_pnl, unrealized_pnl, open_positions, note, self.dte_mode])
                return True
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to save equity snapshot: {e}")
            return False

    def get_current_balance(self) -> float:
        return self.get_paper_account().balance

    # =========================================================================
    # TRADE HISTORY & PERFORMANCE
    # =========================================================================

    def get_closed_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        trades = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT
                        position_id, ticker, expiration,
                        put_short_strike, put_long_strike,
                        call_short_strike, call_long_strike,
                        contracts, spread_width, total_credit,
                        close_price, close_reason, realized_pnl,
                        open_time, close_time,
                        underlying_at_entry, vix_at_entry,
                        wings_adjusted, original_put_width, original_call_width
                    FROM {self._t('positions')}
                    WHERE status IN ('closed', 'expired') AND dte_mode = %s
                    ORDER BY close_time DESC LIMIT %s
                """, [self.dte_mode, limit])

                for row in c.fetchall():
                    put_width = float(row[3]) - float(row[4])
                    call_width = float(row[6]) - float(row[5])
                    trades.append({
                        'position_id': row[0], 'ticker': row[1],
                        'expiration': str(row[2]),
                        'put_short_strike': float(row[3]),
                        'put_long_strike': float(row[4]),
                        'call_short_strike': float(row[5]),
                        'call_long_strike': float(row[6]),
                        'contracts': int(row[7]),
                        'spread_width': float(row[8]),
                        'total_credit': float(row[9]),
                        'close_price': float(row[10] or 0),
                        'close_reason': row[11] or '',
                        'realized_pnl': float(row[12] or 0),
                        'open_time': row[13].isoformat() if row[13] else None,
                        'close_time': row[14].isoformat() if row[14] else None,
                        'underlying_at_entry': float(row[15]),
                        'vix_at_entry': float(row[16] or 0),
                        'wings_adjusted': bool(row[17]),
                        'original_put_width': float(row[18] or 0),
                        'original_call_width': float(row[19] or 0),
                        'put_width': put_width, 'call_width': call_width,
                        'wings_symmetric': abs(put_width - call_width) < 0.01,
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get closed trades: {e}")
        return trades

    def get_performance_stats(self) -> Dict[str, Any]:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                        COALESCE(SUM(realized_pnl), 0) as total_pnl,
                        COALESCE(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
                        COALESCE(AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END), 0) as avg_loss,
                        COALESCE(MAX(realized_pnl), 0) as best_trade,
                        COALESCE(MIN(realized_pnl), 0) as worst_trade
                    FROM {self._t('positions')}
                    WHERE status IN ('closed', 'expired')
                    AND realized_pnl IS NOT NULL AND dte_mode = %s
                """, [self.dte_mode])
                row = c.fetchone()
                if row:
                    total = int(row[0])
                    wins = int(row[1])
                    win_rate = (wins / total * 100) if total > 0 else 0
                    return {
                        'total_trades': total, 'wins': wins,
                        'losses': int(row[2]),
                        'win_rate': round(win_rate, 1),
                        'total_pnl': round(float(row[3]), 2),
                        'avg_win': round(float(row[4]), 2),
                        'avg_loss': round(float(row[5]), 2),
                        'best_trade': round(float(row[6]), 2),
                        'worst_trade': round(float(row[7]), 2),
                    }
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get performance stats: {e}")
        return {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'total_pnl': 0, 'avg_win': 0, 'avg_loss': 0,
            'best_trade': 0, 'worst_trade': 0,
        }

    def get_equity_curve(self) -> List[Dict[str, Any]]:
        curve = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT starting_capital FROM {self._t('paper_account')}
                    WHERE is_active = TRUE AND dte_mode = %s LIMIT 1
                """, [self.dte_mode])
                row = c.fetchone()
                starting_capital = float(row[0]) if row else 10000.0

                c.execute(f"""
                    SELECT close_time, realized_pnl,
                           SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
                    FROM {self._t('positions')}
                    WHERE status IN ('closed', 'expired')
                    AND realized_pnl IS NOT NULL AND close_time IS NOT NULL
                    AND dte_mode = %s
                    ORDER BY close_time
                """, [self.dte_mode])

                for row in c.fetchall():
                    curve.append({
                        'timestamp': row[0].isoformat() if row[0] else None,
                        'pnl': round(float(row[1]), 2),
                        'cumulative_pnl': round(float(row[2]), 2),
                        'equity': round(starting_capital + float(row[2]), 2),
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get equity curve: {e}")
        return curve

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        logs = []
        try:
            with db_connection() as conn:
                c = conn.cursor()
                c.execute(f"""
                    SELECT log_time, level, message, details
                    FROM {self._t('logs')}
                    WHERE dte_mode = %s ORDER BY log_time DESC LIMIT %s
                """, [self.dte_mode, limit])
                for row in c.fetchall():
                    logs.append({
                        'timestamp': row[0].isoformat() if row[0] else None,
                        'level': row[1], 'message': row[2], 'details': row[3],
                    })
        except Exception as e:
            logger.error(f"{self.bot_name}: Failed to get logs: {e}")
        return logs
