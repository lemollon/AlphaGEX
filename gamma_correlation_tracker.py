"""
Gamma Correlation Tracker - Log gamma decay vs actual price moves
Enables backtesting and threshold refinement
"""

import sqlite3
from datetime import datetime, timedelta
import pytz
from typing import Dict, Optional
import pandas as pd

class GammaCorrelationTracker:
    """Track correlation between gamma decay and actual market moves"""

    def __init__(self, db_path='gamma_correlation.db'):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Create correlation tracking table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS gamma_correlation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            day_of_week TEXT,

            -- Gamma metrics (captured at market close)
            gamma_decay_pct REAL,
            weekly_decay_pct REAL,
            risk_level TEXT,
            vix REAL,
            today_total_gamma REAL,
            tomorrow_total_gamma REAL,
            expiring_gamma REAL,

            -- Actual outcomes (filled next trading day)
            next_day_open REAL,
            next_day_close REAL,
            next_day_high REAL,
            next_day_low REAL,
            actual_price_move_pct REAL,
            actual_intraday_range_pct REAL,
            actual_realized_vol REAL,

            -- Trading outcome (if we traded)
            strategy_taken TEXT,
            pnl REAL,
            pnl_pct REAL,

            -- Status
            filled BOOLEAN DEFAULT 0,
            notes TEXT,

            UNIQUE(symbol, timestamp)
        )
        ''')

        # Index for fast queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_date ON gamma_correlation(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_filled ON gamma_correlation(filled)')

        conn.commit()
        conn.close()

    def log_gamma_metrics(self, gamma_intel: Dict, symbol: str, current_price: float, vix: float = 0):
        """
        Log today's gamma metrics (called at market close)

        Args:
            gamma_intel: Full 3-view gamma intelligence
            symbol: Ticker
            current_price: Current spot price
            vix: Current VIX level
        """
        if not gamma_intel.get('success'):
            return None

        daily = gamma_intel['daily_impact']
        weekly = gamma_intel['weekly_evolution']

        timestamp = datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d')
        day_of_week = datetime.now(pytz.timezone('America/New_York')).strftime('%A')

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
            INSERT OR REPLACE INTO gamma_correlation
            (timestamp, symbol, day_of_week, gamma_decay_pct, weekly_decay_pct, risk_level,
             vix, today_total_gamma, tomorrow_total_gamma, expiring_gamma,
             next_day_open, filled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ''', (
                timestamp,
                symbol,
                day_of_week,
                daily['impact_pct'],
                weekly['total_decay_pct'],
                daily['risk_level'],
                vix,
                daily['today_total_gamma'],
                daily['tomorrow_total_gamma'],
                daily['expiring_today'],
                current_price  # Use as baseline for next day calculation
            ))

            conn.commit()
            return cursor.lastrowid

        except sqlite3.IntegrityError:
            # Already logged today
            pass
        finally:
            conn.close()

    def update_actual_outcomes(self, symbol: str, date: str, next_day_data: Dict):
        """
        Update with actual next-day price moves (called after market close next day)

        Args:
            symbol: Ticker
            date: Original date (YYYY-MM-DD)
            next_day_data: {
                'open': float,
                'close': float,
                'high': float,
                'low': float
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get original entry
        cursor.execute('''
        SELECT id, next_day_open FROM gamma_correlation
        WHERE symbol = ? AND timestamp = ? AND filled = 0
        ''', (symbol, date))

        result = cursor.fetchone()
        if not result:
            conn.close()
            return

        entry_id, baseline_price = result

        # Calculate metrics
        open_price = next_day_data['open']
        close_price = next_day_data['close']
        high_price = next_day_data['high']
        low_price = next_day_data['low']

        price_move_pct = ((close_price - baseline_price) / baseline_price) * 100
        intraday_range_pct = ((high_price - low_price) / baseline_price) * 100

        # Simple realized vol estimate (not annualized, just daily)
        realized_vol = abs(price_move_pct)

        cursor.execute('''
        UPDATE gamma_correlation
        SET next_day_open = ?,
            next_day_close = ?,
            next_day_high = ?,
            next_day_low = ?,
            actual_price_move_pct = ?,
            actual_intraday_range_pct = ?,
            actual_realized_vol = ?,
            filled = 1
        WHERE id = ?
        ''', (
            open_price,
            close_price,
            high_price,
            low_price,
            price_move_pct,
            intraday_range_pct,
            realized_vol,
            entry_id
        ))

        conn.commit()
        conn.close()

    def log_trade_outcome(self, symbol: str, date: str, strategy: str, pnl: float, pnl_pct: float):
        """Log if we actually traded this setup"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        UPDATE gamma_correlation
        SET strategy_taken = ?,
            pnl = ?,
            pnl_pct = ?
        WHERE symbol = ? AND timestamp = ?
        ''', (strategy, pnl, pnl_pct, symbol, date))

        conn.commit()
        conn.close()

    def get_correlation_report(self, symbol: Optional[str] = None, days: int = 30) -> pd.DataFrame:
        """
        Get correlation analysis: gamma decay % → actual price moves

        Returns DataFrame with correlations, averages, etc.
        """
        conn = sqlite3.connect(self.db_path)

        query = '''
        SELECT
            symbol,
            day_of_week,
            gamma_decay_pct,
            risk_level,
            actual_price_move_pct,
            actual_intraday_range_pct,
            actual_realized_vol,
            strategy_taken,
            pnl_pct
        FROM gamma_correlation
        WHERE filled = 1
        '''

        if symbol:
            query += f" AND symbol = '{symbol}'"

        query += f" AND timestamp >= date('now', '-{days} days')"
        query += " ORDER BY timestamp DESC"

        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return df

        # Add correlation analysis
        print(f"\n{'='*60}")
        print(f"GAMMA CORRELATION REPORT - Last {days} Days")
        if symbol:
            print(f"Symbol: {symbol}")
        print(f"{'='*60}\n")

        print("CORRELATION: Gamma Decay % → Price Move %")
        correlation = df['gamma_decay_pct'].corr(df['actual_price_move_pct'].abs())
        print(f"  Correlation: {correlation:.3f}")

        print("\nCORRELATION: Gamma Decay % → Intraday Range %")
        correlation_range = df['gamma_decay_pct'].corr(df['actual_intraday_range_pct'])
        print(f"  Correlation: {correlation_range:.3f}")

        print("\nAVERAGES BY RISK LEVEL:")
        for risk_level in ['MINIMAL', 'MODERATE', 'ELEVATED', 'EXTREME']:
            subset = df[df['risk_level'] == risk_level]
            if not subset.empty:
                avg_decay = subset['gamma_decay_pct'].mean()
                avg_move = subset['actual_price_move_pct'].abs().mean()
                avg_range = subset['actual_intraday_range_pct'].mean()
                count = len(subset)

                print(f"\n  {risk_level}:")
                print(f"    Count: {count}")
                print(f"    Avg Gamma Decay: {avg_decay:.1f}%")
                print(f"    Avg Price Move: {avg_move:.2f}%")
                print(f"    Avg Intraday Range: {avg_range:.2f}%")

        if 'strategy_taken' in df.columns and df['strategy_taken'].notna().any():
            print("\nTRADING PERFORMANCE:")
            traded = df[df['strategy_taken'].notna()]
            if not traded.empty:
                avg_pnl = traded['pnl_pct'].mean()
                win_rate = (traded['pnl_pct'] > 0).sum() / len(traded) * 100
                print(f"  Trades Taken: {len(traded)}")
                print(f"  Avg P&L: {avg_pnl:.2f}%")
                print(f"  Win Rate: {win_rate:.1f}%")

        print(f"\n{'='*60}\n")

        return df

    def backtest_thresholds(self, symbol: str, days: int = 60):
        """
        Test if our thresholds (15%, 30%, etc.) are optimal

        Returns recommended threshold adjustments based on actual data
        """
        conn = sqlite3.connect(self.db_path)

        query = f'''
        SELECT gamma_decay_pct, actual_intraday_range_pct, actual_realized_vol
        FROM gamma_correlation
        WHERE symbol = '{symbol}' AND filled = 1
        AND timestamp >= date('now', '-{days} days')
        ORDER BY gamma_decay_pct
        '''

        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) < 10:
            print("Insufficient data for backtesting (need at least 10 days)")
            return

        print(f"\n{'='*60}")
        print(f"THRESHOLD BACKTEST - {symbol} - Last {days} Days")
        print(f"{'='*60}\n")

        # Test different thresholds
        thresholds = [5, 10, 15, 20, 25, 30, 40, 50]

        print("Testing: Which gamma decay % best predicts volatility spike?\n")

        best_threshold = None
        best_separation = 0

        for threshold in thresholds:
            above = df[df['gamma_decay_pct'] >= threshold]
            below = df[df['gamma_decay_pct'] < threshold]

            if len(above) < 3 or len(below) < 3:
                continue

            avg_vol_above = above['actual_realized_vol'].mean()
            avg_vol_below = below['actual_realized_vol'].mean()
            separation = avg_vol_above - avg_vol_below

            print(f"  Threshold {threshold}%:")
            print(f"    Above: {len(above)} days, avg vol: {avg_vol_above:.2f}%")
            print(f"    Below: {len(below)} days, avg vol: {avg_vol_below:.2f}%")
            print(f"    Separation: {separation:.2f}%\n")

            if separation > best_separation:
                best_separation = separation
                best_threshold = threshold

        print(f"RECOMMENDATION: Best threshold = {best_threshold}%")
        print(f"  (Maximizes volatility separation: {best_separation:.2f}%)")
        print(f"\n{'='*60}\n")

        return best_threshold

