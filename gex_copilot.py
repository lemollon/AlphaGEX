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
    DynamicLevelCalculator
)

# Import visualization and planning classes
from visualization_and_plans import (
    GEXVisualizer,
    TradingPlanGenerator,
    StrategyEngine
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
        # US Central Time
        try:
            central = pytz.timezone('US/Central')
            central_time = datetime.now(central)
            current_time = central_time.strftime('%H:%M CT')
        except:
            utc_now = datetime.utcnow()
            central_time = utc_now - timedelta(hours=6)
            current_time = central_time.strftime('%H:%M CT')
        st.metric("Market Time", current_time)
    
    with col5:
        day = datetime.now().strftime('%A')
        day_quality = "🟢" if day in ['Monday', 'Tuesday'] else "🟡" if day == 'Wednesday' else "🔴"
        st.metric("Day Quality", f"{day_quality} {day}")
    
    # Sidebar Configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Symbol Selection
        st.subheader("📊 Symbol Analysis")
        
        col1, col2 = st.columns(2)
        with col1:
            symbol = st.text_input("Enter Symbol", value="SPY")
        with col2:
            if st.button("🔄 Refresh", type="primary", use_container_width=True):
                with st.spinner("Fetching latest data..."):
                    # Fetch all data
                    gex_data = st.session_state.api_client.get_net_gamma(symbol)
                    profile_data = st.session_state.api_client.get_gex_profile(symbol)
                    
                    # Store in session
                    st.session_state.current_data = {
                        'symbol': symbol,
                        'gex': gex_data,
                        'profile': profile_data,
                        'timestamp': datetime.now()
                    }
                    
                    st.success("✅ Data refreshed!")
        
        # Quick symbols
        st.caption("Quick Select:")
        cols = st.columns(4)
        for i, sym in enumerate(['SPY', 'QQQ', 'IWM', 'DIA']):
            with cols[i]:
                if st.button(sym, use_container_width=True):
                    symbol = sym
                    st.rerun()
        
        st.divider()
        
        # Current Analysis Display
        if st.session_state.current_data:
            data = st.session_state.current_data.get('gex', {})
            
            st.subheader("📈 Current Analysis")
            
            # Net GEX
            net_gex = data.get('net_gex', 0)
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
            
            # Key Levels
            st.subheader("📍 Key Levels")
            
            spot = data.get('spot_price', 0)
            flip = data.get('flip_point', 0)
            
            st.metric("Current Price", f"${spot:.2f}")
            st.metric(
                "Flip Point",
                f"${flip:.2f}",
                delta=f"{((flip-spot)/spot*100):+.1f}%" if spot != 0 else "N/A"
            )
            st.metric("Call Wall", f"${data.get('call_wall', 0):.2f}")
            st.metric("Put Wall", f"${data.get('put_wall', 0):.2f}")
        
        st.divider()
        
        # Performance Stats
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
        "📅 Trading Plans",
        "💬 AI Co-Pilot",
        "📊 Positions",
        "📚 Education"
    ])
    
    # Tab 1: GEX Analysis
    with tabs[0]:
        if st.session_state.current_data:
            data = st.session_state.current_data
            
            # Display GEX Profile Chart
            if data.get('profile'):
                visualizer = GEXVisualizer()
                fig = visualizer.create_gex_profile(data['profile'])
                st.plotly_chart(fig, use_container_width=True)
            
            # Display Game Plan
            st.subheader("📋 Today's Game Plan")
            
            # Detect setups
            strategy_engine = StrategyEngine()
            setups = strategy_engine.detect_setups(data.get('gex', {}))
            
            # Generate plan
            game_plan = strategy_engine.generate_game_plan(data.get('gex', {}), setups)
            st.markdown(game_plan)
            
            # Monte Carlo Analysis
            if setups and st.button("🎲 Run Monte Carlo Simulation"):
                with st.spinner("Running 10,000 simulations..."):
                    setup = setups[0]
                    
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
                                st.markdown(f"**Profit Targets:** First target is {trade.get('target_1', 'N/A')}", end="")
                                if 'target_2' in trade:
                                    st.markdown(f", with an extended target at {trade.get('target_2', 'N/A')}. Consider scaling out at each target to lock in profits.")
                                else:
                                    st.markdown(". Consider taking profits at this level.")
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
    
    # Tab 3: Trading Plans
    with tabs[2]:
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
    
    # Tab 4: AI Co-Pilot
    with tabs[3]:
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
    
    # Tab 5: Positions & Tracking
    with tabs[4]:
        display_position_management()
    
    # Tab 6: Education
    with tabs[5]:
        display_education_content()

def display_position_management():
    """Display position management interface"""
    st.subheader("📊 Position Management")
    
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
