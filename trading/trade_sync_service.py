"""
Trade Synchronization Service
=============================

Handles critical trade lifecycle synchronization across all bots:
1. Stale Position Cleanup - Auto-close expired positions
2. Missing P&L Fix - Calculate and fill missing realized_pnl
3. Cross-Bot Sync - Sync bot tables to unified tables
4. Atomic Operations - Race-condition-free position closes

This service runs:
- On scheduler startup
- Every 30 minutes during market hours
- On-demand via API endpoint

Author: AlphaGEX Trading System
"""

import logging
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple
from zoneinfo import ZoneInfo
from contextlib import contextmanager

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Bot configurations: (positions_table, bot_name, has_iron_condor)
BOT_CONFIGS = {
    'ares': {
        'table': 'ares_positions',
        'name': 'ARES',
        'type': 'iron_condor',
        'credit_field': 'total_credit',
        'has_legs': True
    },
    'athena': {
        'table': 'athena_positions',
        'name': 'ATHENA',
        'type': 'directional',
        'credit_field': 'entry_price',
        'has_legs': False
    },
    'titan': {
        'table': 'titan_positions',
        'name': 'TITAN',
        'type': 'iron_condor',
        'credit_field': 'entry_credit',
        'has_legs': True
    },
    'pegasus': {
        'table': 'pegasus_positions',
        'name': 'PEGASUS',
        'type': 'iron_condor',
        'credit_field': 'entry_credit',
        'has_legs': True
    },
    'icarus': {
        'table': 'icarus_positions',
        'name': 'ICARUS',
        'type': 'directional',
        'credit_field': 'entry_price',
        'has_legs': False
    }
}


@contextmanager
def get_db_connection():
    """Get database connection with proper cleanup"""
    conn = None
    try:
        from database_adapter import get_connection
        conn = get_connection()
        yield conn
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


class TradeSyncService:
    """
    Centralized trade synchronization service.

    Addresses:
    - Stale positions (expired but still 'open')
    - Missing P&L values on closed positions
    - Cross-bot sync to unified tables
    - Race conditions in position closes
    """

    def __init__(self):
        self.results = {
            'stale_cleaned': 0,
            'pnl_fixed': 0,
            'synced_to_unified': 0,
            'errors': []
        }

    # =========================================================================
    # 1. STALE POSITION CLEANUP
    # =========================================================================

    def cleanup_stale_positions(self) -> Dict[str, Any]:
        """
        Find and close expired positions that are still marked as 'open'.

        This handles cases where:
        - EOD job failed to run
        - Position expiration was missed
        - Server restart interrupted EOD processing

        Returns:
            Dict with cleanup results per bot
        """
        logger.info("TradeSyncService: Starting stale position cleanup")
        results = {
            'total_cleaned': 0,
            'by_bot': {},
            'errors': []
        }

        today = datetime.now(CENTRAL_TZ).date()

        for bot_key, config in BOT_CONFIGS.items():
            try:
                cleaned = self._cleanup_bot_stale_positions(
                    config['table'],
                    config['name'],
                    config['credit_field'],
                    config['type'],
                    today
                )
                results['by_bot'][config['name']] = cleaned
                results['total_cleaned'] += cleaned['count']
            except Exception as e:
                error_msg = f"{config['name']}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"Stale cleanup failed for {config['name']}: {e}")

        logger.info(f"TradeSyncService: Cleaned {results['total_cleaned']} stale positions")
        return results

    def _cleanup_bot_stale_positions(
        self,
        table: str,
        bot_name: str,
        credit_field: str,
        position_type: str,
        today: date
    ) -> Dict[str, Any]:
        """Clean stale positions for a specific bot"""
        result = {'count': 0, 'positions': []}

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Find stale positions (expired but still open)
            cursor.execute(f"""
                SELECT position_id, expiration, {credit_field}, contracts
                FROM {table}
                WHERE status = 'open'
                AND expiration IS NOT NULL
                AND expiration < %s
            """, (today,))

            stale_positions = cursor.fetchall()

            for pos in stale_positions:
                position_id, expiration, credit, contracts = pos

                # Calculate realized P&L for expired position
                # For expired 0DTE options that finished OTM, we keep full credit
                credit_val = float(credit) if credit else 0
                num_contracts = int(contracts) if contracts else 1
                realized_pnl = credit_val * 100 * num_contracts  # Full credit as profit

                # Update to expired status with atomic transaction
                cursor.execute(f"""
                    UPDATE {table}
                    SET status = 'expired',
                        close_time = %s,
                        close_reason = 'STALE_CLEANUP',
                        realized_pnl = COALESCE(realized_pnl, %s)
                    WHERE position_id = %s
                    AND status = 'open'
                """, (
                    datetime.now(CENTRAL_TZ),
                    realized_pnl,
                    position_id
                ))

                if cursor.rowcount > 0:
                    result['count'] += 1
                    result['positions'].append({
                        'position_id': position_id,
                        'expiration': str(expiration),
                        'realized_pnl': realized_pnl
                    })
                    logger.info(f"{bot_name}: Cleaned stale position {position_id} (expired {expiration})")

            conn.commit()

        return result

    # =========================================================================
    # 2. MISSING P&L FIX
    # =========================================================================

    def fix_missing_pnl(self) -> Dict[str, Any]:
        """
        Find and fix closed/expired positions that have NULL realized_pnl.

        Calculates P&L based on:
        - Entry credit and close price (if available)
        - Entry credit only (assume full profit for expired OTM)

        Returns:
            Dict with fix results per bot
        """
        logger.info("TradeSyncService: Starting missing P&L fix")
        results = {
            'total_fixed': 0,
            'by_bot': {},
            'errors': []
        }

        for bot_key, config in BOT_CONFIGS.items():
            try:
                fixed = self._fix_bot_missing_pnl(
                    config['table'],
                    config['name'],
                    config['credit_field'],
                    config['type']
                )
                results['by_bot'][config['name']] = fixed
                results['total_fixed'] += fixed['count']
            except Exception as e:
                error_msg = f"{config['name']}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"P&L fix failed for {config['name']}: {e}")

        logger.info(f"TradeSyncService: Fixed {results['total_fixed']} positions with missing P&L")
        return results

    def _fix_bot_missing_pnl(
        self,
        table: str,
        bot_name: str,
        credit_field: str,
        position_type: str
    ) -> Dict[str, Any]:
        """Fix missing P&L for a specific bot"""
        result = {'count': 0, 'positions': []}

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Find closed/expired positions with NULL realized_pnl
            cursor.execute(f"""
                SELECT position_id, status, {credit_field}, contracts, close_price
                FROM {table}
                WHERE status IN ('closed', 'expired')
                AND realized_pnl IS NULL
            """)

            positions_to_fix = cursor.fetchall()

            for pos in positions_to_fix:
                position_id, status, credit, contracts, close_price = pos

                credit_val = float(credit) if credit else 0
                num_contracts = int(contracts) if contracts else 1
                close_price_val = float(close_price) if close_price else 0

                # Calculate realized P&L
                if status == 'expired':
                    # Expired OTM = full credit as profit
                    realized_pnl = credit_val * 100 * num_contracts
                elif close_price_val > 0:
                    # Closed with known close price
                    # P&L = (entry_credit - close_price) * 100 * contracts
                    realized_pnl = (credit_val - close_price_val) * 100 * num_contracts
                else:
                    # Closed without close price - estimate based on entry credit
                    # Assume partial profit (50% of credit)
                    realized_pnl = credit_val * 100 * num_contracts * 0.5

                # Update with calculated P&L
                cursor.execute(f"""
                    UPDATE {table}
                    SET realized_pnl = %s
                    WHERE position_id = %s
                    AND realized_pnl IS NULL
                """, (round(realized_pnl, 2), position_id))

                if cursor.rowcount > 0:
                    result['count'] += 1
                    result['positions'].append({
                        'position_id': position_id,
                        'status': status,
                        'calculated_pnl': round(realized_pnl, 2)
                    })
                    logger.info(f"{bot_name}: Fixed P&L for {position_id} = ${realized_pnl:.2f}")

            conn.commit()

        return result

    # =========================================================================
    # 3. CROSS-BOT SYNC TO UNIFIED TABLES
    # =========================================================================

    def sync_to_unified_tables(self) -> Dict[str, Any]:
        """
        Sync bot-specific positions to unified tracking tables.

        Ensures:
        - autonomous_open_positions has all open positions
        - autonomous_closed_trades has all closed positions
        - unified_trades has complete trade history

        Returns:
            Dict with sync results
        """
        logger.info("TradeSyncService: Starting cross-bot sync to unified tables")
        results = {
            'open_synced': 0,
            'closed_synced': 0,
            'by_bot': {},
            'errors': []
        }

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Ensure unified tables exist
            self._ensure_unified_tables_exist(cursor)
            conn.commit()

            for bot_key, config in BOT_CONFIGS.items():
                try:
                    synced = self._sync_bot_to_unified(
                        cursor,
                        config['table'],
                        config['name'],
                        config['credit_field']
                    )
                    results['by_bot'][config['name']] = synced
                    results['open_synced'] += synced.get('open_synced', 0)
                    results['closed_synced'] += synced.get('closed_synced', 0)
                except Exception as e:
                    error_msg = f"{config['name']}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(f"Sync failed for {config['name']}: {e}")

            conn.commit()

        logger.info(f"TradeSyncService: Synced {results['open_synced']} open, {results['closed_synced']} closed to unified tables")
        return results

    def _ensure_unified_tables_exist(self, cursor):
        """Ensure unified tracking tables exist with proper schema"""
        # Create autonomous_open_positions if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_open_positions (
                id SERIAL PRIMARY KEY,
                position_id VARCHAR(100) UNIQUE,
                bot VARCHAR(50),
                symbol VARCHAR(20),
                strategy VARCHAR(50),
                entry_time TIMESTAMP WITH TIME ZONE,
                entry_price DECIMAL(12, 4),
                contracts INTEGER DEFAULT 1,
                current_price DECIMAL(12, 4),
                unrealized_pnl DECIMAL(12, 2),
                status VARCHAR(20) DEFAULT 'open',
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Create autonomous_closed_trades if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_closed_trades (
                id SERIAL PRIMARY KEY,
                position_id VARCHAR(100),
                bot VARCHAR(50),
                symbol VARCHAR(20),
                strategy VARCHAR(50),
                entry_time TIMESTAMP WITH TIME ZONE,
                exit_time TIMESTAMP WITH TIME ZONE,
                entry_price DECIMAL(12, 4),
                exit_price DECIMAL(12, 4),
                contracts INTEGER DEFAULT 1,
                realized_pnl DECIMAL(12, 2),
                exit_reason VARCHAR(100),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Add indexes for performance
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_unified_open_bot ON autonomous_open_positions(bot)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_unified_open_status ON autonomous_open_positions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_unified_closed_bot ON autonomous_closed_trades(bot)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_unified_closed_exit ON autonomous_closed_trades(exit_time)")
        except Exception:
            pass  # Indexes may already exist

    def _sync_bot_to_unified(
        self,
        cursor,
        table: str,
        bot_name: str,
        credit_field: str
    ) -> Dict[str, int]:
        """Sync a single bot's positions to unified tables"""
        result = {'open_synced': 0, 'closed_synced': 0}

        # Sync open positions
        cursor.execute(f"""
            SELECT position_id, 'SPY' as symbol, open_time, {credit_field}, contracts
            FROM {table}
            WHERE status = 'open'
        """)
        open_positions = cursor.fetchall()

        for pos in open_positions:
            position_id, symbol, entry_time, entry_price, contracts = pos

            # Upsert into unified open positions
            cursor.execute("""
                INSERT INTO autonomous_open_positions
                (position_id, bot, symbol, strategy, entry_time, entry_price, contracts, status, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', NOW())
                ON CONFLICT (position_id)
                DO UPDATE SET
                    status = 'open',
                    last_updated = NOW()
            """, (
                str(position_id),
                bot_name,
                symbol,
                f"{bot_name}_TRADE",
                entry_time,
                float(entry_price) if entry_price else 0,
                int(contracts) if contracts else 1
            ))
            result['open_synced'] += 1

        # Sync closed/expired positions (last 7 days only to avoid duplicates)
        # Use COALESCE to handle legacy data with NULL close_time
        cursor.execute(f"""
            SELECT position_id, 'SPY' as symbol, open_time, close_time,
                   {credit_field}, close_price, contracts, realized_pnl, close_reason
            FROM {table}
            WHERE status IN ('closed', 'expired')
            AND COALESCE(close_time, open_time) >= NOW() - INTERVAL '7 days'
        """)
        closed_positions = cursor.fetchall()

        for pos in closed_positions:
            (position_id, symbol, entry_time, exit_time,
             entry_price, exit_price, contracts, realized_pnl, exit_reason) = pos

            # Check if already synced
            cursor.execute("""
                SELECT 1 FROM autonomous_closed_trades
                WHERE position_id = %s AND bot = %s
            """, (str(position_id), bot_name))

            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO autonomous_closed_trades
                    (position_id, bot, symbol, strategy, entry_time, exit_time,
                     entry_price, exit_price, contracts, realized_pnl, exit_reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    str(position_id),
                    bot_name,
                    symbol,
                    f"{bot_name}_TRADE",
                    entry_time,
                    exit_time,
                    float(entry_price) if entry_price else 0,
                    float(exit_price) if exit_price else 0,
                    int(contracts) if contracts else 1,
                    float(realized_pnl) if realized_pnl else 0,
                    exit_reason or 'UNKNOWN'
                ))
                result['closed_synced'] += 1

        # Remove from unified open if closed in bot table
        cursor.execute("""
            DELETE FROM autonomous_open_positions
            WHERE bot = %s
            AND position_id NOT IN (
                SELECT position_id::text FROM """ + table + """ WHERE status = 'open'
            )
        """, (bot_name,))

        return result

    # =========================================================================
    # 4. ATOMIC POSITION CLOSE (Race Condition Prevention)
    # =========================================================================

    def close_position_atomically(
        self,
        bot_key: str,
        position_id: str,
        close_price: float,
        realized_pnl: float,
        close_reason: str
    ) -> Dict[str, Any]:
        """
        Close a position atomically with proper locking to prevent race conditions.

        Uses SELECT FOR UPDATE to lock the row during the close operation.

        Args:
            bot_key: Bot identifier (ares, athena, titan, pegasus, icarus)
            position_id: Position to close
            close_price: Exit price
            realized_pnl: Calculated P&L
            close_reason: Reason for closing

        Returns:
            Dict with close result
        """
        if bot_key not in BOT_CONFIGS:
            return {'success': False, 'error': f'Unknown bot: {bot_key}'}

        config = BOT_CONFIGS[bot_key]
        table = config['table']
        bot_name = config['name']

        with get_db_connection() as conn:
            cursor = conn.cursor()

            try:
                # Start transaction and lock the row
                cursor.execute(f"""
                    SELECT position_id, status, {config['credit_field']}, contracts
                    FROM {table}
                    WHERE position_id = %s
                    FOR UPDATE NOWAIT
                """, (position_id,))

                row = cursor.fetchone()

                if not row:
                    return {'success': False, 'error': 'Position not found'}

                current_status = row[1]
                if current_status != 'open':
                    return {
                        'success': False,
                        'error': f'Position already {current_status}',
                        'current_status': current_status
                    }

                # Close the position atomically
                now = datetime.now(CENTRAL_TZ)
                cursor.execute(f"""
                    UPDATE {table}
                    SET status = 'closed',
                        close_time = %s,
                        close_price = %s,
                        realized_pnl = %s,
                        close_reason = %s
                    WHERE position_id = %s
                    AND status = 'open'
                """, (now, close_price, realized_pnl, close_reason, position_id))

                if cursor.rowcount == 0:
                    conn.rollback()
                    return {'success': False, 'error': 'Position was modified by another process'}

                # Also update unified tables
                cursor.execute("""
                    UPDATE autonomous_open_positions
                    SET status = 'closed', last_updated = NOW()
                    WHERE position_id = %s
                """, (str(position_id),))

                conn.commit()

                logger.info(f"{bot_name}: Atomically closed position {position_id} with P&L ${realized_pnl:.2f}")

                return {
                    'success': True,
                    'position_id': position_id,
                    'bot': bot_name,
                    'realized_pnl': realized_pnl,
                    'close_reason': close_reason,
                    'close_time': now.isoformat()
                }

            except Exception as e:
                conn.rollback()
                error_msg = str(e)

                # Handle lock conflict (another process has the row)
                if 'could not obtain lock' in error_msg.lower():
                    return {
                        'success': False,
                        'error': 'Position is being modified by another process',
                        'retry': True
                    }

                logger.error(f"Atomic close failed for {position_id}: {e}")
                return {'success': False, 'error': error_msg}

    # =========================================================================
    # COMBINED SYNC OPERATIONS
    # =========================================================================

    def run_full_sync(self) -> Dict[str, Any]:
        """
        Run all sync operations in sequence.

        Order:
        1. Cleanup stale positions (expired but open)
        2. Fix missing P&L values
        3. Sync to unified tables

        Returns:
            Combined results from all operations
        """
        logger.info("TradeSyncService: Starting full sync")
        start_time = datetime.now(CENTRAL_TZ)

        results = {
            'stale_cleanup': None,
            'pnl_fix': None,
            'unified_sync': None,
            'total_errors': [],
            'duration_seconds': 0
        }

        # 1. Cleanup stale positions
        try:
            results['stale_cleanup'] = self.cleanup_stale_positions()
            results['total_errors'].extend(results['stale_cleanup'].get('errors', []))
        except Exception as e:
            results['total_errors'].append(f"Stale cleanup failed: {e}")
            logger.error(f"Stale cleanup failed: {e}")

        # 2. Fix missing P&L
        try:
            results['pnl_fix'] = self.fix_missing_pnl()
            results['total_errors'].extend(results['pnl_fix'].get('errors', []))
        except Exception as e:
            results['total_errors'].append(f"P&L fix failed: {e}")
            logger.error(f"P&L fix failed: {e}")

        # 3. Sync to unified tables
        try:
            results['unified_sync'] = self.sync_to_unified_tables()
            results['total_errors'].extend(results['unified_sync'].get('errors', []))
        except Exception as e:
            results['total_errors'].append(f"Unified sync failed: {e}")
            logger.error(f"Unified sync failed: {e}")

        end_time = datetime.now(CENTRAL_TZ)
        results['duration_seconds'] = (end_time - start_time).total_seconds()

        logger.info(f"TradeSyncService: Full sync completed in {results['duration_seconds']:.2f}s")

        return results


# Singleton instance
_sync_service = None

def get_sync_service() -> TradeSyncService:
    """Get the singleton trade sync service instance"""
    global _sync_service
    if _sync_service is None:
        _sync_service = TradeSyncService()
    return _sync_service


# Convenience functions for direct use
def cleanup_stale_positions() -> Dict[str, Any]:
    """Cleanup stale positions across all bots"""
    return get_sync_service().cleanup_stale_positions()


def fix_missing_pnl() -> Dict[str, Any]:
    """Fix missing P&L values across all bots"""
    return get_sync_service().fix_missing_pnl()


def sync_to_unified() -> Dict[str, Any]:
    """Sync all bot positions to unified tables"""
    return get_sync_service().sync_to_unified_tables()


def run_full_sync() -> Dict[str, Any]:
    """Run complete sync operation"""
    return get_sync_service().run_full_sync()


def close_position_atomically(bot_key: str, position_id: str, close_price: float,
                               realized_pnl: float, close_reason: str) -> Dict[str, Any]:
    """Close a position atomically (race-condition safe)"""
    return get_sync_service().close_position_atomically(
        bot_key, position_id, close_price, realized_pnl, close_reason
    )
