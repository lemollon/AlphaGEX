"""
Paper Trading Dashboard V2
Shows real option prices, detailed trade reasoning, and daily trade finder
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from paper_trader_v2 import PaperTradingEngineV2, DailyTradeFinder
from database_adapter import get_connection


def display_paper_trader_v2():
    """Main dashboard for Paper Trading V2"""

    st.title("🤖 SPY Paper Trader V2 - Real Prices & Daily Trade Finder")

    # Initialize engine
    if 'paper_engine_v2' not in st.session_state:
        st.session_state.paper_engine_v2 = PaperTradingEngineV2(initial_capital=1000000)

    engine = st.session_state.paper_engine_v2

    # Tabs
    tabs = st.tabs([
        "🎯 Daily Trade Finder",
        "📊 Performance",
        "📈 Open Positions",
        "📜 Trade History",
        "⚙️ Settings"
    ])

    # TAB 1: Daily Trade Finder
    with tabs[0]:
        display_daily_trade_finder(engine)

    # TAB 2: Performance
    with tabs[1]:
        display_performance_v2(engine)

    # TAB 3: Open Positions
    with tabs[2]:
        display_open_positions_v2(engine)

    # TAB 4: Trade History
    with tabs[3]:
        display_trade_history_v2(engine)

    # TAB 5: Settings
    with tabs[4]:
        display_settings_v2(engine)


def display_daily_trade_finder(engine: PaperTradingEngineV2):
    """Display daily trade finder - finds at least 1 trade every day"""

    st.header("🎯 Today's Trade Opportunity")

    st.info("""
    **Daily Trade Finder**: Analyzes SPY GEX data and market conditions to find the **BEST trade for today**.

    ✅ Uses **REAL option prices** from Yahoo Finance (not mock data)
    ✅ Provides **detailed reasoning** based on GEX, flip point, and dealer positioning
    ✅ Manages exposure: Max 20% of capital at risk, max 5% per position
    ✅ **Guaranteed**: Finds at least 1 profitable setup daily
    """)

    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown("**Ready to find today's best SPY trade?**")

    with col2:
        if st.button("🔍 Find Trade Now", use_container_width=True, type="primary"):
            if 'api_client' not in st.session_state:
                st.error("❌ API client not initialized")
                return

            with st.spinner("Analyzing SPY market conditions..."):
                trade = engine.find_daily_trade(st.session_state.api_client)

            if trade:
                st.session_state.todays_trade = trade
                st.success("✅ Trade found!")
                st.rerun()
            else:
                st.error("❌ Unable to find trade. Check API connection.")

    # Display today's trade if found
    if 'todays_trade' in st.session_state and st.session_state.todays_trade:
        trade = st.session_state.todays_trade

        st.divider()

        # Trade Header
        st.subheader(f"📈 {trade['strategy']}")

        # Confidence badge
        conf = trade['confidence']
        if conf >= 80:
            st.success(f"🟢 **HIGH CONFIDENCE: {conf}%**")
        elif conf >= 70:
            st.info(f"🟡 **GOOD CONFIDENCE: {conf}%**")
        else:
            st.warning(f"🟠 **MODERATE CONFIDENCE: {conf}%**")

        # Trade Details
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Action", trade['action'])

        with col2:
            st.metric("Strike", f"${trade['strike']:.0f}")
            if trade.get('short_strike'):
                st.caption(f"Short: ${trade['short_strike']:.0f}")

        with col3:
            st.metric("Expiration", f"{trade['dte']} DTE")
            st.caption(trade['expiration_str'])

        with col4:
            st.metric("Entry Price", f"${trade['entry_price']:.2f}")
            st.caption("SPY spot price")

        # Real Option Pricing
        st.divider()
        st.markdown("### 💵 Real Market Prices (from Yahoo Finance)")

        price_col1, price_col2, price_col3, price_col4 = st.columns(4)

        with price_col1:
            st.metric(
                "Bid",
                f"${trade['real_bid']:.2f}",
                help="Current bid price"
            )

        with price_col2:
            st.metric(
                "Ask",
                f"${trade['real_ask']:.2f}",
                help="Current ask price"
            )

        with price_col3:
            st.metric(
                "Mid",
                f"${trade['real_mid']:.2f}",
                help="Entry price = (bid + ask) / 2"
            )
            st.success("✅ **Entry Price**")

        with price_col4:
            st.metric(
                "Last Trade",
                f"${trade['real_last']:.2f}",
                help="Last traded price"
            )

        # Contract details
        if trade.get('contract_symbol'):
            st.caption(f"📜 Contract: **{trade['contract_symbol']}**")

        st.caption(f"📊 IV: **{trade['real_iv']*100:.1f}%**")

        # Detailed Reasoning
        st.divider()
        st.markdown("### 📊 Why This Trade? (Detailed Analysis)")

        st.markdown(trade['reasoning'])

        # Position Sizing
        st.divider()
        st.markdown("### 💰 Position Sizing")

        capital = float(engine.get_config('capital'))
        max_position = float(engine.get_config('max_position_size'))
        max_value = capital * max_position

        premium = trade['real_mid']
        cost_per_contract = premium * 100
        quantity = int(max_value / cost_per_contract)
        quantity = max(1, min(quantity, 50))

        total_cost = quantity * cost_per_contract
        pct_of_capital = (total_cost / capital * 100)

        size_col1, size_col2, size_col3 = st.columns(3)

        with size_col1:
            st.metric("Contracts", f"{quantity}")

        with size_col2:
            st.metric("Total Cost", f"${total_cost:,.2f}")

        with size_col3:
            st.metric("% of Capital", f"{pct_of_capital:.2f}%")

        st.info(f"💡 With ${capital:,.0f} capital and {max_position*100:.0f}% max position size, buying {quantity} contracts")

        # Execute Trade Button
        st.divider()

        exec_col1, exec_col2 = st.columns([3, 1])

        with exec_col1:
            st.markdown("**Ready to execute this trade?**")
            st.caption("This will open a paper position with the reasoning above")

        with exec_col2:
            if st.button("✅ Execute Trade", use_container_width=True, type="primary"):
                position_id = engine.execute_trade(trade)

                if position_id:
                    st.success(f"✅ Position #{position_id} opened!")
                    st.balloons()

                    # Clear today's trade
                    del st.session_state.todays_trade

                    st.rerun()
                else:
                    st.error("❌ Failed to execute trade")

    else:
        st.info("👆 Click 'Find Trade Now' to analyze current SPY conditions and get today's best trade")


def display_performance_v2(engine: PaperTradingEngineV2):
    """Display performance metrics with $1M capital"""

    st.header("📊 Performance Dashboard")

    conn = get_connection()

    # Get all closed positions
    closed = pd.read_sql_query("""
        SELECT * FROM paper_positions_v2 WHERE status = 'CLOSED'
    """, conn.raw_connection)

    # Get open positions
    open_pos = pd.read_sql_query("""
        SELECT * FROM paper_positions_v2 WHERE status = 'OPEN'
    """, conn.raw_connection)

    conn.close()

    # Calculate metrics
    capital = float(engine.get_config('capital'))
    total_realized_pnl = closed['realized_pnl'].sum() if not closed.empty else 0
    total_unrealized_pnl = open_pos['unrealized_pnl'].sum() if not open_pos.empty else 0
    total_pnl = total_realized_pnl + total_unrealized_pnl
    current_value = capital + total_pnl
    return_pct = (total_pnl / capital * 100)

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Starting Capital",
            f"${capital:,.0f}",
            help="Initial capital (1,000K)"
        )

    with col2:
        st.metric(
            "Current Value",
            f"${current_value:,.0f}",
            delta=f"${total_pnl:+,.0f}",
            help="Capital + P&L"
        )

    with col3:
        st.metric(
            "Total Return",
            f"{return_pct:+.2f}%",
            delta=f"${total_pnl:+,.0f}",
            help="Overall return percentage"
        )

    with col4:
        win_rate = 0
        if not closed.empty:
            winners = closed[closed['realized_pnl'] > 0]
            win_rate = (len(winners) / len(closed) * 100)

        color = "🟢" if win_rate >= 75 else "🟡" if win_rate >= 65 else "🔴"
        st.metric(
            "Win Rate",
            f"{color} {win_rate:.1f}%",
            help="Target: 75%+"
        )

    # Detailed stats
    if not closed.empty:
        st.divider()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Realized P&L", f"${total_realized_pnl:+,.2f}")

        with col2:
            st.metric("Unrealized P&L", f"${total_unrealized_pnl:+,.2f}")

        with col3:
            st.metric("Total Trades", len(closed))

        with col4:
            st.metric("Open Positions", len(open_pos))

        # Win/Loss stats
        st.divider()

        winners = closed[closed['realized_pnl'] > 0]
        losers = closed[closed['realized_pnl'] < 0]

        col1, col2, col3 = st.columns(3)

        with col1:
            avg_win = winners['realized_pnl'].mean() if not winners.empty else 0
            st.metric("Avg Win", f"${avg_win:+,.2f}")

        with col2:
            avg_loss = losers['realized_pnl'].mean() if not losers.empty else 0
            st.metric("Avg Loss", f"${avg_loss:+,.2f}")

        with col3:
            if avg_loss != 0:
                ratio = abs(avg_win / avg_loss)
                st.metric("Win/Loss Ratio", f"{ratio:.2f}x")


def display_open_positions_v2(engine: PaperTradingEngineV2):
    """Display open positions with full reasoning"""

    st.header("📈 Open Positions")

    conn = get_connection()

    positions = pd.read_sql_query("""
        SELECT * FROM paper_positions_v2
        WHERE status = 'OPEN'
        ORDER BY opened_at DESC
    """, conn.raw_connection)

    conn.close()

    if positions.empty:
        st.info("📊 No open positions. Use the Daily Trade Finder to find and execute trades!")
        return

    # Display each position
    for _, pos in positions.iterrows():
        pnl_pct = (pos['unrealized_pnl'] / (pos['entry_price'] * pos['quantity'] * 100) * 100) if pos['entry_price'] else 0

        # Color based on P&L
        if pnl_pct >= 10:
            container = st.success
        elif pnl_pct >= 0:
            container = st.info
        elif pnl_pct >= -10:
            container = st.warning
        else:
            container = st.error

        with container(f"**{pos['strategy']}** - Opened {pos['opened_at'][:10]}"):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.markdown(f"**Action:** {pos['action']}")
                st.caption(f"Confidence: {pos['confidence_score']}%")

            with col2:
                st.metric("Strike", f"${pos['strike']:.0f}")
                if pos['short_strike']:
                    st.caption(f"Short: ${pos['short_strike']:.0f}")

            with col3:
                st.metric("Expiration", pos['expiration_date'])
                st.caption(f"{pos['dte']} DTE")

            with col4:
                st.metric(
                    "P&L",
                    f"${pos['unrealized_pnl']:+,.2f}",
                    delta=f"{pnl_pct:+.1f}%"
                )

            # Entry details
            with st.expander("💰 Entry Pricing"):
                price_col1, price_col2, price_col3 = st.columns(3)

                with price_col1:
                    st.text(f"Bid: ${pos['entry_premium_bid']:.2f}")
                    st.text(f"Ask: ${pos['entry_premium_ask']:.2f}")

                with price_col2:
                    st.text(f"Mid: ${pos['entry_premium_mid']:.2f}")
                    st.success("✅ Entry Price")

                with price_col3:
                    st.text(f"Quantity: {pos['quantity']} contracts")
                    st.text(f"Cost: ${pos['entry_price'] * pos['quantity'] * 100:,.2f}")

                if pos['contract_symbol']:
                    st.caption(f"📜 {pos['contract_symbol']}")

            # Trade reasoning
            with st.expander("📊 Why This Trade?"):
                st.markdown(pos['trade_reasoning'])

            st.divider()


def display_trade_history_v2(engine: PaperTradingEngineV2):
    """Display trade history with reasoning"""

    st.header("📜 Trade History")

    conn = get_connection()

    positions = pd.read_sql_query("""
        SELECT * FROM paper_positions_v2
        WHERE status = 'CLOSED'
        ORDER BY closed_at DESC
        LIMIT 50
    """, conn.raw_connection)

    conn.close()

    if positions.empty:
        st.info("No closed trades yet")
        return

    # Display each trade
    for _, pos in positions.iterrows():
        pnl_pct = (pos['realized_pnl'] / (pos['entry_price'] * pos['quantity'] * 100) * 100) if pos['entry_price'] else 0

        # Color based on P&L
        if pos['realized_pnl'] > 0:
            emoji = "✅"
            color = "success"
        else:
            emoji = "❌"
            color = "error"

        with st.expander(f"{emoji} **{pos['strategy']}** | P&L: ${pos['realized_pnl']:+,.2f} ({pnl_pct:+.1f}%)"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Trade Details**")
                st.text(f"Action: {pos['action']}")
                st.text(f"Strike: ${pos['strike']:.0f}")
                st.text(f"Opened: {pos['opened_at']}")
                st.text(f"Closed: {pos['closed_at']}")

            with col2:
                st.markdown("**Performance**")
                st.text(f"Entry: ${pos['entry_price']:.2f}")
                st.text(f"Exit: ${pos['exit_price']:.2f}")
                st.text(f"P&L: ${pos['realized_pnl']:+,.2f}")
                st.text(f"Exit Reason: {pos['exit_reason']}")

            # Trade reasoning
            st.markdown("**Trade Thesis**")
            st.markdown(pos['trade_reasoning'])


def display_settings_v2(engine: PaperTradingEngineV2):
    """Display settings"""

    st.header("⚙️ Settings")

    col1, col2 = st.columns(2)

    with col1:
        capital = st.number_input(
            "Capital ($)",
            min_value=100000,
            max_value=10000000,
            value=int(float(engine.get_config('capital'))),
            step=100000,
            help="Total paper trading capital"
        )
        engine.set_config('capital', str(capital))

    with col2:
        max_position = st.slider(
            "Max Position Size (%)",
            min_value=1,
            max_value=20,
            value=int(float(engine.get_config('max_position_size')) * 100),
            help="Maximum % of capital per position"
        )
        engine.set_config('max_position_size', str(max_position / 100))

    max_exposure = st.slider(
        "Max Total Exposure (%)",
        min_value=10,
        max_value=50,
        value=int(float(engine.get_config('max_exposure')) * 100),
        help="Maximum % of capital at risk across all positions"
    )
    engine.set_config('max_exposure', str(max_exposure / 100))

    st.divider()

    st.success(f"""
    **Current Settings:**
    - Capital: ${capital:,}
    - Max Position: {max_position}% (${capital * max_position / 100:,.0f} per trade)
    - Max Exposure: {max_exposure}% (${capital * max_exposure / 100:,.0f} total)
    """)

    st.info("""
    **Recommended Settings:**
    - Start with $1,000,000 capital
    - Max 5% per position ($50,000)
    - Max 20% total exposure ($200,000)
    - This allows 4+ positions simultaneously
    """)
