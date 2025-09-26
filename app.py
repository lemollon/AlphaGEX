#!/usr/bin/env python3
"""
AlphaGEX - Professional Gamma Exposure Trading Platform
========================================================
Complete market maker exploitation system using gamma exposure analysis.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
from datetime import datetime, timedelta
import time
import json
from typing import Dict, List, Optional

# Import configuration and core modules
from config import (
    APP_TITLE, APP_ICON, HIGH_PRIORITY_SYMBOLS, MEDIUM_PRIORITY_SYMBOLS,
    GEX_THRESHOLDS, RISK_LIMITS, COLORS, STREAMLIT_CONFIG
)
from core.logger import logger, log_error, log_info, log_warning, log_success
from core.api_client import TradingVolatilityAPI, test_api_connection
from core.behavioral_engine import BehavioralEngine
from core.visual_analyzer import VisualIntelligenceCoordinator

# Page configuration
st.set_page_config(
    page_title="🎯 AlphaGEX - Gamma Exposure Trading Platform",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: #00ff00;
        text-shadow: 2px 2px 4px rgba(0,255,0,0.3);
        margin-bottom: 1rem;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #1e3c72, #2a5298);
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #00ff00;
        margin: 0.5rem 0;
    }
    
    .status-connected {
        color: #00ff00;
        font-weight: bold;
    }
    
    .status-error {
        color: #ff4444;
        font-weight: bold;
    }
    
    .gex-positive {
        background-color: rgba(255, 99, 132, 0.1);
        border-left: 4px solid #ff6384;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .gex-negative {
        background-color: rgba(54, 162, 235, 0.1);
        border-left: 4px solid #36a2eb;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .signal-box {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border: 1px solid #00ff00;
    }
</style>
""", unsafe_allow_html=True)

class AlphaGEXApp:
    """Main AlphaGEX Application Class"""
    
    def __init__(self):
        """Initialize the AlphaGEX application"""
        self.initialize_session_state()
        self.api = TradingVolatilityAPI()
        self.behavioral_engine = BehavioralEngine()
        self.visual_analyzer = VisualIntelligenceCoordinator()
        
    def initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        if 'system_status' not in st.session_state:
            st.session_state.system_status = '🟡 Initializing'
        if 'analysis_history' not in st.session_state:
            st.session_state.analysis_history = []
        if 'api_connected' not in st.session_state:
            st.session_state.api_connected = False
        if 'api_username' not in st.session_state:
            st.session_state.api_username = ''
        if 'redis_status' not in st.session_state:
            st.session_state.redis_status = '🟡 Unknown'
        if 'current_analysis' not in st.session_state:
            st.session_state.current_analysis = None
        if 'scanner_results' not in st.session_state:
            st.session_state.scanner_results = []
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
            
    def render_header(self):
        """Render main application header"""
        st.markdown(f'<h1 class="main-header">{APP_ICON} AlphaGEX</h1>', unsafe_allow_html=True)
        st.markdown("*Professional Gamma Exposure Trading Platform*")
        
        # Status metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("System Status", st.session_state.system_status)
        with col2:
            st.metric("Redis Cache", st.session_state.get('redis_status', 'Unknown'))
        with col3:
            st.metric("Analyses", len(st.session_state.analysis_history))
        with col4:
            api_status = "🟢 Connected" if st.session_state.get('api_connected', False) else "🔴 Not Configured"
            st.metric("API Status", api_status)
            
    def render_sidebar(self):
        """Render sidebar with configuration options"""
        with st.sidebar:
            st.header("⚙️ Configuration")
            
            # API Configuration
            st.subheader("📡 TradingVolatility.net API")
            username = st.text_input(
                "API Username", 
                value=st.session_state.get('api_username', ''),
                help="Enter your TradingVolatility.net username"
            )
            
            if username and username != st.session_state.get('api_username', ''):
                st.session_state['api_username'] = username
                self.api.set_credentials(username)
                
                # Test connection
                with st.spinner("Testing API connection..."):
                    result = test_api_connection(username)
                    if result['status'] == 'success':
                        st.session_state['api_connected'] = True
                        st.success("✅ API Connected!")
                        log_success("API connection established")
                    else:
                        st.session_state['api_connected'] = False
                        st.error(f"❌ API Error: {result['message']}")
                        log_error(f"API connection failed: {result['message']}")
            
            # System Settings
            st.subheader("⚙️ System Settings")
            
            # Analysis settings
            st.selectbox(
                "Default Analysis Timeframe",
                options=["Intraday", "1-3 DTE", "1-2 Weeks"],
                index=1,
                key="default_timeframe"
            )
            
            # Risk settings
            max_position_size = st.slider(
                "Max Position Size (%)",
                min_value=1,
                max_value=10,
                value=3,
                help="Maximum percentage of capital per trade"
            )
            st.session_state['max_position_size'] = max_position_size / 100
            
            # Scanner settings
            st.subheader("🔍 Scanner Settings")
            min_confidence = st.slider(
                "Minimum Signal Confidence",
                min_value=0.3,
                max_value=0.9,
                value=0.65,
                step=0.05,
                help="Minimum confidence level for signals"
            )
            st.session_state['min_confidence'] = min_confidence
            
            # Status indicators
            st.subheader("📊 System Status")
            if st.session_state.get('api_connected'):
                st.success("🟢 API Connected")
            else:
                st.warning("🟡 API Not Configured")
                
            if len(st.session_state.analysis_history) > 0:
                st.info(f"📈 {len(st.session_state.analysis_history)} analyses performed")
            else:
                st.info("📊 No analyses yet")
                
    def render_chart_analysis_tab(self):
        """Render the chart analysis tab"""
        st.subheader("📊 GEX Chart Analysis & Symbol Deep Dive")
        
        # Symbol input section
        col1, col2 = st.columns([2, 1])
        
        with col1:
            symbol = st.text_input(
                "Enter Symbol for Analysis",
                value="SPY",
                help="Enter any optionable symbol (e.g., SPY, QQQ, AAPL)"
            ).upper()
            
        with col2:
            analyze_btn = st.button("🚀 Analyze Symbol", type="primary")
        
        if analyze_btn and symbol:
            self.perform_symbol_analysis(symbol)
        
        # Image upload section
        st.subheader("📸 Upload GEX Chart for Visual Analysis")
        uploaded_file = st.file_uploader(
            "Choose a GEX profile chart image",
            type=['png', 'jpg', 'jpeg', 'gif', 'bmp'],
            help="Upload a GEX profile chart for automated pattern recognition"
        )
        
        if uploaded_file is not None:
            self.analyze_uploaded_chart(uploaded_file)
        
        # Display current analysis if available
        if st.session_state.get('current_analysis'):
            self.display_analysis_results(st.session_state.current_analysis)
    
    def render_copilot_chat_tab(self):
        """Render the AI co-pilot chat interface"""
        st.subheader("💬 AlphaGEX AI Co-Pilot")
        st.info("🤖 Your intelligent trading assistant for GEX analysis and strategy suggestions")
        
        # Chat history display
        chat_container = st.container()
        
        with chat_container:
            for i, message in enumerate(st.session_state.chat_history):
                if message['role'] == 'user':
                    st.markdown(f"**You:** {message['content']}")
                else:
                    st.markdown(f"**AlphaGEX:** {message['content']}")
                st.markdown("---")
        
        # Chat input
        user_input = st.text_input(
            "Ask AlphaGEX about gamma exposure, market maker behavior, or trading strategies:",
            placeholder="e.g., 'What does high positive GEX mean for SPY?'",
            key="chat_input"
        )
        
        if st.button("💬 Send") and user_input:
            self.process_chat_message(user_input)
            st.rerun()
            
        # Quick action buttons
        st.subheader("🚀 Quick Actions")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("💡 Explain Current Market"):
                self.quick_market_explanation()
                
        with col2:
            if st.button("🎯 Find Best Setups"):
                self.find_best_setups()
                
        with col3:
            if st.button("⚠️ Risk Check"):
                self.perform_risk_check()
                
        with col4:
            if st.button("📚 Trading Tips"):
                self.show_trading_tips()
    
    def render_scanner_tab(self):
        """Render the live market scanner tab"""
        st.subheader("🔍 Live 200+ Symbol GEX Scanner")
        st.info("🎯 Scanning for high-probability gamma exposure setups across 200+ symbols")
        
        # Scanner controls
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            scan_type = st.selectbox(
                "Scan Type",
                options=["All Symbols (200+)", "High Priority Only", "Custom List"],
                help="Select which symbols to scan"
            )
            
        with col2:
            if st.button("🚀 Start Scan", type="primary"):
                self.run_market_scan(scan_type)
                
        with col3:
            auto_scan = st.checkbox("Auto Refresh (5min)", help="Automatically refresh scan results")
            
        # Display scan results
        if st.session_state.scanner_results:
            self.display_scanner_results()
        else:
            st.info("👆 Click 'Start Scan' to begin scanning for GEX opportunities")
            
        # Scanner statistics
        if st.session_state.scanner_results:
            self.display_scanner_stats()
    
    def perform_symbol_analysis(self, symbol: str):
        """Perform comprehensive analysis of a specific symbol"""
        with st.spinner(f"Analyzing {symbol}... This may take a moment."):
            try:
                # Get GEX data from API
                gex_result = self.api.get_net_gex(symbol)
                
                if gex_result['success']:
                    # Perform behavioral analysis
                    price_data = self.get_price_data(symbol)
                    behavioral_analysis = self.behavioral_engine.analyze_mm_behavior(gex_result, price_data)
                    
                    # Create comprehensive analysis
                    analysis = {
                        'symbol': symbol,
                        'timestamp': datetime.now(),
                        'gex_data': gex_result,
                        'price_data': price_data,
                        'behavioral_analysis': behavioral_analysis,
                        'visual_analysis': self.visual_analyzer.process_gex_data_visually(gex_result)
                    }
                    
                    # Store in session state and history
                    st.session_state.current_analysis = analysis
                    st.session_state.analysis_history.append(analysis)
                    
                    st.success(f"✅ Analysis complete for {symbol}")
                    log_success(f"Completed analysis for {symbol}")
                    
                else:
                    st.error(f"❌ Failed to get GEX data for {symbol}: {gex_result.get('error', 'Unknown error')}")
                    log_error(f"GEX data fetch failed for {symbol}")
                    
            except Exception as e:
                st.error(f"❌ Analysis error: {str(e)}")
                log_error(f"Symbol analysis error for {symbol}: {str(e)}")
    
    def analyze_uploaded_chart(self, uploaded_file):
        """Analyze an uploaded chart image"""
        with st.spinner("Analyzing chart image..."):
            try:
                # Display the uploaded image
                st.image(uploaded_file, caption="Uploaded GEX Chart", use_column_width=True)
                
                # Perform visual analysis
                visual_result = self.visual_analyzer.analyze_chart_image(uploaded_file)
                
                if visual_result.get('success', True):
                    st.success("✅ Chart analysis complete!")
                    
                    # Display insights
                    if visual_result.get('insights'):
                        st.subheader("🔍 Visual Analysis Insights")
                        for insight in visual_result['insights']:
                            st.write(f"• {insight}")
                    
                    # Display confidence score
                    confidence = visual_result.get('confidence', 0)
                    st.metric("Analysis Confidence", f"{confidence:.1%}")
                    
                else:
                    st.warning("⚠️ Chart analysis had limited success")
                    
            except Exception as e:
                st.error(f"❌ Chart analysis error: {str(e)}")
                log_error(f"Chart analysis error: {str(e)}")
    
    def display_analysis_results(self, analysis: Dict):
        """Display comprehensive analysis results"""
        st.subheader(f"📊 Analysis Results: {analysis['symbol']}")
        
        # Key metrics
        gex_data = analysis['gex_data']
        behavioral_data = analysis['behavioral_analysis']
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            net_gex = gex_data.get('net_gex', 0)
            st.metric("Net GEX", f"${net_gex/1e9:.2f}B")
            
        with col2:
            gamma_flip = gex_data.get('gamma_flip', 0)
            st.metric("Gamma Flip", f"${gamma_flip:.2f}")
            
        with col3:
            mm_state = behavioral_data.get('mm_state', 'Unknown')
            st.metric("MM State", mm_state)
            
        with col4:
            confidence = behavioral_data.get('confidence', 0)
            st.metric("Confidence", f"{confidence:.1%}")
        
        # GEX regime analysis
        if net_gex > 1e9:  # Positive GEX
            st.markdown("""
            <div class="gex-positive">
                <strong>🛡️ Positive GEX Environment</strong><br>
                Market makers are long gamma, expecting range-bound price action.
                Consider premium selling strategies or iron condors.
            </div>
            """, unsafe_allow_html=True)
        elif net_gex < -1e9:  # Negative GEX
            st.markdown("""
            <div class="gex-negative">
                <strong>🔥 Negative GEX Environment</strong><br>
                Market makers are short gamma, expecting volatile price action.
                Look for squeeze setups and momentum plays.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("📊 Neutral GEX environment - mixed signals")
        
        # Trading signals
        signals = behavioral_data.get('signals', [])
        if signals:
            st.subheader("🎯 Trading Signals")
            for signal in signals:
                st.markdown(f"""
                <div class="signal-box">
                    <strong>{signal['type']}</strong><br>
                    <em>{signal['reason']}</em><br>
                    Confidence: {signal['confidence']:.1%} | Time Horizon: {signal['time_horizon']}
                </div>
                """, unsafe_allow_html=True)
    
    def get_price_data(self, symbol: str) -> Dict:
        """Get current price data for a symbol"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                return {
                    'current_price': current_price,
                    'daily_change': (hist['Close'].iloc[-1] - hist['Open'].iloc[0]) / hist['Open'].iloc[0]
                }
            else:
                return {'current_price': 0, 'daily_change': 0}
        except Exception as e:
            log_error(f"Price data fetch error for {symbol}: {str(e)}")
            return {'current_price': 0, 'daily_change': 0}
    
    def process_chat_message(self, message: str):
        """Process a chat message from the user"""
        # Add user message to history
        st.session_state.chat_history.append({'role': 'user', 'content': message})
        
        # Generate AI response (placeholder - integrate with your AI system)
        response = self.generate_ai_response(message)
        
        # Add AI response to history
        st.session_state.chat_history.append({'role': 'assistant', 'content': response})
    
    def generate_ai_response(self, message: str) -> str:
        """Generate AI response to user message (placeholder)"""
        # This is a placeholder - integrate with your AI system
        if 'gex' in message.lower():
            return "Gamma Exposure (GEX) represents the dollar amount market makers need to hedge based on options positioning. High positive GEX suggests range-bound markets, while negative GEX indicates potential for explosive moves."
        elif 'squeeze' in message.lower():
            return "A gamma squeeze occurs when market makers are short gamma and must buy stock as prices rise, creating a feedback loop. Look for negative GEX environments near gamma flip points for squeeze setups."
        elif 'strategy' in message.lower():
            return "Based on current market conditions, I recommend focusing on the gamma regime. In positive GEX environments, consider premium selling. In negative GEX, look for directional plays above/below the gamma flip."
        else:
            return "I'm here to help with gamma exposure analysis and trading strategies. Ask me about GEX levels, market maker behavior, or specific trading setups!"
    
    def quick_market_explanation(self):
        """Provide quick market explanation"""
        explanation = """
        📊 **Current Market Analysis:**
        
        • **GEX Environment**: Analyzing current gamma exposure levels across major indices
        • **Market Maker Positioning**: Evaluating dealer hedging requirements
        • **Key Levels**: Identifying gamma flip points and wall levels
        • **Trade Setups**: Looking for high-probability opportunities
        
        Use the scanner to find specific opportunities across 200+ symbols!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': explanation})
    
    def find_best_setups(self):
        """Find and display best current setups"""
        setup_analysis = """
        🎯 **Best Current Setups:**
        
        Based on gamma exposure analysis:
        
        1. **SPY**: Check for squeeze setup if negative GEX
        2. **QQQ**: Monitor tech gamma positioning  
        3. **High IV names**: Look for premium selling opportunities
        
        Run a full scan to get real-time opportunities!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': setup_analysis})
    
    def perform_risk_check(self):
        """Perform risk assessment"""
        risk_analysis = """
        ⚠️ **Risk Assessment:**
        
        • **Position Sizing**: Max 3% per trade recommended
        • **Stop Losses**: Set at 50% loss for long options
        • **Profit Targets**: 100% for directional, 50% for short premium
        • **Diversification**: Avoid concentration in single names
        
        Remember: Gamma analysis is probabilistic, not guaranteed!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': risk_analysis})
    
    def show_trading_tips(self):
        """Show trading tips"""
        tips = """
        📚 **AlphaGEX Trading Tips:**
        
        1. **Follow the Gamma**: Let GEX guide your strategy selection
        2. **Respect the Walls**: Don't fight strong gamma levels
        3. **Time Decay**: Use expiration cycles to your advantage
        4. **Risk Management**: Size positions appropriately
        5. **Stay Flexible**: Market conditions change rapidly
        
        Master these principles for consistent profitability!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': tips})
    
    def run_market_scan(self, scan_type: str):
        """Run market scan for GEX opportunities"""
        with st.spinner("Scanning market for GEX opportunities..."):
            try:
                # Determine symbols to scan
                if scan_type == "High Priority Only":
                    symbols_to_scan = HIGH_PRIORITY_SYMBOLS[:50]  # Top 50
                elif scan_type == "Custom List":
                    symbols_to_scan = HIGH_PRIORITY_SYMBOLS[:20]  # Smaller custom list
                else:  # All symbols
                    symbols_to_scan = HIGH_PRIORITY_SYMBOLS + MEDIUM_PRIORITY_SYMBOLS
                
                # Simulate scanning (replace with real API calls)
                results = []
                progress_bar = st.progress(0)
                
                for i, symbol in enumerate(symbols_to_scan[:50]):  # Limit for demo
                    # Update progress
                    progress = (i + 1) / len(symbols_to_scan[:50])
                    progress_bar.progress(progress)
                    
                    # Simulate scan result (replace with real analysis)
                    if np.random.random() > 0.7:  # 30% chance of signal
                        results.append({
                            'symbol': symbol,
                            'signal_type': np.random.choice(['LONG_CALL', 'LONG_PUT', 'SELL_CALL', 'IRON_CONDOR']),
                            'confidence': np.random.uniform(0.6, 0.9),
                            'net_gex': np.random.uniform(-2e9, 3e9),
                            'gamma_flip': np.random.uniform(100, 500),
                            'mm_state': np.random.choice(['TRAPPED', 'DEFENDING', 'HUNTING', 'PANICKING'])
                        })
                    
                    time.sleep(0.1)  # Respect rate limits
                
                progress_bar.empty()
                st.session_state.scanner_results = results
                st.success(f"✅ Scan complete! Found {len(results)} opportunities")
                log_success(f"Market scan completed: {len(results)} signals found")
                
            except Exception as e:
                st.error(f"❌ Scan error: {str(e)}")
                log_error(f"Market scan error: {str(e)}")
    
    def display_scanner_results(self):
        """Display scanner results in a table"""
        if not st.session_state.scanner_results:
            return
            
        st.subheader(f"📊 Scan Results ({len(st.session_state.scanner_results)} signals)")
        
        # Convert to DataFrame for display
        df = pd.DataFrame(st.session_state.scanner_results)
        
        # Format the data
        df['Confidence'] = df['confidence'].apply(lambda x: f"{x:.1%}")
        df['Net GEX'] = df['net_gex'].apply(lambda x: f"${x/1e9:.2f}B")
        df['Gamma Flip'] = df['gamma_flip'].apply(lambda x: f"${x:.2f}")
        
        # Display with formatting
        st.dataframe(
            df[['symbol', 'signal_type', 'Confidence', 'Net GEX', 'mm_state']],
            column_config={
                'symbol': 'Symbol',
                'signal_type': 'Signal Type',
                'mm_state': 'MM State'
            },
            use_container_width=True
        )
        
    def display_scanner_stats(self):
        """Display scanner statistics"""
        if not st.session_state.scanner_results:
            return
            
        st.subheader("📈 Scan Statistics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_signals = len(st.session_state.scanner_results)
            st.metric("Total Signals", total_signals)
            
        with col2:
            high_conf_signals = sum(1 for r in st.session_state.scanner_results if r['confidence'] > 0.75)
            st.metric("High Confidence", high_conf_signals)
            
        with col3:
            avg_confidence = np.mean([r['confidence'] for r in st.session_state.scanner_results])
            st.metric("Avg Confidence", f"{avg_confidence:.1%}")
            
        with col4:
            negative_gex_count = sum(1 for r in st.session_state.scanner_results if r['net_gex'] < 0)
            st.metric("Negative GEX", negative_gex_count)
    
    def run(self):
        """Main application run method"""
        # Update system status
        st.session_state.system_status = '🟢 Online'
        
        # Render main components
        self.render_header()
        self.render_sidebar()
        
        # Main interface tabs
        tab1, tab2, tab3 = st.tabs(["📊 Chart Analysis", "💬 AlphaGEX Co-Pilot", "🔍 Live Scanner"])
        
        with tab1:
            self.render_chart_analysis_tab()
        
        with tab2:
            self.render_copilot_chat_tab()
        
        with tab3:
            self.render_scanner_tab()
        
        # Footer
        st.markdown("---")
        st.markdown("""
        **AlphaGEX v1.0** | Professional Gamma Exposure Trading Platform  
        Built on comprehensive gamma exposure research and market maker behavioral analysis.  
        ⚠️ **Educational purposes only. Not financial advice.**
        """)

# Main execution
def main():
    """Main application entry point"""
    try:
        app = AlphaGEXApp()
        app.run()
    except Exception as e:
        st.error(f"❌ Application Error: {str(e)}")
        log_error(f"Application startup error: {str(e)}")

if __name__ == "__main__":
    main()
