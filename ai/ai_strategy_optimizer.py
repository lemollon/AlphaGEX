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
import json
import psycopg2.extras

# Optional langchain imports - only needed if using the AI optimizer feature
# Compatible with both langchain 0.1.x and 1.0.x
try:
    from langchain_anthropic import ChatAnthropic
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    ChatAnthropic = None

from database_adapter import get_connection


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
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
                    WHERE strategy_name LIKE %s
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
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
                  AND primary_regime_type LIKE %s
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
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
                  AND primary_regime_type LIKE %s
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
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
                      AND primary_regime_type LIKE %s
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
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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

            conn = get_connection()
            cursor = conn.cursor()

            # NOTE: Table 'ai_recommendations' defined in db/config_and_database.py (single source of truth)

            cursor.execute("""
                INSERT INTO ai_recommendations (
                    strategy_name, recommendation, reasoning, expected_improvement
                ) VALUES (%s, %s, %s, %s)
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
    # Enhanced Analysis Functions (Strike, DTE, Greeks, Regime Optimization)
    # ========================================================================

    def _analyze_strike_performance(self, strategy_name: str = None) -> str:
        """
        Analyze which strikes performed best

        Returns performance by:
        - Strike distance from spot (ATM, 1% OTM, 2% OTM, etc.)
        - Moneyness (ITM, ATM, OTM)
        - VIX regime
        - Win rate and avg P&L per strike type
        """
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if strategy_name:
                query = """
                    SELECT
                        strategy_name,
                        moneyness,
                        ROUND(strike_distance_pct::numeric, 1) as strike_distance,
                        vix_regime,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END) as wins,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct,
                        MAX(pnl_pct) as best_trade_pct,
                        MIN(pnl_pct) as worst_trade_pct,
                        AVG(delta) as avg_delta,
                        AVG(dte) as avg_dte
                    FROM strike_performance
                    WHERE strategy_name LIKE %s
                    GROUP BY strategy_name, moneyness, strike_distance, vix_regime
                    HAVING total_trades >= 3
                    ORDER BY win_rate DESC, avg_pnl_pct DESC
                    LIMIT 50
                """
                cursor.execute(query, (f'%{strategy_name}%',))
            else:
                query = """
                    SELECT
                        strategy_name,
                        moneyness,
                        ROUND(strike_distance_pct::numeric, 1) as strike_distance,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct
                    FROM strike_performance
                    GROUP BY strategy_name, moneyness, strike_distance
                    HAVING total_trades >= 5
                    ORDER BY strategy_name, win_rate DESC
                    LIMIT 100
                """
                cursor.execute(query)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'strategy': row['strategy_name'],
                    'moneyness': row['moneyness'],
                    'strike_distance_pct': row['strike_distance'],
                    'vix_regime': row.get('vix_regime', 'N/A'),
                    'total_trades': row['total_trades'],
                    'wins': row.get('wins', 0),
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'avg_pnl': f"{row['avg_pnl_pct']:.2f}%",
                    'best_trade': f"{row.get('best_trade_pct', 0):.2f}%",
                    'worst_trade': f"{row.get('worst_trade_pct', 0):.2f}%",
                    'avg_delta': f"{row.get('avg_delta', 0):.3f}",
                    'avg_dte': row.get('avg_dte', 'N/A')
                })

            conn.close()

            if not results:
                return f"No strike performance data found{' for ' + strategy_name if strategy_name else ''}. Log trades first."

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error analyzing strike performance: {str(e)}"

    def _analyze_dte_performance(self, strategy_name: str = None) -> str:
        """
        Analyze performance by Days To Expiration (DTE)

        Shows which DTE ranges work best:
        - 0-3 DTE (weekly expiration)
        - 4-7 DTE
        - 8-14 DTE
        - 15-30 DTE
        - 30+ DTE
        """
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if strategy_name:
                query = """
                    SELECT
                        strategy_name,
                        dte_bucket,
                        pattern_type,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct,
                        AVG(hold_time_hours) / 24.0 as avg_hold_days,
                        AVG(theta_at_entry) as avg_theta,
                        SUM(CASE WHEN held_to_expiration = 1 THEN 1 ELSE 0 END) as held_to_exp
                    FROM dte_performance
                    WHERE strategy_name LIKE %s
                    GROUP BY strategy_name, dte_bucket, pattern_type
                    HAVING total_trades >= 3
                    ORDER BY win_rate DESC, avg_pnl_pct DESC
                """
                cursor.execute(query, (f'%{strategy_name}%',))
            else:
                query = """
                    SELECT
                        strategy_name,
                        dte_bucket,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct,
                        AVG(hold_time_hours) / 24.0 as avg_hold_days
                    FROM dte_performance
                    GROUP BY strategy_name, dte_bucket
                    HAVING total_trades >= 5
                    ORDER BY strategy_name, win_rate DESC
                """
                cursor.execute(query)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'strategy': row['strategy_name'],
                    'dte_bucket': row['dte_bucket'],
                    'pattern': row.get('pattern_type', 'N/A'),
                    'total_trades': row['total_trades'],
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'avg_pnl': f"{row['avg_pnl_pct']:.2f}%",
                    'avg_hold_days': f"{row['avg_hold_days']:.1f}",
                    'avg_theta': f"{row.get('avg_theta', 0):.2f}",
                    'held_to_expiration': row.get('held_to_exp', 0)
                })

            conn.close()

            if not results:
                return f"No DTE performance data found{' for ' + strategy_name if strategy_name else ''}."

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error analyzing DTE performance: {str(e)}"

    def _optimize_spread_widths(self, strategy_name: str = None) -> str:
        """
        Optimize spread widths for multi-leg strategies

        Analyzes:
        - Iron condor wing widths
        - Butterfly spread configuration
        - Vertical spread width
        - Optimal strike spacing
        """
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if strategy_name:
                query = """
                    SELECT
                        strategy_name,
                        spread_type,
                        ROUND(call_spread_width_points, 0) as call_width,
                        ROUND(put_spread_width_points, 0) as put_width,
                        ROUND(AVG(short_call_distance_pct), 1) as avg_short_call_dist,
                        ROUND(AVG(short_put_distance_pct), 1) as avg_short_put_dist,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct,
                        AVG(entry_credit) as avg_credit,
                        AVG(pnl_dollars) as avg_profit_dollars
                    FROM spread_width_performance
                    WHERE strategy_name LIKE %s
                    GROUP BY strategy_name, spread_type, call_width, put_width
                    HAVING total_trades >= 3
                    ORDER BY win_rate DESC, avg_pnl_pct DESC
                """
                cursor.execute(query, (f'%{strategy_name}%',))
            else:
                query = """
                    SELECT
                        strategy_name,
                        spread_type,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct
                    FROM spread_width_performance
                    GROUP BY strategy_name, spread_type
                    HAVING total_trades >= 5
                    ORDER BY strategy_name, win_rate DESC
                """
                cursor.execute(query)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'strategy': row['strategy_name'],
                    'spread_type': row['spread_type'],
                    'call_width': row.get('call_width'),
                    'put_width': row.get('put_width'),
                    'short_call_distance': f"{row.get('avg_short_call_dist', 0):.1f}%",
                    'short_put_distance': f"{row.get('avg_short_put_dist', 0):.1f}%",
                    'total_trades': row['total_trades'],
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'avg_pnl': f"{row['avg_pnl_pct']:.2f}%",
                    'avg_credit': f"${row.get('avg_credit', 0):.2f}",
                    'avg_profit': f"${row.get('avg_profit_dollars', 0):.2f}"
                })

            conn.close()

            if not results:
                return f"No spread width data found{' for ' + strategy_name if strategy_name else ''}."

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error optimizing spread widths: {str(e)}"

    def _optimize_greeks(self, strategy_name: str = None) -> str:
        """
        Optimize Greeks (delta, gamma, theta, vega)

        Shows which Greek ranges perform best:
        - Delta targets (0.20-0.30 vs 0.40-0.50 vs 0.60-0.70)
        - Theta efficiency (profit per theta decay)
        - Gamma exposure
        - Vega exposure in different VIX environments
        """
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if strategy_name:
                query = """
                    SELECT
                        strategy_name,
                        delta_target,
                        theta_strategy,
                        position_type,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct,
                        AVG(delta_pnl_ratio) as avg_delta_efficiency,
                        AVG(theta_pnl_ratio) as avg_theta_efficiency,
                        AVG(entry_delta) as avg_delta,
                        AVG(entry_theta) as avg_theta
                    FROM greeks_performance
                    WHERE strategy_name LIKE %s
                    GROUP BY strategy_name, delta_target, theta_strategy, position_type
                    HAVING total_trades >= 3
                    ORDER BY win_rate DESC, avg_pnl_pct DESC
                """
                cursor.execute(query, (f'%{strategy_name}%',))
            else:
                query = """
                    SELECT
                        strategy_name,
                        delta_target,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct
                    FROM greeks_performance
                    GROUP BY strategy_name, delta_target
                    HAVING total_trades >= 5
                    ORDER BY strategy_name, win_rate DESC
                """
                cursor.execute(query)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'strategy': row['strategy_name'],
                    'delta_target': row['delta_target'],
                    'theta_strategy': row.get('theta_strategy', 'N/A'),
                    'position_type': row.get('position_type', 'N/A'),
                    'total_trades': row['total_trades'],
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'avg_pnl': f"{row['avg_pnl_pct']:.2f}%",
                    'delta_efficiency': f"{row.get('avg_delta_efficiency', 0):.3f}",
                    'theta_efficiency': f"{row.get('avg_theta_efficiency', 0):.3f}",
                    'avg_delta': f"{row.get('avg_delta', 0):.3f}",
                    'avg_theta': f"{row.get('avg_theta', 0):.3f}"
                })

            conn.close()

            if not results:
                return f"No Greeks performance data found{' for ' + strategy_name if strategy_name else ''}."

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error optimizing Greeks: {str(e)}"

    def _optimize_by_regime(self, strategy_name: str = None) -> str:
        """
        Regime-specific optimization

        Different strategies for different regimes:
        - VIX < 15 (Low Vol)
        - VIX 15-25 (Normal Vol)
        - VIX > 25 (High Vol)
        - Positive vs Negative Gamma
        - Different patterns by regime
        """
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if strategy_name:
                query = """
                    SELECT
                        strategy_name,
                        vix_regime,
                        gamma_regime,
                        pattern_type,
                        moneyness,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct,
                        MAX(pnl_pct) as best_trade,
                        MIN(pnl_pct) as worst_trade,
                        AVG(vix_current) as avg_vix
                    FROM strike_performance
                    WHERE strategy_name LIKE %s
                    GROUP BY strategy_name, vix_regime, gamma_regime, pattern_type, moneyness
                    HAVING total_trades >= 3
                    ORDER BY win_rate DESC, avg_pnl_pct DESC
                    LIMIT 50
                """
                cursor.execute(query, (f'%{strategy_name}%',))
            else:
                query = """
                    SELECT
                        strategy_name,
                        vix_regime,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct
                    FROM strike_performance
                    GROUP BY strategy_name, vix_regime
                    HAVING total_trades >= 5
                    ORDER BY strategy_name, win_rate DESC
                """
                cursor.execute(query)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'strategy': row['strategy_name'],
                    'vix_regime': row['vix_regime'],
                    'gamma_regime': row.get('gamma_regime', 'N/A'),
                    'pattern': row.get('pattern_type', 'N/A'),
                    'moneyness': row.get('moneyness', 'N/A'),
                    'total_trades': row['total_trades'],
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'avg_pnl': f"{row['avg_pnl_pct']:.2f}%",
                    'best_trade': f"{row.get('best_trade', 0):.2f}%",
                    'worst_trade': f"{row.get('worst_trade', 0):.2f}%",
                    'avg_vix': f"{row.get('avg_vix', 0):.1f}"
                })

            conn.close()

            if not results:
                return f"No regime-specific data found{' for ' + strategy_name if strategy_name else ''}."

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error analyzing regime optimization: {str(e)}"

    def _find_best_combinations(self, strategy_name: str = None) -> str:
        """
        Find winning combinations of conditions

        Examples:
        "VIX < 16 AND liberation setup AND 5 DTE AND 2% OTM call = 78% win rate"
        "VIX > 25 AND ATM straddle AND 7 DTE = 85% win rate"

        This is the MOST actionable analysis - shows exact conditions that win
        """
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Complex multi-condition query
            if strategy_name:
                query = """
                    SELECT
                        sp.strategy_name,
                        sp.vix_regime,
                        sp.pattern_type,
                        dp.dte_bucket,
                        sp.moneyness,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN sp.win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(sp.pnl_pct) as avg_pnl_pct,
                        AVG(sp.vix_current) as avg_vix,
                        AVG(sp.strike_distance_pct) as avg_strike_distance
                    FROM strike_performance sp
                    LEFT JOIN dte_performance dp ON sp.strategy_name = dp.strategy_name
                        AND sp.timestamp = dp.timestamp
                    WHERE sp.strategy_name LIKE %s
                    GROUP BY sp.strategy_name, sp.vix_regime, sp.pattern_type, dp.dte_bucket, sp.moneyness
                    HAVING total_trades >= 5 AND win_rate >= 60
                    ORDER BY win_rate DESC, total_trades DESC, avg_pnl_pct DESC
                    LIMIT 25
                """
                cursor.execute(query, (f'%{strategy_name}%',))
            else:
                query = """
                    SELECT
                        strategy_name,
                        vix_regime,
                        pattern_type,
                        moneyness,
                        COUNT(*) as total_trades,
                        AVG(CASE WHEN win = 1 THEN 1.0 ELSE 0.0 END) * 100 as win_rate,
                        AVG(pnl_pct) as avg_pnl_pct
                    FROM strike_performance
                    GROUP BY strategy_name, vix_regime, pattern_type, moneyness
                    HAVING total_trades >= 8 AND win_rate >= 65
                    ORDER BY win_rate DESC, total_trades DESC
                    LIMIT 30
                """
                cursor.execute(query)

            results = []
            for row in cursor.fetchall():
                # Build condition string
                conditions = []
                if row.get('vix_regime'):
                    conditions.append(f"VIX {row['vix_regime']}")
                if row.get('pattern_type'):
                    conditions.append(row['pattern_type'])
                if row.get('dte_bucket'):
                    conditions.append(f"{row['dte_bucket']} DTE")
                if row.get('moneyness'):
                    conditions.append(row['moneyness'])

                results.append({
                    'strategy': row['strategy_name'],
                    'conditions': ' + '.join(conditions),
                    'vix_regime': row.get('vix_regime', 'N/A'),
                    'pattern': row.get('pattern_type', 'N/A'),
                    'dte_bucket': row.get('dte_bucket', 'N/A'),
                    'moneyness': row.get('moneyness', 'N/A'),
                    'total_trades': row['total_trades'],
                    'win_rate': f"{row['win_rate']:.1f}%",
                    'avg_pnl': f"{row['avg_pnl_pct']:.2f}%",
                    'avg_vix': f"{row.get('avg_vix', 0):.1f}",
                    'avg_strike_distance': f"{row.get('avg_strike_distance', 0):.1f}%"
                })

            conn.close()

            if not results:
                return f"No high-probability combinations found{' for ' + strategy_name if strategy_name else ''}. Need more trade data."

            return json.dumps(results, indent=2)

        except Exception as e:
            return f"Error finding best combinations: {str(e)}"

    def get_optimal_strikes_for_current_market(self, current_market_data: Dict) -> Dict:
        """
        Get optimal strike recommendations for current market conditions

        Based on historical performance + current regime, recommend EXACT strikes

        Args:
            current_market_data: Dict with:
                - spot_price: Current SPY price
                - vix_current: Current VIX
                - net_gex: Current gamma exposure
                - pattern_type: Detected pattern (e.g., 'LIBERATION', 'GAMMA_SQUEEZE')
                - regime_analysis: Full psychology trap analysis

        Returns:
            Dict with exact strike recommendations, expected performance, reasoning
        """
        try:
            spot = current_market_data.get('spot_price')
            vix = current_market_data.get('vix_current')
            pattern = current_market_data.get('pattern_type', 'UNKNOWN')

            # Determine VIX regime
            if vix < 15:
                vix_regime = 'low'
            elif vix > 25:
                vix_regime = 'high'
            else:
                vix_regime = 'normal'

            # Query historical performance for this pattern + regime
            strike_data = self._analyze_strike_performance(pattern)
            dte_data = self._analyze_dte_performance(pattern)
            regime_data = self._optimize_by_regime(pattern)

            # Use AI to synthesize recommendations
            prompt = f"""Given current market conditions, recommend EXACT option strikes for entry.

CURRENT MARKET:
- SPY Price: ${spot:.2f}
- VIX: {vix:.1f} ({vix_regime} volatility regime)
- Pattern: {pattern}
- Net GEX: {current_market_data.get('net_gex', 0)/1e9:.2f}B

HISTORICAL PERFORMANCE FOR THIS PATTERN:
Strike Performance:
{strike_data}

DTE Performance:
{dte_data}

Regime-Specific Performance:
{regime_data}

Based on this data, provide EXACT strike recommendations in JSON format:

{{
  "recommended_strategy": "iron_condor" | "vertical_call" | "vertical_put" | "straddle" | "strangle",
  "strikes": {{
    "short_call": <exact strike>,
    "long_call": <exact strike>,
    "short_put": <exact strike>,
    "long_put": <exact strike>
  }},
  "distances": {{
    "short_call_pct": <% from spot>,
    "short_put_pct": <% from spot>
  }},
  "optimal_dte": <days to expiration>,
  "expiration_date": "<date>",
  "expected_credit": <dollars>,
  "expected_win_rate": <percentage>,
  "expected_profit_pct": <percentage>,
  "max_loss": <dollars>,
  "confidence": <0-100>,
  "reasoning": "<1-2 sentences why these strikes>"
}}

Be SPECIFIC. Use the historical data to choose strikes that have actually worked in this regime."""

            result = self.llm.invoke(prompt)
            response_text = result.content if hasattr(result, 'content') else str(result)

            # Try to parse JSON response
            try:
                # Extract JSON from markdown code blocks if present
                if '```json' in response_text:
                    json_start = response_text.find('```json') + 7
                    json_end = response_text.find('```', json_start)
                    response_text = response_text[json_start:json_end].strip()
                elif '```' in response_text:
                    json_start = response_text.find('```') + 3
                    json_end = response_text.find('```', json_start)
                    response_text = response_text[json_start:json_end].strip()

                recommendation = json.loads(response_text)
            except (json.JSONDecodeError, ValueError, Exception):
                # If JSON parsing fails, return raw text
                recommendation = {
                    "raw_response": response_text,
                    "error": "Could not parse JSON response"
                }

            return {
                "current_market": current_market_data,
                "optimal_strikes": recommendation,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "error": f"Error getting optimal strikes: {str(e)}",
                "current_market": current_market_data
            }

    # ========================================================================
    # Main Optimization Functions
    # ========================================================================

    def optimize_strategy(self, strategy_name: str) -> Dict:
        """
        Analyze a specific strategy and provide optimization recommendations

        NOW INCLUDES:
        - Strike-level analysis
        - DTE optimization
        - Greeks performance
        - Regime-specific recommendations
        - Spread width optimization
        - High-probability combination finder

        Args:
            strategy_name: Name of strategy to optimize

        Returns:
            Dict with comprehensive analysis and recommendations
        """

        # Get all performance data
        backtest_data = self._query_backtest_results(strategy_name)
        strike_data = self._analyze_strike_performance(strategy_name)
        dte_data = self._analyze_dte_performance(strategy_name)
        greeks_data = self._optimize_greeks(strategy_name)
        regime_data = self._optimize_by_regime(strategy_name)
        spread_data = self._optimize_spread_widths(strategy_name)
        combinations_data = self._find_best_combinations(strategy_name)

        prompt = f"""You are an expert quantitative trading analyst. Analyze the '{strategy_name}' trading strategy with COMPREHENSIVE strike-level detail.

========================================
OVERALL BACKTEST RESULTS:
========================================
{json.dumps(backtest_data, indent=2)}

========================================
STRIKE-LEVEL PERFORMANCE:
========================================
{strike_data}

========================================
DTE (DAYS TO EXPIRATION) OPTIMIZATION:
========================================
{dte_data}

========================================
GREEKS PERFORMANCE:
========================================
{greeks_data}

========================================
REGIME-SPECIFIC PERFORMANCE:
========================================
{regime_data}

========================================
SPREAD WIDTH OPTIMIZATION:
========================================
{spread_data}

========================================
BEST WINNING COMBINATIONS:
========================================
{combinations_data}

========================================
PROVIDE DETAILED RECOMMENDATIONS:
========================================

1. STRIKE SELECTION OPTIMIZATION:
   - Best performing moneyness (ITM/ATM/OTM)
   - Optimal strike distance from spot (e.g., "2% OTM calls")
   - Strike selection by VIX regime

2. DTE OPTIMIZATION:
   - Best DTE range (e.g., "5-7 DTE for this pattern")
   - Optimal hold time before expiration
   - When to hold to expiration vs exit early

3. GREEKS OPTIMIZATION:
   - Optimal delta range (e.g., "0.30-0.40 delta")
   - Theta strategy (positive vs negative theta)
   - Vega exposure recommendations

4. SPREAD CONFIGURATION (if applicable):
   - Optimal wing widths (e.g., "10-point iron condor")
   - Strike spacing
   - Credit targets

5. REGIME-SPECIFIC RULES:
   - VIX < 15: [specific rules]
   - VIX 15-25: [specific rules]
   - VIX > 25: [specific rules]

6. HIGH-PROBABILITY SETUPS:
   - List the top 3 winning combinations from the data
   - E.g., "VIX low + Liberation + 5 DTE + 2% OTM = 78% win rate"

BE EXTREMELY SPECIFIC with exact numbers. Examples:
- "Use 585 strike (2% OTM) when VIX < 16" (not "use OTM strikes")
- "Enter at 5 DTE, exit at 2 DTE" (not "short DTE works")
- "Target 0.35 delta" (not "medium delta")
- "10-point iron condor wings" (not "wider spreads")

END with clear verdict:
- IMPLEMENT: If win rate >65% and expectancy >1%
- TEST CAREFULLY: If win rate 55-65%
- KILL STRATEGY: If win rate <55% or negative expectancy
"""

        result = self.llm.invoke(prompt)

        return {
            "strategy": strategy_name,
            "analysis": result.content if hasattr(result, 'content') else str(result),
            "detailed_data": {
                "backtest": backtest_data,
                "strike_analysis": strike_data,
                "dte_analysis": dte_data,
                "greeks_analysis": greeks_data,
                "regime_analysis": regime_data,
                "spread_analysis": spread_data,
                "best_combinations": combinations_data
            },
            "timestamp": datetime.now().isoformat()
        }

    def analyze_all_strategies(self) -> Dict:
        """
        Analyze all strategies and rank them by profitability

        NOW INCLUDES regime-specific analysis across all strategies

        Returns:
            Dict with rankings and recommendations
        """

        # Get all backtest results and regime-specific data
        all_results = self._query_backtest_results("all")
        all_regime_data = self._optimize_by_regime()  # All strategies
        all_combinations = self._find_best_combinations()  # Best setups across all

        prompt = f"""You are an expert quantitative trading analyst. Analyze ALL trading strategies with regime-specific detail.

========================================
ALL BACKTEST RESULTS:
========================================
{json.dumps(all_results, indent=2)}

========================================
REGIME-SPECIFIC PERFORMANCE (ALL STRATEGIES):
========================================
{all_regime_data}

========================================
BEST WINNING COMBINATIONS (ALL STRATEGIES):
========================================
{all_combinations}

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

        result = self.llm.invoke(prompt)

        return {
            "recommendation": result.content if hasattr(result, 'content') else str(result),
            "market_data": current_market_data,
            "timestamp": datetime.now().isoformat()
        }

    def optimize_with_dynamic_stats(self, strategy_name: str = None) -> Dict:
        """
        Optimize strategies using dynamic stats system integration

        Integrates with strategy_stats.py to get live win rates and backtest data.
        Provides recommendations that can auto-update the dynamic stats.

        Args:
            strategy_name: Specific strategy to optimize, or None for all

        Returns:
            Dict with optimization results and auto-update status
        """
        try:
            from strategy_stats import get_strategy_stats, get_recent_changes

            # Get live strategy stats
            live_stats = get_strategy_stats()

            if strategy_name:
                # Optimize specific strategy
                if strategy_name not in live_stats:
                    return {
                        "error": f"Strategy '{strategy_name}' not found in dynamic stats",
                        "available_strategies": list(live_stats.keys())
                    }

                stat = live_stats[strategy_name]

                prompt = f"""Analyze the '{strategy_name}' trading strategy with REAL backtest data.

LIVE PERFORMANCE DATA (Auto-updated from backtests):
- Win Rate: {stat['win_rate']*100:.1f}%
- Average Win: {stat.get('avg_win', 0):.2f}%
- Average Loss: {stat.get('avg_loss', 0):.2f}%
- Expectancy: {stat.get('expectancy', 0):.2f}%
- Total Trades: {stat.get('total_trades', 0)}
- Last Updated: {stat.get('last_updated', 'Never')}
- Data Source: {stat.get('source', 'unknown')}

Provide 3-5 SPECIFIC optimizations that could improve this strategy:
1. Parameter adjustments (with exact numbers)
2. Filter improvements (reduce false signals)
3. Risk management enhancements

Rate each suggestion's expected impact (Low/Medium/High) and difficulty (Easy/Medium/Hard).

Format as JSON:
{{
  "current_performance": "summary",
  "recommendations": [
    {{"suggestion": "...", "impact": "High", "difficulty": "Easy", "reasoning": "..."}}
  ],
  "verdict": "IMPLEMENT/TEST/KILL"
}}
"""

                result = self.llm.invoke(prompt)
                analysis = result.content if hasattr(result, 'content') else str(result)

                return {
                    "strategy": strategy_name,
                    "live_stats": stat,
                    "analysis": analysis,
                    "recent_changes": get_recent_changes(limit=5),
                    "timestamp": datetime.now().isoformat()
                }

            else:
                # Analyze all strategies
                strategies_summary = []
                for name, stat in live_stats.items():
                    strategies_summary.append({
                        "name": name,
                        "win_rate": f"{stat['win_rate']*100:.1f}%",
                        "expectancy": f"{stat.get('expectancy', 0):.2f}%",
                        "trades": stat.get('total_trades', 0),
                        "source": stat.get('source', 'unknown')
                    })

                prompt = f"""Analyze ALL trading strategies with LIVE auto-updated data.

LIVE STRATEGY PERFORMANCE:
{json.dumps(strategies_summary, indent=2)}

Provide:
1. Rank strategies by expectancy (best first)
2. Top 3 strategies to focus on
3. Strategies to kill (negative expectancy or <50% win rate)
4. Quick wins (easy improvements with high impact)
5. Resource allocation recommendation

Be brutally honest. Focus on what actually makes money.
"""

                result = self.llm.invoke(prompt)
                analysis = result.content if hasattr(result, 'content') else str(result)

                return {
                    "all_strategies": strategies_summary,
                    "analysis": analysis,
                    "recent_auto_updates": get_recent_changes(limit=10),
                    "timestamp": datetime.now().isoformat()
                }

        except ImportError:
            return {
                "error": "strategy_stats.py not available",
                "fallback": "Using database backtest results instead",
                "recommendation": "Use optimize_strategy() or analyze_all_strategies() methods"
            }
        except Exception as e:
            return {
                "error": f"Error in dynamic stats optimization: {str(e)}"
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
