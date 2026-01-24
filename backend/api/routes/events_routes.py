"""
Trading Events Routes - Auto-detected events for equity curve visualization
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo
import json
import logging

logger = logging.getLogger(__name__)

# Import database adapter
try:
    from database_adapter import get_connection
except ImportError:
    from ...database_adapter import get_connection

# Import MTM functions for unrealized P&L calculation
MTM_IC_AVAILABLE = False
MTM_SPREAD_AVAILABLE = False
try:
    from core.mark_to_market import calculate_ic_mark_to_market
    MTM_IC_AVAILABLE = True
except ImportError:
    calculate_ic_mark_to_market = None

try:
    from core.mark_to_market import calculate_spread_mark_to_market
    MTM_SPREAD_AVAILABLE = True
except ImportError:
    calculate_spread_mark_to_market = None

router = APIRouter(prefix="/api/events", tags=["Events"])


# ============================================================================
# CAPITAL FETCHERS FOR BOTS
# ============================================================================

def _get_ares_capital() -> float:
    """
    Get ARES starting capital from database config.

    CRITICAL: Do NOT use Tradier balance as starting capital!
    Tradier balance = starting_capital + all P&L (double-counting issue).
    Starting capital is the FIXED amount the bot started with.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT value FROM autonomous_config
            WHERE key = 'ares_starting_capital'
        ''')
        row = cursor.fetchone()
        conn.close()

        if row and float(row[0]) > 0:
            return float(row[0])

        # Default fallback - NEVER use Tradier balance here
        return 100000

    except Exception as e:
        logger.warning(f"Could not fetch ARES capital: {e}")
        return 100000


def _get_bot_capital(bot_name: str) -> float:
    """
    Get starting capital for a bot.

    - ARES: Fetched from Tradier sandbox account (real money)
    - ATHENA: $100,000 paper trading capital
    - ICARUS: $100,000 paper trading (aggressive ATHENA clone)
    - PEGASUS: $200,000 paper trading SPX
    - TITAN: $200,000 paper trading (aggressive PEGASUS clone)
    """
    if not bot_name:
        return 200000

    bot_upper = bot_name.upper()

    if bot_upper == 'ARES':
        return _get_ares_capital()
    elif bot_upper == 'ATHENA':
        return 100000  # Paper trading
    elif bot_upper == 'ICARUS':
        return 100000  # Paper trading - aggressive ATHENA clone
    elif bot_upper == 'PEGASUS':
        return 200000  # Paper trading SPX
    elif bot_upper == 'TITAN':
        return 200000  # Paper trading SPX - aggressive PEGASUS clone
    else:
        return 200000  # Default


# ============================================================================
# DATABASE SETUP
# ============================================================================

def ensure_events_table():
    """Create the trading_events table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_events (
            id SERIAL PRIMARY KEY,
            event_date DATE NOT NULL,
            event_time TIMESTAMPTZ DEFAULT NOW(),
            event_type TEXT NOT NULL,
            bot_name TEXT,
            severity TEXT DEFAULT 'info',
            title TEXT NOT NULL,
            description TEXT,
            value REAL,
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Create index for fast date range queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trading_events_date
        ON trading_events(event_date)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trading_events_type
        ON trading_events(event_type)
    ''')

    # Create unique constraint for deduplication
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trading_events_unique
        ON trading_events(event_date, event_type, COALESCE(bot_name, ''), COALESCE(value::text, ''))
    ''')

    conn.commit()
    conn.close()

# Ensure table exists on module load
try:
    ensure_events_table()
except Exception as e:
    print(f"Warning: Could not create trading_events table: {e}")

# ============================================================================
# EVENT DETECTION LOGIC
# ============================================================================

def detect_events_from_trades(days: int = 90, bot_filter: str = None) -> List[dict]:
    """
    Auto-detect trading events from historical trade data.

    IMPORTANT: V2 bots (ARES, ATHENA, PEGASUS) store trades in their own tables.
    This function reads from the correct table based on the bot filter.

    Detects:
    - New equity highs
    - Winning streaks (3+)
    - Losing streaks (3+)
    - Max drawdown events
    - Model version changes
    - VIX spikes (>25)
    - Circuit breaker triggers
    - Large trades (>2x average)
    """
    conn = get_connection()
    cursor = conn.cursor()
    events = []

    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # V2 bot table mapping
        v2_bot_tables = {
            'ARES': 'ares_positions',
            'ATHENA': 'athena_positions',
            'PEGASUS': 'pegasus_positions'
        }

        trades = []

        if bot_filter and bot_filter.upper() in v2_bot_tables:
            # Query V2 bot-specific table
            table_name = v2_bot_tables[bot_filter.upper()]
            bot_upper = bot_filter.upper()

            cursor.execute(f'''
                SELECT
                    DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') as exit_date,
                    close_time as exit_time,
                    realized_pnl,
                    %s as strategy,
                    ticker as symbol,
                    vix_at_entry as entry_vix,
                    vix_at_entry as exit_vix,
                    gex_regime
                FROM {table_name}
                WHERE status IN ('closed', 'expired', 'partial_close')
                AND close_time IS NOT NULL
                AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') >= %s
                ORDER BY close_time ASC
            ''', [bot_upper, start_date])

            trades = cursor.fetchall()

            # Fall back to legacy table if no V2 data
            if not trades:
                params = [start_date, f'%{bot_filter}%']
                cursor.execute(f'''
                    SELECT
                        exit_date,
                        exit_time,
                        realized_pnl,
                        strategy,
                        symbol,
                        entry_vix,
                        exit_vix,
                        gex_regime
                    FROM autonomous_closed_trades
                    WHERE exit_date >= %s AND strategy ILIKE %s
                    ORDER BY exit_date ASC, exit_time ASC
                ''', params)
                trades = cursor.fetchall()
        else:
            # Use legacy unified table
            params = [start_date]
            bot_clause = ""
            if bot_filter:
                bot_clause = "AND strategy ILIKE %s"
                params.append(f'%{bot_filter}%')

            cursor.execute(f'''
                SELECT
                    exit_date,
                    exit_time,
                    realized_pnl,
                    strategy,
                    symbol,
                    entry_vix,
                    exit_vix,
                    gex_regime
                FROM autonomous_closed_trades
                WHERE exit_date >= %s {bot_clause}
                ORDER BY exit_date ASC, exit_time ASC
            ''', params)

            trades = cursor.fetchall()

        if not trades:
            return events

        # Track metrics for event detection
        cumulative_pnl = 0
        high_water_mark = 0
        max_drawdown = 0
        consecutive_wins = 0
        consecutive_losses = 0
        avg_pnl = 0
        pnl_list = []

        for i, trade in enumerate(trades):
            exit_date, exit_time, pnl, strategy, symbol, entry_vix, exit_vix, gex_regime = trade
            pnl = pnl or 0

            cumulative_pnl += pnl
            pnl_list.append(pnl)
            avg_pnl = sum(pnl_list) / len(pnl_list) if pnl_list else 0

            # Ensure date is a string for consistent sorting
            date_str = str(exit_date) if exit_date else None

            # New equity high
            if cumulative_pnl > high_water_mark:
                if high_water_mark > 0:  # Not the first trade
                    events.append({
                        'date': date_str,
                        'type': 'new_high',
                        'severity': 'success',
                        'title': 'New Equity High',
                        'description': f'Cumulative P&L reached ${cumulative_pnl:,.0f}',
                        'value': cumulative_pnl,
                        'bot': strategy
                    })
                high_water_mark = cumulative_pnl
                max_drawdown = 0

            # Drawdown tracking
            if high_water_mark > 0:
                current_dd = (high_water_mark - cumulative_pnl) / high_water_mark * 100
                if current_dd > max_drawdown and current_dd > 5:
                    max_drawdown = current_dd
                    events.append({
                        'date': date_str,
                        'type': 'drawdown',
                        'severity': 'warning',
                        'title': 'Max Drawdown',
                        'description': f'Drawdown reached {current_dd:.1f}%',
                        'value': current_dd,
                        'bot': strategy
                    })

            # Streak tracking
            if pnl > 0:
                consecutive_wins += 1
                consecutive_losses = 0
                if consecutive_wins == 3:
                    events.append({
                        'date': date_str,
                        'type': 'winning_streak',
                        'severity': 'success',
                        'title': 'Winning Streak',
                        'description': f'{consecutive_wins} consecutive wins',
                        'value': consecutive_wins,
                        'bot': strategy
                    })
            else:
                consecutive_losses += 1
                consecutive_wins = 0
                if consecutive_losses == 3:
                    events.append({
                        'date': date_str,
                        'type': 'losing_streak',
                        'severity': 'danger',
                        'title': 'Losing Streak',
                        'description': f'{consecutive_losses} consecutive losses',
                        'value': consecutive_losses,
                        'bot': strategy
                    })

            # Large trade detection (>2x average after we have enough data)
            # Guard against division by zero when avg_pnl is 0
            if len(pnl_list) > 5 and avg_pnl != 0 and abs(pnl) > abs(avg_pnl) * 2:
                multiplier = abs(pnl / avg_pnl)
                if pnl > 0:
                    events.append({
                        'date': date_str,
                        'type': 'big_win',
                        'severity': 'success',
                        'title': 'Large Win',
                        'description': f'+${pnl:,.0f} ({multiplier:.1f}x average)',
                        'value': pnl,
                        'bot': strategy
                    })
                else:
                    events.append({
                        'date': date_str,
                        'type': 'big_loss',
                        'severity': 'danger',
                        'title': 'Large Loss',
                        'description': f'-${abs(pnl):,.0f} ({multiplier:.1f}x average)',
                        'value': pnl,
                        'bot': strategy
                    })

            # VIX spike detection
            vix = exit_vix or entry_vix
            if vix and vix > 25:
                # Check if we already have a VIX event for this date
                if not any(e['date'] == date_str and e['type'] == 'vix_spike' for e in events):
                    events.append({
                        'date': date_str,
                        'type': 'vix_spike',
                        'severity': 'warning',
                        'title': 'VIX Spike',
                        'description': f'VIX at {vix:.1f}',
                        'value': vix,
                        'bot': None
                    })

        # Check for model version changes from oracle_bot_interactions
        try:
            cursor.execute('''
                SELECT DISTINCT
                    DATE(timestamp) as event_date,
                    model_version,
                    bot_name
                FROM oracle_bot_interactions
                WHERE timestamp >= %s
                AND model_version IS NOT NULL
                ORDER BY event_date
            ''', (start_date,))

            versions = cursor.fetchall()
            last_version = {}

            for event_date, version, bot in versions:
                key = bot or 'ORACLE'
                if key in last_version and last_version[key] != version:
                    events.append({
                        'date': str(event_date),
                        'type': 'model_change',
                        'severity': 'info',
                        'title': 'Model Version Change',
                        'description': f'{key}: v{last_version[key]} → v{version}',
                        'value': None,
                        'bot': bot
                    })
                last_version[key] = version
        except Exception as e:
            print(f"Could not check model versions: {e}")

        # Check for circuit breaker events
        try:
            cursor.execute('''
                SELECT
                    DATE(timestamp) as event_date,
                    trigger_event,
                    change_type
                FROM gex_change_log
                WHERE timestamp >= %s
                AND trigger_event ILIKE '%circuit%'
                ORDER BY timestamp
            ''', (start_date,))

            circuits = cursor.fetchall()
            for event_date, trigger, change_type in circuits:
                events.append({
                    'date': str(event_date),
                    'type': 'circuit_breaker',
                    'severity': 'warning',
                    'title': 'Circuit Breaker',
                    'description': trigger or 'Trading paused',
                    'value': None,
                    'bot': None
                })
        except Exception as e:
            print(f"Could not check circuit breakers: {e}")

        # Sort events by date
        events.sort(key=lambda x: x['date'])

        return events

    finally:
        conn.close()


def persist_events(events: List[dict]) -> dict:
    """
    Persist detected events to the database with deduplication.
    Uses INSERT ... ON CONFLICT DO NOTHING for idempotent upserts.

    Returns:
        dict with 'inserted' and 'skipped' counts
    """
    if not events:
        return {'inserted': 0, 'skipped': 0}

    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    try:
        for event in events:
            try:
                # Convert date to string if needed
                event_date = event.get('date')
                if hasattr(event_date, 'strftime'):
                    event_date = event_date.strftime('%Y-%m-%d')

                cursor.execute('''
                    INSERT INTO trading_events (
                        event_date, event_type, bot_name, severity,
                        title, description, value, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_date, event_type, COALESCE(bot_name, ''), COALESCE(value::text, ''))
                    DO NOTHING
                ''', (
                    event_date,
                    event.get('type'),
                    event.get('bot'),
                    event.get('severity', 'info'),
                    event.get('title'),
                    event.get('description'),
                    event.get('value'),
                    json.dumps(event.get('metadata')) if event.get('metadata') else None
                ))

                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1

            except Exception as e:
                print(f"Error persisting event: {e}")
                skipped += 1

        conn.commit()
        return {'inserted': inserted, 'skipped': skipped}

    finally:
        conn.close()


def get_persisted_events(days: int = 90, bot_filter: str = None, event_type: str = None) -> List[dict]:
    """
    Get events from the database (persisted events).
    Falls back to dynamic detection if no persisted events found.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = '''
            SELECT
                id, event_date, event_type, bot_name, severity,
                title, description, value, metadata, created_at
            FROM trading_events
            WHERE event_date >= %s
        '''
        params = [start_date]

        if bot_filter:
            query += " AND bot_name ILIKE %s"
            params.append(f'%{bot_filter}%')

        if event_type:
            query += " AND event_type = %s"
            params.append(event_type)

        query += " ORDER BY event_date ASC, created_at ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        events = []
        for row in rows:
            events.append({
                'id': row[0],
                'date': str(row[1]),
                'type': row[2],
                'bot': row[3],
                'severity': row[4],
                'title': row[5],
                'description': row[6],
                'value': row[7],
                'metadata': row[8],
                'created_at': str(row[9]) if row[9] else None,
                'persisted': True
            })

        return events

    finally:
        conn.close()


def sync_events(days: int = 90, bot_filter: str = None) -> dict:
    """
    Detect and persist events from trade data.
    This is the main sync function that should be called after trade closes.

    Returns:
        dict with sync results
    """
    # Detect events from trade data
    detected = detect_events_from_trades(days=days, bot_filter=bot_filter)

    # Persist to database
    result = persist_events(detected)

    return {
        'detected': len(detected),
        'inserted': result['inserted'],
        'skipped': result['skipped'],
        'timestamp': datetime.now().isoformat()
    }


def _calculate_bot_unrealized_pnl(cursor, bot_filter: str = None) -> float:
    """
    Calculate unrealized P&L from open positions for a specific bot.

    Uses MTM (mark-to-market) pricing when available, falls back to estimation.
    Handles both Iron Condor bots (ARES, TITAN, PEGASUS) and Directional bots (ATHENA, ICARUS).
    """
    if not bot_filter:
        return 0.0

    bot_filter_upper = bot_filter.upper()
    unrealized_pnl = 0.0

    # Bot-specific table and position structure mapping
    ic_bots = {'ARES': ('ares_positions', 'SPY'),
               'TITAN': ('titan_positions', 'SPX'),
               'PEGASUS': ('pegasus_positions', 'SPX')}

    directional_bots = {'ATHENA': ('athena_positions', 'SPY'),
                        'ICARUS': ('icarus_positions', 'SPY')}

    try:
        if bot_filter_upper in ic_bots:
            # Iron Condor bots
            table_name, underlying = ic_bots[bot_filter_upper]
            cursor.execute(f'''
                SELECT position_id, total_credit, contracts,
                       put_long_strike, put_short_strike,
                       call_short_strike, call_long_strike, expiration
                FROM {table_name}
                WHERE status = 'open'
            ''')
            open_positions = cursor.fetchall()

            if open_positions and MTM_IC_AVAILABLE and calculate_ic_mark_to_market:
                for pos in open_positions:
                    pos_id, total_credit, contracts, pl, ps, cs, cl, exp = pos
                    try:
                        exp_str = exp.strftime('%Y-%m-%d') if hasattr(exp, 'strftime') else str(exp)
                        mtm_result = calculate_ic_mark_to_market(
                            underlying=underlying,
                            expiration=exp_str,
                            put_short_strike=float(ps) if ps else 0,
                            put_long_strike=float(pl) if pl else 0,
                            call_short_strike=float(cs) if cs else 0,
                            call_long_strike=float(cl) if cl else 0,
                            contracts=int(contracts) if contracts else 1,
                            entry_credit=float(total_credit) if total_credit else 0
                        )
                        if mtm_result and mtm_result.get('success'):
                            unrealized_pnl += mtm_result.get('unrealized_pnl', 0) or 0
                    except Exception as e:
                        logger.debug(f"MTM calculation failed for {bot_filter_upper} position {pos_id}: {e}")

        elif bot_filter_upper in directional_bots:
            # Directional spread bots
            table_name, underlying = directional_bots[bot_filter_upper]
            cursor.execute(f'''
                SELECT position_id, spread_type, entry_debit, contracts,
                       long_strike, short_strike, expiration
                FROM {table_name}
                WHERE status = 'open'
            ''')
            open_positions = cursor.fetchall()

            if open_positions and MTM_SPREAD_AVAILABLE and calculate_spread_mark_to_market:
                for pos in open_positions:
                    pos_id, spread_type, entry_debit, contracts, long_strike, short_strike, exp = pos
                    try:
                        exp_str = exp.strftime('%Y-%m-%d') if hasattr(exp, 'strftime') else str(exp)
                        mtm_result = calculate_spread_mark_to_market(
                            underlying=underlying,
                            expiration=exp_str,
                            spread_type=spread_type or 'CALL',
                            long_strike=float(long_strike) if long_strike else 0,
                            short_strike=float(short_strike) if short_strike else 0,
                            contracts=int(contracts) if contracts else 1,
                            entry_debit=float(entry_debit) if entry_debit else 0
                        )
                        if mtm_result and mtm_result.get('success'):
                            unrealized_pnl += mtm_result.get('unrealized_pnl', 0) or 0
                    except Exception as e:
                        logger.debug(f"MTM calculation failed for {bot_filter_upper} position {pos_id}: {e}")

    except Exception as e:
        logger.warning(f"Error calculating unrealized P&L for {bot_filter}: {e}")

    return unrealized_pnl


def get_equity_curve_data(days: int = 90, bot_filter: str = None, timeframe: str = 'daily') -> List[dict]:
    """
    Get equity curve data from trades.

    For 'daily' timeframe: Returns individual trade points for granular charts
    For 'weekly'/'monthly': Returns aggregated data by period

    IMPORTANT: V2 bots (ARES, ATHENA, PEGASUS) store trades in their own tables,
    not in autonomous_closed_trades. This function reads from the correct table
    based on the bot filter to ensure proper equity curve synchronization.

    Args:
        days: Number of days of history
        bot_filter: Optional bot name filter (ARES, ATHENA, PEGASUS)
        timeframe: 'daily', 'weekly', or 'monthly'
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Bot-specific table mapping for V2 bots
        # Each V2 bot stores closed trades in its own positions table
        bot_tables = {
            'ARES': 'ares_positions',      # SPY Iron Condors - capital from Tradier
            'ATHENA': 'athena_positions',  # SPY Directional - $100k paper
            'ICARUS': 'icarus_positions',  # SPY Aggressive Directional - $100k paper
            'PEGASUS': 'pegasus_positions', # SPX Iron Condors - $200k paper
            'TITAN': 'titan_positions',    # SPX Aggressive Iron Condors - $200k paper
        }

        rows = []
        is_individual_trades = (timeframe == 'daily')  # For daily, get individual trades

        # Get starting capital dynamically (ARES fetches from Tradier)
        starting_capital = _get_bot_capital(bot_filter)

        if bot_filter and bot_filter.upper() in bot_tables:
            # Use bot-specific V2 table
            table_name = bot_tables[bot_filter.upper()]

            try:
                if is_individual_trades:
                    # Get individual trades with full timestamps for granular daily chart
                    # Use COALESCE to fall back to open_time if close_time is NULL (legacy data)
                    cursor.execute(f'''
                        SELECT
                            COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago' as close_timestamp,
                            realized_pnl,
                            position_id
                        FROM {table_name}
                        WHERE status IN ('closed', 'expired', 'partial_close')
                        ORDER BY COALESCE(close_time, open_time) ASC
                    ''')
                else:
                    # Weekly/monthly aggregation
                    # Use COALESCE to fall back to open_time if close_time is NULL (legacy data)
                    if timeframe == 'weekly':
                        date_format_v2 = "DATE_TRUNC('week', DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago'))::date"
                    else:  # monthly
                        date_format_v2 = "DATE_TRUNC('month', DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago'))::date"

                    cursor.execute(f'''
                        SELECT
                            {date_format_v2} as period_date,
                            SUM(realized_pnl) as daily_pnl,
                            COUNT(*) as trade_count
                        FROM {table_name}
                        WHERE status IN ('closed', 'expired', 'partial_close')
                        GROUP BY {date_format_v2}
                        ORDER BY period_date ASC
                    ''')

                rows = cursor.fetchall()
            except Exception as table_err:
                # Table might not exist yet (e.g., bot never run)
                logger.debug(f"Could not query {table_name}: {table_err}")
                rows = []

            # If no V2 data found, fall back to legacy table for backwards compatibility
            if not rows:
                if is_individual_trades:
                    # Get ALL trades - no date filter per CLAUDE.md requirements
                    cursor.execute('''
                        SELECT
                            exit_date::date as close_timestamp,
                            realized_pnl,
                            id as position_id
                        FROM autonomous_closed_trades
                        WHERE strategy ILIKE %s
                        ORDER BY exit_date ASC
                    ''', [f'%{bot_filter}%'])
                else:
                    if timeframe == 'weekly':
                        date_format_legacy = "DATE_TRUNC('week', exit_date::date)::date"
                    else:
                        date_format_legacy = "DATE_TRUNC('month', exit_date::date)::date"
                    # Get ALL trades - no date filter per CLAUDE.md requirements
                    cursor.execute(f'''
                        SELECT
                            {date_format_legacy} as period_date,
                            SUM(realized_pnl) as daily_pnl,
                            COUNT(*) as trade_count
                        FROM autonomous_closed_trades
                        WHERE strategy ILIKE %s
                        GROUP BY {date_format_legacy}
                        ORDER BY period_date ASC
                    ''', [f'%{bot_filter}%'])
                rows = cursor.fetchall()
        else:
            # No bot filter or unknown bot - use legacy unified table
            bot_clause = ""
            params = []
            if bot_filter:
                bot_clause = "WHERE strategy ILIKE %s"
                params.append(f'%{bot_filter}%')

            if is_individual_trades:
                # Get ALL trades - no date filter per CLAUDE.md requirements
                cursor.execute(f'''
                    SELECT
                        exit_date::date as close_timestamp,
                        realized_pnl,
                        id as position_id
                    FROM autonomous_closed_trades
                    {bot_clause}
                    ORDER BY exit_date ASC
                ''', params)
            else:
                if timeframe == 'weekly':
                    date_format_legacy = "DATE_TRUNC('week', exit_date::date)::date"
                else:
                    date_format_legacy = "DATE_TRUNC('month', exit_date::date)::date"
                # Get ALL trades - no date filter per CLAUDE.md requirements
                where_clause = f"WHERE {bot_clause[6:]}" if bot_clause else ""
                cursor.execute(f'''
                    SELECT
                        {date_format_legacy} as period_date,
                        SUM(realized_pnl) as daily_pnl,
                        COUNT(*) as trade_count
                    FROM autonomous_closed_trades
                    {where_clause}
                    GROUP BY {date_format_legacy}
                    ORDER BY period_date ASC
                ''', params if bot_clause else [])
            rows = cursor.fetchall()

        if not rows:
            # Even with no closed positions, check for open positions with unrealized P&L
            unrealized_pnl = _calculate_bot_unrealized_pnl(cursor, bot_filter)
            if unrealized_pnl != 0:
                today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')
                equity = starting_capital + unrealized_pnl
                return [{
                    'date': today,
                    'equity': round(equity, 2),
                    'daily_pnl': round(unrealized_pnl, 2),
                    'cumulative_pnl': round(unrealized_pnl, 2),
                    'drawdown_pct': 0,
                    'trade_count': 0,
                    'unrealized_pnl': round(unrealized_pnl, 2),
                    'open_positions': True
                }]
            return []

        # Build equity curve
        equity_curve = []
        cumulative_pnl = 0
        high_water_mark = starting_capital
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        if is_individual_trades:
            # Build one point per trade for granular visualization
            if rows:
                # Add starting point
                first_timestamp = rows[0][0]
                if first_timestamp:
                    first_date = first_timestamp.strftime('%Y-%m-%d') if hasattr(first_timestamp, 'strftime') else str(first_timestamp)[:10]
                    equity_curve.append({
                        'date': first_date,
                        'equity': starting_capital,
                        'daily_pnl': 0,
                        'cumulative_pnl': 0,
                        'drawdown_pct': 0,
                        'trade_count': 0
                    })

            for close_timestamp, pnl, position_id in rows:
                daily_pnl = float(pnl or 0)
                cumulative_pnl += daily_pnl
                equity = starting_capital + cumulative_pnl

                if equity > high_water_mark:
                    high_water_mark = equity

                drawdown_pct = ((high_water_mark - equity) / high_water_mark * 100) if high_water_mark > 0 else 0

                # Format date from timestamp
                if close_timestamp:
                    if hasattr(close_timestamp, 'strftime'):
                        date_str = close_timestamp.strftime('%Y-%m-%d')
                    else:
                        date_str = str(close_timestamp)[:10]
                else:
                    date_str = today

                equity_curve.append({
                    'date': date_str,
                    'equity': round(equity, 2),
                    'daily_pnl': round(daily_pnl, 2),
                    'cumulative_pnl': round(cumulative_pnl, 2),
                    'drawdown_pct': round(drawdown_pct, 2),
                    'trade_count': 1
                })
        else:
            # Weekly/monthly aggregated view
            for period_date, daily_pnl, trade_count in rows:
                daily_pnl = daily_pnl or 0
                cumulative_pnl += daily_pnl
                equity = starting_capital + cumulative_pnl

                if equity > high_water_mark:
                    high_water_mark = equity

                drawdown_pct = ((high_water_mark - equity) / high_water_mark * 100) if high_water_mark > 0 else 0

                equity_curve.append({
                    'date': str(period_date),
                    'equity': round(equity, 2),
                    'daily_pnl': round(daily_pnl, 2),
                    'cumulative_pnl': round(cumulative_pnl, 2),
                    'drawdown_pct': round(drawdown_pct, 2),
                    'trade_count': trade_count
                })

        # Add unrealized P&L from open positions to current day
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')
        unrealized_pnl = _calculate_bot_unrealized_pnl(cursor, bot_filter)

        if unrealized_pnl != 0 or (equity_curve and equity_curve[-1]['date'] != today):
            total_pnl_with_unrealized = cumulative_pnl + unrealized_pnl
            equity_with_unrealized = starting_capital + total_pnl_with_unrealized

            if equity_with_unrealized > high_water_mark:
                high_water_mark = equity_with_unrealized

            drawdown_pct = ((high_water_mark - equity_with_unrealized) / high_water_mark * 100) if high_water_mark > 0 else 0

            # Update or add today's entry
            if equity_curve and equity_curve[-1]['date'] == today:
                # Update existing today entry with unrealized
                equity_curve[-1]['equity'] = round(equity_with_unrealized, 2)
                equity_curve[-1]['cumulative_pnl'] = round(total_pnl_with_unrealized, 2)
                equity_curve[-1]['drawdown_pct'] = round(drawdown_pct, 2)
                equity_curve[-1]['unrealized_pnl'] = round(unrealized_pnl, 2)
            else:
                # Add new today entry
                equity_curve.append({
                    'date': today,
                    'equity': round(equity_with_unrealized, 2),
                    'daily_pnl': round(unrealized_pnl, 2),
                    'cumulative_pnl': round(total_pnl_with_unrealized, 2),
                    'drawdown_pct': round(drawdown_pct, 2),
                    'trade_count': 0,
                    'unrealized_pnl': round(unrealized_pnl, 2),
                    'open_positions': True
                })

        return equity_curve

    finally:
        conn.close()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/")
async def get_trading_events(
    days: int = 90,
    bot: Optional[str] = None,
    event_type: Optional[str] = None
):
    """
    Get auto-detected trading events.

    Args:
        days: Number of days of history (default 90)
        bot: Filter by bot name (ARES, ATHENA, etc.)
        event_type: Filter by event type
    """
    try:
        events = detect_events_from_trades(days=days, bot_filter=bot)

        if event_type:
            events = [e for e in events if e['type'] == event_type]

        return {
            "success": True,
            "count": len(events),
            "events": events
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_equity_curve(
    days: int = 90,
    bot: Optional[str] = None,
    timeframe: str = 'daily',
    auto_sync: bool = True
):
    """
    Get equity curve data with optional bot filter and timeframe.

    Args:
        days: Number of days of history (default 90)
        bot: Filter by bot name (ARES, ATHENA, etc.)
        timeframe: 'daily', 'weekly', or 'monthly'
        auto_sync: Automatically sync events to database (default True)
    """
    try:
        if timeframe not in ['daily', 'weekly', 'monthly']:
            timeframe = 'daily'

        equity_curve = get_equity_curve_data(days=days, bot_filter=bot, timeframe=timeframe)
        events = detect_events_from_trades(days=days, bot_filter=bot)

        # Auto-persist events when chart is loaded (lazy sync)
        sync_result = None
        if auto_sync and events:
            try:
                sync_result = persist_events(events)
            except Exception as e:
                print(f"Event sync failed (non-critical): {e}")

        # Get correct starting capital for bot (ARES fetches from Tradier)
        starting_capital = _get_bot_capital(bot)

        # Calculate summary stats
        if equity_curve:
            final = equity_curve[-1]
            max_dd = max(p['drawdown_pct'] for p in equity_curve)
            total_pnl = final['cumulative_pnl']

            summary = {
                'total_pnl': total_pnl,
                'final_equity': final['equity'],
                'max_drawdown_pct': max_dd,
                'total_trades': sum(p['trade_count'] for p in equity_curve),
                'starting_capital': starting_capital
            }
        else:
            summary = {
                'total_pnl': 0,
                'final_equity': starting_capital,
                'max_drawdown_pct': 0,
                'total_trades': 0,
                'starting_capital': starting_capital
            }

        response = {
            "success": True,
            "timeframe": timeframe,
            "equity_curve": equity_curve,
            "events": events,
            "summary": summary
        }

        # Include sync info if sync was performed
        if sync_result:
            response["sync"] = {
                "persisted": sync_result.get('inserted', 0),
                "skipped": sync_result.get('skipped', 0)
            }

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_trading_events(
    days: int = 90,
    bot: Optional[str] = None
):
    """
    Sync events by detecting from trade data and persisting to database.
    This endpoint should be called:
    - After trades close
    - Periodically (e.g., end of day)
    - Manually when needed

    Args:
        days: Number of days of history to scan (default 90)
        bot: Optional bot name filter (ARES, ATHENA, etc.)
    """
    try:
        result = sync_events(days=days, bot_filter=bot)
        return {
            "success": True,
            "message": f"Synced {result['inserted']} new events ({result['skipped']} already existed)",
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/persisted")
async def get_persisted_trading_events(
    days: int = 90,
    bot: Optional[str] = None,
    event_type: Optional[str] = None
):
    """
    Get events that have been persisted to the database.
    Unlike the main / endpoint, this only returns events that were saved.

    Args:
        days: Number of days of history (default 90)
        bot: Filter by bot name (ARES, ATHENA, etc.)
        event_type: Filter by event type
    """
    try:
        events = get_persisted_events(days=days, bot_filter=bot, event_type=event_type)
        return {
            "success": True,
            "count": len(events),
            "events": events,
            "source": "database"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear")
async def clear_trading_events(
    days: Optional[int] = None,
    bot: Optional[str] = None
):
    """
    Clear persisted events from the database.
    Use with caution - this deletes data.

    Args:
        days: Only clear events older than this many days (optional)
        bot: Only clear events for this bot (optional)
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        query = "DELETE FROM trading_events WHERE 1=1"
        params = []

        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            query += " AND event_date < %s"
            params.append(cutoff_date)

        if bot:
            query += " AND bot_name ILIKE %s"
            params.append(f'%{bot}%')

        cursor.execute(query, params)
        deleted = cursor.rowcount
        conn.commit()

        return {
            "success": True,
            "deleted": deleted,
            "message": f"Deleted {deleted} events"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/types")
async def get_event_types():
    """Get all available event types and their configurations."""
    return {
        "success": True,
        "event_types": {
            "new_high": {
                "label": "New Equity High",
                "color": "#22C55E",
                "icon": "trophy",
                "severity": "success"
            },
            "winning_streak": {
                "label": "Winning Streak",
                "color": "#22C55E",
                "icon": "flame",
                "severity": "success"
            },
            "losing_streak": {
                "label": "Losing Streak",
                "color": "#EF4444",
                "icon": "alert-triangle",
                "severity": "danger"
            },
            "drawdown": {
                "label": "Max Drawdown",
                "color": "#EF4444",
                "icon": "trending-down",
                "severity": "danger"
            },
            "big_win": {
                "label": "Large Win",
                "color": "#22C55E",
                "icon": "award",
                "severity": "success"
            },
            "big_loss": {
                "label": "Large Loss",
                "color": "#EF4444",
                "icon": "x-circle",
                "severity": "danger"
            },
            "model_change": {
                "label": "Model Version",
                "color": "#8B5CF6",
                "icon": "cpu",
                "severity": "info"
            },
            "vix_spike": {
                "label": "VIX Spike",
                "color": "#3B82F6",
                "icon": "activity",
                "severity": "warning"
            },
            "circuit_breaker": {
                "label": "Circuit Breaker",
                "color": "#F59E0B",
                "icon": "pause-circle",
                "severity": "warning"
            }
        }
    }
