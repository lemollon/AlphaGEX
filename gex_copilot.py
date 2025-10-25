"""
main.py - Main Streamlit Application for GEX Trading Co-Pilot v7.0
This is the main entry point that imports all classes from the other files
Run this with: streamlit run main.py
"""

import sys
import os
from pathlib import Path

# Add the current directory to Python path to ensure imports work
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import json
import pytz

# Import configuration and database functions
from config_and_database import (
    DB_PATH, MM_STATES, STRATEGIES,
    init_database
)

# Import core classes and engines
from core_classes_and_engines import (
    TradingVolatilityAPI,
    MonteCarloEngine,
    BlackScholesPricer
)

# Import intelligence and strategy classes
from intelligence_and_strategies import (
    TradingRAG,
    FREDIntegration,
    ClaudeIntelligence,
    SmartStrikeSelector,
    MultiStrategyOptimizer,
    DynamicLevelCalculator,
    get_et_time,
    get_utc_time,
    get_local_time,
    is_market_open
)

# Import visualization and planning classes
from visualization_and_plans import (
    GEXVisualizer,
    TradingPlanGenerator,
    StrategyEngine
)

# Force module reload to pick up latest changes (fixes AttributeError issues)
import importlib
import core_classes_and_engines
import intelligence_and_strategies
import visualization_and_plans
importlib.reload(core_classes_and_engines)
importlib.reload(intelligence_and_strategies)
importlib.reload(visualization_and_plans)

# Re-import classes after reload
from core_classes_and_engines import TradingVolatilityAPI, MonteCarloEngine, BlackScholesPricer
from intelligence_and_strategies import (
    TradingRAG, FREDIntegration, ClaudeIntelligence,
    SmartStrikeSelector, MultiStrategyOptimizer, DynamicLevelCalculator,
    get_et_time, get_utc_time, get_local_time, is_market_open
)
from visualization_and_plans import GEXVisualizer, TradingPlanGenerator, StrategyEngine
from std_tracking_component import display_std_level_changes

# Import new feature modules
from position_sizing import (
    calculate_optimal_position_size,
    display_position_sizing,
    display_position_size_controls,
    display_kelly_criterion_calculator
)
from multi_symbol_scanner import (
    SmartCache,
    scan_symbols,
    display_scanner_dashboard,
    display_watchlist_manager,
    display_scanner_controls
)
from alerts_system import (
    Alert,
    AlertManager,
    display_alert_dashboard,
    display_alert_monitor_widget,
    display_alert_settings,
    display_quick_alert_setup
)
from intraday_tracking import (
    IntradayTracker,
    display_intraday_dashboard,
    display_snapshot_widget,
    get_intraday_summary
)
from trade_journal_agent import (
    TradeJournalAgent,
    display_trade_journal,
    display_journal_settings
)
from position_management_agent import (
    PositionManagementAgent,
    display_position_monitoring,
    display_position_monitoring_widget
)
from autonomous_trader_dashboard import (
    display_autonomous_trader
)

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="GEX Trading Co-Pilot v7.0",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# MAIN APPLICATION
# ============================================================================
def main():
    """Main application entry point"""
    
    # Initialize database
    init_database()
    
    # Initialize session state
    if 'api_client' not in st.session_state:
        st.session_state.api_client = TradingVolatilityAPI()
    if 'claude_ai' not in st.session_state:
        st.session_state.claude_ai = ClaudeIntelligence()
    if 'current_data' not in st.session_state:
        st.session_state.current_data = {}
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'active_positions' not in st.session_state:
        st.session_state.active_positions = []
    if 'rag_system' not in st.session_state:
        st.session_state.rag_system = TradingRAG()
    if 'strike_selector' not in st.session_state:
        st.session_state.strike_selector = SmartStrikeSelector()
    if 'strategy_optimizer' not in st.session_state:
        st.session_state.strategy_optimizer = MultiStrategyOptimizer()
    if 'level_calculator' not in st.session_state:
        st.session_state.level_calculator = DynamicLevelCalculator()
    if 'trade_journal_agent' not in st.session_state:
        st.session_state.trade_journal_agent = TradeJournalAgent()
    if 'position_management_agent' not in st.session_state:
        st.session_state.position_management_agent = PositionManagementAgent()

    # Header with better styling
    st.markdown("""
    <h1 style='text-align: center; color: #00D4FF;'>
    🎯 GEX Trading Co-Pilot v7.0
    </h1>
    <p style='text-align: center; font-size: 18px; color: #888;'>
    The Ultimate Market Maker Hunting Platform
    </p>
    """, unsafe_allow_html=True)
    
    # Top metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("System Status", "🟢 ACTIVE")
    
    with col2:
        positions_count = len(st.session_state.active_positions)
        st.metric("Active Positions", positions_count)
    
    with col3:
        # Calculate today's P&L
        conn = sqlite3.connect(DB_PATH)
        today_pnl_query = pd.read_sql_query(
            "SELECT SUM(pnl) as total FROM positions WHERE DATE(closed_at) = DATE('now')",
            conn
        )
        today_pnl = today_pnl_query.iloc[0]['total'] if not today_pnl_query.empty and today_pnl_query.iloc[0]['total'] is not None else 0.0
        conn.close()
        st.metric("Today's P&L", f"${today_pnl:,.2f}", delta=f"{today_pnl:+,.2f}")
    
    with col4:
        # Get user's timezone preference (default to Central)
        user_tz = st.session_state.get('user_timezone', 'US/Central')
        local_time = get_local_time(user_tz)
        et_time = get_et_time()
        market_status = "🟢 OPEN" if is_market_open() else "🔴 CLOSED"

        # Determine timezone abbreviation
        tz_abbrev = {
            'US/Eastern': 'ET',
            'US/Central': 'CT',
            'US/Mountain': 'MT',
            'US/Pacific': 'PT'
        }.get(user_tz, 'Local')

        current_time = f"{local_time.strftime('%I:%M %p')} {tz_abbrev}"
        st.metric("Current Time", current_time, delta=market_status)

    with col5:
        day = et_time.strftime('%A')
        day_quality = "🟢" if day in ['Monday', 'Tuesday'] else "🟡" if day == 'Wednesday' else "🔴"
        st.metric("Day Quality", f"{day_quality} {day}")
    
    # Sidebar Configuration
    with st.sidebar:
        st.header("⚙️ Configuration")

        # AI Status Indicator (no test button)
        claude_api_key = st.secrets.get("claude_api_key", "")
        if claude_api_key:
            st.success("🤖 **AI Copilot:** ✅ ACTIVE")
        else:
            st.warning("🤖 **AI Copilot:** ⚠️ BASIC MODE")

        st.divider()

        # 1. Symbol Selection (TOP)
        st.subheader("📊 Symbol Analysis")

        col1, col2 = st.columns(2)
        with col1:
            # Initialize default symbol in session state
            if 'selected_symbol' not in st.session_state:
                st.session_state.selected_symbol = "SPY"

            symbol = st.text_input(
                "Enter Symbol",
                value=st.session_state.selected_symbol,
                key="symbol_input"
            ).upper().strip()

            # Update session state
            st.session_state.selected_symbol = symbol
        with col2:
            if st.button("🔄 Refresh", type="primary", use_container_width=True):
                with st.spinner("Fetching latest data..."):
                    try:
                        # OPTIMIZATION: Fetch gammaOI first to check if it includes aggregate data
                        profile_data = st.session_state.api_client.get_gex_profile(symbol)

                        # Check if gammaOI includes aggregate metrics
                        if profile_data and 'aggregate_from_gammaOI' in profile_data:
                            # Use aggregate data from gammaOI - NO NEED for separate /gex/latest call!
                            agg = profile_data['aggregate_from_gammaOI']
                            gex_data = {
                                'symbol': symbol,
                                'spot_price': profile_data['spot_price'],
                                'net_gex': agg['net_gex'],
                                'flip_point': profile_data['flip_point'],
                                'call_wall': profile_data['call_wall'],
                                'put_wall': profile_data['put_wall'],
                                'put_call_ratio': agg['put_call_ratio'],
                                'implied_volatility': agg['implied_volatility'],
                                'collection_date': agg['collection_date']
                            }
                            st.success("⚡ Optimized: Using consolidated gammaOI endpoint (saved 1 API call)")
                        else:
                            # Fall back to separate /gex/latest call
                            gex_data = st.session_state.api_client.get_net_gamma(symbol)

                            # Update gex_data with wall values from profile
                            if profile_data and not gex_data.get('error'):
                                if not gex_data.get('call_wall'):
                                    gex_data['call_wall'] = profile_data.get('call_wall', 0)
                                if not gex_data.get('put_wall'):
                                    gex_data['put_wall'] = profile_data.get('put_wall', 0)

                        # Fetch skew data for enhanced analysis
                        skew_data = st.session_state.api_client.get_skew_data(symbol)

                        # Store in session
                        st.session_state.current_data = {
                            'symbol': symbol,
                            'gex': gex_data,
                            'profile': profile_data if profile_data and profile_data.get('strikes') else None,
                            'skew': skew_data,
                            'timestamp': get_utc_time()
                        }

                        if profile_data and profile_data.get('strikes'):
                            st.success(f"✅ Data refreshed for {symbol}! Profile has {len(profile_data['strikes'])} strikes")
                        else:
                            st.warning(f"⚠️ Data refreshed but no strike-level profile data available")
                    except Exception as e:
                        st.error(f"❌ Error fetching data: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())

        # Quick symbols
        st.caption("Quick Select:")
        cols = st.columns(4)
        for i, sym in enumerate(['SPY', 'QQQ', 'IWM', 'DIA']):
            with cols[i]:
                if st.button(sym, use_container_width=True):
                    st.session_state.selected_symbol = sym
                    st.rerun()

        st.divider()

        # Alert Monitoring Widget
        if st.session_state.current_data:
            display_alert_monitor_widget(st.session_state.current_data.get('gex', {}))

        # Position Monitoring Widget
        display_position_monitoring_widget()

        st.divider()

        # 2. Timezone Settings (SECOND)
        st.subheader("🕐 Timezone Preference")
        if 'user_timezone' not in st.session_state:
            st.session_state.user_timezone = 'US/Central'

        timezone_options = {
            'Eastern Time (ET)': 'US/Eastern',
            'Central Time (CT)': 'US/Central',
            'Mountain Time (MT)': 'US/Mountain',
            'Pacific Time (PT)': 'US/Pacific'
        }

        selected_tz_display = st.selectbox(
            "Your Local Timezone",
            options=list(timezone_options.keys()),
            index=1,  # Default to Central
            help="Select your local timezone for time displays"
        )
        st.session_state.user_timezone = timezone_options[selected_tz_display]

        st.divider()

        # 4. Account Settings (FOURTH)
        st.subheader("💰 Account Settings")
        if 'account_size' not in st.session_state:
            st.session_state.account_size = 50000
        if 'risk_per_trade' not in st.session_state:
            st.session_state.risk_per_trade = 2.0  # Float for slider compatibility

        account_size = st.number_input(
            "Account Size ($)",
            min_value=1000,
            max_value=10000000,
            value=st.session_state.account_size,
            step=1000,
            help="Your total trading account size for position sizing calculations"
        )
        st.session_state.account_size = account_size

        risk_pct = st.slider(
            "Risk Per Trade (%)",
            min_value=0.5,
            max_value=5.0,
            value=float(st.session_state.risk_per_trade),  # Ensure float
            step=0.5,
            help="Percentage of account to risk per trade (1-2% recommended)"
        )
        st.session_state.risk_per_trade = risk_pct

        max_risk = account_size * (risk_pct / 100)
        st.caption(f"Max Risk: ${max_risk:,.2f} per trade")

    # Performance Stats
    with st.sidebar:
        st.divider()
        st.subheader("📊 Performance")
        
        conn = sqlite3.connect(DB_PATH)
        
        # Calculate stats with None handling
        stats_query = pd.read_sql_query("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                AVG(pnl) as avg_pnl,
                SUM(pnl) as total_pnl
            FROM positions
            WHERE status = 'CLOSED'
            AND closed_at >= datetime('now', '-30 days')
        """, conn)
        
        conn.close()
        
        # Safe extraction with defaults
        if not stats_query.empty:
            stats = stats_query.iloc[0]
            total_trades = int(stats['total_trades']) if stats['total_trades'] is not None else 0
            wins = int(stats['wins']) if stats['wins'] is not None else 0
            total_pnl = float(stats['total_pnl']) if stats['total_pnl'] is not None else 0.0
            
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        else:
            win_rate = 0
            total_pnl = 0
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("30D Win Rate", f"{win_rate:.1f}%")
        with col2:
            st.metric("30D P&L", f"${total_pnl:,.2f}")
    
    # Main Content Area - Tabs
    tabs = st.tabs([
        "📈 GEX Analysis",
        "🎯 Trade Setups",
        "🔍 Multi-Symbol Scanner",
        "🔔 Alerts",
        "📅 Trading Plans",
        "💬 AI Co-Pilot",
        "🤖 Auto Trader",
        "📊 Positions",
        "📔 Trade Journal",
        "📚 Education"
    ])
    
    # Tab 1: GEX Analysis
    with tabs[0]:
        if st.session_state.current_data:
            data = st.session_state.current_data

            # Get symbol
            current_symbol = data.get('symbol', 'SPY')

            # ==================================================================
            # SECTION 1: CURRENT MARKET ANALYSIS
            # ==================================================================
            st.header(f"🎯 {current_symbol} - Current Market Analysis")

            # Current Analysis Metrics
            gex_data = data.get('gex', {})

            col1, col2, col3 = st.columns(3)

            with col1:
                # Net GEX
                net_gex = gex_data.get('net_gex', 0)
                st.metric(
                    "Net GEX",
                    f"${net_gex/1e9:.2f}B",
                    delta="Negative" if net_gex < 0 else "Positive",
                    delta_color="inverse" if net_gex < 0 else "normal"
                )

                # MM State
                claude = ClaudeIntelligence()
                mm_state = claude._determine_mm_state(net_gex)
                state_config = MM_STATES[mm_state]

                st.info(f"""
                **MM State: {mm_state}**
                {state_config['behavior']}

                **Action: {state_config['action']}**
                """)

            with col2:
                # Key Levels
                st.subheader("📍 Key Levels")

                spot = gex_data.get('spot_price', 0)
                flip = gex_data.get('flip_point', 0)

                st.metric("Current Price", f"${spot:.2f}")
                st.metric(
                    "Flip Point",
                    f"${flip:.2f}",
                    delta=f"{((flip-spot)/spot*100):+.2f}%" if spot != 0 else "N/A"
                )

                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)

                if call_wall:
                    st.metric("Call Wall", f"${call_wall:.2f}")
                if put_wall:
                    st.metric("Put Wall", f"${put_wall:.2f}")

            with col3:
                # Advanced Skew Metrics (if available)
                if st.session_state.current_data and st.session_state.current_data.get('skew'):
                    st.subheader("📊 Skew Analysis")
                    skew = st.session_state.current_data['skew']

                    # Expected Moves
                    one_day_std = float(skew.get('one_day_std', 0)) * 100
                    one_week_std = float(skew.get('one_week_std', 0)) * 100

                    st.metric("1-Day Expected Move", f"{one_day_std:.2f}%")
                    st.metric("7-Day Expected Move", f"{one_week_std:.2f}%")

                    # Delta Spread (Put/Call skew indicator)
                    delta_spread = float(skew.get('put_call_delta_spread', 0))
                    avg_spread = float(skew.get('avg_PC_delta_spread', 0))

                    skew_status = "BEARISH" if delta_spread < -0.03 else "BULLISH" if delta_spread > 0.03 else "NEUTRAL"
                    skew_color = "🔴" if delta_spread < -0.03 else "🟢" if delta_spread > 0.03 else "🟡"

                    st.metric(
                        "Delta Spread",
                        f"{skew_color} {delta_spread:.4f}",
                        delta=f"Avg: {avg_spread:.4f}"
                    )
                    st.caption(f"Skew: **{skew_status}** - {'Puts expensive' if delta_spread < -0.03 else 'Calls expensive' if delta_spread > 0.03 else 'Balanced'}")

                    # Bollinger Band Width
                    bb_width = float(skew.get('bollinger_band_width', 0)) * 100
                    st.metric("Bollinger Band Width", f"{bb_width:.1f}%")

                    # PCR Changes
                    pcr_30d = float(skew.get('pcr_oi_30_day_change', 0))
                    pcr_60d = float(skew.get('pcr_oi_60_day_change', 0))

                    st.metric("PCR 30d Change", f"{pcr_30d:+.2f}")
                    st.metric("PCR 60d Change", f"{pcr_60d:+.2f}")

            # Day-Over-Day Changes (lazy-loaded to save API calls)
            with st.expander("📊 Day-Over-Day Trends (Click to Load)", expanded=False):
                if st.button("📈 Load Yesterday's Data", key="load_dod_trends"):
                    # Fetch yesterday's data for comparison (historical API call)
                    yesterday_data_quick = st.session_state.api_client.get_yesterday_data(current_symbol)

                    if yesterday_data_quick:
                        changes = st.session_state.api_client.calculate_day_over_day_changes(gex_data, yesterday_data_quick)

                        if changes:
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                if 'flip_point' in changes:
                                    fc = changes['flip_point']
                                    st.metric(
                                        "Flip Point Trend",
                                        f"{fc['trend']} ${fc['current']:.2f}",
                                        delta=f"{fc['change']:+.2f} ({fc['pct_change']:+.1f}%)"
                                    )

                            with col2:
                                if 'implied_volatility' in changes:
                                    iv = changes['implied_volatility']
                                    st.metric(
                                        "IV Trend",
                                        f"{iv['trend']} {iv['current']*100:.1f}%",
                                        delta=f"{iv['pct_change']:+.1f}%"
                                    )

                            with col3:
                                if 'rating' in changes:
                                    rt = changes['rating']
                                    st.metric(
                                        "TV Rating",
                                        f"{rt['trend']} {rt['current']:.0f}",
                                        delta=f"{rt['change']:+.0f}"
                                    )
                        else:
                            st.info("No trend data available for yesterday")
                    else:
                        st.info("No historical data available for yesterday")
                else:
                    st.caption("💡 Click 'Load Yesterday's Data' to see day-over-day changes in flip point, IV, and rating")

            # Skew data educational expander
            if st.session_state.current_data and st.session_state.current_data.get('skew'):
                with st.expander("💡 How to Use Skew Data"):
                    st.markdown("""
                    **Delta Spread:**
                    - **Negative (<-0.03)**: Puts more expensive than calls → Fear in market
                      - **Action**: Consider selling put spreads, be cautious on longs
                    - **Positive (>0.03)**: Calls more expensive → Greed/bullish positioning
                      - **Action**: Consider selling call spreads, look for reversal
                    - **Neutral**: Balanced positioning

                    **Expected Moves:**
                    - Use these for strike selection boundaries
                    - 1-Day: For 0DTE trades
                    - 7-Day: For weekly options

                    **Bollinger Band Width:**
                    - **Narrow (<15%)**: Low volatility, potential breakout coming
                    - **Wide (>25%)**: High volatility, potential mean reversion

                    **PCR Changes:**
                    - **Increasing**: More puts being bought → Defensive positioning
                    - **Decreasing**: Less fear → Bullish sentiment
                    """)

            st.divider()

            # Display GEX Profile Chart
            st.subheader(f"📊 GEX Profile")
            if data.get('profile'):
                visualizer = GEXVisualizer()
                # Add flip_point from GEX data to profile for chart consistency
                profile_with_levels = data['profile'].copy()
                profile_with_levels['flip_point'] = gex_data.get('flip_point', 0)
                profile_with_levels['spot_price'] = gex_data.get('spot_price', 0)
                fig = visualizer.create_gex_profile(profile_with_levels)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"No GEX profile data available for {current_symbol}. Chart cannot be displayed.")

            # Display Game Plan
            st.subheader(f"📋 Today's Trading Plan")

            # Detect setups
            strategy_engine = StrategyEngine()
            setups = strategy_engine.detect_setups(data.get('gex', {}))

            # Generate plan - pass the symbol
            gex_with_symbol = data.get('gex', {}).copy()
            gex_with_symbol['symbol'] = current_symbol
            game_plan = strategy_engine.generate_game_plan(gex_with_symbol, setups)
            st.markdown(game_plan)

            # ==================================================================
            # SECTION 2: DAY-OVER-DAY COMPARISON
            # ==================================================================
            st.divider()
            st.header(f"📏 Day-Over-Day Analysis")

            # Get yesterday's data for comparison
            yesterday_data = st.session_state.api_client.get_yesterday_data(current_symbol)

            if yesterday_data:
                display_std_level_changes(data.get('gex', {}), yesterday_data)
            else:
                st.info("📊 Yesterday's data not available yet. Day-over-day comparison will appear tomorrow once we have 2+ days of data in the system.")

            # ==================================================================
            # SECTION 3: HISTORICAL TRENDS (30 DAYS)
            # ==================================================================
            st.divider()
            st.header(f"📈 30-Day Historical Trends")

            st.info("📅 **Note**: Historical charts require 30 days of data to display properly. If the chart appears blank, the API may not have accumulated 30 days of history yet. Check back in a few days as data is collected daily.")

            if st.button("📊 Load Historical Data"):
                with st.spinner("Fetching 30 days of historical data..."):
                    # Fetch historical gamma and skew data
                    gamma_history = st.session_state.api_client.get_historical_gamma(current_symbol, days_back=30)
                    skew_history = st.session_state.api_client.get_historical_skew(current_symbol, days_back=30)

                    if gamma_history or skew_history:
                        visualizer = GEXVisualizer()
                        hist_fig = visualizer.create_historical_chart(gamma_history, skew_history, current_symbol)
                        st.plotly_chart(hist_fig, use_container_width=True)

                        # Key insights
                        st.subheader("💡 Historical Insights")

                        col1, col2, col3 = st.columns(3)

                        with col1:
                            if gamma_history and len(gamma_history) >= 2:
                                first_flip = float(gamma_history[0].get('gex_flip_price', 0))
                                last_flip = float(gamma_history[-1].get('gex_flip_price', 0))
                                flip_change = ((last_flip - first_flip) / first_flip * 100) if first_flip != 0 else 0

                                st.metric(
                                    "Flip Point 30d Change",
                                    f"${last_flip:.2f}",
                                    delta=f"{flip_change:+.1f}%"
                                )

                        with col2:
                            if skew_history and len(skew_history) >= 2:
                                first_iv = float(skew_history[0].get('implied_volatility', 0)) * 100
                                last_iv = float(skew_history[-1].get('implied_volatility', 0)) * 100
                                iv_change = last_iv - first_iv

                                st.metric(
                                    "IV 30d Change",
                                    f"{last_iv:.1f}%",
                                    delta=f"{iv_change:+.1f}%"
                                )

                        with col3:
                            if skew_history and len(skew_history) >= 2:
                                first_pcr = float(skew_history[0].get('pcr_oi', 0))
                                last_pcr = float(skew_history[-1].get('pcr_oi', 0))
                                pcr_change = last_pcr - first_pcr

                                st.metric(
                                    "PCR 30d Change",
                                    f"{last_pcr:.2f}",
                                    delta=f"{pcr_change:+.2f}"
                                )
                    else:
                        st.warning("No historical data available for this symbol")

            # ==================================================================
            # SECTION 4: MONTE CARLO SIMULATION (PREDICTIVE)
            # ==================================================================
            st.divider()
            st.header(f"🎲 Monte Carlo Price Prediction")

            # Show button if we have GEX data (not dependent on setups)
            gex_data_available = data.get('gex', {}).get('spot_price', 0) > 0

            if gex_data_available:
                if st.button("🎲 Run Monte Carlo Simulation (10,000 paths)"):
                    with st.spinner("Running 10,000 simulations..."):
                        monte_carlo = MonteCarloEngine()
                        sim_results = monte_carlo.simulate_squeeze_play(
                            data['gex'].get('spot_price', 100),
                            data['gex'].get('flip_point', 101),
                            data['gex'].get('call_wall', 105),
                            volatility=0.20,
                            days=5
                        )

                        # Display results
                        col1, col2, col3, col4 = st.columns(4)

                        with col1:
                            st.metric("Hit Flip %", f"{sim_results['probability_hit_flip']:.1f}%")
                        with col2:
                            st.metric("Hit Wall %", f"{sim_results['probability_hit_wall']:.1f}%")
                        with col3:
                            st.metric("Expected Price", f"${sim_results['expected_final_price']:.2f}")
                        with col4:
                            st.metric("Max Gain", f"{sim_results['max_gain_percent']:.1f}%")

                        # Display chart
                        visualizer = GEXVisualizer()
                        mc_fig = visualizer.create_monte_carlo_chart(
                            sim_results,
                            data['gex'].get('spot_price', 100)
                        )
                        st.plotly_chart(mc_fig, use_container_width=True)
            else:
                st.info("💡 Monte Carlo simulation requires valid GEX data. Refresh the symbol to load data.")

            # ==================================================================
            # SECTION 5: INTRADAY GEX TRACKING
            # ==================================================================
            st.divider()
            st.header(f"📸 Intraday GEX Tracking")

            # Auto-capture snapshot on refresh (only if we have valid GEX data)
            if gex_data and gex_data.get('spot_price', 0) > 0:
                tracker = IntradayTracker()
                tracker.capture_snapshot(
                    current_symbol,
                    gex_data,
                    data.get('skew', {})
                )

                # Display intraday dashboard
                display_intraday_dashboard(current_symbol)
            else:
                st.info("💡 Intraday tracking requires valid GEX data. Refresh the symbol to start tracking.")

        else:
            st.info("👈 Enter a symbol and click Refresh to begin analysis")
    
    # Tab 2: Trade Setups - USES SAME LOGIC AS TRADING PLAN
    with tabs[1]:
        st.subheader("🎯 Trading Setups - Profit Opportunities")

        if st.session_state.current_data:
            try:
                # Use TradingPlanGenerator to get setups with same logic as Trading Plan
                plan_generator = TradingPlanGenerator()
                gex_data = st.session_state.current_data.get('gex', {})

                # Extract market data
                symbol = st.session_state.current_data.get('symbol', 'SPY')
                spot = gex_data.get('spot_price', 0)
                net_gex = gex_data.get('net_gex', 0)
                flip = gex_data.get('flip_point', 0)
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)

                # Calculate regime (same as Trading Plan)
                regime = plan_generator._calculate_regime_from_gex(net_gex, spot, flip, call_wall, put_wall)

                # Get current day
                import pytz
                central = pytz.timezone('US/Central')
                now = datetime.now(central)
                day = now.strftime('%A')

                # Generate setups using same method as Trading Plan
                setups = plan_generator._generate_all_setups(symbol, spot, net_gex, flip, call_wall, put_wall, day, regime)

                if setups:
                    # Display market context first
                    st.info(f"**Market Regime:** {regime.get('type', 'N/A')} | **Net GEX:** {regime.get('net_gex_billions', 'N/A')} | **MM Behavior:** {regime.get('mm_behavior', 'N/A')}")

                    # Display each setup in blog/narrative format
                    for i, trade in enumerate(setups, 1):
                        conf = trade.get('confidence', 0)
                        stars = '⭐' * (conf // 20)

                        with st.expander(
                            f"{stars} Setup #{i}: {trade.get('strategy', 'Unknown')} ({conf}% Confidence)",
                            expanded=True
                        ):
                            # Start with WHY - the reasoning
                            st.markdown(f"**{trade.get('reasoning', 'Strong setup based on current market conditions.')}**")
                            st.markdown("---")

                            # The Play
                            st.markdown(f"**The Play:** {trade.get('action', 'N/A')}. Target the {trade.get('strikes', 'N/A')} strikes with {trade.get('expiration', 'N/A')} expiration.")

                            if trade.get('win_rate'):
                                st.markdown(f"*This setup has a {trade.get('win_rate')} win rate based on historical data.*")

                            # Entry Strategy
                            entry_value = trade.get('entry', trade.get('entry_zone', 'N/A'))
                            st.markdown(f"**Entry Strategy:** Look to enter around {entry_value}.")

                            # Profit Targets
                            if 'target_1' in trade:
                                profit_text = f"**Profit Targets:** First target is {trade.get('target_1', 'N/A')}"
                                if 'target_2' in trade:
                                    profit_text += f", with an extended target at {trade.get('target_2', 'N/A')}. Consider scaling out at each target to lock in profits."
                                else:
                                    profit_text += ". Consider taking profits at this level."
                                st.markdown(profit_text)
                            elif 'max_profit' in trade:
                                st.markdown(f"**Maximum Profit Potential:** {trade.get('max_profit', 'N/A')}.")
                                if 'credit' in trade:
                                    st.markdown(f"You'll collect {trade.get('credit', 'N/A')} in credit when you enter this trade.")

                            # Risk Management
                            risk_text = "**Risk Management:** "
                            if 'stop' in trade:
                                risk_text += f"Set your stop loss at {trade.get('stop', 'N/A')}. "
                            if 'max_risk' in trade:
                                risk_text += f"Your maximum risk on this trade is {trade.get('max_risk', 'N/A')}. "

                            size_value = trade.get('size', '2-3% of capital')
                            risk_text += f"Position size should be {size_value} to maintain proper risk management."
                            st.markdown(risk_text)

                            # Position Sizing Calculator
                            st.markdown("---")
                            account_size = st.session_state.get('account_size', 50000)
                            risk_pct = st.session_state.get('risk_per_trade', 2.0)

                            # Add option premium to trade dict if not present (default estimate)
                            if 'option_premium' not in trade:
                                trade['option_premium'] = 2.50

                            display_position_sizing(trade, account_size, risk_pct)

                            # Why This Works
                            win_rate_value = trade.get('win_rate', '')
                            if win_rate_value:
                                reasoning = trade.get('reasoning', '').lower()
                                why_text = f"**Why This Works:** This is a {win_rate_value} win rate setup because "

                                if 'negative gex' in reasoning or 'short gamma' in reasoning:
                                    why_text += "when dealers are short gamma (negative GEX), they're forced to buy rallies to hedge, creating upward momentum that pushes prices higher."
                                elif 'positive gex' in reasoning or 'range' in reasoning:
                                    why_text += "high positive GEX creates a volatility-suppressed environment where market makers defend their key levels, making range-bound strategies highly profitable."
                                elif 'wall' in reasoning:
                                    why_text += "gamma walls represent massive positioning by market makers who will defend these levels, creating strong support or resistance zones."
                                elif 'theta' in reasoning or 'premium' in reasoning:
                                    why_text += "time decay works in your favor, allowing you to collect premium while staying protected within defined risk parameters."
                                else:
                                    why_text += "the market structure creates favorable risk/reward dynamics for this strategy."

                                st.markdown(why_text)

                            # Trade execution button
                            if st.button(f"Execute {trade.get('strategy')}", key=f"exec_setup_{i}"):
                                conn = sqlite3.connect(DB_PATH)
                                c = conn.cursor()

                                claude = ClaudeIntelligence()
                                c.execute('''
                                    INSERT INTO recommendations
                                    (symbol, strategy, confidence, entry_price, reasoning, mm_behavior)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                ''', (
                                    symbol,
                                    trade.get('strategy', 'Unknown'),
                                    conf,
                                    spot,
                                    trade.get('reasoning', 'N/A'),
                                    regime.get('mm_behavior', 'N/A')
                                ))

                                conn.commit()
                                conn.close()

                                st.success(f"✅ {trade.get('strategy')} logged to positions!")
                else:
                    st.warning("No high-confidence setups available (all setups below 50% confidence threshold)")
            except Exception as e:
                st.error(f"⚠️ Error generating setups: {str(e)}")
                st.info("💡 Trading setups work best with high-volume symbols like SPY, QQQ, TSLA, AAPL")
        else:
            st.info("👈 Enter a symbol and click Refresh to see available setups")

    # Tab 3: Multi-Symbol Scanner
    with tabs[2]:
        st.subheader("🔍 Multi-Symbol Scanner")
        st.markdown("**Find the best trading opportunities across your watchlist**")

        # Watchlist Manager
        watchlist = display_watchlist_manager()

        st.divider()

        # Scan controls
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"💡 Ready to scan {len(watchlist)} symbols from your watchlist")
        with col2:
            force_refresh = st.checkbox("Force Refresh", help="Bypass cache and fetch fresh data")

        # Scan button
        if st.button("🔍 Scan Watchlist", type="primary", use_container_width=True):
            with st.spinner(f"Scanning {len(watchlist)} symbols..."):
                try:
                    scan_results = scan_symbols(
                        watchlist,
                        st.session_state.api_client,
                        force_refresh=force_refresh
                    )
                    st.session_state.scan_results = scan_results
                except Exception as e:
                    st.error(f"❌ Error scanning symbols: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())

        # Display results
        if 'scan_results' in st.session_state and not st.session_state.scan_results.empty:
            display_scanner_dashboard(st.session_state.scan_results)
        else:
            st.info("👆 Click 'Scan Watchlist' to find trading opportunities")

    # Tab 4: Alerts
    with tabs[3]:
        display_alert_dashboard()

    # Tab 5: Trading Plans
    with tabs[4]:
        st.subheader("📅 Comprehensive Trading Plans")
        
        # Plan type selector
        plan_col1, plan_col2, plan_col3, plan_col4 = st.columns(4)
        
        with plan_col1:
            plan_symbol = st.text_input("Symbol for Plan", value=symbol if 'symbol' in locals() else "SPY")
        
        with plan_col2:
            plan_type = st.selectbox(
                "Plan Type",
                ["Daily", "Weekly", "Monthly"],
                index=0
            )
        
        with plan_col3:
            if st.button("🔄 Generate Plan", type="primary", use_container_width=True):
                with st.spinner(f"Generating {plan_type.lower()} plan..."):
                    # Fetch latest data for symbol
                    plan_data = st.session_state.api_client.get_net_gamma(plan_symbol)
                    st.session_state.generated_plan = {
                        'type': plan_type,
                        'data': plan_data,
                        'symbol': plan_symbol
                    }
        
        with plan_col4:
            if st.button("💾 Export Plan", use_container_width=True):
                if 'generated_plan' in st.session_state:
                    st.download_button(
                        label="Download Plan",
                        data=json.dumps(st.session_state.generated_plan, indent=2),
                        file_name=f"{plan_symbol}_{plan_type}_plan.json",
                        mime="application/json"
                    )
        
        # Display generated plan
        if 'generated_plan' in st.session_state:
            plan_generator = TradingPlanGenerator()
            plan_data = st.session_state.generated_plan['data']

            try:
                if st.session_state.generated_plan['type'] == 'Daily':
                    daily_plan = plan_generator.generate_daily_plan(
                        st.session_state.generated_plan['symbol'],
                        plan_data
                    )
                    # Display formatted markdown instead of JSON
                    formatted_plan = plan_generator.format_daily_plan_markdown(daily_plan)
                    st.markdown(formatted_plan)

                elif st.session_state.generated_plan['type'] == 'Weekly':
                    weekly_plan = plan_generator.generate_weekly_plan(
                        st.session_state.generated_plan['symbol'],
                        plan_data
                    )
                    # Display formatted markdown instead of JSON
                    formatted_plan = plan_generator.format_weekly_plan_markdown(weekly_plan)
                    st.markdown(formatted_plan)

                elif st.session_state.generated_plan['type'] == 'Monthly':
                    monthly_plan = plan_generator.generate_monthly_plan(
                        st.session_state.generated_plan['symbol'],
                        plan_data
                    )
                    # Display formatted markdown instead of JSON
                    formatted_plan = plan_generator.format_monthly_plan_markdown(monthly_plan)
                    st.markdown(formatted_plan)
            except Exception as e:
                st.error(f"⚠️ Error generating plan: {str(e)}")
                st.info("💡 Trading plans work best with high-volume symbols like SPY, QQQ, TSLA, AAPL")
        else:
            st.info("👈 Enter a symbol and click 'Generate Plan' to create a comprehensive trading plan")

    # Tab 6: AI Co-Pilot
    with tabs[5]:
        st.subheader("💬 Intelligent Trading Co-Pilot")

        # Mode selection buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📊 Analyze Market", use_container_width=True):
                prompt = "Analyze current market conditions and tell me the best trade setup right now with specific strikes, entry price, targets, and stop loss. Include why this trade makes money based on MM positioning."
                st.session_state.conversation_history.append({
                    "role": "user",
                    "content": prompt
                })
                with st.spinner("🔍 Deep market analysis in progress..."):
                    response = st.session_state.claude_ai.analyze_market(
                        st.session_state.current_data.get('gex', {}),
                        prompt
                    )
                st.session_state.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
                st.rerun()

        with col2:
            if st.button("🥊 Challenge My Idea", use_container_width=True):
                # Set up challenge mode
                st.session_state['challenge_mode'] = True
                st.info("💡 Challenge Mode Active: Enter your trade idea and I'll critically analyze it, push back on weaknesses, and suggest better alternatives.")

        with col3:
            if st.button("📚 Teach Me", use_container_width=True):
                prompt = "Teach me about gamma exposure and market maker positioning. Explain how I can use this to make profitable trades. Include real examples from current market conditions."
                st.session_state.conversation_history.append({
                    "role": "user",
                    "content": prompt
                })
                with st.spinner("📖 Preparing educational content..."):
                    response = st.session_state.claude_ai.teach_concept(
                        st.session_state.current_data.get('gex', {}),
                        prompt
                    )
                st.session_state.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
                st.rerun()

        # Display conversation history
        for msg in st.session_state.conversation_history[-10:]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Chat input with intelligent routing
        if prompt := st.chat_input("Ask about gamma, market makers, or trading strategies..."):
            # Add to history
            st.session_state.conversation_history.append({
                "role": "user",
                "content": prompt
            })

            # Determine mode based on content and context
            with st.spinner("🤖 Thinking deeply..."):
                # Check if in challenge mode or if question is a challenge
                challenge_keywords = ["challenge", "wrong", "disagree", "bad idea", "risky", "why not", "what if i"]
                teach_keywords = ["teach", "explain", "how does", "what is", "help me understand", "why"]

                if st.session_state.get('challenge_mode') or any(kw in prompt.lower() for kw in challenge_keywords):
                    # Challenge mode - be critical and push back
                    st.session_state['challenge_mode'] = False  # Reset after use
                    response = st.session_state.claude_ai.challenge_trade_idea(
                        prompt,
                        st.session_state.current_data.get('gex', {})
                    )
                elif any(kw in prompt.lower() for kw in teach_keywords):
                    # Educational mode
                    response = st.session_state.claude_ai.teach_concept(
                        st.session_state.current_data.get('gex', {}),
                        prompt
                    )
                else:
                    # Analysis mode - provide specific trades
                    response = st.session_state.claude_ai.analyze_market(
                        st.session_state.current_data.get('gex', {}),
                        prompt
                    )

            # Add response to history
            st.session_state.conversation_history.append({
                "role": "assistant",
                "content": response
            })

            st.rerun()
        
        # Quick prompts
        st.divider()
        st.caption("Quick Prompts:")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💰 Best Trade Now", use_container_width=True):
                prompt = "Give me the highest probability trade right now with exact strikes, entry, targets, and stop. Show me the math on why this makes money."
                st.session_state.conversation_history.append({"role": "user", "content": prompt})
                with st.spinner("Analyzing..."):
                    response = st.session_state.claude_ai.analyze_market(
                        st.session_state.current_data.get('gex', {}),
                        prompt
                    )
                st.session_state.conversation_history.append({"role": "assistant", "content": response})
                st.rerun()

        with col2:
            if st.button("🎯 Risk Analysis", use_container_width=True):
                prompt = "What are the biggest risks in the market right now? Where could I get trapped? What's the worst-case scenario?"
                st.session_state.conversation_history.append({"role": "user", "content": prompt})
                with st.spinner("Analyzing risks..."):
                    response = st.session_state.claude_ai.challenge_trade_idea(
                        prompt,
                        st.session_state.current_data.get('gex', {})
                    )
                st.session_state.conversation_history.append({"role": "assistant", "content": response})
                st.rerun()

        with col3:
            if st.button("📖 Explain Current Setup", use_container_width=True):
                prompt = "Explain what's happening in the market right now in terms of gamma positioning. Why are MMs acting this way? What does it mean for my trading?"
                st.session_state.conversation_history.append({"role": "user", "content": prompt})
                with st.spinner("Preparing explanation..."):
                    response = st.session_state.claude_ai.teach_concept(
                        st.session_state.current_data.get('gex', {}),
                        prompt
                    )
                st.session_state.conversation_history.append({"role": "assistant", "content": response})
                st.rerun()

        # Advanced Features Section
        st.divider()
        st.subheader("🚀 Advanced Trading Tools")

        # Create tabs for advanced features
        adv_tab1, adv_tab2, adv_tab3, adv_tab4 = st.tabs([
            "📊 Scenario Planning",
            "🎯 Portfolio Risk",
            "📚 Trade Post-Mortem",
            "🎲 Monte Carlo"
        ])

        # TAB 1: SCENARIO PLANNING
        with adv_tab1:
            st.markdown("### 📊 What-If Scenario Analysis")
            st.caption("Analyze how your position performs under different market conditions")

            # Get active positions or create example
            if st.session_state.active_positions:
                pos_options = [f"{p.get('symbol', 'N/A')} {p.get('type', 'N/A')} {p.get('strike', 'N/A')}"
                              for p in st.session_state.active_positions]
                selected_pos_idx = st.selectbox("Select Position", range(len(pos_options)), format_func=lambda x: pos_options[x])
                current_position = st.session_state.active_positions[selected_pos_idx]
            else:
                st.info("💡 No active positions. Using example position for demonstration.")
                current_position = {
                    'symbol': 'SPY',
                    'type': 'call',
                    'strike': 585,
                    'entry_price': 4.50,
                    'contracts': 7,
                    'delta': 0.45,
                    'theta': -0.12,
                    'current_price': 582.50
                }

            # Scenario inputs
            col1, col2, col3 = st.columns(3)
            with col1:
                price_change = st.slider("Stock Price Change (%)", -10.0, 10.0, -2.0, 0.5)
            with col2:
                days_forward = st.slider("Days Forward", 1, 7, 1)
            with col3:
                iv_change = st.slider("IV Change (%)", -50.0, 50.0, 0.0, 5.0)

            if st.button("🔮 Run Scenario", use_container_width=True):
                scenario = {
                    'name': f"{price_change:+.1f}% move in {days_forward} days",
                    'price_change_pct': price_change,
                    'days_forward': days_forward,
                    'iv_change_pct': iv_change
                }

                from intelligence_and_strategies import ScenarioPlanner
                planner = ScenarioPlanner()
                result = planner.analyze_scenario(current_position, scenario)

                # Display results with visual indicators
                st.markdown("---")
                st.markdown(f"### 📊 Scenario: **{result['scenario_name']}**")

                metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                with metric_col1:
                    st.metric("Stock Price", f"${result['new_stock_price']:.2f}",
                             delta=f"{result['stock_move_pct']:+.1f}%")
                with metric_col2:
                    st.metric("Option Price", f"${result['estimated_option_price']:.2f}")
                with metric_col3:
                    pnl_color = "normal" if result['total_pnl'] >= 0 else "inverse"
                    st.metric("Total P/L", f"${result['total_pnl']:,.0f}",
                             delta=f"{result['pnl_pct']:+.1f}%", delta_color=pnl_color)
                with metric_col4:
                    st.metric("Days Elapsed", f"{result['days_elapsed']}")

                # Recommendation with color coding
                if "TAKE PROFITS" in result['recommendation']:
                    st.success(f"✅ {result['recommendation']}")
                elif "CUT LOSS" in result['recommendation']:
                    st.error(f"🛑 {result['recommendation']}")
                elif "at risk" in result['recommendation'].lower():
                    st.warning(f"⚠️ {result['recommendation']}")
                else:
                    st.info(f"📊 {result['recommendation']}")

                # Interpretation guide
                with st.expander("📖 How to Interpret This"):
                    st.markdown("""
                    **Understanding the Scenario Analysis:**

                    - **Stock Price**: Where the stock would be after the move
                    - **Option Price**: Estimated option value using delta/theta
                    - **Total P/L**: Your actual profit/loss in dollars
                    - **Days Elapsed**: Theta decay impact over time

                    **Action Recommendations:**
                    - 🎯 **Take Profits**: 50%+ gain - lock it in!
                    - ✅ **Scale Out**: 30%+ gain - take some off
                    - 📊 **Hold**: Still profitable, let it run
                    - ⚠️ **Monitor**: Breaking even or small loss
                    - 🛑 **Cut Loss**: -50% or worse - exit now

                    **Pro Tip**: Run multiple scenarios to understand your risk/reward range
                    before entering a trade!
                    """)

        # TAB 2: PORTFOLIO RISK ANALYSIS
        with adv_tab2:
            st.markdown("### 🎯 Portfolio Risk & Correlation Analysis")
            st.caption("Identify concentration risk and correlated positions")

            if st.button("🔍 Analyze Portfolio", use_container_width=True):
                from intelligence_and_strategies import PortfolioAnalyzer
                analyzer = PortfolioAnalyzer()

                # Analyze portfolio
                analysis = analyzer.analyze_portfolio(st.session_state.active_positions)

                if analysis['status'] == 'empty':
                    st.info("📭 No active positions to analyze. Add positions to see portfolio risk.")
                else:
                    # Display key metrics
                    metric_col1, metric_col2, metric_col3 = st.columns(3)
                    with metric_col1:
                        st.metric("Total Positions", analysis['total_positions'])
                    with metric_col2:
                        st.metric("Total Risk", f"${analysis['total_risk']:,.0f}")
                    with metric_col3:
                        st.metric("Unique Symbols", len(analysis['symbol_counts']))

                    # Diversification score
                    st.markdown(f"**Diversification Score**: {analysis['diversification_score']}")

                    # Warnings
                    if analysis['warnings']:
                        st.markdown("### ⚠️ Risk Warnings:")
                        for warning in analysis['warnings']:
                            if warning['severity'] == 'high':
                                st.error(warning['message'])
                            elif warning['severity'] == 'medium':
                                st.warning(warning['message'])
                            else:
                                st.info(warning['message'])
                    else:
                        st.success("✅ No major concentration risks detected!")

                    # Breakdown visualizations
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**📊 Sector Exposure**")
                        sector_data = analysis['sector_exposure']
                        for sector, count in sector_data.items():
                            if count > 0:
                                st.progress(count / analysis['total_positions'],
                                           text=f"{sector.upper()}: {count} positions")

                    with col2:
                        st.markdown("**📈 Directional Bias**")
                        bias_data = analysis['directional_bias']
                        for direction, count in bias_data.items():
                            if count > 0:
                                st.progress(count / analysis['total_positions'],
                                           text=f"{direction.upper()}: {count} positions")

                    # Interpretation guide
                    with st.expander("📖 How to Read Portfolio Risk"):
                        st.markdown("""
                        **Portfolio Risk Indicators:**

                        🚨 **HIGH SEVERITY** - Take action immediately:
                        - 3+ positions in same symbol = Overconcentration
                        - 4+ tech positions = Sector correlation risk
                        - Total risk >$10K = Too much exposure

                        ⚠️ **MEDIUM SEVERITY** - Monitor closely:
                        - 3+ market ETF positions = Index correlation
                        - 75%+ bullish/bearish = One-sided risk

                        **Diversification Scores:**
                        - 🌟 **EXCELLENT**: 80%+ different symbols
                        - ✅ **GOOD**: 50-80% different symbols
                        - ⚠️ **MODERATE**: 30-50% different symbols
                        - 🚨 **POOR**: <30% different symbols

                        **Why This Matters:**
                        Correlated positions = Correlated losses. If tech sells off and you have
                        5 tech positions, they ALL lose together. Diversification protects you.
                        """)

        # TAB 3: TRADE POST-MORTEM
        with adv_tab3:
            st.markdown("### 📚 Trade Post-Mortem Analysis")
            st.caption("Learn from your closed trades - what went right/wrong?")

            # Manual entry for demonstration
            with st.expander("➕ Enter Closed Trade Details"):
                col1, col2 = st.columns(2)
                with col1:
                    trade_symbol = st.text_input("Symbol", "SPY", key="pm_symbol")
                    trade_strategy = st.selectbox("Strategy", ["Call", "Put", "Iron Condor", "Call Spread"], key="pm_strategy")
                    entry_price = st.number_input("Entry Price", 4.50, key="pm_entry")
                    exit_price = st.number_input("Exit Price", 2.50, key="pm_exit")

                with col2:
                    day_entered = st.selectbox("Day Entered", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], key="pm_day")
                    hold_days = st.number_input("Days Held", 1, 7, 3, key="pm_days")
                    entry_gex = st.number_input("Entry GEX (Billions)", -5.0, 5.0, 1.5, 0.1, key="pm_gex") * 1e9
                    exit_reason = st.text_input("Exit Reason", "Target hit", key="pm_reason")

            if st.button("🔍 Analyze Trade", use_container_width=True):
                pnl = (exit_price - entry_price) * 100  # Per contract

                trade_data = {
                    'symbol': trade_symbol,
                    'strategy': trade_strategy,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'entry_gex': entry_gex,
                    'exit_reason': exit_reason,
                    'hold_time_days': hold_days,
                    'day_entered': day_entered
                }

                from intelligence_and_strategies import PostMortemAnalyzer
                analyzer = PostMortemAnalyzer()
                lessons = analyzer.analyze_trade(trade_data)

                # Display grade prominently
                st.markdown(f"## Trade Grade: **{lessons['grade']}**")

                # P/L metrics
                pnl_col1, pnl_col2 = st.columns(2)
                with pnl_col1:
                    st.metric("P/L", f"${lessons['pnl']:.2f}", delta=f"{lessons['pnl_pct']:.1f}%")
                with pnl_col2:
                    result_emoji = "✅" if lessons['pnl'] > 0 else "❌"
                    st.metric("Result", f"{result_emoji} {lessons['trade_summary']}")

                # What went right
                if lessons['what_went_right']:
                    st.success("### ✅ What Went RIGHT:")
                    for item in lessons['what_went_right']:
                        st.markdown(f"- {item}")

                # What went wrong
                if lessons['what_went_wrong']:
                    st.error("### ❌ What Went WRONG:")
                    for item in lessons['what_went_wrong']:
                        st.markdown(f"- {item}")

                # Key lessons
                st.info("### 📚 Key Lessons:")
                for lesson in lessons['key_lessons']:
                    st.markdown(f"**{lesson}**")

                # Interpretation guide
                with st.expander("📖 Understanding Trade Grades"):
                    st.markdown("""
                    **Grade Meanings:**

                    - **A**: Excellent execution - You did everything right
                      - Good timing, proper GEX alignment, quick exit
                      - Keep doing exactly this!

                    - **B**: Profitable but could improve
                      - Made money but missed some best practices
                      - Review what could have been better

                    - **D**: Small mistake or bad luck
                      - Lost money but only one major error
                      - Learn the lesson and move on

                    - **F**: Multiple mistakes - review needed
                      - Several errors compounded the loss
                      - Study the rules before next trade

                    **Common Mistakes to Avoid:**
                    - ❌ Buying calls when MMs defending (GEX > $2B)
                    - ❌ Buying puts when MMs trapped (GEX < -$1B)
                    - ❌ Holding directionals past Wednesday 3PM
                    - ❌ Long options on Thursday/Friday (theta trap)
                    - ❌ Holding 4+ days (theta decay kills profits)
                    """)

        # TAB 4: MONTE CARLO SIMULATION
        with adv_tab4:
            st.markdown("### 🎲 Monte Carlo Probability Simulation")
            st.caption("Run 10,000 simulations to see probability distribution of outcomes")

            # Simulation inputs
            col1, col2, col3 = st.columns(3)
            with col1:
                mc_current_price = st.number_input("Current Price", 580.0, 600.0, 582.5, 0.5, key="mc_price")
                mc_strike = st.number_input("Strike Price", 570.0, 600.0, 585.0, 1.0, key="mc_strike")

            with col2:
                mc_volatility = st.slider("Expected Volatility (%)", 10, 50, 20, 1, key="mc_vol")
                mc_days = st.slider("Days to Expiration", 1, 30, 7, 1, key="mc_days")

            with col3:
                mc_simulations = st.select_slider("Simulations", [1000, 5000, 10000], 10000, key="mc_sims")

            if st.button("🎲 Run Monte Carlo", use_container_width=True):
                with st.spinner(f"Running {mc_simulations:,} simulations..."):
                    import numpy as np
                    import plotly.graph_objects as go

                    # Monte Carlo simulation
                    dt = mc_days / 365
                    volatility = mc_volatility / 100

                    # Generate random price paths
                    np.random.seed(42)
                    returns = np.random.normal(0, volatility * np.sqrt(dt), mc_simulations)
                    final_prices = mc_current_price * np.exp(returns)

                    # Calculate probabilities
                    prob_above_strike = (final_prices > mc_strike).mean() * 100
                    prob_below_strike = (final_prices < mc_strike).mean() * 100
                    prob_at_strike = (np.abs(final_prices - mc_strike) < 1).mean() * 100

                    # Calculate statistics
                    mean_price = final_prices.mean()
                    std_price = final_prices.std()
                    percentile_5 = np.percentile(final_prices, 5)
                    percentile_95 = np.percentile(final_prices, 95)

                    # Display probabilities
                    st.markdown("### 📊 Simulation Results")
                    prob_col1, prob_col2, prob_col3 = st.columns(3)
                    with prob_col1:
                        st.metric("Prob Above Strike", f"{prob_above_strike:.1f}%",
                                 help="Probability price finishes above strike")
                    with prob_col2:
                        st.metric("Prob Below Strike", f"{prob_below_strike:.1f}%",
                                 help="Probability price finishes below strike")
                    with prob_col3:
                        st.metric("Expected Price", f"${mean_price:.2f}",
                                 help="Average price across all simulations")

                    # Price distribution chart
                    fig = go.Figure()

                    # Histogram of outcomes
                    fig.add_trace(go.Histogram(
                        x=final_prices,
                        nbinsx=50,
                        name='Price Distribution',
                        marker_color='lightblue',
                        opacity=0.7
                    ))

                    # Add strike line
                    fig.add_vline(x=mc_strike, line_dash="dash", line_color="red",
                                 annotation_text=f"Strike ${mc_strike:.0f}")

                    # Add current price line
                    fig.add_vline(x=mc_current_price, line_dash="dash", line_color="green",
                                 annotation_text=f"Current ${mc_current_price:.2f}")

                    fig.update_layout(
                        title=f"Monte Carlo: {mc_simulations:,} Simulations - {mc_days} Days",
                        xaxis_title="Final Stock Price",
                        yaxis_title="Frequency",
                        height=400,
                        showlegend=False
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    # Statistics table
                    st.markdown("### 📈 Statistical Summary")
                    stat_col1, stat_col2 = st.columns(2)
                    with stat_col1:
                        st.metric("5th Percentile", f"${percentile_5:.2f}", help="95% chance price above this")
                        st.metric("Mean Price", f"${mean_price:.2f}")
                    with stat_col2:
                        st.metric("95th Percentile", f"${percentile_95:.2f}", help="95% chance price below this")
                        st.metric("Std Deviation", f"${std_price:.2f}")

                    # Trading implications
                    st.markdown("### 💡 Trading Implications")
                    if prob_above_strike > 60:
                        st.success(f"✅ **BULLISH SETUP**: {prob_above_strike:.1f}% chance of finishing above ${mc_strike:.0f}")
                        st.markdown("- **Consider**: Buying calls at this strike")
                        st.markdown(f"- **Confidence**: High ({prob_above_strike:.0f}%)")
                    elif prob_below_strike > 60:
                        st.error(f"🔻 **BEARISH SETUP**: {prob_below_strike:.1f}% chance of finishing below ${mc_strike:.0f}")
                        st.markdown("- **Consider**: Buying puts at this strike")
                        st.markdown(f"- **Confidence**: High ({prob_below_strike:.0f}%)")
                    else:
                        st.warning(f"⚠️ **NEUTRAL SETUP**: Probabilities near 50/50")
                        st.markdown("- **Consider**: Iron condors or theta strategies")
                        st.markdown("- **Confidence**: Low (choppy/uncertain)")

                    # Interpretation guide
                    with st.expander("📖 How to Interpret Monte Carlo Results"):
                        st.markdown("""
                        **What is Monte Carlo Simulation?**

                        Runs thousands of random price paths to estimate probability distributions.
                        Think of it as "rolling the dice" 10,000 times to see all possible outcomes.

                        **Key Metrics:**

                        - **Prob Above/Below Strike**: What % of simulations finished above/below your strike
                        - **Expected Price**: Average outcome across all simulations
                        - **5th/95th Percentile**: 90% confidence interval for final price

                        **How to Use This:**

                        1. **High Probability (>60%)**: Strong directional signal
                           - Buy options in that direction
                           - Higher confidence = larger position size

                        2. **Near 50/50**: Neutral/choppy market
                           - Sell premium (iron condors)
                           - Avoid directional bets

                        3. **Check Risk Range**: 5th to 95th percentile = likely price range
                           - Plan your strikes within this range
                           - Stops outside this range

                        **Pro Tip**: Combine with GEX analysis!
                        - Negative GEX + High prob above = Perfect long call setup
                        - Positive GEX + Near 50/50 = Perfect iron condor setup
                        """)


    # Tab 7: Autonomous Paper Trader
    with tabs[6]:
        display_autonomous_trader()

    # Tab 8: Positions & Tracking
    with tabs[7]:
        display_position_management()

    # Tab 9: Trade Journal - AI Performance Analysis
    with tabs[8]:
        journal_period = display_journal_settings()
        display_trade_journal(st.session_state.trade_journal_agent, days_back=journal_period)

    # Tab 10: Education
    with tabs[9]:
        display_education_content()

def display_position_management():
    """Display position management interface"""
    st.subheader("📊 Position Management")

    # Position Monitoring Agent
    display_position_monitoring(st.session_state.position_management_agent)

    st.divider()

    # Position Entry Form
    with st.expander("➕ Add New Position", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            pos_symbol = st.text_input("Symbol", value="SPY")
            pos_strategy = st.selectbox(
                "Strategy",
                ["SQUEEZE", "FADE", "IRON CONDOR", "PREMIUM SELL"]
            )
        
        with col2:
            pos_direction = st.selectbox("Direction", ["LONG", "SHORT"])
            pos_entry = st.number_input("Entry Price", value=100.0, step=0.01)
        
        with col3:
            pos_target = st.number_input("Target", value=105.0, step=0.01)
            pos_stop = st.number_input("Stop Loss", value=98.0, step=0.01)
        
        with col4:
            pos_size = st.number_input("Size ($)", value=1000.0, step=100.0)
            
            if st.button("Add Position", type="primary"):
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                
                c.execute('''
                    INSERT INTO positions 
                    (symbol, strategy, direction, entry_price, current_price, target, stop, size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pos_symbol, pos_strategy, pos_direction,
                    pos_entry, pos_entry, pos_target, pos_stop, pos_size
                ))
                
                conn.commit()
                conn.close()
                
                st.success("✅ Position added!")
                st.rerun()
    
    # Display Active Positions
    st.subheader("📈 Active Positions")
    
    conn = sqlite3.connect(DB_PATH)
    positions_df = pd.read_sql_query("""
        SELECT * FROM positions 
        WHERE status = 'ACTIVE'
        ORDER BY opened_at DESC
    """, conn)
    
    if not positions_df.empty:
        for idx, pos in positions_df.iterrows():
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                
                with col1:
                    current_pnl = (pos['current_price'] - pos['entry_price']) * pos['size'] / pos['entry_price']
                    if pos['direction'] == 'SHORT':
                        current_pnl = -current_pnl
                    
                    emoji = "🟢" if current_pnl > 0 else "🔴"
                    st.write(f"{emoji} **{pos['symbol']}** - {pos['strategy']}")
                    st.caption(f"{pos['direction']} @ ${pos['entry_price']:.2f}")
                
                with col2:
                    pnl_percent = (current_pnl / pos['size'] * 100) if pos['size'] > 0 else 0
                    st.metric(
                        "Current",
                        f"${pos['current_price']:.2f}",
                        delta=f"{pnl_percent:.1f}%"
                    )
                
                with col3:
                    st.metric("P&L", f"${current_pnl:.2f}")
                
                with col4:
                    st.caption(f"T: ${pos['target']:.2f}")
                    st.caption(f"S: ${pos['stop']:.2f}")
                
                with col5:
                    if st.button("Close", key=f"close_{pos['id']}"):
                        c = conn.cursor()
                        c.execute("""
                            UPDATE positions 
                            SET status = 'CLOSED',
                                closed_at = datetime('now'),
                                pnl = ?
                            WHERE id = ?
                        """, (current_pnl, pos['id']))
                        
                        conn.commit()
                        st.success("Position closed!")
                        st.rerun()
                
                st.divider()
    else:
        st.info("No active positions")
    
    # Trade History
    st.subheader("📜 Trade History")
    
    history_df = pd.read_sql_query("""
        SELECT 
            symbol,
            strategy,
            direction,
            entry_price,
            CAST(closed_at as DATE) as date,
            pnl,
            ROUND(pnl / size * 100, 1) as pnl_percent
        FROM positions 
        WHERE status = 'CLOSED'
        ORDER BY closed_at DESC
        LIMIT 20
    """, conn)
    
    if not history_df.empty:
        st.dataframe(
            history_df,
            use_container_width=True,
            hide_index=True
        )
        
        # Performance Summary
        total_pnl = history_df['pnl'].sum()
        win_rate = (history_df['pnl'] > 0).mean() * 100
        avg_win = history_df[history_df['pnl'] > 0]['pnl'].mean() if len(history_df[history_df['pnl'] > 0]) > 0 else 0
        avg_loss = history_df[history_df['pnl'] < 0]['pnl'].mean() if len(history_df[history_df['pnl'] < 0]) > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total P&L", f"${total_pnl:,.2f}")
        with col2:
            st.metric("Win Rate", f"{win_rate:.1f}%")
        with col3:
            st.metric("Avg Win", f"${avg_win:,.2f}")
        with col4:
            st.metric("Avg Loss", f"${avg_loss:,.2f}")
    
    conn.close()

def display_education_content():
    """Display educational content"""
    st.subheader("📚 GEX Trading Education")
    
    # Educational sections with expanders
    with st.expander("🎓 Understanding Gamma Exposure (GEX)", expanded=True):
        st.markdown("""
        ### What is GEX?
        
        **Gamma Exposure (GEX)** measures the aggregate gamma positioning of options market makers.
        It tells us how much market makers need to hedge for every 1% move in the underlying.
        
        **Formula:** `GEX = Spot Price × Gamma × Open Interest × Contract Multiplier`
        
        ### Key Concepts:
        
        **Positive GEX (> $1B)**
        - Market makers are **long gamma**
        - They **sell rallies** and **buy dips**
        - This **suppresses volatility**
        - Market tends to be **range-bound**
        
        **Negative GEX (< -$1B)**
        - Market makers are **short gamma**
        - They must **buy rallies** and **sell dips**
        - This **amplifies volatility**
        - Market tends to **trend strongly**
        
        **The Gamma Flip Point**
        - The price level where Net GEX crosses zero
        - **Above flip:** Positive gamma (suppression)
        - **Below flip:** Negative gamma (amplification)
        - **Most important level** for intraday trading
        """)
    
    with st.expander("🧠 Market Maker Psychology"):
        st.markdown("""
        ### MM Behavioral States
        
        **TRAPPED State (Net GEX < -$2B)**
        - MMs are massively short gamma
        - Any rally forces aggressive buying
        - Creates violent upside squeezes
        - **Your Edge:** Buy calls on flip break
        
        **DEFENDING State (Net GEX > $1B)**
        - MMs are comfortably long gamma
        - They defend their position aggressively
        - Sell every rally, buy every dip
        - **Your Edge:** Fade moves at extremes
        
        **PANICKING State (Net GEX < -$3B)**
        - MMs in full capitulation mode
        - Covering at any price
        - Trend days with no resistance
        - **Your Edge:** Maximum aggression
        """)
    
    with st.expander("📊 Trading Strategies"):
        st.markdown("""
        ### 1. Negative GEX Squeeze
        
        **Setup Requirements:**
        - Net GEX < -$1B
        - Price within 1.5% of flip point
        - Strong put wall support below
        
        **Entry:** Break above flip point with volume
        **Target 1:** Previous day high
        **Target 2:** Call wall
        **Stop:** Below put wall
        **Win Rate:** 68%
        
        ### 2. Positive GEX Fade
        
        **Setup Requirements:**
        - Net GEX > $2B
        - Price at call wall resistance
        - Recent rejection from level
        
        **Entry:** Sell call spreads at wall
        **Target:** 50% of credit
        **Stop:** Break above wall
        **Win Rate:** 65%
        
        ### 3. Iron Condor
        
        **Setup Requirements:**
        - Net GEX > $1B
        - Call and put walls > 3% apart
        - Low IV rank (< 50th percentile)
        
        **Entry:** Short strikes at walls
        **Wings:** 10 points beyond shorts
        **Target:** 50% of credit
        **Win Rate:** 72%
        """)
    
    with st.expander("⚠️ Risk Management"):
        st.markdown("""
        ### Position Sizing Rules
        
        **Squeeze Plays:** Max 3% of capital
        **Premium Selling:** Max 5% of capital
        **Iron Condors:** Size for max 2% loss
        
        ### The Wednesday 3 PM Rule
        
        **Why It Matters:**
        - Gamma decay accelerates exponentially
        - Theta becomes dominant force
        - Directional edge disappears
        
        **Action Required:**
        - Close ALL directional positions by 3 PM Wednesday
        - No exceptions, even if showing profit
        - Switch to theta strategies only
        
        ### Stop Loss Discipline
        
        **Directional Plays:** -50% max loss
        **Short Premium:** -100% max loss (defined risk)
        **Iron Condors:** Exit if short strike threatened
        """)

# ============================================================================
# RUN APPLICATION
# ============================================================================
if __name__ == "__main__":
    main()
