"""
Autonomous Trader Dashboard
Monitor the fully automated paper trader - NO manual intervention needed
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from autonomous_paper_trader import AutonomousPaperTrader


def display_autonomous_trader():
    """Display autonomous trader dashboard"""

    st.markdown("""
    <div style='text-align: center; margin-bottom: 30px;'>
        <h1 style='font-size: 48px; font-weight: 900; margin-bottom: 10px;
                   background: linear-gradient(135deg, #00D4FF 0%, #0099ff 50%, #00ffaa 100%);
                   -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                   text-shadow: 0 0 40px rgba(0, 212, 255, 0.3);'>
            🤖 Autonomous SPY Paper Trader
        </h1>
        <p style='color: #8b92a7; font-size: 14px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase;'>
            AI-Powered Fully Automated Trading System
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style='background: linear-gradient(135deg, rgba(0, 212, 255, 0.12) 0%, rgba(0, 153, 204, 0.08) 100%);
                padding: 28px; border-radius: 16px;
                border: 2px solid rgba(0, 212, 255, 0.3);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                margin-bottom: 30px;'>
        <div style='text-align: center; margin-bottom: 20px;'>
            <span style='font-size: 16px; font-weight: 900; color: #00D4FF; text-transform: uppercase; letter-spacing: 1px;'>
                🤖 AI-POWERED AUTONOMOUS TRADER
            </span>
            <div style='color: #d4d8e1; font-size: 14px; margin-top: 5px;'>
                Thinks like a real options trader!
            </div>
        </div>
        <div style='display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-top: 20px;'>
            <div style='background: rgba(0, 0, 0, 0.3); padding: 15px; border-radius: 10px; border: 1px solid rgba(0, 212, 255, 0.2);'>
                <div style='color: #00FF88; font-size: 13px; font-weight: 800; margin-bottom: 8px;'>✅ STARTING CAPITAL</div>
                <div style='color: white; font-size: 18px; font-weight: 900;'>$5,000</div>
            </div>
            <div style='background: rgba(0, 0, 0, 0.3); padding: 15px; border-radius: 10px; border: 1px solid rgba(0, 212, 255, 0.2);'>
                <div style='color: #00FF88; font-size: 13px; font-weight: 800; margin-bottom: 8px;'>✅ GUARANTEED DAILY TRADE</div>
                <div style='color: white; font-size: 14px; font-weight: 700;'>Always has a position working</div>
            </div>
            <div style='background: rgba(0, 0, 0, 0.3); padding: 15px; border-radius: 10px; border: 1px solid rgba(0, 212, 255, 0.2);'>
                <div style='color: #00FF88; font-size: 13px; font-weight: 800; margin-bottom: 8px;'>✅ AI-POWERED EXITS</div>
                <div style='color: white; font-size: 14px; font-weight: 700;'>Claude AI makes intelligent close decisions</div>
            </div>
            <div style='background: rgba(0, 0, 0, 0.3); padding: 15px; border-radius: 10px; border: 1px solid rgba(0, 212, 255, 0.2);'>
                <div style='color: #00FF88; font-size: 13px; font-weight: 800; margin-bottom: 8px;'>✅ REAL OPTION PRICES</div>
                <div style='color: white; font-size: 14px; font-weight: 700;'>From Yahoo Finance</div>
            </div>
        </div>
        <div style='margin-top: 20px; padding: 15px; background: rgba(0, 255, 136, 0.1); border-radius: 10px; border: 1px solid rgba(0, 255, 136, 0.3);'>
            <div style='color: #00FF88; font-size: 13px; font-weight: 800; margin-bottom: 8px;'>🎯 DUAL STRATEGY SYSTEM:</div>
            <div style='color: #d4d8e1; font-size: 13px; line-height: 1.6;'>
                <strong>Primary:</strong> Directional trades (calls/puts) based on GEX<br>
                <strong>Fallback:</strong> Iron Condors for premium collection
            </div>
        </div>
        <div style='margin-top: 15px; text-align: center;'>
            <div style='color: #FFB800; font-size: 12px; font-weight: 800; text-transform: uppercase;'>
                🚀 Auto Iron Condor when no clear GEX setup | AI analyzes positions to decide HOLD or CLOSE
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Initialize trader
    if 'autonomous_trader' not in st.session_state:
        st.session_state.autonomous_trader = AutonomousPaperTrader()

    trader = st.session_state.autonomous_trader

    # Initialize scheduler with auto-restart capability
    try:
        from trader_scheduler import get_scheduler, APSCHEDULER_AVAILABLE
        scheduler = get_scheduler()

        # Auto-restart logic (survives app restarts)
        if 'scheduler_auto_started' not in st.session_state:
            if APSCHEDULER_AVAILABLE:
                # Check if scheduler should auto-restart
                should_restart = scheduler._load_state()

                if should_restart and not scheduler.is_running:
                    try:
                        scheduler.start()
                        st.session_state.scheduler_auto_started = True
                        st.success("🔄 **Autonomous Trader Auto-Restarted** - Resumed from previous session")
                    except Exception as e:
                        st.warning(f"Auto-restart failed: {str(e)}")
                elif not scheduler.is_running:
                    st.info("💡 Autonomous trader is stopped. Enable it in the Auto-Pilot tab to start trading.")
                else:
                    st.session_state.scheduler_auto_started = True
            elif not APSCHEDULER_AVAILABLE:
                st.warning("⚠️ APScheduler not installed. Auto-pilot features are disabled. Install with: pip install apscheduler")
    except Exception as e:
        st.error(f"Failed to initialize scheduler: {str(e)}")
        scheduler = None

    # Main tabs
    tabs = st.tabs([
        "📊 Performance",
        "📈 Current Positions",
        "📜 Trade History",
        "📋 Activity Log",
        "🔄 Auto-Pilot",
        "⚙️ Settings"
    ])

    # TAB 1: Performance
    with tabs[0]:
        display_performance(trader)

    # TAB 2: Current Positions
    with tabs[1]:
        display_current_positions(trader)

    # TAB 3: Trade History
    with tabs[2]:
        display_trade_history(trader)

    # TAB 4: Activity Log
    with tabs[3]:
        display_activity_log(trader)

    # TAB 5: Auto-Pilot Scheduler
    with tabs[4]:
        display_autopilot_scheduler(scheduler)

    # TAB 6: Settings
    with tabs[5]:
        display_settings(trader)

    # Control Panel
    st.divider()
    display_control_panel(trader)


def display_performance(trader: AutonomousPaperTrader):
    """Display performance metrics"""

    st.header("📊 Trading Performance")

    # Show data timestamp
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    st.caption(f"📅 Data as of: {current_time}")

    perf = trader.get_performance()

    # Main metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Starting Capital",
            f"${perf['starting_capital']:,.0f}",
            help="Initial account value"
        )

    with col2:
        st.metric(
            "Current Value",
            f"${perf['current_value']:,.2f}",
            delta=f"${perf['total_pnl']:+,.2f}",
            help="Current account value"
        )

    with col3:
        st.metric(
            "Total Return",
            f"{perf['return_pct']:+.2f}%",
            delta=f"${perf['total_pnl']:+,.2f}",
            help="Overall return %"
        )

    with col4:
        color = "🟢" if perf['win_rate'] >= 75 else "🟡" if perf['win_rate'] >= 60 else "🔴"
        st.metric(
            "Win Rate",
            f"{color} {perf['win_rate']:.1f}%",
            help="Target: 75%+"
        )

    # Detailed stats
    if perf['total_trades'] > 0:
        st.divider()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Trades", perf['total_trades'])

        with col2:
            st.metric("Open Positions", perf['open_positions'])

        with col3:
            st.metric("Realized P&L", f"${perf['realized_pnl']:+,.2f}")

        with col4:
            st.metric("Unrealized P&L", f"${perf['unrealized_pnl']:+,.2f}")

    # Performance Line Graph
    st.divider()
    st.subheader("📈 Account Value Over Time")

    # Get historical performance data
    conn = sqlite3.connect(trader.db_path)

    # Get all trades chronologically
    trades = pd.read_sql_query("""
        SELECT
            entry_date,
            entry_time,
            closed_date,
            closed_time,
            realized_pnl,
            status
        FROM autonomous_positions
        ORDER BY entry_date, entry_time
    """, conn)
    conn.close()

    if not trades.empty:
        # Build performance timeline
        timeline = []
        running_capital = perf['starting_capital']

        # Add starting point
        if len(trades) > 0:
            first_date = trades.iloc[0]['entry_date']
            timeline.append({
                'date': first_date,
                'account_value': running_capital,
                'event': 'Start'
            })

        # Add each completed trade
        for _, trade in trades.iterrows():
            if trade['status'] == 'CLOSED' and trade['closed_date']:
                running_capital += trade['realized_pnl']
                timeline.append({
                    'date': trade['closed_date'],
                    'account_value': running_capital,
                    'event': f"${trade['realized_pnl']:+,.0f}"
                })

        # Add current value
        today = datetime.now().strftime('%Y-%m-%d')
        timeline.append({
            'date': today,
            'account_value': perf['current_value'],
            'event': 'Now'
        })

        # Create DataFrame
        df = pd.DataFrame(timeline)
        df['date'] = pd.to_datetime(df['date'])

        # Plot
        import plotly.graph_objects as go

        fig = go.Figure()

        # Account value line
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['account_value'],
            mode='lines+markers',
            name='Account Value',
            line=dict(color='#00D4FF', width=3),
            marker=dict(size=8),
            hovertemplate='%{x}<br>$%{y:,.2f}<extra></extra>'
        ))

        # Starting capital reference line
        fig.add_hline(
            y=perf['starting_capital'],
            line_dash="dash",
            line_color="gray",
            annotation_text=f"Starting Capital: ${perf['starting_capital']:,.0f}",
            annotation_position="right"
        )

        # Styling
        fig.update_layout(
            title="",
            xaxis_title="Date",
            yaxis_title="Account Value ($)",
            hovermode='x unified',
            height=400,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )

        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

        st.plotly_chart(fig, use_container_width=True, key="autonomous_trader_performance_chart")

        # ============================================================================
        # PROFITABILITY ANALYTICS - Help Identify What Makes Money
        # ============================================================================

        st.divider()
        st.subheader("💰 Profitability Analytics - Optimize Your Edge")

        # Get all closed trades for analysis
        conn = sqlite3.connect(trader.db_path)
        all_trades = pd.read_sql_query("""
            SELECT
                strategy,
                action,
                realized_pnl,
                entry_date,
                closed_date,
                confidence,
                CASE
                    WHEN realized_pnl > 0 THEN 'Win'
                    ELSE 'Loss'
                END as outcome
            FROM autonomous_positions
            WHERE status = 'CLOSED'
            ORDER BY closed_date, closed_time
        """, conn)
        conn.close()

        if len(all_trades) >= 5:  # Need at least 5 trades for meaningful analysis

            # Row 1: Advanced Performance Metrics
            st.markdown("#### 🎯 Key Performance Indicators")
            col1, col2, col3, col4 = st.columns(4)

            wins = all_trades[all_trades['realized_pnl'] > 0]
            losses = all_trades[all_trades['realized_pnl'] <= 0]

            avg_win = wins['realized_pnl'].mean() if len(wins) > 0 else 0
            avg_loss = abs(losses['realized_pnl'].mean()) if len(losses) > 0 else 0

            # Profit Factor (total wins / total losses)
            total_wins = wins['realized_pnl'].sum()
            total_losses = abs(losses['realized_pnl'].sum())
            profit_factor = total_wins / total_losses if total_losses > 0 else 0

            # Expectancy (average $ per trade)
            expectancy = all_trades['realized_pnl'].mean()

            # Win/Loss Ratio
            win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

            with col1:
                pf_color = "🟢" if profit_factor >= 2.0 else "🟡" if profit_factor >= 1.5 else "🔴"
                st.metric(
                    "Profit Factor",
                    f"{pf_color} {profit_factor:.2f}",
                    help="Total Wins / Total Losses (Target: 2.0+)"
                )

            with col2:
                exp_color = "🟢" if expectancy >= 100 else "🟡" if expectancy >= 50 else "🔴"
                st.metric(
                    "Expectancy",
                    f"{exp_color} ${expectancy:+,.2f}",
                    help="Average $ per trade (higher is better)"
                )

            with col3:
                ratio_color = "🟢" if win_loss_ratio >= 2.0 else "🟡" if win_loss_ratio >= 1.5 else "🔴"
                st.metric(
                    "Win/Loss Ratio",
                    f"{ratio_color} {win_loss_ratio:.2f}x",
                    help="Avg Win / Avg Loss (Target: 2.0x+)"
                )

            with col4:
                # Consecutive streak
                streaks = []
                current_streak = 0
                for _, trade in all_trades.iterrows():
                    if trade['realized_pnl'] > 0:
                        current_streak = current_streak + 1 if current_streak > 0 else 1
                    else:
                        current_streak = current_streak - 1 if current_streak < 0 else -1
                    streaks.append(current_streak)

                current_streak = streaks[-1] if streaks else 0
                streak_emoji = "🔥" if current_streak > 0 else "❄️"
                streak_color = "green" if current_streak > 0 else "red"
                st.metric(
                    "Current Streak",
                    f"{streak_emoji} {abs(current_streak)} {'W' if current_streak > 0 else 'L'}",
                    help="Consecutive wins or losses"
                )

            # Row 2: Strategy Performance Leaderboard
            st.divider()
            st.markdown("#### 🏆 Strategy Performance Leaderboard - What Actually Makes Money")

            strategy_perf = all_trades.groupby('strategy').agg({
                'realized_pnl': ['sum', 'mean', 'count'],
                'outcome': lambda x: (x == 'Win').sum() / len(x) * 100
            }).round(2)

            strategy_perf.columns = ['Total P&L', 'Avg P&L', 'Trades', 'Win Rate %']
            strategy_perf = strategy_perf.sort_values('Total P&L', ascending=False)

            # Display as styled dataframe with color coding
            def highlight_pnl(val):
                if isinstance(val, (int, float)):
                    if val > 0:
                        return 'background-color: rgba(0, 255, 136, 0.2); color: #00FF88; font-weight: 700'
                    elif val < 0:
                        return 'background-color: rgba(255, 68, 68, 0.2); color: #FF4444; font-weight: 700'
                return ''

            st.dataframe(
                strategy_perf.style.applymap(highlight_pnl, subset=['Total P&L', 'Avg P&L']),
                use_container_width=True
            )

            # Best vs Worst Strategy Callout
            best_strategy = strategy_perf.index[0]
            best_pnl = strategy_perf.iloc[0]['Total P&L']
            worst_strategy = strategy_perf.index[-1]
            worst_pnl = strategy_perf.iloc[-1]['Total P&L']

            col1, col2 = st.columns(2)
            with col1:
                st.success(f"**🏆 Best Strategy:** {best_strategy}\n\n**Total P&L:** ${best_pnl:+,.2f}")
            with col2:
                if worst_pnl < 0:
                    st.error(f"**⚠️ Worst Strategy:** {worst_strategy}\n\n**Total P&L:** ${worst_pnl:+,.2f}")
                else:
                    st.info(f"**Lowest Performer:** {worst_strategy}\n\n**Total P&L:** ${worst_pnl:+,.2f}")

            # Row 3: Win Rate Trend (Rolling Average)
            st.divider()
            st.markdown("#### 📈 Win Rate Trend - Is Your Edge Improving?")

            # Calculate rolling 5-trade win rate
            all_trades['is_win'] = (all_trades['realized_pnl'] > 0).astype(int)
            all_trades['rolling_win_rate'] = all_trades['is_win'].rolling(window=min(5, len(all_trades)), min_periods=1).mean() * 100
            all_trades['trade_number'] = range(1, len(all_trades) + 1)

            fig2 = go.Figure()

            # Win rate line
            fig2.add_trace(go.Scatter(
                x=all_trades['trade_number'],
                y=all_trades['rolling_win_rate'],
                mode='lines+markers',
                name='Win Rate',
                line=dict(color='#00FF88', width=3),
                marker=dict(size=8),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 136, 0.1)'
            ))

            # Target line at 75%
            fig2.add_hline(
                y=75,
                line_dash="dash",
                line_color="#FFB800",
                annotation_text="Target: 75%",
                annotation_position="right"
            )

            fig2.update_layout(
                xaxis_title="Trade Number",
                yaxis_title="Win Rate (%)",
                hovermode='x',
                height=350,
                showlegend=False,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
            )

            fig2.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
            fig2.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)', range=[0, 100])

            st.plotly_chart(fig2, use_container_width=True, key="win_rate_trend_chart")

            # Row 4: Day of Week Performance
            if len(all_trades) >= 10:
                st.divider()
                st.markdown("#### 📅 Day of Week Performance - When Do You Make Money?")

                all_trades['day_of_week'] = pd.to_datetime(all_trades['entry_date']).dt.day_name()
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

                day_perf = all_trades.groupby('day_of_week').agg({
                    'realized_pnl': ['sum', 'mean', 'count']
                }).round(2)

                day_perf.columns = ['Total P&L', 'Avg P&L', 'Trades']
                day_perf = day_perf.reindex([d for d in day_order if d in day_perf.index])

                # Bar chart
                fig3 = go.Figure()

                colors = ['#00FF88' if x > 0 else '#FF4444' for x in day_perf['Total P&L']]

                fig3.add_trace(go.Bar(
                    x=day_perf.index,
                    y=day_perf['Total P&L'],
                    marker_color=colors,
                    text=day_perf['Total P&L'].apply(lambda x: f'${x:+,.0f}'),
                    textposition='outside'
                ))

                fig3.update_layout(
                    xaxis_title="Day of Week",
                    yaxis_title="Total P&L ($)",
                    height=350,
                    showlegend=False,
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                )

                fig3.update_xaxes(showgrid=False)
                fig3.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

                st.plotly_chart(fig3, use_container_width=True, key="day_of_week_chart")

                # Best day callout
                best_day = day_perf['Total P&L'].idxmax()
                best_day_pnl = day_perf.loc[best_day, 'Total P&L']
                st.info(f"💡 **Best Trading Day:** {best_day} with ${best_day_pnl:+,.2f} total P&L")

        elif len(all_trades) > 0:
            st.info("📊 **Coming Soon!** Advanced analytics will appear after 5+ closed trades")

    else:
        st.info("📊 Performance chart will appear after your first trade is closed")


def display_current_positions(trader: AutonomousPaperTrader):
    """Display current open positions"""

    st.header("📈 Current Positions")

    # Show data timestamp
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    st.caption(f"📅 Data as of: {current_time}")

    conn = sqlite3.connect(trader.db_path)
    positions = pd.read_sql_query("""
        SELECT * FROM autonomous_positions
        WHERE status = 'OPEN'
        ORDER BY entry_date DESC, entry_time DESC
    """, conn)
    conn.close()

    if positions.empty:
        st.info("No open positions. The trader will automatically find and execute a new trade on the next market day.")
        return

    # Display each position
    for _, pos in positions.iterrows():
        entry_value = pos['entry_price'] * pos['contracts'] * 100
        pnl_pct = (pos['unrealized_pnl'] / entry_value * 100) if entry_value > 0 else 0

        # Color based on P&L
        if pnl_pct >= 25:
            status_color = "🟢"
        elif pnl_pct >= 0:
            status_color = "🟡"
        elif pnl_pct >= -15:
            status_color = "🟠"
        else:
            status_color = "🔴"

        with st.container():
            st.markdown(f"### {status_color} {pos['strategy']}")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.text(f"Action: {pos['action']}")
                st.text(f"Opened: {pos['entry_date']} {pos['entry_time'][:5]}")

            with col2:
                st.metric("Strike", f"${pos['strike']:.0f}")
                st.caption(f"{pos['option_type'].upper()}")
                st.caption(f"Exp: {pos['expiration_date']}")

            with col3:
                st.metric("Contracts", pos['contracts'])
                st.caption(f"Entry: ${pos['entry_price']:.2f}")

            with col4:
                st.metric(
                    "P&L",
                    f"${pos['unrealized_pnl']:+,.2f}",
                    delta=f"{pnl_pct:+.1f}%"
                )

            # Trade reasoning
            with st.expander("📊 Why This Trade?"):
                st.markdown(pos['trade_reasoning'])

                st.markdown("**Entry Details:**")
                st.text(f"Bid: ${pos['entry_bid']:.2f} | Ask: ${pos['entry_ask']:.2f}")
                st.text(f"Entry: ${pos['entry_price']:.2f} (mid)")
                st.text(f"SPY: ${pos['entry_spot_price']:.2f}")
                st.text(f"Confidence: {pos['confidence']}%")

                if pos['contract_symbol']:
                    st.caption(f"Contract: {pos['contract_symbol']}")

            st.divider()


def display_trade_history(trader: AutonomousPaperTrader):
    """Display closed trades"""

    st.header("📜 Trade History")

    # Show data timestamp
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    st.caption(f"📅 Data as of: {current_time}")

    conn = sqlite3.connect(trader.db_path)
    positions = pd.read_sql_query("""
        SELECT * FROM autonomous_positions
        WHERE status = 'CLOSED'
        ORDER BY closed_date DESC, closed_time DESC
        LIMIT 50
    """, conn)
    conn.close()

    if positions.empty:
        st.info("No closed trades yet. Trades will appear here after they're automatically closed.")
        return

    # Summary
    winners = positions[positions['realized_pnl'] > 0]
    losers = positions[positions['realized_pnl'] <= 0]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Closed", len(positions))

    with col2:
        st.metric("Winners", len(winners))

    with col3:
        st.metric("Losers", len(losers))

    with col4:
        total_pnl = positions['realized_pnl'].sum()
        st.metric("Total P&L", f"${total_pnl:+,.2f}")

    st.divider()

    # Trade list
    for _, pos in positions.iterrows():
        entry_value = pos['entry_price'] * pos['contracts'] * 100
        pnl_pct = (pos['realized_pnl'] / entry_value * 100) if entry_value > 0 else 0

        # Color
        emoji = "✅" if pos['realized_pnl'] > 0 else "❌"

        with st.expander(f"{emoji} {pos['strategy']} | {pos['entry_date']} | P&L: ${pos['realized_pnl']:+,.2f} ({pnl_pct:+.1f}%)"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Trade Details**")
                st.text(f"Action: {pos['action']}")
                st.text(f"Strike: ${pos['strike']:.0f} {pos['option_type'].upper()}")
                st.text(f"Expiration: {pos['expiration_date']}")
                st.text(f"Contracts: {pos['contracts']}")
                st.text(f"Opened: {pos['entry_date']} {pos['entry_time'][:5]}")
                st.text(f"Closed: {pos['closed_date']} {pos['closed_time'][:5]}")

            with col2:
                st.markdown("**Performance**")
                st.text(f"Entry: ${pos['entry_price']:.2f}")
                st.text(f"Exit: ${pos['exit_price']:.2f}")
                st.text(f"P&L: ${pos['realized_pnl']:+,.2f}")
                st.text(f"Return: {pnl_pct:+.1f}%")
                st.text(f"Exit Reason: {pos['exit_reason']}")

            st.markdown("**Trade Reasoning**")
            st.caption(pos['trade_reasoning'])


def display_activity_log(trader: AutonomousPaperTrader):
    """Display system activity log"""

    st.header("📋 Activity Log")

    # Show data timestamp
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    st.caption(f"📅 Data as of: {current_time}")

    conn = sqlite3.connect(trader.db_path)
    log = pd.read_sql_query("""
        SELECT * FROM autonomous_trade_log
        ORDER BY date DESC, time DESC
        LIMIT 100
    """, conn)
    conn.close()

    if log.empty:
        st.info("No activity yet. The system will log all actions here.")
        return

    # Display log entries
    for _, entry in log.iterrows():
        timestamp = f"{entry['date']} {entry['time'][:5]}"
        icon = "✅" if entry['success'] else "❌"

        with st.expander(f"{icon} {timestamp} - {entry['action']}"):
            st.text(entry['details'])
            if entry['position_id']:
                st.caption(f"Position ID: {entry['position_id']}")


def display_settings(trader: AutonomousPaperTrader):
    """Display settings"""

    st.header("⚙️ Settings")

    st.success("""
    **🤖 AI-Powered Trading Settings:**

    🤖 **Auto-Execute**: ON (always)
    💰 **Starting Capital**: $5,000
    📊 **Position Sizing**:
       - Directional (calls/puts): 25% max ($1,250)
       - Iron Condors: 20% max ($1,000)
    📅 **Trading Frequency**: GUARANTEED 1 trade per day

    **🧠 AI Exit Strategy (Flexible & Intelligent)**:
    - Hard Stop: -50% loss (protect capital)
    - Expiration Safety: Close on expiration day
    - **AI Decision**: Claude analyzes P&L, GEX changes, time left, thesis validity
    - **Fallback Rules**: If AI unavailable (±40%, ±30%, 1 DTE, GEX flip)

    **🎯 Dual Strategy System**:
    1. **Primary**: Directional trades based on GEX regime
       - Negative GEX squeeze/breakdown setups
       - 5-7 DTE for quick moves
    2. **Fallback**: Iron Condor premium collection
       - Used when no clear GEX signal (< 70% confidence)
       - 30-45 DTE for theta decay
       - ±6% wings for safety on $5K account
    """)

    st.divider()

    # Performance targets
    st.markdown("### 🎯 Performance Targets")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Target Win Rate", "75%+")

    with col2:
        st.metric("Target Monthly Return", "10-15%")

    with col3:
        st.metric("Max Drawdown", "< 20%")


def display_autopilot_scheduler(scheduler):
    """Display Auto-Pilot scheduler monitoring dashboard"""

    st.header("🔄 Auto-Pilot Scheduler")

    st.info("""
    **🤖 FULLY AUTOMATED TRADING** - Runs in background during market hours!

    ✅ **APScheduler Integration**: Background scheduler runs with Streamlit web service
    ✅ **Market Hours**: Every hour from 10:00 AM - 3:00 PM ET, Monday-Friday
    ✅ **Automatic Execution**: Finds trades and manages positions without manual intervention
    ✅ **Persistent Logging**: All activity logged to logs/autonomous_trader.log
    ✅ **Render Compatible**: Designed for Render standard plan deployment
    """)

    st.divider()

    # Get scheduler status
    status = scheduler.get_status()

    # Status Overview
    st.subheader("📊 Scheduler Status")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if status['is_running']:
            st.success("✅ **RUNNING**")
            st.caption("Scheduler active")
        else:
            st.warning("⏸️ **STOPPED**")
            st.caption("Scheduler inactive")

    with col2:
        if status['market_open']:
            st.success("📈 **MARKET OPEN**")
            st.caption("Trading hours")
        else:
            st.info("🔒 **MARKET CLOSED**")
            st.caption("Outside hours")

    with col3:
        st.metric("Executions", status['execution_count'])
        st.caption("Total runs completed")

    with col4:
        st.metric("Current Time ET", "")
        st.caption(status['current_time_et'])

    st.divider()

    # Control Buttons
    st.subheader("🎮 Controls")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("▶️ START SCHEDULER", type="primary", disabled=status['is_running']):
            try:
                scheduler.start()
                st.success("✅ Scheduler started successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error starting scheduler: {str(e)}")

    with col2:
        if st.button("⏸️ STOP SCHEDULER", type="secondary", disabled=not status['is_running']):
            try:
                scheduler.stop()
                st.warning("⏸️ Scheduler stopped")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error stopping scheduler: {str(e)}")

    with col3:
        if st.button("🔄 REFRESH STATUS"):
            st.rerun()

    st.divider()

    # Schedule Information
    st.subheader("📅 Schedule Information")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Next Scheduled Run**")
        next_run = status.get('next_run', 'Not scheduled')
        if status['is_running'] and next_run != 'Scheduler not running':
            st.info(f"🕐 {next_run}")
        else:
            st.caption(next_run)

    with col2:
        st.markdown("**Last Activity**")
        st.caption(f"Trade Check: {status['last_trade_check']}")
        st.caption(f"Position Check: {status['last_position_check']}")

    st.divider()

    # Error Display
    if status['last_error']:
        st.subheader("⚠️ Last Error")
        with st.expander("View Error Details", expanded=True):
            st.error(f"**Timestamp**: {status['last_error']['timestamp']}")
            st.error(f"**Error**: {status['last_error']['error']}")
            st.code(status['last_error']['traceback'], language='python')

    st.divider()

    # Recent Logs
    st.subheader("📜 Recent Logs")

    log_lines = st.slider("Number of log lines to display", min_value=10, max_value=200, value=50, step=10)

    try:
        recent_logs = scheduler.get_recent_logs(lines=log_lines)

        if recent_logs:
            # Display in code block for better readability
            log_text = "".join(recent_logs)
            st.code(log_text, language='log')

            # Download button
            st.download_button(
                label="📥 Download Full Log",
                data=log_text,
                file_name=f"autonomous_trader_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain"
            )
        else:
            st.info("No log entries yet. Logs will appear after the scheduler starts running.")

    except Exception as e:
        st.error(f"Error reading logs: {str(e)}")

    st.divider()

    # How It Works
    st.subheader("🤖 How Auto-Pilot Works")

    st.markdown("""
    **Scheduled Execution (Every Hour, 10 AM - 3 PM ET, Mon-Fri)**:

    1. **Check Market Status**
       - Verify market is open (9:30 AM - 4:00 PM ET)
       - Skip execution if market closed

    2. **Find Daily Trade**
       - Check if already traded today
       - If not, scan for high-confidence GEX setups
       - Execute directional trade OR Iron Condor fallback
       - GUARANTEED one trade per day

    3. **Manage Open Positions**
       - Check all open positions
       - Apply AI-powered exit logic
       - Execute stops, take profits, or hold
       - Log all decisions

    4. **Log Everything**
       - All actions logged to persistent file
       - Accessible via this dashboard
       - Render maintains logs across restarts

    **Why APScheduler?**
    - Runs in background with Streamlit web service
    - No separate processes needed (Render compatible)
    - Timezone-aware (America/New_York)
    - Survives web service restarts
    - More reliable than cron jobs on Render
    """)

    st.divider()

    # Deployment Info
    st.subheader("🚀 Render Deployment Notes")

    st.success("""
    **✅ Ready for Render Standard Plan**

    This scheduler is designed to run seamlessly on Render:

    1. **Starts Automatically**: When Streamlit app starts, scheduler initializes
    2. **Background Operation**: Runs independently of user dashboard interactions
    3. **Persistent Logging**: Logs stored in logs/ directory (Render maintains this)
    4. **Low Resource Usage**: Minimal CPU/memory footprint
    5. **API Friendly**: Respects rate limits with built-in throttling

    **To Deploy**:
    1. Push code to GitHub
    2. Connect Render to your repo
    3. Add environment variables (if needed)
    4. Deploy as Web Service
    5. Scheduler auto-starts with the app
    6. Monitor via this dashboard

    **No manual intervention needed after deployment!**
    """)


def display_control_panel(trader: AutonomousPaperTrader):
    """Display automation status - NO manual controls"""

    st.header("🤖 Automation Status")

    # Get last trade date
    last_trade_date = trader.get_config('last_trade_date')
    today = datetime.now().strftime('%Y-%m-%d')

    # Check if traded today
    traded_today = (last_trade_date == today)

    # Get open positions count
    conn = sqlite3.connect(trader.db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM autonomous_positions WHERE status = 'OPEN'")
    open_positions = c.fetchone()[0]
    conn.close()

    # Check if scheduler is running
    try:
        from trader_scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler_running = scheduler.is_running
    except:
        scheduler_running = False

    # Display status
    col1, col2, col3 = st.columns(3)

    with col1:
        if traded_today:
            st.success("✅ **Trade Finding**")
            st.caption(f"✓ Executed today at {last_trade_date}")
        else:
            if scheduler_running:
                st.warning("⏳ **Trade Finding**")
                st.caption("🔍 Looking for today's trade (checks hourly 10AM-3PM ET)")
            else:
                st.error("⚠️ **Trade Finding**")
                st.caption("⛔ Scheduler stopped - not searching")

    with col2:
        if open_positions > 0:
            st.success("👀 **Position Monitoring**")
            st.caption(f"{open_positions} position(s) being monitored")
        else:
            st.info("✋ **Position Monitoring**")
            st.caption("No open positions")

    with col3:
        if scheduler_running:
            st.success("🟢 **Scheduler Status**")
            st.caption("✓ Running - auto-checking hourly")
        else:
            st.error("🔴 **Scheduler Status**")
            st.caption("⛔ Stopped - trades paused")

    # Show next scheduled check time
    if scheduler_running:
        try:
            from trader_scheduler import get_scheduler
            import pytz
            scheduler = get_scheduler()
            status = scheduler.get_status()

            if 'next_run' in status and status['next_run'] != 'Scheduler not running':
                st.info(f"⏰ **Next Check:** {status['next_run']}")
        except:
            pass

    st.divider()

    # Trading schedule
    st.markdown("### 📅 Autonomous Trading Schedule")

    st.info("""
    **🤖 HOW THE AI TRADER WORKS**

    The system thinks like a professional options trader:

    ✅ **GUARANTEED Daily Trade**: Never sits idle
    ✅ **Smart Strategy Selection**:
       - Strong GEX signal → Directional trade (calls/puts)
       - Unclear GEX → Iron Condor (collect premium)
    ✅ **Timing**: Checks hourly 10:00 AM - 3:00 PM ET (6 checks per day)
    ✅ **AI-Powered Exits**: Claude analyzes each position intelligently

    **TRADE SELECTION LOGIC:**
    1. **Get GEX Data**: Analyze SPY gamma exposure
    2. **Find Setup**:
       - High confidence (70%+) → Execute directional trade
       - Low confidence → Execute Iron Condor fallback
    3. **GUARANTEED**: Always makes 1 trade per day
    4. **Reset**: Next market day, repeat

    **Examples:**
    - Negative GEX at 10 AM → Buys calls for squeeze
    - Neutral GEX at 10 AM → Iron Condor for premium
    - Strong setup at 2 PM → Executes immediately

    **AI EXIT MANAGEMENT:**
    - **Hourly Checks**: Monitors all open positions
    - **AI Analysis**: Claude evaluates:
      - Is thesis still valid? (GEX regime changes)
      - Should we take profit or let it run?
      - Has risk/reward shifted?
    - **Safety Stops**: -50% hard stop, expiration day
    - **Fallback**: Simple rules if AI unavailable
    """)

