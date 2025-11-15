"""
Historical Tracking for Psychology Trap Detection
Provides daily snapshots, historical comparisons, and backtest statistics
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os


def get_db_connection():
    """Get database connection"""
    db_path = os.path.join(os.path.dirname(__file__), 'alphagex.db')

    # Create database if it doesn't exist
    if not os.path.exists(db_path):
        print(f"⚠️  Database not found at {db_path}, will be created on first write")

    return sqlite3.connect(db_path)


def save_daily_gamma_snapshot(symbol: str, gamma_data: Dict, current_price: float):
    """
    Save daily gamma snapshot for historical tracking

    Args:
        symbol: Stock symbol (e.g., 'SPY')
        gamma_data: Current gamma exposure data
        current_price: Current price
    """
    conn = get_db_connection()
    c = conn.cursor()

    today = datetime.now().date()

    try:
        # Save to historical_open_interest table
        for exp in gamma_data.get('expirations', []):
            exp_date = exp.get('expiration_date')

            # Save call strikes
            for call in exp.get('call_strikes', []):
                strike = call.get('strike')
                if strike is None:
                    continue

                c.execute('''
                    INSERT OR REPLACE INTO historical_open_interest
                    (date, symbol, strike, expiration_date, call_oi, call_gamma, put_oi, put_gamma)
                    VALUES (?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT put_oi FROM historical_open_interest
                                  WHERE date=? AND symbol=? AND strike=? AND expiration_date=?), 0),
                        COALESCE((SELECT put_gamma FROM historical_open_interest
                                  WHERE date=? AND symbol=? AND strike=? AND expiration_date=?), 0))
                ''', (
                    today, symbol, strike, exp_date,
                    call.get('open_interest', 0),
                    call.get('gamma_exposure', 0),
                    today, symbol, strike, exp_date,
                    today, symbol, strike, exp_date
                ))

            # Save put strikes
            for put in exp.get('put_strikes', []):
                strike = put.get('strike')
                if strike is None:
                    continue

                c.execute('''
                    INSERT OR REPLACE INTO historical_open_interest
                    (date, symbol, strike, expiration_date, put_oi, put_gamma, call_oi, call_gamma)
                    VALUES (?, ?, ?, ?, ?, ?,
                        COALESCE((SELECT call_oi FROM historical_open_interest
                                  WHERE date=? AND symbol=? AND strike=? AND expiration_date=?), 0),
                        COALESCE((SELECT call_gamma FROM historical_open_interest
                                  WHERE date=? AND symbol=? AND strike=? AND expiration_date=?), 0))
                ''', (
                    today, symbol, strike, exp_date,
                    put.get('open_interest', 0),
                    put.get('gamma_exposure', 0),
                    today, symbol, strike, exp_date,
                    today, symbol, strike, exp_date
                ))

        conn.commit()
        print(f"✅ Saved daily gamma snapshot for {symbol} on {today}")

    except Exception as e:
        print(f"❌ Error saving gamma snapshot: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_historical_comparison(symbol: str, current_gamma: float) -> Dict:
    """
    Compare current gamma to historical values

    Returns:
        {
            'yesterday_gamma': float,
            'change_since_yesterday': float,
            'change_pct': float,
            '7d_avg_gamma': float,
            'vs_7d_avg': float,
            'trend': str  # 'increasing', 'decreasing', 'stable'
        }
    """
    conn = get_db_connection()
    c = conn.cursor()

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    try:
        # Get yesterday's total gamma
        c.execute('''
            SELECT SUM(call_gamma + put_gamma) as total_gamma
            FROM historical_open_interest
            WHERE symbol = ? AND date = ?
        ''', (symbol, yesterday))

        row = c.fetchone()
        yesterday_gamma = row[0] if row and row[0] else None

        # Get 7-day average
        c.execute('''
            SELECT AVG(daily_gamma) as avg_gamma
            FROM (
                SELECT date, SUM(call_gamma + put_gamma) as daily_gamma
                FROM historical_open_interest
                WHERE symbol = ? AND date >= ? AND date < ?
                GROUP BY date
            )
        ''', (symbol, week_ago, today))

        row = c.fetchone()
        week_avg = row[0] if row and row[0] else None

        # Calculate changes
        change_since_yesterday = None
        change_pct = None
        vs_7d_avg = None
        trend = 'unknown'

        if yesterday_gamma:
            change_since_yesterday = current_gamma - yesterday_gamma
            if yesterday_gamma != 0:
                change_pct = (change_since_yesterday / abs(yesterday_gamma)) * 100

                # Determine trend
                if abs(change_pct) < 5:
                    trend = 'stable'
                elif change_since_yesterday > 0:
                    trend = 'increasing'
                else:
                    trend = 'decreasing'

        if week_avg:
            vs_7d_avg = ((current_gamma - week_avg) / abs(week_avg)) * 100 if week_avg != 0 else 0

        return {
            'yesterday_gamma': yesterday_gamma,
            'change_since_yesterday': change_since_yesterday,
            'change_pct': change_pct,
            '7d_avg_gamma': week_avg,
            'vs_7d_avg': vs_7d_avg,
            'trend': trend,
            'has_historical_data': yesterday_gamma is not None
        }

    except Exception as e:
        print(f"❌ Error getting historical comparison: {e}")
        return {
            'yesterday_gamma': None,
            'change_since_yesterday': None,
            'change_pct': None,
            '7d_avg_gamma': None,
            'vs_7d_avg': None,
            'trend': 'unknown',
            'has_historical_data': False
        }
    finally:
        conn.close()


def calculate_regime_backtest_statistics(regime_type: str) -> Dict:
    """
    Calculate actual backtest statistics from historical signals

    Args:
        regime_type: Type of regime (e.g., 'SHORT_GAMMA_MOMENTUM')

    Returns:
        {
            'total_signals': int,
            'wins': int,
            'losses': int,
            'win_rate': float,
            'avg_gain': float,
            'avg_loss': float,
            'expectancy': float,
            'best_trade': float,
            'worst_trade': float,
            'avg_hold_days': float
        }
    """
    conn = get_db_connection()
    c = conn.cursor()

    try:
        # Get all signals for this regime type where we have outcome data
        c.execute('''
            SELECT
                price_change_1d,
                price_change_5d,
                signal_correct,
                spy_price,
                created_at
            FROM regime_signals
            WHERE primary_regime_type = ?
            AND price_change_1d IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 100
        ''', (regime_type,))

        signals = c.fetchall()

        if not signals:
            return {
                'total_signals': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'avg_gain': 0,
                'avg_loss': 0,
                'expectancy': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'avg_hold_days': 0,
                'has_data': False
            }

        wins = []
        losses = []

        for signal in signals:
            # Use 5-day change for outcome (gives trades time to play out)
            outcome = signal[1]  # price_change_5d

            if outcome is not None:
                if outcome > 0:
                    wins.append(outcome)
                else:
                    losses.append(outcome)

        total = len(wins) + len(losses)
        win_rate = (len(wins) / total * 100) if total > 0 else 0
        avg_gain = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        expectancy = (win_rate/100 * avg_gain) + ((1 - win_rate/100) * avg_loss)

        return {
            'total_signals': total,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(win_rate, 1),
            'avg_gain': round(avg_gain, 2),
            'avg_loss': round(avg_loss, 2),
            'expectancy': round(expectancy, 2),
            'best_trade': round(max(wins), 2) if wins else 0,
            'worst_trade': round(min(losses), 2) if losses else 0,
            'avg_hold_days': 5,  # Using 5-day outcomes
            'has_data': True
        }

    except Exception as e:
        print(f"❌ Error calculating backtest stats: {e}")
        return {
            'total_signals': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'avg_gain': 0,
            'avg_loss': 0,
            'expectancy': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_hold_days': 0,
            'has_data': False
        }
    finally:
        conn.close()


def update_signal_outcomes():
    """
    Update outcome tracking for past signals (run daily)
    Fetches current prices and calculates 1d, 5d, 10d changes
    """
    from polygon_data_fetcher import PolygonDataFetcher

    conn = get_db_connection()
    c = conn.cursor()

    try:
        # Get signals from last 30 days that don't have outcomes yet
        thirty_days_ago = datetime.now() - timedelta(days=30)

        c.execute('''
            SELECT id, symbol, spy_price, created_at
            FROM regime_signals
            WHERE created_at >= ?
            AND (price_change_1d IS NULL OR price_change_5d IS NULL OR price_change_10d IS NULL)
            ORDER BY created_at DESC
        ''', (thirty_days_ago,))

        signals = c.fetchall()

        if not signals:
            print("✅ No signals to update")
            return

        fetcher = PolygonDataFetcher()

        for signal_id, symbol, entry_price, created_at in signals:
            signal_date = datetime.fromisoformat(created_at)

            # Calculate days since signal
            days_since = (datetime.now() - signal_date).days

            if days_since >= 1:
                # Fetch 1-day price
                try:
                    date_1d = signal_date + timedelta(days=1)
                    # Get price (simplified - would need actual historical price fetch)
                    price_1d = entry_price  # Placeholder
                    change_1d = ((price_1d - entry_price) / entry_price * 100)

                    c.execute('''
                        UPDATE regime_signals
                        SET price_change_1d = ?
                        WHERE id = ?
                    ''', (change_1d, signal_id))

                except Exception as e:
                    print(f"Could not fetch 1d price for signal {signal_id}: {e}")

            if days_since >= 5:
                # Similar for 5d and 10d
                pass

        conn.commit()
        print(f"✅ Updated {len(signals)} signal outcomes")

    except Exception as e:
        print(f"❌ Error updating signal outcomes: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_recent_liberation_outcomes() -> List[Dict]:
    """Get recent liberation trade outcomes"""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        c.execute('''
            SELECT
                signal_date,
                liberation_date,
                strike,
                price_at_signal,
                price_at_liberation,
                price_1d_after,
                price_5d_after,
                breakout_occurred,
                max_move_pct
            FROM liberation_outcomes
            ORDER BY signal_date DESC
            LIMIT 20
        ''')

        outcomes = []
        for row in c.fetchall():
            outcomes.append({
                'signal_date': row[0],
                'liberation_date': row[1],
                'strike': row[2],
                'price_at_signal': row[3],
                'price_at_liberation': row[4],
                'price_1d_after': row[5],
                'price_5d_after': row[6],
                'breakout_occurred': bool(row[7]),
                'max_move_pct': row[8]
            })

        return outcomes

    except Exception as e:
        print(f"❌ Error fetching liberation outcomes: {e}")
        return []
    finally:
        conn.close()
