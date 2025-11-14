"""
Backtesting Engine for Psychology Trap Patterns
Tests each pattern against historical data to validate effectiveness

Validates:
- Liberation setups
- False floor detection
- Gamma squeeze patterns
- All psychology trap patterns

Measures:
- Win rate
- Average profit/loss
- Max drawdown
- Sharpe ratio
- Pattern accuracy
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from config_and_database import DB_PATH
import pandas as pd
import numpy as np


class PatternBacktester:
    """Backtest psychology trap patterns against historical data"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def backtest_pattern(self, pattern_name: str, lookback_days: int = 90) -> Dict:
        """
        Backtest a specific pattern

        Returns:
            {
                'pattern': str,
                'total_signals': int,
                'win_rate': float,
                'avg_profit_pct': float,
                'avg_loss_pct': float,
                'max_win_pct': float,
                'max_loss_pct': float,
                'sharpe_ratio': float,
                'profit_factor': float,
                'expectancy': float,
                'signals': List[Dict]  # Individual signal details
            }
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Get historical signals for this pattern
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        c.execute("""
            SELECT
                id, timestamp, spy_price, confidence_score, trade_direction,
                price_change_1d, price_change_5d, signal_correct,
                target_price_near, target_timeline_days
            FROM regime_signals
            WHERE primary_regime_type = ?
            AND timestamp >= ?
            ORDER BY timestamp DESC
        """, (pattern_name, start_date))

        signals = []
        for row in c.fetchall():
            signals.append({
                'id': row[0],
                'timestamp': row[1],
                'entry_price': row[2],
                'confidence': row[3],
                'direction': row[4],
                'price_change_1d': row[5],
                'price_change_5d': row[6],
                'correct': row[7],
                'target': row[8],
                'timeline': row[9]
            })

        conn.close()

        if not signals:
            return self._empty_backtest_result(pattern_name)

        # Calculate statistics
        total_signals = len(signals)
        winning_signals = sum(1 for s in signals if s['correct'] == 1)
        losing_signals = total_signals - winning_signals

        win_rate = (winning_signals / total_signals * 100) if total_signals > 0 else 0

        # Calculate profit/loss percentages
        profits = [s['price_change_5d'] for s in signals if s['price_change_5d'] and s['correct'] == 1]
        losses = [s['price_change_5d'] for s in signals if s['price_change_5d'] and s['correct'] == 0]

        avg_profit_pct = np.mean(profits) if profits else 0
        avg_loss_pct = np.mean(losses) if losses else 0
        max_win_pct = max(profits) if profits else 0
        max_loss_pct = min(losses) if losses else 0

        # Calculate Sharpe Ratio
        all_returns = [s['price_change_5d'] for s in signals if s['price_change_5d']]
        sharpe = self._calculate_sharpe(all_returns)

        # Profit Factor: total wins / total losses
        total_wins = sum(profits) if profits else 0
        total_losses = abs(sum(losses)) if losses else 0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else 0

        # Expectancy: (win_rate * avg_win) - (loss_rate * avg_loss)
        expectancy = (win_rate / 100 * avg_profit_pct) + ((1 - win_rate / 100) * avg_loss_pct)

        return {
            'pattern': pattern_name,
            'total_signals': total_signals,
            'winning_signals': winning_signals,
            'losing_signals': losing_signals,
            'win_rate': win_rate,
            'avg_profit_pct': avg_profit_pct,
            'avg_loss_pct': avg_loss_pct,
            'max_win_pct': max_win_pct,
            'max_loss_pct': max_loss_pct,
            'sharpe_ratio': sharpe,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'signals': signals
        }

    def backtest_all_patterns(self, lookback_days: int = 90) -> List[Dict]:
        """Backtest all patterns and return ranked results"""
        # Get list of all patterns
        patterns = self._get_all_patterns()

        results = []
        for pattern in patterns:
            result = self.backtest_pattern(pattern, lookback_days)
            results.append(result)

        # Sort by expectancy (best to worst)
        results.sort(key=lambda x: x['expectancy'], reverse=True)

        return results

    def analyze_liberation_accuracy(self, lookback_days: int = 90) -> Dict:
        """Analyze accuracy of liberation setup detection"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        c.execute("""
            SELECT
                COUNT(*) as total_liberations,
                SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as successful,
                AVG(price_change_5d) as avg_move_pct,
                AVG(confidence_score) as avg_confidence
            FROM regime_signals
            WHERE liberation_setup_detected = 1
            AND timestamp >= ?
        """, (start_date,))

        row = c.fetchone()
        conn.close()

        total = row[0] if row[0] else 0
        successful = row[1] if row[1] else 0
        avg_move = row[2] if row[2] else 0
        avg_confidence = row[3] if row[3] else 0

        accuracy = (successful / total * 100) if total > 0 else 0

        return {
            'total_liberation_signals': total,
            'successful_liberations': successful,
            'accuracy_pct': accuracy,
            'avg_move_after_liberation_pct': avg_move,
            'avg_confidence': avg_confidence
        }

    def analyze_false_floor_effectiveness(self, lookback_days: int = 90) -> Dict:
        """Analyze how effective false floor detection is at preventing bad trades"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        # Get signals where false floor was detected and trade direction was bearish
        c.execute("""
            SELECT
                COUNT(*) as total_false_floors,
                AVG(price_change_5d) as avg_move_pct
            FROM regime_signals
            WHERE false_floor_detected = 1
            AND trade_direction = 'BEARISH'
            AND timestamp >= ?
        """, (start_date,))

        row = c.fetchone()
        total = row[0] if row[0] else 0
        avg_move = row[1] if row[1] else 0

        conn.close()

        # If avg_move is positive, false floor detection saved us from bad short trades
        saved_trades = total if avg_move > 0 else 0

        return {
            'total_false_floor_detections': total,
            'avoided_bad_short_trades': saved_trades,
            'avg_price_move_pct': avg_move,
            'effectiveness': 'GOOD' if avg_move > 0 else 'POOR'
        }

    def save_backtest_results(self, results: Dict):
        """Save backtest results to database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO backtest_results (
                timestamp, strategy_name, symbol, start_date, end_date,
                total_trades, winning_trades, losing_trades, win_rate,
                avg_win_pct, avg_loss_pct, largest_win_pct, largest_loss_pct,
                expectancy_pct, total_return_pct, max_drawdown_pct, sharpe_ratio,
                avg_trade_duration_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            results['pattern'],
            'SPY',
            results.get('start_date', ''),
            results.get('end_date', ''),
            results['total_signals'],
            results['winning_signals'],
            results['losing_signals'],
            results['win_rate'],
            results['avg_profit_pct'],
            results['avg_loss_pct'],
            results['max_win_pct'],
            results['max_loss_pct'],
            results['expectancy'],
            0,  # total_return_pct (calculate if needed)
            0,  # max_drawdown_pct (calculate if needed)
            results['sharpe_ratio'],
            results.get('avg_duration', 5)
        ))

        conn.commit()
        conn.close()

    # Helper methods
    def _calculate_sharpe(self, returns: List[float]) -> float:
        """Calculate Sharpe Ratio"""
        if len(returns) < 2:
            return 0.0

        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        # Annualized Sharpe (252 trading days)
        sharpe = (mean_return / std_return) * np.sqrt(252 / 5)  # 5-day holding period

        return sharpe

    def _get_all_patterns(self) -> List[str]:
        """Get list of all detected patterns"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            SELECT DISTINCT primary_regime_type
            FROM regime_signals
            WHERE primary_regime_type IS NOT NULL
        """)

        patterns = [row[0] for row in c.fetchall()]
        conn.close()

        return patterns

    def _empty_backtest_result(self, pattern_name: str) -> Dict:
        """Return empty result when no signals found"""
        return {
            'pattern': pattern_name,
            'total_signals': 0,
            'winning_signals': 0,
            'losing_signals': 0,
            'win_rate': 0,
            'avg_profit_pct': 0,
            'avg_loss_pct': 0,
            'max_win_pct': 0,
            'max_loss_pct': 0,
            'sharpe_ratio': 0,
            'profit_factor': 0,
            'expectancy': 0,
            'signals': []
        }


# Singleton instance
_backtester = None

def get_backtester() -> PatternBacktester:
    """Get singleton backtester"""
    global _backtester
    if _backtester is None:
        _backtester = PatternBacktester()
    return _backtester
