"""
AlphaGEX AI Strategy Optimizer
Powered by Claude + LangChain

This system makes your trading strategies SMARTER over time by:
1. Analyzing backtest results to identify what works
2. Suggesting parameter improvements (entry rules, stops, position sizing)
3. Learning from winning vs losing patterns
4. Adapting to changing market conditions

The Goal: Make you profitable by continuously improving strategies based on data.
"""

import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import sqlite3
import json

# Optional langchain imports - only needed if using the AI optimizer feature
# Compatible with both langchain 0.1.x and 1.0.x
try:
    from langchain_anthropic import ChatAnthropic
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    ChatAnthropic = None

from config_and_database import DB_PATH


class StrategyOptimizerAgent:
    """
    Claude-powered agent that analyzes trading strategies and suggests improvements

    This agent can:
    - Query backtest results from database
    - Identify winning vs losing patterns
    - Suggest parameter adjustments
    - Provide actionable recommendations
    - Learn from feedback over time
    """

    def __init__(self, anthropic_api_key: str = None):
        """Initialize the AI Strategy Optimizer"""

        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain-anthropic is required for AI Strategy Optimizer. "
                "Install with: pip install langchain-anthropic"
            )

        self.api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY or CLAUDE_API_KEY must be set")

        # Initialize Claude via LangChain (simplified - no deprecated agent framework)
        # Using Haiku 4.5: 67% cheaper, 2x faster, 73% as good as Sonnet for analysis
        self.llm = ChatAnthropic(
            model="claude-haiku-4-5-20251001",  # Latest Haiku 4.5 (Oct 2025)
            anthropic_api_key=self.api_key,
            temperature=0.1,  # Low temperature for consistent analysis
            max_tokens=4096
        )

    # ========================================================================
    # Helper Functions
    # ========================================================================

    def _query_backtest_results(self, query: str):
        """Query backtest results from database - returns dict/list"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if query.lower() == 'all':
                cursor.execute("""
                    SELECT
                        strategy_name,
                        total_trades,
                        win_rate,
                        expectancy_pct,
                        total_return_pct,
                        max_drawdown_pct,
                        sharpe_ratio,
                        avg_win_pct,
                        avg_loss_pct
                    FROM backtest_results
                    ORDER BY expectancy_pct DESC
                """)
            else:
                cursor.execute("""
                    SELECT
                        strategy_name,
                        total_trades,
                        win_rate,
                        expectancy_pct,
                        total_return_pct,
                        max_drawdown_pct,
                        sharpe_ratio,
                        avg_win_pct,
                        avg_loss_pct,
                        start_date,
                        end_date
                    FROM backtest_results
                    WHERE strategy_name LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT 5
                """, (f'%{query}%',))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'strategy': row['strategy_name'],
                    'trades': row['total_trades'],
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'expectancy': f"{row['expectancy_pct']:.2f}%",
                    'total_return': f"{row['total_return_pct']:.2f}%",
                    'max_drawdown': f"{row['max_drawdown_pct']:.2f}%",
                    'sharpe': f"{row['sharpe_ratio']:.2f}",
                    'avg_win': f"{row['avg_win_pct']:.2f}%",
                    'avg_loss': f"{row['avg_loss_pct']:.2f}%"
                })

            conn.close()

            if not results:
                return {"error": f"No backtest results found for '{query}'. Database might be empty. Run backtests first."}

            return results

        except Exception as e:
            return f"Error querying backtest results: {str(e)}"

    def _get_winning_trades(self, strategy_name: str) -> str:
        """Get winning trades for analysis"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get winning regime signals
            cursor.execute("""
                SELECT
                    timestamp,
                    primary_regime_type,
                    confidence_score,
                    trade_direction,
                    spy_price,
                    vix_current,
                    volatility_regime,
                    price_change_1d,
                    price_change_5d
                FROM regime_signals
                WHERE signal_correct = 1
                  AND primary_regime_type LIKE ?
                ORDER BY price_change_1d DESC
                LIMIT 20
            """, (f'%{strategy_name}%',))

            trades = []
            for row in cursor.fetchall():
                trades.append({
                    'timestamp': row['timestamp'],
                    'pattern': row['primary_regime_type'],
                    'confidence': row['confidence_score'],
                    'direction': row['trade_direction'],
                    'price': row['spy_price'],
                    'vix': row['vix_current'],
                    'vol_regime': row['volatility_regime'],
                    'gain_1d': f"{row['price_change_1d']:.2f}%" if row['price_change_1d'] else 'N/A',
                    'gain_5d': f"{row['price_change_5d']:.2f}%" if row['price_change_5d'] else 'N/A'
                })

            conn.close()

            if not trades:
                return f"No winning trades found for '{strategy_name}'"

            return json.dumps(trades, indent=2)

        except Exception as e:
            return f"Error getting winning trades: {str(e)}"

    def _get_losing_trades(self, strategy_name: str) -> str:
        """Get losing trades for analysis"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    timestamp,
                    primary_regime_type,
                    confidence_score,
                    trade_direction,
                    spy_price,
                    vix_current,
                    volatility_regime,
                    price_change_1d,
                    price_change_5d
                FROM regime_signals
                WHERE signal_correct = 0
                  AND primary_regime_type LIKE ?
                ORDER BY price_change_1d ASC
                LIMIT 20
            """, (f'%{strategy_name}%',))

            trades = []
            for row in cursor.fetchall():
                trades.append({
                    'timestamp': row['timestamp'],
                    'pattern': row['primary_regime_type'],
                    'confidence': row['confidence_score'],
                    'direction': row['trade_direction'],
                    'price': row['spy_price'],
                    'vix': row['vix_current'],
                    'vol_regime': row['volatility_regime'],
                    'loss_1d': f"{row['price_change_1d']:.2f}%" if row['price_change_1d'] else 'N/A',
                    'loss_5d': f"{row['price_change_5d']:.2f}%" if row['price_change_5d'] else 'N/A'
                })

            conn.close()

            if not trades:
                return f"No losing trades found for '{strategy_name}'"

            return json.dumps(trades, indent=2)

        except Exception as e:
            return f"Error getting losing trades: {str(e)}"

    def _analyze_pattern_performance(self, pattern: str) -> str:
        """Analyze performance by pattern type"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if pattern.lower() == 'all':
                cursor.execute("""
                    SELECT
                        primary_regime_type,
                        COUNT(*) as total_signals,
                        SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
                        AVG(CASE WHEN signal_correct = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(confidence_score) as avg_confidence
                    FROM regime_signals
                    WHERE signal_correct IS NOT NULL
                    GROUP BY primary_regime_type
                    ORDER BY win_rate DESC
                """)
            else:
                cursor.execute("""
                    SELECT
                        primary_regime_type,
                        COUNT(*) as total_signals,
                        SUM(CASE WHEN signal_correct = 1 THEN 1 ELSE 0 END) as wins,
                        AVG(CASE WHEN signal_correct = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(confidence_score) as avg_confidence
                    FROM regime_signals
                    WHERE signal_correct IS NOT NULL
                      AND primary_regime_type LIKE ?
                    GROUP BY primary_regime_type
                """, (f'%{pattern}%',))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'pattern': row['primary_regime_type'],
                    'total_signals': row['total_signals'],
                    'wins': row['wins'],
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'avg_confidence': f"{row['avg_confidence']:.1f}%"
                })

            conn.close()

            if not results:
                return f"No pattern data found for '{pattern}'"

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error analyzing patterns: {str(e)}"

    def _get_market_context(self, days: str) -> str:
        """Get recent market context"""
        try:
            days_int = int(days)
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(f"""
                SELECT
                    timestamp,
                    vix_current,
                    volatility_regime,
                    primary_regime_type
                FROM regime_signals
                WHERE timestamp > datetime('now', '-{days_int} days')
                ORDER BY timestamp DESC
                LIMIT 30
            """)

            context = []
            for row in cursor.fetchall():
                context.append({
                    'date': row['timestamp'],
                    'vix': row['vix_current'],
                    'vol_regime': row['volatility_regime'],
                    'market_regime': row['primary_regime_type']
                })

            conn.close()

            if not context:
                return f"No market context found for last {days} days"

            return json.dumps(context, indent=2)

        except Exception as e:
            return f"Error getting market context: {str(e)}"

    def _save_recommendation(self, recommendation_json: str) -> str:
        """Save optimization recommendation"""
        try:
            recommendation = json.loads(recommendation_json)

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Create recommendations table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    strategy_name TEXT,
                    recommendation TEXT,
                    reasoning TEXT,
                    expected_improvement REAL,
                    implemented INTEGER DEFAULT 0,
                    actual_improvement REAL,
                    status TEXT DEFAULT 'pending'
                )
            """)

            cursor.execute("""
                INSERT INTO ai_recommendations (
                    strategy_name, recommendation, reasoning, expected_improvement
                ) VALUES (?, ?, ?, ?)
            """, (
                recommendation.get('strategy'),
                recommendation.get('recommendation'),
                recommendation.get('reasoning'),
                recommendation.get('expected_improvement', 0.0)
            ))

            conn.commit()
            conn.close()

            return f"Recommendation saved successfully for {recommendation.get('strategy')}"

        except Exception as e:
            return f"Error saving recommendation: {str(e)}"

    # ========================================================================
    # Main Optimization Functions
    # ========================================================================

    def optimize_strategy(self, strategy_name: str) -> Dict:
        """
        Analyze a specific strategy and provide optimization recommendations

        Args:
            strategy_name: Name of strategy to optimize

        Returns:
            Dict with analysis and recommendations
        """

        # Get backtest data from database
        backtest_data = self._query_backtest_results(strategy_name)

        prompt = f"""You are an expert quantitative trading analyst. Analyze the '{strategy_name}' trading strategy and provide specific optimization recommendations.

BACKTEST RESULTS:
{json.dumps(backtest_data, indent=2)}

ANALYSIS PROCESS:
1. Analyze the performance metrics (win rate, expectancy, drawdown, Sharpe ratio)
2. Identify strengths and weaknesses
3. Provide 3-5 specific, actionable recommendations with expected improvements

FOCUS ON:
- Parameter adjustments (entry/exit rules, stops, position sizing)
- Filter improvements (reduce false signals)
- Risk management enhancements

BE SPECIFIC with numbers. For example:
"Change RSI oversold threshold from 30 to 25" (not "tighten RSI filter")
"Add VIX > 18 requirement for entries" (not "consider volatility")

END with a clear verdict: IMPLEMENT, TEST CAREFULLY, or KILL STRATEGY.
"""

        result = self.llm.invoke(prompt)

        return {
            "strategy": strategy_name,
            "analysis": result.content if hasattr(result, 'content') else str(result),
            "timestamp": datetime.now().isoformat()
        }

    def analyze_all_strategies(self) -> Dict:
        """
        Analyze all strategies and rank them by profitability

        Returns:
            Dict with rankings and recommendations
        """

        # Get all backtest results
        all_results = self._query_backtest_results("all")

        prompt = f"""You are an expert quantitative trading analyst. Analyze ALL trading strategies and provide a comprehensive report.

ALL BACKTEST RESULTS:
{json.dumps(all_results, indent=2)}

YOUR ANALYSIS SHOULD INCLUDE:
1. Rank strategies by expectancy (most profitable first)
2. Identify the top 3 strategies worth focusing on
3. Identify strategies that should be killed (expectancy < 0 or win rate < 50%)
4. Provide specific recommendations for the top 3 strategies

FORMAT YOUR REPORT WITH:
- Summary table of all strategies (sorted by expectancy)
- Top 3 strategies to focus on (with brief reasoning)
- Strategies to kill immediately
- Quick wins (low-hanging fruit improvements)
- Resource allocation recommendation (where to focus effort)

Be brutally honest. Most strategies probably don't work. Focus resources on the 2-3 that actually make money.
"""

        result = self.llm.invoke(prompt)

        return {
            "analysis": result.content if hasattr(result, 'content') else str(result),
            "timestamp": datetime.now().isoformat()
        }

    def get_trade_recommendation(self, current_market_data: Dict) -> Dict:
        """
        Get AI recommendation for current market conditions

        Args:
            current_market_data: Dict with current price, VIX, regime, etc.

        Returns:
            Dict with trade recommendation and reasoning
        """

        prompt = f"""Given current market conditions, should we take a trade?

Current Market Data:
{json.dumps(current_market_data, indent=2)}

Analyze:
1. Query recent pattern performance to see what's working now
2. Get market context for the last 30 days
3. Check if current conditions match any high-probability setups
4. Provide a clear recommendation: BUY, SELL, or WAIT

Your recommendation should include:
- Clear action (BUY/SELL/WAIT)
- Specific strategy to use (if trading)
- Entry price and position size
- Stop loss and target
- Confidence level (0-100%)
- Reasoning (why this setup is good/bad right now)

Be conservative. Only recommend trades with >70% historical win rate in similar conditions.
"""

        result = self.agent.invoke({"input": prompt})

        return {
            "recommendation": result['output'],
            "market_data": current_market_data,
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# Command-Line Interface
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='AI Strategy Optimizer powered by Claude')
    parser.add_argument('--strategy', help='Optimize specific strategy')
    parser.add_argument('--all', action='store_true', help='Analyze all strategies')
    parser.add_argument('--api-key', help='Anthropic API key (or set ANTHROPIC_API_KEY env var)')

    args = parser.parse_args()

    try:
        optimizer = StrategyOptimizerAgent(anthropic_api_key=args.api_key)

        if args.all:
            print("\n🤖 Analyzing all strategies with Claude AI...\n")
            result = optimizer.analyze_all_strategies()
            print("\n" + "="*80)
            print("AI ANALYSIS REPORT")
            print("="*80)
            print(result['analysis'])
            print("="*80 + "\n")

        elif args.strategy:
            print(f"\n🤖 Optimizing '{args.strategy}' with Claude AI...\n")
            result = optimizer.optimize_strategy(args.strategy)
            print("\n" + "="*80)
            print(f"OPTIMIZATION REPORT: {args.strategy}")
            print("="*80)
            print(result['analysis'])
            print("="*80 + "\n")

        else:
            print("Usage:")
            print("  python ai_strategy_optimizer.py --all")
            print("  python ai_strategy_optimizer.py --strategy GAMMA_SQUEEZE_CASCADE")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure:")
        print("1. ANTHROPIC_API_KEY is set in environment")
        print("2. Database has backtest data (run backtests first)")
        print("3. langchain and langchain-anthropic are installed:")
        print("   pip install langchain langchain-anthropic")
