""")


# ============================================================================
# MAIN CONTENT (YOUR EXACT v4.0)
# ============================================================================
if st.session_state.setup_complete:
    
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        symbol = st.selectbox("Symbol", ["SPY", "QQQ", "SPX", "IWM"], index=0)
    with col2:
        account_size = st.number_input("Account Size ($)", value=50000, step=5000)
    with col3:
        if st.button("📊 Fetch GEX Data", type="primary"):
            with st.spinner(f"Fetching {symbol} GEX data..."):
                gex_data = fetch_gex_data(symbol, TV_USERNAME)
                
                if 'error' in gex_data:
                    st.error(f"❌ API Error: {gex_data['error']}")
                    st.info("💡 Check debug output above")
                else:
                    st.success(f"✅ Received GEX data for {symbol}")
                    levels = calculate_levels(gex_data)
                    
                    if levels:
                        st.session_state.current_gex_data = gex_data
                        st.session_state.current_levels = levels
                        st.success(f"🎯 {symbol} analysis ready!")
                        st.balloons()
                    else:
                        st.error("❌ Failed to calculate levels")
    
    if st.session_state.current_levels:
        levels = st.session_state.current_levels
        
        st.markdown("### 📊 Current GEX Profile")
        
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        
        with metric_col1:
            st.metric("Current Price", f"${levels['current_price']:.2f}")
        
        with metric_col2:
            net_gex_b = levels['net_gex'] / 1e9
            regime = "MOVE 📈" if net_gex_b < 0 else "CHOP 📊"
            st.metric(f"Net GEX ({regime})", f"${net_gex_b:.2f}B")
        
        with metric_col3:
            st.metric(
                "Gamma Flip",
                f"${levels['flip_point']:.2f}",
                f"{((levels['current_price'] - levels['flip_point'])/levels['current_price']*100):.2f}%"
            )
        
        with metric_col4:
            wall_distance = levels['call_wall'] - levels['put_wall']
            st.metric(
                "Wall Distance",
                f"${wall_distance:.2f}",
                f"{(wall_distance/levels['current_price']*100):.1f}%"
            )
        
        # YOUR EXACT 3 TABS
        tab1, tab2, tab3 = st.tabs(["📈 GEX Profile", "📊 Dashboard", "🎯 Setups"])
        
        with tab1:
            fig = create_gex_profile_chart(levels)
            st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            mag_calc = MagnitudeCalculator()
            magnitude = mag_calc.calculate_expected_move(
                levels['current_price'],
                levels['flip_point'],
                levels['call_wall'],
                levels['put_wall'],
                levels['net_gex']
            )
            
            timing_data = TimingIntelligence.is_wed_3pm_approaching()
            
            fig_dash = create_dashboard_metrics(levels, timing_data, magnitude)
            st.plotly_chart(fig_dash, use_container_width=True)
        
        with tab3:
            st.markdown("### 🎯 Detected Trading Setups")
            setups = detect_trading_setups(levels)
            
            if setups:
                for setup in setups:
                    with st.expander(f"{setup['type']} - {setup['confidence']}% Confidence"):
                        st.markdown(f"**Direction:** {setup['direction']}")
                        st.markdown(f"**Reason:** {setup['reason']}")
                        
                        if st.button(f"Analyze {setup['type']}", key=setup['type']):
                            prompt = f"Analyze this {setup['type']} setup on {symbol}. {setup['reason']}. Apply all 10 components."
                            st.session_state.pending_prompt = prompt
            else:
                st.info("No high-probability setups detected")
    
    st.markdown("---")
    
    # YOUR EXACT CHAT INTERFACE
    st.markdown("### 💬 Chat with Your Co-Pilot")
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    st.markdown("**Quick Actions:**")
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    
    with btn_col1:
        if st.button("🎯 Complete Analysis"):
            st.session_state.pending_prompt = f"Give me a complete {symbol} analysis with all 10 profitability components addressed"
    
    with btn_col2:
        if st.button("📅 This Week's Plan"):
            st.session_state.pending_prompt = "Give me this week's trading plan. When do I play directional? When Iron Condors?"
    
    with btn_col3:
        if st.button("⚠️ Risk Check"):
            st.session_state.pending_prompt = "Check all risk parameters. Is it safe to trade today?"
    
    if prompt := st.chat_input("Ask your co-pilot anything..."):
        st.session_state.pending_prompt = prompt
    
    if 'pending_prompt' in st.session_state:
        user_prompt = st.session_state.pending_prompt
        del st.session_state.pending_prompt
        
        st.session_state.messages.append({
            "role": "user",
            "content": user_prompt
        })
        
        with st.chat_message("user"):
            st.markdown(user_prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Analyzing with all 10 components..."):
                
                context = None
                if st.session_state.current_levels:
                    context = {
                        'symbol': symbol,
                        'current_price': st.session_state.current_levels['current_price'],
                        'net_gex': st.session_state.current_levels['net_gex'],
                        'flip_point': st.session_state.current_levels['flip_point'],
                        'call_wall': st.session_state.current_levels['call_wall'],
                        'put_wall': st.session_state.current_levels['put_wall'],
                        'day': datetime.now().strftime('%A'),
                        'time': datetime.now().strftime('%I:%M %p')
                    }
                
                response = call_claude_api(
                    st.session_state.messages,
                    CLAUDE_API_KEY,
                    context
                )
                
                st.markdown(response)
                
                # NEW v4.5: SMS alert for high-confidence setups
                if context and "YES ✅" in response and "Confidence: 8" in response:
                    if send_sms_alert(f"High-confidence {symbol} setup! Check AlphaGEX."):
                        st.success("📱 SMS alert sent!")
        
        st.session_state.messages.append({
            "role": "assistant",
            "content": response
        })
        
        st.rerun()

else:
    st.info("👆 Configure API credentials to get started")
    st.markdown("""
    ### 🚀 Setup:
    1. Get TradingVolatility username (you have: I-RWFNBLR2S1DP)
    2. Get Claude API key from console.anthropic.com
    3. Add to Streamlit secrets
    4. Restart app
    """)

# NEW v4.5: Footer with version info
st.markdown("---")
st.caption("v4.5 - Your v4.0 + Database + Black-Scholes + Statistics + SMS | Zero features removed")
