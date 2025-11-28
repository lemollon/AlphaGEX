"""
trade_journal_agent.py - AI Agent for Trade Performance Analysis

This agent analyzes your trading history to identify patterns, calculate performance metrics,
and generate personalized recommendations for improving profitability.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from database_adapter import get_connection


class TradeJournalAgent:
    """AI agent that analyzes trading patterns and generates insights"""

    def __init__(self):
        pass

    def get_closed_trades(self, days_back: int = 30) -> pd.DataFrame:
        """Get all closed trades from the database (PostgreSQL)"""
        conn = get_connection()

        # PostgreSQL uses INTERVAL for date math
        query = """
            SELECT
                symbol,
                strategy,
                entry_price,
                exit_price,
                quantity,
                pnl,
                opened_at,
                closed_at,
                status,
                notes
            FROM positions
            WHERE status = 'CLOSED'
            AND closed_at >= NOW() - INTERVAL '%s days'
            ORDER BY closed_at DESC
        """

        df = pd.read_sql_query(query % days_back, conn.raw_connection)
        conn.close()

        if not df.empty:
            df['opened_at'] = pd.to_datetime(df['opened_at'])
            df['closed_at'] = pd.to_datetime(df['closed_at'])
            df['hold_time'] = (df['closed_at'] - df['opened_at']).dt.total_seconds() / 3600  # hours
            df['winner'] = df['pnl'] > 0

        return df

    def calculate_performance_metrics(self, df: pd.DataFrame) -> Dict:
        """Calculate comprehensive performance metrics"""

        if df.empty:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'total_pnl': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'avg_hold_time': 0,
                'expectancy': 0
            }

        winners = df[df['pnl'] > 0]
        losers = df[df['pnl'] <= 0]

        total_wins = winners['pnl'].sum() if not winners.empty else 0
        total_losses = abs(losers['pnl'].sum()) if not losers.empty else 0

        metrics = {
            'total_trades': len(df),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': (len(winners) / len(df) * 100) if len(df) > 0 else 0,
            'avg_win': winners['pnl'].mean() if not winners.empty else 0,
            'avg_loss': losers['pnl'].mean() if not losers.empty else 0,
            'profit_factor': (total_wins / total_losses) if total_losses > 0 else float('inf'),
            'total_pnl': df['pnl'].sum(),
            'best_trade': df['pnl'].max(),
            'worst_trade': df['pnl'].min(),
            'avg_hold_time': df['hold_time'].mean() if 'hold_time' in df.columns else 0,
            'expectancy': df['pnl'].mean()  # Average profit per trade
        }

        return metrics

    def analyze_by_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Analyze performance by strategy type"""

        if df.empty:
            return pd.DataFrame()

        strategy_analysis = df.groupby('strategy').agg({
            'pnl': ['count', 'sum', 'mean'],
            'winner': 'sum'
        }).round(2)

        strategy_analysis.columns = ['total_trades', 'total_pnl', 'avg_pnl', 'wins']
        strategy_analysis['win_rate'] = (strategy_analysis['wins'] / strategy_analysis['total_trades'] * 100).round(1)
        strategy_analysis = strategy_analysis.sort_values('total_pnl', ascending=False)

        return strategy_analysis

    def analyze_by_symbol(self, df: pd.DataFrame) -> pd.DataFrame:
        """Analyze performance by symbol"""

        if df.empty:
            return pd.DataFrame()

        symbol_analysis = df.groupby('symbol').agg({
            'pnl': ['count', 'sum', 'mean'],
            'winner': 'sum'
        }).round(2)

        symbol_analysis.columns = ['total_trades', 'total_pnl', 'avg_pnl', 'wins']
        symbol_analysis['win_rate'] = (symbol_analysis['wins'] / symbol_analysis['total_trades'] * 100).round(1)
        symbol_analysis = symbol_analysis.sort_values('total_pnl', ascending=False)

        return symbol_analysis

    def detect_patterns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Detect trading patterns and generate insights"""

        patterns = []

        if df.empty:
            return {'insights': ['No trading data available yet. Start trading to build your journal!']}

        # Pattern 1: Strategy performance
        strategy_perf = self.analyze_by_strategy(df)
        if not strategy_perf.empty:
            best_strategy = strategy_perf.index[0]
            best_wr = strategy_perf.loc[best_strategy, 'win_rate']
            best_pnl = strategy_perf.loc[best_strategy, 'total_pnl']

            if best_wr >= 70:
                patterns.append(f"🎯 **Best Strategy**: {best_strategy} - {best_wr:.0f}% win rate, ${best_pnl:,.2f} total P&L. This is your edge!")

            if len(strategy_perf) > 1:
                worst_strategy = strategy_perf.index[-1]
                worst_wr = strategy_perf.loc[worst_strategy, 'win_rate']

                if worst_wr < 45:
                    patterns.append(f"⚠️ **Struggling Strategy**: {worst_strategy} - {worst_wr:.0f}% win rate. Consider avoiding this setup or refining entry rules.")

        # Pattern 2: Win/Loss management
        winners = df[df['pnl'] > 0]
        losers = df[df['pnl'] <= 0]

        if not winners.empty and not losers.empty:
            avg_win = winners['pnl'].mean()
            avg_loss = abs(losers['pnl'].mean())
            win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

            if win_loss_ratio < 1.5:
                patterns.append(f"📉 **Risk/Reward Issue**: Avg win ${avg_win:.2f} vs avg loss ${avg_loss:.2f} (ratio: {win_loss_ratio:.2f}). Let winners run longer!")
            elif win_loss_ratio > 2.5:
                patterns.append(f"✅ **Excellent R:R**: Avg win ${avg_win:.2f} vs avg loss ${avg_loss:.2f} (ratio: {win_loss_ratio:.2f}). Keep doing this!")

        # Pattern 3: Hold time analysis
        if 'hold_time' in df.columns:
            winner_hold_time = winners['hold_time'].mean() if not winners.empty else 0
            loser_hold_time = losers['hold_time'].mean() if not losers.empty else 0

            if loser_hold_time > winner_hold_time * 1.5:
                patterns.append(f"⏰ **Timing Issue**: You hold losers {loser_hold_time:.1f}h but winners only {winner_hold_time:.1f}h. Cut losers faster!")

        # Pattern 4: Symbol performance
        symbol_perf = self.analyze_by_symbol(df)
        if not symbol_perf.empty and len(symbol_perf) >= 2:
            best_symbol = symbol_perf.index[0]
            best_sym_wr = symbol_perf.loc[best_symbol, 'win_rate']

            if best_sym_wr >= 70:
                patterns.append(f"📊 **Best Symbol**: {best_symbol} - {best_sym_wr:.0f}% win rate. Consider focusing more on this ticker.")

        # Pattern 5: Recent trend
        if len(df) >= 10:
            recent_10 = df.head(10)
            recent_wr = (recent_10['winner'].sum() / len(recent_10) * 100)
            overall_wr = (df['winner'].sum() / len(df) * 100)

            if recent_wr > overall_wr + 15:
                patterns.append(f"🔥 **Hot Streak**: Recent 10 trades: {recent_wr:.0f}% win rate vs overall {overall_wr:.0f}%. You're improving!")
            elif recent_wr < overall_wr - 15:
                patterns.append(f"🧊 **Cold Streak**: Recent 10 trades: {recent_wr:.0f}% win rate vs overall {overall_wr:.0f}%. Take a break or review your process.")

        if not patterns:
            patterns.append("📈 Keep trading to build more data. Patterns will emerge over time!")

        return {'insights': patterns}

    def generate_recommendations(self, df: pd.DataFrame, metrics: Dict) -> List[str]:
        """Generate personalized trading recommendations"""

        recommendations = []

        if df.empty:
            return ["Start trading to receive personalized recommendations!"]

        # Recommendation 1: Win rate
        if metrics['win_rate'] < 50:
            recommendations.append("🎯 **Focus on Quality**: Win rate below 50%. Be more selective with entries. Wait for higher-confidence setups (70%+ confidence).")
        elif metrics['win_rate'] > 70:
            recommendations.append("✅ **Excellent Win Rate**: 70%+ win rate. Consider increasing position size on high-confidence setups.")

        # Recommendation 2: Profit factor
        if metrics['profit_factor'] < 1.5:
            recommendations.append("💰 **Improve R:R**: Profit factor below 1.5. Set wider profit targets or tighter stops to improve risk/reward.")
        elif metrics['profit_factor'] > 2.0:
            recommendations.append("🚀 **Strong Edge**: Profit factor above 2.0. Your strategy has a solid edge. Stay consistent!")

        # Recommendation 3: Trade frequency
        if metrics['total_trades'] < 5:
            recommendations.append("📊 **Build Sample Size**: Only a few trades. Keep trading to gather more data for statistical significance.")

        # Recommendation 4: Strategy focus
        strategy_perf = self.analyze_by_strategy(df)
        if not strategy_perf.empty:
            best_strategies = strategy_perf[strategy_perf['win_rate'] >= 65]
            if len(best_strategies) > 0:
                strat_list = ", ".join(best_strategies.index.tolist())
                recommendations.append(f"🎯 **Winning Strategies**: Focus on {strat_list}. These have 65%+ win rates for you.")

        # Recommendation 5: Expectancy
        if metrics['expectancy'] > 50:
            recommendations.append(f"💵 **Positive Expectancy**: ${metrics['expectancy']:.2f} per trade. Keep executing your edge!")
        elif metrics['expectancy'] < 0:
            recommendations.append(f"⚠️ **Negative Expectancy**: ${metrics['expectancy']:.2f} per trade. Review your process - something needs adjustment.")

        return recommendations


def display_trade_journal(agent: TradeJournalAgent, days_back: int = 30):
    """Display comprehensive trade journal analysis"""

    st.header("📔 Trade Journal - AI Performance Analysis")

    # Time period selector
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**Analyzing last {days_back} days of trading**")
    with col2:
        if st.button("🔄 Refresh Analysis"):
            st.rerun()

    # Get data
    trades = agent.get_closed_trades(days_back)

    if trades.empty:
        st.info("""
        📊 **No trading history yet**

        Your trade journal will populate as you close positions. Start trading to see:
        - Win rate by strategy
        - Performance patterns
        - Personalized recommendations
        - Visual performance charts
        """)
        return

    # Calculate metrics
    metrics = agent.calculate_performance_metrics(trades)

    # Section 1: Performance Overview
    st.subheader("📊 Performance Overview")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Total Trades",
            metrics['total_trades'],
            help="Number of closed positions"
        )

    with col2:
        win_rate_color = "normal" if metrics['win_rate'] >= 50 else "inverse"
        st.metric(
            "Win Rate",
            f"{metrics['win_rate']:.1f}%",
            delta=f"{metrics['winners']}W / {metrics['losers']}L",
            delta_color=win_rate_color
        )

    with col3:
        st.metric(
            "Total P&L",
            f"${metrics['total_pnl']:,.2f}",
            delta=f"${metrics['expectancy']:.2f}/trade",
            delta_color="normal" if metrics['total_pnl'] > 0 else "inverse"
        )

    with col4:
        pf_display = f"{metrics['profit_factor']:.2f}" if metrics['profit_factor'] != float('inf') else "∞"
        st.metric(
            "Profit Factor",
            pf_display,
            help="Total wins / Total losses (>1.5 is good)"
        )

    with col5:
        st.metric(
            "Avg Hold Time",
            f"{metrics['avg_hold_time']:.1f}h",
            help="Average time in position"
        )

    st.divider()

    # Section 2: Win/Loss Analysis
    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Average Win",
            f"${metrics['avg_win']:.2f}",
            delta=f"Best: ${metrics['best_trade']:.2f}",
            delta_color="normal"
        )

    with col2:
        st.metric(
            "Average Loss",
            f"${metrics['avg_loss']:.2f}",
            delta=f"Worst: ${metrics['worst_trade']:.2f}",
            delta_color="inverse"
        )

    # Section 3: Strategy Performance
    st.divider()
    st.subheader("🎯 Performance by Strategy")

    strategy_perf = agent.analyze_by_strategy(trades)
    if not strategy_perf.empty:
        # Color code strategies
        def highlight_strategy(row):
            if row['win_rate'] >= 70:
                return ['background-color: rgba(0, 255, 0, 0.2)'] * len(row)
            elif row['win_rate'] >= 50:
                return ['background-color: rgba(255, 255, 0, 0.1)'] * len(row)
            else:
                return ['background-color: rgba(255, 0, 0, 0.1)'] * len(row)

        st.dataframe(
            strategy_perf.style.apply(highlight_strategy, axis=1),
            use_container_width=True
        )
    else:
        st.info("Trade more to see strategy breakdown")

    # Section 4: Symbol Performance
    st.divider()
    st.subheader("📈 Performance by Symbol")

    symbol_perf = agent.analyze_by_symbol(trades)
    if not symbol_perf.empty:
        st.dataframe(symbol_perf, use_container_width=True)
    else:
        st.info("Trade more symbols to see breakdown")

    # Section 5: AI Insights
    st.divider()
    st.subheader("🤖 AI-Generated Insights")

    patterns = agent.detect_patterns(trades)
    for insight in patterns['insights']:
        st.markdown(insight)

    # Section 6: Recommendations
    st.divider()
    st.subheader("💡 Personalized Recommendations")

    recommendations = agent.generate_recommendations(trades, metrics)
    for i, rec in enumerate(recommendations, 1):
        st.markdown(f"{i}. {rec}")

    # Section 7: Performance Chart
    st.divider()
    st.subheader("📊 Cumulative P&L")

    create_performance_chart(trades)

    # Section 8: Recent Trades
    st.divider()
    st.subheader("📋 Recent Trades")

    recent_trades = trades.head(10)[['symbol', 'strategy', 'pnl', 'closed_at', 'hold_time']]
    recent_trades['pnl'] = recent_trades['pnl'].apply(lambda x: f"${x:.2f}")
    recent_trades['hold_time'] = recent_trades['hold_time'].apply(lambda x: f"{x:.1f}h")
    recent_trades['closed_at'] = recent_trades['closed_at'].dt.strftime('%Y-%m-%d %H:%M')

    st.dataframe(recent_trades, use_container_width=True, hide_index=True)


def create_performance_chart(trades: pd.DataFrame):
    """Create cumulative P&L chart"""

    if trades.empty:
        return

    # Sort by closed date
    trades_sorted = trades.sort_values('closed_at')
    trades_sorted['cumulative_pnl'] = trades_sorted['pnl'].cumsum()

    fig = go.Figure()

    # Cumulative P&L line
    fig.add_trace(go.Scatter(
        x=trades_sorted['closed_at'],
        y=trades_sorted['cumulative_pnl'],
        mode='lines+markers',
        name='Cumulative P&L',
        line=dict(color='#00D4FF', width=2),
        marker=dict(size=6),
        fill='tozeroy',
        fillcolor='rgba(0, 212, 255, 0.1)'
    ))

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title="Cumulative P&L Over Time",
        xaxis_title="Date",
        yaxis_title="P&L ($)",
        template="plotly_dark",
        hovermode='x unified',
        height=400
    )

    st.plotly_chart(fig, use_container_width=True, key="trade_journal_performance_chart")


def display_journal_settings():
    """Display journal settings and controls"""

    st.sidebar.divider()
    st.sidebar.subheader("📔 Journal Settings")

    # Time period selector
    period = st.sidebar.selectbox(
        "Analysis Period",
        options=[7, 14, 30, 60, 90, 180],
        index=2,
        format_func=lambda x: f"Last {x} days"
    )

    return period
