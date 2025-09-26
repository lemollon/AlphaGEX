#!/usr/bin/env python3
"""
AlphaGEX - Professional Gamma Exposure Trading Platform
========================================================
Complete market maker exploitation system using gamma exposure analysis.
Updated with Phase 1 Dynamic Symbol Selection
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

#!/usr/bin/env python3
"""
AlphaGEX - Professional Gamma Exposure Trading Platform
========================================================
Complete market maker exploitation system using gamma exposure analysis.
Updated with Phase 1 Dynamic Symbol Selection
"""

print("DEBUG: Starting app.py execution...")

import streamlit as st
print("DEBUG: Streamlit imported successfully")

import pandas as pd
import numpy as np
print("DEBUG: Basic libraries imported")

import plotly.graph_objects as go
from plotly.subplots import make_subplots
print("DEBUG: Plotly imported")

import yfinance as yf
from datetime import datetime, timedelta
import time
import json
from typing import Dict, List, Optional
print("DEBUG: All standard libraries imported")

# Import configuration and core modules
print("DEBUG: Attempting to import config...")
try:
    from config import (
        APP_TITLE, APP_ICON, HIGH_PRIORITY_SYMBOLS, MEDIUM_PRIORITY_SYMBOLS,
        GEX_THRESHOLDS, RISK_LIMITS, COLORS, STREAMLIT_CONFIG
    )
    print("DEBUG: Config imported successfully")
    # Try to import extended symbols if available
    try:
        from config import EXTENDED_PRIORITY_SYMBOLS, FULL_SYMBOL_UNIVERSE
        print("DEBUG: Extended config imported")
    except ImportError:
        print("DEBUG: Using fallback extended config")
        EXTENDED_PRIORITY_SYMBOLS = []
        FULL_SYMBOL_UNIVERSE = HIGH_PRIORITY_SYMBOLS + MEDIUM_PRIORITY_SYMBOLS
except ImportError:
    print("DEBUG: Using fallback configuration")
    # Your fallback config here...

# Import configuration and core modules
try:
    from config import (
        APP_TITLE, APP_ICON, HIGH_PRIORITY_SYMBOLS, MEDIUM_PRIORITY_SYMBOLS,
        GEX_THRESHOLDS, RISK_LIMITS, COLORS, STREAMLIT_CONFIG
    )
    # Try to import extended symbols if available
    try:
        from config import EXTENDED_PRIORITY_SYMBOLS, FULL_SYMBOL_UNIVERSE
    except ImportError:
        EXTENDED_PRIORITY_SYMBOLS = []
        FULL_SYMBOL_UNIVERSE = HIGH_PRIORITY_SYMBOLS + MEDIUM_PRIORITY_SYMBOLS
except ImportError:
    # Comprehensive fallback configuration for 200+ symbols
    APP_TITLE = "AlphaGEX"
    APP_ICON = "🎯"
    
    # High Priority - Major indices and most liquid options (50 symbols)
    HIGH_PRIORITY_SYMBOLS = [
        # Major ETFs & Indices
        "SPY", "QQQ", "IWM", "DIA", "VIX", "EFA", "EEM", "GLD", "SLV", "TLT",
        "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB", "XLRE",
        
        # Mega Cap Tech
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "NVDA", "NFLX", "ADBE",
        
        # Large Cap Tech
        "CRM", "ORCL", "INTC", "AMD", "QCOM", "AVGO", "CSCO", "NOW", "SNOW", "MDB",
        "PLTR", "RBLX", "U", "ZM", "DOCU", "ROKU", "DDOG", "CRWD", "ZS", "OKTA"
    ]
    
    # Medium Priority - Sector leaders (100 symbols)
    MEDIUM_PRIORITY_SYMBOLS = [
        # Communication & Media
        "DIS", "CMCSA", "T", "VZ", "WBD", "PARA", "FOX", "FOXA", "DISH", "SPOT",
        
        # Financial Services
        "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "COF",
        "V", "MA", "PYPL", "SQ", "AFRM", "SOFI", "UPST", "HOOD", "COIN", "USB",
        
        # Healthcare & Biotech
        "JNJ", "PFE", "UNH", "ABBV", "MRK", "GILD", "BIIB", "AMGN", "REGN", "VRTX",
        "BMY", "LLY", "TMO", "DHR", "ABT", "ISRG", "DXCM", "ILMN", "MRNA", "BNTX",
        
        # Consumer Discretionary
        "HD", "MCD", "SBUX", "NKE", "LOW", "TJX", "TGT", "COST", "BKNG", "LULU",
        "ABNB", "UBER", "LYFT", "DASH", "ETSY", "CHWY", "PINS", "SNAP", "RH", "BBY",
        
        # Consumer Staples
        "KO", "PEP", "WMT", "PG", "MDLZ", "KHC", "CL", "KMB", "GIS", "K",
        
        # Industrial
        "BA", "CAT", "GE", "MMM", "HON", "UPS", "FDX", "LMT", "RTX", "NOC",
        "DE", "EMR", "ETN", "ITW", "PH", "ROK", "DOV", "XYL", "CARR", "OTIS",
        
        # Energy
        "XOM", "CVX", "COP", "EOG", "SLB", "OXY", "MPC", "VLO", "PSX", "KMI",
        
        # Semiconductors
        "TSM", "ASML", "TXN", "LRCX", "KLAC", "AMAT", "ADI", "MRVL", "MU", "MCHP"
    ]
    
    # Extended Priority - Additional names for 200+ coverage (100+ symbols)
    EXTENDED_PRIORITY_SYMBOLS = [
        # Additional Tech/Growth
        "SHOP", "TWLO", "VEEV", "WDAY", "PANW", "FTNT", "NET", "ESTC", "SPLK", "TEAM",
        "INTU", "CDNS", "SNPS", "ANSS", "ADSK", "ROP", "TDG", "VRSN", "MTCH", "BMBL",
        
        # Healthcare Extended
        "CI", "CVS", "ANTM", "HUM", "CNC", "MOH", "ELV", "HCA", "UHS", "THC",
        "IDXX", "ZTS", "EW", "SYK", "BSX", "MDT", "GEHC", "IQV", "CRL", "LH",
        
        # Financial Extended
        "PNC", "TFC", "FITB", "KEY", "RF", "ZION", "CMA", "HBAN", "CFG", "MTB",
        "CBOE", "NDAQ", "ICE", "CME", "SPGI", "MCO", "MKTX", "TW", "LPLA", "IBKR",
        
        # Consumer Extended
        "PTON", "ZG", "Z", "WSM", "GPS", "ANF", "UAA", "UA", "CROX", "DECK",
        "SKX", "VFC", "PVH", "RL", "CPRI", "TPG", "YETI", "ONON", "BIRD", "GOLF",
        
        # Industrial Extended
        "DAL", "UAL", "AAL", "LUV", "ALK", "JBLU", "SAVE", "HA", "CSX", "UNP",
        "NSC", "CP", "CNI", "KSU", "GWR", "TRN", "WAB", "CHRW", "EXPD", "LSTR",
        
        # Automotive & Transportation
        "F", "GM", "RIVN", "LCID", "NIO", "XPEV", "LI", "GRAB", "CPNG", "SE",
        
        # Materials & Utilities
        "LIN", "APD", "ECL", "SHW", "DD", "DOW", "PPG", "NEM", "FCX", "VALE",
        "NEE", "DUK", "SO", "D", "AEP", "EXC", "XEL", "WEC", "ES", "AWK",
        
        # Real Estate
        "AMT", "PLD", "CCI", "EQIX", "WELL", "SPG", "O", "VICI", "EXR", "AVB",
        
        # Other Notable Names
        "BILL", "PCTY", "YEXT", "SUMO", "FSLY", "ALGN", "BIDU", "BILI", "BYND", "CDAY"
    ]
    
    # Combine all symbols for full universe
    ALL_SYMBOLS = HIGH_PRIORITY_SYMBOLS + MEDIUM_PRIORITY_SYMBOLS + EXTENDED_PRIORITY_SYMBOLS
    FULL_SYMBOL_UNIVERSE = list(dict.fromkeys(ALL_SYMBOLS))  # Remove duplicates
    
    print(f"✅ AlphaGEX: Loaded {len(FULL_SYMBOL_UNIVERSE)} symbols for scanning")
    
    GEX_THRESHOLDS = {"positive": 1e9, "negative": -1e9}
    RISK_LIMITS = {"max_position": 0.03}
    COLORS = {"primary": "#00ff00", "secondary": "#ff6384"}
    STREAMLIT_CONFIG = {"theme": "dark"}

try:
    from core.logger import logger, log_error, log_info, log_warning, log_success
except ImportError:
    # Fallback logging functions
    def log_error(msg): print(f"ERROR: {msg}")
    def log_info(msg): print(f"INFO: {msg}")
    def log_warning(msg): print(f"WARNING: {msg}")
    def log_success(msg): print(f"SUCCESS: {msg}")

try:
    from core.api_client import TradingVolatilityAPI, test_api_connection
except ImportError:
    # Mock API client
    class TradingVolatilityAPI:
        def __init__(self):
            self.username = None
        def set_credentials(self, username):
            self.username = username
        def get_net_gex(self, symbol):
            return {"success": True, "net_gex": np.random.uniform(-3e9, 4e9), "gamma_flip": np.random.uniform(400, 500)}
    
    def test_api_connection(username):
        return {"status": "success" if username else "error", "message": "Connection test"}

try:
    from core.behavioral_engine import BehavioralEngine
except ImportError:
    # Mock behavioral engine
    class BehavioralEngine:
        def analyze_mm_behavior(self, gex_data, price_data):
            return {
                "mm_state": np.random.choice(["TRAPPED", "DEFENDING", "HUNTING"]),
                "confidence": np.random.uniform(0.6, 0.9),
                "signals": [{"type": "LONG_CALL", "reason": "Mock signal", "confidence": 0.75, "time_horizon": "1-2 days"}]
            }

try:
    from core.visual_analyzer import VisualIntelligenceCoordinator
except ImportError:
    # Mock visual analyzer
    class VisualIntelligenceCoordinator:
        def process_gex_data_visually(self, gex_data):
            return {"insights": ["Mock visual insight"], "confidence": 0.8}
        def analyze_chart_image(self, image):
            return {"success": True, "insights": ["Chart pattern detected"], "confidence": 0.7}

# Dynamic Symbol Selection Import
try:
    from core.dynamic_selector import DynamicSymbolSelector, create_dynamic_selector
    DYNAMIC_SELECTION_AVAILABLE = True
    print("✅ AlphaGEX: Dynamic symbol selection enabled")
except ImportError:
    DYNAMIC_SELECTION_AVAILABLE = False
    print("⚠️ AlphaGEX: Dynamic selection not available, using static lists")
    # Mock dynamic selector for consistency
    class DynamicSymbolSelector:
        def __init__(self, *args):
            pass
        def get_symbols_for_scan_type(self, scan_type):
            return [], {}
        def get_fallback_symbols(self, scan_type):
            return []
        def get_market_regime(self):
            return "NEUTRAL"

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
        print("🚀 AlphaGEX: Starting application initialization...")
        
        self.initialize_session_state()
        print("✅ AlphaGEX: Session state initialized")
        
        self.api = TradingVolatilityAPI()
        print("✅ AlphaGEX: API client initialized")
        
        self.behavioral_engine = BehavioralEngine()
        print("✅ AlphaGEX: Behavioral engine initialized")
        
        self.visual_analyzer = VisualIntelligenceCoordinator()
        print("✅ AlphaGEX: Visual analyzer initialized")
        
        # Initialize dynamic selector if available
        if DYNAMIC_SELECTION_AVAILABLE:
            try:
                self.dynamic_selector = create_dynamic_selector(
                    HIGH_PRIORITY_SYMBOLS, 
                    MEDIUM_PRIORITY_SYMBOLS, 
                    EXTENDED_PRIORITY_SYMBOLS
                )
                print("✅ AlphaGEX: Dynamic selector initialized")
            except Exception as e:
                print(f"⚠️ AlphaGEX: Dynamic selector failed to initialize: {e}")
                self.dynamic_selector = None
        else:
            self.dynamic_selector = None
        
        self.check_system_status()
        print("✅ AlphaGEX: System status checked")
        
    def initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        if 'system_status' not in st.session_state:
            st.session_state.system_status = '🟡 Initializing'
            print("📊 AlphaGEX: System status set to initializing")
            
        if 'analysis_history' not in st.session_state:
            st.session_state.analysis_history = []
            print("📊 AlphaGEX: Analysis history initialized")
            
        if 'api_connected' not in st.session_state:
            st.session_state.api_connected = False
            print("📊 AlphaGEX: API connection status set to False")
            
        if 'api_username' not in st.session_state:
            st.session_state.api_username = ''
            print("📊 AlphaGEX: API username initialized as empty")
            
        if 'redis_status' not in st.session_state:
            st.session_state.redis_status = '🟡 Checking...'
            print("📊 AlphaGEX: Redis status set to checking")
            
        if 'current_analysis' not in st.session_state:
            st.session_state.current_analysis = None
            print("📊 AlphaGEX: Current analysis initialized")
            
        if 'scanner_results' not in st.session_state:
            st.session_state.scanner_results = []
            print("📊 AlphaGEX: Scanner results initialized")
            
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
            print("📊 AlphaGEX: Chat history initialized")
            
        if 'enable_dynamic_selection' not in st.session_state:
            st.session_state.enable_dynamic_selection = True
            print("📊 AlphaGEX: Dynamic selection preference initialized")
            
    def check_system_status(self):
        """Check and update system component status"""
        print("🔍 AlphaGEX: Checking system component status...")
        
        # Check Redis status
        try:
            import redis
            print("✅ AlphaGEX: Redis module imported successfully")
            
            try:
                r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
                r.ping()
                st.session_state.redis_status = '🟢 Connected'
                print("✅ AlphaGEX: Redis connection successful")
            except redis.ConnectionError:
                st.session_state.redis_status = '🟡 Mock Mode'
                print("⚠️ AlphaGEX: Redis not available, using mock mode")
            except Exception as e:
                st.session_state.redis_status = '🔴 Error'
                print(f"❌ AlphaGEX: Redis error: {str(e)}")
                
        except ImportError:
            st.session_state.redis_status = '🔴 Not Installed'
            print("❌ AlphaGEX: Redis not installed")
            
        # Check API configuration
        if st.session_state.get('api_username', '').strip():
            print(f"🔍 AlphaGEX: API username found: {st.session_state.api_username}")
            self.verify_api_connection()
        else:
            st.session_state.api_connected = False
            print("⚠️ AlphaGEX: No API username configured")
            
        st.session_state.system_status = '🟢 Online'
        print("✅ AlphaGEX: System status updated to online")
        
    def verify_api_connection(self):
        """Verify API connection with current credentials"""
        username = st.session_state.get('api_username', '').strip()
        
        if not username:
            print("⚠️ AlphaGEX: No username provided for API verification")
            st.session_state.api_connected = False
            return
            
        print(f"🔍 AlphaGEX: Verifying API connection for user: {username}")
        
        try:
            self.api.set_credentials(username)
            result = test_api_connection(username)
            print(f"📡 AlphaGEX: API test result: {result}")
            
            if result.get('status') == 'success':
                st.session_state.api_connected = True
                print("✅ AlphaGEX: API connection verified successfully")
            else:
                st.session_state.api_connected = False
                error_msg = result.get('message', 'Unknown error')
                print(f"❌ AlphaGEX: API connection failed: {error_msg}")
                
        except Exception as e:
            st.session_state.api_connected = False
            print(f"❌ AlphaGEX: API verification exception: {str(e)}")
            
    def render_header(self):
        """Render main application header"""
        print("🎨 AlphaGEX: Rendering header...")
        
        st.markdown(f'<h1 class="main-header">{APP_ICON} AlphaGEX</h1>', unsafe_allow_html=True)
        st.markdown("*Professional Gamma Exposure Trading Platform*")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            status = st.session_state.get('system_status', '🔴 Unknown')
            st.metric("System Status", status)
            print(f"📊 AlphaGEX: System Status displayed: {status}")
            
        with col2:
            redis_status = st.session_state.get('redis_status', '🔴 Unknown')
            st.metric("Redis Cache", redis_status)
            print(f"📊 AlphaGEX: Redis Status displayed: {redis_status}")
            
        with col3:
            analysis_count = len(st.session_state.get('analysis_history', []))
            st.metric("Analyses", analysis_count)
            print(f"📊 AlphaGEX: Analysis count displayed: {analysis_count}")
            
        with col4:
            is_connected = st.session_state.get('api_connected', False)
            has_username = bool(st.session_state.get('api_username', '').strip())
            
            print(f"🔍 AlphaGEX: API Debug - Connected: {is_connected}, Has Username: {has_username}")
            
            if is_connected and has_username:
                api_status = "🟢 Connected"
            elif has_username and not is_connected:
                api_status = "🔴 Failed"
            else:
                api_status = "🔴 Not Configured"
                
            st.metric("API Status", api_status)
            print(f"📊 AlphaGEX: API Status displayed: {api_status}")
            
    def render_sidebar(self):
        """Render sidebar with configuration options"""
        print("🎨 AlphaGEX: Rendering sidebar...")
        
        with st.sidebar:
            st.header("⚙️ Configuration")
            
            st.subheader("📡 TradingVolatility.net API")
            
            current_username = st.session_state.get('api_username', '')
            print(f"🔍 AlphaGEX: Current API username: '{current_username}'")
            
            username = st.text_input(
                "API Username", 
                value=current_username,
                help="Enter your TradingVolatility.net username",
                key="api_username_input"
            )
            
            username = username.strip() if username else ''
            if username != current_username:
                print(f"🔄 AlphaGEX: Username changed from '{current_username}' to '{username}'")
                st.session_state.api_username = username
                
                if username:
                    print(f"🔍 AlphaGEX: Testing new API credentials...")
                    
                    with st.spinner("Testing API connection..."):
                        self.verify_api_connection()
                        
                    if st.session_state.get('api_connected', False):
                        st.success("✅ API Connected!")
                        print("✅ AlphaGEX: API connection successful in sidebar")
                    else:
                        st.error("❌ API Connection Failed")
                        print("❌ AlphaGEX: API connection failed in sidebar")
                else:
                    st.session_state.api_connected = False
                    print("⚠️ AlphaGEX: API username cleared")
            
            if st.session_state.get('api_connected', False):
                st.success("🟢 API Status: Connected")
            elif st.session_state.get('api_username', '').strip():
                st.error("🔴 API Status: Failed")
            else:
                st.warning("🟡 API Status: Not Configured")
            
            if st.button("🔄 Test API Connection") and st.session_state.get('api_username', '').strip():
                print("🔍 AlphaGEX: Manual API test requested")
                with st.spinner("Testing connection..."):
                    self.verify_api_connection()
                st.rerun()
            
            st.subheader("⚙️ System Settings")
            
            st.selectbox(
                "Default Analysis Timeframe",
                options=["Intraday", "1-3 DTE", "1-2 Weeks"],
                index=1,
                key="default_timeframe"
            )
            
            max_position_size = st.slider(
                "Max Position Size (%)",
                min_value=1,
                max_value=10,
                value=3,
                help="Maximum percentage of capital per trade"
            )
            st.session_state['max_position_size'] = max_position_size / 100
            
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
            
            # Dynamic Selection Settings
            if DYNAMIC_SELECTION_AVAILABLE and self.dynamic_selector:
                st.subheader("🎯 Dynamic Selection")
                
                enable_dynamic = st.checkbox(
                    "Enable Dynamic Symbol Ranking",
                    value=st.session_state.get('enable_dynamic_selection', True),
                    help="Use market conditions to prioritize symbols"
                )
                st.session_state['enable_dynamic_selection'] = enable_dynamic
                
                if enable_dynamic:
                    # Show current market regime
                    try:
                        regime = self.dynamic_selector.get_market_regime()
                        if regime == "BEAR":
                            st.info(f"🐻 Market Regime: {regime} (emphasizing defensive stocks)")
                        elif regime == "HIGH_VOLATILITY":
                            st.warning(f"⚡ Market Regime: {regime} (prioritizing gamma candidates)")
                        elif regime == "BULL":
                            st.success(f"🐂 Market Regime: {regime} (tech leadership)")
                        else:
                            st.info(f"📊 Market Regime: {regime}")
                    except:
                        st.info("📊 Market Regime: Analysis pending")
                        
                    # Cache status
                    if (hasattr(self.dynamic_selector, 'last_update') and 
                        self.dynamic_selector.last_update and 
                        datetime.now() - self.dynamic_selector.last_update < self.dynamic_selector.cache_duration):
                        time_since_update = datetime.now() - self.dynamic_selector.last_update
                        st.success(f"🕒 Rankings cached ({time_since_update.total_seconds()/3600:.1f}h ago)")
                    else:
                        st.warning("🔄 Rankings will be refreshed on next scan")
            else:
                st.subheader("📋 Static Selection")
                st.info("Using predefined symbol lists")
            
            st.subheader("📊 System Status")
            
            if st.session_state.get('api_connected', False):
                st.success("🟢 API Connected")
            else:
                st.warning("🟡 API Not Configured")
                
            redis_status = st.session_state.get('redis_status', '🔴 Unknown')
            if '🟢' in redis_status:
                st.success(f"🟢 Redis: {redis_status}")
            elif '🟡' in redis_status:
                st.info(f"🟡 Redis: {redis_status}")
            else:
                st.error(f"🔴 Redis: {redis_status}")
                
            analysis_count = len(st.session_state.get('analysis_history', []))
            if analysis_count > 0:
                st.info(f"📈 {analysis_count} analyses performed")
            else:
                st.info("📊 No analyses yet")
                
            print("✅ AlphaGEX: Sidebar rendered successfully")
    
    def render_chart_analysis_tab(self):
        """Render the chart analysis tab"""
        print("🎨 AlphaGEX: Rendering chart analysis tab...")
        
        st.subheader("📊 GEX Chart Analysis & Symbol Deep Dive")
        
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
            print(f"🔍 AlphaGEX: Analysis requested for symbol: {symbol}")
            if not st.session_state.get('api_connected', False):
                st.error("❌ Please configure your API credentials in the sidebar first!")
                print("❌ AlphaGEX: Analysis blocked - API not configured")
            else:
                self.perform_symbol_analysis(symbol)
        
        st.subheader("📸 Upload GEX Chart for Visual Analysis")
        uploaded_file = st.file_uploader(
            "Choose a GEX profile chart image",
            type=['png', 'jpg', 'jpeg', 'gif', 'bmp'],
            help="Upload a GEX profile chart for automated pattern recognition"
        )
        
        if uploaded_file is not None:
            print("📸 AlphaGEX: Chart image uploaded for analysis")
            self.analyze_uploaded_chart(uploaded_file)
        
        if st.session_state.get('current_analysis'):
            print("📊 AlphaGEX: Displaying current analysis results")
            self.display_analysis_results(st.session_state.current_analysis)
        else:
            st.info("👆 Enter a symbol and click 'Analyze Symbol' to get started!")
    
    def render_copilot_chat_tab(self):
        """Render the AI co-pilot chat interface"""
        print("🎨 AlphaGEX: Rendering co-pilot chat tab...")
        
        st.subheader("💬 AlphaGEX AI Co-Pilot")
        st.info("🤖 Your intelligent trading assistant for GEX analysis and strategy suggestions")
        
        chat_container = st.container()
        
        with chat_container:
            chat_history = st.session_state.get('chat_history', [])
            print(f"💬 AlphaGEX: Displaying {len(chat_history)} chat messages")
            
            for i, message in enumerate(chat_history):
                if message['role'] == 'user':
                    st.markdown(f"**You:** {message['content']}")
                else:
                    st.markdown(f"**AlphaGEX:** {message['content']}")
                st.markdown("---")
        
        user_input = st.text_input(
            "Ask AlphaGEX about gamma exposure, market maker behavior, or trading strategies:",
            placeholder="e.g., 'What does high positive GEX mean for SPY?'",
            key="chat_input"
        )
        
        if st.button("💬 Send") and user_input:
            print(f"💬 AlphaGEX: Processing chat message: {user_input}")
            self.process_chat_message(user_input)
            st.rerun()
            
        st.subheader("🚀 Quick Actions")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("💡 Explain Current Market"):
                print("💡 AlphaGEX: Quick market explanation requested")
                self.quick_market_explanation()
                st.rerun()
                
        with col2:
            if st.button("🎯 Find Best Setups"):
                print("🎯 AlphaGEX: Best setups search requested")
                self.find_best_setups()
                st.rerun()
                
        with col3:
            if st.button("⚠️ Risk Check"):
                print("⚠️ AlphaGEX: Risk check requested")
                self.perform_risk_check()
                st.rerun()
                
        with col4:
            if st.button("📚 Trading Tips"):
                print("📚 AlphaGEX: Trading tips requested")
                self.show_trading_tips()
                st.rerun()
    
    def render_scanner_tab(self):
        """Render the live market scanner tab"""
        print("🎨 AlphaGEX: Rendering scanner tab...")
        
        st.subheader("🔍 Live 200+ Symbol GEX Scanner")
        st.info("🎯 Scanning for high-probability gamma exposure setups across 200+ symbols")
        
        if not st.session_state.get('api_connected', False):
            st.warning("⚠️ Scanner requires API configuration. Please set up your credentials in the sidebar.")
            return
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            scan_type = st.selectbox(
                "Scan Type",
                options=["All Symbols (200+)", "High Priority Only", "Custom List"],
                help="Select which symbols to scan"
            )
            
        with col2:
            if st.button("🚀 Start Scan", type="primary"):
                print(f"🔍 AlphaGEX: Market scan requested - Type: {scan_type}")
                self.run_market_scan(scan_type)
                
        with col3:
            auto_scan = st.checkbox("Auto Refresh (5min)", help="Automatically refresh scan results")
            if auto_scan:
                print("🔄 AlphaGEX: Auto-refresh enabled")
        
        scanner_results = st.session_state.get('scanner_results', [])
        if scanner_results:
            print(f"📊 AlphaGEX: Displaying {len(scanner_results)} scanner results")
            self.display_scanner_results()
            self.display_scanner_stats()
        else:
            st.info("👆 Click 'Start Scan' to begin scanning for GEX opportunities")
    
    def perform_symbol_analysis(self, symbol: str):
        """Perform comprehensive analysis of a specific symbol"""
        print(f"🔍 AlphaGEX: Starting comprehensive analysis for {symbol}")
        
        with st.spinner(f"Analyzing {symbol}... This may take a moment."):
            try:
                print(f"📡 AlphaGEX: Fetching GEX data for {symbol}")
                gex_result = self.api.get_net_gex(symbol)
                print(f"📡 AlphaGEX: GEX API result: {gex_result}")
                
                if gex_result.get('success', False):
                    print(f"✅ AlphaGEX: GEX data retrieved successfully for {symbol}")
                    
                    print(f"💰 AlphaGEX: Fetching price data for {symbol}")
                    price_data = self.get_price_data(symbol)
                    print(f"💰 AlphaGEX: Price data: {price_data}")
                    
                    print(f"🧠 AlphaGEX: Running behavioral analysis for {symbol}")
                    behavioral_analysis = self.behavioral_engine.analyze_mm_behavior(gex_result, price_data)
                    print(f"🧠 AlphaGEX: Behavioral analysis complete")
                    
                    print(f"👁️ AlphaGEX: Running visual analysis for {symbol}")
                    visual_analysis = self.visual_analyzer.process_gex_data_visually(gex_result)
                    print(f"👁️ AlphaGEX: Visual analysis complete")
                    
                    analysis = {
                        'symbol': symbol,
                        'timestamp': datetime.now(),
                        'gex_data': gex_result,
                        'price_data': price_data,
                        'behavioral_analysis': behavioral_analysis,
                        'visual_analysis': visual_analysis
                    }
                    
                    st.session_state.current_analysis = analysis
                    st.session_state.analysis_history.append(analysis)
                    print(f"✅ AlphaGEX: Analysis stored for {symbol}")
                    
                    st.success(f"✅ Analysis complete for {symbol}")
                    log_success(f"Completed analysis for {symbol}")
                    
                else:
                    error_msg = gex_result.get('error', 'Unknown API error')
                    st.error(f"❌ Failed to get GEX data for {symbol}: {error_msg}")
                    print(f"❌ AlphaGEX: GEX data fetch failed: {error_msg}")
                    log_error(f"GEX data fetch failed for {symbol}: {error_msg}")
                    
            except Exception as e:
                error_msg = str(e)
                st.error(f"❌ Analysis error: {error_msg}")
                print(f"❌ AlphaGEX: Analysis exception: {error_msg}")
                log_error(f"Symbol analysis error for {symbol}: {error_msg}")
    
    def analyze_uploaded_chart(self, uploaded_file):
        """Analyze an uploaded chart image"""
        print("📸 AlphaGEX: Starting chart image analysis")
        
        with st.spinner("Analyzing chart image..."):
            try:
                st.image(uploaded_file, caption="Uploaded GEX Chart", use_column_width=True)
                print("📸 AlphaGEX: Chart image displayed")
                
                visual_result = self.visual_analyzer.analyze_chart_image(uploaded_file)
                print(f"👁️ AlphaGEX: Visual analysis result: {visual_result}")
                
                if visual_result.get('success', True):
                    st.success("✅ Chart analysis complete!")
                    print("✅ AlphaGEX: Chart analysis successful")
                    
                    insights = visual_result.get('insights', [])
                    if insights:
                        st.subheader("🔍 Visual Analysis Insights")
                        for insight in insights:
                            st.write(f"• {insight}")
                            print(f"💡 AlphaGEX: Insight: {insight}")
                    
                    confidence = visual_result.get('confidence', 0)
                    st.metric("Analysis Confidence", f"{confidence:.1%}")
                    print(f"📊 AlphaGEX: Confidence score: {confidence:.1%}")
                    
                else:
                    st.warning("⚠️ Chart analysis had limited success")
                    print("⚠️ AlphaGEX: Chart analysis had limited success")
                    
            except Exception as e:
                error_msg = str(e)
                st.error(f"❌ Chart analysis error: {error_msg}")
                print(f"❌ AlphaGEX: Chart analysis exception: {error_msg}")
                log_error(f"Chart analysis error: {error_msg}")
    
    def display_analysis_results(self, analysis: Dict):
        """Display comprehensive analysis results"""
        print(f"📊 AlphaGEX: Displaying analysis results for {analysis.get('symbol', 'Unknown')}")
        
        st.subheader(f"📊 Analysis Results: {analysis['symbol']}")
        
        gex_data = analysis.get('gex_data', {})
        behavioral_data = analysis.get('behavioral_analysis', {})
        
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
        
        if net_gex > 1e9:
            st.markdown("""
            <div class="gex-positive">
                <strong>🛡️ Positive GEX Environment</strong><br>
                Market makers are long gamma, expecting range-bound price action.
                Consider premium selling strategies or iron condors.
            </div>
            """, unsafe_allow_html=True)
            print("📊 AlphaGEX: Displaying positive GEX environment analysis")
        elif net_gex < -1e9:
            st.markdown("""
            <div class="gex-negative">
                <strong>🔥 Negative GEX Environment</strong><br>
                Market makers are short gamma, expecting volatile price action.
                Look for squeeze setups and momentum plays.
            </div>
            """, unsafe_allow_html=True)
            print("📊 AlphaGEX: Displaying negative GEX environment analysis")
        else:
            st.info("📊 Neutral GEX environment - mixed signals")
            print("📊 AlphaGEX: Displaying neutral GEX environment analysis")
        
        signals = behavioral_data.get('signals', [])
        if signals:
            st.subheader("🎯 Trading Signals")
            print(f"🎯 AlphaGEX: Displaying {len(signals)} trading signals")
            for signal in signals:
                st.markdown(f"""
                <div class="signal-box">
                    <strong>{signal['type']}</strong><br>
                    <em>{signal['reason']}</em><br>
                    Confidence: {signal['confidence']:.1%} | Time Horizon: {signal['time_horizon']}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("🔍 No high-confidence signals detected at this time")
            print("🔍 AlphaGEX: No trading signals found")
    
    def get_price_data(self, symbol: str) -> Dict:
        """Get current price data for a symbol"""
        print(f"💰 AlphaGEX: Fetching price data for {symbol}")
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                daily_change = (hist['Close'].iloc[-1] - hist['Open'].iloc[0]) / hist['Open'].iloc[0]
                
                result = {
                    'current_price': current_price,
                    'daily_change': daily_change
                }
                print(f"💰 AlphaGEX: Price data retrieved - Price: ${current_price:.2f}, Change: {daily_change:.2%}")
                return result
            else:
                print(f"⚠️ AlphaGEX: No price data available for {symbol}")
                return {'current_price': 0, 'daily_change': 0}
                
        except Exception as e:
            print(f"❌ AlphaGEX: Price data fetch error for {symbol}: {str(e)}")
            log_error(f"Price data fetch error for {symbol}: {str(e)}")
            return {'current_price': 0, 'daily_change': 0}
    
    def process_chat_message(self, message: str):
        """Process a chat message from the user"""
        print(f"💬 AlphaGEX: Processing chat message: {message}")
        
        st.session_state.chat_history.append({'role': 'user', 'content': message})
        
        response = self.generate_ai_response(message)
        
        st.session_state.chat_history.append({'role': 'assistant', 'content': response})
        print("💬 AlphaGEX: Chat message processed and response generated")
    
    def generate_ai_response(self, message: str) -> str:
        """Generate AI response to user message"""
        print(f"🤖 AlphaGEX: Generating AI response for: {message}")
        
        message_lower = message.lower()
        
        if 'gex' in message_lower or 'gamma' in message_lower:
            return "Gamma Exposure (GEX) represents the dollar amount market makers need to hedge based on options positioning. High positive GEX suggests range-bound markets, while negative GEX indicates potential for explosive moves. Use our scanner to find current GEX opportunities!"
        elif 'squeeze' in message_lower:
            return "A gamma squeeze occurs when market makers are short gamma and must buy stock as prices rise, creating a feedback loop. Look for negative GEX environments near gamma flip points for squeeze setups. Our behavioral engine identifies these automatically!"
        elif 'strategy' in message_lower or 'trade' in message_lower:
            return "Based on current market conditions, I recommend focusing on the gamma regime. In positive GEX environments (>1B), consider premium selling. In negative GEX (<-1B), look for directional plays above/below the gamma flip. Check our analysis tab for specific setups!"
        elif 'api' in message_lower or 'configure' in message_lower:
            return "To get started, configure your TradingVolatility.net API credentials in the sidebar. This unlocks real-time GEX data and our full 200+ symbol scanner. Need help? Check the configuration section!"
        elif 'help' in message_lower:
            return "I'm AlphaGEX, your gamma exposure trading assistant! I can help you understand GEX analysis, find trading opportunities, and explain market maker behavior. Try asking about specific symbols, GEX levels, or trading strategies!"
        else:
            return "Great question! I'm here to help with gamma exposure analysis and trading strategies. Ask me about GEX levels, market maker behavior, specific symbols, or trading setups. You can also use our scanner to find opportunities across 200+ symbols!"
    
    def quick_market_explanation(self):
        """Provide quick market explanation"""
        print("💡 AlphaGEX: Generating quick market explanation")
        
        explanation = """
        📊 **Current Market Analysis:**
        
        • **GEX Environment**: Analyzing current gamma exposure levels across major indices
        • **Market Maker Positioning**: Evaluating dealer hedging requirements  
        • **Key Levels**: Identifying gamma flip points and wall levels
        • **Trade Setups**: Looking for high-probability opportunities
        
        **Next Steps**: Use the Chart Analysis tab for specific symbols or run the Scanner to find opportunities across 200+ symbols!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': explanation})
    
    def find_best_setups(self):
        """Find and display best current setups"""
        print("🎯 AlphaGEX: Finding best current setups")
        
        setup_analysis = """
        🎯 **Best Current Setups:**
        
        Based on gamma exposure analysis methodology:
        
        1. **SPY**: Check for squeeze setup if negative GEX detected
        2. **QQQ**: Monitor tech sector gamma positioning for breakout plays
        3. **High IV Names**: Look for premium selling opportunities in range-bound names
        4. **Meme Stocks**: Watch for gamma squeeze setups during high volatility periods
        
        **Action Items**: Run a full scan using our 200+ symbol scanner to get real-time opportunities with confidence scores!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': setup_analysis})
    
    def perform_risk_check(self):
        """Perform risk assessment"""
        print("⚠️ AlphaGEX: Performing risk check")
        
        risk_analysis = """
        ⚠️ **Risk Assessment & Management:**
        
        **Position Sizing Rules:**
        • Max 3% per squeeze play (high volatility)
        • Max 5% for premium selling strategies 
        • Max 2% portfolio loss for iron condors
        
        **Exit Rules:**
        • Stop losses at 50% loss for long options
        • Profit targets: 100% for directional, 50% for short premium
        • Time stops: Close positions with <1 DTE
        
        **Risk Factors:**
        • Gamma analysis is probabilistic, not guaranteed
        • Market conditions can change rapidly
        • Always maintain position size discipline
        
        **Current Settings**: Check your risk parameters in the sidebar configuration!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': risk_analysis})
    
    def show_trading_tips(self):
        """Show trading tips"""
        print("📚 AlphaGEX: Showing trading tips")
        
        tips = """
        📚 **AlphaGEX Professional Trading Tips:**
        
        **Core Principles:**
        1. **Follow the Gamma**: Let GEX levels guide your strategy selection
        2. **Respect the Walls**: Don't fight strong gamma concentration levels
        3. **Time is Everything**: Use expiration cycles to your advantage
        4. **Size Properly**: Risk management is key to long-term success
        5. **Stay Flexible**: Market regimes change - adapt your approach
        
        **Advanced Techniques:**
        • Watch for gamma flip breaches (high probability moves)
        • Monitor dealer positioning changes throughout the day
        • Combine multiple timeframes for better entries
        • Use our confidence scores to prioritize trades
        
        **Remember**: Consistent profitability comes from discipline, not prediction!
        """
        st.session_state.chat_history.append({'role': 'assistant', 'content': tips})
    
    def run_market_scan(self, scan_type: str):
        """Run real market scan with optional dynamic symbol selection"""
        print(f"🔍 AlphaGEX: Starting REAL market scan - Type: {scan_type}")
        
        if not st.session_state.get('api_connected', False):
            st.error("❌ API not connected. Cannot perform real scan.")
            return
        
        with st.spinner("Scanning market for real GEX opportunities..."):
            try:
                # Get symbols using dynamic selection if available and enabled
                if (self.dynamic_selector and DYNAMIC_SELECTION_AVAILABLE and 
                    st.session_state.get('enable_dynamic_selection', True)):
                    try:
                        symbols_to_scan, metadata = self.dynamic_selector.get_symbols_for_scan_type(scan_type)
                        
                        # Display dynamic selection info
                        market_regime = metadata.get('market_regime', 'NEUTRAL')
                        st.info(f"📊 Using dynamic selection: {market_regime} market regime detected")
                        print(f"🎯 AlphaGEX: Dynamic selection - Market regime: {market_regime}")
                        print(f"🎯 AlphaGEX: Top symbols: {symbols_to_scan[:10]}")
                        
                    except Exception as e:
                        print(f"⚠️ Dynamic selection failed: {e}, falling back to static lists")
                        if self.dynamic_selector:
                            symbols_to_scan = self.dynamic_selector.get_fallback_symbols(scan_type)
                        else:
                            symbols_to_scan = self._get_static_symbols(scan_type)
                        st.warning("⚠️ Using static symbol list (dynamic selection temporarily unavailable)")
                        
                else:
                    # Use static selection
                    symbols_to_scan = self._get_static_symbols(scan_type)
                    st.info("📋 Using static symbol selection")
                    
                print(f"🔍 AlphaGEX: Scanning {len(symbols_to_scan)} symbols")
                st.info(f"📊 Scanning {len(symbols_to_scan)} symbols - estimated time: {len(symbols_to_scan) * 3 / 60:.1f} minutes")
                
                # Rest of the scanning logic remains exactly the same
                results = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Rate limiting: 20 calls per minute = 1 call every 3 seconds
                call_delay = 3.0
                
                for i, symbol in enumerate(symbols_to_scan):
                    progress = (i + 1) / len(symbols_to_scan)
                    progress_bar.progress(progress)
                    status_text.text(f"Scanning {symbol}... ({i+1}/{len(symbols_to_scan)})")
                    
                    try:
                        # Make real API call
                        gex_result = self.api.get_net_gex(symbol)
                        
                        if gex_result.get('success', False):
                            net_gex = gex_result.get('net_gex', 0)
                            gamma_flip = gex_result.get('gamma_flip', 0)
                            current_price = gex_result.get('current_price', 0)
                            
                            # Analyze the real data for signals
                            signal_analysis = self._analyze_gex_for_signals(
                                symbol, net_gex, gamma_flip, current_price
                            )
                            
                            if signal_analysis['has_signal']:
                                results.append({
                                    'symbol': symbol,
                                    'signal_type': signal_analysis['signal_type'],
                                    'confidence': signal_analysis['confidence'],
                                    'net_gex': net_gex,
                                    'gamma_flip': gamma_flip,
                                    'current_price': current_price,
                                    'mm_state': signal_analysis['mm_state'],
                                    'reason': signal_analysis['reason'],
                                    'scan_time': datetime.now()
                                })
                                
                                print(f"🎯 AlphaGEX: REAL signal found for {symbol}: {signal_analysis['signal_type']} (confidence: {signal_analysis['confidence']:.1%})")
                        
                        else:
                            print(f"⚠️ AlphaGEX: Failed to get data for {symbol}: {gex_result.get('error', 'Unknown error')}")
                    
                    except Exception as e:
                        print(f"❌ AlphaGEX: Error scanning {symbol}: {str(e)}")
                    
                    # Rate limiting delay (except for last call)
                    if i < len(symbols_to_scan) - 1:
                        time.sleep(call_delay)
                
                progress_bar.empty()
                status_text.empty()
                
                st.session_state.scanner_results = results
                
                scan_summary = f"✅ Real scan complete! Found {len(results)} opportunities from {len(symbols_to_scan)} symbols scanned"
                st.success(scan_summary)
                print(f"✅ AlphaGEX: {scan_summary}")
                log_success(f"Real market scan completed: {len(results)} signals found from {len(symbols_to_scan)} symbols")
                
            except Exception as e:
                error_msg = str(e)
                st.error(f"❌ Scan error: {error_msg}")
                print(f"❌ AlphaGEX: Market scan exception: {error_msg}")
                log_error(f"Market scan error: {error_msg}")

    def _get_static_symbols(self, scan_type: str) -> List[str]:
        """Get static symbol list based on scan type"""
        if scan_type == "High Priority Only":
            return HIGH_PRIORITY_SYMBOLS[:50]
        elif scan_type == "Custom List":
            return HIGH_PRIORITY_SYMBOLS[:20]  
        else:
            # Use full static universe
            return FULL_SYMBOL_UNIVERSE[:200]

    def _analyze_gex_for_signals(self, symbol: str, net_gex: float, gamma_flip: float, current_price: float) -> Dict:
        """Analyze real GEX data for trading signals"""
        
        # GEX thresholds (adjust based on symbol)
        if symbol in ['SPY']:
            pos_threshold = 2e9
            neg_threshold = -1e9
        elif symbol in ['QQQ']:
            pos_threshold = 1e9  
            neg_threshold = -500e6
        else:
            pos_threshold = 500e6
            neg_threshold = -200e6
        
        # Calculate distance to gamma flip
        if current_price > 0 and gamma_flip > 0:
            distance_to_flip = abs(current_price - gamma_flip) / current_price
        else:
            distance_to_flip = 1.0  # No valid flip point
        
        # Signal detection logic
        signal_analysis = {
            'has_signal': False,
            'signal_type': 'NONE',
            'confidence': 0.0,
            'mm_state': 'NEUTRAL',
            'reason': 'No significant signal detected'
        }
        
        # Negative GEX squeeze setups
        if net_gex < neg_threshold and distance_to_flip < 0.02:  # Within 2% of flip
            signal_analysis.update({
                'has_signal': True,
                'signal_type': 'SQUEEZE_SETUP',
                'confidence': min(0.9, abs(net_gex) / abs(neg_threshold)),
                'mm_state': 'TRAPPED',
                'reason': f'Negative GEX ({net_gex/1e9:.2f}B) near gamma flip'
            })
        
        # High positive GEX premium selling
        elif net_gex > pos_threshold:
            signal_analysis.update({
                'has_signal': True,
                'signal_type': 'SELL_PREMIUM',
                'confidence': min(0.85, net_gex / (pos_threshold * 2)),
                'mm_state': 'DEFENDING',
                'reason': f'High positive GEX ({net_gex/1e9:.2f}B) - range bound expected'
            })
        
        # Iron condor opportunities  
        elif pos_threshold * 0.5 < net_gex < pos_threshold:
            signal_analysis.update({
                'has_signal': True,
                'signal_type': 'IRON_CONDOR',
                'confidence': 0.65,
                'mm_state': 'STABILIZING',
                'reason': f'Moderate positive GEX ({net_gex/1e9:.2f}B) - defined range likely'
            })
        
        return signal_analysis
        
    def display_scanner_results(self):
        """Display scanner results in a formatted table"""
        scanner_results = st.session_state.get('scanner_results', [])
        if not scanner_results:
            return
            
        print(f"📊 AlphaGEX: Displaying {len(scanner_results)} scanner results")
        
        st.subheader(f"📊 Scan Results ({len(scanner_results)} signals)")
        
        df = pd.DataFrame(scanner_results)
        
        display_df = df.copy()
        display_df['Confidence'] = display_df['confidence'].apply(lambda x: f"{x:.1%}")
        display_df['Net GEX'] = display_df['net_gex'].apply(lambda x: f"${x/1e9:.2f}B")
        display_df['Current Price'] = display_df['current_price'].apply(lambda x: f"${x:.2f}" if x > 0 else "N/A")
        display_df['Reason'] = display_df['reason'].apply(lambda x: x[:50] + "..." if len(x) > 50 else x)
        
        display_columns = {
            'symbol': 'Symbol',
            'signal_type': 'Signal Type', 
            'Confidence': 'Confidence',
            'Net GEX': 'Net GEX',
            'mm_state': 'MM State',
            'Current Price': 'Price',
            'Reason': 'Analysis'
        }
        
        st.dataframe(
            display_df[list(display_columns.keys())].rename(columns=display_columns),
            use_container_width=True,
            hide_index=True
        )
        
        print("✅ AlphaGEX: Scanner results table displayed")
        
    def display_scanner_stats(self):
        """Display comprehensive scanner statistics"""
        scanner_results = st.session_state.get('scanner_results', [])
        if not scanner_results:
            return
            
        print("📊 AlphaGEX: Displaying scanner statistics")
        
        st.subheader("📈 Scan Statistics")
        
        total_signals = len(scanner_results)
        high_conf_signals = sum(1 for r in scanner_results if r['confidence'] > 0.75)
        avg_confidence = np.mean([r['confidence'] for r in scanner_results])
        negative_gex_count = sum(1 for r in scanner_results if r['net_gex'] < 0)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Signals", total_signals)
            
        with col2:
            st.metric("High Confidence", f"{high_conf_signals} ({high_conf_signals/total_signals:.1%})")
            
        with col3:
            st.metric("Avg Confidence", f"{avg_confidence:.1%}")
            
        with col4:
            st.metric("Negative GEX", f"{negative_gex_count} ({negative_gex_count/total_signals:.1%})")
        
        signal_types = {}
        for result in scanner_results:
            signal_type = result['signal_type']
            signal_types[signal_type] = signal_types.get(signal_type, 0) + 1
        
        if signal_types:
            st.subheader("🎯 Signal Type Distribution")
            for signal_type, count in signal_types.items():
                percentage = count / total_signals
                st.write(f"**{signal_type}**: {count} signals ({percentage:.1%})")
        
        print("✅ AlphaGEX: Scanner statistics displayed")
    
    def run(self):
        """Main application run method"""
        print("🚀 AlphaGEX: Starting main application run...")
        
        st.session_state.system_status = '🟢 Online'
        
        self.render_header()
        self.render_sidebar()
        
        tab1, tab2, tab3 = st.tabs(["📊 Chart Analysis", "💬 AlphaGEX Co-Pilot", "🔍 Live Scanner"])
        
        with tab1:
            self.render_chart_analysis_tab()
        
        with tab2:
            self.render_copilot_chat_tab()
