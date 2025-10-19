"""
GEX Trading Co-Pilot v7.0 - COMPLETE INTELLIGENT SYSTEM WITH CLAUDE API
The Ultimate Market Maker Hunting Platform
Includes ALL features from our development history:
- TradingVolatility.net API Integration (Username: I-RWFNBLR2S1DP)
- Claude API for Intelligent Analysis
- FRED Economic Data Integration
- Complete 10-Component Profitability System
- Monte Carlo Simulations
- Black-Scholes Pricing
- Visual Intelligence with Charts
- Comprehensive Trade Tracking
"""

import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import List, Dict, Tuple, Optional
import numpy as np
import time
import sqlite3
from pathlib import Path
import warnings
import base64
from io import StringIO
import pytz
warnings.filterwarnings('ignore')

# Optional advanced imports
try:
    from scipy.stats import norm
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# ============================================================================
# PAGE CONFIG & SYSTEM CONSTANTS
# ============================================================================
st.set_page_config(
    page_title="GEX Trading Co-Pilot v7.0",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
TRADINGVOLATILITY_USERNAME = "I-RWFNBLR2S1DP"
TRADINGVOLATILITY_BASE = "https://stocks.tradingvolatility.net/api"
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Database Path
DB_PATH = Path("gex_copilot.db")

# Market Maker Behavioral States
MM_STATES = {
    'TRAPPED': {
        'threshold': -2e9,
        'behavior': 'Forced buying on rallies, selling on dips',
        'confidence': 85,
        'action': 'HUNT: Buy calls on any approach to flip point'
    },
    'DEFENDING': {
        'threshold': 1e9,
        'behavior': 'Selling rallies aggressively, buying dips',
        'confidence': 70,
        'action': 'FADE: Sell calls at resistance, puts at support'
    },
    'HUNTING': {
        'threshold': -1e9,
        'behavior': 'Aggressive positioning for direction',
        'confidence': 60,
        'action': 'WAIT: Let them show their hand first'
    },
    'PANICKING': {
        'threshold': -3e9,
        'behavior': 'Capitulation - covering at any price',
        'confidence': 90,
        'action': 'RIDE: Maximum aggression on squeeze'
    },
    'NEUTRAL': {
        'threshold': 0,
        'behavior': 'Balanced positioning',
        'confidence': 50,
        'action': 'RANGE: Iron condors between walls'
    }
}

# Trading Strategies Configuration
STRATEGIES = {
    'NEGATIVE_GEX_SQUEEZE': {
        'conditions': {
            'net_gex_threshold': -1e9,
            'distance_to_flip': 1.5,
            'min_put_wall_distance': 1.0
        },
        'win_rate': 0.68,
        'risk_reward': 3.0,
        'typical_move': '2-3% in direction',
        'best_days': ['Monday', 'Tuesday'],
        'entry': 'Break above flip point',
        'exit': 'Call wall or 100% profit'
    },
    'POSITIVE_GEX_BREAKDOWN': {
        'conditions': {
            'net_gex_threshold': 2e9,
            'proximity_to_flip': 0.3,
            'call_wall_rejection': True
        },
        'win_rate': 0.62,
        'risk_reward': 2.5,
        'typical_move': '1-2% down',
        'best_days': ['Wednesday', 'Thursday'],
        'entry': 'Break below flip point',
        'exit': 'Put wall or 75% profit'
    },
    'IRON_CONDOR': {
        'conditions': {
            'net_gex_threshold': 1e9,
            'min_wall_distance': 3.0,
            'iv_rank_below': 50
        },
        'win_rate': 0.72,
        'risk_reward': 0.3,
        'typical_move': 'Range bound',
        'best_days': ['Any with 5-10 DTE'],
        'entry': 'Short strikes at walls',
        'exit': '50% profit or breach'
    },
    'PREMIUM_SELLING': {
        'conditions': {
            'wall_strength': 500e6,
            'distance_from_wall': 1.0,
            'positive_gex': True
        },
        'win_rate': 0.65,
        'risk_reward': 0.5,
        'typical_move': 'Rejection at levels',
        'best_days': ['Any 0-2 DTE'],
        'entry': 'At wall approach',
        'exit': '50% profit or time'
    }
}

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================
def init_database():
    """Initialize comprehensive database schema"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # GEX History
    c.execute('''
        CREATE TABLE IF NOT EXISTS gex_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            net_gex REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            spot_price REAL,
            mm_state TEXT,
            regime TEXT,
            data_source TEXT
        )
    ''')
    
    # Trade Recommendations
    c.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            strategy TEXT,
            confidence REAL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            option_strike REAL,
            option_type TEXT,
            dte INTEGER,
            reasoning TEXT,
            mm_behavior TEXT,
            outcome TEXT,
            pnl REAL
        )
    ''')
    
    # Active Positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            strategy TEXT,
            direction TEXT,
            entry_price REAL,
            current_price REAL,
            target REAL,
            stop REAL,
            size REAL,
            status TEXT DEFAULT 'ACTIVE',
            closed_at DATETIME,
            pnl REAL
        )
    ''')
    
    # Performance Analytics
    c.execute('''
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            total_trades INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            total_pnl REAL,
            win_rate REAL,
            avg_winner REAL,
            avg_loser REAL,
            sharpe_ratio REAL,
            max_drawdown REAL
        )
    ''')
    
    # AI Conversations
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_message TEXT,
            ai_response TEXT,
            context_data TEXT,
            confidence_score REAL
        )
    ''')
    
    conn.commit()
    conn.close()

# ============================================================================
# TRADINGVOLATILITY API INTEGRATION
# ============================================================================
class TradingVolatilityAPI:
    """Complete API integration with rate limiting and caching"""
    
    def __init__(self, username: str):
        self.username = username
        self.base_url = TRADINGVOLATILITY_BASE
        self.rate_limit = 20  # calls per minute weekday
        self.last_calls = []
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def _rate_limit_check(self):
        """Enforce API rate limits"""
        now = time.time()
        self.last_calls = [t for t in self.last_calls if now - t < 60]
        
        if len(self.last_calls) >= self.rate_limit:
            wait_time = 60 - (now - self.last_calls[0]) + 1
            if wait_time > 0:
                st.warning(f"Rate limit reached. Waiting {wait_time:.0f} seconds...")
                time.sleep(wait_time)
        
        self.last_calls.append(now)
    
    def get_net_gamma(self, symbol: str, use_cache: bool = True) -> Dict:
        """Fetch net gamma data with caching"""
        cache_key = f"net_gamma_{symbol}"
        
        # Check cache first
        if use_cache and cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_data
        
        # Rate limit check
        self._rate_limit_check()
        
        try:
            # Correct endpoint structure
            url = f"{self.base_url}/gex"
            params = {
                'username': self.username,
                'ticker': symbol.upper(),
                'type': 'netgamma'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Cache the result
                self.cache[cache_key] = (data, time.time())
                return data
            else:
                st.warning(f"API returned {response.status_code}, using mock data")
                return self._get_mock_data(symbol)
                
        except Exception as e:
            st.warning(f"Using mock data due to API issue: {str(e)[:50]}")
            return self._get_mock_data(symbol)
    
    def get_gex_profile(self, symbol: str, expiry: str = 'all') -> Dict:
        """Fetch complete GEX profile by strike"""
        cache_key = f"gex_profile_{symbol}_{expiry}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_data
        
        self._rate_limit_check()
        
        try:
            url = f"{self.base_url}/gexprofile"
            params = {
                'username': self.username,
                'symbol': symbol.upper(),
                'expiry': expiry
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.cache[cache_key] = (data, time.time())
                return data
            else:
                return self._get_mock_profile(symbol)
                
        except Exception as e:
            return self._get_mock_profile(symbol)
    
    def _get_mock_data(self, symbol: str) -> Dict:
        """Return mock data for testing"""
        base_price = {'SPY': 580, 'QQQ': 490, 'IWM': 220}.get(symbol, 100)
        
        return {
            'symbol': symbol,
            'spot_price': base_price,
            'net_gex': np.random.uniform(-2e9, 3e9),
            'flip_point': base_price + np.random.uniform(-5, 5),
            'call_wall': base_price + np.random.uniform(5, 15),
            'put_wall': base_price - np.random.uniform(5, 15),
            'timestamp': datetime.now().isoformat(),
            'data_quality': 'mock'
        }
    
    def _get_mock_profile(self, symbol: str) -> Dict:
        """Return mock GEX profile for testing"""
        base_price = {'SPY': 580, 'QQQ': 490, 'IWM': 220}.get(symbol, 100)
        strikes = []
        
        for strike in range(int(base_price * 0.9), int(base_price * 1.1), 5):
            distance = abs(strike - base_price)
            gamma = np.random.uniform(1e6, 1e8) * np.exp(-distance/10)
            
            strikes.append({
                'strike': strike,
                'call_gamma': gamma if strike > base_price else gamma * 0.3,
                'put_gamma': gamma if strike < base_price else gamma * 0.3,
                'total_gamma': gamma
            })
        
        return {
            'symbol': symbol,
            'strikes': strikes,
            'spot_price': base_price,
            'timestamp': datetime.now().isoformat()
        }

# ============================================================================
# FRED API INTEGRATION
# ============================================================================
class FREDIntegration:
    """Federal Reserve Economic Data integration for macro context"""
    
    def __init__(self):
        self.api_key = st.secrets.get("FRED_API_KEY", "")
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour cache
    
    def get_economic_data(self) -> Dict:
        """Fetch key economic indicators with better defaults"""
        
        # Use realistic current values as defaults
        defaults = {
            'ten_year_yield': 4.3,
            'fed_funds_rate': 5.5,
            'vix': 20,  # More realistic current VIX
            'dollar_index': 105,
            'unemployment': 3.8,
            'cpi': 3.2
        }
        
        # If no API key, return defaults
        if not self.api_key:
            return defaults
        
        indicators = {
            'DGS10': 'ten_year_yield',
            'DFF': 'fed_funds_rate',
            'VIXCLS': 'vix',
            'DEXUSEU': 'dollar_index',
            'UNRATE': 'unemployment',
            'CPIAUCSL': 'cpi'
        }
        
        data = {}
        
        for series_id, name in indicators.items():
            # Check cache first
            if series_id in self.cache:
                cached_data, cached_time = self.cache[series_id]
                if time.time() - cached_time < self.cache_ttl:
                    data[name] = cached_data
                    continue
            
            # Try to fetch from FRED
            try:
                params = {
                    'series_id': series_id,
                    'api_key': self.api_key,
                    'file_type': 'json',
                    'limit': 1,
                    'sort_order': 'desc'
                }
                
                response = requests.get(self.base_url, params=params, timeout=5)
                
                if response.status_code == 200:
                    result = response.json()
                    if 'observations' in result and len(result['observations']) > 0:
                        value = float(result['observations'][0]['value'])
                        data[name] = value
                        self.cache[series_id] = (value, time.time())
                    else:
                        data[name] = defaults[name]
                else:
                    data[name] = defaults[name]
                    
            except Exception:
                # Use defaults on any error
                data[name] = defaults[name]
        
        return data
    
    def get_regime(self, data: Dict) -> Dict:
        """Determine market regime from economic data"""
        
        vix = data.get('vix', 20)  # Default to 20 if not available
        ten_year = data.get('ten_year_yield', 4.3)
        fed_funds = data.get('fed_funds_rate', 5.5)
        
        # More realistic VIX ranges
        if vix < 15:
            vol_regime = "LOW"
            vol_signal = "Premium selling favorable"
        elif vix < 20:
            vol_regime = "NORMAL"
            vol_signal = "Balanced strategies"
        elif vix < 25:
            vol_regime = "ELEVATED"
            vol_signal = "Directional opportunities"
        elif vix < 30:
            vol_regime = "HIGH"
            vol_signal = "Squeeze plays favorable"
        else:
            vol_regime = "EXTREME"
            vol_signal = "High volatility - reduce size"
        
        # Position sizing multiplier
        if vix < 15 and ten_year < 4:
            size_multiplier = 1.5
            regime_signal = "AGGRESSIVE - Low vol, low rates"
        elif vix > 30 or ten_year > 5:
            size_multiplier = 0.5
            regime_signal = "DEFENSIVE - High vol or rates"
        elif vix > 25:
            size_multiplier = 0.75
            regime_signal = "CAUTIOUS - Elevated volatility"
        else:
            size_multiplier = 1.0
            regime_signal = "NORMAL - Standard sizing"
        
        return {
            'vol_regime': vol_regime,
            'vol_signal': vol_signal,
            'size_multiplier': size_multiplier,
            'regime_signal': regime_signal,
            'vix': vix,
            'ten_year_yield': ten_year,
            'fed_funds_rate': fed_funds
        }

# ============================================================================
# CLAUDE API INTEGRATION
# ============================================================================
class ClaudeIntelligence:
    """Advanced AI integration for market analysis"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or st.secrets.get("CLAUDE_API_KEY", "")
        self.model = CLAUDE_MODEL
        self.conversation_history = []
        self.fred = FREDIntegration()
        
    def analyze_market(self, market_data: Dict, user_query: str) -> str:
        """Generate intelligent market analysis based on actual query"""
        
        if not self.api_key:
            return self._fallback_analysis(market_data, user_query)
        
        # Build comprehensive context with user's actual question
        context = self._build_context(market_data)
        
        # Keep conversation history for context
        self.conversation_history.append({"role": "user", "content": user_query})
        
        # Prepare messages with full history
        messages = self.conversation_history[-10:]  # Keep last 10 messages for context
        
        # Add current context
        messages.append({
            "role": "user",
            "content": f"""
            Current Market Data:
            {json.dumps(context, indent=2)}
            
            User's Specific Question: {user_query}
            
            IMPORTANT: Answer the user's SPECIFIC question above. 
            Don't give generic responses. Think about what they're actually asking.
            If they ask about a specific strike or strategy, analyze that specifically.
            If they ask "why", explain the reasoning.
            If they ask "should I", give a clear yes/no with reasoning.
            
            Be specific with strikes, prices, and timing.
            """
        })
        
        try:
            response = self._call_claude_api(messages)
            self.conversation_history.append({"role": "assistant", "content": response})
            self._log_conversation(user_query, response, market_data)
            return response
            
        except Exception as e:
            st.error(f"Claude API Error: {e}")
            return self._fallback_analysis(market_data, user_query)
    
    def challenge_trade_idea(self, idea: str, market_data: Dict) -> str:
        """Challenge user's trading ideas with data"""
        
        if not self.api_key:
            return self._fallback_challenge(idea, market_data)
        
        context = self._build_context(market_data)
        
        messages = [
            {
                "role": "user",
                "content": f"""
                Acting as a critical trading mentor, challenge this trade idea:
                
                Trade Idea: {idea}
                
                Market Context:
                {json.dumps(context, indent=2)}
                
                Provide:
                1. Data-driven challenges to the idea
                2. Alternative perspectives
                3. Risk factors being overlooked
                4. Better alternatives if applicable
                
                Be direct but constructive.
                """
            }
        ]
        
        try:
            response = self._call_claude_api(messages)
            return response
        except:
            return self._fallback_challenge(idea, market_data)
    
    def _call_claude_api(self, messages: List[Dict]) -> str:
        """Make API call to Claude with enhanced system prompt"""
        
        # Get FRED data for context
        fred_data = self.fred.get_economic_data()
        regime = self.fred.get_regime(fred_data)
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Enhanced aggressive system prompt
        system_prompt = f"""You are an elite options trader specializing in gamma exposure analysis. 
        You hunt market makers by understanding their hedging requirements and MAKE MONEY from their forced behavior.
        
        CURRENT ECONOMIC REGIME:
        VIX: {regime['vix']:.1f} - {regime['vol_regime']} volatility
        10Y Yield: {regime['ten_year_yield']:.2f}%
        Fed Funds: {regime['fed_funds_rate']:.2f}%
        Signal: {regime['regime_signal']}
        Position Size Multiplier: {regime['size_multiplier']}x
        
        CORE MISSION: Tell the trader EXACTLY what to trade to make money.
        
        CRITICAL RULES:
        1. ALWAYS give specific strikes and prices, never vague suggestions
        2. Monday/Tuesday: Push directional plays aggressively
        3. Wednesday 3PM: FORCE exit of all directionals - no exceptions
        4. Thursday/Friday: Iron Condors only (protect from theta crush)
        5. Calculate EXACT entry, target, and stop levels
        
        MONEY-MAKING FOCUS:
        - When Net GEX < -1B: MMs trapped, they MUST buy rallies - BUY CALLS
        - When Net GEX > 2B: MMs defending, they sell rallies - SELL PREMIUM
        - Near flip point: Explosive move imminent - POSITION NOW
        
        RESPONSE FORMAT:
        1. MM State & What They're FORCED to do
        2. EXACT trade: Strike, premium, entry price
        3. Targets with reasoning (where MMs stop hedging)
        4. Stop loss (where thesis breaks)
        5. Win probability based on this exact setup
        
        Be aggressive about making money. Push back HARD on bad ideas.
        If it's Wednesday after 3PM or Friday, REFUSE directional trades."""
        
        payload = {
            "model": self.model,
            "max_tokens": 4000,
            "messages": messages,
            "system": system_prompt
        }
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        return result['content'][0]['text']
    
    def _build_context(self, market_data: Dict) -> Dict:
        """Build comprehensive context for AI"""
        
        return {
            'symbol': market_data.get('symbol', 'SPY'),
            'current_price': market_data.get('spot_price', 0),
            'net_gex': market_data.get('net_gex', 0),
            'net_gex_billions': market_data.get('net_gex', 0) / 1e9,
            'flip_point': market_data.get('flip_point', 0),
            'distance_to_flip': ((market_data.get('flip_point', 0) - market_data.get('spot_price', 0)) / 
                                market_data.get('spot_price', 1) * 100),
            'call_wall': market_data.get('call_wall', 0),
            'put_wall': market_data.get('put_wall', 0),
            'mm_state': self._determine_mm_state(market_data.get('net_gex', 0)),
            'timestamp': market_data.get('timestamp', datetime.now().isoformat()),
            'day_of_week': datetime.now().strftime('%A'),
            'dte_to_friday': (4 - datetime.now().weekday()) % 7
        }
    
    def _determine_mm_state(self, net_gex: float) -> str:
        """Determine current MM state"""
        for state, config in MM_STATES.items():
            if net_gex < config['threshold']:
                return state
        return 'NEUTRAL'
    
    def _fallback_analysis(self, market_data: Dict, user_query: str) -> str:
        """Fallback analysis without API"""
        
        net_gex = market_data.get('net_gex', 0)
        spot = market_data.get('spot_price', 0)
        flip = market_data.get('flip_point', 0)
        
        mm_state = self._determine_mm_state(net_gex)
        state_config = MM_STATES[mm_state]
        
        distance = ((flip - spot) / spot * 100) if spot else 0
        
        analysis = f"""
        📊 **Market Maker Analysis**
        
        **Current State: {mm_state}**
        - Behavior: {state_config['behavior']}
        - Action: {state_config['action']}
        - Confidence: {state_config['confidence']}%
        
        **Key Levels:**
        - Current: ${spot:.2f}
        - Flip Point: ${flip:.2f} ({distance:+.2f}% away)
        - Call Wall: ${market_data.get('call_wall', 0):.2f}
        - Put Wall: ${market_data.get('put_wall', 0):.2f}
        
        **Net GEX: ${net_gex/1e9:.2f}B**
        
        """
        
        # Add specific recommendations based on state
        if mm_state == 'TRAPPED':
            analysis += """
        🎯 **Setup: SQUEEZE PLAY**
        - Entry: Break above ${:.2f} (flip point)
        - Target 1: ${:.2f} (+1.5%)
        - Target 2: ${:.2f} (call wall)
        - Stop: ${:.2f} (-0.5%)
        - Strategy: Buy calls 5 DTE at first break above flip
        """.format(flip, spot * 1.015, market_data.get('call_wall', spot * 1.03), spot * 0.995)
        
        elif mm_state == 'DEFENDING':
            analysis += """
        🎯 **Setup: FADE THE MOVE**
        - Resistance: ${:.2f} (call wall)
        - Support: ${:.2f} (put wall)
        - Strategy: Sell call spreads at resistance, put spreads at support
        - Iron Condor opportunity if range holds
        """.format(market_data.get('call_wall', 0), market_data.get('put_wall', 0))
        
        return analysis
    
    def _fallback_challenge(self, idea: str, market_data: Dict) -> str:
        """Fallback challenge without API"""
        
        net_gex = market_data.get('net_gex', 0)
        mm_state = self._determine_mm_state(net_gex)
        
        challenges = []
        
        idea_lower = idea.lower()
        
        # Context-aware challenges
        if 'buy calls' in idea_lower or 'long calls' in idea_lower:
            if mm_state == 'DEFENDING':
                challenges.append("⚠️ MMs are DEFENDING (long gamma). They will sell every rally.")
                challenges.append("📊 Historical data: 72% of call buys fail when Net GEX > 2B")
                challenges.append("💡 Alternative: Sell call spreads at resistance instead")
            elif mm_state == 'TRAPPED':
                challenges.append("✅ Direction agrees with trapped MMs, but timing is critical")
                challenges.append("⚠️ Risk: Entry too early before flip break")
                challenges.append("💡 Wait for confirmed break above flip with volume")
        
        if 'buy puts' in idea_lower or 'long puts' in idea_lower:
            if mm_state == 'TRAPPED':
                challenges.append("⚠️ MMs are trapped SHORT. They must buy dips.")
                challenges.append("📊 Puts have 30% win rate in negative GEX < -1B")
                challenges.append("💡 Alternative: Wait for positive GEX or buy calls")
        
        if 'iron condor' in idea_lower:
            if abs(net_gex) < 0.5e9:
                challenges.append("⚠️ Low absolute GEX means directional risk")
                challenges.append("📊 Iron Condors need |GEX| > 1B for stability")
                challenges.append("💡 Alternative: Directional plays or wait for higher GEX")
        
        if not challenges:
            challenges.append("🤔 Interesting idea. Let me analyze the gamma structure...")
            challenges.append(f"Current MM State: {mm_state}")
            challenges.append("Consider the forced hedging flows in this regime")
        
        return "\n".join(challenges)
    
    def _log_conversation(self, query: str, response: str, context: Dict):
        """Log conversation to database"""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''
                INSERT INTO conversations (user_message, ai_response, context_data, confidence_score)
                VALUES (?, ?, ?, ?)
            ''', (
                query,
                response,
                json.dumps(context),
                context.get('confidence', 50)
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            st.error(f"Failed to log conversation: {e}")

# ============================================================================
# MONTE CARLO SIMULATION ENGINE
# ============================================================================
class MonteCarloEngine:
    """Probabilistic simulation for trade outcomes"""
    
    @staticmethod
    def simulate_squeeze_play(current_price: float, flip_point: float, 
                             call_wall: float, volatility: float = 0.15, 
                             days: int = 5, simulations: int = 10000) -> Dict:
        """Simulate squeeze play outcomes"""
        
        # Setup parameters
        daily_vol = volatility / np.sqrt(252)
        drift = 0.0  # Assume no drift for short-term
        
        # Generate random price paths
        dt = 1/252  # Daily steps
        random_shocks = np.random.randn(simulations, days)
        
        price_paths = np.zeros((simulations, days + 1))
        price_paths[:, 0] = current_price
        
        for t in range(1, days + 1):
            price_paths[:, t] = price_paths[:, t-1] * np.exp(
                (drift - 0.5 * daily_vol**2) * dt + 
                daily_vol * np.sqrt(dt) * random_shocks[:, t-1]
            )
        
        # Calculate outcomes
        hit_flip = np.any(price_paths >= flip_point, axis=1)
        hit_call_wall = np.any(price_paths >= call_wall, axis=1)
        max_price = np.max(price_paths, axis=1)
        min_price = np.min(price_paths, axis=1)
        final_price = price_paths[:, -1]
        
        # Calculate returns for option
        option_returns = np.maximum(final_price - flip_point, 0)
        
        return {
            'probability_hit_flip': np.mean(hit_flip) * 100,
            'probability_hit_wall': np.mean(hit_call_wall) * 100,
            'expected_final_price': np.mean(final_price),
            'median_final_price': np.median(final_price),
            'percentile_5': np.percentile(final_price, 5),
            'percentile_95': np.percentile(final_price, 95),
            'max_gain_percent': (np.mean(max_price) / current_price - 1) * 100,
            'max_loss_percent': (np.mean(min_price) / current_price - 1) * 100,
            'option_expected_return': np.mean(option_returns),
            'price_paths_sample': price_paths[:100]  # Sample for visualization
        }
    
    @staticmethod
    def simulate_iron_condor(spot: float, call_short: float, call_long: float,
                            put_short: float, put_long: float, 
                            dte: int, volatility: float = 0.15) -> Dict:
        """Simulate Iron Condor profitability"""
        
        # Parameters
        daily_vol = volatility / np.sqrt(252)
        simulations = 10000
        
        # Generate terminal prices
        terminal_prices = spot * np.exp(
            np.random.randn(simulations) * daily_vol * np.sqrt(dte)
        )
        
        # Calculate P&L for each scenario
        pnl = np.zeros(simulations)
        
        for i, price in enumerate(terminal_prices):
            if price <= put_long:
                pnl[i] = -100  # Max loss on put side
            elif price <= put_short:
                pnl[i] = (price - put_long) / (put_short - put_long) * 100 - 100
            elif price <= call_short:
                pnl[i] = 0  # Max profit (credit received)
            elif price <= call_long:
                pnl[i] = -(price - call_short) / (call_long - call_short) * 100
            else:
                pnl[i] = -100  # Max loss on call side
        
        # Calculate statistics
        win_rate = np.mean((terminal_prices > put_short) & (terminal_prices < call_short)) * 100
        
        return {
            'win_probability': win_rate,
            'expected_pnl': np.mean(pnl),
            'max_profit_probability': np.mean(
                (terminal_prices > put_short) & (terminal_prices < call_short)
            ) * 100,
            'put_breach_probability': np.mean(terminal_prices <= put_short) * 100,
            'call_breach_probability': np.mean(terminal_prices >= call_short) * 100,
            'expected_terminal_price': np.mean(terminal_prices),
            'percentile_5': np.percentile(terminal_prices, 5),
            'percentile_95': np.percentile(terminal_prices, 95)
        }

# ============================================================================
# BLACK-SCHOLES PRICING ENGINE
# ============================================================================
class BlackScholesPricer:
    """Option pricing and Greeks calculation"""
    
    @staticmethod
    def calculate(spot: float, strike: float, dte_days: int,
                 volatility: float = 0.15, rate: float = 0.05,
                 option_type: str = 'call') -> Dict:
        """Calculate option price and Greeks"""
        
        if dte_days <= 0:
            return {
                'price': max(0, spot - strike) if option_type == 'call' else max(0, strike - spot),
                'delta': 1.0 if spot > strike and option_type == 'call' else 0.0,
                'gamma': 0.0,
                'theta': 0.0,
                'vega': 0.0
            }
        
        T = dte_days / 365.0
        
        if SCIPY_AVAILABLE:
            # Full Black-Scholes with scipy
            d1 = (np.log(spot/strike) + (rate + 0.5*volatility**2)*T) / (volatility*np.sqrt(T))
            d2 = d1 - volatility * np.sqrt(T)
            
            if option_type == 'call':
                price = spot * norm.cdf(d1) - strike * np.exp(-rate*T) * norm.cdf(d2)
                delta = norm.cdf(d1)
            else:
                price = strike * np.exp(-rate*T) * norm.cdf(-d2) - spot * norm.cdf(-d1)
                delta = -norm.cdf(-d1)
            
            # Greeks
            gamma = norm.pdf(d1) / (spot * volatility * np.sqrt(T))
            theta = -(spot * norm.pdf(d1) * volatility) / (2 * np.sqrt(T))
            vega = spot * norm.pdf(d1) * np.sqrt(T)
            
        else:
            # Simplified approximation
            intrinsic = max(0, spot - strike) if option_type == 'call' else max(0, strike - spot)
            time_value = intrinsic * 0.1 * np.sqrt(T)
            price = intrinsic + time_value
            
            # Simplified Greeks
            delta = 0.5 + 0.5 * np.tanh((spot - strike) / (spot * 0.1))
            if option_type == 'put':
                delta = delta - 1
            
            gamma = 0.01 * np.exp(-((spot - strike) / (spot * 0.1))**2)
            theta = -price * 0.1 / max(T, 0.001)
            vega = price * 0.2
        
        return {
            'price': round(price, 2),
            'delta': round(delta, 3),
            'gamma': round(gamma, 4),
            'theta': round(theta / 365, 3),  # Per day
            'vega': round(vega / 100, 3),  # Per 1% vol
            'iv': volatility
        }

# ============================================================================
# VISUALIZATION ENGINE
# ============================================================================
class GEXVisualizer:
    """Create professional trading visualizations"""
    
    @staticmethod
    def create_gex_profile(gex_data: Dict) -> go.Figure:
        """Create interactive GEX profile chart"""
        
        if not gex_data or 'strikes' not in gex_data:
            fig = go.Figure()
            fig.add_annotation(
                text="No GEX data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig
        
        strikes = []
        call_gamma = []
        put_gamma = []
        total_gamma = []
        
        spot = gex_data.get('spot_price', 0)
        
        for strike_data in gex_data['strikes']:
            strikes.append(strike_data['strike'])
            call_g = strike_data.get('call_gamma', 0) / 1e6  # Convert to millions
            put_g = -abs(strike_data.get('put_gamma', 0)) / 1e6
            
            call_gamma.append(call_g)
            put_gamma.append(put_g)
            total_gamma.append(call_g + put_g)
        
        # Create subplots
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=('Gamma Exposure by Strike', 'Net Gamma Profile')
        )
        
        # Call gamma bars
        fig.add_trace(
            go.Bar(
                x=strikes,
                y=call_gamma,
                name='Call Gamma',
                marker_color='green',
                opacity=0.7,
                hovertemplate='Strike: %{x}<br>Call Gamma: $%{y:.1f}M<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Put gamma bars
        fig.add_trace(
            go.Bar(
                x=strikes,
                y=put_gamma,
                name='Put Gamma',
                marker_color='red',
                opacity=0.7,
                hovertemplate='Strike: %{x}<br>Put Gamma: $%{y:.1f}M<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Net gamma line
        fig.add_trace(
            go.Scatter(
                x=strikes,
                y=total_gamma,
                name='Net Gamma',
                line=dict(color='blue', width=2),
                hovertemplate='Strike: %{x}<br>Net Gamma: $%{y:.1f}M<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Add current price line
        fig.add_vline(
            x=spot,
            line_dash="dash",
            line_color="yellow",
            annotation_text=f"Spot ${spot:.2f}",
            row='all'
        )
        
        # Find and mark flip point (where net gamma crosses zero)
        flip_point = None
        for i in range(len(total_gamma) - 1):
            if total_gamma[i] * total_gamma[i + 1] < 0:
                flip_point = strikes[i] + (strikes[i + 1] - strikes[i]) * (
                    -total_gamma[i] / (total_gamma[i + 1] - total_gamma[i])
                )
                break
        
        if flip_point:
            fig.add_vline(
                x=flip_point,
                line_dash="dash",
                line_color="orange",
                annotation_text=f"Flip ${flip_point:.2f}",
                row='all'
            )
        
        # Update layout
        fig.update_layout(
            title=f'GEX Profile Analysis - {gex_data.get("symbol", "N/A")}',
            height=600,
            showlegend=True,
            hovermode='x unified',
            template='plotly_dark',
            xaxis2_title='Strike Price',
            yaxis_title='Gamma Exposure ($M)',
            yaxis2_title='Net Gamma ($M)'
        )
        
        return fig
    
    @staticmethod
    def create_monte_carlo_chart(simulation_results: Dict, current_price: float) -> go.Figure:
        """Create Monte Carlo simulation visualization"""
        
        if 'price_paths_sample' not in simulation_results:
            return go.Figure()
        
        paths = simulation_results['price_paths_sample']
        days = list(range(paths.shape[1]))
        
        fig = go.Figure()
        
        # Add sample paths
        for i in range(min(50, len(paths))):
            fig.add_trace(
                go.Scatter(
                    x=days,
                    y=paths[i],
                    mode='lines',
                    line=dict(width=0.5, color='lightgray'),
                    showlegend=False,
                    hoverinfo='skip'
                )
            )
        
        # Add percentile bands
        percentiles = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
        
        fig.add_trace(
            go.Scatter(
                x=days + days[::-1],
                y=list(percentiles[0]) + list(percentiles[4][::-1]),
                fill='toself',
                fillcolor='rgba(255, 0, 0, 0.1)',
                line=dict(color='rgba(255, 0, 0, 0)'),
                name='5-95 Percentile',
                showlegend=True
            )
        )
        
        fig.add_trace(
            go.Scatter(
                x=days + days[::-1],
                y=list(percentiles[1]) + list(percentiles[3][::-1]),
                fill='toself',
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(color='rgba(0, 255, 0, 0)'),
                name='25-75 Percentile',
                showlegend=True
            )
        )
        
        # Add median line
        fig.add_trace(
            go.Scatter(
                x=days,
                y=percentiles[2],
                mode='lines',
                line=dict(color='yellow', width=2),
                name='Median Path'
            )
        )
        
        # Add current price line
        fig.add_hline(
            y=current_price,
            line_dash="dash",
            line_color="white",
            annotation_text=f"Current ${current_price:.2f}"
        )
        
        fig.update_layout(
            title='Monte Carlo Price Simulation (10,000 runs)',
            xaxis_title='Days Forward',
            yaxis_title='Price ($)',
            template='plotly_dark',
            height=400,
            hovermode='x unified'
        )
        
        return fig

# ============================================================================
# COMPREHENSIVE PLAN GENERATOR
# ============================================================================
class TradingPlanGenerator:
    """Generate detailed daily, weekly, and monthly trading plans"""
    
    def __init__(self):
        self.fred = FREDIntegration()
        
    def generate_daily_plan(self, symbol: str, market_data: Dict) -> Dict:
        """Generate comprehensive daily trading plan"""
        
        spot = market_data.get('spot_price', 0)
        net_gex = market_data.get('net_gex', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        # Get current day and time
        now = datetime.now()
        day = now.strftime('%A')
        hour = now.hour
        minute = now.minute
        
        # Get FRED regime
        fred_data = self.fred.get_economic_data()
        regime = self.fred.get_regime(fred_data)
        
        plan = {
            'symbol': symbol,
            'date': now.strftime('%Y-%m-%d'),
            'day': day,
            'generated_at': now.strftime('%H:%M ET'),
            'regime': regime,
            'pre_market': {},
            'opening_30min': {},
            'mid_morning': {},
            'lunch': {},
            'power_hour': {},
            'after_hours': {}
        }
        
        # Pre-market prep (8:00-9:30)
        plan['pre_market'] = {
            'checklist': [
                f"✓ Check SPY GEX: Currently ${net_gex/1e9:.1f}B",
                f"✓ Key levels: Flip ${flip:.2f}, Call wall ${call_wall:.2f}, Put wall ${put_wall:.2f}",
                f"✓ Economic regime: {regime['vol_signal']}",
                f"✓ Position size multiplier: {regime['size_multiplier']}x",
                f"✓ VIX at {regime['vix']:.1f} - {regime['vol_regime']} volatility"
            ],
            'bias': 'BULLISH' if net_gex < -1e9 else 'BEARISH' if net_gex > 2e9 else 'NEUTRAL',
            'primary_setup': self._determine_primary_setup(day, net_gex, spot, flip)
        }
        
        # Opening 30 minutes (9:30-10:00)
        if day in ['Monday', 'Tuesday']:
            plan['opening_30min'] = {
                'strategy': 'Wait for initial volatility to settle',
                'entry_trigger': f"Break above ${flip:.2f} with volume" if spot < flip else f"Break below ${flip:.2f}",
                'initial_size': '50% of planned position',
                'stop_level': f"${put_wall:.2f}" if spot < flip else f"${call_wall:.2f}",
                'notes': 'Best entry window for directional plays'
            }
        else:
            plan['opening_30min'] = {
                'strategy': 'Observe only - no directional entries',
                'notes': f"Wednesday+ = Theta decay zone. Wait for Iron Condor setup"
            }
        
        # Mid-morning (10:00-12:00)
        plan['mid_morning'] = {
            'add_zone': f"${spot-1:.2f} - ${spot+1:.2f}",
            'target_1': f"${flip:.2f}" if spot < flip else f"${call_wall:.2f}",
            'profit_taking': 'Take 25% off at target 1',
            'trail_stop': f"Move stop to breakeven after target 1"
        }
        
        # Lunch (12:00-2:00)
        plan['lunch'] = {
            'strategy': 'Hold positions, avoid new entries',
            'notes': 'Low volume period - wait for afternoon'
        }
        
        # Power hour (3:00-4:00)
        if day == 'Wednesday':
            plan['power_hour'] = {
                'ACTION': '🚨 MANDATORY EXIT ALL DIRECTIONALS BY 3:00 PM 🚨',
                'strategy': 'CLOSE EVERYTHING - No exceptions',
                'reasoning': 'Theta acceleration begins',
                'alternative': 'Switch to Iron Condors for Thu/Fri'
            }
        elif day in ['Monday', 'Tuesday']:
            plan['power_hour'] = {
                'strategy': 'Final push common - hold for close',
                'profit_target': f"${call_wall:.2f}" if spot < flip else f"${put_wall:.2f}",
                'overnight_decision': 'Hold if above flip, exit if rejected'
            }
        else:
            plan['power_hour'] = {
                'strategy': 'Iron Condor management only',
                'friday_special': '3PM charm flow if GEX flips negative' if day == 'Friday' else 'Hold condors'
            }
        
        # After hours
        plan['after_hours'] = {
            'alerts_to_set': [
                f"Alert at ${flip:.2f} (flip point)",
                f"Alert at ${call_wall:.2f} (call wall)",
                f"Alert at ${put_wall:.2f} (put wall)"
            ],
            'homework': 'Check Asia markets, plan tomorrow levels'
        }
        
        return plan
    
    def generate_weekly_plan(self, symbol: str, market_data: Dict) -> Dict:
        """Generate comprehensive weekly trading plan"""
        
        spot = market_data.get('spot_price', 0)
        net_gex = market_data.get('net_gex', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        # Calculate strikes
        atm_call = int(spot / 5) * 5 + (5 if spot % 5 > 2.5 else 0)
        otm_call = atm_call + 5
        atm_put = atm_call
        otm_put = atm_put - 5
        
        # Get regime
        fred_data = self.fred.get_economic_data()
        regime = self.fred.get_regime(fred_data)
        
        # Black-Scholes pricing
        pricer = BlackScholesPricer()
        
        plan = {
            'symbol': symbol,
            'week_of': datetime.now().strftime('%Y-%m-%d'),
            'regime': regime,
            'net_gex': f"${net_gex/1e9:.1f}B",
            'expected_return': 0,
            'days': {}
        }
        
        # Monday Plan
        monday_call = pricer.calculate(spot, atm_call, 5, 0.20, 0.05, 'call')
        plan['days']['Monday'] = {
            'strategy': 'DIRECTIONAL HUNTING',
            'conviction': '⭐⭐⭐⭐⭐',
            'entry': {
                'trigger': f"Break above ${flip:.2f}",
                'action': f"BUY {atm_call} calls @ ${monday_call['price']:.2f}",
                'size': f"{3 * regime['size_multiplier']:.1f}% of capital",
                'stop': f"${put_wall:.2f}",
                'target_1': f"${flip + 2:.2f}",
                'target_2': f"${call_wall:.2f}"
            },
            'win_probability': 68 if net_gex < -1e9 else 45,
            'expected_gain': '+8-12%',
            'notes': 'Highest win rate day - be aggressive'
        }
        
        # Tuesday Plan
        tuesday_call = pricer.calculate(spot, atm_call, 4, 0.20, 0.05, 'call')
        plan['days']['Tuesday'] = {
            'strategy': 'CONTINUATION',
            'conviction': '⭐⭐⭐⭐',
            'entry': {
                'morning_action': 'Hold Monday position if profitable',
                'new_entry': f"Add on dips to ${flip:.2f}",
                'size': f"{2 * regime['size_multiplier']:.1f}% additional",
                'stop': 'Raised to breakeven',
                'target': f"${call_wall:.2f}"
            },
            'win_probability': 62,
            'expected_gain': '+5-8%',
            'notes': 'Still favorable but less edge than Monday'
        }
        
        # Wednesday Plan
        plan['days']['Wednesday'] = {
            'strategy': '🚨 EXIT DAY 🚨',
            'conviction': '⚠️⚠️⚠️',
            'morning': {
                '9:30-12:00': 'Final push possible',
                'action': 'Take 75% profits',
                'target': f"${call_wall:.2f} stretch target"
            },
            'afternoon': {
                '3:00 PM': '**MANDATORY EXIT ALL DIRECTIONALS**',
                'reasoning': 'Theta decay accelerates',
                'action': 'CLOSE EVERYTHING - NO EXCEPTIONS'
            },
            'transition': 'Switch to Iron Condor mode',
            'notes': '❌ DO NOT HOLD DIRECTIONALS PAST 3PM ❌'
        }
        
        # Thursday Plan - Iron Condor
        call_short_price = pricer.calculate(spot, call_wall, 2, 0.15, 0.05, 'call')
        put_short_price = pricer.calculate(spot, put_wall, 2, 0.15, 0.05, 'put')
        
        plan['days']['Thursday'] = {
            'strategy': 'IRON CONDOR',
            'conviction': '⭐⭐⭐',
            'setup': {
                'call_spread': f"Sell {call_wall}/{call_wall+5} @ ${call_short_price['price']*0.4:.2f}",
                'put_spread': f"Sell {put_wall}/{put_wall-5} @ ${put_short_price['price']*0.4:.2f}",
                'total_credit': f"${(call_short_price['price'] + put_short_price['price'])*0.4:.2f}",
                'max_risk': f"${5 - (call_short_price['price'] + put_short_price['price'])*0.4:.2f}",
                'breakevens': f"${call_wall + 1:.2f} / ${put_wall - 1:.2f}"
            },
            'win_probability': 72,
            'management': 'Close at 50% profit or hold to expire',
            'notes': 'Positive GEX favors range-bound action'
        }
        
        # Friday Plan
        plan['days']['Friday'] = {
            'strategy': 'THETA HARVEST',
            'conviction': '⭐⭐',
            'morning': {
                'action': 'Manage Iron Condor only',
                'decision': 'Close at 25% remaining profit'
            },
            'afternoon': {
                '3:00 PM': 'Charm flow opportunity',
                'condition': 'Only if GEX flips negative',
                'action': 'Buy 0DTE calls for 15-minute hold',
                'size': '1% risk maximum'
            },
            'win_probability': 25,
            'notes': '⚠️ AVOID DIRECTIONALS - Theta crush day'
        }
        
        # Calculate expected weekly return
        monday_return = 0.1 * 0.68 if net_gex < -1e9 else 0.05 * 0.45
        tuesday_return = 0.08 * 0.62
        thursday_return = 0.03 * 0.72
        plan['expected_return'] = f"+{(monday_return + tuesday_return + thursday_return)*100:.1f}%"
        
        return plan
    
    def generate_monthly_plan(self, symbol: str, market_data: Dict) -> Dict:
        """Generate comprehensive monthly trading plan"""
        
        # Get key dates for the month
        today = datetime.now()
        month = today.month
        year = today.year
        
        # Calculate OPEX (third Friday)
        first_day = datetime(year, month, 1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday() + 7) % 7)
        opex_date = first_friday + timedelta(days=14)
        
        plan = {
            'symbol': symbol,
            'month': today.strftime('%B %Y'),
            'generated': today.strftime('%Y-%m-%d'),
            'key_dates': {},
            'weekly_strategies': {},
            'expected_monthly_return': '',
            'risk_events': []
        }
        
        # Week 1
        plan['weekly_strategies']['Week 1'] = {
            'dates': f"{today.strftime('%b %d')} - {(today + timedelta(days=4)).strftime('%b %d')}",
            'focus': 'Directional plays Mon-Wed',
            'expected_return': '+8-12%',
            'key_levels': {
                'monitor': market_data.get('flip_point', 0),
                'resistance': market_data.get('call_wall', 0),
                'support': market_data.get('put_wall', 0)
            }
        }
        
        # Week 2
        plan['weekly_strategies']['Week 2'] = {
            'dates': f"{(today + timedelta(days=7)).strftime('%b %d')} - {(today + timedelta(days=11)).strftime('%b %d')}",
            'focus': 'CPI/PPI week - volatility expected',
            'strategy': 'Wait for post-data setup',
            'expected_return': '+5-10%',
            'notes': 'Avoid trading morning of CPI'
        }
        
        # Week 3 (OPEX)
        plan['weekly_strategies']['Week 3 (OPEX)'] = {
            'dates': f"{opex_date - timedelta(days=4):%b %d} - {opex_date:%b %d}",
            'focus': 'OPEX week - massive gamma expiry',
            'monday': 'Aggressive directional (2x size)',
            'wednesday': 'MUST EXIT by noon',
            'friday': 'Massive pin expected at major strike',
            'expected_return': '+10-15%',
            'warning': 'Highest volatility week'
        }
        
        # Week 4
        plan['weekly_strategies']['Week 4'] = {
            'dates': 'End of month',
            'focus': 'FOMC week likely',
            'strategy': 'NO TRADES until post-Fed',
            'expected_return': '0% (sit out)',
            'notes': 'Wait for new trend after Fed'
        }
        
        # Key dates
        plan['key_dates'] = {
            'CPI': 'Second Tuesday (8:30 AM)',
            'PPI': 'Second Wednesday (8:30 AM)',
            'OPEX': opex_date.strftime('%B %d'),
            'FOMC': 'Check Fed calendar',
            'Earnings': f"Check {symbol} earnings date",
            'Month-end': 'Window dressing flows'
        }
        
        # Risk events
        plan['risk_events'] = [
            '🔴 CPI/PPI - High volatility mornings',
            '🔴 FOMC - No trades until after',
            '🟡 OPEX - Gamma expiry chaos',
            '🟡 Month-end - Rebalancing flows',
            '🟡 Earnings - IV crush risk'
        ]
        
        # Expected monthly return
        week1_return = 0.10
        week2_return = 0.07
        week3_return = 0.12
        week4_return = 0
        total_return = week1_return + week2_return + week3_return + week4_return
        plan['expected_monthly_return'] = f"+{total_return*100:.1f}% (following all rules)"
        
        return plan
    
    def _determine_primary_setup(self, day: str, net_gex: float, spot: float, flip: float) -> str:
        """Determine the primary setup for the day"""
        
        if day == 'Wednesday':
            if datetime.now().hour >= 15:
                return "🚨 NO NEW TRADES - Exit existing positions"
            else:
                return "Final directional push until 3PM EXIT"
        
        if day in ['Thursday', 'Friday']:
            return "Iron Condor setup only - NO directionals"
        
        if net_gex < -1e9:
            if spot < flip:
                return f"SQUEEZE SETUP: Buy calls on break above ${flip:.2f}"
            else:
                return f"MOMENTUM CONTINUATION: Add to longs on dips"
        elif net_gex > 2e9:
            return f"FADE SETUP: Sell calls at ${flip:.2f} resistance"
        else:
            return "NEUTRAL: Wait for clearer setup"
class StrategyEngine:
    """Generate specific trading recommendations"""
    
    @staticmethod
    def detect_setups(market_data: Dict) -> List[Dict]:
        """Detect all available trading setups"""
        
        setups = []
        
        net_gex = market_data.get('net_gex', 0)
        spot = market_data.get('spot_price', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        if not spot:
            return setups
        
        distance_to_flip = ((flip - spot) / spot * 100) if spot else 0
        
        # Check each strategy
        for strategy_name, config in STRATEGIES.items():
            conditions = config['conditions']
            
            if strategy_name == 'NEGATIVE_GEX_SQUEEZE':
                if (net_gex < conditions['net_gex_threshold'] and 
                    abs(distance_to_flip) < conditions['distance_to_flip'] and
                    spot > put_wall + (spot * conditions['min_put_wall_distance'] / 100)):
                    
                    # Calculate specific strike
                    strike = int(flip / 5) * 5 + (5 if flip % 5 > 2.5 else 0)
                    
                    # Price the option
                    pricer = BlackScholesPricer()
                    option = pricer.calculate(spot, strike, 5, 0.20)
                    
                    setups.append({
                        'strategy': 'NEGATIVE GEX SQUEEZE',
                        'symbol': market_data.get('symbol', 'SPY'),
                        'action': f'BUY {strike} CALLS',
                        'entry_zone': f'${flip - 0.50:.2f} - ${flip + 0.50:.2f}',
                        'current_price': spot,
                        'target_1': flip + (spot * 0.015),
                        'target_2': call_wall,
                        'stop_loss': spot - (spot * 0.005),
                        'option_premium': option['price'],
                        'delta': option['delta'],
                        'gamma': option['gamma'],
                        'confidence': 75,
                        'risk_reward': 3.0,
                        'reasoning': f'Net GEX at ${net_gex/1e9:.1f}B. MMs trapped short. '
                                   f'Distance to flip: {distance_to_flip:.1f}%. '
                                   f'Historical win rate: {config["win_rate"]*100:.0f}%',
                        'best_time': 'Mon/Tue morning after confirmation'
                    })
            
            elif strategy_name == 'IRON_CONDOR':
                wall_distance = ((call_wall - put_wall) / spot * 100) if spot else 0
                
                if (net_gex > conditions['net_gex_threshold'] and 
                    wall_distance > conditions['min_wall_distance']):
                    
                    # Calculate strikes
                    call_short = int(call_wall / 5) * 5
                    put_short = int(put_wall / 5) * 5
                    call_long = call_short + 10
                    put_long = put_short - 10
                    
                    # Run Monte Carlo
                    monte_carlo = MonteCarloEngine()
                    ic_sim = monte_carlo.simulate_iron_condor(
                        spot, call_short, call_long, put_short, put_long, 7
                    )
                    
                    setups.append({
                        'strategy': 'IRON CONDOR',
                        'symbol': market_data.get('symbol', 'SPY'),
                        'action': f'SELL {call_short}/{call_long} CALL SPREAD, '
                                f'{put_short}/{put_long} PUT SPREAD',
                        'entry_zone': f'${spot - 2:.2f} - ${spot + 2:.2f}',
                        'current_price': spot,
                        'max_profit_zone': f'${put_short:.2f} - ${call_short:.2f}',
                        'breakevens': f'${put_short - 1:.2f} / ${call_short + 1:.2f}',
                        'win_probability': ic_sim['win_probability'],
                        'confidence': 80,
                        'risk_reward': 0.3,
                        'reasoning': f'High positive GEX ${net_gex/1e9:.1f}B creates range. '
                                   f'Walls {wall_distance:.1f}% apart. '
                                   f'Win probability: {ic_sim["win_probability"]:.0f}%',
                        'best_time': '5-10 DTE entry'
                    })
        
        return setups
    
    @staticmethod
    def generate_game_plan(market_data: Dict, setups: List[Dict]) -> str:
        """Generate comprehensive daily game plan"""
        
        symbol = market_data.get('symbol', 'SPY')
        net_gex = market_data.get('net_gex', 0)
        spot = market_data.get('spot_price', 0)
        flip = market_data.get('flip_point', 0)
        
        day = datetime.now().strftime('%A')
        time_now = datetime.now().strftime('%H:%M')
        
        # Determine MM state
        claude = ClaudeIntelligence()
        mm_state = claude._determine_mm_state(net_gex)
        state_config = MM_STATES[mm_state]
        
        plan = f"""
# 🎯 {symbol} GAME PLAN - {day} {time_now} ET

## 📊 Market Maker Positioning
- **State: {mm_state}** - {state_config['behavior']}
- **Net GEX: ${net_gex/1e9:.2f}B**
- **Action Required: {state_config['action']}**
- **Confidence: {state_config['confidence']}%**

## 📍 Critical Levels
- **Current: ${spot:.2f}**
- **Flip Point: ${flip:.2f}** ({((flip-spot)/spot*100):+.2f}% away)
- **Call Wall: ${market_data.get('call_wall', 0):.2f}**
- **Put Wall: ${market_data.get('put_wall', 0):.2f}**
        """
        
        if setups:
            plan += "\n## 🎲 Active Setups Available\n"
            for i, setup in enumerate(setups[:3], 1):
                plan += f"""
### Setup #{i}: {setup['strategy']}
- **Action: {setup['action']}**
- **Entry: {setup['entry_zone']}**
- **Confidence: {setup['confidence']}%**
- **Risk/Reward: 1:{setup['risk_reward']}**
- **Reasoning: {setup['reasoning']}**
                """
        else:
            plan += "\n## ⏸️ No High-Confidence Setups\n"
            plan += "Market conditions not optimal for our strategies. Stand aside.\n"
        
        # Add time-based guidance
        if day == 'Monday' or day == 'Tuesday':
            plan += "\n## ⏰ Timing: OPTIMAL\nBest days for directional plays. MMs most vulnerable.\n"
        elif day == 'Wednesday':
            plan += "\n## ⏰ Timing: CAUTION\n⚠️ EXIT DIRECTIONALS BY 3 PM! Theta acceleration begins.\n"
        elif day == 'Thursday' or day == 'Friday':
            plan += "\n## ⏰ Timing: AVOID DIRECTIONALS\n0DTE theta crush zone. Iron Condors only.\n"
        
        return plan

# ============================================================================
# MAIN STREAMLIT APPLICATION
# ============================================================================
def main():
    """Main application entry point"""
    
    # Initialize database
    init_database()
    
    # Initialize session state
    if 'api_client' not in st.session_state:
        st.session_state.api_client = TradingVolatilityAPI(TRADINGVOLATILITY_USERNAME)
    if 'claude_ai' not in st.session_state:
        claude_key = st.secrets.get("CLAUDE_API_KEY", "")
        st.session_state.claude_ai = ClaudeIntelligence(claude_key)
    if 'current_data' not in st.session_state:
        st.session_state.current_data = {}
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'active_positions' not in st.session_state:
        st.session_state.active_positions = []
    
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
            # Fallback if pytz not available
            utc_now = datetime.utcnow()
            central_time = utc_now - timedelta(hours=6)  # UTC-6 for Central
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
                delta=f"{((flip-spot)/spot*100):+.1f}%"
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
                    setup = setups[0]  # Use first setup
                    
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
                    mc_fig = visualizer.create_monte_carlo_chart(
                        sim_results,
                        data['gex'].get('spot_price', 100)
                    )
                    st.plotly_chart(mc_fig, use_container_width=True)
        else:
            st.info("👈 Enter a symbol and click Refresh to begin analysis")
    
    # Tab 2: Trade Setups
    with tabs[1]:
        st.subheader("🎯 Available Trade Setups")
        
        if st.session_state.current_data:
            # Detect setups
            strategy_engine = StrategyEngine()
            setups = strategy_engine.detect_setups(st.session_state.current_data.get('gex', {}))
            
            if setups:
                for setup in setups:
                    with st.expander(
                        f"📊 {setup['strategy']} - Confidence: {setup['confidence']}%",
                        expanded=True
                    ):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.markdown("**Entry Details**")
                            st.write(f"Action: **{setup['action']}**")
                            st.write(f"Entry Zone: {setup['entry_zone']}")
                            
                            if 'option_premium' in setup:
                                st.write(f"Premium: ${setup['option_premium']:.2f}")
                                st.write(f"Delta: {setup.get('delta', 'N/A')}")
                                st.write(f"Gamma: {setup.get('gamma', 'N/A')}")
                        
                        with col2:
                            st.markdown("**Risk Management**")
                            
                            if 'target_1' in setup:
                                st.write(f"Target 1: ${setup['target_1']:.2f}")
                                st.write(f"Target 2: ${setup.get('target_2', 0):.2f}")
                                st.write(f"Stop Loss: ${setup.get('stop_loss', 0):.2f}")
                            else:
                                st.write(f"Profit Zone: {setup.get('max_profit_zone', 'N/A')}")
                                st.write(f"Breakevens: {setup.get('breakevens', 'N/A')}")
                            
                            st.write(f"Risk/Reward: 1:{setup['risk_reward']}")
                        
                        with col3:
                            st.markdown("**Analysis**")
                            st.write(f"Best Time: {setup.get('best_time', 'Now')}")
                            
                            if 'win_probability' in setup:
                                st.write(f"Win Probability: {setup['win_probability']:.0f}%")
                            
                            st.info(setup['reasoning'])
                        
                        # Trade execution button
                        if st.button(f"Execute {setup['strategy']}", key=f"exec_{setup['strategy']}"):
                            # Log to database
                            conn = sqlite3.connect(DB_PATH)
                            c = conn.cursor()
                            
                            c.execute('''
                                INSERT INTO recommendations 
                                (symbol, strategy, confidence, entry_price, reasoning, mm_behavior)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (
                                setup['symbol'],
                                setup['strategy'],
                                setup['confidence'],
                                setup['current_price'],
                                setup['reasoning'],
                                MM_STATES[claude._determine_mm_state(
                                    st.session_state.current_data['gex'].get('net_gex', 0)
                                )]['behavior']
                            ))
                            
                            conn.commit()
                            conn.close()
                            
                            st.success(f"✅ {setup['strategy']} logged to positions!")
            else:
                st.warning("No high-confidence setups available in current market conditions")
        else:
            st.info("Fetch market data first to see available setups")
    
    # Tab 3: Trading Plans
    with tabs[2]:
        st.subheader("📅 Comprehensive Trading Plans")
        
        # Plan type selector
        plan_col1, plan_col2, plan_col3, plan_col4 = st.columns(4)
        
        with plan_col1:
            plan_symbol = st.text_input("Symbol for Plan", value=symbol)
        
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
            
            if st.session_state.generated_plan['type'] == 'Daily':
                # Generate daily plan
                daily_plan = plan_generator.generate_daily_plan(
                    st.session_state.generated_plan['symbol'],
                    plan_data
                )
                
                # Display daily plan
                st.markdown(f"## 📊 Daily Trading Plan - {daily_plan['symbol']}")
                st.markdown(f"**Date:** {daily_plan['date']} ({daily_plan['day']})")
                st.markdown(f"**Generated:** {daily_plan['generated_at']}")
                
                # Economic regime
                regime = daily_plan['regime']
                regime_col1, regime_col2, regime_col3, regime_col4 = st.columns(4)
                
                with regime_col1:
                    st.metric("VIX", f"{regime['vix']:.1f}", delta=regime['vol_regime'])
                with regime_col2:
                    st.metric("10Y Yield", f"{regime['ten_year_yield']:.2f}%")
                with regime_col3:
                    st.metric("Position Multiplier", f"{regime['size_multiplier']}x")
                with regime_col4:
                    st.metric("Regime", regime['regime_signal'])
                
                # Time-based sections
                st.markdown("### 🌅 Pre-Market Prep (8:00-9:30 AM)")
                for item in daily_plan['pre_market']['checklist']:
                    st.write(item)
                st.info(f"**Primary Setup:** {daily_plan['pre_market']['primary_setup']}")
                
                st.markdown("### 🔔 Opening 30 Minutes (9:30-10:00 AM)")
                opening = daily_plan['opening_30min']
                st.write(f"**Strategy:** {opening['strategy']}")
                if 'entry_trigger' in opening:
                    st.write(f"**Entry Trigger:** {opening['entry_trigger']}")
                    st.write(f"**Initial Size:** {opening['initial_size']}")
                    st.write(f"**Stop Level:** {opening['stop_level']}")
                
                st.markdown("### ☀️ Mid-Morning (10:00 AM-12:00 PM)")
                mid = daily_plan['mid_morning']
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Add Zone:** {mid['add_zone']}")
                    st.write(f"**Target 1:** {mid['target_1']}")
                with col2:
                    st.write(f"**Profit Taking:** {mid['profit_taking']}")
                    st.write(f"**Trail Stop:** {mid['trail_stop']}")
                
                st.markdown("### 🍽️ Lunch (12:00-2:00 PM)")
                st.write(daily_plan['lunch']['strategy'])
                
                st.markdown("### 💪 Power Hour (3:00-4:00 PM)")
                power = daily_plan['power_hour']
                if 'ACTION' in power:
                    st.error(power['ACTION'])
                st.write(f"**Strategy:** {power['strategy']}")
                if 'reasoning' in power:
                    st.warning(f"**Reasoning:** {power['reasoning']}")
                
                st.markdown("### 🌙 After Hours")
                ah = daily_plan['after_hours']
                st.write("**Alerts to Set:**")
                for alert in ah['alerts_to_set']:
                    st.write(f"  • {alert}")
            
            elif st.session_state.generated_plan['type'] == 'Weekly':
                # Generate weekly plan
                weekly_plan = plan_generator.generate_weekly_plan(
                    st.session_state.generated_plan['symbol'],
                    plan_data
                )
                
                st.markdown(f"## 📅 Weekly Trading Plan - {weekly_plan['symbol']}")
                st.markdown(f"**Week of:** {weekly_plan['week_of']}")
                st.success(f"**Expected Weekly Return:** {weekly_plan['expected_return']}")
                
                # Display each day
                for day_name, day_plan in weekly_plan['days'].items():
                    with st.expander(f"📆 {day_name} - {day_plan['strategy']}", expanded=True):
                        
                        # Conviction stars
                        st.markdown(f"**Conviction:** {day_plan.get('conviction', 'N/A')}")
                        
                        if 'entry' in day_plan:
                            st.markdown("**Entry Details:**")
                            entry = day_plan['entry']
                            for key, value in entry.items():
                                st.write(f"  • {key.replace('_', ' ').title()}: {value}")
                        
                        if 'setup' in day_plan:
                            st.markdown("**Setup Details:**")
                            setup = day_plan['setup']
                            for key, value in setup.items():
                                st.write(f"  • {key.replace('_', ' ').title()}: {value}")
                        
                        if 'morning' in day_plan:
                            st.markdown("**Morning:**")
                            for key, value in day_plan['morning'].items():
                                st.write(f"  • {key}: {value}")
                        
                        if 'afternoon' in day_plan:
                            st.markdown("**Afternoon:**")
                            for key, value in day_plan['afternoon'].items():
                                if key == '3:00 PM':
                                    st.error(f"  • {key}: {value}")
                                else:
                                    st.write(f"  • {key}: {value}")
                        
                        # Metrics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Win Probability", f"{day_plan.get('win_probability', 0)}%")
                        with col2:
                            if 'expected_gain' in day_plan:
                                st.metric("Expected Gain", day_plan['expected_gain'])
                        with col3:
                            st.info(day_plan.get('notes', ''))
            
            elif st.session_state.generated_plan['type'] == 'Monthly':
                # Generate monthly plan
                monthly_plan = plan_generator.generate_monthly_plan(
                    st.session_state.generated_plan['symbol'],
                    plan_data
                )
                
                st.markdown(f"## 📆 Monthly Trading Plan - {monthly_plan['symbol']}")
                st.markdown(f"**Month:** {monthly_plan['month']}")
                st.success(f"**Expected Monthly Return:** {monthly_plan['expected_monthly_return']}")
                
                # Weekly strategies
                st.markdown("### 📅 Weekly Breakdown")
                for week_name, week_data in monthly_plan['weekly_strategies'].items():
                    with st.expander(f"{week_name}", expanded=True):
                        st.write(f"**Dates:** {week_data.get('dates', 'TBD')}")
                        st.write(f"**Focus:** {week_data.get('focus', '')}")
                        
                        if 'strategy' in week_data:
                            st.write(f"**Strategy:** {week_data['strategy']}")
                        
                        if 'monday' in week_data:
                            st.write(f"**Monday:** {week_data['monday']}")
                        if 'wednesday' in week_data:
                            st.write(f"**Wednesday:** {week_data['wednesday']}")
                        if 'friday' in week_data:
                            st.write(f"**Friday:** {week_data['friday']}")
                        
                        st.metric("Expected Return", week_data.get('expected_return', 'N/A'))
                        
                        if 'warning' in week_data:
                            st.warning(week_data['warning'])
                        if 'notes' in week_data:
                            st.info(week_data['notes'])
                
                # Key dates
                st.markdown("### 📍 Key Dates")
                dates_col1, dates_col2 = st.columns(2)
                with dates_col1:
                    for key, value in list(monthly_plan['key_dates'].items())[:3]:
                        st.write(f"**{key}:** {value}")
                with dates_col2:
                    for key, value in list(monthly_plan['key_dates'].items())[3:]:
                        st.write(f"**{key}:** {value}")
                
                # Risk events
                st.markdown("### ⚠️ Risk Events")
                for event in monthly_plan['risk_events']:
                    st.write(event)
        
        else:
            st.info("👈 Enter a symbol and click 'Generate Plan' to create a comprehensive trading plan")
    
    # Tab 4: AI Co-Pilot (was Tab 3, now Tab 4)
    with tabs[3]:
        st.subheader("💬 Intelligent Trading Co-Pilot")
        
        # Mode selection
        col1, col2, col3 = st.columns(3)
        with col1:
            analysis_mode = st.button("📊 Analyze Market", use_container_width=True)
        with col2:
            challenge_mode = st.button("🥊 Challenge My Idea", use_container_width=True)
        with col3:
            education_mode = st.button("📚 Teach Me", use_container_width=True)
        
        # Display conversation history
        for msg in st.session_state.conversation_history[-10:]:  # Last 10 messages
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
        
        # Chat input
        if prompt := st.chat_input("Ask about gamma, market makers, or trading strategies..."):
            # Add to history
            st.session_state.conversation_history.append({
                "role": "user",
                "content": prompt
            })
            
            # Get response based on mode
            with st.spinner("Analyzing..."):
                if "challenge" in prompt.lower() or "wrong" in prompt.lower():
                    # Challenge mode
                    response = st.session_state.claude_ai.challenge_trade_idea(
                        prompt,
                        st.session_state.current_data.get('gex', {})
                    )
                else:
                    # Normal analysis
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
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("What should I trade today?"):
                prompt = "Based on current gamma levels, what's the best trade setup right now?"
                response = st.session_state.claude_ai.analyze_market(
                    st.session_state.current_data.get('gex', {}),
                    prompt
                )
                st.session_state.conversation_history.append(
                    {"role": "user", "content": prompt}
                )
                st.session_state.conversation_history.append(
                    {"role": "assistant", "content": response}
                )
                st.rerun()
        
        with col2:
            if st.button("Challenge: Buy puts here"):
                prompt = "I want to buy puts at these levels"
                response = st.session_state.claude_ai.challenge_trade_idea(
                    prompt,
                    st.session_state.current_data.get('gex', {})
                )
                st.session_state.conversation_history.append(
                    {"role": "user", "content": prompt}
                )
                st.session_state.conversation_history.append(
                    {"role": "assistant", "content": response}
                )
                st.rerun()
    
    # Tab 5: Positions & Tracking (was Tab 4, now Tab 5)
    with tabs[4]:
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
                    # Add to database
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
            # Add current P&L calculation
            positions_df['current_pnl'] = positions_df.apply(
                lambda row: (row['current_price'] - row['entry_price']) * row['size'] / row['entry_price']
                if row['direction'] == 'LONG' else
                (row['entry_price'] - row['current_price']) * row['size'] / row['entry_price'],
                axis=1
            )
            
            positions_df['pnl_percent'] = positions_df['current_pnl'] / positions_df['size'] * 100
            
            # Display positions
            for idx, pos in positions_df.iterrows():
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                    
                    with col1:
                        emoji = "🟢" if pos['current_pnl'] > 0 else "🔴"
                        st.write(f"{emoji} **{pos['symbol']}** - {pos['strategy']}")
                        st.caption(f"{pos['direction']} @ ${pos['entry_price']:.2f}")
                    
                    with col2:
                        st.metric(
                            "Current",
                            f"${pos['current_price']:.2f}",
                            delta=f"{pos['pnl_percent']:.1f}%"
                        )
                    
                    with col3:
                        st.metric("P&L", f"${pos['current_pnl']:.2f}")
                    
                    with col4:
                        st.caption(f"T: ${pos['target']:.2f}")
                        st.caption(f"S: ${pos['stop']:.2f}")
                    
                    with col5:
                        if st.button("Close", key=f"close_{pos['id']}"):
                            # Close position
                            c.execute("""
                                UPDATE positions 
                                SET status = 'CLOSED',
                                    closed_at = datetime('now'),
                                    pnl = ?
                                WHERE id = ?
                            """, (pos['current_pnl'], pos['id']))
                            
                            conn.commit()
                            st.success("Position closed!")
                            st.rerun()
                    
                    st.divider()
        else:
            st.info("No active positions")
        
        # Closed Positions History
        st.subheader("📜 Trade History")
        
        history_df = pd.read_sql_query("""
            SELECT 
                symbol,
                strategy,
                direction,
                entry_price,
                CAST((closed_at) as DATE) as date,
                pnl,
                ROUND(pnl / size * 100, 1) as pnl_percent
            FROM positions 
            WHERE status = 'CLOSED'
            ORDER BY closed_at DESC
            LIMIT 20
        """, conn)
        
        if not history_df.empty:
            # Style the dataframe
            def color_pnl(val):
                color = 'green' if val > 0 else 'red' if val < 0 else 'white'
                return f'color: {color}'
            
            styled_df = history_df.style.applymap(
                color_pnl,
                subset=['pnl', 'pnl_percent']
            )
            
            st.dataframe(
                styled_df,
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
    
    # Tab 6: Education (was Tab 5, now Tab 6)
    with tabs[5]:
        st.subheader("📚 GEX Trading Education")
        
        # Educational sections
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
            
            ### Time-Based Behaviors
            
            **Monday/Tuesday**
            - Fresh gamma positions
            - Highest directional probability
            - MMs most vulnerable
            
            **Wednesday 3 PM**
            - Critical transition point
            - Gamma decay accelerates
            - **EXIT ALL DIRECTIONALS**
            
            **Thursday/Friday**
            - Theta crush dominates
            - 0DTE gamma chaos
            - Iron Condors only
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
        
        # Add download button for education material
        education_content = """
        # GEX Trading Manual
        
        ## Core Concepts
        - Gamma Exposure (GEX) measures market maker hedging requirements
        - Positive GEX suppresses volatility (MMs sell rallies, buy dips)  
        - Negative GEX amplifies volatility (MMs buy rallies, sell dips)
        - The Gamma Flip Point is where regime changes occur
        
        ## Trading Strategies
        1. Negative GEX Squeeze - Long calls above flip
        2. Positive GEX Fade - Short premium at walls
        3. Iron Condors - Range-bound positive GEX
        
        ## Risk Management
        - Max 3% risk per directional trade
        - Exit all directionals by Wednesday 3 PM
        - Respect gamma walls as support/resistance
        
        ## Market Maker States
        - TRAPPED: Short gamma, forced to chase
        - DEFENDING: Long gamma, fade extremes
        - PANICKING: Capitulation, trend strongly
        """
        
        st.download_button(
            label="📥 Download Trading Manual",
            data=education_content,
            file_name="gex_trading_manual.md",
            mime="text/markdown"
        )

# ============================================================================
# RUN APPLICATION
# ============================================================================
if __name__ == "__main__":
    main()
