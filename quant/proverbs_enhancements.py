"""
PROVERBS Enhancement Module
============================

Advanced features for the Proverbs Feedback Loop Intelligence System:
- Consecutive loss auto-kill trigger
- Max daily loss auto-kill
- Daily performance digest
- Version performance comparison
- Regime-aware learning tracking
- Cross-bot correlation analysis
- Time-of-day performance analysis
- A/B testing framework
- Approval tiers (auto-approve low risk)
- Rollback cooldown period
- Weekend pre-check analysis

Author: AlphaGEX Quant
Date: 2024-12
"""

from __future__ import annotations

import os
import sys
import json
import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_connection = None


# =============================================================================
# ENHANCED GUARDRAILS
# =============================================================================

ENHANCED_GUARDRAILS = {
    # Consecutive loss limits
    'max_consecutive_losses': 5,
    'consecutive_loss_kill_threshold': 3,  # Kill after 3 in a row

    # Daily loss limits
    'max_daily_loss_dollars': 5000,
    'max_daily_loss_percent': 5.0,

    # Approval tiers
    'auto_approve_low_risk': True,
    'auto_approve_max_change_pct': 5.0,

    # Rollback cooldown
    'rollback_cooldown_hours': 24,
    'max_rollbacks_per_day': 3,

    # A/B Testing
    'ab_test_min_duration_days': 7,
    'ab_test_min_trades': 20,
    'ab_test_confidence_threshold': 0.95,
}


# =============================================================================
# DATA CLASSES FOR ENHANCEMENTS
# =============================================================================

@dataclass
class ConsecutiveLossTracker:
    """Track consecutive losses per bot"""
    bot_name: str
    consecutive_losses: int = 0
    last_loss_date: Optional[str] = None
    total_loss_streak_pnl: float = 0.0
    triggered_kill: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DailyLossTracker:
    """Track daily P&L per bot"""
    bot_name: str
    date: str
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    triggered_kill: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class VersionPerformance:
    """Performance metrics for a specific version"""
    version_id: str
    bot_name: str
    period_start: str
    period_end: str
    total_trades: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    sharpe_ratio: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ABTest:
    """A/B test between two configurations"""
    test_id: str
    bot_name: str
    created_at: str

    # Configurations
    control_config: Dict
    variant_config: Dict

    # Allocation
    control_allocation: float = 0.5

    # Results
    control_trades: int = 0
    variant_trades: int = 0
    control_win_rate: float = 0.0
    variant_win_rate: float = 0.0
    control_pnl: float = 0.0
    variant_pnl: float = 0.0

    # Status
    status: str = "RUNNING"  # RUNNING, COMPLETED, STOPPED
    winner: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TimeOfDayAnalysis:
    """Performance analysis by time of day"""
    bot_name: str
    hour: int
    trades_count: int
    win_rate: float
    avg_pnl: float
    best_performance: bool = False
    worst_performance: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CrossBotCorrelation:
    """Correlation between bot performances"""
    bot_a: str
    bot_b: str
    correlation: float
    period_days: int
    sample_size: int

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RegimePerformance:
    """Performance by market regime"""
    bot_name: str
    regime: str  # TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE
    trades_count: int
    win_rate: float
    avg_pnl: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class WeekendPreCheck:
    """Pre-weekend analysis for upcoming week"""
    analysis_date: str

    # Market context
    vix_level: float
    market_trend: str
    upcoming_events: List[str]

    # Bot recommendations
    bot_recommendations: Dict[str, Dict]  # bot -> {action, reason, confidence}

    # Risk assessment
    overall_risk: str  # LOW, MEDIUM, HIGH
    risk_factors: List[str]

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# CONSECUTIVE LOSS AUTO-KILL
# =============================================================================

class ConsecutiveLossMonitor:
    """Monitor and respond to consecutive losses"""

    def __init__(self, proverbs):
        self.proverbs = proverbs
        self._trackers: Dict[str, ConsecutiveLossTracker] = {}

    def _get_tracker(self, bot_name: str) -> ConsecutiveLossTracker:
        """Get or create tracker for bot"""
        if bot_name not in self._trackers:
            self._trackers[bot_name] = ConsecutiveLossTracker(bot_name=bot_name)
        return self._trackers[bot_name]

    def record_trade_outcome(
        self,
        bot_name: str,
        pnl: float,
        trade_date: str
    ) -> Optional[Dict]:
        """
        Record a trade outcome and check for consecutive losses.

        Kill switch activation removed - only tracks and logs consecutive losses.
        """
        tracker = self._get_tracker(bot_name)

        if pnl < 0:
            # Loss - increment counter
            tracker.consecutive_losses += 1
            tracker.total_loss_streak_pnl += pnl
            tracker.last_loss_date = trade_date

            logger.info(f"{bot_name}: Consecutive loss #{tracker.consecutive_losses} (${pnl:,.2f})")

            # Log warning at threshold but do NOT activate kill switch
            if tracker.consecutive_losses >= ENHANCED_GUARDRAILS['consecutive_loss_kill_threshold']:
                logger.warning(
                    f"{bot_name}: {tracker.consecutive_losses} consecutive losses "
                    f"(${tracker.total_loss_streak_pnl:,.2f}) - kill switch DISABLED, continuing to trade"
                )
        else:
            # Win - reset counter
            if tracker.consecutive_losses > 0:
                logger.info(f"{bot_name}: Loss streak broken after {tracker.consecutive_losses} losses")

            tracker.consecutive_losses = 0
            tracker.total_loss_streak_pnl = 0.0
            tracker.triggered_kill = False

        return None

    def get_status(self, bot_name: str = None) -> Dict:
        """Get consecutive loss status"""
        if bot_name:
            tracker = self._get_tracker(bot_name)
            return tracker.to_dict()

        return {name: t.to_dict() for name, t in self._trackers.items()}

    def reset(self, bot_name: str) -> None:
        """Reset tracker for bot"""
        if bot_name in self._trackers:
            self._trackers[bot_name] = ConsecutiveLossTracker(bot_name=bot_name)


# =============================================================================
# DAILY LOSS AUTO-KILL
# =============================================================================

class DailyLossMonitor:
    """Monitor and respond to daily P&L limits"""

    def __init__(self, proverbs):
        self.proverbs = proverbs
        self._trackers: Dict[str, DailyLossTracker] = {}

    def _get_today(self) -> str:
        return datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

    def _get_tracker(self, bot_name: str) -> DailyLossTracker:
        """Get or create tracker for today"""
        key = f"{bot_name}_{self._get_today()}"

        if key not in self._trackers:
            self._trackers[key] = DailyLossTracker(
                bot_name=bot_name,
                date=self._get_today()
            )

        return self._trackers[key]

    def record_trade(
        self,
        bot_name: str,
        pnl: float,
        capital_base: float = 100000.0
    ) -> Optional[Dict]:
        """
        Record a trade and check daily limits.

        Kill switch activation removed - only tracks and logs daily P&L.
        """
        tracker = self._get_tracker(bot_name)

        # Update tracker
        tracker.trades_count += 1
        tracker.total_pnl += pnl

        if pnl > 0:
            tracker.winning_trades += 1
        else:
            tracker.losing_trades += 1

        # Log warnings at limits but do NOT activate kill switches
        if tracker.total_pnl <= -ENHANCED_GUARDRAILS['max_daily_loss_dollars']:
            logger.warning(
                f"{bot_name}: Daily loss ${tracker.total_pnl:,.2f} exceeds "
                f"${ENHANCED_GUARDRAILS['max_daily_loss_dollars']:,.2f} limit - "
                f"kill switch DISABLED, continuing to trade"
            )

        loss_pct = abs(tracker.total_pnl) / capital_base * 100 if tracker.total_pnl < 0 else 0
        if tracker.total_pnl < 0 and loss_pct >= ENHANCED_GUARDRAILS['max_daily_loss_percent']:
            logger.warning(
                f"{bot_name}: Daily loss {loss_pct:.1f}% exceeds "
                f"{ENHANCED_GUARDRAILS['max_daily_loss_percent']:.1f}% limit - "
                f"kill switch DISABLED, continuing to trade"
            )

        return None

                self.proverbs.activate_kill_switch(
                    bot_name=bot_name,
                    reason=f"Daily loss % limit reached: {loss_pct:.1f}% (limit: {ENHANCED_GUARDRAILS['max_daily_loss_percent']:.1f}%)",
                    killed_by="PROVERBS_AUTO"
                )

                return alert

        return None

    def get_status(self, bot_name: str = None) -> Dict:
        """Get daily loss status"""
        today = self._get_today()

        if bot_name:
            key = f"{bot_name}_{today}"
            if key in self._trackers:
                return self._trackers[key].to_dict()
            return DailyLossTracker(bot_name=bot_name, date=today).to_dict()

        return {
            k: v.to_dict()
            for k, v in self._trackers.items()
            if v.date == today
        }


# =============================================================================
# VERSION PERFORMANCE COMPARISON
# =============================================================================

class VersionComparer:
    """Compare performance across versions"""

    def __init__(self, proverbs):
        self.proverbs = proverbs

    def compare_versions(
        self,
        bot_name: str,
        version_a_id: str,
        version_b_id: str
    ) -> Dict:
        """Compare two versions head-to-head"""
        if not DB_AVAILABLE:
            return {'error': 'Database not available'}

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get performance for each version
            results = {}
            for version_id, label in [(version_a_id, 'A'), (version_b_id, 'B')]:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        AVG(win_rate) as avg_win_rate,
                        SUM(total_pnl) as total_pnl,
                        AVG(CASE WHEN total_pnl > 0 THEN total_pnl END) as avg_win,
                        AVG(CASE WHEN total_pnl < 0 THEN total_pnl END) as avg_loss
                    FROM proverbs_performance
                    WHERE version_id = %s
                """, (version_id,))

                row = cursor.fetchone()
                if row:
                    results[label] = {
                        'version_id': version_id,
                        'total_snapshots': row[0] or 0,
                        'avg_win_rate': float(row[1]) if row[1] else 0,
                        'total_pnl': float(row[2]) if row[2] else 0,
                        'avg_win': float(row[3]) if row[3] else 0,
                        'avg_loss': float(row[4]) if row[4] else 0
                    }

            conn.close()

            # Calculate comparison
            if 'A' in results and 'B' in results:
                a, b = results['A'], results['B']

                comparison = {
                    'version_a': a,
                    'version_b': b,
                    'winner': None,
                    'metrics': {}
                }

                # Compare each metric
                if a['avg_win_rate'] > b['avg_win_rate']:
                    comparison['metrics']['win_rate'] = 'A'
                elif b['avg_win_rate'] > a['avg_win_rate']:
                    comparison['metrics']['win_rate'] = 'B'
                else:
                    comparison['metrics']['win_rate'] = 'TIE'

                if a['total_pnl'] > b['total_pnl']:
                    comparison['metrics']['total_pnl'] = 'A'
                elif b['total_pnl'] > a['total_pnl']:
                    comparison['metrics']['total_pnl'] = 'B'
                else:
                    comparison['metrics']['total_pnl'] = 'TIE'

                # Determine overall winner
                a_wins = sum(1 for v in comparison['metrics'].values() if v == 'A')
                b_wins = sum(1 for v in comparison['metrics'].values() if v == 'B')

                if a_wins > b_wins:
                    comparison['winner'] = 'A'
                elif b_wins > a_wins:
                    comparison['winner'] = 'B'
                else:
                    comparison['winner'] = 'TIE'

                return comparison

            return {'error': 'Could not retrieve performance data for both versions'}

        except Exception as e:
            logger.error(f"Failed to compare versions: {e}")
            return {'error': str(e)}

    def get_version_performance_history(
        self,
        bot_name: str,
        days: int = 30
    ) -> List[VersionPerformance]:
        """Get performance history grouped by version"""
        if not DB_AVAILABLE:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    version_id,
                    MIN(timestamp) as period_start,
                    MAX(timestamp) as period_end,
                    SUM(total_trades) as total_trades,
                    AVG(win_rate) as avg_win_rate,
                    SUM(total_pnl) as total_pnl,
                    AVG(avg_win) as avg_win,
                    AVG(avg_loss) as avg_loss,
                    MAX(max_drawdown) as max_drawdown,
                    AVG(sharpe_ratio) as sharpe_ratio
                FROM proverbs_performance
                WHERE bot_name = %s
                AND timestamp > NOW() - INTERVAL '%s days'
                AND version_id IS NOT NULL
                GROUP BY version_id
                ORDER BY period_start DESC
            """, (bot_name, days))

            rows = cursor.fetchall()
            conn.close()

            results = []
            for row in rows:
                results.append(VersionPerformance(
                    version_id=row[0],
                    bot_name=bot_name,
                    period_start=row[1].isoformat() if row[1] else '',
                    period_end=row[2].isoformat() if row[2] else '',
                    total_trades=row[3] or 0,
                    win_rate=float(row[4]) if row[4] else 0,
                    total_pnl=float(row[5]) if row[5] else 0,
                    avg_win=float(row[6]) if row[6] else 0,
                    avg_loss=float(row[7]) if row[7] else 0,
                    max_drawdown=float(row[8]) if row[8] else 0,
                    sharpe_ratio=float(row[9]) if row[9] else 0
                ))

            return results

        except Exception as e:
            logger.error(f"Failed to get version performance history: {e}")
            return []


# =============================================================================
# TIME OF DAY ANALYSIS
# =============================================================================

class TimeOfDayAnalyzer:
    """Analyze performance by time of day"""

    def __init__(self, proverbs):
        self.proverbs = proverbs

    def analyze(self, bot_name: str, days: int = 30) -> List[TimeOfDayAnalysis]:
        """Analyze performance by hour of day"""
        if not DB_AVAILABLE:
            return []

        # Map bot names to their actual position tables
        BOT_TABLES = {
            'FORTRESS': 'fortress_positions',
            'SOLOMON': 'solomon_positions',
            'SAMSON': 'samson_positions',
            'ANCHOR': 'anchor_positions',
            'GIDEON': 'gideon_positions',
            'JUBILEE': 'jubilee_ic_positions',
        }

        table_name = BOT_TABLES.get(bot_name.upper())
        if not table_name:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get trades with hour info - using bot-specific positions table
            # Cast to timestamptz to handle FORTRESS TEXT columns and other bots' timestamp columns
            cursor.execute(f"""
                SELECT
                    EXTRACT(HOUR FROM close_time::timestamptz AT TIME ZONE 'America/Chicago') as hour,
                    COUNT(*) as trades,
                    AVG(CASE WHEN realized_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                    AVG(realized_pnl) as avg_pnl
                FROM {table_name}
                WHERE status = 'closed'
                AND close_time::timestamptz > NOW() - INTERVAL '{days} days'
                GROUP BY EXTRACT(HOUR FROM close_time::timestamptz AT TIME ZONE 'America/Chicago')
                ORDER BY hour
            """)

            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return []

            results = []
            best_hour = None
            worst_hour = None
            best_pnl = float('-inf')
            worst_pnl = float('inf')

            for row in rows:
                hour, trades, win_rate, avg_pnl = row

                if avg_pnl and avg_pnl > best_pnl:
                    best_pnl = avg_pnl
                    best_hour = hour

                if avg_pnl and avg_pnl < worst_pnl:
                    worst_pnl = avg_pnl
                    worst_hour = hour

                results.append(TimeOfDayAnalysis(
                    bot_name=bot_name,
                    hour=int(hour),
                    trades_count=trades or 0,
                    win_rate=float(win_rate) if win_rate else 0,
                    avg_pnl=float(avg_pnl) if avg_pnl else 0
                ))

            # Mark best/worst
            for r in results:
                r.best_performance = (r.hour == best_hour)
                r.worst_performance = (r.hour == worst_hour)

            return results

        except Exception as e:
            logger.error(f"Failed to analyze time of day: {e}")
            return []


# =============================================================================
# CROSS-BOT CORRELATION
# =============================================================================

class CrossBotAnalyzer:
    """Analyze correlations between bots"""

    def __init__(self, proverbs):
        self.proverbs = proverbs

    def calculate_correlation(
        self,
        bot_a: str,
        bot_b: str,
        days: int = 30
    ) -> Optional[CrossBotCorrelation]:
        """Calculate performance correlation between two bots"""
        if not DB_AVAILABLE:
            return None

        # Map bot names to their actual position tables
        BOT_TABLES = {
            'FORTRESS': 'fortress_positions',
            'SOLOMON': 'solomon_positions',
            'SAMSON': 'samson_positions',
            'ANCHOR': 'anchor_positions',
            'GIDEON': 'gideon_positions',
            'JUBILEE': 'jubilee_ic_positions',
        }

        table_a = BOT_TABLES.get(bot_a.upper())
        table_b = BOT_TABLES.get(bot_b.upper())
        if not table_a or not table_b:
            return None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get daily P&L for each bot from their respective tables
            # Cast to timestamptz to handle FORTRESS TEXT columns and other bots' timestamp columns
            cursor.execute(f"""
                WITH daily_a AS (
                    SELECT
                        DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') as trade_date,
                        SUM(realized_pnl) as daily_pnl
                    FROM {table_a}
                    WHERE status = 'closed'
                    AND close_time::timestamptz > NOW() - INTERVAL '{days} days'
                    GROUP BY DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago')
                ),
                daily_b AS (
                    SELECT
                        DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') as trade_date,
                        SUM(realized_pnl) as daily_pnl
                    FROM {table_b}
                    WHERE status = 'closed'
                    AND close_time::timestamptz > NOW() - INTERVAL '{days} days'
                    GROUP BY DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago')
                )
                SELECT
                    a.trade_date,
                    a.daily_pnl as a_pnl,
                    b.daily_pnl as b_pnl
                FROM daily_a a
                JOIN daily_b b ON a.trade_date = b.trade_date
                ORDER BY a.trade_date
            """)

            rows = cursor.fetchall()
            conn.close()

            if len(rows) < 5:
                return None

            # Calculate correlation manually
            # Convert Decimal to float (PostgreSQL returns decimal.Decimal for numeric fields)
            a_values = [float(r[1]) if r[1] is not None else 0.0 for r in rows]
            b_values = [float(r[2]) if r[2] is not None else 0.0 for r in rows]

            n = len(a_values)
            sum_a = sum(a_values)
            sum_b = sum(b_values)
            sum_ab = sum(a * b for a, b in zip(a_values, b_values))
            sum_a2 = sum(a * a for a in a_values)
            sum_b2 = sum(b * b for b in b_values)

            numerator = n * sum_ab - sum_a * sum_b
            denominator = ((n * sum_a2 - sum_a ** 2) * (n * sum_b2 - sum_b ** 2)) ** 0.5

            if denominator == 0:
                correlation = 0.0
            else:
                correlation = numerator / denominator

            return CrossBotCorrelation(
                bot_a=bot_a,
                bot_b=bot_b,
                correlation=round(correlation, 4),
                period_days=days,
                sample_size=n
            )

        except Exception as e:
            logger.error(f"Failed to calculate correlation: {e}")
            return None

    def get_all_correlations(self, days: int = 30) -> List[CrossBotCorrelation]:
        """Get correlations between all bot pairs"""
        # Migration 023: Updated bot list to match actual trading bots
        # IC bots: FORTRESS, SAMSON, ANCHOR, JUBILEE | Directional bots: SOLOMON, GIDEON
        bots = ['FORTRESS', 'SOLOMON', 'SAMSON', 'ANCHOR', 'GIDEON', 'JUBILEE']
        correlations = []

        for i, bot_a in enumerate(bots):
            for bot_b in bots[i+1:]:
                corr = self.calculate_correlation(bot_a, bot_b, days)
                if corr:
                    correlations.append(corr)

        return correlations


# =============================================================================
# REGIME-AWARE LEARNING
# =============================================================================

class RegimePerformanceTracker:
    """Track performance by market regime"""

    def __init__(self, proverbs):
        self.proverbs = proverbs

    def analyze_regime_performance(
        self,
        bot_name: str,
        days: int = 90
    ) -> List[RegimePerformance]:
        """Analyze performance by market regime"""
        if not DB_AVAILABLE:
            return []

        # Map bot names to their actual position tables
        BOT_TABLES = {
            'FORTRESS': 'fortress_positions',
            'SOLOMON': 'solomon_positions',
            'SAMSON': 'samson_positions',
            'ANCHOR': 'anchor_positions',
            'GIDEON': 'gideon_positions',
            'JUBILEE': 'jubilee_ic_positions',
        }

        table_name = BOT_TABLES.get(bot_name.upper())
        if not table_name:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Join trades with regime classifications
            # Cast to timestamptz to handle FORTRESS TEXT columns and other bots' timestamp columns
            cursor.execute(f"""
                SELECT
                    rc.regime,
                    COUNT(*) as trades,
                    AVG(CASE WHEN t.realized_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                    AVG(t.realized_pnl) as avg_pnl
                FROM {table_name} t
                LEFT JOIN regime_classifications rc
                    ON DATE(t.close_time::timestamptz AT TIME ZONE 'America/Chicago') = rc.classification_date
                WHERE t.status = 'closed'
                AND t.close_time::timestamptz > NOW() - INTERVAL '{days} days'
                AND rc.regime IS NOT NULL
                GROUP BY rc.regime
                ORDER BY trades DESC
            """)

            rows = cursor.fetchall()
            conn.close()

            results = []
            for row in rows:
                results.append(RegimePerformance(
                    bot_name=bot_name,
                    regime=row[0] or 'UNKNOWN',
                    trades_count=row[1] or 0,
                    win_rate=float(row[2]) if row[2] else 0,
                    avg_pnl=float(row[3]) if row[3] else 0
                ))

            return results

        except Exception as e:
            logger.error(f"Failed to analyze regime performance: {e}")
            return []


# =============================================================================
# A/B TESTING FRAMEWORK
# =============================================================================

class ABTestingFramework:
    """Framework for A/B testing bot configurations with database persistence"""

    def __init__(self, proverbs):
        self.proverbs = proverbs
        self._active_tests: Dict[str, ABTest] = {}
        # Load existing tests from database on initialization
        self._load_from_database()

    def _load_from_database(self) -> None:
        """Load active A/B tests from database into memory cache"""
        if not DB_AVAILABLE:
            return

        try:
            import json
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT test_id, bot_name, created_at,
                       control_config, variant_config, control_allocation,
                       control_trades, variant_trades,
                       control_win_rate, variant_win_rate,
                       control_pnl, variant_pnl,
                       status, winner, confidence
                FROM proverbs_ab_tests
                WHERE status IN ('RUNNING', 'COMPLETED')
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                test_id = row[0]
                self._active_tests[test_id] = ABTest(
                    test_id=row[0],
                    bot_name=row[1],
                    created_at=row[2].isoformat() if hasattr(row[2], 'isoformat') else str(row[2]),
                    control_config=row[3] if isinstance(row[3], dict) else json.loads(row[3] or '{}'),
                    variant_config=row[4] if isinstance(row[4], dict) else json.loads(row[4] or '{}'),
                    control_allocation=float(row[5] or 0.5),
                    control_trades=int(row[6] or 0),
                    variant_trades=int(row[7] or 0),
                    control_win_rate=float(row[8] or 0),
                    variant_win_rate=float(row[9] or 0),
                    control_pnl=float(row[10] or 0),
                    variant_pnl=float(row[11] or 0),
                    status=row[12] or 'RUNNING',
                    winner=row[13],
                    confidence=float(row[14] or 0)
                )

            logger.info(f"Loaded {len(self._active_tests)} A/B tests from database")

        except Exception as e:
            logger.warning(f"Failed to load A/B tests from database (table may not exist): {e}")

    def _save_to_database(self, test: ABTest) -> bool:
        """Save or update A/B test in database"""
        if not DB_AVAILABLE:
            return False

        try:
            import json
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO proverbs_ab_tests (
                    test_id, bot_name, created_at,
                    control_config, variant_config, control_allocation,
                    control_trades, variant_trades,
                    control_win_rate, variant_win_rate,
                    control_pnl, variant_pnl,
                    status, winner, confidence,
                    updated_at
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    NOW()
                )
                ON CONFLICT (test_id) DO UPDATE SET
                    control_trades = EXCLUDED.control_trades,
                    variant_trades = EXCLUDED.variant_trades,
                    control_win_rate = EXCLUDED.control_win_rate,
                    variant_win_rate = EXCLUDED.variant_win_rate,
                    control_pnl = EXCLUDED.control_pnl,
                    variant_pnl = EXCLUDED.variant_pnl,
                    status = EXCLUDED.status,
                    winner = EXCLUDED.winner,
                    confidence = EXCLUDED.confidence,
                    updated_at = NOW()
            """, (
                test.test_id, test.bot_name, test.created_at,
                json.dumps(test.control_config), json.dumps(test.variant_config), test.control_allocation,
                test.control_trades, test.variant_trades,
                test.control_win_rate, test.variant_win_rate,
                test.control_pnl, test.variant_pnl,
                test.status, test.winner, test.confidence
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Failed to save A/B test to database: {e}")
            return False

    def create_test(
        self,
        bot_name: str,
        control_config: Dict,
        variant_config: Dict,
        control_allocation: float = 0.5
    ) -> str:
        """Create a new A/B test"""
        import uuid

        test_id = f"AB-{bot_name}-{datetime.now(CENTRAL_TZ).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

        test = ABTest(
            test_id=test_id,
            bot_name=bot_name,
            created_at=datetime.now(CENTRAL_TZ).isoformat(),
            control_config=control_config,
            variant_config=variant_config,
            control_allocation=control_allocation
        )

        self._active_tests[test_id] = test
        # Persist to database
        self._save_to_database(test)

        logger.info(f"Created A/B test {test_id} for {bot_name}")
        return test_id

    def record_trade(
        self,
        test_id: str,
        is_control: bool,
        pnl: float
    ) -> None:
        """Record a trade result for an A/B test"""
        if test_id not in self._active_tests:
            return

        test = self._active_tests[test_id]

        if is_control:
            test.control_trades += 1
            test.control_pnl += pnl
            if pnl > 0:
                test.control_win_rate = (
                    (test.control_win_rate * (test.control_trades - 1) + 1)
                    / test.control_trades
                )
        else:
            test.variant_trades += 1
            test.variant_pnl += pnl
            if pnl > 0:
                test.variant_win_rate = (
                    (test.variant_win_rate * (test.variant_trades - 1) + 1)
                    / test.variant_trades
                )

        # Persist updated results to database
        self._save_to_database(test)

    def evaluate_test(self, test_id: str) -> Dict:
        """Evaluate A/B test results"""
        if test_id not in self._active_tests:
            return {'error': 'Test not found'}

        test = self._active_tests[test_id]

        # Check minimum requirements
        min_trades = ENHANCED_GUARDRAILS['ab_test_min_trades']
        if test.control_trades < min_trades or test.variant_trades < min_trades:
            return {
                'test_id': test_id,
                'status': 'INSUFFICIENT_DATA',
                'control_trades': test.control_trades,
                'variant_trades': test.variant_trades,
                'required_trades': min_trades
            }

        # Calculate statistical significance (simplified)
        # In production, use proper statistical tests
        total = test.control_trades + test.variant_trades
        control_rate = test.control_pnl / test.control_trades if test.control_trades else 0
        variant_rate = test.variant_pnl / test.variant_trades if test.variant_trades else 0

        diff = variant_rate - control_rate

        # Simple confidence approximation
        confidence = min(0.99, 0.5 + abs(diff) * total / 10000)

        result = {
            'test_id': test_id,
            'status': test.status,
            'control': {
                'trades': test.control_trades,
                'win_rate': test.control_win_rate * 100,
                'total_pnl': test.control_pnl,
                'avg_pnl': control_rate
            },
            'variant': {
                'trades': test.variant_trades,
                'win_rate': test.variant_win_rate * 100,
                'total_pnl': test.variant_pnl,
                'avg_pnl': variant_rate
            },
            'difference': diff,
            'confidence': confidence,
            'winner': None
        }

        # Determine winner if confident enough
        if confidence >= ENHANCED_GUARDRAILS['ab_test_confidence_threshold']:
            if diff > 0:
                result['winner'] = 'VARIANT'
                test.winner = 'VARIANT'
            else:
                result['winner'] = 'CONTROL'
                test.winner = 'CONTROL'

            test.status = 'COMPLETED'
            test.confidence = confidence

            # Persist completion status to database
            self._save_to_database(test)

        return result

    def stop_test(self, test_id: str) -> bool:
        """Stop an A/B test early"""
        if test_id not in self._active_tests:
            return False

        test = self._active_tests[test_id]
        test.status = 'STOPPED'
        self._save_to_database(test)
        logger.info(f"Stopped A/B test {test_id}")
        return True

    def get_active_tests(self, bot_name: str = None) -> List[Dict]:
        """Get active A/B tests"""
        tests = list(self._active_tests.values())

        if bot_name:
            tests = [t for t in tests if t.bot_name == bot_name]

        return [t.to_dict() for t in tests if t.status == 'RUNNING']

    def get_all_tests(self, bot_name: str = None, include_completed: bool = True) -> List[Dict]:
        """Get all A/B tests (including completed)"""
        tests = list(self._active_tests.values())

        if bot_name:
            tests = [t for t in tests if t.bot_name == bot_name]

        if not include_completed:
            tests = [t for t in tests if t.status == 'RUNNING']

        return [t.to_dict() for t in tests]


# =============================================================================
# APPROVAL TIERS
# =============================================================================

class ApprovalTierManager:
    """Manage proposal approval tiers"""

    TIERS = {
        'AUTO_APPROVE': {
            'max_change_pct': 5.0,
            'risk_level': 'LOW',
            'requires_human': False
        },
        'EXPEDITED': {
            'max_change_pct': 15.0,
            'risk_level': 'MEDIUM',
            'requires_human': True,
            'min_wait_hours': 1
        },
        'STANDARD': {
            'max_change_pct': 30.0,
            'risk_level': 'MEDIUM',
            'requires_human': True,
            'min_wait_hours': 4
        },
        'HIGH_IMPACT': {
            'max_change_pct': 100.0,
            'risk_level': 'HIGH',
            'requires_human': True,
            'min_wait_hours': 24
        }
    }

    def __init__(self, proverbs):
        self.proverbs = proverbs

    def determine_tier(
        self,
        risk_level: str,
        change_pct: float
    ) -> str:
        """Determine approval tier based on risk and change magnitude"""
        if risk_level == 'LOW' and change_pct <= self.TIERS['AUTO_APPROVE']['max_change_pct']:
            return 'AUTO_APPROVE'
        elif risk_level == 'LOW' and change_pct <= self.TIERS['EXPEDITED']['max_change_pct']:
            return 'EXPEDITED'
        elif risk_level in ['LOW', 'MEDIUM'] and change_pct <= self.TIERS['STANDARD']['max_change_pct']:
            return 'STANDARD'
        else:
            return 'HIGH_IMPACT'

    def should_auto_approve(
        self,
        risk_level: str,
        change_pct: float
    ) -> bool:
        """Check if a proposal should be auto-approved"""
        if not ENHANCED_GUARDRAILS['auto_approve_low_risk']:
            return False

        tier = self.determine_tier(risk_level, change_pct)
        return tier == 'AUTO_APPROVE'

    def get_min_wait_hours(self, tier: str) -> int:
        """Get minimum wait hours before applying"""
        return self.TIERS.get(tier, {}).get('min_wait_hours', 24)


# =============================================================================
# ROLLBACK COOLDOWN
# =============================================================================

class RollbackCooldownManager:
    """Manage rollback cooldown periods"""

    def __init__(self, proverbs):
        self.proverbs = proverbs
        self._last_rollbacks: Dict[str, List[datetime]] = {}

    def can_rollback(self, bot_name: str) -> Tuple[bool, str]:
        """Check if a rollback is allowed"""
        now = datetime.now(CENTRAL_TZ)
        cooldown_hours = ENHANCED_GUARDRAILS['rollback_cooldown_hours']
        max_per_day = ENHANCED_GUARDRAILS['max_rollbacks_per_day']

        if bot_name not in self._last_rollbacks:
            self._last_rollbacks[bot_name] = []

        # Clean old entries
        cutoff = now - timedelta(hours=24)
        self._last_rollbacks[bot_name] = [
            r for r in self._last_rollbacks[bot_name] if r > cutoff
        ]

        rollbacks = self._last_rollbacks[bot_name]

        # Check daily limit
        if len(rollbacks) >= max_per_day:
            return False, f"Maximum {max_per_day} rollbacks per day reached"

        # Check cooldown
        if rollbacks:
            last_rollback = max(rollbacks)
            hours_since = (now - last_rollback).total_seconds() / 3600

            if hours_since < cooldown_hours:
                remaining = cooldown_hours - hours_since
                return False, f"Cooldown active: {remaining:.1f} hours remaining"

        return True, "Rollback allowed"

    def record_rollback(self, bot_name: str) -> None:
        """Record a rollback"""
        if bot_name not in self._last_rollbacks:
            self._last_rollbacks[bot_name] = []

        self._last_rollbacks[bot_name].append(datetime.now(CENTRAL_TZ))


# =============================================================================
# WEEKEND PRE-CHECK
# =============================================================================

class WeekendPreChecker:
    """Generate weekend pre-check analysis"""

    def __init__(self, proverbs):
        self.proverbs = proverbs

    def generate_precheck(self) -> WeekendPreCheck:
        """Generate pre-weekend analysis"""
        # Get current market data
        vix_level = self._get_current_vix()
        market_trend = self._detect_market_trend()
        upcoming_events = self._get_upcoming_events()

        # Analyze each bot
        # Migration 023: Updated bot list to include SAMSON and GIDEON
        # Migration 024: Added JUBILEE (Box Spread + IC Trading)
        bot_recommendations = {}
        for bot in ['FORTRESS', 'SOLOMON', 'SAMSON', 'ANCHOR', 'GIDEON', 'JUBILEE']:
            bot_recommendations[bot] = self._analyze_bot_readiness(bot)

        # Overall risk assessment
        risk_factors = []
        if vix_level > 25:
            risk_factors.append(f"Elevated VIX: {vix_level:.1f}")
        if upcoming_events:
            risk_factors.append(f"Upcoming events: {', '.join(upcoming_events[:3])}")

        overall_risk = 'LOW'
        if len(risk_factors) >= 2:
            overall_risk = 'HIGH'
        elif len(risk_factors) == 1:
            overall_risk = 'MEDIUM'

        return WeekendPreCheck(
            analysis_date=datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'),
            vix_level=vix_level,
            market_trend=market_trend,
            upcoming_events=upcoming_events,
            bot_recommendations=bot_recommendations,
            overall_risk=overall_risk,
            risk_factors=risk_factors
        )

    def _get_current_vix(self) -> float:
        """Get current VIX level"""
        if not DB_AVAILABLE:
            return 15.0

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT vix FROM market_data
                ORDER BY timestamp DESC LIMIT 1
            """)

            row = cursor.fetchone()

            return float(row[0]) if row else 15.0

        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Could not get VIX: {e}")
            return 15.0
        finally:
            if conn:
                conn.close()

    def _detect_market_trend(self) -> str:
        """Detect current market trend"""
        if not DB_AVAILABLE:
            return 'UNKNOWN'

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT close FROM market_data
                WHERE symbol = 'SPY'
                ORDER BY timestamp DESC LIMIT 5
            """)

            rows = cursor.fetchall()

            if len(rows) >= 5:
                closes = [r[0] for r in rows]
                if closes[0] > closes[-1] * 1.01:
                    return 'TRENDING_UP'
                elif closes[0] < closes[-1] * 0.99:
                    return 'TRENDING_DOWN'
                else:
                    return 'RANGING'

            return 'UNKNOWN'

        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Could not detect market trend: {e}")
            return 'UNKNOWN'
        finally:
            if conn:
                conn.close()

    def _get_upcoming_events(self) -> List[str]:
        """Get upcoming market-moving events"""
        # In production, integrate with economic calendar
        return []

    def _analyze_bot_readiness(self, bot_name: str) -> Dict:
        """Analyze if a bot is ready for the upcoming week"""
        is_killed = self.proverbs.is_bot_killed(bot_name)
        performance = self.proverbs._get_current_performance(bot_name)

        if is_killed:
            return {
                'action': 'DISABLED',
                'reason': 'Kill switch is active',
                'confidence': 1.0
            }

        win_rate = performance.get('win_rate', 0)

        if win_rate >= 60:
            return {
                'action': 'CONTINUE',
                'reason': f'Strong performance ({win_rate:.1f}% win rate)',
                'confidence': 0.8
            }
        elif win_rate >= 50:
            return {
                'action': 'MONITOR',
                'reason': f'Moderate performance ({win_rate:.1f}% win rate)',
                'confidence': 0.6
            }
        else:
            return {
                'action': 'CAUTION',
                'reason': f'Weak performance ({win_rate:.1f}% win rate)',
                'confidence': 0.4
            }


# =============================================================================
# DAILY DIGEST
# =============================================================================

class DailyDigestGenerator:
    """Generate daily performance digest"""

    def __init__(self, proverbs):
        self.proverbs = proverbs

    def generate_digest(self, for_date: str = None) -> Dict:
        """Generate daily performance digest"""
        if not for_date:
            for_date = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

        digest = {
            'date': for_date,
            'generated_at': datetime.now(CENTRAL_TZ).isoformat(),
            'summary': {},
            'bots': {},
            'alerts': [],
            'recommendations': []
        }

        total_pnl = 0
        total_trades = 0
        total_wins = 0

        # Migration 023: Updated bot list to include SAMSON and GIDEON
        # Migration 024: Added JUBILEE (Box Spread + IC Trading)
        for bot in ['FORTRESS', 'SOLOMON', 'SAMSON', 'ANCHOR', 'GIDEON', 'JUBILEE']:
            bot_stats = self._get_bot_daily_stats(bot, for_date)
            digest['bots'][bot] = bot_stats

            total_pnl += bot_stats.get('pnl', 0)
            total_trades += bot_stats.get('trades', 0)
            total_wins += bot_stats.get('wins', 0)

        digest['summary'] = {
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'total_wins': total_wins,
            'win_rate': (total_wins / total_trades * 100) if total_trades else 0
        }

        # Add alerts
        if total_pnl < -1000:
            digest['alerts'].append({
                'severity': 'HIGH',
                'message': f'Significant daily loss: ${total_pnl:,.2f}'
            })

        # Add recommendations
        if total_trades == 0:
            digest['recommendations'].append('No trades executed today - check bot status')

        return digest

    def _get_bot_daily_stats(self, bot_name: str, date: str) -> Dict:
        """Get daily stats for a bot"""
        if not DB_AVAILABLE:
            return {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0}

        # Map bot names to their actual position tables
        BOT_TABLES = {
            'FORTRESS': 'fortress_positions',
            'SOLOMON': 'solomon_positions',
            'SAMSON': 'samson_positions',
            'ANCHOR': 'anchor_positions',
            'GIDEON': 'gideon_positions',
            'JUBILEE': 'jubilee_ic_positions',
        }

        table_name = BOT_TABLES.get(bot_name.upper())
        if not table_name:
            return {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0}

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Cast to timestamptz to handle FORTRESS TEXT columns and other bots' timestamp columns
            cursor.execute(f"""
                SELECT
                    COUNT(*) as trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(realized_pnl), 0) as total_pnl
                FROM {table_name}
                WHERE status = 'closed'
                AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
            """, (date,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    'trades': row[0] or 0,
                    'wins': row[1] or 0,
                    'losses': row[2] or 0,
                    'pnl': float(row[3]) if row[3] else 0
                }

            return {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0}

        except Exception as e:
            logger.error(f"Failed to get bot daily stats: {e}")
            return {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0}


# =============================================================================
# PROPOSAL VALIDATION - PROVEN IMPROVEMENT REQUIRED
# =============================================================================

@dataclass
class ValidationResult:
    """Result of proposal validation"""
    is_valid: bool
    can_apply: bool
    validation_method: str  # BACKTEST, AB_TEST, SHADOW_MODE, HISTORICAL
    improvement_proven: bool
    improvement_metrics: Dict
    rejection_reasons: List[str]
    detailed_reasoning: Dict

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ProposalReasoning:
    """
    Detailed reasoning for a proposal - captures ALL the WHY.

    This ensures complete transparency on why a change is being made.
    """
    proposal_id: str

    # WHY is this change being proposed?
    problem_statement: str  # What problem are we solving?
    hypothesis: str  # What do we believe will happen?

    # Evidence supporting the change
    supporting_evidence: List[Dict]  # [{type, description, data}]
    historical_analysis: Dict  # Past performance data
    statistical_significance: float  # 0.0-1.0

    # Expected outcomes
    expected_improvement: Dict  # {metric: expected_change}
    confidence_level: float  # 0.0-1.0

    # Risk analysis
    risk_assessment: str
    potential_downsides: List[str]
    mitigation_strategies: List[str]

    # Validation plan
    validation_method: str  # How will we prove this works?
    success_criteria: Dict  # {metric: threshold}
    rollback_trigger: Dict  # {metric: threshold}

    # Approval requirements
    minimum_validation_period_days: int
    minimum_trades_required: int
    requires_ab_test: bool

    def to_dict(self) -> Dict:
        return asdict(self)


class ProposalValidator:
    """
    Validates proposals BEFORE they can be applied.

    KEY PRINCIPLE: Changes are ONLY applied if improvement is PROVEN.

    Validation Methods:
    1. BACKTEST - Run historical backtest comparing old vs new
    2. AB_TEST - Run live A/B test for minimum period
    3. SHADOW_MODE - Run new config in shadow mode alongside current
    4. HISTORICAL - Compare to known good historical periods

    Requirements:
    - Minimum validation period (default 7 days for A/B)
    - Minimum trade count (default 20 trades)
    - Statistical significance (default 95%)
    - Clear improvement in primary metric

    Data is persisted to proverbs_validations table for durability across restarts.
    """

    VALIDATION_REQUIREMENTS = {
        'min_validation_days': 7,
        'min_trades': 20,
        'min_confidence': 0.95,
        'min_improvement_pct': 5.0,  # Must show at least 5% improvement
        'backtest_min_days': 30,
        'shadow_mode_min_days': 3,
    }

    def __init__(self, proverbs):
        self.proverbs = proverbs
        self._ab_tests: Dict[str, str] = {}  # proposal_id -> ab_test_id
        # In-memory cache, backed by database
        self._pending_validations: Dict[str, Dict] = {}
        self._load_from_database()

    def _load_from_database(self) -> None:
        """Load pending validations from database into cache"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT validation_id, proposal_id, bot_name, method, started_at,
                       current_config, proposed_config, status,
                       current_trades, current_wins, current_pnl, current_win_rate,
                       proposed_trades, proposed_wins, proposed_pnl, proposed_win_rate,
                       problem_statement, hypothesis, supporting_evidence,
                       expected_improvement, confidence_level, success_criteria, rollback_trigger
                FROM proverbs_validations
                WHERE status = 'RUNNING'
            """)
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                validation_id = row[0]
                self._pending_validations[validation_id] = {
                    'validation_id': row[0],
                    'proposal_id': row[1],
                    'bot_name': row[2],
                    'method': row[3],
                    'started_at': row[4].isoformat() if row[4] else datetime.now(CENTRAL_TZ).isoformat(),
                    'current_config': row[5] or {},
                    'proposed_config': row[6] or {},
                    'status': row[7],
                    'current_performance': {
                        'trades': row[8] or 0,
                        'wins': row[9] or 0,
                        'pnl': float(row[10] or 0),
                        'win_rate': float(row[11] or 0)
                    },
                    'proposed_performance': {
                        'trades': row[12] or 0,
                        'wins': row[13] or 0,
                        'pnl': float(row[14] or 0),
                        'win_rate': float(row[15] or 0)
                    },
                    'reasoning': {
                        'problem_statement': row[16],
                        'hypothesis': row[17],
                        'supporting_evidence': row[18] or [],
                        'expected_improvement': row[19] or {},
                        'confidence_level': float(row[20] or 0.7),
                        'success_criteria': row[21] or {},
                        'rollback_trigger': row[22] or {}
                    }
                }

            logger.info(f"Loaded {len(self._pending_validations)} pending validations from database")

        except Exception as e:
            logger.warning(f"Failed to load validations from database (table may not exist yet): {e}")

    def _save_to_database(self, validation: Dict) -> bool:
        """Save or update validation in database"""
        if not DB_AVAILABLE:
            return False

        try:
            import json
            conn = get_connection()
            cursor = conn.cursor()

            reasoning = validation.get('reasoning', {})
            current_perf = validation.get('current_performance', {})
            proposed_perf = validation.get('proposed_performance', {})

            cursor.execute("""
                INSERT INTO proverbs_validations (
                    validation_id, proposal_id, bot_name, method, started_at,
                    current_config, proposed_config, status,
                    current_trades, current_wins, current_pnl, current_win_rate,
                    proposed_trades, proposed_wins, proposed_pnl, proposed_win_rate,
                    problem_statement, hypothesis, supporting_evidence,
                    expected_improvement, confidence_level, success_criteria, rollback_trigger,
                    updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    NOW()
                )
                ON CONFLICT (validation_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    current_trades = EXCLUDED.current_trades,
                    current_wins = EXCLUDED.current_wins,
                    current_pnl = EXCLUDED.current_pnl,
                    current_win_rate = EXCLUDED.current_win_rate,
                    proposed_trades = EXCLUDED.proposed_trades,
                    proposed_wins = EXCLUDED.proposed_wins,
                    proposed_pnl = EXCLUDED.proposed_pnl,
                    proposed_win_rate = EXCLUDED.proposed_win_rate,
                    updated_at = NOW()
            """, (
                validation['validation_id'],
                validation['proposal_id'],
                validation['bot_name'],
                validation['method'],
                validation['started_at'],
                json.dumps(validation.get('current_config', {})),
                json.dumps(validation.get('proposed_config', {})),
                validation.get('status', 'RUNNING'),
                current_perf.get('trades', 0),
                current_perf.get('wins', 0),
                current_perf.get('pnl', 0),
                current_perf.get('win_rate', 0),
                proposed_perf.get('trades', 0),
                proposed_perf.get('wins', 0),
                proposed_perf.get('pnl', 0),
                proposed_perf.get('win_rate', 0),
                reasoning.get('problem_statement'),
                reasoning.get('hypothesis'),
                json.dumps(reasoning.get('supporting_evidence', [])),
                json.dumps(reasoning.get('expected_improvement', {})),
                reasoning.get('confidence_level', 0.7),
                json.dumps(reasoning.get('success_criteria', {})),
                json.dumps(reasoning.get('rollback_trigger', {}))
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Failed to save validation to database: {e}")
            return False

    def start_validation(
        self,
        proposal_id: str,
        bot_name: str,
        current_config: Dict,
        proposed_config: Dict,
        method: str = "AB_TEST",
        reasoning: Dict = None
    ) -> str:
        """
        Start validation for a proposal.

        Returns validation ID. Data is persisted to database.
        """
        import uuid

        validation_id = f"VAL-{proposal_id}-{uuid.uuid4().hex[:8]}"

        validation = {
            'validation_id': validation_id,
            'proposal_id': proposal_id,
            'bot_name': bot_name,
            'method': method,
            'started_at': datetime.now(CENTRAL_TZ).isoformat(),
            'current_config': current_config,
            'proposed_config': proposed_config,
            'status': 'RUNNING',
            'current_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
            'proposed_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
            'reasoning': reasoning or {}
        }

        # Save to cache and database
        self._pending_validations[validation_id] = validation
        self._save_to_database(validation)

        logger.info(f"Started validation {validation_id} for proposal {proposal_id} using {method}")
        return validation_id

    def record_validation_trade(
        self,
        validation_id: str,
        is_proposed: bool,
        pnl: float
    ) -> None:
        """Record a trade result during validation. Persisted to database."""
        if validation_id not in self._pending_validations:
            # Try loading from database
            self._load_from_database()
            if validation_id not in self._pending_validations:
                logger.warning(f"Validation {validation_id} not found")
                return

        val = self._pending_validations[validation_id]

        key = 'proposed_performance' if is_proposed else 'current_performance'
        val[key]['trades'] += 1
        val[key]['pnl'] += pnl
        if pnl > 0:
            val[key]['wins'] = val[key].get('wins', 0) + 1
        # Always recalculate win_rate after every trade (not just wins)
        val[key]['win_rate'] = (val[key].get('wins', 0) / val[key]['trades']) * 100 if val[key]['trades'] > 0 else 0

        # Persist to database
        self._save_to_database(val)

    def evaluate_validation(self, validation_id: str) -> ValidationResult:
        """
        Evaluate if validation proves improvement.

        Returns ValidationResult with detailed reasoning.
        """
        if validation_id not in self._pending_validations:
            return ValidationResult(
                is_valid=False,
                can_apply=False,
                validation_method='UNKNOWN',
                improvement_proven=False,
                improvement_metrics={},
                rejection_reasons=['Validation not found'],
                detailed_reasoning={'error': 'Validation ID not found'}
            )

        val = self._pending_validations[validation_id]
        rejection_reasons = []

        # Check minimum trades
        min_trades = self.VALIDATION_REQUIREMENTS['min_trades']
        current_trades = val['current_performance']['trades']
        proposed_trades = val['proposed_performance']['trades']

        if current_trades < min_trades or proposed_trades < min_trades:
            rejection_reasons.append(
                f"Insufficient trades: current={current_trades}, proposed={proposed_trades}, required={min_trades}"
            )

        # Check validation period
        started_at = datetime.fromisoformat(val['started_at'])
        days_elapsed = (datetime.now(CENTRAL_TZ) - started_at).days
        min_days = self.VALIDATION_REQUIREMENTS['min_validation_days']

        if days_elapsed < min_days:
            rejection_reasons.append(
                f"Insufficient validation period: {days_elapsed} days elapsed, {min_days} required"
            )

        # Calculate improvement metrics
        current_perf = val['current_performance']
        proposed_perf = val['proposed_performance']

        improvement_metrics = {
            'current_win_rate': current_perf['win_rate'],
            'proposed_win_rate': proposed_perf['win_rate'],
            'win_rate_change': proposed_perf['win_rate'] - current_perf['win_rate'],
            'current_pnl': current_perf['pnl'],
            'proposed_pnl': proposed_perf['pnl'],
            'pnl_change': proposed_perf['pnl'] - current_perf['pnl'],
            'current_trades': current_trades,
            'proposed_trades': proposed_trades,
            'validation_days': days_elapsed
        }

        # Check if improvement is proven
        improvement_proven = False
        min_improvement = self.VALIDATION_REQUIREMENTS['min_improvement_pct']

        if current_perf['win_rate'] > 0:
            win_rate_improvement = (
                (proposed_perf['win_rate'] - current_perf['win_rate'])
                / current_perf['win_rate'] * 100
            )
            improvement_metrics['win_rate_improvement_pct'] = win_rate_improvement

            if win_rate_improvement >= min_improvement:
                improvement_proven = True

        # Also consider P&L improvement
        if current_perf['pnl'] != 0:
            pnl_improvement = (
                (proposed_perf['pnl'] - current_perf['pnl'])
                / abs(current_perf['pnl']) * 100
            )
            improvement_metrics['pnl_improvement_pct'] = pnl_improvement

            if pnl_improvement >= min_improvement:
                improvement_proven = True

        if not improvement_proven and not rejection_reasons:
            rejection_reasons.append(
                f"Improvement not proven: minimum {min_improvement}% improvement required. "
                f"Win rate change: {improvement_metrics.get('win_rate_improvement_pct', 0):.1f}%, "
                f"P&L change: {improvement_metrics.get('pnl_improvement_pct', 0):.1f}%"
            )

        # Build detailed reasoning
        detailed_reasoning = {
            'validation_id': validation_id,
            'proposal_id': val['proposal_id'],
            'bot_name': val['bot_name'],
            'validation_method': val['method'],
            'validation_period': {
                'started': val['started_at'],
                'days_elapsed': days_elapsed,
                'min_required': min_days
            },
            'trade_counts': {
                'current': current_trades,
                'proposed': proposed_trades,
                'min_required': min_trades
            },
            'performance_comparison': {
                'current': current_perf,
                'proposed': proposed_perf,
                'improvement_metrics': improvement_metrics
            },
            'validation_requirements': self.VALIDATION_REQUIREMENTS,
            'conclusion': 'APPROVED - Improvement proven' if improvement_proven and not rejection_reasons else 'REJECTED - Improvement not proven'
        }

        can_apply = improvement_proven and len(rejection_reasons) == 0

        return ValidationResult(
            is_valid=True,
            can_apply=can_apply,
            validation_method=val['method'],
            improvement_proven=improvement_proven,
            improvement_metrics=improvement_metrics,
            rejection_reasons=rejection_reasons,
            detailed_reasoning=detailed_reasoning
        )

    def get_pending_validations(self, bot_name: str = None) -> List[Dict]:
        """Get all pending validations"""
        validations = list(self._pending_validations.values())

        if bot_name:
            validations = [v for v in validations if v['bot_name'] == bot_name]

        return validations

    def validate_proposal_reasoning(self, reasoning: ProposalReasoning) -> Tuple[bool, List[str]]:
        """
        Validate that proposal reasoning is complete.

        Returns (is_valid, list_of_issues)
        """
        issues = []

        # Required fields
        if not reasoning.problem_statement or len(reasoning.problem_statement) < 20:
            issues.append("Problem statement is required and must be detailed (min 20 chars)")

        if not reasoning.hypothesis or len(reasoning.hypothesis) < 20:
            issues.append("Hypothesis is required and must be detailed (min 20 chars)")

        if not reasoning.supporting_evidence:
            issues.append("At least one piece of supporting evidence is required")

        if reasoning.confidence_level < 0.5:
            issues.append("Confidence level is too low (minimum 50%)")

        if not reasoning.expected_improvement:
            issues.append("Expected improvement metrics must be specified")

        if not reasoning.success_criteria:
            issues.append("Success criteria must be defined")

        if not reasoning.rollback_trigger:
            issues.append("Rollback triggers must be defined")

        if reasoning.minimum_trades_required < 10:
            issues.append("Minimum trades for validation must be at least 10")

        return len(issues) == 0, issues

    def create_proposal_reasoning(
        self,
        proposal_id: str,
        problem_statement: str,
        hypothesis: str,
        supporting_evidence: List[Dict],
        expected_improvement: Dict,
        risk_assessment: str,
        potential_downsides: List[str],
        validation_method: str = "AB_TEST",
        success_criteria: Dict = None,
        rollback_trigger: Dict = None
    ) -> ProposalReasoning:
        """
        Create complete proposal reasoning document.

        This captures all the WHY for a proposal.
        """
        return ProposalReasoning(
            proposal_id=proposal_id,
            problem_statement=problem_statement,
            hypothesis=hypothesis,
            supporting_evidence=supporting_evidence,
            historical_analysis={},  # To be populated by analysis
            statistical_significance=0.0,  # To be calculated
            expected_improvement=expected_improvement,
            confidence_level=0.7,  # Default medium confidence
            risk_assessment=risk_assessment,
            potential_downsides=potential_downsides,
            mitigation_strategies=[
                "Automatic rollback if performance degrades >10%",
                "Kill switch remains available",
                "Version control enables instant revert"
            ],
            validation_method=validation_method,
            success_criteria=success_criteria or {
                'win_rate_improvement': 5.0,
                'pnl_improvement': 5.0
            },
            rollback_trigger=rollback_trigger or {
                'max_drawdown': 10.0,
                'consecutive_losses': 3
            },
            minimum_validation_period_days=7,
            minimum_trades_required=20,
            requires_ab_test=validation_method == "AB_TEST"
        )


# =============================================================================
# ENHANCED PROVERBS CLASS
# =============================================================================

class ProverbsEnhanced:
    """
    Enhanced Proverbs with all advanced features.

    Wraps the base Proverbs instance and adds:
    - Consecutive loss monitoring
    - Daily loss monitoring
    - Version comparison
    - Time of day analysis
    - Cross-bot correlation
    - Regime performance tracking
    - A/B testing
    - Approval tiers
    - Rollback cooldown
    - Weekend pre-check
    - Daily digest
    - PROPOSAL VALIDATION (changes only apply if improvement is PROVEN)
    """

    def __init__(self, proverbs):
        self.proverbs = proverbs

        # Initialize all enhancement modules
        self.consecutive_loss_monitor = ConsecutiveLossMonitor(proverbs)
        self.daily_loss_monitor = DailyLossMonitor(proverbs)
        self.version_comparer = VersionComparer(proverbs)
        self.time_analyzer = TimeOfDayAnalyzer(proverbs)
        self.cross_bot_analyzer = CrossBotAnalyzer(proverbs)
        self.regime_tracker = RegimePerformanceTracker(proverbs)
        self.ab_testing = ABTestingFramework(proverbs)
        self.approval_tiers = ApprovalTierManager(proverbs)
        self.rollback_cooldown = RollbackCooldownManager(proverbs)
        self.weekend_precheck = WeekendPreChecker(proverbs)
        self.daily_digest = DailyDigestGenerator(proverbs)
        self.proposal_validator = ProposalValidator(proverbs)  # NEW: Validates improvements before applying

        # Store proposal reasoning documents
        self._proposal_reasoning: Dict[str, ProposalReasoning] = {}

        logger.info("Proverbs Enhanced initialized with all modules including proposal validation")

    def record_trade_outcome(
        self,
        bot_name: str,
        pnl: float,
        trade_date: str,
        capital_base: float = 100000.0,
        # Migration 023: New feedback loop parameters
        outcome_type: str = None,  # MAX_PROFIT, CALL_BREACHED, PUT_BREACHED, WIN, LOSS
        oracle_advice: str = None,  # TRADE_FULL, TRADE_REDUCED, SKIP_TODAY
        strategy_type: str = None,  # IRON_CONDOR, DIRECTIONAL
        oracle_prediction_id: int = None,  # Link to prophet_predictions
        direction_predicted: str = None,  # BULLISH, BEARISH (for directional)
        direction_correct: bool = None  # Was direction right?
    ) -> List[Dict]:
        """
        Record a trade outcome and check all triggers.

        Migration 023: Enhanced to track strategy-level performance and
        link to Prophet predictions for accurate feedback loop.

        Returns list of any alerts triggered.
        """
        alerts = []

        # Check consecutive losses
        consec_alert = self.consecutive_loss_monitor.record_trade_outcome(
            bot_name, pnl, trade_date
        )
        if consec_alert:
            alerts.append(consec_alert)

        # Check daily loss
        daily_alert = self.daily_loss_monitor.record_trade(
            bot_name, pnl, capital_base
        )
        if daily_alert:
            alerts.append(daily_alert)

        # Migration 023: Record enhanced feedback data to proverbs_performance
        self._record_enhanced_outcome(
            bot_name=bot_name,
            pnl=pnl,
            trade_date=trade_date,
            outcome_type=outcome_type,
            oracle_advice=oracle_advice,
            strategy_type=strategy_type,
            oracle_prediction_id=oracle_prediction_id,
            direction_predicted=direction_predicted,
            direction_correct=direction_correct
        )

        return alerts

    def _record_enhanced_outcome(
        self,
        bot_name: str,
        pnl: float,
        trade_date: str,
        outcome_type: str = None,
        oracle_advice: str = None,
        strategy_type: str = None,
        oracle_prediction_id: int = None,
        direction_predicted: str = None,
        direction_correct: bool = None
    ):
        """
        Record enhanced outcome data to proverbs_performance table.

        Migration 023: This data enables strategy-level analysis of
        Iron Condor vs Directional effectiveness.
        """
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Infer strategy_type from bot_name if not provided
            if not strategy_type:
                if bot_name in ['SOLOMON', 'GIDEON']:
                    strategy_type = 'DIRECTIONAL'
                else:
                    strategy_type = 'IRON_CONDOR'

            # Insert or update proverbs_performance with enhanced data
            cursor.execute("""
                INSERT INTO proverbs_performance (
                    bot_name, trade_date, pnl, is_win,
                    strategy_type, outcome_type, oracle_advice,
                    oracle_prediction_id, direction_taken, direction_correct,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (bot_name, trade_date) DO UPDATE SET
                    pnl = EXCLUDED.pnl,
                    is_win = EXCLUDED.is_win,
                    strategy_type = COALESCE(EXCLUDED.strategy_type, proverbs_performance.strategy_type),
                    outcome_type = COALESCE(EXCLUDED.outcome_type, proverbs_performance.outcome_type),
                    oracle_advice = COALESCE(EXCLUDED.oracle_advice, proverbs_performance.oracle_advice),
                    oracle_prediction_id = COALESCE(EXCLUDED.oracle_prediction_id, proverbs_performance.oracle_prediction_id),
                    direction_taken = COALESCE(EXCLUDED.direction_taken, proverbs_performance.direction_taken),
                    direction_correct = COALESCE(EXCLUDED.direction_correct, proverbs_performance.direction_correct),
                    updated_at = NOW()
            """, (
                bot_name,
                trade_date,
                pnl,
                pnl > 0,  # is_win
                strategy_type,
                outcome_type,
                oracle_advice,
                oracle_prediction_id,
                direction_predicted,
                direction_correct
            ))

            conn.commit()
            conn.close()

            logger.debug(f"Proverbs: Enhanced outcome recorded for {bot_name} on {trade_date}")

        except Exception as e:
            logger.warning(f"Proverbs: Failed to record enhanced outcome: {e}")

    def get_comprehensive_analysis(self, bot_name: str) -> Dict:
        """Get comprehensive analysis for a bot"""
        return {
            'bot_name': bot_name,
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'consecutive_losses': self.consecutive_loss_monitor.get_status(bot_name),
            'daily_status': self.daily_loss_monitor.get_status(bot_name),
            'time_of_day': [t.to_dict() for t in self.time_analyzer.analyze(bot_name)],
            'regime_performance': [r.to_dict() for r in self.regime_tracker.analyze_regime_performance(bot_name)],
            'version_history': [v.to_dict() for v in self.version_comparer.get_version_performance_history(bot_name)]
        }

    def get_portfolio_correlations(self) -> Dict:
        """Get correlations across all bots"""
        correlations = self.cross_bot_analyzer.get_all_correlations()
        return {
            'correlations': [c.to_dict() for c in correlations],
            'analysis': self._interpret_correlations(correlations)
        }

    def _interpret_correlations(self, correlations: List[CrossBotCorrelation]) -> Dict:
        """Interpret correlation results"""
        if not correlations:
            return {'status': 'insufficient_data'}

        high_corr = [c for c in correlations if abs(c.correlation) > 0.7]

        return {
            'status': 'analyzed',
            'high_correlations': [c.to_dict() for c in high_corr],
            'diversification_score': 1 - (sum(abs(c.correlation) for c in correlations) / len(correlations)) if correlations else 0,
            'recommendation': 'Consider reducing positions when highly correlated bots both signal' if high_corr else 'Good diversification'
        }

    # =========================================================================
    # STRATEGY ANALYSIS (Migration 023)
    # =========================================================================

    # Bot strategy configurations - defines goals for each bot
    BOT_STRATEGY_CONFIGS = {
        # Iron Condor bots - want price stability (price stays between strikes)
        'FORTRESS': {'strategy_type': 'IRON_CONDOR', 'goal': 'stability', 'symbol': 'SPY'},
        'SAMSON': {'strategy_type': 'IRON_CONDOR', 'goal': 'stability', 'symbol': 'SPX'},
        'ANCHOR': {'strategy_type': 'IRON_CONDOR', 'goal': 'stability', 'symbol': 'SPX'},
        'JUBILEE': {'strategy_type': 'IRON_CONDOR', 'goal': 'stability', 'symbol': 'SPX'},  # Box Spread + IC
        # Directional bots - want price movement in predicted direction
        'SOLOMON': {'strategy_type': 'DIRECTIONAL', 'goal': 'movement', 'symbol': 'SPY'},
        'GIDEON': {'strategy_type': 'DIRECTIONAL', 'goal': 'movement', 'symbol': 'SPY'},
    }

    def get_strategy_analysis(self, days: int = 30) -> Dict:
        """
        Analyze performance by strategy type (Iron Condor vs Directional).

        Migration 023: This enables Proverbs to understand which strategy works
        best in different market conditions and provide insights to Prophet.

        Fix: Now queries unified_trades directly instead of proverbs_performance
        to ensure we're analyzing actual trade data.
        """
        if not DB_AVAILABLE:
            return {'status': 'database_unavailable'}

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Bot tables mapping - bots store closed trades in *_positions tables
            BOT_TABLES = {
                'FORTRESS': 'fortress_positions',
                'SOLOMON': 'solomon_positions',
                'SAMSON': 'samson_positions',
                'ANCHOR': 'anchor_positions',
                'GIDEON': 'gideon_positions',
                'JUBILEE': 'jubilee_ic_positions',
            }

            # Get performance from actual bot positions tables
            ic_bot_breakdown = {}
            dir_bot_breakdown = {}

            # IC bots: FORTRESS, SAMSON, ANCHOR, JUBILEE
            # Cast to timestamptz to handle FORTRESS TEXT columns and other bots' timestamp columns
            for bot_name in ['FORTRESS', 'SAMSON', 'ANCHOR', 'JUBILEE']:
                table = BOT_TABLES.get(bot_name)
                if table:
                    cursor.execute(f"""
                        SELECT
                            COUNT(*) as trades,
                            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                            SUM(realized_pnl) as total_pnl,
                            AVG(realized_pnl) as avg_pnl
                        FROM {table}
                        WHERE status = 'closed'
                            AND close_time::timestamptz >= NOW() - INTERVAL '{days} days'
                    """)
                    row = cursor.fetchone()
                    if row and row[0]:
                        ic_bot_breakdown[bot_name] = {
                            'trades': row[0] or 0,
                            'wins': row[1] or 0,
                            'pnl': float(row[2] or 0),
                            'win_rate': (row[1] / row[0] * 100) if row[0] else 0
                        }

            # Directional bots: SOLOMON, GIDEON
            # Cast to timestamptz to handle TEXT columns where applicable
            for bot_name in ['SOLOMON', 'GIDEON']:
                table = BOT_TABLES.get(bot_name)
                if table:
                    cursor.execute(f"""
                        SELECT
                            COUNT(*) as trades,
                            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                            SUM(realized_pnl) as total_pnl,
                            AVG(realized_pnl) as avg_pnl
                        FROM {table}
                        WHERE status = 'closed'
                            AND close_time::timestamptz >= NOW() - INTERVAL '{days} days'
                    """)
                    row = cursor.fetchone()
                    if row and row[0]:
                        dir_bot_breakdown[bot_name] = {
                            'trades': row[0] or 0,
                            'wins': row[1] or 0,
                            'pnl': float(row[2] or 0),
                            'win_rate': (row[1] / row[0] * 100) if row[0] else 0
                        }

            conn.close()

            # Aggregate IC stats
            ic_trades = sum(b.get('trades', 0) for b in ic_bot_breakdown.values())
            ic_wins = sum(b.get('wins', 0) for b in ic_bot_breakdown.values())
            ic_total_pnl = sum(b.get('pnl', 0) for b in ic_bot_breakdown.values())
            ic_avg_pnl = ic_total_pnl / ic_trades if ic_trades > 0 else 0

            # Aggregate Directional stats
            dir_trades = sum(b.get('trades', 0) for b in dir_bot_breakdown.values())
            dir_wins = sum(b.get('wins', 0) for b in dir_bot_breakdown.values())
            dir_total_pnl = sum(b.get('pnl', 0) for b in dir_bot_breakdown.values())
            dir_avg_pnl = dir_total_pnl / dir_trades if dir_trades > 0 else 0

            # Build response with actual trade data
            ic_result = {
                'trades': ic_trades,
                'wins': ic_wins,
                'win_rate': (ic_wins / ic_trades * 100) if ic_trades > 0 else 0,
                'total_pnl': ic_total_pnl,
                'avg_pnl': ic_avg_pnl,
                'bots': ['FORTRESS', 'SAMSON', 'ANCHOR', 'JUBILEE'],
                'bot_breakdown': ic_bot_breakdown
            }

            dir_result = {
                'trades': dir_trades,
                'wins': dir_wins,
                'win_rate': (dir_wins / dir_trades * 100) if dir_trades > 0 else 0,
                'total_pnl': dir_total_pnl,
                'avg_pnl': dir_avg_pnl,
                'bots': ['SOLOMON', 'GIDEON'],
                'bot_breakdown': dir_bot_breakdown
            }

            return {
                'status': 'analyzed',
                'period_days': days,
                'data_source': 'unified_trades',
                'iron_condor': ic_result,
                'directional': dir_result,
                'recommendation': self._generate_strategy_recommendation_v2(ic_result, dir_result)
            }

        except Exception as e:
            logger.error(f"Proverbs: Failed to analyze strategies: {e}")
            return {'status': 'error', 'message': str(e)}

    def _generate_strategy_recommendation(self, ic_row, dir_row, ic_trades: int, dir_trades: int) -> str:
        """Generate a recommendation based on strategy performance comparison."""
        if ic_trades < 5 and dir_trades < 5:
            return "Insufficient data - need at least 5 trades per strategy for meaningful analysis"

        ic_win_rate = (ic_row[1] / ic_trades * 100) if ic_trades > 0 else 0
        dir_win_rate = (dir_row[1] / dir_trades * 100) if dir_trades > 0 else 0

        ic_avg_pnl = float(ic_row[3] or 0)
        dir_avg_pnl = float(dir_row[3] or 0)

        if ic_win_rate > dir_win_rate + 10 and ic_avg_pnl > dir_avg_pnl:
            return "Iron Condor strategy outperforming - consider increasing IC allocation"
        elif dir_win_rate > ic_win_rate + 10 and dir_avg_pnl > ic_avg_pnl:
            return "Directional strategy outperforming - market may be trending"
        elif ic_win_rate > 60 and dir_win_rate > 60:
            return "Both strategies performing well - maintain current allocation"
        elif ic_win_rate < 45 and dir_win_rate < 45:
            return "Both strategies underperforming - consider reducing position sizes"
        else:
            return "Strategies performing similarly - no allocation change recommended"

    def _generate_strategy_recommendation_v2(self, ic_result: Dict, dir_result: Dict) -> str:
        """Generate a recommendation based on strategy performance comparison (v2 for unified_trades)."""
        ic_trades = ic_result.get('trades', 0)
        dir_trades = dir_result.get('trades', 0)

        if ic_trades < 5 and dir_trades < 5:
            return "Insufficient data - need at least 5 trades per strategy for meaningful analysis"

        ic_win_rate = ic_result.get('win_rate', 0)
        dir_win_rate = dir_result.get('win_rate', 0)
        ic_avg_pnl = ic_result.get('avg_pnl', 0)
        dir_avg_pnl = dir_result.get('avg_pnl', 0)

        if ic_win_rate > dir_win_rate + 10 and ic_avg_pnl > dir_avg_pnl:
            return "Iron Condor strategy outperforming - consider increasing IC allocation"
        elif dir_win_rate > ic_win_rate + 10 and dir_avg_pnl > ic_avg_pnl:
            return "Directional strategy outperforming - market may be trending"
        elif ic_win_rate > 60 and dir_win_rate > 60:
            return "Both strategies performing well - maintain current allocation"
        elif ic_win_rate < 45 and dir_win_rate < 45:
            return "Both strategies underperforming - consider reducing position sizes"
        else:
            return "Strategies performing similarly - no allocation change recommended"

    def get_prophet_accuracy(self, days: int = 30) -> Dict:
        """
        Analyze Prophet recommendation accuracy by correlating oracle_advice with trade outcomes.

        Migration 023: This measures how well Prophet's advice correlates with actual outcomes.

        Enhancement: Now queries the oracle_advice column directly from position tables to
        measure how often Prophet's TAKE_TRADE vs SKIP advice led to wins or losses.
        """
        if not DB_AVAILABLE:
            return {'status': 'database_unavailable'}

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Bot tables mapping - all have oracle_advice column
            BOT_TABLES = {
                'FORTRESS': 'fortress_positions',
                'SOLOMON': 'solomon_positions',
                'SAMSON': 'samson_positions',
                'ANCHOR': 'anchor_positions',
                'GIDEON': 'gideon_positions',
                'JUBILEE': 'jubilee_ic_positions',
            }

            ic_bots = ['FORTRESS', 'SAMSON', 'ANCHOR', 'JUBILEE']
            dir_bots = ['SOLOMON', 'GIDEON']

            # Step 1: Get Prophet advice accuracy from actual positions tables
            by_advice = {}
            by_strategy = {
                'IRON_CONDOR': {'trades': 0, 'wins': 0, 'total_pnl': 0, 'bots': {}},
                'DIRECTIONAL': {'trades': 0, 'wins': 0, 'total_pnl': 0, 'bots': {}}
            }

            for bot_name, table in BOT_TABLES.items():
                try:
                    # Query oracle_advice accuracy for this bot
                    # Cast to timestamptz to handle FORTRESS TEXT columns and other bots' timestamp columns
                    cursor.execute(f"""
                        SELECT
                            COALESCE(oracle_advice, 'UNKNOWN') as advice,
                            COUNT(*) as trades,
                            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                            COALESCE(SUM(realized_pnl), 0) as total_pnl,
                            COALESCE(AVG(realized_pnl), 0) as avg_pnl
                        FROM {table}
                        WHERE status = 'closed'
                            AND close_time::timestamptz >= NOW() - INTERVAL '{days} days'
                        GROUP BY COALESCE(oracle_advice, 'UNKNOWN')
                    """)
                    rows = cursor.fetchall()

                    for row in rows:
                        advice, trades, wins, total_pnl, avg_pnl = row
                        if not advice or advice == '' or advice == 'UNKNOWN':
                            advice = 'NO_ADVICE'

                        # Aggregate by Prophet advice type
                        if advice not in by_advice:
                            by_advice[advice] = {'count': 0, 'wins': 0, 'total_pnl': 0, 'bots': {}}
                        by_advice[advice]['count'] += trades or 0
                        by_advice[advice]['wins'] += wins or 0
                        by_advice[advice]['total_pnl'] += float(total_pnl or 0)
                        if bot_name not in by_advice[advice]['bots']:
                            by_advice[advice]['bots'][bot_name] = {'trades': 0, 'wins': 0}
                        by_advice[advice]['bots'][bot_name]['trades'] += trades or 0
                        by_advice[advice]['bots'][bot_name]['wins'] += wins or 0

                        # Aggregate by strategy
                        strategy = 'IRON_CONDOR' if bot_name in ic_bots else 'DIRECTIONAL'
                        by_strategy[strategy]['trades'] += trades or 0
                        by_strategy[strategy]['wins'] += wins or 0
                        by_strategy[strategy]['total_pnl'] += float(total_pnl or 0)
                        if bot_name not in by_strategy[strategy]['bots']:
                            by_strategy[strategy]['bots'][bot_name] = {'trades': 0, 'wins': 0, 'total_pnl': 0}
                        by_strategy[strategy]['bots'][bot_name]['trades'] += trades or 0
                        by_strategy[strategy]['bots'][bot_name]['wins'] += wins or 0
                        by_strategy[strategy]['bots'][bot_name]['total_pnl'] += float(total_pnl or 0)

                except Exception as e:
                    logger.warning(f"Could not query oracle_advice from {table}: {e}")
                    continue

            conn.close()

            # Calculate accuracy metrics for each advice type
            for advice in by_advice:
                count = by_advice[advice]['count']
                wins = by_advice[advice]['wins']
                total_pnl = by_advice[advice]['total_pnl']
                by_advice[advice]['accuracy'] = (wins / count * 100) if count > 0 else 0
                by_advice[advice]['avg_pnl'] = (total_pnl / count) if count > 0 else 0

            # Calculate strategy-level metrics
            for strategy in by_strategy:
                trades = by_strategy[strategy]['trades']
                wins = by_strategy[strategy]['wins']
                total_pnl = by_strategy[strategy]['total_pnl']
                by_strategy[strategy]['count'] = trades
                by_strategy[strategy]['accuracy'] = (wins / trades * 100) if trades > 0 else 0
                by_strategy[strategy]['avg_pnl'] = (total_pnl / trades) if trades > 0 else 0
                # Calculate per-bot win rates
                for bot in by_strategy[strategy]['bots']:
                    b = by_strategy[strategy]['bots'][bot]
                    b['win_rate'] = (b['wins'] / b['trades'] * 100) if b['trades'] > 0 else 0

            # Generate summary
            total_trades = sum(s['trades'] for s in by_strategy.values())
            total_wins = sum(s['wins'] for s in by_strategy.values())
            overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

            # Check Prophet advice effectiveness
            take_trade = by_advice.get('TAKE_TRADE', {})
            skip = by_advice.get('SKIP', {})
            take_accuracy = take_trade.get('accuracy', 0)
            take_count = take_trade.get('count', 0)

            summary_text = f"Analyzed {total_trades} trades over {days} days. "
            if take_count > 0:
                summary_text += f"When Prophet advised TAKE_TRADE: {take_accuracy:.1f}% win rate ({take_count} trades). "
            if overall_win_rate >= 60:
                summary_text += f"Overall win rate of {overall_win_rate:.1f}% is strong."
            elif overall_win_rate >= 50:
                summary_text += f"Overall win rate of {overall_win_rate:.1f}% is acceptable."
            else:
                summary_text += f"Overall win rate of {overall_win_rate:.1f}% needs improvement."

            return {
                'status': 'analyzed',
                'period_days': days,
                'data_source': 'bot_positions_tables (oracle_advice column)',
                'by_advice': by_advice,
                'by_strategy': by_strategy,
                'summary': summary_text,
                'summary_data': {
                    'total_trades': total_trades,
                    'total_wins': total_wins,
                    'overall_win_rate': overall_win_rate,
                    'summary_text': summary_text
                }
            }

        except Exception as e:
            logger.error(f"Proverbs: Failed to analyze Prophet accuracy: {e}")
            return {'status': 'error', 'message': str(e)}

    def _generate_prophet_accuracy_summary(self, advice_analysis: Dict) -> Dict:
        """Generate summary of Prophet accuracy."""
        summary = {
            'trade_full_effective': False,
            'trade_reduced_effective': False,
            'skip_followed': False,
            'recommendations': [],
            'summary_text': ''
        }

        full_win_rate = 0
        reduced_win_rate = 0

        if 'TRADE_FULL' in advice_analysis:
            full_trades = advice_analysis['TRADE_FULL']
            total_full_wins = sum(s.get('wins', 0) for s in full_trades.values())
            total_full_trades = sum(s.get('trades', 0) for s in full_trades.values())
            if total_full_trades > 0:
                full_win_rate = total_full_wins / total_full_trades * 100
                summary['trade_full_effective'] = full_win_rate > 50
                if full_win_rate < 45:
                    summary['recommendations'].append("TRADE_FULL signals underperforming - review confidence thresholds")

        if 'TRADE_REDUCED' in advice_analysis:
            reduced_trades = advice_analysis['TRADE_REDUCED']
            total_reduced_wins = sum(s.get('wins', 0) for s in reduced_trades.values())
            total_reduced_trades = sum(s.get('trades', 0) for s in reduced_trades.values())
            if total_reduced_trades > 0:
                reduced_win_rate = total_reduced_wins / total_reduced_trades * 100
                summary['trade_reduced_effective'] = reduced_win_rate > 40

        # Generate human-readable summary text
        summary_parts = []
        if summary['trade_full_effective']:
            summary_parts.append(f"TRADE_FULL signals are effective ({full_win_rate:.1f}% win rate)")
        elif full_win_rate > 0:
            summary_parts.append(f"TRADE_FULL signals need review ({full_win_rate:.1f}% win rate)")

        if summary['trade_reduced_effective']:
            summary_parts.append(f"TRADE_REDUCED signals performing adequately ({reduced_win_rate:.1f}%)")

        if summary['recommendations']:
            summary_parts.extend(summary['recommendations'])

        summary['summary_text'] = ' | '.join(summary_parts) if summary_parts else 'Insufficient data for Prophet accuracy analysis'

        return summary

    def get_bot_strategy_config(self, bot_name: str) -> Dict:
        """Get strategy configuration for a specific bot."""
        return self.BOT_STRATEGY_CONFIGS.get(bot_name, {'strategy_type': 'UNKNOWN', 'goal': 'unknown'})

    # =========================================================================
    # PROPOSAL VALIDATION WORKFLOW
    # =========================================================================

    def create_proposal_with_reasoning(
        self,
        bot_name: str,
        title: str,
        problem_statement: str,
        hypothesis: str,
        supporting_evidence: List[Dict],
        expected_improvement: Dict,
        current_config: Dict,
        proposed_config: Dict,
        risk_level: str = "MEDIUM",
        risk_assessment: str = "",
        potential_downsides: List[str] = None,
        validation_method: str = "AB_TEST"
    ) -> Dict:
        """
        Create a proposal with complete reasoning documentation.

        This is the recommended way to create proposals as it enforces
        detailed reasoning and sets up validation.

        Returns dict with proposal_id, reasoning, and validation_id.
        """
        from quant.proverbs_feedback_loop import ProposalType

        # Create the reasoning document
        reasoning = self.proposal_validator.create_proposal_reasoning(
            proposal_id="PENDING",  # Will be updated
            problem_statement=problem_statement,
            hypothesis=hypothesis,
            supporting_evidence=supporting_evidence,
            expected_improvement=expected_improvement,
            risk_assessment=risk_assessment or f"Risk level: {risk_level}",
            potential_downsides=potential_downsides or [],
            validation_method=validation_method
        )

        # Validate the reasoning is complete
        is_valid, issues = self.proposal_validator.validate_proposal_reasoning(reasoning)
        if not is_valid:
            return {
                'success': False,
                'error': 'Incomplete proposal reasoning',
                'issues': issues
            }

        # Create the proposal in base Proverbs
        proposal_id = self.proverbs.create_proposal(
            bot_name=bot_name,
            proposal_type=ProposalType.MODEL_UPDATE,
            title=title,
            description=f"PROBLEM: {problem_statement}\nHYPOTHESIS: {hypothesis}",
            current_value=current_config,
            proposed_value=proposed_config,
            reason=hypothesis,
            supporting_metrics={
                'evidence': supporting_evidence,
                'expected_improvement': expected_improvement
            },
            expected_improvement=expected_improvement,
            risk_level=risk_level,
            risk_factors=potential_downsides or [],
            rollback_plan="Automatic rollback if improvement not proven during validation"
        )

        if not proposal_id:
            return {
                'success': False,
                'error': 'Failed to create proposal'
            }

        # Update reasoning with actual proposal ID
        reasoning.proposal_id = proposal_id
        self._proposal_reasoning[proposal_id] = reasoning

        # Start validation
        validation_id = self.proposal_validator.start_validation(
            proposal_id=proposal_id,
            bot_name=bot_name,
            current_config=current_config,
            proposed_config=proposed_config,
            method=validation_method
        )

        return {
            'success': True,
            'proposal_id': proposal_id,
            'validation_id': validation_id,
            'reasoning': reasoning.to_dict(),
            'status': 'PENDING_VALIDATION',
            'message': f"Proposal created. Validation started using {validation_method}. "
                       f"Changes will only be applied after improvement is proven."
        }

    def get_proposal_reasoning(self, proposal_id: str) -> Optional[Dict]:
        """Get detailed reasoning for a proposal"""
        # First check in-memory cache
        if proposal_id in self._proposal_reasoning:
            return self._proposal_reasoning[proposal_id].to_dict()

        # Fallback: Reconstruct reasoning from database proposal
        proposals = self.proverbs.get_pending_proposals()
        proposal = next((p for p in proposals if p.get('proposal_id') == proposal_id), None)

        if not proposal:
            # Also check non-pending proposals
            try:
                from database_adapter import get_connection
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT reason, supporting_metrics, expected_improvement, risk_factors, description "
                    "FROM proverbs_proposals WHERE proposal_id = %s",
                    (proposal_id,)
                )
                row = cursor.fetchone()
                conn.close()

                if row:
                    reason, supporting_metrics, expected_improvement, risk_factors, description = row
                    # Parse JSONB fields
                    import json
                    if isinstance(supporting_metrics, str):
                        supporting_metrics = json.loads(supporting_metrics) if supporting_metrics else {}
                    if isinstance(expected_improvement, str):
                        expected_improvement = json.loads(expected_improvement) if expected_improvement else {}
                    if isinstance(risk_factors, str):
                        risk_factors = json.loads(risk_factors) if risk_factors else []

                    proposal = {
                        'reason': reason,
                        'supporting_metrics': supporting_metrics or {},
                        'expected_improvement': expected_improvement or {},
                        'risk_factors': risk_factors or [],
                        'description': description
                    }
            except Exception as e:
                logger.debug(f"Could not fetch proposal from DB: {e}")
                return None

        if not proposal:
            return None

        # Reconstruct reasoning from proposal data
        supporting_metrics = proposal.get('supporting_metrics', {})
        return {
            'proposal_id': proposal_id,
            'problem_statement': proposal.get('description', ''),
            'hypothesis': proposal.get('reason', ''),
            'supporting_evidence': supporting_metrics.get('evidence', []),
            'expected_improvement': proposal.get('expected_improvement', {}),
            'confidence_level': supporting_metrics.get('confidence_level', 0.7),
            'success_criteria': supporting_metrics.get('success_criteria', {
                'min_improvement_pct': 5.0,
                'min_trades': 20,
                'min_days': 7
            }),
            'rollback_trigger': supporting_metrics.get('rollback_trigger', {
                'max_drawdown_pct': 15.0
            }),
            'risk_factors': proposal.get('risk_factors', [])
        }

    def can_apply_proposal(self, proposal_id: str) -> Dict:
        """
        Check if a proposal can be applied.

        Returns detailed status on why/why not.
        """
        # First check if proposal exists and is not expired
        proposals = self.proverbs.get_pending_proposals()
        proposal = next((p for p in proposals if p.get('proposal_id') == proposal_id), None)

        if not proposal:
            return {
                'can_apply': False,
                'improvement_proven': False,
                'rejection_reasons': ['Proposal not found'],
                'message': 'Proposal not found'
            }

        # Check if proposal has expired
        if proposal.get('status') == 'EXPIRED':
            return {
                'can_apply': False,
                'improvement_proven': False,
                'rejection_reasons': ['Proposal has expired'],
                'message': 'Proposal has expired and cannot be applied'
            }

        # Check expiration date
        expires_at = proposal.get('expires_at')
        if expires_at:
            from datetime import datetime
            try:
                if isinstance(expires_at, str):
                    exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                else:
                    exp_dt = expires_at
                if exp_dt < datetime.now(CENTRAL_TZ):
                    return {
                        'can_apply': False,
                        'improvement_proven': False,
                        'rejection_reasons': ['Proposal has expired'],
                        'message': 'Proposal has expired and cannot be applied'
                    }
            except (ValueError, TypeError):
                pass  # If we can't parse the date, proceed with validation check

        # Find the validation for this proposal
        validations = self.proposal_validator.get_pending_validations()
        proposal_validation = None

        for v in validations:
            if v['proposal_id'] == proposal_id:
                proposal_validation = v
                break

        if not proposal_validation:
            return {
                'can_apply': False,
                'improvement_proven': False,
                'rejection_reasons': ['Validation not started'],
                'message': 'No validation found for this proposal. Start validation before applying.'
            }

        # Evaluate the validation
        result = self.proposal_validator.evaluate_validation(proposal_validation['validation_id'])

        if result.can_apply:
            return {
                'can_apply': True,
                'improvement_proven': True,
                'improvement_metrics': result.improvement_metrics,
                'detailed_reasoning': result.detailed_reasoning,
                'message': 'Improvement has been PROVEN. Proposal can be applied.'
            }
        else:
            return {
                'can_apply': False,
                'improvement_proven': result.improvement_proven,
                'rejection_reasons': result.rejection_reasons,
                'improvement_metrics': result.improvement_metrics,
                'detailed_reasoning': result.detailed_reasoning,
                'message': 'Improvement has NOT been proven. Proposal cannot be applied yet.'
            }

    def apply_validated_proposal(
        self,
        proposal_id: str,
        reviewer: str
    ) -> Dict:
        """
        Apply a proposal ONLY if validation proves improvement.

        This is the safe way to apply proposals - it enforces the
        "proven improvement required" policy.
        """
        # Check if we can apply
        can_apply_result = self.can_apply_proposal(proposal_id)

        if not can_apply_result['can_apply']:
            return {
                'success': False,
                'error': 'Cannot apply proposal - improvement not proven',
                'details': can_apply_result
            }

        # Get reasoning for logging
        reasoning = self.get_proposal_reasoning(proposal_id)

        # Apply via base Proverbs
        success = self.proverbs.approve_proposal(
            proposal_id=proposal_id,
            reviewer=reviewer,
            notes=f"VALIDATED: Improvement proven. {can_apply_result.get('message', '')}"
        )

        if success:
            # Log the detailed reasoning
            # Import ActionType for logging
            from quant.proverbs_feedback_loop import ActionType
            self.proverbs.log_action(
                bot_name=reasoning.get('bot_name', 'UNKNOWN') if reasoning else 'UNKNOWN',
                action_type=ActionType.PROPOSAL_APPROVED,
                description=f"Proposal {proposal_id} applied after validation proved improvement",
                reason="Improvement proven through validation",
                justification={
                    'validation_result': can_apply_result,
                    'reasoning': reasoning
                }
            )

            return {
                'success': True,
                'proposal_id': proposal_id,
                'applied_by': reviewer,
                'validation_result': can_apply_result,
                'reasoning': reasoning,
                'message': 'Proposal applied successfully after proving improvement.'
            }

        return {
            'success': False,
            'error': 'Failed to apply proposal',
            'validation_result': can_apply_result
        }

    def get_validation_status(self, proposal_id: str = None) -> Dict:
        """
        Get status of all validations or a specific proposal's validation.
        """
        validations = self.proposal_validator.get_pending_validations()

        if proposal_id:
            for v in validations:
                if v['proposal_id'] == proposal_id:
                    result = self.proposal_validator.evaluate_validation(v['validation_id'])
                    return {
                        'validation': v,
                        'evaluation': result.to_dict()
                    }
            return {'error': 'Validation not found for proposal'}

        # Return all validations with their evaluation status
        results = []
        for v in validations:
            evaluation = self.proposal_validator.evaluate_validation(v['validation_id'])
            results.append({
                'validation': v,
                'evaluation': evaluation.to_dict()
            })

        return {
            'validations': results,
            'total': len(results),
            'ready_to_apply': sum(1 for r in results if r['evaluation']['can_apply'])
        }

    def get_proposal_transparency_report(self, proposal_id: str) -> Dict:
        """
        Get complete transparency report for a proposal.

        This shows ALL the details of WHY a change is being made.
        """
        # Get proposal from base Proverbs
        proposals = self.proverbs.get_pending_proposals()
        proposal = None
        for p in proposals:
            if p.get('proposal_id') == proposal_id:
                proposal = p
                break

        if not proposal:
            # Check audit log for applied proposals
            audit = self.proverbs.get_audit_log(limit=100)
            for entry in audit:
                if entry.get('proposal_id') == proposal_id:
                    proposal = entry
                    break

        reasoning = self.get_proposal_reasoning(proposal_id)
        validation_status = self.get_validation_status(proposal_id)

        return {
            'proposal_id': proposal_id,
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),

            # WHO is making the change
            'who': {
                'proposed_by': 'PROVERBS' if proposal else 'Unknown',
                'requires_approval_from': 'Human operator',
                'approval_status': proposal.get('status', 'Unknown') if proposal else 'Unknown'
            },

            # WHAT is changing
            'what': {
                'title': proposal.get('title', 'Unknown') if proposal else 'Unknown',
                'description': proposal.get('description', '') if proposal else '',
                'current_value': proposal.get('current_value', {}) if proposal else {},
                'proposed_value': proposal.get('proposed_value', {}) if proposal else {},
                'change_summary': proposal.get('change_summary', '') if proposal else ''
            },

            # WHY is this change being made (DETAILED)
            'why': {
                'problem_statement': reasoning.get('problem_statement', '') if reasoning else '',
                'hypothesis': reasoning.get('hypothesis', '') if reasoning else '',
                'supporting_evidence': reasoning.get('supporting_evidence', []) if reasoning else [],
                'expected_improvement': reasoning.get('expected_improvement', {}) if reasoning else {},
                'confidence_level': reasoning.get('confidence_level', 0) if reasoning else 0,
                'supporting_metrics': proposal.get('supporting_metrics', {}) if proposal else {}
            },

            # WHEN will this be applied
            'when': {
                'created_at': proposal.get('created_at', '') if proposal else '',
                'expires_at': proposal.get('expires_at', '') if proposal else '',
                'validation_started': validation_status.get('validation', {}).get('started_at', '') if 'validation' in validation_status else '',
                'can_apply_after_validation': validation_status.get('evaluation', {}).get('can_apply', False) if 'evaluation' in validation_status else False
            },

            # VALIDATION status
            'validation': validation_status,

            # RISK assessment
            'risk': {
                'risk_level': proposal.get('risk_level', 'Unknown') if proposal else 'Unknown',
                'risk_factors': proposal.get('risk_factors', []) if proposal else [],
                'potential_downsides': reasoning.get('potential_downsides', []) if reasoning else [],
                'mitigation_strategies': reasoning.get('mitigation_strategies', []) if reasoning else [],
                'rollback_plan': proposal.get('rollback_plan', '') if proposal else ''
            },

            # SUCCESS criteria
            'success_criteria': reasoning.get('success_criteria', {}) if reasoning else {},

            # ROLLBACK triggers
            'rollback_triggers': reasoning.get('rollback_trigger', {}) if reasoning else {}
        }


# =============================================================================
# SINGLETON
# =============================================================================

_enhanced: Optional[ProverbsEnhanced] = None


def get_proverbs_enhanced():
    """Get or create enhanced Proverbs singleton"""
    global _enhanced

    if _enhanced is None:
        from quant.proverbs_feedback_loop import get_proverbs
        _enhanced = ProverbsEnhanced(get_proverbs())

    return _enhanced


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    enhanced = get_proverbs_enhanced()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "analysis":
            bot = sys.argv[2] if len(sys.argv) > 2 else "FORTRESS"
            analysis = enhanced.get_comprehensive_analysis(bot)
            print(json.dumps(analysis, indent=2, default=str))

        elif command == "correlations":
            corr = enhanced.get_portfolio_correlations()
            print(json.dumps(corr, indent=2, default=str))

        elif command == "digest":
            digest = enhanced.daily_digest.generate_digest()
            print(json.dumps(digest, indent=2, default=str))

        elif command == "precheck":
            precheck = enhanced.weekend_precheck.generate_precheck()
            print(json.dumps(precheck.to_dict(), indent=2, default=str))

        else:
            print(f"Unknown command: {command}")
    else:
        print("Proverbs Enhanced - Advanced Features")
        print("Commands: analysis [bot], correlations, digest, precheck")
