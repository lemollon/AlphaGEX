"""
Paper Trading Dashboard
Integrated UI for paper trading, gamma tracking, and strategy management
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List
from paper_trader import PaperTradingEngine, get_next_expiration, parse_dte_from_strategy
from gamma_tracking_database import GammaTrackingDB, display_weekly_gamma_tracking
from expiration_utils import add_expiration_to_setup, display_expiration_info, format_expiration_display


def display_paper_trading_config():
    """Display paper trading configuration settings"""
    st.subheader("⚙️ Paper Trading Settings")

    engine = PaperTradingEngine()

    col1, col2 = st.columns(2)

    with col1:
        # Enable/disable paper trading
        enabled = st.checkbox(
            "Enable Paper Trading",
            value=engine.is_enabled(),
            help="Turn paper trading on/off"
        )
        engine.set_config('enabled', 'true' if enabled else 'false')

        # Auto-execute setting
        auto_execute = st.checkbox(
            "Auto-Execute Trades",
            value=engine.is_auto_execute_enabled(),
            help="Automatically enter trades when high-confidence setups appear"
        )
        engine.set_config('auto_execute', 'true' if auto_execute else 'false')

    with col2:
        # Capital setting
        current_capital = float(engine.get_config('capital'))
        capital = st.number_input(
            "Total Capital ($)",
            min_value=1000.0,
            max_value=10000000.0,
            value=current_capital,
            step=1000.0
        )
        engine.set_config('capital', str(capital))

        # Min confidence
        min_confidence = st.slider(
            "Minimum Confidence for Auto-Execute (%)",
            min_value=50,
            max_value=90,
            value=int(engine.get_config('min_confidence')),
            help="Only auto-execute setups with confidence >= this threshold"
        )
        engine.set_config('min_confidence', str(min_confidence))

    # Max position size
    max_position = st.slider(
        "Maximum Position Size (% of capital)",
        min_value=1.0,
        max_value=25.0,
        value=float(engine.get_config('max_position_size')) * 100,
        step=1.0,
        help="Maximum percentage of capital to risk on a single position"
    )
    engine.set_config('max_position_size', str(max_position / 100))

    # Status indicator
    if enabled:
        if auto_execute:
            st.success("🟢 Paper Trading: ACTIVE (Auto-Execute ON)")
        else:
            st.info("🟡 Paper Trading: ACTIVE (Manual Mode)")
    else:
        st.warning("⚪ Paper Trading: DISABLED")


def display_paper_trading_performance():
    """Display paper trading performance metrics"""
    st.subheader("📊 Performance Summary")

    engine = PaperTradingEngine()
    performance = engine.get_performance_summary()

    # Top-level metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        pnl_delta = performance['total_realized_pnl'] + performance['total_unrealized_pnl']
        pnl_pct = (pnl_delta / performance['total_capital'] * 100) if performance['total_capital'] > 0 else 0
        st.metric(
            "Total P&L",
            f"${pnl_delta:,.2f}",
            delta=f"{pnl_pct:+.2f}%",
            help="Realized + Unrealized P&L"
        )

    with col2:
        st.metric(
            "Account Value",
            f"${performance['current_value']:,.2f}",
            delta=f"${pnl_delta:+,.2f}",
            help="Current account value including open positions"
        )

    with col3:
        win_rate_color = "🟢" if performance['win_rate'] >= 70 else "🟡" if performance['win_rate'] >= 60 else "🔴"
        st.metric(
            "Win Rate",
            f"{win_rate_color} {performance['win_rate']:.1f}%",
            help="Percentage of winning trades"
        )

    with col4:
        st.metric(
            "Total Trades",
            f"{performance['total_trades']}",
            delta=f"{performance['open_positions']} open",
            help="Closed trades + open positions"
        )

    # Detailed stats
    if performance['total_trades'] > 0:
        st.divider()
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Realized P&L",
                f"${performance['total_realized_pnl']:,.2f}",
                help="P&L from closed positions"
            )

        with col2:
            st.metric(
                "Unrealized P&L",
                f"${performance['total_unrealized_pnl']:,.2f}",
                help="P&L from open positions"
            )

        with col3:
            st.metric(
                "Best Trade",
                f"${performance['best_trade']:,.2f}",
                help="Largest winning trade"
            )

        with col4:
            st.metric(
                "Worst Trade",
                f"${performance['worst_trade']:,.2f}",
                help="Largest losing trade"
            )

        # Average win/loss
        if performance['avg_win'] != 0 or performance['avg_loss'] != 0:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "Avg Win",
                    f"${performance['avg_win']:,.2f}"
                )

            with col2:
                st.metric(
                    "Avg Loss",
                    f"${performance['avg_loss']:,.2f}"
                )

            with col3:
                # Win/loss ratio
                if performance['avg_loss'] != 0:
                    win_loss_ratio = abs(performance['avg_win'] / performance['avg_loss'])
                    st.metric(
                        "Win/Loss Ratio",
                        f"{win_loss_ratio:.2f}x",
                        help="Average win / average loss"
                    )


def display_open_positions():
    """Display currently open paper trading positions"""
    st.subheader("📈 Open Positions")

    engine = PaperTradingEngine()

    conn = engine.db_path
    import sqlite3
    conn = sqlite3.connect(engine.db_path)

    positions = pd.read_sql_query("""
        SELECT * FROM paper_positions
        WHERE status = 'OPEN'
        ORDER BY opened_at DESC
    """, conn)
    conn.close()

    if positions.empty:
        st.info("""
        📊 **No Open Positions**

        Positions will appear here when:
        - You manually open a position from a strategy setup
        - Auto-execute opens a position based on high-confidence setups

        **Ready to trade?** Enable auto-execute in settings or manually open a position from the GEX Copilot.
        """)
        return

    # Update all position values
    if 'api_client' in st.session_state:
        for _, pos in positions.iterrows():
            try:
                gex_data = st.session_state.api_client.get_net_gamma(pos['symbol'])
                if gex_data and not gex_data.get('error'):
                    engine.update_position_value(pos['id'], gex_data.get('spot_price', 0))
            except:
                pass

        # Reload positions after update
        conn = sqlite3.connect(engine.db_path)
        positions = pd.read_sql_query("""
            SELECT * FROM paper_positions
            WHERE status = 'OPEN'
            ORDER BY opened_at DESC
        """, conn)
        conn.close()

    # Display positions
    for _, pos in positions.iterrows():
        # Color code by P&L
        pnl_pct = (pos['unrealized_pnl'] / (pos['entry_premium'] * pos['quantity'] * 100) * 100) if (pos['entry_premium'] * pos['quantity']) != 0 else 0

        if pnl_pct >= 10:
            container = st.success
        elif pnl_pct >= 0:
            container = st.info
        elif pnl_pct >= -10:
            container = st.warning
        else:
            container = st.error

        with container(f"**{pos['symbol']} - {pos['strategy']}**"):
            col1, col2, col3, col4, col5 = st.columns(5)

            with col1:
                st.markdown(f"**Action:** {pos['action']}")
                st.caption(f"Opened: {pos['opened_at'][:10]}")

            with col2:
                st.metric("Strike", f"${pos['strike']:.0f}")
                st.caption(f"{pos['option_type'].upper()}")

            with col3:
                st.metric("Expiration", pos['expiration_date'])
                # Calculate time left
                from expiration_utils import get_time_until_expiration
                exp_date = datetime.strptime(pos['expiration_date'], '%Y-%m-%d')
                time_left = get_time_until_expiration(exp_date)
                st.caption(f"{time_left} left")

            with col4:
                st.metric(
                    "P&L",
                    f"${pos['unrealized_pnl']:,.2f}",
                    delta=f"{pnl_pct:+.1f}%"
                )

            with col5:
                if st.button(f"Close Position", key=f"close_{pos['id']}"):
                    engine.close_position(pos['id'], "Manual close")
                    st.success("✅ Position closed!")
                    st.rerun()

            # Expandable details
            with st.expander("View Position Details"):
                detail_col1, detail_col2 = st.columns(2)

                with detail_col1:
                    st.markdown("**Entry Conditions**")
                    st.text(f"Entry Price: ${pos['entry_premium']:.2f}")
                    st.text(f"Entry Spot: ${pos['entry_spot_price']:.2f}")
                    st.text(f"Quantity: {pos['quantity']} contracts")
                    st.text(f"Confidence: {pos['confidence_score']}%")

                with detail_col2:
                    st.markdown("**Current Values**")
                    st.text(f"Current Value: ${pos['current_value']:,.2f}")
                    st.text(f"Entry Value: ${pos['entry_premium'] * pos['quantity'] * 100:,.2f}")
                    st.text(f"Unrealized P&L: ${pos['unrealized_pnl']:,.2f}")

                if pos['notes']:
                    st.markdown("**Strategy Reasoning**")
                    st.caption(pos['notes'])


def display_closed_positions():
    """Display trade history"""
    st.subheader("📜 Trade History")

    engine = PaperTradingEngine()

    import sqlite3
    conn = sqlite3.connect(engine.db_path)

    positions = pd.read_sql_query("""
        SELECT * FROM paper_positions
        WHERE status = 'CLOSED'
        ORDER BY closed_at DESC
        LIMIT 50
    """, conn)
    conn.close()

    if positions.empty:
        st.info("No closed positions yet. Open and close some trades to build history!")
        return

    # Summary metrics
    winners = positions[positions['realized_pnl'] > 0]
    losers = positions[positions['realized_pnl'] < 0]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Total Closed",
            len(positions),
            help=f"{len(winners)} winners, {len(losers)} losers"
        )

    with col2:
        win_rate = (len(winners) / len(positions) * 100) if len(positions) > 0 else 0
        st.metric("Win Rate", f"{win_rate:.1f}%")

    with col3:
        total_pnl = positions['realized_pnl'].sum()
        st.metric("Total Realized", f"${total_pnl:,.2f}")

    # Display table
    st.divider()

    display_df = positions[[
        'symbol', 'strategy', 'action', 'opened_at', 'closed_at',
        'entry_premium', 'exit_price', 'quantity', 'realized_pnl', 'exit_reason'
    ]].copy()

    # Format columns
    display_df['opened_at'] = pd.to_datetime(display_df['opened_at']).dt.strftime('%Y-%m-%d')
    display_df['closed_at'] = pd.to_datetime(display_df['closed_at']).dt.strftime('%Y-%m-%d')
    display_df['pnl_pct'] = ((display_df['exit_price'] - display_df['entry_premium']) / display_df['entry_premium'] * 100)

    display_df.columns = [
        'Symbol', 'Strategy', 'Action', 'Opened', 'Closed',
        'Entry $', 'Exit $', 'Qty', 'P&L $', 'Exit Reason'
    ]

    # Add P&L % column
    display_df['P&L %'] = display_df['P&L $'].apply(lambda x: f"{(x / 1000):+.1f}%")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )


def display_auto_execute_panel(setups: List[Dict], gex_data: Dict):
    """
    Display panel for evaluating and auto-executing setups

    Args:
        setups: List of strategy setups
        gex_data: Current GEX data
    """
    if not setups:
        return

    engine = PaperTradingEngine()

    if not engine.is_enabled():
        return

    st.divider()
    st.subheader("🤖 Auto-Execute Evaluation")

    # Check each setup
    executable_setups = []

    for setup in setups:
        should_execute = engine.evaluate_new_setup(setup, gex_data)
        if should_execute:
            executable_setups.append(setup)

    if not executable_setups:
        st.info("ℹ️ No setups currently meet auto-execute criteria (confidence, capital, uniqueness)")
        return

    st.success(f"✅ {len(executable_setups)} setup(s) ready for auto-execute!")

    for setup in executable_setups:
        # Add expiration info
        setup = add_expiration_to_setup(setup)

        with st.container():
            st.markdown(f"**{setup.get('strategy', 'Unknown')}** - Confidence: {setup.get('confidence', 0)}%")

            col1, col2 = st.columns([3, 1])

            with col1:
                st.text(f"Action: {setup.get('action', 'N/A')}")
                st.text(f"Expiration: {setup.get('expiration_display', 'N/A')}")
                st.caption(setup.get('reasoning', ''))

            with col2:
                if engine.is_auto_execute_enabled():
                    if st.button(f"Execute Now", key=f"exec_{setup.get('strategy', '')}_{setup.get('confidence', 0)}"):
                        position_id = engine.open_position(setup, gex_data)
                        if position_id:
                            st.success(f"✅ Position #{position_id} opened!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to open position")
                else:
                    st.button(f"Execute", disabled=True, help="Enable auto-execute in settings")

            st.divider()


def display_gamma_tracking_integration(symbol: str):
    """
    Display integrated gamma tracking for the current symbol

    Args:
        symbol: Current symbol being analyzed
    """
    st.divider()
    st.subheader(f"📅 Gamma Tracking - {symbol}")

    gamma_db = GammaTrackingDB()

    # Capture snapshot button
    if 'api_client' in st.session_state:
        col1, col2 = st.columns([3, 1])

        with col1:
            snapshots = gamma_db.get_snapshots_for_date_range(symbol, days_back=1)
            st.info(f"📸 {len(snapshots)} snapshots captured today")

        with col2:
            if st.button("📸 Capture Snapshot", key=f"capture_{symbol}", use_container_width=True):
                try:
                    gex_data = st.session_state.api_client.get_net_gamma(symbol)
                    skew_data = st.session_state.api_client.get_skew_data(symbol)

                    if gex_data and not gex_data.get('error'):
                        gamma_db.store_gamma_snapshot(symbol, gex_data, skew_data)
                        st.success("✅ Snapshot captured!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to get data")
                except Exception as e:
                    st.error(f"Error: {e}")

    # Display weekly tracking
    display_weekly_gamma_tracking(symbol, gamma_db)


def display_paper_trading_dashboard_page():
    """Main page for paper trading dashboard"""
    st.title("📊 Paper Trading Dashboard")

    tabs = st.tabs([
        "📈 Performance",
        "🎯 Open Positions",
        "📜 Trade History",
        "⚙️ Settings"
    ])

    with tabs[0]:
        display_paper_trading_performance()

    with tabs[1]:
        display_open_positions()

        # Auto-manage positions button
        st.divider()
        col1, col2 = st.columns([3, 1])

        with col1:
            st.info("💡 Click to update all position values and check exit conditions")

        with col2:
            if st.button("🔄 Manage Positions", use_container_width=True):
                if 'api_client' in st.session_state:
                    engine = PaperTradingEngine()
                    with st.spinner("Managing positions..."):
                        actions = engine.auto_manage_positions(st.session_state.api_client)

                    if actions:
                        st.success(f"✅ Took {len(actions)} action(s)")
                        for action in actions:
                            st.markdown(f"- Closed {action['symbol']} {action['strategy']}: {action['reason']} (P&L: ${action['pnl']:,.2f})")
                        st.rerun()
                    else:
                        st.info("No actions needed - all positions look good!")
                else:
                    st.error("API client not initialized")

    with tabs[2]:
        display_closed_positions()

    with tabs[3]:
        display_paper_trading_config()
