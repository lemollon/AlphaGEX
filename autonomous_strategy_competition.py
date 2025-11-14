"""
Paper Trading Competition - Multiple Strategies Compete
Each strategy gets equal capital and trades independently

Tracks:
- Win rate per strategy
- Total P&L
- Sharpe ratio
- Max drawdown
- Risk-adjusted returns
- Pattern preferences

Strategies Competing:
1. Psychology Trap + Liberation (our main strategy)
2. Pure GEX Regime (basic GEX only)
3. RSI + Gamma Walls (technical + GEX)
4. Liberation Only (only trade liberation setups)
5. Forward Magnets Only (target monthly OPEX)
6. Conservative (low risk, high probability only)
7. Aggressive (high risk, high reward)
8. AI-Only (Claude makes all decisions)
"""

import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from config_and_database import DB_PATH
import pandas as pd


class StrategyCompetition:
    """Run competitive paper trading across multiple strategies"""

    def __init__(self, starting_capital: float = 5000.0, db_path: str = DB_PATH):
        self.starting_capital = starting_capital
        self.db_path = db_path

        # Define competing strategies
        self.strategies = {
            'PSYCHOLOGY_TRAP_FULL': {
                'name': 'Psychology Trap + Liberation',
                'description': 'Full system with all layers',
                'filters': {
                    'use_psychology_trap': True,
                    'use_liberation': True,
                    'use_false_floor': True,
                    'use_forward_magnets': True,
                    'use_rsi': True,
                    'min_confidence': 70
                }
            },
            'PURE_GEX': {
                'name': 'Pure GEX Regime',
                'description': 'Basic GEX analysis only',
                'filters': {
                    'use_psychology_trap': False,
                    'use_liberation': False,
                    'use_false_floor': False,
                    'use_forward_magnets': False,
                    'use_rsi': False,
                    'min_confidence': 60
                }
            },
            'RSI_GAMMA_WALLS': {
                'name': 'RSI + Gamma Walls',
                'description': 'Technical analysis with gamma walls',
                'filters': {
                    'use_psychology_trap': False,
                    'use_liberation': False,
                    'use_false_floor': False,
                    'use_forward_magnets': False,
                    'use_rsi': True,
                    'min_confidence': 65,
                    'require_rsi_alignment': True
                }
            },
            'LIBERATION_ONLY': {
                'name': 'Liberation Setups Only',
                'description': 'Only trades liberation setups',
                'filters': {
                    'use_psychology_trap': True,
                    'use_liberation': True,
                    'use_false_floor': False,
                    'use_forward_magnets': False,
                    'use_rsi': False,
                    'min_confidence': 75,
                    'require_liberation': True
                }
            },
            'FORWARD_MAGNETS': {
                'name': 'Forward GEX Magnets',
                'description': 'Target monthly OPEX strikes',
                'filters': {
                    'use_psychology_trap': True,
                    'use_liberation': False,
                    'use_false_floor': False,
                    'use_forward_magnets': True,
                    'use_rsi': False,
                    'min_confidence': 65
                }
            },
            'CONSERVATIVE': {
                'name': 'Conservative (Low Risk)',
                'description': 'High probability, low risk only',
                'filters': {
                    'use_psychology_trap': True,
                    'use_liberation': True,
                    'use_false_floor': True,
                    'use_forward_magnets': True,
                    'use_rsi': True,
                    'min_confidence': 85,
                    'max_position_size_pct': 10  # Only 10% per trade
                }
            },
            'AGGRESSIVE': {
                'name': 'Aggressive (High Risk)',
                'description': 'High risk, high reward',
                'filters': {
                    'use_psychology_trap': True,
                    'use_liberation': True,
                    'use_false_floor': False,  # Take more risks
                    'use_forward_magnets': True,
                    'use_rsi': False,
                    'min_confidence': 60,  # Lower bar
                    'max_position_size_pct': 25  # Bigger positions
                }
            },
            'AI_ONLY': {
                'name': 'AI-Powered (Claude Decision)',
                'description': 'Claude makes all decisions',
                'filters': {
                    'use_psychology_trap': True,
                    'use_liberation': True,
                    'use_false_floor': True,
                    'use_forward_magnets': True,
                    'use_rsi': True,
                    'use_ai_evaluation': True,  # Must pass AI evaluation
                    'min_confidence': 70
                }
            }
        }

        self._initialize_competition()

    def _initialize_competition(self):
        """Initialize competition in database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Create competition table if not exists
        c.execute("""
            CREATE TABLE IF NOT EXISTS strategy_competition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                starting_capital REAL NOT NULL,
                current_capital REAL NOT NULL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                sharpe_ratio REAL DEFAULT 0,
                max_drawdown_pct REAL DEFAULT 0,
                profit_factor REAL DEFAULT 0,
                last_trade_date TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy_id)
            )
        """)

        # Initialize each strategy
        for strategy_id, strategy in self.strategies.items():
            c.execute("""
                INSERT OR IGNORE INTO strategy_competition (
                    strategy_id, strategy_name, starting_capital, current_capital
                ) VALUES (?, ?, ?, ?)
            """, (strategy_id, strategy['name'], self.starting_capital, self.starting_capital))

        conn.commit()
        conn.close()

    def get_leaderboard(self) -> List[Dict]:
        """Get current competition leaderboard"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT
                strategy_id, strategy_name, starting_capital, current_capital,
                total_trades, winning_trades, losing_trades, total_pnl,
                win_rate, sharpe_ratio, max_drawdown_pct, profit_factor,
                ((current_capital - starting_capital) / starting_capital * 100) as return_pct
            FROM strategy_competition
            ORDER BY return_pct DESC
        """)

        leaderboard = [dict(row) for row in c.fetchall()]
        conn.close()

        # Add rank
        for i, entry in enumerate(leaderboard, 1):
            entry['rank'] = i

        return leaderboard

    def get_strategy_performance(self, strategy_id: str) -> Dict:
        """Get detailed performance for a specific strategy"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT * FROM strategy_competition WHERE strategy_id = ?
        """, (strategy_id,))

        result = c.fetchone()
        conn.close()

        if not result:
            return {}

        performance = dict(result)

        # Add strategy config
        performance['config'] = self.strategies.get(strategy_id, {})

        return performance

    def record_trade(self, strategy_id: str, trade_result: Dict):
        """Record trade result for a strategy"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Get current stats
        c.execute("""
            SELECT current_capital, total_trades, winning_trades, losing_trades, total_pnl
            FROM strategy_competition
            WHERE strategy_id = ?
        """, (strategy_id,))

        row = c.fetchone()

        if not row:
            print(f"⚠️ Strategy {strategy_id} not found")
            conn.close()
            return

        current_capital = row[0]
        total_trades = row[1]
        winning_trades = row[2]
        losing_trades = row[3]
        total_pnl = row[4]

        # Update with new trade
        pnl = trade_result.get('pnl', 0)
        new_capital = current_capital + pnl
        new_total_trades = total_trades + 1
        new_winning_trades = winning_trades + (1 if pnl > 0 else 0)
        new_losing_trades = losing_trades + (1 if pnl <= 0 else 0)
        new_total_pnl = total_pnl + pnl

        new_win_rate = (new_winning_trades / new_total_trades * 100) if new_total_trades > 0 else 0

        # Update database
        c.execute("""
            UPDATE strategy_competition
            SET
                current_capital = ?,
                total_trades = ?,
                winning_trades = ?,
                losing_trades = ?,
                total_pnl = ?,
                win_rate = ?,
                last_trade_date = ?,
                updated_at = ?
            WHERE strategy_id = ?
        """, (
            new_capital, new_total_trades, new_winning_trades, new_losing_trades,
            new_total_pnl, new_win_rate, datetime.now().strftime('%Y-%m-%d'),
            datetime.now().isoformat(), strategy_id
        ))

        conn.commit()
        conn.close()

    def get_comparison_summary(self) -> Dict:
        """Get summary comparison of all strategies"""
        leaderboard = self.get_leaderboard()

        if not leaderboard:
            return {}

        best_strategy = leaderboard[0]
        worst_strategy = leaderboard[-1]

        return {
            'total_strategies': len(leaderboard),
            'best_strategy': {
                'name': best_strategy['strategy_name'],
                'return_pct': best_strategy['return_pct'],
                'win_rate': best_strategy['win_rate'],
                'total_trades': best_strategy['total_trades']
            },
            'worst_strategy': {
                'name': worst_strategy['strategy_name'],
                'return_pct': worst_strategy['return_pct'],
                'win_rate': worst_strategy['win_rate'],
                'total_trades': worst_strategy['total_trades']
            },
            'leaderboard': leaderboard
        }

    def should_trade_for_strategy(self, strategy_id: str, regime: Dict) -> bool:
        """Determine if a strategy should take this trade based on its filters"""
        strategy = self.strategies.get(strategy_id)

        if not strategy:
            return False

        filters = strategy['filters']

        # Check min confidence
        if regime.get('confidence_score', 0) < filters.get('min_confidence', 70):
            return False

        # Check liberation requirement
        if filters.get('require_liberation') and not regime.get('liberation_setup_detected'):
            return False

        # Check RSI alignment requirement
        if filters.get('require_rsi_alignment'):
            if not regime.get('rsi_aligned_overbought') and not regime.get('rsi_aligned_oversold'):
                return False

        # Check false floor (if strategy uses it)
        if filters.get('use_false_floor') and regime.get('false_floor_detected'):
            # Don't trade bearish if false floor detected
            if regime.get('trade_direction') == 'BEARISH':
                return False

        return True


# Singleton instance
_competition = None

def get_competition() -> StrategyCompetition:
    """Get singleton competition instance"""
    global _competition
    if _competition is None:
        _competition = StrategyCompetition()
    return _competition
