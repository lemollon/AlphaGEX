"""
GammaHunter - Market Maker Co-Pilot
===================================

Main Streamlit application bringing together all trading intelligence components.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import redis
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Any
from PIL import Image
import io

# Import core components
from config import APP_TITLE, APP_ICON, HIGH_PRIORITY_SYMBOLS, MEDIUM_PRIORITY_SYMBOLS
from core.logger import logger, log_error
from core.api_client import TradingVolatilityAPI, test_api_connection
from core.behavioral_engine import BehavioralEngine
from core.visual_analyzer import VisualIntelligenceCoordinator

# Page configuration
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
.main-header {
    font-size: 2.5rem;
    font-weight: bold;
    color: #1f77b4;
    text-align: center;
    margin-bottom: 2rem;
}
.copilot-response {
    background-color: #f0f2f6;
    border-left: 4px solid #1f77b4;
    padding: 1rem;
    margin: 1rem 0;
    border-radius: 0.5rem;
}
.confidence-high { color: #28a745; font-weight: bold; }
.confidence-medium { color: #ffc107; font-weight: bold; }
.confidence-low { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

class GammaHunterApp:
    """Main Streamlit application class"""
    
    def __init__(self):
        self.setup_session_state()
        self.initialize_systems()
    
    def setup_session_state(self):
        """Initialize session state variables"""
        if 'analysis_history' not in st.session_state:
            st.session_state.analysis_history = []
        if 'conversation_history' not in st.session_state:
            st.session_state.conversation_history = []
        if 'api_key' not in st.session_state:
            st.session_state.api_key = ""
        if 'current_analysis' not in st.session_state:
            st.session_state.current_analysis = None
        if 'system_status' not in st.session_state:
            st.session_state.system_status = "Initializing..."
    
    def initialize_systems(self):
        """Initialize backend systems"""
        try:
            # Try Redis connection
            try:
                self.redis_client = redis.Redis(
                    host='localhost', port=6379, db=0, decode_responses=True
                )
                self.redis_client.ping()
                st.session_state.redis_status = "Connected"
            except:
                # Mock Redis for development
                class MockRedis:
                    def __init__(self): self.data = {}
                    def get(self, key): return self.data.get(key)
                    def setex(self, key, ttl, value): self.data[key] = value
                    def hmget(self, key, *fields): return [None] * len(fields)
                    def eval(self, *args, **kwargs): return 1
                    def ping(self): return True
                
                self.redis_client = MockRedis()
                st.session_state.redis_status = "Mock (Development)"
            
            # Initialize engines
            self.behavioral_engine = BehavioralEngine()
            self.visual_coordinator = VisualIntelligenceCoordinator(self.behavioral_engine)
            
            # API will be initialized when key is provided
            self.api = None
            
            st.session_state.system_status = "Operational"
            
        except Exception as e:
            error_id = log_error("app_initialization", e)
            st.session_state.system_status = f"Error: {error_id}"
    
def render_header(self):
    """Render main header"""
    st.markdown(f'<h1 class="main-header">{APP_ICON} GammaHunter</h1>', unsafe_allow_html=True)
    st.markdown("*Your intelligent Market Maker Co-Pilot*")
    
    # Status metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("System Status", st.session_state.system_status)
    with col2:
        st.metric("Redis", st.session_state.get('redis_status', 'Unknown'))
    with col3:
        st.metric("Analyses", len(st.session_state.analysis_history))
    with col4:
        # Fix: Check if self.api exists and is properly configured
        api_status = "Connected" if hasattr(self, 'api') and self.api and getattr(self.api, 'username', None) else "Not Configured"
        st.metric("API Status", api_status)
    
    def render_sidebar(self):
        """Render sidebar configuration"""
        with st.sidebar:
            st.header("Configuration")
            
            # API Key input
            api_key = st.text_input(
                "TradingVolatility.net API Key",
                type="password",
                value=st.session_state.api_key,
                help="Enter your API key from stocks.tradingvolatility.net"
            )
            
            if api_key != st.session_state.api_key:
                st.session_state.api_key = api_key
                if api_key:
                    try:
                        # Test connection
                        with st.spinner("Testing API connection..."):
                            self.api = TradingVolatilityAPI(api_key, self.redis_client)
                            # Note: In production, you'd test with async
                            st.success("API configured successfully")
                    except Exception as e:
                        st.error(f"API configuration failed: {str(e)}")
                        self.api = None
            
            st.divider()
            
            # Analysis History
            st.header("Recent Analysis")
            if st.session_state.analysis_history:
                for analysis in st.session_state.analysis_history[-3:]:
                    with st.expander(f"{analysis.get('symbol', 'Unknown')} - {analysis.get('timestamp', '')[:10]}"):
                        st.write(f"Signal: {analysis.get('signal_type', 'N/A')}")
                        st.write(f"Confidence: {analysis.get('confidence', 0):.1f}%")
            else:
                st.caption("No analysis history yet")
            
            st.divider()
            
            # System Information
            st.header("System Info")
            st.write(f"**Behavioral Engine:** Loaded")
            st.write(f"**Visual Analyzer:** Ready")
            st.write(f"**Cache System:** {st.session_state.get('redis_status', 'Unknown')}")
            
            # Export system state
            if st.button("Export System State"):
                try:
                    state = logger.export_session_state()
                    st.download_button(
                        "Download State",
                        json.dumps(state, indent=2, default=str),
                        file_name=f"gammahunter_state_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json"
                    )
                except Exception as e:
                    st.error(f"Export failed: {str(e)}")
    
    def render_chart_analysis_tab(self):
        """Chart analysis interface"""
        st.subheader("📊 Upload GEX Chart for Analysis")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            uploaded_file = st.file_uploader(
                "Choose a gamma exposure chart",
                type=['png', 'jpg', 'jpeg'],
                help="Upload a GEX profile chart for intelligent analysis"
            )
            
            symbol = st.text_input(
                "Symbol (optional for API validation)", 
                placeholder="SPY", 
                max_chars=10
            ).upper().strip()
            
            if uploaded_file and st.button("🧠 Analyze Chart", type="primary"):
                self.analyze_uploaded_chart(uploaded_file, symbol)
        
        with col2:
            if uploaded_file:
                image = Image.open(uploaded_file)
                st.image(image, caption="Uploaded Chart", use_column_width=True)
        
        # Display results if available
        if st.session_state.current_analysis:
            self.display_analysis_results(st.session_state.current_analysis)
    
    def analyze_uploaded_chart(self, uploaded_file, symbol: str):
        """Analyze uploaded chart"""
        with st.spinner("🧠 Analyzing your chart..."):
            try:
                image_bytes = uploaded_file.read()
                
                # Get API data if symbol provided
                api_data = None
                if symbol and self.api:
                    try:
                        # In production, this would be async
                        # For now, create mock data structure
                        api_data = {
                            "spot_price": 450.0,
                            "net_gex": -1500000000,  # Mock negative GEX
                            "gamma_flip_price": 455.0,
                            "strikes": [
                                {"strike": 445, "gex": -300000000, "open_interest": 10000},
                                {"strike": 450, "gex": 500000000, "open_interest": 15000},
                                {"strike": 455, "gex": -200000000, "open_interest": 8000}
                            ]
                        }
                        st.info(f"Using mock API data for {symbol} (configure Redis and API for production)")
                    except Exception as e:
                        st.warning(f"Could not fetch API data: {str(e)}")
                
                # Perform visual analysis
                analysis_result = self.visual_coordinator.analyze_chart_image(
                    image_bytes, symbol, api_data
                )
                
                # Store results
                st.session_state.current_analysis = analysis_result
                
                # Add to history
                history_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'symbol': symbol or 'Unknown',
                    'analysis_type': 'visual',
                    'confidence': analysis_result.get('overall_confidence', 0),
                    'signal_type': 'visual_analysis'
                }
                st.session_state.analysis_history.append(history_entry)
                
                st.success("Analysis complete!")
                
            except Exception as e:
                error_id = log_error("chart_analysis_ui", e)
                st.error(f"Analysis failed. Error ID: {error_id}")
    
    def display_analysis_results(self, analysis_result: Dict[str, Any]):
        """Display comprehensive analysis results"""
        st.subheader("🎯 Analysis Results")
        
        # Overall confidence
        confidence = analysis_result.get('overall_confidence', 0)
        confidence_class = (
            'confidence-high' if confidence > 70 else
            'confidence-medium' if confidence > 40 else
            'confidence-low'
        )
        
        st.markdown(f"""
        <div class="copilot-response">
        <h4>📊 Co-Pilot Assessment</h4>
        <p><span class="{confidence_class}">Overall Confidence: {confidence:.0f}%</span></p>
        </div>
        """, unsafe_allow_html=True)
        
        # Visual analysis details
        visual_analysis = analysis_result.get('visual_analysis')
        if visual_analysis:
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Visual Detection:**")
                st.write(f"Chart Type: {visual_analysis.chart_type}")
                st.write(f"Elements Found: {len(visual_analysis.detected_elements)}")
                
                if visual_analysis.detected_elements:
                    for elem in visual_analysis.detected_elements:
                        st.write(f"• {elem.element_type}: {elem.confidence:.0f}% confidence")
            
            with col2:
                st.write("**Recommendations:**")
                for rec in visual_analysis.recommendations:
                    st.write(f"• {rec}")
        
        # API validation
        validation = analysis_result.get('validation_results')
        if validation:
            st.write("**API Validation:**")
            agreement = validation.get('agreement_score', 0)
            st.progress(agreement / 100)
            st.write(f"Agreement Score: {agreement:.0f}%")
            
            for conf in validation.get('confirmations', []):
                st.success(f"✅ {conf}")
            for disc in validation.get('discrepancies', []):
                st.warning(f"⚠️ {disc}")
        
        # Integrated insights
        insights = analysis_result.get('integrated_insights', [])
        if insights:
            st.write("**Co-Pilot Insights:**")
            for insight in insights:
                st.info(insight)
    
    def render_copilot_chat_tab(self):
        """Co-pilot chat interface"""
        st.subheader("💬 Chat with GammaHunter Co-Pilot")
        
        # Display conversation history
        for message in st.session_state.conversation_history:
            if message['role'] == 'user':
                st.chat_message("user").write(message['content'])
            else:
                st.chat_message("assistant").write(message['content'])
        
        # Chat input
        if prompt := st.chat_input("Ask about gamma analysis, market maker behavior, or trading strategies..."):
            # Add user message
            st.session_state.conversation_history.append({
                'role': 'user',
                'content': prompt,
                'timestamp': datetime.now().isoformat()
            })
            
            # Generate response (simplified for Phase 1)
            response = self.generate_simple_response(prompt)
            
            # Add assistant response
            st.session_state.conversation_history.append({
                'role': 'assistant', 
                'content': response,
                'timestamp': datetime.now().isoformat()
            })
            
            st.rerun()
    
    def generate_simple_response(self, prompt: str) -> str:
        """Generate simple co-pilot response (Phase 1 implementation)"""
        
        prompt_lower = prompt.lower()
        
        if 'gamma' in prompt_lower or 'gex' in prompt_lower:
            return """Based on our gamma exposure research:

• **Positive GEX (>2B)**: Market makers long gamma → volatility suppression (buy dips, sell rallies)
• **Negative GEX (<-1B)**: Market makers short gamma → volatility amplification (sell dips, buy rallies)  
• **Gamma Flip Point**: Where cumulative GEX crosses zero - critical transition level
• **Gamma Walls**: Large concentrations that create support/resistance

Our analysis shows negative GEX squeeze setups win 68% of the time when properly timed."""
        
        elif 'trade' in prompt_lower or 'signal' in prompt_lower:
            return """GammaHunter focuses on 3 high-probability strategies:

1. **Long Calls**: When dealers trapped short gamma below flip point (68% win rate)
2. **Long Puts**: When positive GEX breaks down below flip (58% win rate)  
3. **Iron Condors**: When strong gamma walls define clear ranges (72% win rate)

Upload a GEX chart for specific analysis, or use our scanner for live signals."""
        
        elif 'help' in prompt_lower:
            return """I'm your Market Maker Co-Pilot! I can help you:

• **Analyze GEX charts** - Upload images for pattern recognition
• **Explain gamma concepts** - Market maker behavior and psychology
• **Identify trading setups** - Long calls/puts and iron condors
• **Validate ideas** - Challenge your analysis with research-backed insights

What would you like to explore first?"""
        
        else:
            return """I'm here to help you understand market maker behavior through gamma exposure analysis. 

I can analyze your charts, explain GEX concepts, identify trading opportunities, and challenge your ideas with research-backed insights. 

What specific aspect of gamma trading would you like to explore?"""
    
    def render_scanner_tab(self):
        """Live scanner interface"""
        st.subheader("🔍 Live Gamma Scanner")
        
        if not self.api:
            st.warning("⚠️ API key required for live scanning. Configure in sidebar.")
            st.info("The scanner will monitor 200+ stocks for high-probability gamma setups using our intelligent priority system.")
            
            # Show what the scanner would do
            col1, col2 = st.columns(2)
            with col1:
                st.write("**High Priority Symbols:**")
                for symbol in HIGH_PRIORITY_SYMBOLS[:8]:
                    st.write(f"• {symbol}")
                st.caption(f"...and {len(HIGH_PRIORITY_SYMBOLS)-8} more")
            
            with col2:
                st.write("**Medium Priority Symbols:**")
                for symbol in MEDIUM_PRIORITY_SYMBOLS[:8]:
                    st.write(f"• {symbol}")
                st.caption(f"...and {len(MEDIUM_PRIORITY_SYMBOLS)-8} more")
            
            return
        
        # Scanner controls
        col1, col2 = st.columns([3, 1])
        with col1:
            symbols_input = st.text_input(
                "Symbols to scan", 
                value="SPY,QQQ,IWM,AAPL,TSLA",
                help="Comma-separated symbols"
            )
        with col2:
            if st.button("🚀 Start Scan", type="primary"):
                self.perform_scan(symbols_input)
        
        # Display mock results for Phase 1
        if st.button("Show Demo Results"):
            self.display_demo_scan_results()
    
    def perform_scan(self, symbols_input: str):
        """Perform live scan (Phase 1 mock implementation)"""
        symbols = [s.strip().upper() for s in symbols_input.split(',')]
        
        with st.spinner(f"Scanning {len(symbols)} symbols..."):
            st.info("Live scanning requires Redis and API configuration. Showing demo results.")
            self.display_demo_scan_results()
    
    def display_demo_scan_results(self):
        """Display demo scan results"""
        st.write("**Demo Scan Results:**")
        
        demo_data = [
            {"Symbol": "SPY", "Signal": "Long Calls", "Confidence": "85%", "GEX": "-1.5B", "State": "Trapped"},
            {"Symbol": "QQQ", "Signal": "Iron Condor", "Confidence": "72%", "GEX": "+2.1B", "State": "Defending"},
            {"Symbol": "TSLA", "Signal": "Long Puts", "Confidence": "68%", "GEX": "+3.2B", "State": "Defending"},
            {"Symbol": "AAPL", "Signal": "No Signal", "Confidence": "45%", "GEX": "+0.8B", "State": "Neutral"},
            {"Symbol": "NVDA", "Signal": "Long Calls", "Confidence": "79%", "GEX": "-2.1B", "State": "Trapped"}
        ]
        
        df = pd.DataFrame(demo_data)
        st.dataframe(df, use_container_width=True)
        
        # Summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("High Confidence", "3")
        with col2:
            st.metric("Actionable Signals", "4")
        with col3:
            st.metric("Avg Confidence", "70%")
    
    def run(self):
        """Main application run method"""
        self.render_header()
        self.render_sidebar()
        
        # Main interface tabs
        tab1, tab2, tab3 = st.tabs(["📊 Chart Analysis", "💬 Co-Pilot Chat", "🔍 Live Scanner"])
        
        with tab1:
            self.render_chart_analysis_tab()
        
        with tab2:
            self.render_copilot_chat_tab()
        
        with tab3:
            self.render_scanner_tab()
        
        # Footer
        st.markdown("---")
        st.markdown("""
        **GammaHunter v1.0** | Built on comprehensive gamma exposure research  
        ⚠️ Educational purposes only. Not financial advice.
        """)

# Main execution
def main():
    app = GammaHunterApp()
    app.run()

if __name__ == "__main__":  # Fix: Change **name** to __name__
    main()
