"""
Trading Events Routes - Auto-detected events for equity curve visualization
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from typing import Optional, List
import json
import logging

logger = logging.getLogger(__name__)

# Import database adapter
try:
    from database_adapter import get_connection
except ImportError:
    from ...database_adapter import get_connection

router = APIRouter(prefix="/api/events", tags=["Events"])


# ============================================================================
# CAPITAL FETCHERS FOR BOTS
# ============================================================================

def _get_ares_capital() -> float:
    """
    Get ARES starting capital from Tradier or database.

    ARES represents the actual Tradier sandbox account, so we fetch the real balance.
    Falls back to stored starting capital or $100k default.
    """
    try:
        # Try to get stored starting capital from database first
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

        # Fall back to fetching from Tradier
        try:
            from backend.api.routes.ares_routes import _get_tradier_account_balance
            tradier_balance = _get_tradier_account_balance()
            if tradier_balance.get('connected') and tradier_balance.get('total_equity', 0) > 0:
                return round(tradier_balance['total_equity'], 2)
        except ImportError:
            pass

        # Default fallback
        return 100000

    except Exception as e:
        logger.warning(f"Could not fetch ARES capital: {e}")
        return 100000


def _get_bot_capital(bot_name: str) -> float:
    """
    Get starting capital for a bot.

    - ARES: Fetched from Tradier sandbox account (real money)
    - ATHENA: $100,000 paper trading capital
    - PEGASUS: $200,000 paper trading capital
    """
    if not bot_name:
        return 200000

    bot_upper = bot_name.upper()

    if bot_upper == 'ARES':
        return _get_ares_capital()
    elif bot_upper == 'ATHENA':
        return 100000  # Paper trading
    elif bot_upper == 'PEGASUS':
        return 200000  # Paper trading SPX
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
                    DATE(close_time AT TIME ZONE 'America/Chicago') as exit_date,
                    close_time as exit_time,
                    realized_pnl,
                    %s as strategy,
                    ticker as symbol,
                    vix_at_entry as entry_vix,
                    vix_at_entry as exit_vix,
                    gex_regime
                FROM {table_name}
                WHERE status IN ('closed', 'expired')
                AND close_time IS NOT NULL
                AND DATE(close_time AT TIME ZONE 'America/Chicago') >= %s
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


def get_equity_curve_data(days: int = 90, bot_filter: str = None, timeframe: str = 'daily') -> List[dict]:
    """
    Get equity curve data from trades, aggregated by timeframe.

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

        # Get daily aggregated trades
        if timeframe == 'daily':
            date_format_legacy = "exit_date"
            date_format_v2 = "DATE(close_time AT TIME ZONE 'America/Chicago')"
        elif timeframe == 'weekly':
            date_format_legacy = "DATE_TRUNC('week', exit_date::date)::date"
            date_format_v2 = "DATE_TRUNC('week', DATE(close_time AT TIME ZONE 'America/Chicago'))::date"
        else:  # monthly
            date_format_legacy = "DATE_TRUNC('month', exit_date::date)::date"
            date_format_v2 = "DATE_TRUNC('month', DATE(close_time AT TIME ZONE 'America/Chicago'))::date"

        # Bot-specific table mapping for V2 bots
        # Each V2 bot stores closed trades in its own positions table
        bot_tables = {
            'ARES': 'ares_positions',      # SPY Iron Condors - capital from Tradier
            'ATHENA': 'athena_positions',  # SPY Directional - $100k paper
            'PEGASUS': 'pegasus_positions' # SPX Iron Condors - $200k paper
        }

        rows = []
        # Get starting capital dynamically (ARES fetches from Tradier)
        starting_capital = _get_bot_capital(bot_filter)

        if bot_filter and bot_filter.upper() in bot_tables:
            # Use bot-specific V2 table
            table_name = bot_tables[bot_filter.upper()]

            cursor.execute(f'''
                SELECT
                    {date_format_v2} as period_date,
                    SUM(realized_pnl) as daily_pnl,
                    COUNT(*) as trade_count
                FROM {table_name}
                WHERE status IN ('closed', 'expired')
                AND close_time IS NOT NULL
                AND DATE(close_time AT TIME ZONE 'America/Chicago') >= %s
                GROUP BY {date_format_v2}
                ORDER BY period_date ASC
            ''', [start_date])

            rows = cursor.fetchall()

            # If no V2 data found, fall back to legacy table for backwards compatibility
            if not rows:
                params = [start_date, f'%{bot_filter}%']
                cursor.execute(f'''
                    SELECT
                        {date_format_legacy} as period_date,
                        SUM(realized_pnl) as daily_pnl,
                        COUNT(*) as trade_count
                    FROM autonomous_closed_trades
                    WHERE exit_date >= %s AND strategy ILIKE %s
                    GROUP BY {date_format_legacy}
                    ORDER BY period_date ASC
                ''', params)
                rows = cursor.fetchall()
        else:
            # No bot filter or unknown bot - use legacy unified table
            params = [start_date]
            bot_clause = ""
            if bot_filter:
                bot_clause = "AND strategy ILIKE %s"
                params.append(f'%{bot_filter}%')

            cursor.execute(f'''
                SELECT
                    {date_format_legacy} as period_date,
                    SUM(realized_pnl) as daily_pnl,
                    COUNT(*) as trade_count
                FROM autonomous_closed_trades
                WHERE exit_date >= %s {bot_clause}
                GROUP BY {date_format_legacy}
                ORDER BY period_date ASC
            ''', params)
            rows = cursor.fetchall()

        if not rows:
            return []

        # Build equity curve
        equity_curve = []
        cumulative_pnl = 0
        high_water_mark = starting_capital

        for period_date, daily_pnl, trade_count in rows:
            daily_pnl = daily_pnl or 0
            cumulative_pnl += daily_pnl
            equity = starting_capital + cumulative_pnl

            if equity > high_water_mark:
                high_water_mark = equity

            drawdown_pct = ((high_water_mark - equity) / high_water_mark * 100) if high_water_mark > 0 else 0

            equity_curve.append({
                'date': str(period_date),
                'equity': equity,
                'daily_pnl': daily_pnl,
                'cumulative_pnl': cumulative_pnl,
                'drawdown_pct': drawdown_pct,
                'trade_count': trade_count
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
