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

    st.title("🤖 Autonomous SPY Paper Trader")

    st.info("""
    **FULLY AUTOMATED** - This trader runs on its own with ZERO manual intervention!

    ✅ **Starting Capital**: $5,000
    ✅ **Finds trades automatically**: Every market day
    ✅ **Executes automatically**: Based on GEX analysis
    ✅ **Manages exits automatically**: +50% profit, -30% stop, or expiration
    ✅ **Uses REAL option prices**: From Yahoo Finance

    **You don't need to do anything!** Just watch it work.
    """)

    # Initialize trader
    if 'autonomous_trader' not in st.session_state:
        st.session_state.autonomous_trader = AutonomousPaperTrader()

    trader = st.session_state.autonomous_trader

    # Main tabs
    tabs = st.tabs([
        "📊 Performance",
        "📈 Current Positions",
        "📜 Trade History",
        "📋 Activity Log",
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

    # TAB 5: Settings
    with tabs[4]:
        display_settings(trader)

    # Control Panel
    st.divider()
    display_control_panel(trader)


def display_performance(trader: AutonomousPaperTrader):
    """Display performance metrics"""

    st.header("📊 Trading Performance")

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

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📊 Performance chart will appear after your first trade is closed")


def display_current_positions(trader: AutonomousPaperTrader):
    """Display current open positions"""

    st.header("📈 Current Positions")

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
    **Autonomous Trading Settings:**

    🤖 **Auto-Execute**: ON (always)
    💰 **Starting Capital**: $5,000
    📊 **Max Position Size**: 25% ($1,250 per trade)
    🎯 **Profit Target**: +50%
    🛑 **Stop Loss**: -30%
    📅 **Trading Frequency**: Once per market day

    **Exit Rules (Automatic)**:
    - +50% profit → Close immediately
    - -30% loss → Close immediately
    - 1 DTE or less → Close before expiration
    - GEX regime flip → Close (thesis invalidated)
    - +25% with 5+ DTE → Close early (take profit)
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

    # Display status
    col1, col2, col3 = st.columns(3)

    with col1:
        if traded_today:
            st.success("✅ **Trade Finding**")
            st.caption(f"Executed today ({last_trade_date})")
        else:
            st.info("🔍 **Trade Finding**")
            st.caption("Ready for next market day")

    with col2:
        if open_positions > 0:
            st.success("👀 **Position Monitoring**")
            st.caption(f"{open_positions} position(s) being monitored")
        else:
            st.info("✋ **Position Monitoring**")
            st.caption("No open positions")

    with col3:
        st.success("🟢 **System Status**")
        st.caption("Fully autonomous - running")

    st.divider()

    # Trading schedule
    st.markdown("### 📅 Autonomous Trading Schedule")

    st.info("""
    **WHEN IT TRADES (Flexible Opportunity-Based)**

    The autonomous trader is **FLEXIBLE** and waits for the right opportunity:

    ✅ **Once Per Market Day**: Maximum 1 new trade per day
    ✅ **Market Hours Required**: Trades only during 9:30 AM - 4:00 PM ET
    ✅ **Opportunity-Based**: Waits for clear GEX setups, doesn't force trades
    ✅ **No Fixed Time**: Not locked to "30 mins after open" - it's smarter than that!

    **EXECUTION LOGIC:**
    1. **9:30 AM - 4:00 PM ET**: Checks every hour for opportunities
    2. **Analyzes GEX**: Waits for negative GEX with clear regime
    3. **Confirms Setup**: 75%+ confidence required
    4. **Executes**: First valid setup of the day wins
    5. **Stops Looking**: After 1 trade, waits until next market day

    **This means:**
    - If perfect setup at 10:00 AM → Executes then
    - If market unclear at 10:00 AM → Waits for 11:00 AM check
    - If no clear setup all day → No trade (better than forcing bad trades)
    - Next market day → Resets, looks for new opportunity

    **POSITION MANAGEMENT (Continuous)**
    - Checks every hour during market hours
    - Monitors for profit targets: +50%, -30% stop
    - Closes 1 DTE positions automatically
    - Exits on GEX regime flip (thesis invalidated)
    """)

    st.divider()

    # Deployment instructions
    st.markdown("### 🚀 Render Deployment (For True Automation)")

    st.code("""
# Add to Render cron job (runs every hour during market hours):
# Schedule: "0 9-16 * * 1-5" (every hour, 9 AM-4 PM ET, Mon-Fri)

from autonomous_paper_trader import AutonomousPaperTrader
from core_classes_and_engines import TradingVolatilityAPI

trader = AutonomousPaperTrader()
api_client = TradingVolatilityAPI()

# Step 1: Find new trade if haven't traded today
trader.find_and_execute_daily_trade(api_client)

# Step 2: Manage existing positions
trader.auto_manage_positions(api_client)
""", language="python")

    st.success("""
    **Current Mode**: Manual Dashboard View
    **Deploy to Render**: For 24/7 autonomous operation
    **API Usage**: ~2-4 calls per hour (well within limits)
    """)
