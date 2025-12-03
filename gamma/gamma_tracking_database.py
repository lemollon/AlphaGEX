"""
Gamma Tracking Database
Stores and analyzes historical gamma movements for correlation analysis
Tracks daily expirations (SPY, QQQ, IWM, etc.) throughout the week

This module provides database storage and analysis functionality.
UI rendering has been removed - use the backend API for tracking views.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database_adapter import get_connection
import numpy as np
import logging

logger = logging.getLogger(__name__)


class GammaTrackingDB:
    """Database for historical gamma tracking and correlation analysis (PostgreSQL)"""

    def __init__(self):
        self._ensure_gamma_tables()

    def _ensure_gamma_tables(self):
        """
        Verify gamma tracking tables exist.
        NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
        """
        # Tables gamma_history, gamma_daily_summary, spy_correlation are created by
        # db/config_and_database.py init_database() on app startup.
        pass

    def store_gamma_snapshot(self, symbol: str, gex_data: Dict, skew_data: Dict = None):
        """
        Store a gamma snapshot for historical tracking (PostgreSQL)

        Args:
            symbol: Ticker symbol
            gex_data: Current GEX data
            skew_data: Optional skew data
        """
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        date = now.strftime('%Y-%m-%d')
        time_of_day = now.strftime('%H:%M')

        spot_price = float(gex_data.get('spot_price', 0))
        net_gex = float(gex_data.get('net_gex', 0))
        flip_point = float(gex_data.get('flip_point', 0))
        call_wall = float(gex_data.get('call_wall', 0))
        put_wall = float(gex_data.get('put_wall', 0))

        # Calculate distance to flip
        distance_to_flip_pct = ((flip_point - spot_price) / spot_price * 100) if spot_price else 0

        # Determine regime
        regime = "Positive GEX" if net_gex > 0 else "Negative GEX"
        if spot_price and flip_point:
            regime += ", Above Flip" if spot_price > flip_point else ", Below Flip"

        # Get skew data
        implied_vol = 0
        put_call_ratio = 0
        if skew_data:
            implied_vol = float(skew_data.get('implied_volatility', 0))
            put_call_ratio = float(skew_data.get('pcr_oi', 0))

        conn = get_connection()
        c = conn.cursor()

        try:
            # PostgreSQL ON CONFLICT for upsert
            c.execute("""
                INSERT INTO gamma_history (
                    symbol, timestamp, date, time_of_day, spot_price, net_gex, flip_point,
                    call_wall, put_wall, implied_volatility, put_call_ratio,
                    distance_to_flip_pct, regime
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    spot_price = EXCLUDED.spot_price,
                    net_gex = EXCLUDED.net_gex,
                    flip_point = EXCLUDED.flip_point,
                    call_wall = EXCLUDED.call_wall,
                    put_wall = EXCLUDED.put_wall,
                    implied_volatility = EXCLUDED.implied_volatility,
                    put_call_ratio = EXCLUDED.put_call_ratio,
                    distance_to_flip_pct = EXCLUDED.distance_to_flip_pct,
                    regime = EXCLUDED.regime
            """, (
                symbol, timestamp, date, time_of_day, spot_price, net_gex, flip_point,
                call_wall, put_wall, implied_vol, put_call_ratio,
                distance_to_flip_pct, regime
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Error storing gamma snapshot: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_snapshots_for_date_range(self, symbol: str, days_back: int = 7) -> pd.DataFrame:
        """
        Get gamma snapshots for a date range (PostgreSQL)

        Args:
            symbol: Ticker symbol
            days_back: Number of days to look back

        Returns:
            DataFrame with snapshots
        """
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        conn = get_connection()
        query = """
            SELECT * FROM gamma_history
            WHERE symbol = %s AND date >= %s
            ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn.raw_connection, params=(symbol, start_date))
        conn.close()

        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['date'] = pd.to_datetime(df['date'])

        return df

    def calculate_daily_summary(self, symbol: str, date: str):
        """
        Calculate and store daily summary for a symbol (PostgreSQL)

        Args:
            symbol: Ticker symbol
            date: Date string (YYYY-MM-DD)
        """
        conn = get_connection()

        # Get all snapshots for the date
        query = """
            SELECT * FROM gamma_history
            WHERE symbol = %s AND date = %s
            ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn.raw_connection, params=(symbol, date))

        if df.empty:
            conn.close()
            return

        # Calculate daily metrics
        open_gex = df.iloc[0]['net_gex']
        close_gex = df.iloc[-1]['net_gex']
        high_gex = df['net_gex'].max()
        low_gex = df['net_gex'].min()
        gex_change = close_gex - open_gex
        gex_change_pct = (gex_change / abs(open_gex) * 100) if open_gex != 0 else 0

        open_flip = df.iloc[0]['flip_point']
        close_flip = df.iloc[-1]['flip_point']
        flip_change = close_flip - open_flip
        flip_change_pct = (flip_change / open_flip * 100) if open_flip != 0 else 0

        open_price = df.iloc[0]['spot_price']
        close_price = df.iloc[-1]['spot_price']
        price_change_pct = ((close_price - open_price) / open_price * 100) if open_price != 0 else 0

        avg_iv = df['implied_volatility'].mean()
        snapshots_count = len(df)

        # Store summary with PostgreSQL ON CONFLICT
        c = conn.cursor()
        c.execute("""
            INSERT INTO gamma_daily_summary (
                symbol, date, open_gex, close_gex, high_gex, low_gex, gex_change,
                gex_change_pct, open_flip, close_flip, flip_change, flip_change_pct,
                open_price, close_price, price_change_pct, avg_iv, snapshots_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET
                open_gex = EXCLUDED.open_gex,
                close_gex = EXCLUDED.close_gex,
                high_gex = EXCLUDED.high_gex,
                low_gex = EXCLUDED.low_gex,
                gex_change = EXCLUDED.gex_change,
                gex_change_pct = EXCLUDED.gex_change_pct,
                open_flip = EXCLUDED.open_flip,
                close_flip = EXCLUDED.close_flip,
                flip_change = EXCLUDED.flip_change,
                flip_change_pct = EXCLUDED.flip_change_pct,
                open_price = EXCLUDED.open_price,
                close_price = EXCLUDED.close_price,
                price_change_pct = EXCLUDED.price_change_pct,
                avg_iv = EXCLUDED.avg_iv,
                snapshots_count = EXCLUDED.snapshots_count
        """, (
            symbol, date, open_gex, close_gex, high_gex, low_gex, gex_change,
            gex_change_pct, open_flip, close_flip, flip_change, flip_change_pct,
            open_price, close_price, price_change_pct, avg_iv, snapshots_count
        ))

        conn.commit()
        conn.close()

    def get_weekly_summary(self, symbol: str) -> pd.DataFrame:
        """
        Get weekly summary for a symbol (PostgreSQL)

        Args:
            symbol: Ticker symbol

        Returns:
            DataFrame with daily summaries for the past week
        """
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        conn = get_connection()
        query = """
            SELECT * FROM gamma_daily_summary
            WHERE symbol = %s AND date >= %s
            ORDER BY date DESC
        """
        df = pd.read_sql_query(query, conn.raw_connection, params=(symbol, start_date))
        conn.close()

        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])

        return df

    def calculate_spy_correlation(self, symbol: str, date: str):
        """
        Calculate correlation between symbol and SPY for a specific date (PostgreSQL)

        Args:
            symbol: Ticker symbol (not SPY)
            date: Date string (YYYY-MM-DD)
        """
        if symbol == 'SPY':
            return  # Don't correlate SPY with itself

        conn = get_connection()

        # Get SPY daily summary
        spy_summary = pd.read_sql_query("""
            SELECT * FROM gamma_daily_summary
            WHERE symbol = 'SPY' AND date = %s
        """, conn.raw_connection, params=(date,))

        # Get symbol daily summary
        symbol_summary = pd.read_sql_query("""
            SELECT * FROM gamma_daily_summary
            WHERE symbol = %s AND date = %s
        """, conn.raw_connection, params=(symbol, date))

        if spy_summary.empty or symbol_summary.empty:
            conn.close()
            return

        spy_gex_change_pct = spy_summary.iloc[0]['gex_change_pct']
        symbol_gex_change_pct = symbol_summary.iloc[0]['gex_change_pct']
        spy_price_change_pct = spy_summary.iloc[0]['price_change_pct']
        symbol_price_change_pct = symbol_summary.iloc[0]['price_change_pct']

        # Calculate simple correlation score (direction agreement)
        gex_direction_match = (spy_gex_change_pct * symbol_gex_change_pct) > 0
        price_direction_match = (spy_price_change_pct * symbol_price_change_pct) > 0

        # Correlation score: 1.0 = perfect correlation, 0 = no correlation, -1.0 = inverse
        if gex_direction_match and price_direction_match:
            correlation_score = 0.8 + min(0.2, abs(symbol_price_change_pct - spy_price_change_pct) / 100)
        elif gex_direction_match or price_direction_match:
            correlation_score = 0.5
        else:
            correlation_score = -0.5

        # Store correlation with PostgreSQL ON CONFLICT
        c = conn.cursor()
        c.execute("""
            INSERT INTO spy_correlation (
                date, symbol, spy_gex_change_pct, symbol_gex_change_pct,
                spy_price_change_pct, symbol_price_change_pct, correlation_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET
                spy_gex_change_pct = EXCLUDED.spy_gex_change_pct,
                symbol_gex_change_pct = EXCLUDED.symbol_gex_change_pct,
                spy_price_change_pct = EXCLUDED.spy_price_change_pct,
                symbol_price_change_pct = EXCLUDED.symbol_price_change_pct,
                correlation_score = EXCLUDED.correlation_score
        """, (
            date, symbol, spy_gex_change_pct, symbol_gex_change_pct,
            spy_price_change_pct, symbol_price_change_pct, correlation_score
        ))

        conn.commit()
        conn.close()

    def get_correlation_history(self, symbol: str, days_back: int = 30) -> pd.DataFrame:
        """
        Get SPY correlation history for a symbol (PostgreSQL)

        Args:
            symbol: Ticker symbol
            days_back: Number of days to look back

        Returns:
            DataFrame with correlation data
        """
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        conn = get_connection()
        query = """
            SELECT * FROM spy_correlation
            WHERE symbol = %s AND date >= %s
            ORDER BY date DESC
        """
        df = pd.read_sql_query(query, conn.raw_connection, params=(symbol, start_date))
        conn.close()

        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])

        return df

    def get_intraday_gamma_pattern(self, symbol: str, days_back: int = 5) -> Dict:
        """
        Analyze intraday gamma patterns over multiple days

        Args:
            symbol: Ticker symbol
            days_back: Number of days to analyze

        Returns:
            Dictionary with pattern analysis
        """
        df = self.get_snapshots_for_date_range(symbol, days_back)

        if df.empty:
            return {}

        # Group by time of day
        df['hour'] = df['timestamp'].dt.hour
        df['minute_bucket'] = (df['timestamp'].dt.minute // 15) * 15  # 15-min buckets

        # Analyze patterns by time
        hourly_patterns = df.groupby('hour').agg({
            'net_gex': ['mean', 'std'],
            'distance_to_flip_pct': ['mean', 'std'],
            'spot_price': 'count'
        }).reset_index()

        # Find key times with largest GEX changes
        time_buckets = df.groupby(['hour', 'minute_bucket']).agg({
            'net_gex': ['mean', 'std', 'min', 'max'],
            'distance_to_flip_pct': 'mean'
        }).reset_index()

        # Identify market open (9:30) and close (16:00) patterns
        market_open_data = df[df['hour'] == 9]
        market_close_data = df[df['hour'] == 15]

        pattern_analysis = {
            'hourly_patterns': hourly_patterns.to_dict('records'),
            'time_buckets': time_buckets.to_dict('records'),
            'open_avg_gex': market_open_data['net_gex'].mean() if not market_open_data.empty else 0,
            'close_avg_gex': market_close_data['net_gex'].mean() if not market_close_data.empty else 0,
            'total_snapshots': len(df),
            'days_analyzed': df['date'].nunique()
        }

        return pattern_analysis

    def cleanup_old_data(self, days_to_keep: int = 90):
        """
        Clean up old gamma tracking data (PostgreSQL)

        Args:
            days_to_keep: Number of days of data to retain
        """
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')

        conn = get_connection()
        c = conn.cursor()

        c.execute("DELETE FROM gamma_history WHERE date < %s", (cutoff_date,))
        c.execute("DELETE FROM gamma_daily_summary WHERE date < %s", (cutoff_date,))
        c.execute("DELETE FROM spy_correlation WHERE date < %s", (cutoff_date,))

        deleted_count = c.rowcount
        conn.commit()
        conn.close()

        return deleted_count


def get_weekly_insights(symbol: str, gamma_db: GammaTrackingDB) -> List[str]:
    """
    Generate insights from weekly gamma tracking data

    Args:
        symbol: Ticker symbol
        gamma_db: GammaTrackingDB instance

    Returns:
        List of insight strings
    """
    weekly_summary = gamma_db.get_weekly_summary(symbol)

    if weekly_summary.empty:
        return []

    insights = []

    # Trend analysis
    recent_gex_changes = weekly_summary.head(3)['gex_change_pct'].tolist()
    if len(recent_gex_changes) >= 3:
        if all(x > 0 for x in recent_gex_changes):
            insights.append("Consistent GEX Increase: Dealers accumulating long gamma - Expect lower volatility")
        elif all(x < 0 for x in recent_gex_changes):
            insights.append("Consistent GEX Decrease: Dealers shedding gamma - Expect higher volatility")

    # Flip point trend
    recent_flip_changes = weekly_summary.head(3)['flip_change_pct'].tolist()
    if len(recent_flip_changes) >= 3:
        if all(x > 1 for x in recent_flip_changes):
            insights.append("Flip Point Rising: Bullish dealer repositioning over past 3 days")
        elif all(x < -1 for x in recent_flip_changes):
            insights.append("Flip Point Falling: Bearish dealer repositioning over past 3 days")

    # IV trend
    if not weekly_summary.empty and len(weekly_summary) >= 2:
        current_iv = weekly_summary.iloc[0]['avg_iv']
        week_ago_iv = weekly_summary.iloc[-1]['avg_iv']
        iv_change = current_iv - week_ago_iv

        if iv_change > 0.05:
            insights.append(f"IV Expanding: Volatility increased {iv_change*100:.1f}% over the week - Options getting more expensive")
        elif iv_change < -0.05:
            insights.append(f"IV Contracting: Volatility decreased {abs(iv_change)*100:.1f}% over the week - Premium selling opportunity")

    return insights


def get_correlation_summary(symbol: str, gamma_db: GammaTrackingDB) -> Optional[Dict]:
    """
    Get SPY correlation summary for a symbol

    Args:
        symbol: Ticker symbol
        gamma_db: GammaTrackingDB instance

    Returns:
        Dictionary with correlation summary or None
    """
    if symbol == 'SPY':
        return None

    correlation_data = gamma_db.get_correlation_history(symbol, days_back=7)

    if correlation_data.empty:
        return None

    avg_correlation = correlation_data['correlation_score'].mean()
    correlation_strength = "Strong" if abs(avg_correlation) > 0.7 else "Moderate" if abs(avg_correlation) > 0.4 else "Weak"

    return {
        'symbol': symbol,
        'avg_correlation': avg_correlation,
        'correlation_strength': correlation_strength,
        'data_points': len(correlation_data)
    }
