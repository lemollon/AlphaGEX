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
from typing import Dict, List, Optional
from datetime import datetime
import sqlite3
import json

# Optional langchain imports - only needed if using the AI optimizer feature
try:
    from langchain.agents import Tool, AgentExecutor, create_openai_functions_agent
    from langchain_anthropic import ChatAnthropic
    from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain.memory import ConversationBufferMemory
    from langchain.schema import HumanMessage, AIMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("⚠️ langchain not installed - AI Strategy Optimizer will not be available")
    print("   Install with: pip install langchain langchain-anthropic")

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
                "langchain is required for AI Strategy Optimizer. "
                "Install with: pip install langchain langchain-anthropic"
            )

        self.api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY or CLAUDE_API_KEY must be set")

        # Initialize Claude via LangChain
        self.llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            anthropic_api_key=self.api_key,
            temperature=0.1,  # Low temperature for consistent analysis
            max_tokens=4096
        )

        # Create tools for the agent
        self.tools = self._create_tools()

        # Create agent
        self.agent = self._create_agent()

        # Memory for learning
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

    def _create_tools(self) -> List[Tool]:
        """Create tools the agent can use"""

        return [
            Tool(
                name="query_backtest_results",
                func=self._query_backtest_results,
                description="""
                Query backtest results from database.
                Input should be a strategy name or 'all' to get all strategies.
                Returns: Strategy performance metrics including win rate, expectancy, drawdown.
                Use this to analyze which strategies are profitable.
                """
            ),
            Tool(
                name="get_winning_trades",
                func=self._get_winning_trades,
                description="""
                Get details of winning trades for a strategy.
                Input: strategy name
                Returns: List of profitable trades with entry/exit conditions
                Use this to identify what makes trades successful.
                """
            ),
            Tool(
                name="get_losing_trades",
                func=self._get_losing_trades,
                description="""
                Get details of losing trades for a strategy.
                Input: strategy name
                Returns: List of unprofitable trades with entry/exit conditions
                Use this to identify what causes losses.
                """
            ),
            Tool(
                name="analyze_pattern_performance",
                func=self._analyze_pattern_performance,
                description="""
                Analyze performance by pattern type (psychology traps, GEX signals, etc).
                Input: 'all' or specific pattern name
                Returns: Win rates and expectancy by pattern
                Use this to see which patterns work best.
                """
            ),
            Tool(
                name="get_market_context",
                func=self._get_market_context,
                description="""
                Get recent market conditions and regime data.
                Input: number of days to look back (e.g., '30')
                Returns: VIX levels, volatility regimes, market trends
                Use this to understand current market environment.
                """
            ),
            Tool(
                name="save_recommendation",
                func=self._save_recommendation,
                description="""
                Save an optimization recommendation to track over time.
                Input: JSON string with {strategy, recommendation, reasoning, expected_improvement}
                Returns: Confirmation that recommendation was saved
                Use this to record your suggestions for future evaluation.
                """
            )
        ]

    def _create_agent(self) -> AgentExecutor:
        """Create the LangChain agent"""

        system_prompt = """You are an expert quantitative trading analyst specializing in options and derivatives strategies.

Your role is to analyze trading strategy performance and provide ACTIONABLE recommendations to improve profitability.

Core Principles:
1. DATA-DRIVEN: Base all recommendations on actual backtest results, not theory
2. HONEST: If a strategy is losing money, say so clearly
3. SPECIFIC: Provide exact parameter changes (e.g., "Change RSI threshold from 70 to 75")
4. PROFITABLE: Focus ONLY on changes that increase expectancy and win rate
5. RISK-AWARE: Consider max drawdown and Sharpe ratio, not just returns

Your Analysis Process:
1. Query backtest results to see overall performance
2. Compare winning vs losing trades to find patterns
3. Identify what differentiates profitable trades
4. Suggest specific parameter improvements
5. Estimate expected improvement quantitatively

Red Flags to Watch For:
- Win rate < 55% → Strategy needs major improvement or should be killed
- Expectancy < 0.5% → Barely profitable, costs will kill it
- Max drawdown > 20% → Too risky
- Sharpe ratio < 1.0 → Poor risk-adjusted returns
- Sample size < 50 trades → Not enough data, could be luck

When Analyzing:
- Look for common patterns in winning trades (VIX levels, time of day, market regime)
- Identify what causes losses (false signals, poor entries, late exits)
- Suggest tighter filters to reduce false positives
- Recommend better entry/exit rules based on what worked

Always provide:
1. Current performance summary
2. Key issues identified
3. Specific recommendations (with parameters)
4. Expected improvement (quantitative estimate)
5. Implementation priority (critical, high, medium, low)

Be BRUTALLY honest. If a strategy sucks, say it should be killed. Focus on the 2-3 best strategies, not trying to fix everything.
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            max_iterations=10,
            handle_parsing_errors=True
        )

    # ========================================================================
    # Tool Implementation Functions
    # ========================================================================

    def _query_backtest_results(self, query: str) -> str:
        """Query backtest results from database"""
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
                return f"No backtest results found for '{query}'. Database might be empty. Run backtests first."

            return json.dumps(results, indent=2)

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

        prompt = f"""Analyze the '{strategy_name}' trading strategy and provide specific optimization recommendations.

Follow this analysis process:
1. Query the backtest results for this strategy
2. Get winning trades to see what works
3. Get losing trades to see what fails
4. Identify patterns in wins vs losses
5. Provide 3-5 specific, actionable recommendations with expected improvements

Focus on:
- Parameter adjustments (entry/exit rules, stops, position sizing)
- Filter improvements (reduce false signals)
- Risk management enhancements

Be specific with numbers. For example:
"Change RSI oversold threshold from 30 to 25" (not "tighten RSI filter")
"Add VIX > 18 requirement for entries" (not "consider volatility")

End with a clear verdict: IMPLEMENT, TEST CAREFULLY, or KILL STRATEGY.
"""

        result = self.agent.invoke({"input": prompt})

        return {
            "strategy": strategy_name,
            "analysis": result['output'],
            "timestamp": datetime.now().isoformat()
        }

    def analyze_all_strategies(self) -> Dict:
        """
        Analyze all strategies and rank them by profitability

        Returns:
            Dict with rankings and recommendations
        """

        prompt = """Analyze ALL trading strategies in the database and provide a comprehensive report.

1. Query all backtest results
2. Rank strategies by expectancy (most profitable first)
3. Identify the top 3 strategies worth focusing on
4. Identify strategies that should be killed (expectancy < 0 or win rate < 50%)
5. Provide specific recommendations for the top 3 strategies

Your report should include:
- Summary table of all strategies (sorted by expectancy)
- Top 3 strategies to focus on (with brief reasoning)
- Strategies to kill immediately
- Quick wins (low-hanging fruit improvements)
- Resource allocation recommendation (where to focus effort)

Be brutally honest. Most strategies probably don't work. Focus resources on the 2-3 that actually make money.
"""

        result = self.agent.invoke({"input": prompt})

        return {
            "analysis": result['output'],
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
