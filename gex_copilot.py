"""
main.py - Main Streamlit Application for AlphaGEX
Professional Options Intelligence Platform
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

# Direct imports without reload - significant performance improvement
# Module reloading was causing 6,600 lines of code to reload on every interaction
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
# Removed: Intraday tracking feature (not needed)
# from intraday_tracking import (
#     IntradayTracker,
#     display_intraday_dashboard,
#     display_snapshot_widget,
#     get_intraday_summary
# )
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
# PERFORMANCE OPTIMIZATION: CACHED HELPER FUNCTIONS
# ============================================================================

@st.cache_data(ttl=60)  # Cache for 60 seconds
def get_todays_pnl(db_path: str) -> float:
    """Get today's P&L from database with caching to reduce DB queries"""
    conn = sqlite3.connect(db_path)
    try:
        today_pnl_query = pd.read_sql_query(
            "SELECT SUM(pnl) as total FROM positions WHERE DATE(closed_at) = DATE('now')",
            conn
        )
        return today_pnl_query.iloc[0]['total'] if not today_pnl_query.empty and today_pnl_query.iloc[0]['total'] is not None else 0.0
    finally:
        conn.close()

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_yesterday_data_cached(symbol: str, api_client_id: int) -> dict:
    """Cached wrapper for yesterday's data to prevent redundant API calls

    Args:
        symbol: Stock symbol
        api_client_id: ID of the API client (to bust cache when client changes)

    Returns:
        Yesterday's GEX data
    """
    # Note: We pass api_client_id to make the cache key unique per client instance
    # but we need to get the actual client from session state
    if 'api_client' in st.session_state:
        return st.session_state.api_client.get_yesterday_data(symbol)
    return {}

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="AlphaGEX - Options Intelligence",
    page_icon="⚡",
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

    # PROFESSIONAL CSS DESIGN SYSTEM v2.0 - Premium Trading Platform
    st.markdown("""
    <style>
    /* ============================================================
       ALPHAGEX PROFESSIONAL DESIGN SYSTEM
       Premium Trading Intelligence Platform
       ============================================================ */

    /* Core Theme - Ultra Professional Dark */
    .stApp {
        background: radial-gradient(ellipse at top, #0f1419 0%, #0a0e14 50%, #060810 100%);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    /* Enhanced Sidebar with Glassmorphism */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(15, 20, 25, 0.95) 0%, rgba(26, 31, 46, 0.95) 100%);
        border-right: 1px solid rgba(0, 212, 255, 0.15);
        backdrop-filter: blur(20px);
    }

    [data-testid="stSidebar"] > div:first-child {
        background: transparent;
    }

    /* Professional Metric Cards - Enhanced */
    [data-testid="stMetricValue"] {
        font-size: 34px !important;
        font-weight: 900 !important;
        color: #00D4FF !important;
        text-shadow: 0 0 30px rgba(0, 212, 255, 0.4);
        letter-spacing: -1px;
    }

    [data-testid="stMetricDelta"] {
        font-size: 14px !important;
        font-weight: 700 !important;
        padding: 4px 10px;
        border-radius: 6px;
        background: rgba(0, 0, 0, 0.4);
    }

    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
        font-weight: 700 !important;
        color: #8b92a7 !important;
        text-transform: uppercase;
        letter-spacing: 1.2px;
    }

    /* Premium Card Styling */
    .stMarkdown div[data-testid="stMarkdownContainer"] > p {
        font-size: 15px;
        line-height: 1.8;
        color: #d4d8e1;
    }

    /* Elite Button System */
    .stButton>button {
        background: linear-gradient(135deg, #0099ff 0%, #00d4ff 100%);
        color: white;
        font-weight: 800;
        font-size: 13px;
        border: none;
        border-radius: 12px;
        padding: 0.8rem 1.8rem;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        text-transform: uppercase;
        letter-spacing: 1px;
        box-shadow: 0 6px 20px rgba(0, 153, 255, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }

    .stButton>button:hover {
        transform: translateY(-4px) scale(1.02);
        box-shadow: 0 10px 30px rgba(0, 212, 255, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.2);
        background: linear-gradient(135deg, #00aff5 0%, #00e4ff 100%);
    }

    .stButton>button:active {
        transform: translateY(-2px) scale(1.01);
    }

    /* Primary Button - Success Variant */
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #00ff88 0%, #00d4a1 100%);
        box-shadow: 0 6px 20px rgba(0, 255, 136, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.15);
    }

    .stButton>button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1aff98 0%, #00e4b1 100%);
        box-shadow: 0 10px 30px rgba(0, 255, 136, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.25);
    }

    /* Premium Tab Navigation - Compact & Desktop Optimized */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: linear-gradient(135deg, rgba(10, 14, 20, 0.98) 0%, rgba(20, 25, 35, 0.98) 100%);
        padding: 6px;
        border-radius: 14px;
        border: 1px solid rgba(0, 212, 255, 0.2);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05);
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        display: flex !important;
    }

    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 10px;
        color: #6b7280;
        font-weight: 700;
        font-size: 11px;
        padding: 12px 16px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        white-space: nowrap;
        flex-shrink: 0;
    }

    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(0, 212, 255, 0.08);
        color: #9ca3af;
        transform: translateY(-1px);
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #0099ff 0%, #00d4ff 100%) !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(0, 212, 255, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.2);
    }

    /* Mobile responsive tabs */
    @media (max-width: 768px) {
        .stTabs [data-baseweb="tab"] {
            font-size: 10px;
            padding: 10px 12px;
        }
    }

    /* Luxury Expander Design */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, rgba(0, 212, 255, 0.1) 0%, rgba(0, 153, 204, 0.1) 100%);
        border-radius: 14px;
        border: 2px solid rgba(0, 212, 255, 0.3);
        font-weight: 800;
        font-size: 14px;
        color: #00D4FF;
        padding: 18px 24px;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
    }

    .streamlit-expanderHeader:hover {
        border-color: rgba(0, 212, 255, 0.7);
        background: linear-gradient(135deg, rgba(0, 212, 255, 0.15) 0%, rgba(0, 153, 204, 0.15) 100%);
        box-shadow: 0 6px 25px rgba(0, 212, 255, 0.3);
        transform: translateY(-2px);
    }

    /* Executive DataFrames */
    .stDataFrame {
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid rgba(0, 212, 255, 0.25);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }

    .stDataFrame [data-testid="stDataFrameResizable"] {
        background: rgba(10, 14, 20, 0.7);
    }

    /* Stunning Header Design with Animated Gradient */
    .main-header {
        background: linear-gradient(135deg, #00D4FF 0%, #0099ff 20%, #0066cc 40%, #0099ff 60%, #00D4FF 80%, #00ffff 100%);
        background-size: 300% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 62px;
        font-weight: 900;
        text-align: center;
        margin-bottom: 12px;
        letter-spacing: 4px;
        animation: shimmer-text 10s ease-in-out infinite;
        filter: drop-shadow(0 0 40px rgba(0, 212, 255, 0.6));
    }

    @keyframes shimmer-text {
        0%, 100% {
            background-position: 0% 50%;
        }
        50% {
            background-position: 100% 50%;
        }
    }

    .sub-header {
        text-align: center;
        font-size: 15px;
        font-weight: 700;
        color: #6b7280;
        margin-bottom: 40px;
        letter-spacing: 3px;
        text-transform: uppercase;
    }

    /* Premium Alert Cards with Glassmorphism */
    .stAlert {
        border-radius: 14px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 18px 24px;
        backdrop-filter: blur(15px);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }

    div[data-baseweb="notification"] {
        border-radius: 14px;
        border-left: 5px solid;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }

    /* Elite Text Input */
    .stTextInput>div>div>input {
        background: rgba(10, 14, 20, 0.9);
        border: 2px solid rgba(0, 212, 255, 0.25);
        border-radius: 12px;
        color: white;
        font-weight: 700;
        font-size: 15px;
        padding: 14px 18px;
        transition: all 0.3s ease;
    }

    .stTextInput>div>div>input:focus {
        border-color: #00D4FF;
        box-shadow: 0 0 0 4px rgba(0, 212, 255, 0.15), 0 0 20px rgba(0, 212, 255, 0.3);
        background: rgba(10, 14, 20, 1);
    }

    /* Advanced Premium Animations */
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes fadeInUp {
        from {
            transform: translateY(40px);
            opacity: 0;
        }
        to {
            transform: translateY(0);
            opacity: 1;
        }
    }

    @keyframes shimmer {
        0% {
            background-position: -1200px 0;
        }
        100% {
            background-position: 1200px 0;
        }
    }

    @keyframes glow {
        0%, 100% {
            box-shadow: 0 0 25px rgba(0, 212, 255, 0.6);
        }
        50% {
            box-shadow: 0 0 50px rgba(0, 212, 255, 0.9);
        }
    }

    .fade-in-up {
        animation: fadeInUp 0.8s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .slide-in-right {
        animation: slideInRight 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* Elite Hover Effects */
    .hover-lift {
        transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .hover-lift:hover {
        transform: translateY(-8px) scale(1.02);
        box-shadow: 0 16px 40px rgba(0, 212, 255, 0.5);
    }

    /* Success notification with enhanced bounce */
    @keyframes notify {
        0%, 100% {
            transform: translateY(0) scale(1);
        }
        10%, 30%, 50%, 70%, 90% {
            transform: translateY(-14px) scale(1.03);
        }
        20%, 40%, 60%, 80% {
            transform: translateY(-7px) scale(1.015);
        }
    }

    .notification {
        animation: notify 3s ease-in-out;
    }

    /* Premium shimmer effect with color */
    .shimmer {
        background: linear-gradient(90deg,
            rgba(255,255,255,0) 0%,
            rgba(255,255,255,0.08) 25%,
            rgba(0,212,255,0.25) 50%,
            rgba(255,255,255,0.08) 75%,
            rgba(255,255,255,0) 100%
        );
        background-size: 250% 100%;
        animation: shimmer 3.5s ease-in-out infinite;
    }

    /* Pulsing dot with enhanced glow */
    .pulse-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #00FF88;
        box-shadow: 0 0 0 0 rgba(0, 255, 136, 0.8);
        animation: pulse-ring 2.5s ease-out infinite;
    }

    @keyframes pulse-ring {
        0% {
            box-shadow: 0 0 0 0 rgba(0, 255, 136, 0.8), 0 0 10px rgba(0, 255, 136, 0.6);
        }
        40% {
            box-shadow: 0 0 0 12px rgba(0, 255, 136, 0.4), 0 0 15px rgba(0, 255, 136, 0.4);
        }
        100% {
            box-shadow: 0 0 0 25px rgba(0, 255, 136, 0), 0 0 20px rgba(0, 255, 136, 0);
        }
    }

    /* Professional Number Input */
    .stNumberInput>div>div>input {
        background: rgba(10, 14, 20, 0.9);
        border: 2px solid rgba(0, 212, 255, 0.25);
        border-radius: 12px;
        color: white;
        font-weight: 700;
        font-size: 15px;
        padding: 14px 18px;
    }

    /* Premium Slider */
    .stSlider>div>div>div>div {
        background: linear-gradient(90deg, #0099ff 0%, #00d4ff 100%);
        box-shadow: 0 2px 10px rgba(0, 212, 255, 0.4);
    }

    .stSlider>div>div>div>div:hover {
        box-shadow: 0 2px 15px rgba(0, 212, 255, 0.6);
    }

    /* Selectbox Enhancement */
    .stSelectbox>div>div>div {
        background: rgba(10, 14, 20, 0.9);
        border: 2px solid rgba(0, 212, 255, 0.25);
        border-radius: 12px;
        font-weight: 600;
    }

    /* Luxury Scrollbar */
    ::-webkit-scrollbar {
        width: 14px;
        height: 14px;
    }

    ::-webkit-scrollbar-track {
        background: rgba(10, 14, 20, 0.6);
        border-radius: 12px;
    }

    ::-webkit-scrollbar-thumb {
        background: linear-gradient(135deg, #0099ff 0%, #00d4ff 100%);
        border-radius: 12px;
        box-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
    }

    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(135deg, #00aff5 0%, #00e4ff 100%);
        box-shadow: 0 0 15px rgba(0, 212, 255, 0.7);
    }

    /* Professional Divider with Glow */
    hr {
        margin: 2.5rem 0;
        border: none;
        height: 2px;
        background: linear-gradient(90deg,
            transparent 0%,
            rgba(0, 212, 255, 0.5) 50%,
            transparent 100%
        );
        box-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
    }

    /* Premium Status Badges */
    .status-badge {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 24px;
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .status-active {
        background: linear-gradient(135deg, rgba(0, 255, 136, 0.25) 0%, rgba(0, 212, 161, 0.25) 100%);
        border: 2px solid rgba(0, 255, 136, 0.6);
        color: #00FF88;
        box-shadow: 0 4px 15px rgba(0, 255, 136, 0.3);
    }

    .status-warning {
        background: linear-gradient(135deg, rgba(255, 184, 0, 0.25) 0%, rgba(255, 153, 0, 0.25) 100%);
        border: 2px solid rgba(255, 184, 0, 0.6);
        color: #FFB800;
        box-shadow: 0 4px 15px rgba(255, 184, 0, 0.3);
    }

    .status-error {
        background: linear-gradient(135deg, rgba(255, 68, 68, 0.25) 0%, rgba(255, 34, 34, 0.25) 100%);
        border: 2px solid rgba(255, 68, 68, 0.6);
        color: #FF4444;
        box-shadow: 0 4px 15px rgba(255, 68, 68, 0.3);
    }

    /* Professional Code Blocks */
    .stCodeBlock {
        border-radius: 12px;
        border: 1px solid rgba(0, 212, 255, 0.2);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }

    /* Enhanced Spinner */
    .stSpinner > div {
        border-top-color: #00D4FF !important;
        border-right-color: #00D4FF !important;
    }
    </style>

    <div class="main-header">
    ⚡ AlphaGEX
    </div>
    <div class="sub-header">
    Professional Options Intelligence Platform
    </div>
    """, unsafe_allow_html=True)
    
    # Premium Top Metrics Row - Executive Dashboard Style
    col1, col2, col3, col4, col5 = st.columns(5, gap="medium")

    with col1:
        st.markdown("""
<div class='hover-lift' style='background: linear-gradient(135deg, rgba(0,212,255,0.18) 0%, rgba(0,153,204,0.12) 100%);
            padding: 24px; border-radius: 16px;
            border: 2px solid rgba(0,212,255,0.4);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 120px; height: 120px; max-height: 120px;
            display: flex; flex-direction: column; justify-content: space-between;
            box-sizing: border-box; overflow: hidden;'>
    <div style='color: rgba(255,255,255,0.6); font-size: 14px;'>System Status</div>
    <div style='color: white; font-size: 24px; font-weight: 600; line-height: 1.2;'>🟢 ACTIVE</div>
    <div style='color: rgba(255,255,255,0.5); font-size: 14px; visibility: hidden;'>placeholder</div>
</div>
        """, unsafe_allow_html=True)

    with col2:
        positions_count = len(st.session_state.active_positions)
        st.markdown(f"""
<div class='hover-lift' style='background: linear-gradient(135deg, rgba(255,184,0,0.18) 0%, rgba(255,153,0,0.12) 100%);
            padding: 24px; border-radius: 16px;
            border: 2px solid rgba(255,184,0,0.4);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 120px; height: 120px; max-height: 120px;
            display: flex; flex-direction: column; justify-content: space-between;
            box-sizing: border-box; overflow: hidden;'>
    <div style='color: rgba(255,255,255,0.6); font-size: 14px;'>Active Positions</div>
    <div style='color: white; font-size: 24px; font-weight: 600; line-height: 1.2;'>{positions_count}</div>
    <div style='color: rgba(255,255,255,0.5); font-size: 14px; visibility: hidden;'>placeholder</div>
</div>
        """, unsafe_allow_html=True)

    with col3:
        # Calculate today's P&L (cached for 60 seconds)
        today_pnl = get_todays_pnl(DB_PATH)
        pnl_color = "rgba(0,255,136,0.18)" if today_pnl >= 0 else "rgba(255,68,68,0.18)"
        pnl_color2 = "rgba(0,255,136,0.12)" if today_pnl >= 0 else "rgba(255,68,68,0.12)"
        pnl_border = "rgba(0,255,136,0.5)" if today_pnl >= 0 else "rgba(255,68,68,0.5)"
        pnl_delta_color = "#00FF88" if today_pnl >= 0 else "#FF4444"
        pnl_arrow = "▲" if today_pnl >= 0 else "▼"
        st.markdown(f"""
<div class='hover-lift' style='background: linear-gradient(135deg, {pnl_color} 0%, {pnl_color2} 100%);
            padding: 24px; border-radius: 16px;
            border: 2px solid {pnl_border};
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 120px; height: 120px; max-height: 120px;
            display: flex; flex-direction: column; justify-content: space-between;
            box-sizing: border-box; overflow: hidden;'>
    <div style='color: rgba(255,255,255,0.6); font-size: 14px;'>Today's P&L</div>
    <div style='color: white; font-size: 24px; font-weight: 600; line-height: 1.2;'>${today_pnl:,.2f}</div>
    <div style='color: {pnl_delta_color}; font-size: 14px;'>{pnl_arrow} ${abs(today_pnl):,.2f}</div>
</div>
        """, unsafe_allow_html=True)

    with col4:
        # Always use Central Time for Texas-based user
        user_tz = 'US/Central'
        local_time = get_local_time(user_tz)
        et_time = get_et_time()
        market_status = "🟢 OPEN" if is_market_open() else "🔴 CLOSED"

        current_time = f"{local_time.strftime('%I:%M %p')} CT"
        market_open = is_market_open()
        time_color = "rgba(0,255,136,0.18)" if market_open else "rgba(255,68,68,0.18)"
        time_color2 = "rgba(0,255,136,0.12)" if market_open else "rgba(255,68,68,0.12)"
        time_border = "rgba(0,255,136,0.5)" if market_open else "rgba(255,68,68,0.5)"
        st.markdown(f"""
<div class='hover-lift' style='background: linear-gradient(135deg, {time_color} 0%, {time_color2} 100%);
            padding: 24px; border-radius: 16px;
            border: 2px solid {time_border};
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 120px; height: 120px; max-height: 120px;
            display: flex; flex-direction: column; justify-content: space-between;
            box-sizing: border-box; overflow: hidden;'>
    <div style='color: rgba(255,255,255,0.6); font-size: 14px;'>Market Time</div>
    <div style='color: white; font-size: 24px; font-weight: 600; line-height: 1.2;'>{current_time}</div>
    <div style='color: {"#00FF88" if market_open else "#FF4444"}; font-size: 14px;'>{market_status}</div>
</div>
        """, unsafe_allow_html=True)

    with col5:
        # Use Central Time for day of week
        day = local_time.strftime('%A')
        day_quality = "🟢" if day in ['Monday', 'Tuesday'] else "🟡" if day == 'Wednesday' else "🔴"
        st.markdown(f"""
<div class='hover-lift' style='background: linear-gradient(135deg, rgba(138,43,226,0.18) 0%, rgba(75,0,130,0.12) 100%);
            padding: 24px; border-radius: 16px;
            border: 2px solid rgba(138,43,226,0.4);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            min-height: 120px; height: 120px; max-height: 120px;
            display: flex; flex-direction: column; justify-content: space-between;
            box-sizing: border-box; overflow: hidden;'>
    <div style='color: rgba(255,255,255,0.6); font-size: 14px;'>Trading Day</div>
    <div style='color: white; font-size: 24px; font-weight: 600; line-height: 1.2;'>{day_quality} {day}</div>
    <div style='color: rgba(255,255,255,0.5); font-size: 14px;'>{'Best' if day in ['Monday', 'Tuesday'] else 'Good' if day == 'Wednesday' else 'Caution'}</div>
</div>
        """, unsafe_allow_html=True)
    
    # Sidebar Configuration
    with st.sidebar:
        st.header("⚙️ Configuration")

        # AI Status Indicator (no test button)
        # Check environment variables first (for Render), then secrets (for local)
        import os
        claude_api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
        if not claude_api_key:
            try:
                claude_api_key = st.secrets.get("claude_api_key", "")
            except:
                claude_api_key = ""

        if claude_api_key:
            st.success("🤖 **AI Copilot:** ✅ ACTIVE")
        else:
            st.warning("🤖 **AI Copilot:** ⚠️ BASIC MODE")

        # API Usage Stats
        if 'api_client' in st.session_state:
            stats = st.session_state.api_client.get_api_usage_stats()

            with st.expander("📊 API Usage (This Session)", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Calls", stats['total_calls'])
                with col2:
                    st.metric("This Minute", stats['calls_this_minute'])

                st.caption(f"🗃️ Cache: {stats['cache_size']} entries (30s)")
                st.caption(f"⏱️ Minute resets in: {stats['time_until_minute_reset']}s")

                # Color indicator based on usage
                if stats['calls_this_minute'] < 10:
                    st.success("🟢 Normal usage")
                elif stats['calls_this_minute'] < 20:
                    st.warning("🟡 Moderate usage")
                else:
                    st.error("🔴 Heavy usage - slow down!")

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

                        # SKIP skew data to save API calls (reduces calls from 2-3 to just 1 per refresh)
                        # Skew data is nice-to-have but not critical for core GEX analysis
                        # This dramatically reduces API usage and prevents rate limit errors
                        skew_data = {}  # Skip for now - can add back as optional button later

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

        # Quick symbols - responsive layout for mobile
        st.caption("Quick Select:")
        # Use 2x2 grid for better mobile display
        col1, col2 = st.columns(2)
        with col1:
            if st.button('SPY', use_container_width=True, key='btn_spy'):
                st.session_state.selected_symbol = 'SPY'
                st.rerun()
            if st.button('IWM', use_container_width=True, key='btn_iwm'):
                st.session_state.selected_symbol = 'IWM'
                st.rerun()
        with col2:
            if st.button('QQQ', use_container_width=True, key='btn_qqq'):
                st.session_state.selected_symbol = 'QQQ'
                st.rerun()
            if st.button('DIA', use_container_width=True, key='btn_dia'):
                st.session_state.selected_symbol = 'DIA'
                st.rerun()

        st.divider()

        # Alert Monitoring Widget
        if st.session_state.current_data:
            display_alert_monitor_widget(st.session_state.current_data.get('gex', {}))

        # Position Monitoring Widget
        display_position_monitoring_widget()

        st.divider()

        # Timezone is fixed to Central Time (Texas)
        if 'user_timezone' not in st.session_state:
            st.session_state.user_timezone = 'US/Central'
        st.session_state.user_timezone = 'US/Central'  # Always use Central Time

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

        st.divider()

        # Professional Navigation Guide
        st.markdown("""
<div style='background: linear-gradient(135deg, rgba(0, 212, 255, 0.1) 0%, rgba(0, 153, 204, 0.08) 100%);
            padding: 16px; border-radius: 12px;
            border: 1px solid rgba(0, 212, 255, 0.25);
            margin-bottom: 15px;'>
    <div style='color: #00D4FF; font-weight: 800; font-size: 13px; margin-bottom: 12px; text-align: center;'>
        🗺️ QUICK NAVIGATION GUIDE
    </div>
    <div style='color: #d4d8e1; font-size: 11px; line-height: 1.7;'>
        <div style='margin-bottom: 10px;'>
            <strong style='color: #00FF88;'>📊 Analysis & Data:</strong><br>
            <span style='color: #8b92a7;'>GEX Analysis • Trade Setups • Scanner • Plans</span>
        </div>
        <div style='margin-bottom: 10px;'>
            <strong style='color: #FFB800;'>🤖 AI & Automation:</strong><br>
            <span style='color: #8b92a7;'>AI Assistant • Auto Trader • Alerts</span>
        </div>
        <div>
            <strong style='color: #8888FF;'>📈 Tracking & Learning:</strong><br>
            <span style='color: #8b92a7;'>Positions • Trade Journal • Education</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

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
        "🤖 AI Assistant",
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
            # Analysis header with live indicator
            st.markdown(f"""
            <div style='display: flex; align-items: center; gap: 10px; margin-bottom: 20px;'>
                <h2 style='margin: 0; color: white;'>🎯 {current_symbol} - Current Market Analysis</h2>
                <div class='pulse-dot'></div>
                <span style='color: #00FF88; font-size: 12px; font-weight: 600;'>LIVE</span>
            </div>
            """, unsafe_allow_html=True)

            # Show data timestamp
            current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            st.caption(f"📅 Data as of: {current_time}")

            # Current Analysis Metrics
            gex_data = data.get('gex', {})

            # ROW 1: Core Metrics (Net GEX, Price, Flip Point)
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                net_gex = gex_data.get('net_gex', 0)
                st.metric(
                    "Net GEX",
                    f"${net_gex/1e9:.2f}B",
                    delta="Negative" if net_gex < 0 else "Positive",
                    delta_color="inverse" if net_gex < 0 else "normal"
                )

            with col2:
                spot = gex_data.get('spot_price', 0)
                st.metric("Current Price", f"${spot:.2f}")

            with col3:
                flip = gex_data.get('flip_point', 0)
                st.metric(
                    "Flip Point",
                    f"${flip:.2f}",
                    delta=f"{((flip-spot)/spot*100):+.2f}%" if spot != 0 else "N/A"
                )

            with col4:
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)
                if call_wall and put_wall:
                    wall_range = call_wall - put_wall
                    st.metric("Wall Range", f"${wall_range:.2f}",
                             delta=f"${put_wall:.2f} → ${call_wall:.2f}")

            # ROW 2: Market Maker State + Key Support/Resistance
            col1, col2 = st.columns([1, 1])

            with col1:
                st.markdown("### 🏦 Market Maker State")
                claude = ClaudeIntelligence()
                mm_state = claude._determine_mm_state(net_gex)
                state_config = MM_STATES[mm_state]

                st.info(f"""
                **State: {mm_state}**
                {state_config['behavior']}

                **Recommended Action:**
                {state_config['action']}
                """)

            with col2:
                st.markdown("### 📍 Key Support & Resistance")

                # Show walls and flip in organized way
                metrics_col1, metrics_col2 = st.columns(2)

                with metrics_col1:
                    if put_wall:
                        st.metric("📉 Put Wall (Support)", f"${put_wall:.2f}")
                    st.metric("🔄 Gamma Flip", f"${flip:.2f}")

                with metrics_col2:
                    if call_wall:
                        st.metric("📈 Call Wall (Resistance)", f"${call_wall:.2f}")
                    if spot:
                        position_vs_flip = "Above ✅" if spot > flip else "Below ⚠️"
                        st.metric("Position vs Flip", position_vs_flip)

            st.divider()

            # Display GEX Profile Chart with STD Movement
            st.subheader(f"📊 GEX Profile")

            # Fetch yesterday's data using Streamlit cache (5-minute TTL)
            # This replaces the manual session state caching with proper @st.cache_data
            yesterday_data = get_yesterday_data_cached(current_symbol, id(st.session_state.api_client))

            if data.get('profile'):
                visualizer = GEXVisualizer()
                # Add flip_point and STD levels from GEX data to profile for chart consistency
                profile_with_levels = data['profile'].copy()
                profile_with_levels['flip_point'] = gex_data.get('flip_point', 0)
                profile_with_levels['spot_price'] = gex_data.get('spot_price', 0)

                # Add ±1 STD levels if available
                if 'std_1_pos' in gex_data:
                    profile_with_levels['std_1_pos'] = gex_data.get('std_1_pos', 0)
                    profile_with_levels['std_1_neg'] = gex_data.get('std_1_neg', 0)

                # Pass yesterday_data for STD movement tracking (None if not requested)
                fig = visualizer.create_gex_profile(profile_with_levels, yesterday_data)
                st.plotly_chart(fig, use_container_width=True, key="gex_profile_chart")
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
            # SECTION 1.5: DAILY EXPIRATION GEX TRACKER (0DTE Trading)
            # ==================================================================
            st.divider()
            st.header(f"⏰ Daily Expiration Gamma Tracker - 0DTE Opportunities")

            # Get current day of week and time
            from datetime import datetime
            import pytz

            # Always use Central Time
            user_tz = 'US/Central'
            current_time = datetime.now(pytz.timezone(user_tz))
            day_of_week = current_time.strftime('%A')
            hour = current_time.hour
            minute = current_time.minute

            # Daily expiration schedule for major tickers (VERIFIED AS OF 2024)
            # Note: CBOE expanded daily (0DTE) options to major ETFs in recent years
            daily_exp_schedule = {
                'SPY': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],  # 5 days - Daily 0DTE
                'QQQ': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],  # 5 days - Daily 0DTE
                'IWM': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],  # 5 days - Daily 0DTE
                'SPX': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],  # 5 days - Daily 0DTE
                'XSP': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],  # 5 days - Mini-SPX Daily
                'DIA': ['Monday', 'Wednesday', 'Friday'],  # 3 days - MWF schedule
                'EEM': ['Friday'],  # 1 day - Weekly only (standard monthlies + weeklies)
                'TLT': ['Friday'],  # 1 day - Weekly only
                'GLD': ['Friday'],  # 1 day - Weekly only
                'SLV': ['Friday'],  # 1 day - Weekly only
            }

            # Check if current symbol has daily expirations
            has_daily_exp = current_symbol in daily_exp_schedule
            exp_days = daily_exp_schedule.get(current_symbol, [])

            if has_daily_exp:
                # ==================================================================
                # GAMMA EXPIRATION INTELLIGENCE - Fetch real data from API
                # ==================================================================

                # Fetch GEX levels for precise strike selection
                gex_levels = st.session_state.api_client.get_gex_levels(current_symbol)

                # Debug: Check if we got valid data
                if gex_levels:
                    # Check if all values are zero
                    all_zero = all(v == 0 for k, v in gex_levels.items() if k != 'symbol')
                    if all_zero:
                        st.warning(f"⚠️ GEX Levels API returned all zeros for {current_symbol}. The API may not have data for this symbol yet.")
                        gex_levels = None  # Treat as no data to hide the display

                # =================================================================
                # NEW GAMMA EXPIRATION INTELLIGENCE - 3 VIEWS + STRATEGIES
                # =================================================================

                st.markdown("### 📊 Gamma Expiration Intelligence - Current Week Only")

                # Mobile optimization CSS
                st.markdown("""
                <style>
                /* Mobile responsive design for gamma intelligence */
                @media (max-width: 768px) {
                    /* Stack columns vertically on mobile */
                    div[data-testid="column"] {
                        width: 100% !important;
                        flex: 100% !important;
                    }

                    /* Smaller fonts on mobile */
                    .stMarkdown h4 {
                        font-size: 18px !important;
                    }

                    /* Reduce padding on mobile */
                    div[style*="padding: 16px"] {
                        padding: 12px !important;
                    }

                    /* Collapsible sections on mobile */
                    details {
                        margin-bottom: 12px;
                    }

                    summary {
                        cursor: pointer;
                        font-weight: 700;
                        padding: 10px;
                        background: rgba(0, 212, 255, 0.1);
                        border-radius: 8px;
                        margin-bottom: 8px;
                    }
                }
                </style>
                """, unsafe_allow_html=True)

                # Get current VIX for context-aware adjustments (if available)
                current_vix = 0
                try:
                    import yfinance as yf
                    vix_data = yf.Ticker("^VIX").history(period="1d")
                    if not vix_data.empty:
                        current_vix = float(vix_data['Close'].iloc[-1])
                except:
                    current_vix = 0

                # Fetch comprehensive gamma intelligence
                with st.spinner("🔬 Analyzing current week's gamma structure..."):
                    gamma_intel = st.session_state.api_client.get_current_week_gamma_intelligence(
                        current_symbol,
                        current_vix=current_vix
                    )

                if gamma_intel.get('success'):
                    # Display week info
                    week_info = f"**Week of {gamma_intel['week_start']} to {gamma_intel['week_end']}** | Today: **{gamma_intel['current_day']}**"
                    if gamma_intel.get('edge_case'):
                        if gamma_intel['edge_case'] == 'WEEKEND':
                            week_info += " | 🔶 Weekend - Showing Next Week"
                        elif gamma_intel['edge_case'] == 'FRIDAY_AFTER_CLOSE':
                            week_info += " | 🔴 After Hours - Week Complete"

                    st.markdown(week_info)
                    st.divider()

                    # =================================================================
                    # VIEW 1: DAILY IMPACT (Today → Tomorrow)
                    # =================================================================

                    daily = gamma_intel['daily_impact']

                    st.markdown("#### ⚡ VIEW 1: TODAY'S IMPACT (Intraday Trading)")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Current Gamma", f"${daily['today_total_gamma']/1e9:.2f}B",
                                 help="Total gamma supporting market right now")
                    with col2:
                        st.metric("After 4pm", f"${daily['tomorrow_total_gamma']/1e9:.2f}B",
                                 help="Gamma remaining after today's expiration")
                    with col3:
                        delta_display = f"-${daily['expiring_today']/1e9:.2f}B ({daily['impact_pct']:.0f}%)"
                        st.metric("Loss Today", delta_display, delta_color="inverse",
                                 help=f"{daily['risk_level']} risk level")

                    # Risk level indicator
                    risk_html = f"""
                    <div style='background: linear-gradient(135deg, {daily['risk_color']}20 0%, {daily['risk_color']}10 100%);
                                padding: 16px; border-radius: 12px; border: 2px solid {daily['risk_color']};
                                margin: 16px 0;'>
                        <div style='color: {daily['risk_color']}; font-size: 14px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;'>
                            🎯 RISK LEVEL: {daily['risk_level']}
                        </div>
                        <div style='color: #d4d8e1; font-size: 12px;'>
                            {' | '.join(daily['context_notes']) if daily['context_notes'] else 'Standard thresholds applied'}
                        </div>
                    </div>
                    """
                    st.markdown(risk_html, unsafe_allow_html=True)

                    # Money-making strategies for View 1
                    st.markdown("**💰 HOW TO PROFIT TODAY:**")

                    for strategy in daily['strategies']:
                        priority_color = {'HIGH': '#FF4444', 'MEDIUM': '#FFB800', 'LOW': '#00D4FF'}[strategy['priority']]

                        strategy_html = f"""
                        <div style='background: rgba(20, 25, 35, 0.6); padding: 14px; border-radius: 10px;
                                    border-left: 4px solid {priority_color}; margin-bottom: 12px;'>
                            <div style='color: {priority_color}; font-size: 13px; font-weight: 700; margin-bottom: 8px;'>
                                {strategy['priority']} PRIORITY: {strategy['name']}
                            </div>
                            <div style='color: #d4d8e1; font-size: 11px; line-height: 1.6;'>
                                <strong>Strategy:</strong> {strategy['description']}<br>
                                <strong>Strike:</strong> {strategy['strike']}<br>
                                <strong>Expiration:</strong> {strategy['expiration']}<br>
                                <strong>Entry:</strong> {strategy['entry_time']}<br>
                                <strong>Exit:</strong> {strategy['exit_time']}<br>
                                <strong>Risk:</strong> {strategy['risk']} | <strong>Size:</strong> {strategy['position_size']}<br>
                                <strong style='color: #00D4FF;'>Why:</strong> {strategy['rationale']}
                            </div>
                        </div>
                        """
                        st.markdown(strategy_html, unsafe_allow_html=True)

                    st.divider()

                    # =================================================================
                    # VIEW 2: WEEKLY EVOLUTION (Monday → Friday)
                    # =================================================================

                    weekly = gamma_intel['weekly_evolution']

                    st.markdown("#### 📅 VIEW 2: WEEKLY EVOLUTION (Positional Trading)")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Monday Baseline", f"${weekly['monday_baseline']/1e9:.2f}B")
                    with col2:
                        st.metric("Friday End", f"${weekly['friday_end']/1e9:.2f}B")
                    with col3:
                        st.metric("Total Decay", f"{weekly['total_decay_pct']:.0f}%",
                                 delta=f"{weekly['decay_pattern']}", delta_color="off")

                    # Weekly progression chart
                    st.markdown("**Week's Gamma Structure:**")

                    for day in weekly['daily_breakdown']:
                        is_today = day['is_today']
                        bar_width = int(day['pct_of_week'])
                        bar_color = '#00D4FF' if is_today else '#4a5568'

                        day_html = f"""
                        <div style='margin-bottom: 10px;'>
                            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;'>
                                <span style='color: {"#00D4FF" if is_today else "#8b92a7"}; font-size: 12px; font-weight: {"800" if is_today else "600"};'>
                                    {"📍 " if is_today else ""}{day['day']} {day['date']}
                                </span>
                                <span style='color: #d4d8e1; font-size: 11px;'>
                                    ${day['cumulative_gamma']/1e9:.1f}B ({day['pct_of_week']:.0f}%)
                                </span>
                            </div>
                            <div style='background: rgba(30,35,45,0.5); border-radius: 6px; height: 20px; overflow: hidden;'>
                                <div style='background: {bar_color}; width: {bar_width}%; height: 100%; transition: width 0.3s;'></div>
                            </div>
                        </div>
                        """
                        st.markdown(day_html, unsafe_allow_html=True)

                    # Weekly strategies
                    st.markdown("**💰 HOW TO PROFIT THIS WEEK:**")

                    for phase, strategy in weekly['strategies'].items():
                        strategy_html = f"""
                        <div style='background: rgba(0, 212, 255, 0.08); padding: 14px; border-radius: 10px;
                                    border: 1px solid rgba(0, 212, 255, 0.3); margin-bottom: 12px;'>
                            <div style='color: #00D4FF; font-size: 13px; font-weight: 700; margin-bottom: 8px;'>
                                {strategy['name']}
                            </div>
                            <div style='color: #d4d8e1; font-size: 11px; line-height: 1.6;'>
                                <strong>Description:</strong> {strategy['description']}<br>
                                {f"<strong>Strategy:</strong> {strategy.get('strategy_type', 'N/A')}<br>" if 'strategy_type' in strategy else ""}
                                {f"<strong>Strikes:</strong> {strategy.get('strikes', 'N/A')}<br>" if 'strikes' in strategy else ""}
                                {f"<strong>Expiration:</strong> {strategy.get('expiration', 'N/A')}<br>" if 'expiration' in strategy else ""}
                                {f"<strong>Entry:</strong> {strategy.get('entry_time', 'N/A')}<br>" if 'entry_time' in strategy else ""}
                                {f"<strong>Exit:</strong> {strategy.get('exit_time', 'N/A')}<br>" if 'exit_time' in strategy else ""}
                                {f"<strong>Size:</strong> {strategy.get('position_size', 'N/A')}<br>" if 'position_size' in strategy else ""}
                                {f"<strong>Mon-Tue:</strong> {strategy.get('monday_tuesday', 'N/A')}<br>" if 'monday_tuesday' in strategy else ""}
                                {f"<strong>Wed:</strong> {strategy.get('wednesday', 'N/A')}<br>" if 'wednesday' in strategy else ""}
                                {f"<strong>Thu-Fri:</strong> {strategy.get('thursday_friday', 'N/A')}<br>" if 'thursday_friday' in strategy else ""}
                                <strong style='color: #00D4FF;'>Why:</strong> {strategy['rationale']}
                            </div>
                        </div>
                        """
                        st.markdown(strategy_html, unsafe_allow_html=True)

                    st.divider()

                    # =================================================================
                    # VIEW 3: VOLATILITY POTENTIAL (Risk Calendar)
                    # =================================================================

                    vol = gamma_intel['volatility_potential']

                    st.markdown("#### ⚠️ VIEW 3: VOLATILITY CLIFFS (Risk Management)")

                    st.markdown("**Relative Expiration Risk by Day:**")

                    for day in vol['by_day']:
                        risk_icon = {'LOW': '✅', 'MODERATE': '⚠️', 'HIGH': '🔶', 'EXTREME': '🚨'}[day['risk_level']]

                        day_html = f"""
                        <div style='background: {day['risk_color']}15; padding: 12px; border-radius: 8px;
                                    border-left: 4px solid {day['risk_color']}; margin-bottom: 8px;'>
                            <div style='display: flex; justify-content: space-between; align-items: center;'>
                                <div>
                                    <span style='color: {day['risk_color']}; font-size: 12px; font-weight: 700;'>
                                        {risk_icon} {day['day_name']} {day['date']} {"📍 TODAY" if day['is_today'] else ""}
                                    </span>
                                </div>
                                <div style='text-align: right;'>
                                    <span style='color: {day['risk_color']}; font-size: 16px; font-weight: 900;'>
                                        {day['vol_pct']:.0f}%
                                    </span>
                                    <span style='color: #8b92a7; font-size: 10px;'> {day['risk_level']}</span>
                                </div>
                            </div>
                        </div>
                        """
                        st.markdown(day_html, unsafe_allow_html=True)

                    # Highest risk day strategies
                    if vol['highest_risk_day'] and vol['strategies']:
                        st.markdown(f"**💰 STRATEGIES FOR HIGHEST RISK DAY ({vol['highest_risk_day']['day_name']}):**")

                        for strategy in vol['strategies']:
                            priority_color = {'HIGH': '#FF4444', 'MEDIUM': '#FFB800', 'LOW': '#00D4FF'}[strategy['priority']]

                            strategy_html = f"""
                            <div style='background: rgba(255, 68, 68, 0.08); padding: 14px; border-radius: 10px;
                                        border: 1px solid {priority_color}; margin-bottom: 12px;'>
                                <div style='color: {priority_color}; font-size: 13px; font-weight: 700; margin-bottom: 8px;'>
                                    {strategy['priority']} PRIORITY: {strategy['name']}
                                </div>
                                <div style='color: #d4d8e1; font-size: 11px; line-height: 1.6;'>
                                    <strong>Strategy:</strong> {strategy['description']}<br>
                                    <strong>Type:</strong> {strategy['strategy_type']}<br>
                                    <strong>Strike:</strong> {strategy['strike']}<br>
                                    <strong>Expiration:</strong> {strategy['expiration']}<br>
                                    <strong>Entry:</strong> {strategy['entry_time']}<br>
                                    <strong>Exit:</strong> {strategy['exit_time']}<br>
                                    <strong>Risk:</strong> {strategy['risk']} | <strong>Size:</strong> {strategy['position_size']}<br>
                                    <strong style='color: #00D4FF;'>Why:</strong> {strategy['rationale']}
                                </div>
                            </div>
                            """
                            st.markdown(strategy_html, unsafe_allow_html=True)

                    st.divider()

                    # Research footnote
                    st.markdown("""
                    <div style='background: rgba(0, 212, 255, 0.05); padding: 12px; border-radius: 8px;
                                border-left: 3px solid #00D4FF; margin-top: 20px;'>
                        <div style='color: #00D4FF; font-size: 11px; font-weight: 700; margin-bottom: 6px;'>
                            📚 EVIDENCE-BASED THRESHOLDS
                        </div>
                        <div style='color: #8b92a7; font-size: 10px; line-height: 1.5;'>
                            Thresholds based on: Academic research (Dim, Eraker, Vilkov 2023), SpotGamma professional analysis,
                            ECB Financial Stability Review 2023, and validated production trading data.
                            Context-aware adjustments for Friday expirations and high-VIX environments.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                else:
                    # Error or no data
                    st.warning(f"⚠️ Could not load gamma intelligence: {gamma_intel.get('error', 'Unknown error')}")
                    st.info("Using fallback analysis...")

                st.divider()

            if has_daily_exp:
                # Check if today is an expiration day
                is_expiration_day = day_of_week in exp_days

                # Market phases
                market_closed = hour < 9 or (hour == 9 and minute < 30) or hour >= 16
                morning_session = 9 <= hour < 12 and minute >= 30 if hour == 9 else True
                afternoon_session = 12 <= hour < 16

                # Calculate gamma regime based on day of week and time
                st.markdown(f"""
                <div style='background: linear-gradient(135deg, rgba(0, 212, 255, 0.15) 0%, rgba(0, 153, 204, 0.1) 100%);
                            padding: 24px; border-radius: 16px; border: 2px solid rgba(0, 212, 255, 0.3);
                            margin-bottom: 20px;'>
                    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;'>
                        <div>
                            <div style='color: #00D4FF; font-size: 14px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;'>
                                {day_of_week} | {current_time.strftime('%I:%M %p')} {user_tz.split('/')[-1]}
                            </div>
                            <div style='color: {'#00FF88' if is_expiration_day else '#FFB800'}; font-size: 20px; font-weight: 900; margin-top: 8px;'>
                                {'🔴 EXPIRATION DAY' if is_expiration_day else '🟢 NON-EXPIRATION DAY'}
                            </div>
                        </div>
                        <div style='text-align: right;'>
                            <div style='color: #8b92a7; font-size: 11px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;'>
                                Daily Exp Schedule
                            </div>
                            <div style='color: white; font-size: 13px; font-weight: 700;'>
                                {' • '.join(exp_days)}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Gamma Decay Timeline
                st.markdown("### 📊 Weekly Gamma Decay Pattern")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown("""
                    <div style='background: linear-gradient(135deg, rgba(0, 255, 136, 0.15) 0%, rgba(0, 153, 102, 0.1) 100%);
                                padding: 16px; border-radius: 12px; border: 2px solid rgba(0, 255, 136, 0.3);'>
                        <div style='color: #00FF88; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;'>
                            🟢 HIGH GAMMA DAYS
                        </div>
                        <div style='color: white; font-size: 13px; font-weight: 700; margin-bottom: 12px;'>
                            Monday - Tuesday
                        </div>
                        <div style='color: #d4d8e1; font-size: 11px; line-height: 1.6;'>
                            <strong>Gamma Effect:</strong> Maximum dealer hedging<br>
                            <strong>Volatility:</strong> Suppressed (range-bound)<br>
                            <strong>Strategy:</strong> Iron Condors, Theta harvesting
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with col2:
                    st.markdown("""
                    <div style='background: linear-gradient(135deg, rgba(255, 184, 0, 0.15) 0%, rgba(204, 147, 0, 0.1) 100%);
                                padding: 16px; border-radius: 12px; border: 2px solid rgba(255, 184, 0, 0.3);'>
                        <div style='color: #FFB800; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;'>
                            🟡 MID GAMMA DAYS
                        </div>
                        <div style='color: white; font-size: 13px; font-weight: 700; margin-bottom: 12px;'>
                            Wednesday
                        </div>
                        <div style='color: #d4d8e1; font-size: 11px; line-height: 1.6;'>
                            <strong>Gamma Effect:</strong> Moderate decay begins<br>
                            <strong>Volatility:</strong> Increasing<br>
                            <strong>Strategy:</strong> Vertical spreads, directional plays
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with col3:
                    st.markdown("""
                    <div style='background: linear-gradient(135deg, rgba(255, 68, 68, 0.15) 0%, rgba(204, 54, 54, 0.1) 100%);
                                padding: 16px; border-radius: 12px; border: 2px solid rgba(255, 68, 68, 0.3);'>
                        <div style='color: #FF4444; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;'>
                            🔴 LOW GAMMA DAYS
                        </div>
                        <div style='color: white; font-size: 13px; font-weight: 700; margin-bottom: 12px;'>
                            Thursday - Friday
                        </div>
                        <div style='color: #d4d8e1; font-size: 11px; line-height: 1.6;'>
                            <strong>Gamma Effect:</strong> Massive decay<br>
                            <strong>Volatility:</strong> High (breakout potential)<br>
                            <strong>Strategy:</strong> 0DTE Straddles, Long Gamma
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                # Actionable Trade Playbook
                st.divider()
                st.markdown("### 🎯 Actionable Trade Playbook - Today's Opportunity")

                # Determine today's strategy based on day of week and current GEX
                net_gex = gex_data.get('net_gex', 0)
                net_gex_billions = net_gex / 1e9
                spot = gex_data.get('spot_price', 0)
                flip = gex_data.get('flip_point', 0)

                # Build trade recommendation based on day and GEX structure
                trade_recommendations = []

                if day_of_week in ['Monday', 'Tuesday']:
                    # High Gamma Period - Range Bound Strategies
                    if net_gex > 2e9:
                        trade_recommendations.append({
                            'title': '🟢 Iron Condor - High Probability Income',
                            'scenario': 'High positive GEX + Early week = Maximum range compression',
                            'strategy': 'Iron Condor',
                            'entry_timing': 'Market open (9:30 AM ET) - Capture morning theta',
                            'structure': f"""
                            **Sell Call Spread:** ${spot + 2:.2f} / ${spot + 4:.2f}
                            **Sell Put Spread:** ${spot - 2:.2f} / ${spot - 4:.2f}
                            **Expiration:** This Friday (Weekly)
                            **Credit Target:** $0.40 - $0.60 per contract
                            """,
                            'profit_target': 'Close at 50% max profit or Thursday 3 PM',
                            'stop_loss': 'Exit if price breaches flip point or touches a short strike',
                            'position_size': '1-2% of account per side (2-4% total)',
                            'edge': 'Dealers will pin price between strikes through Friday, theta decay accelerates Wed-Fri'
                        })
                    else:
                        trade_recommendations.append({
                            'title': '🟡 Vertical Spread - Directional with Protection',
                            'scenario': 'Neutral GEX + Early week = Moderate volatility',
                            'strategy': 'Bull Put Spread' if spot > flip else 'Bear Call Spread',
                            'entry_timing': 'Wait for morning volatility to settle (10:30 AM ET)',
                            'structure': f"""
                            **Direction:** {'Bullish' if spot > flip else 'Bearish'} (Price {'above' if spot > flip else 'below'} flip)
                            **Sell Strike:** ${(spot - 1.5) if spot > flip else (spot + 1.5):.2f}
                            **Buy Strike:** ${(spot - 3) if spot > flip else (spot + 3):.2f}
                            **Expiration:** This Friday (Weekly)
                            **Credit Target:** $0.50 - $0.80 per contract
                            """,
                            'profit_target': 'Close at 60% max profit or Thursday 2 PM',
                            'stop_loss': 'Exit if GEX flips or price approaches flip point',
                            'position_size': '2-3% of account',
                            'edge': 'Moderate gamma allows controlled directional movement'
                        })

                elif day_of_week == 'Wednesday':
                    # Mid-week - Transition Period
                    if is_expiration_day:
                        trade_recommendations.append({
                            'title': '⏰ 0DTE Decay Play - Wednesday Expiration',
                            'scenario': 'Wednesday 0DTE expiration + Gamma decay begins',
                            'strategy': 'Short 0DTE Iron Fly (if high IV) or Calendar Spread',
                            'entry_timing': 'Morning: 10:00 AM - 11:00 AM ET',
                            'structure': f"""
                            **ATM Short Iron Fly:**
                            **Sell Call:** ${spot + 0.5:.2f}
                            **Sell Put:** ${spot - 0.5:.2f}
                            **Buy Call:** ${spot + 2:.2f}
                            **Buy Put:** ${spot - 2:.2f}
                            **Expiration:** TODAY (0DTE)
                            **Credit Target:** $0.80 - $1.20 per contract
                            """,
                            'profit_target': 'Hold until 3:30 PM or 75% profit',
                            'stop_loss': 'Exit if price moves $2+ from entry or at $150 loss per contract',
                            'position_size': '1% of account (higher risk due to 0DTE)',
                            'edge': 'Theta decay accelerates exponentially in final hours, gamma decay increases volatility'
                        })
                    else:
                        trade_recommendations.append({
                            'title': '📈 Volatility Expansion Play',
                            'scenario': 'Mid-week + Gamma decay starting = Volatility increases',
                            'strategy': 'Long Call/Put Spread or Butterfly',
                            'entry_timing': 'Early morning (9:45 AM - 10:15 AM ET) before volatility spike',
                            'structure': f"""
                            **Long Butterfly (Cheap Lotto):**
                            **Buy Call:** ${spot + 2:.2f}
                            **Sell 2x Call:** ${spot + 4:.2f}
                            **Buy Call:** ${spot + 6:.2f}
                            **Expiration:** This Friday (Weekly)
                            **Debit:** $0.20 - $0.40 per contract
                            """,
                            'profit_target': 'Close when price reaches body strikes or 200% profit',
                            'stop_loss': 'Let it expire worthless (defined risk)',
                            'position_size': '0.5% of account (lottery ticket)',
                            'edge': 'As gamma decays Thu/Fri, volatility will expand - cheap asymmetric bet'
                        })

                elif day_of_week in ['Thursday', 'Friday']:
                    # Low Gamma Period - High Volatility Strategies
                    if is_expiration_day:
                        if hour < 14:  # Before 2 PM
                            trade_recommendations.append({
                                'title': '🔥 0DTE Straddle - Volatility Explosion',
                                'scenario': f'{day_of_week} Expiration + Massive gamma decay = Volatility spike',
                                'strategy': 'Long 0DTE ATM Straddle',
                                'entry_timing': '9:30 AM - 10:30 AM ET (Early to capture full move)',
                                'structure': f"""
                                **Buy ATM Call:** ${spot:.2f} strike
                                **Buy ATM Put:** ${spot:.2f} strike
                                **Expiration:** TODAY (0DTE)
                                **Debit:** $1.50 - $2.50 per straddle
                                **Breakevens:** ${spot - 2:.2f} / ${spot + 2:.2f}
                                """,
                                'profit_target': 'Exit when either leg is ITM by $2+ OR at 1:00 PM ET',
                                'stop_loss': 'Exit at 11:30 AM if no movement (down 30-40%) or at $100 loss per straddle',
                                'position_size': '1-2% of account (aggressive but defined risk)',
                                'edge': 'Low gamma = dealers stop hedging = big intraday moves. Friday afternoon typically sees 1-2% swings'
                            })
                        else:
                            trade_recommendations.append({
                                'title': '⚡ Final Hour Scalp - Pure Theta',
                                'scenario': 'Final trading hour + 0DTE = Extreme theta decay',
                                'strategy': 'Sell OTM 0DTE options (directional)',
                                'entry_timing': '3:00 PM - 3:30 PM ET',
                                'structure': f"""
                                **Sell OTM Option:**
                                **Strike:** ${(spot + 2) if net_gex < 0 else (spot - 2):.2f}
                                **Premium:** $0.10 - $0.25 per contract
                                **Expiration:** TODAY (0DTE - expires in 1-1.5 hours!)
                                """,
                                'profit_target': 'Hold until 3:55 PM or worthless',
                                'stop_loss': 'Exit immediately if price moves toward strike ($30 loss max)',
                                'position_size': '0.5% of account (very aggressive)',
                                'edge': 'Theta decay is $0.10-0.15 per 10 minutes in final hour - collect pennies but high win rate'
                            })
                    else:
                        trade_recommendations.append({
                            'title': '💥 Gamma Squeeze Setup - Big Move Ahead',
                            'scenario': f'{day_of_week} + Low gamma = Next expiration day will see explosive move',
                            'strategy': 'Long Straddle or Strangle (Weekly expiration)',
                            'entry_timing': 'Afternoon (2:00 PM - 3:00 PM ET) - Position for next day',
                            'structure': f"""
                            **Long Weekly Straddle:**
                            **Buy Call:** ${spot:.2f} (ATM)
                            **Buy Put:** ${spot:.2f} (ATM)
                            **Expiration:** Next Friday (Weekly)
                            **Debit:** $3.00 - $4.50 per straddle
                            """,
                            'profit_target': 'Hold through next expiration day volatility, exit when 50% ITM',
                            'stop_loss': 'Exit Monday if no movement by 11 AM (gamma rebuilds)',
                            'position_size': '2% of account',
                            'edge': 'Gamma vacuum into next Monday expiration = dealers will be forced to hedge aggressively = big move'
                        })

                elif day_of_week in ['Saturday', 'Sunday']:
                    trade_recommendations.append({
                        'title': '📚 Weekend Planning - Prepare for Monday',
                        'scenario': 'Markets closed - Use this time to analyze',
                        'strategy': 'Pre-Market Setup',
                        'entry_timing': 'Monday market open (9:30 AM ET)',
                        'structure': """
                        **Weekend Checklist:**
                        1. Review Friday's closing GEX levels
                        2. Identify key support/resistance from last week
                        3. Check Monday's economic calendar (high impact events?)
                        4. Plan Iron Condor strikes based on expected high-gamma range
                        5. Set alerts for flip point breaches
                        """,
                        'profit_target': 'N/A - Planning phase',
                        'stop_loss': 'N/A - Planning phase',
                        'position_size': 'Review account balance and adjust sizing rules',
                        'edge': 'Monday typically opens with maximum gamma = tight range = perfect for IC setup'
                    })

                # Display trade recommendations
                for i, trade in enumerate(trade_recommendations):
                    with st.expander(f"📊 {trade['title']}", expanded=(i == 0)):
                        col1, col2 = st.columns([2, 1])

                        with col1:
                            st.markdown(f"**📍 Current Market Scenario:**")
                            st.info(trade['scenario'])

                            st.markdown(f"**💼 Strategy:** {trade['strategy']}")
                            st.markdown(f"**⏰ Entry Timing:** {trade['entry_timing']}")

                            st.markdown("**📋 Trade Structure:**")
                            st.markdown(f"""
<div style='background: linear-gradient(135deg, rgba(0, 212, 255, 0.12) 0%, rgba(0, 153, 204, 0.08) 100%);
            padding: 16px; border-radius: 10px; border-left: 4px solid #00D4FF; margin: 10px 0;'>
    <div style='color: white; font-size: 14px; line-height: 1.8; white-space: pre-wrap; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;'>{trade['structure']}</div>
</div>
                            """, unsafe_allow_html=True)

                        with col2:
                            st.markdown("**🎯 Exit Rules:**")
                            st.success(f"**Target:** {trade['profit_target']}")
                            st.error(f"**Stop:** {trade['stop_loss']}")

                            st.markdown("**💰 Risk Management:**")
                            st.warning(f"**Size:** {trade['position_size']}")

                            st.markdown("**🧠 Edge:**")
                            st.markdown(f"_{trade['edge']}_")

                # Claude AI Strategy Generator
                st.divider()
                st.markdown("### 🤖 AI-Powered Strategy Generator")

                # Use container for centered content
                with st.container():
                    # Add CSS for centering just this section
                    st.markdown("""
                    <style>
                    div[data-testid="stVerticalBlock"] > div:has(div.ai-trade-section) {
                        max-width: 900px;
                        margin: 0 auto;
                    }
                    </style>
                    """, unsafe_allow_html=True)

                    st.markdown('<div class="ai-trade-section">', unsafe_allow_html=True)
                    st.markdown("Get a custom trade recommendation based on current market conditions using Claude AI")

                    st.markdown(f"""
                    **Current Conditions:**
                    - Symbol: **{current_symbol}**
                    - Net GEX: **${net_gex_billions:.2f}B**
                    - Spot Price: **${spot:.2f}**
                    - Flip Point: **${flip:.2f}**
                    - Day: **{day_of_week}**
                    - Time: **{current_time.strftime('%I:%M %p')}**
                    - Expiration Today: **{'Yes' if is_expiration_day else 'No'}**
                    """)

                    if st.button("🤖 Generate AI Trade", type="primary", use_container_width=True):
                        with st.spinner("Claude is analyzing gamma intelligence and market structure..."):
                            # Call Claude AI for recommendation
                            # ClaudeIntelligence already imported at top of file
                            claude = ClaudeIntelligence()

                            # Fetch/reuse gamma intelligence (NEW - critical for strategy selection)
                            # If we already fetched it above, use that; otherwise fetch now
                            if 'gamma_intel' not in locals() or not gamma_intel.get('success'):
                                # Get current VIX for context-aware adjustments
                                current_vix = 0
                                try:
                                    import yfinance as yf
                                    vix_data = yf.Ticker("^VIX").history(period="1d")
                                    if not vix_data.empty:
                                        current_vix = float(vix_data['Close'].iloc[-1])
                                except:
                                    current_vix = 0

                                # Fetch comprehensive gamma intelligence
                                gamma_intel = st.session_state.api_client.get_current_week_gamma_intelligence(
                                    current_symbol,
                                    current_vix=current_vix
                                )

                            # Generate recommendation with NEW gamma intelligence integration
                            prompt = f"""What's the best trade right now for {current_symbol} based on current gamma regime?

Consider:
- Current gamma structure (is it high or low?)
- Which strategies are favored vs. avoided in this regime?
- Specific strikes and expirations that make sense given gamma decay

Provide ONE specific, actionable trade with exact strikes, expiration, entry/exit.
"""

                            try:
                                # Use analyze_market method with proper market data structure + GAMMA INTELLIGENCE
                                market_data = {
                                    'net_gex': net_gex,
                                    'spot_price': spot,
                                    'flip_point': flip,
                                    'gex_levels': gex_levels,
                                    'symbol': current_symbol
                                }

                                # *** CRITICAL: Pass gamma_intel to eliminate iron condor bias ***
                                ai_response = claude.analyze_market(
                                    market_data=market_data,
                                    user_query=prompt,
                                    gamma_intel=gamma_intel  # NEW - enables context-aware strategy selection
                                )

                                st.markdown("#### 🎯 Claude's Gamma-Optimized Trade Recommendation")
                                st.markdown(f"""
<div style='background: linear-gradient(135deg, rgba(138, 43, 226, 0.15) 0%, rgba(75, 0, 130, 0.1) 100%);
            padding: 24px; border-radius: 14px; border: 2px solid rgba(138, 43, 226, 0.4);
            margin: 15px 0;'>
    <div style='color: white; font-size: 15px; line-height: 1.9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", sans-serif;'>
{ai_response}
    </div>
</div>
                                """, unsafe_allow_html=True)

                                # Show the data Claude used
                                with st.expander("📊 Data Used by Claude AI"):
                                    st.markdown(f"**Net GEX:** ${net_gex_billions:.2f}B")
                                    st.markdown(f"**Spot:** ${spot:.2f} | **Flip:** ${flip:.2f}")
                                    if gex_levels:
                                        st.markdown("**GEX Levels:**")
                                        st.json(gex_levels)
                                    if gamma_intel and gamma_intel.get('success'):
                                        st.markdown("**Gamma Intelligence Used:**")
                                        st.markdown(f"- Daily Impact: {gamma_intel['daily_impact']['impact_pct']:.1f}% decay")
                                        st.markdown(f"- Risk Level: {gamma_intel['daily_impact']['risk_level']}")
                                        st.markdown(f"- Weekly Decay: {gamma_intel['weekly_evolution']['total_decay_pct']:.1f}%")

                            except Exception as e:
                                st.error(f"Could not generate AI recommendation: {str(e)}")
                                st.info("💡 Tip: Check your API configuration in intelligence_and_strategies.py")

                    # Close the ai-trade-section div
                    st.markdown("</div>", unsafe_allow_html=True)

            else:
                # Symbol doesn't have daily expirations
                st.info(f"""
                ℹ️ **{current_symbol} does not have daily expirations** (0DTE)

                Daily expiration tracking is currently available for:
                - **SPY, QQQ, IWM** (Mon/Wed/Fri)
                - **SPX** (Mon-Fri)

                Select one of these symbols to access the Daily Expiration Gamma Tracker and 0DTE trading strategies.
                """)

            # ==================================================================
            # SECTION 2: MONTE CARLO SIMULATION (PREDICTIVE)
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
                        st.plotly_chart(mc_fig, use_container_width=True, key="monte_carlo_chart")
            else:
                st.info("💡 Monte Carlo simulation requires valid GEX data. Refresh the symbol to load data.")

        else:
            st.info("👈 Enter a symbol and click Refresh to begin analysis")
    
    # Tab 2: Trade Setups - USES SAME LOGIC AS TRADING PLAN
    with tabs[1]:
        st.subheader("🎯 Trading Setups - Profit Opportunities")

        # Show data timestamp
        current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        st.caption(f"📅 Data as of: {current_time}")

        # Center the content with max-width for better readability
        st.markdown("""
<style>
.trade-setup-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}
</style>
<div class="trade-setup-container">
""", unsafe_allow_html=True)

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

                    # Show notification for high-confidence setups
                    high_conf_setups = [s for s in setups if s.get('confidence', 0) >= 80]
                    if high_conf_setups:
                        st.markdown(f"""
<div class='notification' style='background: linear-gradient(135deg, rgba(0, 255, 136, 0.2) 0%, rgba(0, 212, 255, 0.2) 100%);
            border: 2px solid #00FF88;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0, 255, 136, 0.3);'>
    <div style='display: flex; align-items: center; gap: 10px;'>
        <div class='pulse-dot'></div>
        <div>
            <div style='color: #00FF88; font-weight: 800; font-size: 16px;'>
                🚨 {len(high_conf_setups)} HIGH-CONFIDENCE SETUP{'S' if len(high_conf_setups) > 1 else ''} DETECTED!
            </div>
            <div style='color: white; font-size: 13px; margin-top: 5px;'>
                Grade A opportunities with 80%+ confidence are available below
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

                    # Display each setup with enhanced professional cards
                    for i, trade in enumerate(setups, 1):
                        conf = trade.get('confidence', 0)

                        # Determine grade and styling based on confidence
                        if conf >= 80:
                            grade = "A"
                            grade_color = "#00FF88"
                            border_color = "rgba(0, 255, 136, 0.5)"
                            bg_gradient = "linear-gradient(135deg, rgba(0, 255, 136, 0.1) 0%, rgba(0, 212, 255, 0.1) 100%)"
                            badge = "🏆"
                        elif conf >= 70:
                            grade = "B"
                            grade_color = "#FFB800"
                            border_color = "rgba(255, 184, 0, 0.5)"
                            bg_gradient = "linear-gradient(135deg, rgba(255, 184, 0, 0.1) 0%, rgba(255, 153, 0, 0.1) 100%)"
                            badge = "⭐"
                        else:
                            grade = "C"
                            grade_color = "#888"
                            border_color = "rgba(136, 136, 136, 0.5)"
                            bg_gradient = "linear-gradient(135deg, rgba(136, 136, 136, 0.1) 0%, rgba(100, 100, 100, 0.1) 100%)"
                            badge = "📊"

                        # Calculate profit potential
                        target_1 = trade.get('target_1', '')
                        entry = trade.get('entry', '')
                        profit_potential = "TBD"
                        if target_1 and entry:
                            try:
                                target_val = float(str(target_1).replace('$', ''))
                                entry_val = float(str(entry).replace('$', ''))
                                profit_pct = ((target_val - entry_val) / entry_val) * 100
                                profit_potential = f"+${abs(profit_pct * 4.2):.0f}"  # Estimated for 1 contract
                            except:
                                pass

                        # Enhanced card header
                        st.markdown(f"""
<div style='background: {bg_gradient};
            padding: 20px; border-radius: 12px;
            border: 2px solid {border_color};
            margin-bottom: 20px;'>
    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;'>
        <div style='font-size: 24px; font-weight: 800; color: {grade_color};'>
            {badge} SETUP #{i} - GRADE {grade}
        </div>
        <div style='background: rgba(0, 0, 0, 0.5); padding: 8px 16px; border-radius: 8px;'>
            <span style='color: #00D4FF; font-size: 14px; font-weight: 600;'>💰 Est. Profit:</span>
            <span style='color: {grade_color}; font-size: 20px; font-weight: 800; margin-left: 8px;'>{profit_potential}</span>
        </div>
    </div>
    <div style='font-size: 18px; font-weight: 700; color: white; margin-bottom: 5px;'>
        {trade.get('strategy', 'Unknown Strategy')}
    </div>
    <div style='display: flex; gap: 15px; margin-top: 10px;'>
        <div style='background: rgba(0, 0, 0, 0.3); padding: 5px 12px; border-radius: 6px;'>
            <span style='color: #888; font-size: 12px;'>CONFIDENCE</span><br>
            <span style='color: {grade_color}; font-size: 16px; font-weight: 700;'>{conf}%</span>
        </div>
        <div style='background: rgba(0, 0, 0, 0.3); padding: 5px 12px; border-radius: 6px;'>
            <span style='color: #888; font-size: 12px;'>DTE</span><br>
            <span style='color: white; font-size: 16px; font-weight: 700;'>{trade.get('dte', 'N/A')}</span>
        </div>
        <div style='background: rgba(0, 0, 0, 0.3); padding: 5px 12px; border-radius: 6px;'>
            <span style='color: #888; font-size: 12px;'>WIN RATE</span><br>
            <span style='color: #00FF88; font-size: 16px; font-weight: 700;'>{trade.get('win_rate', 'N/A')}</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

                        with st.expander("📋 Full Trade Details", expanded=True):
                            # Reasoning with visual emphasis
                            st.markdown(f"""
<div style='background: rgba(0, 212, 255, 0.1); padding: 15px; border-radius: 8px;
            border-left: 4px solid #00D4FF; margin-bottom: 15px;'>
    <div style='color: #00D4FF; font-weight: 600; margin-bottom: 8px;'>💡 WHY THIS WORKS:</div>
    <div style='color: white; font-size: 15px;'>{trade.get('reasoning', 'Strong setup based on current market conditions.')}</div>
</div>
""", unsafe_allow_html=True)

                            # The Play with visual styling
                            dte_text = ""
                            if 'dte' in trade:
                                dte_text = f" with **{trade['dte']} DTE** ({trade.get('best_time', '')})"
                            elif 'expiration' in trade:
                                dte_text = f" with {trade['expiration']} expiration"

                            st.markdown(f"""
<div style='background: rgba(138, 43, 226, 0.1); padding: 12px; border-radius: 8px; margin-bottom: 10px;'>
    <span style='color: #00D4FF; font-weight: 600;'>🎯 THE PLAY:</span>
    <span style='color: white; font-size: 15px;'> {trade.get('action', 'N/A')}{dte_text}</span>
</div>
""", unsafe_allow_html=True)

                            # Entry/Exit Levels with visual bars
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                entry_value = trade.get('entry', trade.get('entry_zone', 'N/A'))
                                st.markdown(f"""
<div style='background: rgba(255, 184, 0, 0.2); padding: 12px; border-radius: 8px; text-align: center;'>
    <div style='color: #FFB800; font-size: 12px; font-weight: 600;'>📍 ENTRY</div>
    <div style='color: white; font-size: 20px; font-weight: 700;'>{entry_value}</div>
</div>
""", unsafe_allow_html=True)

                            with col2:
                                target_value = trade.get('target_1', trade.get('max_profit', 'N/A'))
                                st.markdown(f"""
<div style='background: rgba(0, 255, 136, 0.2); padding: 12px; border-radius: 8px; text-align: center;'>
    <div style='color: #00FF88; font-size: 12px; font-weight: 600;'>🎯 TARGET</div>
    <div style='color: white; font-size: 20px; font-weight: 700;'>{target_value}</div>
</div>
""", unsafe_allow_html=True)

                            with col3:
                                stop_value = trade.get('stop', trade.get('max_risk', 'N/A'))
                                st.markdown(f"""
<div style='background: rgba(255, 68, 68, 0.2); padding: 12px; border-radius: 8px; text-align: center;'>
    <div style='color: #FF4444; font-size: 12px; font-weight: 600;'>🛑 STOP</div>
    <div style='color: white; font-size: 20px; font-weight: 700;'>{stop_value}</div>
</div>
""", unsafe_allow_html=True)

                            st.markdown("<br>", unsafe_allow_html=True)

                            # Risk/Reward Visual Bar
                            risk_reward = trade.get('risk_reward', 2.0)
                            max_risk_val = trade.get('max_risk', '$420')
                            try:
                                risk_amount = float(str(max_risk_val).replace('$', '').replace(',', ''))
                                reward_amount = risk_amount * risk_reward

                                st.markdown(f"""
<div style='margin: 20px 0;'>
    <div style='color: #00D4FF; font-weight: 600; margin-bottom: 10px;'>⚖️ RISK/REWARD RATIO: {risk_reward}:1</div>
    <div style='display: flex; gap: 10px; align-items: center;'>
        <div style='flex: 1; background: rgba(255, 68, 68, 0.3); padding: 15px; border-radius: 8px; border: 2px solid #FF4444;'>
            <div style='color: #FF4444; font-size: 12px; font-weight: 600;'>RISK</div>
            <div style='color: white; font-size: 18px; font-weight: 700;'>${risk_amount:.0f}</div>
        </div>
        <div style='color: white; font-size: 24px;'>→</div>
        <div style='flex: {risk_reward}; background: rgba(0, 255, 136, 0.3); padding: 15px; border-radius: 8px; border: 2px solid #00FF88;'>
            <div style='color: #00FF88; font-size: 12px; font-weight: 600;'>REWARD</div>
            <div style='color: white; font-size: 18px; font-weight: 700;'>${reward_amount:.0f}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
                            except:
                                pass

                            # Additional targets if available
                            if 'target_2' in trade:
                                st.info(f"💎 **Extended Target:** {trade.get('target_2')} - Consider scaling out at each target to lock in profits.")

                            # Position sizing callout
                            size_value = trade.get('size', '2-3% of capital')
                            st.markdown(f"""
<div style='background: rgba(0, 212, 255, 0.1); padding: 12px; border-radius: 8px; border-left: 4px solid #00D4FF; margin-top: 15px;'>
    <span style='color: #00D4FF; font-weight: 600;'>💼 POSITION SIZE:</span>
    <span style='color: white;'> {size_value}</span>
</div>
""", unsafe_allow_html=True)

                            # Position Sizing Calculator
                            st.markdown("---")
                            account_size = st.session_state.get('account_size', 50000)
                            risk_pct = st.session_state.get('risk_per_trade', 2.0)

                            # Add option premium to trade dict if not present (default estimate)
                            if 'option_premium' not in trade:
                                trade['option_premium'] = 2.50

                            # Pass unique key suffix to avoid duplicate plotly chart IDs
                            display_position_sizing(trade, account_size, risk_pct, key_suffix=f"setup_{i}")

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

        # Close container div
        st.markdown("</div>", unsafe_allow_html=True)

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
            if len(watchlist) > 0:
                scan_time_minutes = (len(watchlist) * 15) / 60
                st.caption(f"⏱️ Estimated scan time: ~{scan_time_minutes:.1f} minutes (15s delay per symbol to prevent rate limits)")
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

    # Tab 6: AI Assistant
    with tabs[5]:
        st.subheader("🤖 AI Trading Assistant")

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

                    st.plotly_chart(fig, use_container_width=True, key="monte_carlo_histogram")

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
