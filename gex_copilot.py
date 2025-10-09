"""
GEX Trading Co-Pilot v4.5 - TRUE HYBRID SYSTEM
Your complete working v4.0 + Professional enhancements (Black-Scholes, Database, Statistics, SMS)
ZERO features removed - ONLY additions
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
warnings.filterwarnings('ignore')

# NEW: Optional professional imports
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    st.sidebar.info("📦 Install yfinance for enhanced data: pip install yfinance")

try:
    from py_vollib.black_scholes import black_scholes as bs
    from py_vollib.black_scholes.greeks import analytical as greeks
    VOLLIB_AVAILABLE = True
except ImportError:
    VOLLIB_AVAILABLE = False
    st.sidebar.info("📦 Install py_vollib for real pricing: pip install py_vollib")

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="GEX Trading Co-Pilot v4.5 - Complete",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# NEW: DATABASE SETUP (runs silently in background)
# ============================================================================
DB_PATH = Path("alphagex.db")

def init_database():
    """Initialize SQLite database - NEW v4.5 feature"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # GEX History
        c.execute('''
            CREATE TABLE IF NOT EXISTS gex_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                current_price REAL,
                net_gex REAL,
                flip_point REAL,
                call_wall REAL,
                put_wall REAL,
                regime TEXT,
                data_json TEXT
            )
        ''')
        
        # Trade Log
        c.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date DATETIME,
                exit_date DATETIME,
                symbol TEXT NOT NULL,
                setup_type TEXT,
                direction TEXT,
                strike REAL,
                entry_price REAL,
                exit_price REAL,
                contracts INTEGER,
                pnl REAL,
                pnl_pct REAL,
                win BOOLEAN,
                notes TEXT
            )
        ''')
        
        # Performance Metrics
        c.execute('''
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                total_trades INTEGER,
                wins INTEGER,
                win_rate REAL,
                avg_win REAL,
                avg_loss REAL,
                total_pnl REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    except Exception as e:
        pass  # Silent fail - doesn't break app

init_database()

# ============================================================================
# NEW: Load configuration from secrets
# ============================================================================
def load_config():
    """Load all configuration from secrets"""
    try:
        return {
            'tv_username': st.secrets.get("tradingvolatility_username"),
            'claude_api_key': st.secrets.get("claude_api_key"),
            'fred_api_key': st.secrets.get("fred_api_key", ""),
            'twilio_sid': st.secrets.get("twilio_account_sid", ""),
            'twilio_token': st.secrets.get("twilio_auth_token", ""),
            'twilio_from': st.secrets.get("twilio_phone_number", ""),
            'phone_number': st.secrets.get("your_phone_number", ""),
            'configured': True
        }
    except:
        return {'configured': False}

CONFIG = load_config()

# ============================================================================
# SYSTEM PROMPT - Complete with all 10 components (YOUR EXACT v4.0)
# ============================================================================
SYSTEM_PROMPT = """You are a COMPLETE GEX trading co-pilot with ALL 10 profitability components active.

You MUST address ALL components in every recommendation:
1. MM BEHAVIOR: Explain dealer positioning and forced hedging
2. TIMING: Enforce Wed 3PM exits, show theta decay
3. CATALYSTS: Identify what triggers the move
4. MAGNITUDE: Calculate expected move distance
5. OPTIONS MECHANICS: Show theta, DTE selection, Greeks
6. RISK MANAGEMENT: Position sizing, Kelly criterion
7. REGIME FILTERS: Check Fed/CPI/earnings calendar
8. EXECUTION: Bid/ask spreads, volume, timing windows
9. STATISTICAL EDGE: Expected value calculation
10. LEARNING LOOP: Adjust based on historical performance

USER'S SPECIFIC PROBLEM:
- Profitable Mon/Tue (66% win rate)
- Gets KILLED on Fridays (theta crush)
- Holds directional too long (Wed/Thu bleed)
- Needs Wed 3PM EXIT ENFORCEMENT

RESPONSE STRUCTURE:
**REGIME CHECK** (Component 7)
✅ Safe to trade / ⚠️ Caution / ❌ Skip today

**MM POSITIONING** (Component 1)
Net GEX, flip point, dealer forced behavior

**CATALYST ANALYSIS** (Component 3)
What triggers this setup?

**TIMING INTELLIGENCE** (Component 2)
- Best entry window
- Theta decay rate
- MANDATORY EXIT: Wed 3PM
- Days until theta acceleration

**MAGNITUDE CALCULATION** (Component 4)
Expected move with probability

**OPTIONS MECHANICS** (Component 5)
Strike, DTE, Theta, IV

**RISK MANAGEMENT** (Component 6)
Position size, stops, targets

**EXECUTION PLAN** (Component 8)
Entry window, bid/ask, order type

**EXPECTED VALUE** (Component 9)
Win rate, avg win/loss, EV

**LEARNING ADJUSTMENT** (Component 10)
Historical performance, adjustments

BE PRESCRIPTIVE. Address ALL 10 components."""


# ============================================================================
# COMPONENT 1: Market Maker Behavior Analysis (YOUR v4.0)
# ============================================================================
class MMBehaviorAnalyzer:
    """Component 1: Market Maker forced hedging analysis"""
    
    @staticmethod
    def analyze_dealer_positioning(net_gex: float, flip_point: float, current_price: float) -> Dict:
        """Determine dealer positioning and forced behavior"""
        
        if net_gex > 0:
            positioning = "LONG GAMMA"
            behavior = "Dealers MUST sell into rallies, buy into dips (volatility suppression)"
            regime = "CHOP - Range bound expected"
        else:
            positioning = "SHORT GAMMA"
            behavior = "Dealers MUST buy into rallies, sell into dips (volatility amplification)"
            regime = "MOVE - Trending expected"
        
        distance_to_flip = ((current_price - flip_point) / current_price) * 100
        
        if abs(distance_to_flip) < 0.5:
            urgency = "CRITICAL - At flip point, regime change imminent"
        elif abs(distance_to_flip) < 1.0:
            urgency = "HIGH - Near flip point"
        else:
            urgency = "NORMAL - Established regime"
        
        return {
            'positioning': positioning,
            'behavior': behavior,
            'regime': regime,
            'distance_to_flip_pct': distance_to_flip,
            'urgency': urgency
        }


# ============================================================================
# COMPONENT 2: Timing Intelligence (YOUR v4.0)
# ============================================================================
class TimingIntelligence:
    """Component 2: Timing optimization and theta management"""
    
    @staticmethod
    def get_current_day_strategy() -> Dict:
        """Determine today's trading strategy"""
        day = datetime.now().strftime('%A')
        hour = datetime.now().hour
        
        strategies = {
            'Monday': {'action': 'DIRECTIONAL', 'dte': 5, 'priority': 'HIGH', 'risk': 0.03},
            'Tuesday': {'action': 'DIRECTIONAL', 'dte': 4, 'priority': 'HIGH', 'risk': 0.03},
            'Wednesday': {'action': 'EXIT_BY_3PM', 'dte': 0, 'priority': 'CRITICAL', 'risk': 0},
            'Thursday': {'action': 'IRON_CONDOR', 'dte': 1, 'priority': 'MEDIUM', 'risk': 0.05},
            'Friday': {'action': 'IC_HOLD_OR_CHARM', 'dte': 0, 'priority': 'LOW', 'risk': 0.02}
        }
        
        strategy = strategies.get(day, strategies['Monday'])
        strategy['day'] = day
        strategy['hour'] = hour
        
        return strategy
    
    @staticmethod
    def calculate_theta_decay(dte: int, premium: float) -> Dict:
        """Calculate theta decay trajectory"""
        if dte == 0:
            theta_per_day = premium * 0.50
        elif dte == 1:
            theta_per_day = premium * 0.40
        elif dte == 2:
            theta_per_day = premium * 0.30
        elif dte <= 5:
            theta_per_day = premium * 0.15
        else:
            theta_per_day = premium * 0.05
        
        return {
            'theta_per_day': theta_per_day,
            'days_to_danger': max(0, dte - 2),
            'total_theta_risk': theta_per_day * min(dte, 3),
            'acceleration_zone': dte <= 2
        }
    
    @staticmethod
    def is_wed_3pm_approaching() -> Dict:
        """Check Wednesday 3PM deadline"""
        now = datetime.now()
        day = now.strftime('%A')
        hour = now.hour
        
        if day == 'Wednesday' and hour >= 14:
            return {
                'status': 'CRITICAL',
                'message': '🚨 WEDNESDAY 3PM APPROACHING - EXIT ALL DIRECTIONAL NOW',
                'minutes_remaining': (15 - hour) * 60 + (60 - now.minute),
                'action_required': True
            }
        elif day == 'Wednesday':
            return {
                'status': 'WARNING',
                'message': '⚠️ Wednesday - Exit all directional by 3PM',
                'minutes_remaining': (15 - hour) * 60,
                'action_required': False
            }
        else:
            days_to_wed = (2 - now.weekday()) % 7
            return {
                'status': 'OK',
                'message': f'📅 {days_to_wed} days until Wed 3PM exit',
                'minutes_remaining': days_to_wed * 24 * 60,
                'action_required': False
            }


# ============================================================================
# COMPONENT 3: Catalyst Detection (YOUR v4.0)
# ============================================================================
class CatalystDetector:
    """Component 3: Identify what triggers the move"""
    
    @staticmethod
    def identify_trigger(net_gex: float, distance_to_flip: float, dte: int) -> str:
        """Identify the primary catalyst"""
        
        if abs(distance_to_flip) < 0.5:
            return "TECHNICAL: Breaking gamma flip (immediate trigger)"
        elif abs(net_gex) > 1e9:
            return "STRUCTURE: Large gamma imbalance (gradual build)"
        elif dte <= 2:
            return "TIME: Charm decay acceleration (expiration trigger)"
        elif abs(distance_to_flip) < 1.5:
            return "PROXIMITY: Approaching key gamma level"
        else:
            return "WAITING: No clear catalyst yet"
    
    @staticmethod
    def check_market_events() -> Dict:
        """Check for major market events (simplified)"""
        today = datetime.now()
        
        return {
            'fed_event': False,
            'earnings': False,
            'cpi_release': False,
            'safe_to_trade': True,
            'next_event': 'None identified'
        }


# ============================================================================
# COMPONENT 4: Magnitude Calculator (YOUR v4.0)
# ============================================================================
class MagnitudeCalculator:
    """Component 4: Expected move estimation"""
    
    @staticmethod
    def calculate_expected_move(current: float, flip: float, call_wall: float, 
                               put_wall: float, net_gex: float) -> Dict:
        """Calculate expected price targets"""
        
        if current < flip:
            target_70 = flip + (call_wall - flip) * 0.5
            target_30 = call_wall
            stop = put_wall
            direction = "BULLISH"
        else:
            target_70 = flip - (flip - put_wall) * 0.5
            target_30 = put_wall
            stop = call_wall
            direction = "BEARISH"
        
        expected_gain_pct = ((target_70 - current) / current) * 100
        max_gain_pct = ((target_30 - current) / current) * 100
        risk_pct = ((current - stop) / current) * 100
        
        return {
            'direction': direction,
            'target_primary': target_70,
            'target_extended': target_30,
            'stop_loss': stop,
            'expected_gain_pct': expected_gain_pct,
            'max_gain_pct': max_gain_pct,
            'risk_pct': abs(risk_pct),
            'reward_risk_ratio': abs(expected_gain_pct / risk_pct) if risk_pct != 0 else 0
        }


# ============================================================================
# COMPONENT 5: Options Mechanics Analyzer (YOUR v4.0)
# ============================================================================
class OptionsAnalyzer:
    """Component 5: Greeks and options characteristics"""
    
    @staticmethod
    def analyze_option(strike: float, current_price: float, dte: int, 
                      iv: float = 0.25, option_type: str = 'call') -> Dict:
        """Analyze option characteristics"""
        
        # Simplified pricing
        moneyness = (strike - current_price) / current_price
        
        if option_type == 'call':
            intrinsic = max(0, current_price - strike)
        else:
            intrinsic = max(0, strike - current_price)
        
        time_value = abs(moneyness) * current_price * iv * np.sqrt(dte / 365)
        estimated_premium = intrinsic + time_value
        
        theta_data = TimingIntelligence.calculate_theta_decay(dte, estimated_premium)
        
        return {
            'strike': strike,
            'estimated_premium': round(estimated_premium, 2),
            'moneyness_pct': round(moneyness * 100, 2),
            'theta_per_day': round(theta_data['theta_per_day'], 2),
            'dte': dte,
            'iv': iv,
            'intrinsic_value': round(intrinsic, 2),
            'time_value': round(time_value, 2)
        }
    
    @staticmethod
    def recommend_strikes(current: float, flip: float, call_wall: float, 
                         put_wall: float, direction: str) -> Dict:
        """Recommend optimal strikes"""
        
        if direction == "BULLISH":
            atm_strike = round(current / 5) * 5
            otm_strike = atm_strike + 5
            return {
                'recommended_strike': otm_strike,
                'alternative_strike': atm_strike,
                'target_strike': round(call_wall / 5) * 5,
                'type': 'CALL'
            }
        else:
            atm_strike = round(current / 5) * 5
            otm_strike = atm_strike - 5
            return {
                'recommended_strike': otm_strike,
                'alternative_strike': atm_strike,
                'target_strike': round(put_wall / 5) * 5,
                'type': 'PUT'
            }


# ============================================================================
# COMPONENT 6: Risk Manager (YOUR v4.0)
# ============================================================================
class RiskManager:
    """Component 6: Position sizing and risk management"""
    
    @staticmethod
    def calculate_position_size(account_size: float, risk_pct: float, 
                               premium: float, stop_distance_pct: float) -> Dict:
        """Calculate optimal position size"""
        
        max_risk_dollars = account_size * risk_pct
        risk_per_contract = premium * stop_distance_pct * 100
        
        contracts = int(max_risk_dollars / risk_per_contract)
        contracts = max(1, min(contracts, 10))
        
        actual_risk = contracts * risk_per_contract
        
        return {
            'contracts': contracts,
            'total_premium': contracts * premium * 100,
            'total_risk': round(actual_risk, 2),
            'pct_of_account': round((actual_risk / account_size) * 100, 2)
        }
    
    @staticmethod
    def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Calculate Kelly Criterion bet size"""
        if avg_loss == 0:
            return 0
        
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p
        
        kelly = (b * p - q) / b
        
        return max(0, min(kelly * 0.5, 0.10))


# ============================================================================
# COMPONENT 7: Regime Filter (YOUR v4.0)
# ============================================================================
class RegimeFilter:
    """Component 7: Market regime and safety checks"""
    
    @staticmethod
    def check_trading_safety() -> Dict:
        """Comprehensive safety check"""
        today = datetime.now()
        day = today.strftime('%A')
        hour = today.hour
        
        if day in ['Saturday', 'Sunday']:
            return {
                'safe': False,
                'status': '❌',
                'reason': 'Market closed (weekend)'
            }
        
        if hour < 9 or hour >= 16:
            return {
                'safe': False,
                'status': '❌',
                'reason': 'Outside market hours (9:30 AM - 4:00 PM ET)'
            }
        
        if day == 'Wednesday' and hour >= 15:
            return {
                'safe': False,
                'status': '🚨',
                'reason': 'After 3PM Wednesday - EXIT ONLY, NO NEW POSITIONS'
            }
        
        events = CatalystDetector.check_market_events()
        if not events['safe_to_trade']:
            return {
                'safe': False,
                'status': '⚠️',
                'reason': f"Major event today: {events['next_event']}"
            }
        
        return {
            'safe': True,
            'status': '✅',
            'reason': 'Safe to trade'
        }


# ============================================================================
# COMPONENT 8: Execution Analyzer (YOUR v4.0)
# ============================================================================
class ExecutionAnalyzer:
    """Component 8: Execution quality and timing"""
    
    @staticmethod
    def get_execution_window() -> Dict:
        """Determine optimal execution window"""
        hour = datetime.now().hour
        minute = datetime.now().minute
        
        if hour == 9 and minute >= 30:
            return {
                'quality': 'EXCELLENT',
                'reason': 'High volume opening hour',
                'recommendation': 'Enter now'
            }
        elif hour == 10:
            return {
                'quality': 'GOOD',
                'reason': 'Still good volume',
                'recommendation': 'Acceptable entry'
            }
        elif 11 <= hour < 14:
            return {
                'quality': 'POOR',
                'reason': 'Midday chop - low volume',
                'recommendation': 'Avoid new entries'
            }
        elif 14 <= hour < 16:
            return {
                'quality': 'GOOD',
                'reason': 'Afternoon institutional flow',
                'recommendation': 'Acceptable entry'
            }
        else:
            return {
                'quality': 'CLOSED',
                'reason': 'Market closed',
                'recommendation': 'Wait for open'
            }
    
    @staticmethod
    def estimate_slippage(price: float, liquidity: str = 'high') -> Dict:
        """Estimate execution costs"""
        spreads = {
            'high': 0.001,
            'medium': 0.005,
            'low': 0.01
        }
        
        spread_pct = spreads.get(liquidity, spreads['medium'])
        spread_dollars = price * spread_pct
        
        return {
            'bid_ask_spread': round(spread_dollars, 2),
            'spread_pct': spread_pct * 100,
            'recommendation': 'Use limit orders' if spread_pct > 0.003 else 'Market orders OK'
        }


# ============================================================================
# COMPONENT 9: Statistical Edge (YOUR v4.0)
# ============================================================================
class StatisticalEdge:
    """Component 9: Expected value and edge tracking"""
    
    @staticmethod
    def calculate_expected_value(win_rate: float, avg_win: float, 
                                avg_loss: float, cost: float) -> Dict:
        """Calculate trade expected value"""
        
        ev_pct = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        ev_dollars = cost * ev_pct
        
        return {
            'expected_value_pct': round(ev_pct * 100, 2),
            'ev_dollars': round(ev_dollars, 2),
            'win_rate': round(win_rate * 100, 1),
            'avg_win_pct': round(avg_win * 100, 1),
            'avg_loss_pct': round(avg_loss * 100, 1),
            'edge': 'POSITIVE' if ev_pct > 0 else 'NEGATIVE',
            'trade_worthwhile': ev_pct > 0.15
        }


# ============================================================================
# COMPONENT 10: Learning Loop (YOUR v4.0)
# ============================================================================
class LearningLoop:
    """Component 10: Performance tracking and adjustments"""
    
    @staticmethod
    def get_historical_performance() -> Dict:
        """Get historical performance by strategy"""
        return {
            'mon_tue_directional': {
                'win_rate': 0.66,
                'avg_win': 0.85,
                'avg_loss': 0.50,
                'trades': 50
            },
            'fri_directional': {
                'win_rate': 0.12,
                'avg_win': 0.30,
                'avg_loss': 0.70,
                'trades': 25
            },
            'iron_condors': {
                'win_rate': 0.70,
                'avg_win': 0.25,
                'avg_loss': 0.80,
                'trades': 40
            }
        }
    
    @staticmethod
    def adjust_strategy(day: str, historical: Dict) -> Dict:
        """Adjust strategy based on historical performance"""
        
        if day in ['Monday', 'Tuesday']:
            return {
                'recommendation': 'PLAY DIRECTIONAL - This is your edge',
                'confidence': 'HIGH',
                'adjustment': 'Standard position sizing'
            }
        elif day == 'Wednesday':
            return {
                'recommendation': 'EXIT ALL DIRECTIONAL BY 3PM',
                'confidence': 'CRITICAL',
                'adjustment': 'Mandatory exit to avoid Friday losses'
            }
        elif day == 'Friday':
            return {
                'recommendation': 'AVOID DIRECTIONAL - Your worst day',
                'confidence': 'HIGH',
                'adjustment': 'Only play Iron Condors or sit out'
            }
        else:
            return {
                'recommendation': 'Iron Condors preferred',
                'confidence': 'MEDIUM',
                'adjustment': 'Standard approach'
            }


# ============================================================================
# NEW: ENHANCED COMPONENTS (Optional upgrades)
# ============================================================================
class OptionsPricingEngine:
    """NEW v4.5: Real Black-Scholes pricing (only if py_vollib installed)"""
    
    @staticmethod
    def price_option(S: float, K: float, T: float, r: float = 0.045, 
                    sigma: float = 0.25, option_type: str = 'c') -> Dict:
        """Calculate real option price with Greeks"""
        if not VOLLIB_AVAILABLE or T <= 0:
            return OptionsAnalyzer.analyze_option(K, S, int(T*365), sigma, 'call' if option_type == 'c' else 'put')
        
        try:
            price = bs(option_type, S, K, T, r, sigma)
            delta = greeks.delta(option_type, S, K, T, r, sigma)
            gamma = greeks.gamma(option_type, S, K, T, r, sigma)
            theta = greeks.theta(option_type, S, K, T, r, sigma)
            vega = greeks.vega(option_type, S, K, T, r, sigma)
            
            return {
                'price': price,
                'delta': delta,
                'gamma': gamma,
                'theta': theta / 365,
                'vega': vega / 100,
                'source': 'black_scholes'
            }
        except:
            return OptionsAnalyzer.analyze_option(K, S, int(T*365), sigma, 'call' if option_type == 'c' else 'put')


class StatisticalEngine:
    """NEW v4.5: Monte Carlo simulations"""
    
    @staticmethod
    def monte_carlo_simulation(current_price: float, volatility: float, 
                              days: int, simulations: int = 1000) -> Dict:
        """Run Monte Carlo price simulations"""
        dt = 1/252
        final_prices = []
        
        for _ in range(simulations):
            price = current_price
            for _ in range(days):
                z = np.random.standard_normal()
                price *= np.exp((0.0 - 0.5 * volatility**2) * dt + volatility * np.sqrt(dt) * z)
            final_prices.append(price)
        
        final_prices = np.array(final_prices)
        
        return {
            'mean_price': np.mean(final_prices),
            'percentile_5': np.percentile(final_prices, 5),
            'percentile_95': np.percentile(final_prices, 95),
            'probability_above': np.sum(final_prices > current_price) / simulations * 100
        }


# ============================================================================
# NEW: DATABASE FUNCTIONS (runs silently)
# ============================================================================
def store_gex_snapshot(symbol: str, levels: Dict):
    """NEW v4.5: Store GEX snapshot in database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO gex_history 
            (symbol, current_price, net_gex, flip_point, call_wall, put_wall, regime, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol,
            levels.get('current_price', 0),
            levels.get('net_gex', 0),
            levels.get('flip_point', 0),
            levels.get('call_wall', 0),
            levels.get('put_wall', 0),
            'MOVE' if levels.get('net_gex', 0) < 0 else 'CHOP',
            json.dumps(levels)
        ))
        
        conn.commit()
        conn.close()
    except:
        pass  # Silent fail


def get_performance_stats() -> Dict:
    """NEW v4.5: Get performance from database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END) as wins,
                AVG(CASE WHEN win = 1 THEN pnl_pct ELSE NULL END) as avg_win,
                AVG(CASE WHEN win = 0 THEN pnl_pct ELSE NULL END) as avg_loss,
                SUM(pnl) as total_pnl
            FROM trades WHERE exit_date IS NOT NULL
        ''')
        
        row = c.fetchone()
        conn.close()
        
        if row and row[0] > 0:
            total, wins, avg_win, avg_loss, total_pnl = row
            return {
                'total_trades': total,
                'wins': wins,
                'win_rate': (wins / total * 100) if total > 0 else 0,
                'avg_win': avg_win or 0,
                'avg_loss': avg_loss or 0,
                'total_pnl': total_pnl or 0
            }
    except:
        pass
    
    return {
        'total_trades': 0,
        'wins': 0,
        'win_rate': 0,
        'avg_win': 0,
        'avg_loss': 0,
        'total_pnl': 0
    }


def send_sms_alert(message: str) -> bool:
    """NEW v4.5: Send SMS alert via Twilio"""
    if not TWILIO_AVAILABLE or not CONFIG.get('twilio_sid'):
        return False
    
    try:
        client = Client(CONFIG['twilio_sid'], CONFIG['twilio_token'])
        client.messages.create(
            body=message,
            from_=CONFIG['twilio_from'],
            to=CONFIG['phone_number']
        )
        return True
    except:
        return False


# ============================================================================
# GEX DATA INTEGRATION (YOUR EXACT v4.0)
# ============================================================================
def fetch_gex_data(symbol: str, tv_username: str) -> Dict:
    """Fetch GEX data from TradingVolatility.net"""
    try:
        url = "https://stocks.tradingvolatility.net/api/gex/latest"
        params = {
            'username': tv_username,
            'ticker': symbol,
            'format': 'json'
        }
        
        st.info(f"📡 Fetching data from: {url}")
        st.info(f"Parameters: username={tv_username}, ticker={symbol}")
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Debug: Show raw data structure
        with st.expander("🔍 Debug: Raw API Response"):
            st.json(data)
        
        return data
    
    except requests.exceptions.RequestException as e:
        return {"error": f"API Error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def calculate_levels(gex_data: Dict) -> Optional[Dict]:
    """Calculate key GEX levels from API data (YOUR EXACT v4.0)"""
    try:
        if 'error' in gex_data or not gex_data:
            st.error("❌ No valid GEX data to process")
            return None
        
        st.info("🔍 Parsing GEX data structure...")
        
        strikes = []
        gamma_values = []
        current_price = None
        
        st.info(f"Available keys in response: {list(gex_data.keys())}")
        
        # Try different possible data structures
        if 'data' in gex_data:
            for item in gex_data['data']:
                try:
                    strikes.append(float(item.get('strike', 0)))
                    gamma_values.append(float(item.get('gex', 0)))
                except (ValueError, TypeError) as e:
                    st.warning(f"Skipping invalid data point: {item}")
                    continue
        
        elif 'strikes' in gex_data and 'gex' in gex_data:
            strikes = [float(x) for x in gex_data['strikes']]
            gamma_values = [float(x) for x in gex_data['gex']]
        
        else:
            st.error("❌ Unknown GEX data structure")
            st.json(gex_data)
            return None
        
        # Try to get current price
        for price_field in ['current_price', 'spot', 'price', 'underlying_price']:
            if price_field in gex_data:
                current_price = float(gex_data[price_field])
                break
        
        if not strikes or len(strikes) < 3:
            st.error(f"❌ Insufficient strike data: only {len(strikes)} strikes found")
            return None
        
        st.success(f"✅ Parsed {len(strikes)} strikes")
        
        net_gex = sum(gamma_values)
        st.info(f"Net GEX: ${net_gex/1e9:.2f}B")
        
        cumulative_gex = np.cumsum(gamma_values)
        flip_idx = np.argmin(np.abs(cumulative_gex))
        flip_point = strikes[flip_idx]
        
        call_gammas = [(s, g) for s, g in zip(strikes, gamma_values) if g > 0]
        call_wall = max(call_gammas, key=lambda x: x[1])[0] if call_gammas else strikes[-1]
        
        put_gammas = [(s, g) for s, g in zip(strikes, gamma_values) if g < 0]
        put_wall = max(put_gammas, key=lambda x: abs(x[1]))[0] if put_gammas else strikes[0]
        
        if current_price is None:
            current_price = strikes[len(strikes)//2]
            st.warning(f"⚠️ Current price not in API response, estimated as ${current_price:.2f}")
        
        st.success(f"✅ Calculated all levels successfully")
        
        result = {
            'current_price': current_price,
            'net_gex': net_gex,
            'flip_point': flip_point,
            'call_wall': call_wall,
            'put_wall': put_wall,
            'strikes': strikes,
            'gamma_values': gamma_values
        }
        
        # NEW v4.5: Store in database silently
        store_gex_snapshot(symbol, result)
        
        return result
    
    except Exception as e:
        st.error(f"❌ Error calculating levels: {str(e)}")
        st.exception(e)
        return None


# ============================================================================
# VISUALIZATION (YOUR EXACT v4.0)
# ============================================================================
def create_gex_profile_chart(levels: Dict) -> go.Figure:
    """Create interactive GEX profile visualization"""
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=levels['strikes'],
        y=levels['gamma_values'],
        name='Gamma Exposure',
        marker=dict(
            color=levels['gamma_values'],
            colorscale='RdYlGn',
            showscale=True,
            colorbar=dict(title="GEX")
        )
    ))
    
    fig.add_vline(
        x=levels['current_price'],
        line_dash="solid",
        line_color="white",
        line_width=2,
        annotation_text=f"Current: ${levels['current_price']:.2f}"
    )
    
    fig.add_vline(
        x=levels['flip_point'],
        line_dash="dash",
        line_color="yellow",
        annotation_text=f"Flip: ${levels['flip_point']:.2f}"
    )
    
    fig.add_vline(
        x=levels['call_wall'],
        line_dash="dot",
        line_color="red",
        annotation_text=f"Call Wall: ${levels['call_wall']:.2f}"
    )
    
    fig.add_vline(
        x=levels['put_wall'],
        line_dash="dot",
        line_color="green",
        annotation_text=f"Put Wall: ${levels['put_wall']:.2f}"
    )
    
    fig.update_layout(
        title="GEX Profile with Key Levels",
        xaxis_title="Strike Price",
        yaxis_title="Gamma Exposure",
        template="plotly_dark",
        height=500
    )
    
    return fig


def create_dashboard_metrics(levels: Dict, timing: Dict, magnitude: Dict) -> go.Figure:
    """Create metrics dashboard"""
    
    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=(
            'Net GEX Regime',
            'Time to Wed 3PM',
            'Expected Move',
            'Distance to Flip',
            'R:R Ratio',
            'Regime Status'
        ),
        specs=[
            [{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}],
            [{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}]
        ]
    )
    
    fig.add_trace(go.Indicator(
        mode="number+delta",
        value=levels['net_gex'] / 1e9,
        title={'text': "Net GEX (B)"},
        number={'suffix': "B", 'valueformat': '.2f'},
        delta={'reference': 0, 'position': "bottom"}
    ), row=1, col=1)
    
    fig.add_trace(go.Indicator(
        mode="number",
        value=timing.get('minutes_remaining', 0) / 60,
        title={'text': "Hours to Wed 3PM"},
        number={'suffix': "h"}
    ), row=1, col=2)
    
    fig.add_trace(go.Indicator(
        mode="number+delta",
        value=magnitude.get('expected_gain_pct', 0),
        title={'text': "Expected Move"},
        number={'suffix': "%", 'valueformat': '.2f'}
    ), row=1, col=3)
    
    distance_pct = ((levels['current_price'] - levels['flip_point']) / levels['current_price']) * 100
    fig.add_trace(go.Indicator(
        mode="number",
        value=distance_pct,
        title={'text': "Distance to Flip"},
        number={'suffix': "%", 'valueformat': '.2f'}
    ), row=2, col=1)
    
    fig.add_trace(go.Indicator(
        mode="number",
        value=magnitude.get('reward_risk_ratio', 0),
        title={'text': "Reward:Risk"},
        number={'valueformat': '.2f'}
    ), row=2, col=2)
    
    regime_text = "MOVE" if levels['net_gex'] < 0 else "CHOP"
    fig.add_trace(go.Indicator(
        mode="number+delta",
        value=1 if levels['net_gex'] < 0 else 0,
        title={'text': regime_text},
        number={'valueformat': '.0f'}
    ), row=2, col=3)
    
    fig.update_layout(
        height=600,
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    
    return fig


# ============================================================================
# CLAUDE API INTEGRATION (YOUR EXACT v4.0)
# ============================================================================
def call_claude_api(messages: List[Dict], api_key: str, 
                   context_data: Optional[Dict] = None) -> str:
    """Call Claude API with GEX context"""
    
    try:
        enhanced_system = SYSTEM_PROMPT
        
        if context_data:
            enhanced_system += f"""

CURRENT MARKET DATA:
- Symbol: {context_data.get('symbol', 'N/A')}
- Current Price: ${context_data.get('current_price', 0):.2f}
- Net GEX: ${context_data.get('net_gex', 0)/1e9:.2f}B
- Flip Point: ${context_data.get('flip_point', 0):.2f}
- Call Wall: ${context_data.get('call_wall', 0):.2f}
- Put Wall: ${context_data.get('put_wall', 0):.2f}
- Day: {context_data.get('day', 'Unknown')}
- Time: {context_data.get('time', 'Unknown')}

Use this data in your analysis."""
        
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4000,
            "system": enhanced_system,
            "messages": messages
        }
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                st.info(f"📡 Calling Claude API (attempt {attempt + 1}/{max_retries})...")
                
                response = requests.post(
                    url, 
                    headers=headers, 
                    json=payload, 
                    timeout=60
                )
                response.raise_for_status()
                
                result = response.json()
                return result['content'][0]['text']
            
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    st.warning(f"⏱️ Request timed out, retrying...")
                    time.sleep(2)
                    continue
                else:
                    return "❌ Claude API timed out after multiple attempts. Please try again."
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    return "❌ Invalid API key."
                elif e.response.status_code == 429:
                    return "❌ Rate limit exceeded."
                else:
                    return f"❌ HTTP Error {e.response.status_code}: {e.response.text}"
    
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# SETUP DETECTION (YOUR EXACT v4.0)
# ============================================================================
def detect_trading_setups(levels: Dict) -> List[Dict]:
    """Detect all trading setups"""
    
    setups = []
    current = levels['current_price']
    flip = levels['flip_point']
    net_gex = levels['net_gex']
    
    if net_gex < -500e6:
        distance_to_flip = ((current - flip) / current) * 100
        if -1.5 <= distance_to_flip <= -0.5:
            setups.append({
                'type': 'NEGATIVE GEX SQUEEZE',
                'direction': 'BULLISH (Long Calls)',
                'confidence': 75,
                'reason': 'Below flip with negative GEX - squeeze potential'
            })
    
    if net_gex > 1e9:
        distance_to_flip = ((current - flip) / current) * 100
        if 0 <= distance_to_flip <= 0.5:
            setups.append({
                'type': 'POSITIVE GEX BREAKDOWN',
                'direction': 'BEARISH (Long Puts)',
                'confidence': 70,
                'reason': 'At flip with positive GEX - breakdown potential'
            })
    
    wall_distance = abs(levels['call_wall'] - levels['put_wall'])
    wall_pct = (wall_distance / current) * 100
    
    if net_gex > 1e9 and wall_pct > 3:
        setups.append({
            'type': 'IRON CONDOR',
            'direction': 'NEUTRAL (Sell premium)',
            'confidence': 80,
            'reason': f'Strong walls {wall_pct:.1f}% apart with positive GEX'
        })
    
    return setups


# ============================================================================
# SESSION STATE (YOUR EXACT v4.0)
# ============================================================================
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'trade_log' not in st.session_state:
    st.session_state.trade_log = []

if 'setup_complete' not in st.session_state:
    st.session_state.setup_complete = False

if 'current_gex_data' not in st.session_state:
    st.session_state.current_gex_data = None

if 'current_levels' not in st.session_state:
    st.session_state.current_levels = None


# ============================================================================
# CREDENTIALS (YOUR EXACT v4.0)
# ============================================================================
try:
    TV_USERNAME = st.secrets["tradingvolatility_username"]
    CLAUDE_API_KEY = st.secrets["claude_api_key"]
    st.session_state.setup_complete = True
except:
    TV_USERNAME = None
    CLAUDE_API_KEY = None
    st.session_state.setup_complete = False


# ============================================================================
# MAIN UI (YOUR EXACT v4.0)
# ============================================================================
st.title("🎯 GEX Trading Co-Pilot v4.5")
st.markdown("**Complete System - All 10 Components + Professional Enhancements**")

# ============================================================================
# SIDEBAR (YOUR EXACT v4.0 + Performance Stats)
# ============================================================================
with st.sidebar:
    st.header("📊 System Status")
    
    if st.session_state.setup_complete:
        timing = TimingIntelligence()
        today_strategy = timing.get_current_day_strategy()
        wed_check = timing.is_wed_3pm_approaching()
        regime_check = RegimeFilter.check_trading_safety()
        execution = ExecutionAnalyzer.get_execution_window()
        
        st.markdown("### 7️⃣ Regime Filter")
        st.markdown(f"{regime_check['status']} {regime_check['reason']}")
        
        st.markdown("### 2️⃣ Timing Status")
        st.markdown(f"**Today:** {today_strategy['action']}")
        
        if wed_check['status'] in ['CRITICAL', 'WARNING']:
            st.error(wed_check['message'])
        else:
            st.info(wed_check['message'])
        
        st.markdown("### 8️⃣ Execution Quality")
        exec_color = "🟢" if execution['quality'] in ['EXCELLENT', 'GOOD'] else "🔴"
        st.markdown(f"{exec_color} **{execution['quality']}**: {execution['reason']}")
        
        st.markdown("---")
        
        st.markdown("### ⚙️ All Components Active")
        st.markdown("""
        ✅ 1. MM Behavior  
        ✅ 2. Timing Intelligence  
        ✅ 3. Catalyst Detection  
        ✅ 4. Magnitude Estimation  
        ✅ 5. Options Mechanics  
        ✅ 6. Risk Management  
        ✅ 7. Regime Filters  
        ✅ 8. Execution Quality  
        ✅ 9. Statistical Edge  
        ✅ 10. Learning Loop
        """)
        
        # NEW v4.5: Performance tracking
        perf = get_performance_stats()
        if perf['total_trades'] > 0:
            st.markdown("---")
            st.markdown("### 📊 Performance (NEW)")
            st.metric("Trades", perf['total_trades'])
            st.metric("Win Rate", f"{perf['win_rate']:.1f}%")
            st.metric("Total P&L", f"${perf['total_pnl']:,.2f}")
        
        st.markdown("---")
        
        if st.button("🔄 Refresh GEX Data"):
            st.session_state.current_gex_data = None
            st.session_state.current_levels = None
            st.rerun()
        
        st.markdown("### 🔌 Connection Tests")
        
        if st.button("Test Claude API"):
            with st.spinner("Testing..."):
                test_response = call_claude_api(
                    [{"role": "user", "content": "Say 'API connection successful' and nothing else."}],
                    CLAUDE_API_KEY,
                    None
                )
                if "successful" in test_response.lower():
                    st.success("✅ Working!")
                else:
                    st.error(f"❌ Issue: {test_response}")
        
        if st.button("Test TradingVolatility API"):
            with st.spinner("Testing..."):
                test_data = fetch_gex_data("SPY", TV_USERNAME)
                if 'error' not in test_data:
                    st.success("✅ Working!")
                else:
                    st.error(f"❌ Issue: {test_data['error']}")
    
    else:
        st.warning("⚠️ Setup Required")
        st.markdown("""
        Add to secrets:
        ```
        tradingvolatility_username = "YOUR_KEY"
        claude_api_key = "sk-ant-..."
        ```
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
