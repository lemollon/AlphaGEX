"""
Backtest vs Live Drift Detector
================================

Compares expected backtest performance to actual live trading results.
Detects when live performance deviates significantly from backtest expectations.

Key Metrics Compared:
1. Win Rate - Expected vs Actual
2. Average Win - Expected vs Actual
3. Average Loss - Expected vs Actual
4. Expectancy - Expected vs Actual
5. Sharpe Ratio - Expected vs Actual

Drift Detection:
- NORMAL: Actual within 20% of backtest expectations
- WARNING: Actual 20-40% worse than backtest
- CRITICAL: Actual >40% worse than backtest

Author: AlphaGEX Quant Team
Date: January 2025
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


class DriftSeverity(Enum):
    """Severity levels for performance drift"""
    NORMAL = "NORMAL"      # Within expected range
    WARNING = "WARNING"    # Moderate drift, monitor closely
    CRITICAL = "CRITICAL"  # Significant drift, investigate
    OUTPERFORM = "OUTPERFORM"  # Better than expected


@dataclass
class DriftMetric:
    """Single metric comparison"""
    metric_name: str
    backtest_value: float
    live_value: float
    drift_pct: float  # Positive = worse, Negative = better
    severity: DriftSeverity

    def to_dict(self) -> Dict:
        return {
            'metric': self.metric_name,
            'backtest': round(self.backtest_value, 2),
            'live': round(self.live_value, 2),
            'drift_pct': round(self.drift_pct, 2),
            'severity': self.severity.value
        }


@dataclass
class BotDriftReport:
    """Complete drift report for a single bot"""
    bot_name: str
    backtest_trades: int
    live_trades: int
    metrics: List[DriftMetric]
    overall_severity: DriftSeverity
    recommendations: List[str]
    analysis_date: str

    def to_dict(self) -> Dict:
        return {
            'bot_name': self.bot_name,
            'backtest_trades': self.backtest_trades,
            'live_trades': self.live_trades,
            'metrics': [m.to_dict() for m in self.metrics],
            'overall_severity': self.overall_severity.value,
            'recommendations': self.recommendations,
            'analysis_date': self.analysis_date
        }


class BacktestLiveDriftDetector:
    """
    Compares backtest expectations to live trading results.

    Usage:
        detector = BacktestLiveDriftDetector()
        report = detector.analyze_bot("ARES")

        if report.overall_severity == DriftSeverity.CRITICAL:
            # Take action - reduce position size, pause bot, etc.
            pass
    """

    # Drift thresholds (as percentages)
    WARNING_THRESHOLD = 20.0   # 20% worse triggers warning
    CRITICAL_THRESHOLD = 40.0  # 40% worse triggers critical

    def __init__(self):
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create drift analysis table if needed"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backtest_live_drift (
                    id SERIAL PRIMARY KEY,
                    bot_name VARCHAR(50) NOT NULL,
                    metric_name VARCHAR(50) NOT NULL,
                    backtest_value FLOAT,
                    live_value FLOAT,
                    drift_pct FLOAT,
                    severity VARCHAR(20),
                    analysis_date TIMESTAMP DEFAULT NOW(),
                    lookback_days INT DEFAULT 90
                )
            """)

            # Index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_drift_bot_date
                ON backtest_live_drift(bot_name, analysis_date DESC)
            """)

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to create drift table: {e}")

    def get_backtest_stats(self, bot_name: str) -> Optional[Dict]:
        """
        Get backtest statistics for a bot.

        Looks in backtest_results table for the most recent backtest.
        """
        if not DB_AVAILABLE:
            return None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get most recent backtest results
            cursor.execute("""
                SELECT
                    total_trades,
                    winning_trades,
                    win_rate,
                    expectancy_pct,
                    sharpe_ratio,
                    avg_win_pct,
                    avg_loss_pct,
                    max_drawdown_pct
                FROM backtest_results
                WHERE UPPER(strategy_name) LIKE UPPER(%s)
                ORDER BY timestamp DESC
                LIMIT 1
            """, (f'%{bot_name}%',))

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                'total_trades': row[0] or 0,
                'winning_trades': row[1] or 0,
                'win_rate': float(row[2]) if row[2] else 0.5,
                'expectancy': float(row[3]) if row[3] else 0.0,
                'sharpe_ratio': float(row[4]) if row[4] else 0.0,
                'avg_win': float(row[5]) if row[5] else 5.0,
                'avg_loss': float(row[6]) if row[6] else 5.0,
                'max_drawdown': float(row[7]) if row[7] else 20.0
            }

        except Exception as e:
            logger.error(f"Failed to get backtest stats for {bot_name}: {e}")
            return None

    def get_live_stats(self, bot_name: str, lookback_days: int = 90) -> Optional[Dict]:
        """
        Get live trading statistics for a bot.

        Queries closed trades from the last N days.
        """
        if not DB_AVAILABLE:
            return None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get live trading stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    AVG(realized_pnl_pct) as expectancy,
                    AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl_pct ELSE NULL END) as avg_win,
                    AVG(CASE WHEN realized_pnl <= 0 THEN ABS(realized_pnl_pct) ELSE NULL END) as avg_loss,
                    STDDEV(realized_pnl_pct) as pnl_stddev
                FROM autonomous_closed_trades
                WHERE UPPER(bot_name) = UPPER(%s)
                AND closed_at > NOW() - INTERVAL '%s days'
            """, (bot_name, lookback_days))

            row = cursor.fetchone()
            conn.close()

            if not row or not row[0] or row[0] == 0:
                return None

            total_trades = row[0]
            winning_trades = row[1] or 0
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.5

            # Calculate Sharpe approximation (annualized)
            expectancy = float(row[2]) if row[2] else 0.0
            pnl_stddev = float(row[5]) if row[5] else 1.0
            # Assume ~250 trading days per year
            sharpe = (expectancy * 250) / (pnl_stddev * (250 ** 0.5)) if pnl_stddev > 0 else 0.0

            return {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'win_rate': win_rate,
                'expectancy': expectancy,
                'sharpe_ratio': sharpe,
                'avg_win': float(row[3]) if row[3] else 5.0,
                'avg_loss': float(row[4]) if row[4] else 5.0
            }

        except Exception as e:
            logger.error(f"Failed to get live stats for {bot_name}: {e}")
            return None

    def calculate_drift(self, backtest_val: float, live_val: float, higher_is_better: bool = True) -> Tuple[float, DriftSeverity]:
        """
        Calculate drift percentage and severity.

        Args:
            backtest_val: Expected value from backtest
            live_val: Actual value from live trading
            higher_is_better: True for win rate, expectancy; False for losses

        Returns:
            (drift_pct, severity) - Positive drift means worse performance
        """
        if backtest_val == 0:
            return 0.0, DriftSeverity.NORMAL

        if higher_is_better:
            # For win rate, expectancy - higher is better
            # drift = (expected - actual) / expected * 100
            drift_pct = (backtest_val - live_val) / abs(backtest_val) * 100
        else:
            # For losses - lower is better
            drift_pct = (live_val - backtest_val) / abs(backtest_val) * 100

        # Determine severity
        if drift_pct < 0:
            # Negative drift = outperforming
            severity = DriftSeverity.OUTPERFORM
        elif drift_pct < self.WARNING_THRESHOLD:
            severity = DriftSeverity.NORMAL
        elif drift_pct < self.CRITICAL_THRESHOLD:
            severity = DriftSeverity.WARNING
        else:
            severity = DriftSeverity.CRITICAL

        return drift_pct, severity

    def analyze_bot(self, bot_name: str, lookback_days: int = 90) -> Optional[BotDriftReport]:
        """
        Analyze a bot's live performance vs backtest expectations.

        Args:
            bot_name: Name of the bot (ARES, ATHENA, etc.)
            lookback_days: How many days of live data to analyze

        Returns:
            BotDriftReport with detailed comparison
        """
        backtest = self.get_backtest_stats(bot_name)
        live = self.get_live_stats(bot_name, lookback_days)

        if not backtest:
            logger.warning(f"No backtest data found for {bot_name}")
            return None

        if not live:
            logger.warning(f"No live trading data found for {bot_name}")
            return None

        metrics = []

        # Win Rate comparison
        wr_drift, wr_severity = self.calculate_drift(
            backtest['win_rate'], live['win_rate'], higher_is_better=True
        )
        metrics.append(DriftMetric(
            metric_name='Win Rate',
            backtest_value=backtest['win_rate'] * 100,
            live_value=live['win_rate'] * 100,
            drift_pct=wr_drift,
            severity=wr_severity
        ))

        # Expectancy comparison
        exp_drift, exp_severity = self.calculate_drift(
            backtest['expectancy'], live['expectancy'], higher_is_better=True
        )
        metrics.append(DriftMetric(
            metric_name='Expectancy %',
            backtest_value=backtest['expectancy'],
            live_value=live['expectancy'],
            drift_pct=exp_drift,
            severity=exp_severity
        ))

        # Average Win comparison
        win_drift, win_severity = self.calculate_drift(
            backtest['avg_win'], live['avg_win'], higher_is_better=True
        )
        metrics.append(DriftMetric(
            metric_name='Avg Win %',
            backtest_value=backtest['avg_win'],
            live_value=live['avg_win'],
            drift_pct=win_drift,
            severity=win_severity
        ))

        # Average Loss comparison (lower is better)
        loss_drift, loss_severity = self.calculate_drift(
            backtest['avg_loss'], live['avg_loss'], higher_is_better=False
        )
        metrics.append(DriftMetric(
            metric_name='Avg Loss %',
            backtest_value=backtest['avg_loss'],
            live_value=live['avg_loss'],
            drift_pct=loss_drift,
            severity=loss_severity
        ))

        # Sharpe Ratio comparison
        sharpe_drift, sharpe_severity = self.calculate_drift(
            backtest['sharpe_ratio'], live['sharpe_ratio'], higher_is_better=True
        )
        metrics.append(DriftMetric(
            metric_name='Sharpe Ratio',
            backtest_value=backtest['sharpe_ratio'],
            live_value=live['sharpe_ratio'],
            drift_pct=sharpe_drift,
            severity=sharpe_severity
        ))

        # Determine overall severity (worst of all metrics)
        severities = [m.severity for m in metrics]
        if DriftSeverity.CRITICAL in severities:
            overall = DriftSeverity.CRITICAL
        elif DriftSeverity.WARNING in severities:
            overall = DriftSeverity.WARNING
        elif all(s == DriftSeverity.OUTPERFORM for s in severities):
            overall = DriftSeverity.OUTPERFORM
        else:
            overall = DriftSeverity.NORMAL

        # Generate recommendations
        recommendations = self._generate_recommendations(bot_name, metrics, overall)

        # Save to database
        self._save_analysis(bot_name, metrics, lookback_days)

        return BotDriftReport(
            bot_name=bot_name,
            backtest_trades=backtest['total_trades'],
            live_trades=live['total_trades'],
            metrics=metrics,
            overall_severity=overall,
            recommendations=recommendations,
            analysis_date=datetime.now(CENTRAL_TZ).isoformat()
        )

    def _generate_recommendations(self, bot_name: str, metrics: List[DriftMetric], overall: DriftSeverity) -> List[str]:
        """Generate actionable recommendations based on drift analysis"""
        recommendations = []

        if overall == DriftSeverity.OUTPERFORM:
            recommendations.append(f"{bot_name} is outperforming backtest expectations - consider increasing allocation")
            return recommendations

        if overall == DriftSeverity.NORMAL:
            recommendations.append(f"{bot_name} is performing within expected range - no action needed")
            return recommendations

        # Analyze specific issues
        for metric in metrics:
            if metric.severity in [DriftSeverity.WARNING, DriftSeverity.CRITICAL]:
                if metric.metric_name == 'Win Rate':
                    recommendations.append(
                        f"Win rate {metric.drift_pct:.1f}% below backtest - review entry filters and signal quality"
                    )
                elif metric.metric_name == 'Expectancy %':
                    recommendations.append(
                        f"Expectancy {metric.drift_pct:.1f}% below backtest - check exit timing and position sizing"
                    )
                elif metric.metric_name == 'Avg Win %':
                    recommendations.append(
                        f"Average wins {metric.drift_pct:.1f}% smaller - consider holding winners longer"
                    )
                elif metric.metric_name == 'Avg Loss %':
                    recommendations.append(
                        f"Average losses {metric.drift_pct:.1f}% larger - tighten stop losses"
                    )
                elif metric.metric_name == 'Sharpe Ratio':
                    recommendations.append(
                        f"Risk-adjusted returns degraded - review overall strategy parameters"
                    )

        if overall == DriftSeverity.CRITICAL:
            recommendations.append(f"CRITICAL: Consider reducing {bot_name} position sizes by 50% until drift is resolved")
            recommendations.append("Run fresh backtest to verify strategy validity in current market conditions")

        return recommendations

    def _save_analysis(self, bot_name: str, metrics: List[DriftMetric], lookback_days: int):
        """Save drift analysis to database for historical tracking"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            for metric in metrics:
                cursor.execute("""
                    INSERT INTO backtest_live_drift
                    (bot_name, metric_name, backtest_value, live_value, drift_pct, severity, lookback_days)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    bot_name,
                    metric.metric_name,
                    metric.backtest_value,
                    metric.live_value,
                    metric.drift_pct,
                    metric.severity.value,
                    lookback_days
                ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to save drift analysis: {e}")

    def analyze_all_bots(self, lookback_days: int = 90) -> Dict[str, BotDriftReport]:
        """
        Analyze all live trading bots.

        Returns:
            Dict mapping bot name to drift report
        """
        bots = ['ARES', 'ATHENA', 'ICARUS', 'PEGASUS', 'TITAN']
        reports = {}

        for bot in bots:
            report = self.analyze_bot(bot, lookback_days)
            if report:
                reports[bot] = report
                logger.info(f"{bot} drift analysis: {report.overall_severity.value}")

        return reports

    def get_drift_history(self, bot_name: str, days: int = 30) -> List[Dict]:
        """Get historical drift analysis for a bot"""
        if not DB_AVAILABLE:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT metric_name, backtest_value, live_value, drift_pct, severity, analysis_date
                FROM backtest_live_drift
                WHERE bot_name = %s
                AND analysis_date > NOW() - INTERVAL '%s days'
                ORDER BY analysis_date DESC
            """, (bot_name, days))

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    'metric': row[0],
                    'backtest': row[1],
                    'live': row[2],
                    'drift_pct': row[3],
                    'severity': row[4],
                    'date': row[5].isoformat() if row[5] else None
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to get drift history: {e}")
            return []


# Singleton instance
_drift_detector = None

def get_drift_detector() -> BacktestLiveDriftDetector:
    """Get or create the drift detector singleton"""
    global _drift_detector
    if _drift_detector is None:
        _drift_detector = BacktestLiveDriftDetector()
    return _drift_detector


def check_bot_drift(bot_name: str, lookback_days: int = 90) -> Optional[Dict]:
    """
    Convenience function to check drift for a single bot.

    Returns dict with drift analysis or None if insufficient data.
    """
    detector = get_drift_detector()
    report = detector.analyze_bot(bot_name, lookback_days)
    return report.to_dict() if report else None


def check_all_bots_drift(lookback_days: int = 90) -> Dict[str, Dict]:
    """
    Check drift for all bots.

    Returns dict mapping bot name to drift analysis.
    """
    detector = get_drift_detector()
    reports = detector.analyze_all_bots(lookback_days)
    return {name: report.to_dict() for name, report in reports.items()}
