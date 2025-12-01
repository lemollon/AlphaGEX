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
        try:
            conn = get_connection()
            c = conn.cursor()

            # Total signals - PostgreSQL syntax
            c.execute("""
                SELECT COUNT(*) FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type != 'NEUTRAL'
            """, (days,))
            row = c.fetchone()
            total_signals = row[0] if row else 0

            # Signals with outcomes
            c.execute("""
                SELECT
                    COUNT(*),
                    SUM(CASE WHEN signal_correct = true THEN 1 ELSE 0 END),
                    AVG(CASE WHEN signal_correct = true THEN price_change_1d ELSE NULL END),
                    AVG(CASE WHEN signal_correct = false THEN price_change_1d ELSE NULL END),
                    AVG(confidence_score)
                FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type != 'NEUTRAL'
                AND signal_correct IS NOT NULL
            """, (days,))
            outcomes = c.fetchone()

            total_with_outcomes = outcomes[0] if outcomes and outcomes[0] else 0
            wins = outcomes[1] if outcomes and outcomes[1] else 0
            avg_win_pct = outcomes[2] if outcomes and outcomes[2] else 0
            avg_loss_pct = outcomes[3] if outcomes and outcomes[3] else 0
            avg_confidence = outcomes[4] if outcomes and outcomes[4] else 0
            win_rate = (wins / total_with_outcomes * 100) if total_with_outcomes > 0 else 0

            # High confidence signals (>80%)
            c.execute("""
                SELECT COUNT(*) FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND confidence_score >= 80
                AND primary_regime_type != 'NEUTRAL'
            """, (days,))
            row = c.fetchone()
            high_confidence = row[0] if row else 0

            # Critical alerts
            c.execute("""
                SELECT COUNT(*) FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type IN ('GAMMA_SQUEEZE_CASCADE', 'FLIP_POINT_CRITICAL')
            """, (days,))
            row = c.fetchone()
            critical_alerts = row[0] if row else 0

            # Pattern distribution
            c.execute("""
                SELECT primary_regime_type, COUNT(*)
                FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type != 'NEUTRAL'
                GROUP BY primary_regime_type
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, (days,))

            top_patterns = [
                {'pattern': row[0], 'count': row[1]}
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
                'avg_win_pct': round(float(avg_win_pct or 0), 2),
                'avg_loss_pct': round(float(avg_loss_pct or 0), 2),
                'avg_confidence': round(float(avg_confidence or 0), 1),
                'high_confidence_signals': high_confidence,
                'critical_alerts': critical_alerts,
                'top_patterns': top_patterns
            }
        except Exception as e:
            # Return empty metrics on error
            return {
                'period_days': days,
                'total_signals': 0,
                'total_with_outcomes': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'avg_win_pct': 0,
                'avg_loss_pct': 0,
                'avg_confidence': 0,
                'high_confidence_signals': 0,
                'critical_alerts': 0,
                'top_patterns': [],
                'error': str(e)
            }

    def get_pattern_performance(self, days: int = 90) -> List[Dict]:
        """
        Get performance metrics for each pattern type

        Args:
            days: Number of days to analyze

        Returns:
            List of pattern performance data
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            # Get stats from regime_signals table - PostgreSQL syntax
            c.execute("""
                SELECT
                    primary_regime_type,
                    COUNT(*),
                    SUM(CASE WHEN signal_correct = true THEN 1 ELSE 0 END),
                    SUM(CASE WHEN signal_correct = false THEN 1 ELSE 0 END),
                    AVG(confidence_score),
                    AVG(CASE WHEN signal_correct = true THEN price_change_1d ELSE NULL END),
                    AVG(CASE WHEN signal_correct = false THEN price_change_1d ELSE NULL END),
                    MAX(price_change_1d),
                    MIN(price_change_1d)
                FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type != 'NEUTRAL'
                GROUP BY primary_regime_type
                ORDER BY COUNT(*) DESC
            """, (days,))

            patterns = []
            for row in c.fetchall():
                total = row[1] or 0
                wins = row[2] or 0
                losses = row[3] or 0
                avg_confidence = row[4] or 0
                avg_win = row[5] or 0
                avg_loss = row[6] or 0
                max_gain = row[7] or 0
                max_loss = row[8] or 0

                win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

                patterns.append({
                    'pattern_type': row[0],
                    'total_signals': total,
                    'wins': wins,
                    'losses': losses,
                    'win_rate': round(win_rate, 2),
                    'avg_confidence': round(float(avg_confidence), 1),
                    'avg_win_pct': round(float(avg_win), 2),
                    'avg_loss_pct': round(float(avg_loss), 2),
                    'max_gain_pct': round(float(max_gain), 2),
                    'max_loss_pct': round(float(max_loss), 2),
                    'expectancy': round(((wins * avg_win) + (losses * avg_loss)) / (wins + losses), 2) if (wins + losses) > 0 else 0
                })

            conn.close()
            return patterns
        except Exception as e:
            return []

    def get_historical_signals(self, limit: int = 100, pattern_type: Optional[str] = None) -> List[Dict]:
        """
        Get historical signals with full details

        Args:
            limit: Maximum number of signals to return
            pattern_type: Filter by specific pattern type (optional)

        Returns:
            List of historical signals
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            # Query without vix_change_pct which may not exist
            if pattern_type:
                c.execute("""
                    SELECT
                        timestamp, spy_price, primary_regime_type, confidence_score,
                        trade_direction, risk_level, description,
                        price_change_1d, price_change_5d, signal_correct
                    FROM regime_signals
                    WHERE primary_regime_type = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (pattern_type, limit))
            else:
                c.execute("""
                    SELECT
                        timestamp, spy_price, primary_regime_type, confidence_score,
                        trade_direction, risk_level, description,
                        price_change_1d, price_change_5d, signal_correct
                    FROM regime_signals
                    WHERE primary_regime_type != 'NEUTRAL'
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (limit,))

            signals = []
            for row in c.fetchall():
                signals.append({
                    'timestamp': str(row[0]) if row[0] else None,
                    'price': float(row[1]) if row[1] else None,
                    'pattern': row[2],
                    'confidence': float(row[3]) if row[3] else None,
                    'direction': row[4],
                    'risk_level': row[5],
                    'description': row[6],
                    'outcome_1d': float(row[7]) if row[7] else None,
                    'outcome_5d': float(row[8]) if row[8] else None,
                    'correct': row[9]
                })

            conn.close()
            return signals
        except Exception as e:
            return []

    def get_chart_data(self, days: int = 90) -> Dict:
        """
        Get time series data for performance charts

        Args:
            days: Number of days of data

        Returns:
            Dict with chart data
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            # Daily signal count - PostgreSQL syntax
            c.execute("""
                SELECT
                    DATE(timestamp),
                    COUNT(*),
                    SUM(CASE WHEN confidence_score >= 80 THEN 1 ELSE 0 END),
                    AVG(confidence_score)
                FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type != 'NEUTRAL'
                GROUP BY DATE(timestamp)
                ORDER BY DATE(timestamp) ASC
            """, (days,))

            daily_signals = [
                {
                    'date': str(row[0]),
                    'count': row[1] or 0,
                    'high_confidence': row[2] or 0,
                    'avg_confidence': round(float(row[3] or 0), 1)
                }
                for row in c.fetchall()
            ]

            # Cumulative win rate over time
            c.execute("""
                SELECT
                    DATE(timestamp),
                    SUM(CASE WHEN signal_correct = true THEN 1 ELSE 0 END),
                    COUNT(*)
                FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type != 'NEUTRAL'
                AND signal_correct IS NOT NULL
                GROUP BY DATE(timestamp)
                ORDER BY DATE(timestamp) ASC
            """, (days,))

            cumulative_wins = 0
            cumulative_total = 0
            win_rate_timeline = []

            for row in c.fetchall():
                cumulative_wins += row[1] or 0
                cumulative_total += row[2] or 0

                win_rate = (cumulative_wins / cumulative_total * 100) if cumulative_total > 0 else 0

                win_rate_timeline.append({
                    'date': str(row[0]),
                    'win_rate': round(win_rate, 2),
                    'total_signals': cumulative_total
                })

            # Pattern distribution over time
            c.execute("""
                SELECT
                    DATE(timestamp),
                    primary_regime_type,
                    COUNT(*)
                FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND primary_regime_type != 'NEUTRAL'
                GROUP BY DATE(timestamp), primary_regime_type
                ORDER BY DATE(timestamp) ASC
            """, (days,))

            pattern_timeline = {}
            for row in c.fetchall():
                date = str(row[0])
                pattern = row[1]

                if date not in pattern_timeline:
                    pattern_timeline[date] = {}

                pattern_timeline[date][pattern] = row[2]

            conn.close()

            return {
                'daily_signals': daily_signals,
                'win_rate_timeline': win_rate_timeline,
                'pattern_timeline': pattern_timeline
            }
        except Exception as e:
            return {
                'daily_signals': [],
                'win_rate_timeline': [],
                'pattern_timeline': {}
            }

    def get_vix_correlation(self, days: int = 90) -> Dict:
        """
        Analyze correlation between VIX levels and pattern performance

        Args:
            days: Number of days to analyze

        Returns:
            Dict with VIX correlation data
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            # Performance by VIX level - PostgreSQL syntax
            c.execute("""
                SELECT
                    CASE
                        WHEN vix_current < 15 THEN 'Low (<15)'
                        WHEN vix_current < 20 THEN 'Normal (15-20)'
                        WHEN vix_current < 30 THEN 'Elevated (20-30)'
                        ELSE 'High (>30)'
                    END,
                    COUNT(*),
                    SUM(CASE WHEN signal_correct = true THEN 1 ELSE 0 END),
                    AVG(price_change_1d)
                FROM regime_signals
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                AND vix_current IS NOT NULL
                AND signal_correct IS NOT NULL
                GROUP BY 1
            """, (days,))

            vix_performance = []
            for row in c.fetchall():
                total = row[1] or 0
                wins = row[2] or 0
                win_rate = (wins / total * 100) if total > 0 else 0

                vix_performance.append({
                    'vix_level': row[0],
                    'total_signals': total,
                    'win_rate': round(win_rate, 2),
                    'avg_price_change': round(float(row[3] or 0), 2)
                })

            conn.close()

            return {
                'by_vix_level': vix_performance,
                'by_spike_status': []  # vix_spike_detected column may not exist
            }
        except Exception as e:
            return {
                'by_vix_level': [],
                'by_spike_status': []
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
