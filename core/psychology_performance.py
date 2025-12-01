"""
Psychology Trap Performance Tracking API

This module provides endpoints for tracking and analyzing the performance
of psychology trap detection patterns over time.

Endpoints:
- GET /api/psychology/performance/overview - Overall performance metrics
- GET /api/psychology/performance/by-pattern - Win rates by pattern type
- GET /api/psychology/performance/signals - Historical signals with outcomes
- GET /api/psychology/performance/chart-data - Time series data for charts
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database_adapter import get_connection


class PerformanceTracker:
    """Track and analyze psychology trap detection performance"""

    def get_overview_metrics(self, days: int = 30) -> Dict:
        """
        Get overall performance metrics for the last N days

        Args:
            days: Number of days to analyze (default 30)

        Returns:
            Dict with overall metrics
        """
        conn = get_connection()
        
        c = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Total signals
        c.execute('''
            SELECT COUNT(*) as total FROM regime_signals
            WHERE timestamp >= ? AND primary_regime_type != 'NEUTRAL'
        ''', (cutoff_date,))
        total_signals = c.fetchone()['total']

        # Signals with outcomes (from backtest or live tracking)
        c.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
                AVG(CASE WHEN signal_correct = 1 THEN price_change_1d ELSE NULL END) as avg_win_pct,
                AVG(CASE WHEN signal_correct = 0 THEN price_change_1d ELSE NULL END) as avg_loss_pct,
                AVG(confidence_score) as avg_confidence
            FROM regime_signals
            WHERE timestamp >= ?
            AND primary_regime_type != 'NEUTRAL'
            AND signal_correct IS NOT NULL
        ''', (cutoff_date,))

        outcomes = c.fetchone()

        total_with_outcomes = outcomes['total'] if outcomes['total'] else 0
        wins = outcomes['wins'] if outcomes['wins'] else 0
        win_rate = (wins / total_with_outcomes * 100) if total_with_outcomes > 0 else 0

        # High confidence signals (>80%)
        c.execute('''
            SELECT COUNT(*) as count FROM regime_signals
            WHERE timestamp >= ?
            AND confidence_score >= 80
            AND primary_regime_type != 'NEUTRAL'
        ''', (cutoff_date,))
        high_confidence = c.fetchone()['count']

        # Critical alerts (GAMMA_SQUEEZE_CASCADE, FLIP_POINT_CRITICAL)
        c.execute('''
            SELECT COUNT(*) as count FROM regime_signals
            WHERE timestamp >= ?
            AND primary_regime_type IN ('GAMMA_SQUEEZE_CASCADE', 'FLIP_POINT_CRITICAL')
        ''', (cutoff_date,))
        critical_alerts = c.fetchone()['count']

        # Pattern distribution
        c.execute('''
            SELECT primary_regime_type, COUNT(*) as count
            FROM regime_signals
            WHERE timestamp >= ? AND primary_regime_type != 'NEUTRAL'
            GROUP BY primary_regime_type
            ORDER BY count DESC
            LIMIT 5
        ''', (cutoff_date,))

        top_patterns = [
            {'pattern': row['primary_regime_type'], 'count': row['count']}
            for row in c.fetchall()
        ]

        conn.close()

        return {
            'period_days': days,
            'total_signals': total_signals,
            'total_with_outcomes': total_with_outcomes,
            'wins': wins,
            'losses': total_with_outcomes - wins,
            'win_rate': round(win_rate, 2),
            'avg_win_pct': round(outcomes['avg_win_pct'] or 0, 2),
            'avg_loss_pct': round(outcomes['avg_loss_pct'] or 0, 2),
            'avg_confidence': round(outcomes['avg_confidence'] or 0, 1),
            'high_confidence_signals': high_confidence,
            'critical_alerts': critical_alerts,
            'top_patterns': top_patterns
        }

    def get_pattern_performance(self, days: int = 90) -> List[Dict]:
        """
        Get performance metrics for each pattern type

        Args:
            days: Number of days to analyze

        Returns:
            List of pattern performance data
        """
        conn = get_connection()
        
        c = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Get stats from regime_signals table
        c.execute('''
            SELECT
                primary_regime_type,
                COUNT(*) as total_signals,
                SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN signal_correct = 0 THEN 1 ELSE 0 END) as losses,
                AVG(confidence_score) as avg_confidence,
                AVG(CASE WHEN signal_correct = 1 THEN price_change_1d ELSE NULL END) as avg_win,
                AVG(CASE WHEN signal_correct = 0 THEN price_change_1d ELSE NULL END) as avg_loss,
                MAX(price_change_1d) as max_gain,
                MIN(price_change_1d) as max_loss
            FROM regime_signals
            WHERE timestamp >= ?
            AND primary_regime_type != 'NEUTRAL'
            GROUP BY primary_regime_type
            ORDER BY total_signals DESC
        ''', (cutoff_date,))

        patterns = []
        for row in c.fetchall():
            total = row['total_signals']
            wins = row['wins'] if row['wins'] else 0
            losses = row['losses'] if row['losses'] else 0

            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

            patterns.append({
                'pattern_type': row['primary_regime_type'],
                'total_signals': total,
                'wins': wins,
                'losses': losses,
                'win_rate': round(win_rate, 2),
                'avg_confidence': round(row['avg_confidence'] or 0, 1),
                'avg_win_pct': round(row['avg_win'] or 0, 2),
                'avg_loss_pct': round(row['avg_loss'] or 0, 2),
                'max_gain_pct': round(row['max_gain'] or 0, 2),
                'max_loss_pct': round(row['max_loss'] or 0, 2),
                'expectancy': round(((wins * (row['avg_win'] or 0)) + (losses * (row['avg_loss'] or 0))) / (wins + losses), 2) if (wins + losses) > 0 else 0
            })

        conn.close()
        return patterns

    def get_historical_signals(self, limit: int = 100, pattern_type: Optional[str] = None) -> List[Dict]:
        """
        Get historical signals with full details

        Args:
            limit: Maximum number of signals to return
            pattern_type: Filter by specific pattern type (optional)

        Returns:
            List of historical signals
        """
        conn = get_connection()
        
        c = conn.cursor()

        if pattern_type:
            c.execute('''
                SELECT
                    timestamp, spy_price, primary_regime_type, confidence_score,
                    trade_direction, risk_level, description, psychology_trap,
                    price_change_1d, price_change_5d, signal_correct,
                    vix_current, vix_change_pct, volatility_regime
                FROM regime_signals
                WHERE primary_regime_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (pattern_type, limit))
        else:
            c.execute('''
                SELECT
                    timestamp, spy_price, primary_regime_type, confidence_score,
                    trade_direction, risk_level, description, psychology_trap,
                    price_change_1d, price_change_5d, signal_correct,
                    vix_current, vix_change_pct, volatility_regime
                FROM regime_signals
                WHERE primary_regime_type != 'NEUTRAL'
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

        signals = []
        for row in c.fetchall():
            signals.append({
                'timestamp': row['timestamp'],
                'price': row['spy_price'],
                'pattern': row['primary_regime_type'],
                'confidence': row['confidence_score'],
                'direction': row['trade_direction'],
                'risk_level': row['risk_level'],
                'description': row['description'],
                'psychology_trap': row['psychology_trap'],
                'outcome_1d': row['price_change_1d'],
                'outcome_5d': row['price_change_5d'],
                'correct': row['signal_correct'],
                'vix': row['vix_current'],
                'vix_change': row['vix_change_pct'],
                'vol_regime': row['volatility_regime']
            })

        conn.close()
        return signals

    def get_chart_data(self, days: int = 90) -> Dict:
        """
        Get time series data for performance charts

        Args:
            days: Number of days of data

        Returns:
            Dict with chart data
        """
        conn = get_connection()
        
        c = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Daily signal count
        c.execute('''
            SELECT
                DATE(timestamp) as date,
                COUNT(*) as count,
                SUM(CASE WHEN confidence_score >= 80 THEN 1 ELSE 0 END) as high_confidence,
                AVG(confidence_score) as avg_confidence
            FROM regime_signals
            WHERE timestamp >= ? AND primary_regime_type != 'NEUTRAL'
            GROUP BY DATE(timestamp)
            ORDER BY date ASC
        ''', (cutoff_date,))

        daily_signals = [
            {
                'date': row['date'],
                'count': row['count'],
                'high_confidence': row['high_confidence'],
                'avg_confidence': round(row['avg_confidence'], 1)
            }
            for row in c.fetchall()
        ]

        # Cumulative win rate over time
        c.execute('''
            SELECT
                DATE(timestamp) as date,
                SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
                COUNT(*) as total
            FROM regime_signals
            WHERE timestamp >= ?
            AND primary_regime_type != 'NEUTRAL'
            AND signal_correct IS NOT NULL
            GROUP BY DATE(timestamp)
            ORDER BY date ASC
        ''', (cutoff_date,))

        cumulative_wins = 0
        cumulative_total = 0
        win_rate_timeline = []

        for row in c.fetchall():
            cumulative_wins += row['wins']
            cumulative_total += row['total']

            win_rate = (cumulative_wins / cumulative_total * 100) if cumulative_total > 0 else 0

            win_rate_timeline.append({
                'date': row['date'],
                'win_rate': round(win_rate, 2),
                'total_signals': cumulative_total
            })

        # Pattern distribution over time
        c.execute('''
            SELECT
                DATE(timestamp) as date,
                primary_regime_type,
                COUNT(*) as count
            FROM regime_signals
            WHERE timestamp >= ? AND primary_regime_type != 'NEUTRAL'
            GROUP BY DATE(timestamp), primary_regime_type
            ORDER BY date ASC
        ''', (cutoff_date,))

        pattern_timeline = {}
        for row in c.fetchall():
            date = row['date']
            pattern = row['primary_regime_type']

            if date not in pattern_timeline:
                pattern_timeline[date] = {}

            pattern_timeline[date][pattern] = row['count']

        conn.close()

        return {
            'daily_signals': daily_signals,
            'win_rate_timeline': win_rate_timeline,
            'pattern_timeline': pattern_timeline
        }

    def get_vix_correlation(self, days: int = 90) -> Dict:
        """
        Analyze correlation between VIX levels and pattern performance

        Args:
            days: Number of days to analyze

        Returns:
            Dict with VIX correlation data
        """
        conn = get_connection()
        
        c = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Performance by VIX level
        c.execute('''
            SELECT
                CASE
                    WHEN vix_current < 15 THEN 'Low (<15)'
                    WHEN vix_current < 20 THEN 'Normal (15-20)'
                    WHEN vix_current < 30 THEN 'Elevated (20-30)'
                    ELSE 'High (>30)'
                END as vix_level,
                COUNT(*) as total,
                SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
                AVG(price_change_1d) as avg_change
            FROM regime_signals
            WHERE timestamp >= ?
            AND vix_current IS NOT NULL
            AND signal_correct IS NOT NULL
            GROUP BY vix_level
        ''', (cutoff_date,))

        vix_performance = []
        for row in c.fetchall():
            total = row['total']
            wins = row['wins'] if row['wins'] else 0
            win_rate = (wins / total * 100) if total > 0 else 0

            vix_performance.append({
                'vix_level': row['vix_level'],
                'total_signals': total,
                'win_rate': round(win_rate, 2),
                'avg_price_change': round(row['avg_change'] or 0, 2)
            })

        # Performance when VIX spike detected
        c.execute('''
            SELECT
                vix_spike_detected,
                COUNT(*) as total,
                SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
                AVG(price_change_1d) as avg_change
            FROM regime_signals
            WHERE timestamp >= ?
            AND vix_spike_detected IS NOT NULL
            AND signal_correct IS NOT NULL
            GROUP BY vix_spike_detected
        ''', (cutoff_date,))

        spike_performance = []
        for row in c.fetchall():
            total = row['total']
            wins = row['wins'] if row['wins'] else 0
            win_rate = (wins / total * 100) if total > 0 else 0

            spike_performance.append({
                'vix_spike': bool(row['vix_spike_detected']),
                'total_signals': total,
                'win_rate': round(win_rate, 2),
                'avg_price_change': round(row['avg_change'] or 0, 2)
            })

        conn.close()

        return {
            'by_vix_level': vix_performance,
            'by_spike_status': spike_performance
        }


# Singleton instance
performance_tracker = PerformanceTracker()


# Wrapper functions for API routes compatibility
def get_performance_overview(days: int = 30) -> Dict:
    """Get overall performance overview - wrapper for API routes"""
    return performance_tracker.get_overview_metrics(days)


def get_performance_by_pattern(days: int = 90) -> Dict:
    """Get performance by pattern type - wrapper for API routes"""
    patterns = performance_tracker.get_pattern_performance(days)
    return {"patterns": patterns}


def get_recent_signals(limit: int = 100, pattern_type: Optional[str] = None) -> Dict:
    """Get recent signals - wrapper for API routes"""
    signals = performance_tracker.get_historical_signals(limit, pattern_type)
    return {"signals": signals, "count": len(signals)}


def get_chart_data(days: int = 90) -> Dict:
    """Get chart data - wrapper for API routes"""
    return performance_tracker.get_chart_data(days)


def get_vix_correlation(days: int = 90) -> Dict:
    """Get VIX correlation - wrapper for API routes"""
    return performance_tracker.get_vix_correlation(days)
