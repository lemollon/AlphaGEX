"""
Trading Events Routes - Auto-detected events for equity curve visualization
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from typing import Optional, List
import json

# Import database adapter
try:
    from database_adapter import get_connection
except ImportError:
    from ...database_adapter import get_connection

router = APIRouter(prefix="/api/events", tags=["Events"])

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

    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    events = []

    # Get closed trades
    bot_clause = f"AND strategy ILIKE '%{bot_filter}%'" if bot_filter else ""
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
    ''', (start_date,))

    trades = cursor.fetchall()

    if not trades:
        conn.close()
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

        # New equity high
        if cumulative_pnl > high_water_mark:
            if high_water_mark > 0:  # Not the first trade
                events.append({
                    'date': exit_date,
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
                    'date': exit_date,
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
                    'date': exit_date,
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
                    'date': exit_date,
                    'type': 'losing_streak',
                    'severity': 'danger',
                    'title': 'Losing Streak',
                    'description': f'{consecutive_losses} consecutive losses',
                    'value': consecutive_losses,
                    'bot': strategy
                })

        # Large trade detection (>2x average after we have enough data)
        if len(pnl_list) > 5 and abs(pnl) > abs(avg_pnl) * 2:
            if pnl > 0:
                events.append({
                    'date': exit_date,
                    'type': 'big_win',
                    'severity': 'success',
                    'title': 'Large Win',
                    'description': f'+${pnl:,.0f} ({abs(pnl/avg_pnl):.1f}x average)',
                    'value': pnl,
                    'bot': strategy
                })
            else:
                events.append({
                    'date': exit_date,
                    'type': 'big_loss',
                    'severity': 'danger',
                    'title': 'Large Loss',
                    'description': f'-${abs(pnl):,.0f} ({abs(pnl/avg_pnl):.1f}x average)',
                    'value': pnl,
                    'bot': strategy
                })

        # VIX spike detection
        vix = exit_vix or entry_vix
        if vix and vix > 25:
            # Check if we already have a VIX event for this date
            if not any(e['date'] == exit_date and e['type'] == 'vix_spike' for e in events):
                events.append({
                    'date': exit_date,
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

    conn.close()

    # Sort events by date
    events.sort(key=lambda x: x['date'])

    return events


def get_equity_curve_data(days: int = 90, bot_filter: str = None, timeframe: str = 'daily') -> List[dict]:
    """
    Get equity curve data from trades, aggregated by timeframe.

    Args:
        days: Number of days of history
        bot_filter: Optional bot name filter (ARES, ATHENA, etc.)
        timeframe: 'daily', 'weekly', or 'monthly'
    """
    conn = get_connection()
    cursor = conn.cursor()

    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    bot_clause = f"AND strategy ILIKE '%{bot_filter}%'" if bot_filter else ""

    # Get daily aggregated trades
    if timeframe == 'daily':
        date_format = "exit_date"
    elif timeframe == 'weekly':
        date_format = "DATE_TRUNC('week', exit_date::date)::date"
    else:  # monthly
        date_format = "DATE_TRUNC('month', exit_date::date)::date"

    cursor.execute(f'''
        SELECT
            {date_format} as period_date,
            SUM(realized_pnl) as daily_pnl,
            COUNT(*) as trade_count
        FROM autonomous_closed_trades
        WHERE exit_date >= %s {bot_clause}
        GROUP BY {date_format}
        ORDER BY period_date ASC
    ''', (start_date,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    # Build equity curve
    equity_curve = []
    cumulative_pnl = 0
    high_water_mark = 0
    starting_capital = 200000  # Default starting capital

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
    timeframe: str = 'daily'
):
    """
    Get equity curve data with optional bot filter and timeframe.

    Args:
        days: Number of days of history (default 90)
        bot: Filter by bot name (ARES, ATHENA, etc.)
        timeframe: 'daily', 'weekly', or 'monthly'
    """
    try:
        if timeframe not in ['daily', 'weekly', 'monthly']:
            timeframe = 'daily'

        equity_curve = get_equity_curve_data(days=days, bot_filter=bot, timeframe=timeframe)
        events = detect_events_from_trades(days=days, bot_filter=bot)

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
                'starting_capital': 200000
            }
        else:
            summary = {
                'total_pnl': 0,
                'final_equity': 200000,
                'max_drawdown_pct': 0,
                'total_trades': 0,
                'starting_capital': 200000
            }

        return {
            "success": True,
            "timeframe": timeframe,
            "equity_curve": equity_curve,
            "events": events,
            "summary": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
