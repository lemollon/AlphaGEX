"""
GEX Trading Co-Pilot v5.0 - COMPLETE VERSION
Part 1 of 3: Core Engine + All 10 Components
Lines: 1-750
"""

import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Dict, Optional
import numpy as np
import time
import sqlite3
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Optional libraries
try:
    from py_vollib.black_scholes import black_scholes as bs
    from py_vollib.black_scholes.greeks import analytical as greeks
    VOLLIB_AVAILABLE = True
except ImportError:
    VOLLIB_AVAILABLE = False

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

# Page config
st.set_page_config(
    page_title="GEX Trading Co-Pilot v5.0",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database path
DB_PATH = Path("alphagex.db")

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_database():
    """Initialize SQLite database for trade tracking and history"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS gex_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT, current_price REAL, net_gex REAL,
            flip_point REAL, call_wall REAL, put_wall REAL,
            regime TEXT, data_json TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            exit_date DATETIME, symbol TEXT, setup_type TEXT,
            direction TEXT, strike REAL, expiration TEXT,
            entry_price REAL, exit_price REAL, contracts INTEGER,
            pnl REAL, pnl_pct REAL, status TEXT, notes TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT, alert_type TEXT, priority TEXT,
            message TEXT, is_read INTEGER DEFAULT 0)''')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        return False

# ============================================================================
# COMPONENT 1: MM BEHAVIOR ANALYZER
# ============================================================================

class MMBehaviorAnalyzer:
    """Analyze market maker positioning and forced hedging flows"""
    
    @staticmethod
    def analyze_dealer_positioning(gex_data: Dict) -> Dict:
        """Determine if dealers are long or short gamma"""
        net_gex = gex_data['total_net_gex']
        current_price = gex_data['current_price']
        flip_point = gex_data.get('flip_point')
        
        if net_gex > 1_000_000_000:
            position = "LONG_GAMMA"
            hedging = "Dealers must SELL on rallies, BUY on dips (volatility suppression)"
            regime = "CHOP_ZONE"
        elif net_gex < -500_000_000:
            position = "SHORT_GAMMA"
            hedging = "Dealers must BUY on rallies, SELL on dips (volatility amplification)"
            regime = "MOVE_MODE"
        else:
            position = "NEUTRAL"
            hedging = "Mixed positioning, no strong bias"
            regime = "TRANSITIONAL"
        
        if flip_point:
            if current_price > flip_point:
                zone = "ABOVE_FLIP"
                bias = "Positive gamma zone - resistance to upside"
            else:
                zone = "BELOW_FLIP"
                bias = "Negative gamma zone - momentum can accelerate"
        else:
            zone = "UNKNOWN"
            bias = "Cannot determine"
        
        return {
            'position': position,
            'hedging_flow': hedging,
            'regime': regime,
            'zone': zone,
            'bias': bias,
            'net_gex_b': net_gex / 1e9
        }

# ============================================================================
# COMPONENT 2: TIMING INTELLIGENCE
# ============================================================================

class TimingIntelligence:
    """Optimal entry/exit timing based on day of week and time decay"""
    
    @staticmethod
    def get_current_day_strategy() -> Dict:
        """Return strategy for current day of week"""
        day = datetime.now().strftime('%A')
        hour = datetime.now().hour
        
        strategies = {
            'Monday': {
                'action': 'DIRECTIONAL HUNTING',
                'best_setups': ['Long calls', 'Long puts'],
                'timing': 'Enter 9:30-10:30 AM',
                'win_rate': '66%',
                'notes': 'Best day for directional - highest win rate'
            },
            'Tuesday': {
                'action': 'CONTINUATION OR ADD',
                'best_setups': ['Hold Monday', 'Add to winners'],
                'timing': 'Review at open, add by 10 AM',
                'win_rate': '62%',
                'notes': 'Second best day, momentum continues'
            },
            'Wednesday': {
                'action': '🚨 EXIT BY 3PM 🚨',
                'best_setups': ['CLOSE ALL DIRECTIONAL'],
                'timing': 'Exit by 3:00 PM MANDATORY',
                'win_rate': 'N/A',
                'notes': 'Theta decay accelerates Thu/Fri - MUST EXIT'
            },
            'Thursday': {
                'action': 'IRON CONDORS ONLY',
                'best_setups': ['Premium selling', 'Range-bound plays'],
                'timing': 'Enter 9:30-11 AM',
                'win_rate': '58%',
                'notes': 'Directional has low win rate - sell premium instead'
            },
            'Friday': {
                'action': 'CHARM FLOW ONLY',
                'best_setups': ['0DTE iron condors', 'Scalps'],
                'timing': 'Close everything by noon',
                'win_rate': '12%',
                'notes': 'WORST day for directional - gamma decay extreme'
            }
        }
        
        return strategies.get(day, strategies['Monday'])
    
    @staticmethod
    def is_wed_3pm_approaching() -> Dict:
        """Check if Wednesday 3PM deadline is approaching"""
        now = datetime.now()
        day = now.strftime('%A')
        hour = now.hour
        
        if day == 'Wednesday':
            if hour >= 15:
                return {'status': 'CRITICAL', 'message': '🚨 PAST 3PM - EXIT NOW!'}
            elif hour >= 14:
                return {'status': 'WARNING', 'message': '⚠️ 1 hour until 3PM exit deadline'}
            else:
                return {'status': 'NORMAL', 'message': f'✅ Exit directional by 3PM ({15-hour} hours remaining)'}
        else:
            return {'status': 'NORMAL', 'message': f'Current day: {day}'}

# ============================================================================
# COMPONENT 3: CATALYST DETECTOR
# ============================================================================

class CatalystDetector:
    """Detect upcoming catalysts that affect volatility"""
    
    @staticmethod
    def check_upcoming_events() -> List[Dict]:
        """Check for FOMC, CPI, earnings, OPEX"""
        today = datetime.now()
        
        # Simplified - would integrate with actual calendar API
        events = []
        
        # Check if monthly OPEX (3rd Friday)
        if today.weekday() == 4:  # Friday
            if 15 <= today.day <= 21:
                events.append({
                    'type': 'OPEX',
                    'date': today.strftime('%Y-%m-%d'),
                    'impact': 'HIGH',
                    'note': 'Monthly expiration - high gamma concentration'
                })
        
        # Check for FOMC (typically every 6 weeks)
        fomc_months = [1, 3, 5, 7, 9, 11]  # Typical FOMC months
        if today.month in fomc_months and today.day >= 25:
            events.append({
                'type': 'FOMC',
                'date': 'This week',
                'impact': 'EXTREME',
                'note': 'Federal Reserve meeting - expect volatility'
            })
        
        return events

# ============================================================================
# COMPONENT 4: MAGNITUDE CALCULATOR
# ============================================================================

class MagnitudeCalculator:
    """Calculate expected move distances"""
    
    @staticmethod
    def calculate_expected_move(current_price: float, iv: float, dte: int) -> Dict:
        """Calculate 1 standard deviation expected move"""
        daily_move = current_price * iv * np.sqrt(dte / 365)
        
        return {
            'expected_move': daily_move,
            'upper_bound': current_price + daily_move,
            'lower_bound': current_price - daily_move,
            'move_pct': (daily_move / current_price) * 100
        }

# ============================================================================
# COMPONENT 5: OPTIONS MECHANICS
# ============================================================================

class OptionsMechanics:
    """Deep options knowledge - theta, vega, gamma"""
    
    @staticmethod
    def analyze_time_decay(dte: int, premium: float) -> Dict:
        """Analyze theta decay profile"""
        # Theta accelerates exponentially in last 30 days
        if dte <= 7:
            decay_rate = "EXTREME (>$0.10/day)"
            action = "AVOID long options"
        elif dte <= 21:
            decay_rate = "HIGH (accelerating)"
            action = "Monitor closely"
        elif dte <= 45:
            decay_rate = "MODERATE"
            action = "Normal management"
        else:
            decay_rate = "LOW (linear)"
            action = "Time on your side"
        
        estimated_daily_theta = premium * 0.03 * (45 / max(dte, 1))
        
        return {
            'dte': dte,
            'decay_rate': decay_rate,
            'action': action,
            'estimated_daily_theta': estimated_daily_theta
        }

# ============================================================================
# COMPONENT 6: RISK MANAGER
# ============================================================================

class RiskManager:
    """Position sizing and risk calculation"""
    
    @staticmethod
    def calculate_position_size(account_size: float, risk_pct: float, 
                                stop_distance_pct: float) -> Dict:
        """Calculate proper position size using Kelly criterion"""
        max_risk_dollars = account_size * (risk_pct / 100)
        
        # Kelly fraction (simplified)
        win_rate = 0.60  # Historical assumption
        avg_win = 1.0
        avg_loss = 0.5
        kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
        
        recommended_size = max_risk_dollars * kelly_fraction
        
        return {
            'max_risk': max_risk_dollars,
            'kelly_fraction': kelly_fraction,
            'recommended_size': recommended_size,
            'contracts': int(recommended_size / 100)  # Rough estimate
        }

# ============================================================================
# COMPONENT 7: REGIME FILTER
# ============================================================================

class RegimeFilter:
    """Determine if market conditions are safe for trading"""
    
    @staticmethod
    def check_trading_safety() -> Dict:
        """Check if it's safe to trade based on regime"""
        # Simplified - would check VIX, breadth, etc.
        
        now = datetime.now()
        hour = now.hour
        
        # Market hours check
        if hour < 9 or hour >= 16:
            return {
                'status': '🔴 CLOSED',
                'reason': 'Outside market hours',
                'safe_to_trade': False
            }
        
        # First 15 minutes
        if hour == 9 and now.minute < 45:
            return {
                'status': '⚠️ OPENING',
                'reason': 'Wait for opening volatility to settle',
                'safe_to_trade': False
            }
        
        # Last 30 minutes
        if hour == 15 and now.minute >= 30:
            return {
                'status': '⚠️ CLOSING',
                'reason': 'Avoid new entries near close',
                'safe_to_trade': False
            }
        
        return {
            'status': '✅ NORMAL',
            'reason': 'Normal trading conditions',
            'safe_to_trade': True
        }

# ============================================================================
# COMPONENT 8: EXECUTION ANALYZER
# ============================================================================

class ExecutionAnalyzer:
    """Optimize execution quality"""
    
    @staticmethod
    def get_execution_window() -> Dict:
        """Determine best time window for execution"""
        hour = datetime.now().hour
        
        if 9 <= hour < 10:
            return {'quality': 'POOR', 'reason': 'High spreads, volatility'}
        elif 10 <= hour < 15:
            return {'quality': 'GOOD', 'reason': 'Best liquidity, tight spreads'}
        elif 15 <= hour < 16:
            return {'quality': 'MODERATE', 'reason': 'Closing volatility'}
        else:
            return {'quality': 'CLOSED', 'reason': 'Market closed'}

# ============================================================================
# COMPONENT 9: STATISTICAL EDGE
# ============================================================================

class StatisticalEdge:
    """Calculate expected value and probability"""
    
    @staticmethod
    def calculate_ev(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Calculate expected value"""
        return (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    @staticmethod
    def probability_of_profit(distance_to_target: float, expected_move: float) -> float:
        """Estimate probability based on expected move"""
        if expected_move == 0:
            return 0.5
        
        z_score = distance_to_target / expected_move
        # Simplified normal distribution approximation
        prob = 0.5 + 0.5 * np.tanh(z_score)
        return max(0, min(prob, 1))

# ============================================================================
# COMPONENT 10: LEARNING LOOP
# ============================================================================

class LearningLoop:
    """Track performance and adjust strategy"""
    
    @staticmethod
    def analyze_performance(trades_df: pd.DataFrame) -> Dict:
        """Analyze historical performance to find what works"""
        if len(trades_df) == 0:
            return {'status': 'No trades yet'}
        
        # Win rate by day
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['day_of_week'] = trades_df['entry_date'].dt.day_name()
        
        performance_by_day = trades_df.groupby('day_of_week').agg({
            'pnl': ['count', 'mean', 'sum']
        }).to_dict()
        
        return {
            'total_trades': len(trades_df),
            'by_day': performance_by_day,
            'best_day': trades_df.groupby('day_of_week')['pnl'].mean().idxmax()
        }

# ============================================================================
# FRED ECONOMIC REGIME ANALYSIS
# ============================================================================

def get_actionable_economic_regime():
    """Fetch FRED data and return ACTIONABLE trading directives"""
    try:
        # Check if we have FRED API key
        fred_api_key = st.session_state.get('fred_key')
        
        if fred_api_key:
            # Use real FRED API
            from fredapi import Fred
            fred = Fred(api_key=fred_api_key)
            
            # Fetch real data
            try:
                import pandas as pd
                from datetime import datetime, timedelta
                
                # Get latest data points
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                # VIX
                try:
                    vix_data = fred.get_series('VIXCLS', start_date, end_date)
                    vix = float(vix_data.iloc[-1]) if len(vix_data) > 0 else 16.2
                except:
                    vix = 16.2
                
                # Fed Funds Rate
                try:
                    fed_data = fred.get_series('DFF', start_date, end_date)
                    fed_funds = float(fed_data.iloc[-1]) if len(fed_data) > 0 else 4.33
                except:
                    fed_funds = 4.33
                
                # 10-Year Treasury
                try:
                    treasury_data = fred.get_series('DGS10', start_date, end_date)
                    treasury_10y = float(treasury_data.iloc[-1]) if len(treasury_data) > 0 else 4.25
                except:
                    treasury_10y = 4.25
                
                # Unemployment Rate
                try:
                    unemployment_data = fred.get_series('UNRATE', start_date, end_date)
                    unemployment = float(unemployment_data.iloc[-1]) if len(unemployment_data) > 0 else 3.7
                except:
                    unemployment = 3.7
                
                fred_data = {
                    'vix': vix,
                    'fed_funds': fed_funds,
                    'treasury_10y': treasury_10y,
                    'unemployment': unemployment,
                    'source': 'FRED API'
                }
            except:
                # If FRED API fails, use simulated data
                fred_data = {
                    'vix': 16.2,
                    'fed_funds': 4.33,
                    'treasury_10y': 4.25,
                    'unemployment': 3.7,
                    'source': 'Simulated (FRED API error)'
                }
        else:
            # Simulate FRED data if no API key
            fred_data = {
                'vix': 16.2,
                'fed_funds': 4.33,
                'treasury_10y': 4.25,
                'unemployment': 3.7,
                'source': 'Simulated (No FRED API key)'
            }
        
        # Determine market bias
        if fred_data['vix'] < 15:
            bias = "BULLISH"
            position_mult = 1.2
            action = "BUY CALLS"
        elif fred_data['vix'] > 25:
            bias = "BEARISH"
            position_mult = 0.7
            action = "BUY PUTS"
        else:
            bias = "NEUTRAL"
            position_mult = 1.0
            action = "TRADE NORMALLY"
        
        # Risk level
        if fred_data['vix'] > 30:
            risk_level = "HIGH"
        elif fred_data['vix'] < 12:
            risk_level = "LOW"
        else:
            risk_level = "MODERATE"
        
        directives = []
        
        # VIX signals
        if fred_data['vix'] < 15:
            directives.append("🟢 VIX: {:.1f} (LOW) → SELL PREMIUM favored".format(fred_data['vix']))
        elif fred_data['vix'] > 25:
            directives.append("🔴 VIX: {:.1f} (HIGH) → BUY OPTIONS favored".format(fred_data['vix']))
        else:
            directives.append("🟡 VIX: {:.1f} (MODERATE) → Normal strategies".format(fred_data['vix']))
        
        # Fed rates
        if fred_data['fed_funds'] > 5:
            directives.append("🔴 Fed Funds: {:.2f}% (RESTRICTIVE) → Caution on rallies".format(fred_data['fed_funds']))
        else:
            directives.append("🟡 Fed Funds: {:.2f}% (MODERATE) → Normal environment".format(fred_data['fed_funds']))
        
        # Add data source
        directives.append(f"📊 Data source: {fred_data['source']}")
        
        return {
            'market_bias': bias,
            'risk_level': risk_level,
            'position_multiplier': position_mult,
            'action': action,
            'directives': directives,
            'data': fred_data
        }
    except Exception as e:
        return {
            'market_bias': 'UNKNOWN',
            'risk_level': 'HIGH',
            'position_multiplier': 0.5,
            'action': 'REDUCED SIZING',
            'directives': ['⚠️ Unable to fetch economic data: ' + str(e)],
            'data': {}
        }

# END OF PART 1 - Continue to Part 2
# ============================================================================
# MONTE CARLO SIMULATION ENGINE
# ============================================================================

class MonteCarloEngine:
    """Monte Carlo price simulation for probability analysis"""
    
    @staticmethod
    def simulate_price_path(current_price: float, volatility: float, 
                           days: int, simulations: int = 1000) -> Dict:
        """Run Monte Carlo simulation for price paths"""
        dt = 1/252
        drift = 0
        
        price_paths = np.zeros((simulations, days + 1))
        price_paths[:, 0] = current_price
        
        for t in range(1, days + 1):
            random_shock = np.random.normal(0, 1, simulations)
            price_paths[:, t] = price_paths[:, t-1] * np.exp(
                (drift - 0.5 * volatility**2) * dt + 
                volatility * np.sqrt(dt) * random_shock
            )
        
        final_prices = price_paths[:, -1]
        
        return {
            'price_paths': price_paths,
            'final_prices': final_prices,
            'mean_price': np.mean(final_prices),
            'median_price': np.median(final_prices),
            'std_dev': np.std(final_prices),
            'percentile_5': np.percentile(final_prices, 5),
            'percentile_95': np.percentile(final_prices, 95),
            'probability_above_current': np.sum(final_prices > current_price) / simulations
        }
    
    @staticmethod
    def probability_of_target(current_price: float, target_price: float,
                             volatility: float, days: int) -> float:
        """Calculate probability of reaching target price"""
        result = MonteCarloEngine.simulate_price_path(
            current_price, volatility, days, simulations=1000
        )
        
        if target_price > current_price:
            prob = np.sum(result['final_prices'] >= target_price) / len(result['final_prices'])
        else:
            prob = np.sum(result['final_prices'] <= target_price) / len(result['final_prices'])
        
        return prob * 100  # Return as percentage

# ============================================================================
# BLACK-SCHOLES PRICING ENGINE
# ============================================================================

class BlackScholesEngine:
    """Black-Scholes option pricing and Greeks"""
    
    @staticmethod
    def price_option_complete(spot: float, strike: float, time_to_expiry: float,
                             risk_free_rate: float = 0.045, volatility: float = 0.25,
                             option_type: str = 'call') -> Dict:
        """Calculate option price and all Greeks"""
        
        if VOLLIB_AVAILABLE:
            try:
                price = bs(option_type, spot, strike, time_to_expiry, 
                          risk_free_rate, volatility)
                delta = greeks.delta(option_type, spot, strike, time_to_expiry,
                                    risk_free_rate, volatility)
                gamma = greeks.gamma(option_type, spot, strike, time_to_expiry,
                                    risk_free_rate, volatility)
                theta = greeks.theta(option_type, spot, strike, time_to_expiry,
                                    risk_free_rate, volatility)
                vega = greeks.vega(option_type, spot, strike, time_to_expiry,
                                  risk_free_rate, volatility)
                
                return {
                    'price': price,
                    'delta': delta,
                    'gamma': gamma,
                    'theta': theta / 365,  # Daily
                    'vega': vega / 100,  # Per 1% IV
                    'method': 'py_vollib'
                }
            except:
                pass
        
        # Fallback simplified Black-Scholes
        d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / (volatility * np.sqrt(time_to_expiry))
        d2 = d1 - volatility * np.sqrt(time_to_expiry)
        
        from scipy.stats import norm
        
        if option_type == 'call':
            price = spot * norm.cdf(d1) - strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
            delta = norm.cdf(d1)
        else:
            price = strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
            delta = -norm.cdf(-d1)
        
        gamma = norm.pdf(d1) / (spot * volatility * np.sqrt(time_to_expiry))
        theta = -(spot * norm.pdf(d1) * volatility) / (2 * np.sqrt(time_to_expiry))
        vega = spot * norm.pdf(d1) * np.sqrt(time_to_expiry)
        
        return {
            'price': price,
            'delta': delta,
            'gamma': gamma,
            'theta': theta / 365,
            'vega': vega / 100,
            'method': 'simplified'
        }

# ============================================================================
# GEX DATA FETCHING
# ============================================================================

def fetch_gex_data(symbol: str = "SPY") -> Optional[Dict]:
    """Fetch GEX data from API"""
    try:
        url = f"https://api.gammaswap.com/api/v1/gex/{symbol}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def parse_gex_data(raw_data: Dict) -> Dict:
    """Parse and structure GEX data"""
    try:
        strikes = []
        call_gex = []
        put_gex = []
        net_gex = []
        
        for strike_data in raw_data.get('strikes', []):
            strikes.append(strike_data['strike'])
            call_gex.append(strike_data.get('call_gex', 0))
            put_gex.append(strike_data.get('put_gex', 0))
            net_gex.append(strike_data.get('call_gex', 0) + strike_data.get('put_gex', 0))
        
        # Find gamma flip
        cumsum = np.cumsum(net_gex)
        flip_idx = np.argmin(np.abs(cumsum))
        flip_point = strikes[flip_idx] if flip_idx < len(strikes) else None
        
        # Find walls
        call_wall_idx = np.argmax(call_gex)
        put_wall_idx = np.argmin(put_gex)
        
        return {
            'strikes': strikes,
            'call_gex': call_gex,
            'put_gex': put_gex,
            'net_gex': net_gex,
            'total_net_gex': sum(net_gex),
            'flip_point': flip_point,
            'call_wall': strikes[call_wall_idx] if call_wall_idx < len(strikes) else None,
            'put_wall': strikes[put_wall_idx] if put_wall_idx < len(strikes) else None,
            'current_price': raw_data.get('spot_price', 0),
            'timestamp': datetime.now()
        }
    except:
        return None

# ============================================================================
# ENHANCED STRIKE RECOMMENDATIONS WITH MONTE CARLO + BLACK-SCHOLES
# ============================================================================

def generate_enhanced_strike_recommendations(levels: Dict, symbol: str) -> Dict:
    """Generate strike recommendations with Monte Carlo probabilities and Greeks"""
    
    current = levels['current_price']
    flip = levels['flip_point']
    call_wall = levels['call_wall']
    put_wall = levels['put_wall']
    net_gex = levels['net_gex']
    
    recommendations = []
    
    # Determine primary direction
    if current < flip:
        primary_direction = "BULLISH (Below flip point)"
    elif current > flip and abs(current - flip) / current < 0.01:
        primary_direction = "NEUTRAL (Near flip point)"
    else:
        primary_direction = "BEARISH (Above flip point)"
    
    # Strike increment based on symbol
    increment = 5 if symbol == "SPY" else 10 if symbol == "QQQ" else 5
    
    # LONG CALL RECOMMENDATION
    if current < flip or net_gex < 0:
        atm_strike = round(current / increment) * increment
        otm_strike = atm_strike + increment
        dte = 5
        
        # Black-Scholes pricing
        bs_data = BlackScholesEngine.price_option_complete(
            current, otm_strike, dte/365, option_type='call'
        )
        
        # Monte Carlo simulation
        mc_result = MonteCarloEngine.simulate_price_path(
            current_price=current,
            volatility=0.25,
            days=dte,
            simulations=1000
        )
        
        # Probability of reaching call wall
        prob_target = MonteCarloEngine.probability_of_target(
            current_price=current,
            target_price=call_wall,
            volatility=0.25,
            days=dte
        )
        
        recommendations.append({
            'type': 'LONG CALL',
            'strikes': [otm_strike],
            'entry_zone': f"${current:.2f} - ${current + 1:.2f}",
            'target_1': call_wall,
            'target_2': call_wall + (increment * 2),
            'stop_loss': flip,
            'dte': f'{dte} DTE',
            'confidence': 75 if net_gex < -1e9 else 60,
            'expected_return': f"{((call_wall - current) / current * 100):.1f}%",
            'black_scholes': bs_data,
            'monte_carlo': mc_result,
            'probability_target': prob_target
        })
    
    # LONG PUT RECOMMENDATION
    if current > flip or (abs(current - flip) / current < 0.01 and net_gex > 2e9):
        atm_strike = round(current / increment) * increment
        otm_strike = atm_strike - increment
        dte = 5
        
        bs_data = BlackScholesEngine.price_option_complete(
            current, otm_strike, dte/365, option_type='put'
        )
        
        mc_result = MonteCarloEngine.simulate_price_path(
            current_price=current,
            volatility=0.25,
            days=dte,
            simulations=1000
        )
        
        prob_target = MonteCarloEngine.probability_of_target(
            current_price=current,
            target_price=flip,
            volatility=0.25,
            days=dte
        )
        
        recommendations.append({
            'type': 'LONG PUT',
            'strikes': [otm_strike],
            'entry_zone': f"${current:.2f} - ${current - 1:.2f}",
            'target_1': flip,
            'target_2': put_wall,
            'stop_loss': call_wall,
            'dte': f'{dte} DTE',
            'confidence': 70 if abs((current - flip) / current) < 0.01 else 55,
            'expected_return': f"{((current - put_wall) / current * 100):.1f}%",
            'black_scholes': bs_data,
            'monte_carlo': mc_result,
            'probability_target': prob_target
        })
    
    # IRON CONDOR RECOMMENDATION
    wall_distance = abs(call_wall - put_wall)
    wall_pct = (wall_distance / current) * 100
    
    if net_gex > 1e9 and wall_pct > 3:
        call_short = round(call_wall / increment) * increment
        call_long = call_short + increment
        put_short = round(put_wall / increment) * increment
        put_long = put_short - increment
        
        # Price the short strikes
        call_short_price = BlackScholesEngine.price_option_complete(
            current, call_short, 7/365, option_type='call'
        )
        put_short_price = BlackScholesEngine.price_option_complete(
            current, put_short, 7/365, option_type='put'
        )
        
        recommendations.append({
            'type': 'IRON CONDOR',
            'strikes': [put_long, put_short, call_short, call_long],
            'entry_zone': f"${current - 2:.2f} - ${current + 2:.2f}",
            'target_1': 'Collect 50% of premium',
            'target_2': 'Expiration',
            'stop_loss': 'Exit if price threatens strikes',
            'dte': '5-10 DTE',
            'confidence': 80,
            'expected_return': '20-30% on risk',
            'premium_estimate': call_short_price['price'] + put_short_price['price']
        })
    
    return {
        'primary_direction': primary_direction,
        'recommendations': recommendations,
        'current_regime': 'MOVE' if net_gex < 0 else 'CHOP'
    }

# ============================================================================
# ENHANCED WEEKLY PLAN WITH MONTE CARLO + FRED ADJUSTMENTS
# ============================================================================

def generate_enhanced_weekly_plan(levels: Dict, symbol: str, econ_regime: Dict) -> Dict:
    """Generate weekly plan with Monte Carlo and FRED position sizing"""
    
    current = levels['current_price']
    flip = levels['flip_point']
    call_wall = levels['call_wall']
    put_wall = levels['put_wall']
    net_gex = levels['net_gex']
    
    today = datetime.now()
    day_of_week = today.strftime('%A')
    
    plan = {
        'generated_at': today.strftime('%Y-%m-%d %H:%M'),
        'symbol': symbol,
        'current_price': current,
        'economic_regime': econ_regime,
        'days': {}
    }
    
    # Estimate daily volatility
    daily_volatility = 0.008 if abs(net_gex) > 1e9 else 0.005
    
    days_ahead = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    current_day_index = days_ahead.index(day_of_week) if day_of_week in days_ahead else 0
    
    for i, day in enumerate(days_ahead):
        days_from_now = max(1, (i - current_day_index) % 5)
        
        # Run Monte Carlo for this day
        mc_result = MonteCarloEngine.simulate_price_path(
            current_price=current,
            volatility=daily_volatility,
            days=days_from_now,
            simulations=1000
        )
        
        projected_price = mc_result['mean_price']
        confidence_low = mc_result['percentile_5']
        confidence_high = mc_result['percentile_95']
        
        # Adjust position size with FRED multiplier
        base_size = 0.03  # 3% base
        adjusted_size = base_size * econ_regime['position_multiplier']
        
        # Generate day-specific strategy
        if day == 'Monday':
            plan['days'][day] = {
                'strategy': 'DIRECTIONAL HUNTING',
                'action': 'Long Calls' if current < flip else 'Long Puts',
                'projected_price': f"${projected_price:.2f}",
                'confidence_range': f"${confidence_low:.2f} - ${confidence_high:.2f}",
                'monte_carlo_prob': f"{mc_result['probability_above_current']:.1f}%",
                'entry_zone': f"${current - 1:.2f} - ${current + 1:.2f}",
                'dte': '5 DTE',
                'target': f"${flip:.2f} then ${call_wall if current < flip else put_wall:.2f}",
                'stop': f"${flip - 2 if current < flip else flip + 2:.2f}",
                'position_size': f'{adjusted_size*100:.1f}% of capital',
                'position_breakdown': f'(Base: 3% × {econ_regime["position_multiplier"]:.2f} FRED multiplier)',
                'notes': 'Highest win rate day'
            }
        
        elif day == 'Tuesday':
            plan['days'][day] = {
                'strategy': 'CONTINUATION',
                'action': 'Hold Monday or add',
                'projected_price': f"${projected_price:.2f}",
                'confidence_range': f"${confidence_low:.2f} - ${confidence_high:.2f}",
                'monte_carlo_prob': f"{mc_result['probability_above_current']:.1f}%",
                'dte': '4 DTE',
                'target': f"${flip:.2f} then ${call_wall if current < flip else put_wall:.2f}",
                'position_size': f'{adjusted_size*100:.1f}% if new',
                'position_breakdown': f'(Base: 3% × {econ_regime["position_multiplier"]:.2f} FRED)',
                'notes': 'Still favorable'
            }
        
        elif day == 'Wednesday':
            plan['days'][day] = {
                'strategy': '🚨 EXIT DAY 🚨',
                'action': 'CLOSE ALL BY 3PM',
                'projected_price': f"${projected_price:.2f}",
                'entry_zone': 'NO NEW ENTRIES',
                'target': 'Exit at profit or small loss',
                'stop': '3:00 PM MANDATORY EXIT',
                'position_size': '0%',
                'notes': 'Theta will kill you Thu/Fri'
            }
        
        elif day == 'Thursday':
            wall_distance_pct = abs(call_wall - put_wall) / current * 100
            
            if wall_distance_pct > 3:
                ic_size = 0.05 * econ_regime['position_multiplier']
                plan['days'][day] = {
                    'strategy': 'IRON CONDOR',
                    'action': 'Sell premium',
                    'projected_price': f"${projected_price:.2f}",
                    'confidence_range': f"${confidence_low:.2f} - ${confidence_high:.2f}",
                    'dte': '1-2 DTE',
                    'target': '50% profit or Friday close',
                    'stop': f"Exit if breaks ${put_wall:.2f} or ${call_wall:.2f}",
                    'position_size': f'{ic_size*100:.1f}% of capital',
                    'position_breakdown': f'(Base: 5% × {econ_regime["position_multiplier"]:.2f} FRED)',
                    'notes': f'Walls at ${put_wall:.2f} and ${call_wall:.2f}'
                }
            else:
                plan['days'][day] = {
                    'strategy': 'SIT OUT',
                    'action': 'No favorable setups',
                    'projected_price': f"${projected_price:.2f}",
                    'notes': 'Walls too close'
                }
        
        elif day == 'Friday':
            plan['days'][day] = {
                'strategy': 'CHARM DECAY ONLY',
                'action': 'IC HOLD - NO DIRECTIONAL',
                'projected_price': f"${projected_price:.2f}",
                'entry_zone': 'NO NEW POSITIONS',
                'dte': '0 DTE',
                'target': 'Close ICs at open or by noon',
                'stop': 'Exit any position showing loss',
                'position_size': '0%',
                'notes': 'Worst day for directional'
            }
    
    return plan

# ============================================================================
# SETUP DETECTION LOGIC
# ============================================================================

def detect_setups(gex_data: Dict, fred_regime: Dict) -> List[Dict]:
    """Detect trading setups based on GEX structure"""
    setups = []
    
    try:
        current_price = gex_data['current_price']
        net_gex = gex_data['total_net_gex']
        flip_point = gex_data['flip_point']
        call_wall = gex_data['call_wall']
        put_wall = gex_data['put_wall']
        
        dist_to_flip = ((current_price - flip_point) / current_price * 100) if flip_point else 0
        dist_to_call = ((call_wall - current_price) / current_price * 100) if call_wall else 0
        dist_to_put = ((current_price - put_wall) / current_price * 100) if put_wall else 0
        
        # Negative GEX Squeeze
        if net_gex < -1_000_000_000 and dist_to_flip < -0.5:
            confidence = 75 if dist_to_put < 1.0 else 65
            setups.append({
                'type': 'NEGATIVE_GEX_SQUEEZE',
                'direction': 'LONG_CALLS',
                'confidence': confidence,
                'entry': 'ATM or first OTM call above flip',
                'target_strike': flip_point,
                'dte_range': '2-5 days',
                'size': '3% of capital',
                'stop_loss': '50% of premium',
                'profit_target': '100% gain',
                'rationale': f'Net GEX at {net_gex/1e9:.1f}B (negative), price {abs(dist_to_flip):.1f}% below flip'
            })
        
        # Positive GEX Breakdown
        if net_gex > 2_000_000_000 and abs(dist_to_flip) < 0.3:
            setups.append({
                'type': 'POSITIVE_GEX_BREAKDOWN',
                'direction': 'LONG_PUTS',
                'confidence': 70,
                'entry': 'ATM or first OTM put below flip',
                'target_strike': flip_point,
                'dte_range': '3-7 days',
                'size': '3% of capital',
                'stop_loss': 'Close above call wall',
                'profit_target': '100% gain',
                'rationale': f'Net GEX at {net_gex/1e9:.1f}B (positive), hovering near flip'
            })
        
        # Call Selling
        if net_gex > 3_000_000_000 and 0 < dist_to_call < 2.0:
            setups.append({
                'type': 'CALL_SELLING',
                'direction': 'SHORT_CALLS',
                'confidence': 65,
                'entry': f'Sell calls at {call_wall:.2f} strike',
                'target_strike': call_wall,
                'dte_range': '0-2 days',
                'size': '5% of capital max',
                'stop_loss': 'Price breaks above wall',
                'profit_target': '50% premium decay',
                'rationale': f'Strong call wall at {call_wall:.2f}'
            })
        
        # Iron Condor
        if call_wall and put_wall:
            wall_spread = ((call_wall - put_wall) / current_price * 100)
            if wall_spread > 3.0 and net_gex > 1_000_000_000:
                setups.append({
                    'type': 'IRON_CONDOR',
                    'direction': 'NEUTRAL',
                    'confidence': 55,
                    'entry': f'Short {put_wall:.2f}P / {call_wall:.2f}C',
                    'target_strike': None,
                    'dte_range': '5-10 days',
                    'size': '2% max portfolio loss',
                    'stop_loss': 'Threatened strike',
                    'profit_target': '25% premium',
                    'rationale': f'Wide walls ({wall_spread:.1f}% apart)'
                })
        
        # FRED adjustments
        if fred_regime['market_bias'] == 'BEARISH':
            for setup in setups:
                if 'LONG_CALLS' in setup['direction']:
                    setup['confidence'] -= 10
        
        setups.sort(key=lambda x: x['confidence'], reverse=True)
        return setups
    
    except:
        return []

# ============================================================================
# TRADE TRACKING FUNCTIONS (FIXED NaN HANDLING)
# ============================================================================

def save_trade(trade_data: Dict) -> bool:
    """Save trade to database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO trades 
                    (symbol, setup_type, direction, strike, expiration,
                     entry_price, contracts, status, notes)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (trade_data['symbol'], trade_data['setup_type'],
                   trade_data['direction'], trade_data['strike'],
                   trade_data['expiration'], trade_data['entry_price'],
                   trade_data['contracts'], 'OPEN', trade_data.get('notes', '')))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def get_open_trades() -> pd.DataFrame:
    """Retrieve all open trades"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_date DESC",
            conn
        )
        conn.close()
        return df
    except:
        return pd.DataFrame()

def close_trade(trade_id: int, exit_price: float) -> bool:
    """Close a trade and calculate P&L"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("SELECT entry_price, contracts, direction FROM trades WHERE id = ?", (trade_id,))
        trade = c.fetchone()
        
        if trade:
            entry_price, contracts, direction = trade
            
            if direction.upper() in ['LONG', 'CALL', 'PUT']:
                pnl = (exit_price - entry_price) * contracts * 100
            else:
                pnl = (entry_price - exit_price) * contracts * 100
            
            pnl_pct = ((exit_price / entry_price) - 1) * 100
            
            c.execute('''UPDATE trades 
                        SET exit_date = ?, exit_price = ?, pnl = ?, 
                            pnl_pct = ?, status = 'CLOSED'
                        WHERE id = ?''',
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                      exit_price, pnl, pnl_pct, trade_id))
            
            conn.commit()
            conn.close()
            return True
        
        conn.close()
        return False
    except:
        return False

def get_trade_stats() -> Dict:
    """Calculate trading statistics with NaN protection"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df_closed = pd.read_sql_query(
            "SELECT * FROM trades WHERE status = 'CLOSED'",
            conn
        )
        conn.close()
        
        if len(df_closed) == 0:
            return {'total_trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0}
        
        wins = df_closed[df_closed['pnl'] > 0]
        losses = df_closed[df_closed['pnl'] <= 0]
        
        # Ensure no NaN values - convert to float and check
        avg_win = float(wins['pnl'].mean()) if len(wins) > 0 else 0.0
        avg_loss = float(losses['pnl'].mean()) if len(losses) > 0 else 0.0
        total_pnl = float(df_closed['pnl'].sum())
        
        # Replace NaN with 0.0
        avg_win = 0.0 if pd.isna(avg_win) else avg_win
        avg_loss = 0.0 if pd.isna(avg_loss) else avg_loss
        total_pnl = 0.0 if pd.isna(total_pnl) else total_pnl
        
        return {
            'total_trades': int(len(df_closed)),
            'win_rate': float(len(wins) / len(df_closed) * 100),
            'total_pnl': total_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }
    except Exception as e:
        return {'total_trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0}

# ============================================================================
# ALERT SYSTEM
# ============================================================================

def create_alert(symbol: str, alert_type: str, priority: str, message: str):
    """Create alert in database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO alerts (symbol, alert_type, priority, message)
                     VALUES (?, ?, ?, ?)''',
                  (symbol, alert_type, priority, message))
        conn.commit()
        conn.close()
    except:
        pass

def get_unread_alerts() -> pd.DataFrame:
    """Get unread alerts"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT * FROM alerts WHERE is_read = 0 ORDER BY timestamp DESC LIMIT 10",
            conn
        )
        conn.close()
        return df
    except:
        return pd.DataFrame()

# END OF PART 2 - Continue to Part 3
# ============================================================================
# VISUALIZATION FUNCTIONS
# ============================================================================

def create_gex_profile_chart(gex_data: Dict) -> go.Figure:
    """Create interactive GEX profile visualization"""
    try:
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            subplot_titles=('Gamma Exposure Profile', 'Net GEX'),
            vertical_spacing=0.1
        )
        
        current_price = gex_data['current_price']
        strikes = gex_data['strikes']
        call_gex = gex_data['call_gex']
        put_gex = gex_data['put_gex']
        net_gex = gex_data['net_gex']
        
        # Call GEX bars
        fig.add_trace(go.Bar(x=strikes, y=call_gex, name='Call GEX',
                            marker_color='rgba(0, 255, 0, 0.6)'), row=1, col=1)
        
        # Put GEX bars
        fig.add_trace(go.Bar(x=strikes, y=put_gex, name='Put GEX',
                            marker_color='rgba(255, 0, 0, 0.6)'), row=1, col=1)
        
        # Current price line
        fig.add_vline(x=current_price, line_dash="dash", line_color="white",
                     annotation_text=f"Current: ${current_price:.2f}", row=1, col=1)
        
        # Gamma flip
        if gex_data.get('flip_point'):
            fig.add_vline(x=gex_data['flip_point'], line_dash="dot", line_color="yellow",
                         annotation_text=f"Flip: ${gex_data['flip_point']:.2f}", row=1, col=1)
        
        # Net GEX line
        fig.add_trace(go.Scatter(x=strikes, y=net_gex, name='Net GEX',
                                line=dict(color='cyan', width=2), fill='tozeroy'), row=2, col=1)
        
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
        
        fig.update_layout(height=700, showlegend=True, hovermode='x unified',
                         template='plotly_dark',
                         title_text=f"GEX Profile - Net: {gex_data['total_net_gex']/1e9:.2f}B")
        
        return fig
    except:
        return go.Figure()

def create_monte_carlo_chart(mc_results: Dict) -> go.Figure:
    """Create Monte Carlo visualization"""
    try:
        fig = go.Figure()
        
        sample_paths = mc_results['price_paths'][:100]
        days = range(sample_paths.shape[1])
        
        for path in sample_paths:
            fig.add_trace(go.Scatter(x=list(days), y=path, mode='lines',
                                    line=dict(width=0.5, color='rgba(100, 100, 255, 0.1)'),
                                    showlegend=False, hoverinfo='skip'))
        
        mean_path = np.mean(mc_results['price_paths'], axis=0)
        fig.add_trace(go.Scatter(x=list(days), y=mean_path, mode='lines',
                                name='Mean', line=dict(width=3, color='yellow')))
        
        fig.update_layout(title='Monte Carlo Simulation', template='plotly_dark', height=500)
        return fig
    except:
        return go.Figure()

def create_greeks_display(greeks_data: Dict) -> go.Figure:
    """Create Greeks indicators"""
    try:
        fig = make_subplots(rows=2, cols=2, subplot_titles=('Delta', 'Gamma', 'Theta', 'Vega'),
                           specs=[[{"type": "indicator"}, {"type": "indicator"}],
                                  [{"type": "indicator"}, {"type": "indicator"}]])
        
        fig.add_trace(go.Indicator(mode="number", value=greeks_data['delta'],
                                  title={'text': "Delta"}), row=1, col=1)
        fig.add_trace(go.Indicator(mode="number", value=greeks_data['gamma'],
                                  title={'text': "Gamma"}), row=1, col=2)
        fig.add_trace(go.Indicator(mode="number", value=greeks_data['theta'],
                                  title={'text': "Theta (daily)"}), row=2, col=1)
        fig.add_trace(go.Indicator(mode="number", value=greeks_data['vega'],
                                  title={'text': "Vega (per 1%)"}), row=2, col=2)
        
        fig.update_layout(template='plotly_dark', height=400)
        return fig
    except:
        return go.Figure()

# ============================================================================
# UI COMPONENTS (FIXED NaN HANDLING)
# ============================================================================

def render_sidebar():
    """Render sidebar with controls"""
    with st.sidebar:
        st.title("🎯 GEX Co-Pilot v5.0")
        st.markdown("---")
        
        # Changed from selectbox to text_input to allow any symbol
        symbol = st.text_input(
            "📊 Enter Stock Symbol",
            value=st.session_state.get('current_symbol', 'SPY'),
            help="Enter any stock symbol (e.g., SPY, QQQ, AAPL, TSLA, etc.)",
            placeholder="Enter symbol..."
        ).upper()  # Convert to uppercase
        
        # Validate symbol
        if symbol:
            if not symbol.isalpha() or len(symbol) > 5:
                st.warning("⚠️ Please enter a valid stock symbol")
            else:
                st.session_state['current_symbol'] = symbol
        
        # Popular symbols for quick access
        st.markdown("**Quick Select:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("SPY", use_container_width=True):
                st.session_state['current_symbol'] = 'SPY'
                st.rerun()
        with col2:
            if st.button("QQQ", use_container_width=True):
                st.session_state['current_symbol'] = 'QQQ'
                st.rerun()
        with col3:
            if st.button("IWM", use_container_width=True):
                st.session_state['current_symbol'] = 'IWM'
                st.rerun()
        
        col4, col5, col6 = st.columns(3)
        with col4:
            if st.button("TSLA", use_container_width=True):
                st.session_state['current_symbol'] = 'TSLA'
                st.rerun()
        with col5:
            if st.button("AAPL", use_container_width=True):
                st.session_state['current_symbol'] = 'AAPL'
                st.rerun()
        with col6:
            if st.button("NVDA", use_container_width=True):
                st.session_state['current_symbol'] = 'NVDA'
                st.rerun()
        
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
        
        st.markdown("---")
        
        # Position sizing
        st.subheader("💰 Position Sizing")
        account_size = st.number_input("Account Size ($)", min_value=1000, value=50000, step=1000)
        risk_pct = st.slider("Risk per Trade (%)", 1.0, 5.0, 2.0, 0.5)
        
        max_position = account_size * (risk_pct / 100)
        st.metric("Max Position Size", f"${max_position:,.0f}")
        
        st.markdown("---")
        
        # Performance stats with NaN protection
        st.subheader("📈 Performance")
        stats = get_trade_stats()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")
            st.metric("Total Trades", stats.get('total_trades', 0))
        with col2:
            # Handle NaN values
            avg_win = stats.get('avg_win', 0)
            avg_win = 0 if pd.isna(avg_win) else avg_win
            total_pnl = stats.get('total_pnl', 0)
            total_pnl = 0 if pd.isna(total_pnl) else total_pnl
            
            st.metric("Total P&L", f"${total_pnl:,.0f}")
            st.metric("Avg Win", f"${avg_win:,.0f}")
        
        # Economic regime
        st.markdown("---")
        st.subheader("🌐 Economic Regime")
        econ_regime = get_actionable_economic_regime()
        
        st.metric("Market Bias", econ_regime['market_bias'])
        st.metric("Risk Level", econ_regime['risk_level'])
        st.metric("Position Multiplier", f"{econ_regime['position_multiplier']:.2f}x")
        
        with st.expander("📋 Trading Directives"):
            for directive in econ_regime['directives']:
                st.write(f"- {directive}")
        
        return symbol, account_size, risk_pct, econ_regime

def render_gex_overview(gex_data: Dict):
    """Render main GEX overview"""
    st.header("📊 Gamma Exposure Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        net_gex_b = gex_data['total_net_gex'] / 1e9
        st.metric("Net GEX", f"{net_gex_b:.2f}B",
                 delta="Positive" if net_gex_b > 0 else "Negative")
    
    with col2:
        if gex_data['flip_point']:
            dist_to_flip = ((gex_data['current_price'] - gex_data['flip_point']) / 
                           gex_data['current_price'] * 100)
            st.metric("Gamma Flip", f"${gex_data['flip_point']:.2f}",
                     delta=f"{dist_to_flip:.2f}%")
    
    with col3:
        if gex_data['call_wall']:
            st.metric("Call Wall", f"${gex_data['call_wall']:.2f}")
    
    with col4:
        if gex_data['put_wall']:
            st.metric("Put Wall", f"${gex_data['put_wall']:.2f}")
    
    # MM Behavior Analysis
    mm_analysis = MMBehaviorAnalyzer.analyze_dealer_positioning(gex_data)
    
    st.info(f"**Dealer Position:** {mm_analysis['position']} | **Regime:** {mm_analysis['regime']}")
    st.write(f"💡 {mm_analysis['hedging_flow']}")
    
    # GEX Chart
    fig = create_gex_profile_chart(gex_data)
    st.plotly_chart(fig, use_container_width=True)

def render_setup_recommendations(setups: List[Dict], symbol: str):
    """Render setup recommendations"""
    st.header("🎯 Trading Setups")
    
    if not setups:
        st.warning("No high-confidence setups detected")
        return
    
    for i, setup in enumerate(setups[:3]):
        with st.expander(
            f"{'🔥' if setup['confidence'] > 70 else '⚠️'} "
            f"{setup['type']} - Confidence: {setup['confidence']}%",
            expanded=(i == 0)
        ):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**Direction:** {setup['direction']}")
                st.markdown(f"**Entry:** {setup['entry']}")
                st.markdown(f"**DTE Range:** {setup['dte_range']}")
                st.markdown(f"**Position Size:** {setup['size']}")
                st.markdown(f"**Stop Loss:** {setup['stop_loss']}")
                st.markdown(f"**Profit Target:** {setup['profit_target']}")
                st.info(f"💡 {setup['rationale']}")
            
            with col2:
                if st.button(f"📝 Log Trade #{i+1}", key=f"log_{i}"):
                    st.session_state[f'log_trade_{i}'] = True
                
                if st.session_state.get(f'log_trade_{i}'):
                    with st.form(key=f'trade_form_{i}'):
                        strike = st.number_input("Strike", value=setup.get('target_strike', 0))
                        expiration = st.date_input("Expiration")
                        entry_price = st.number_input("Entry Price", min_value=0.01, value=1.0)
                        contracts = st.number_input("Contracts", min_value=1, value=1)
                        notes = st.text_area("Notes")
                        
                        if st.form_submit_button("Save Trade"):
                            trade_data = {
                                'symbol': symbol,
                                'setup_type': setup['type'],
                                'direction': setup['direction'],
                                'strike': strike,
                                'expiration': expiration.strftime('%Y-%m-%d'),
                                'entry_price': entry_price,
                                'contracts': contracts,
                                'notes': notes
                            }
                            
                            if save_trade(trade_data):
                                st.success("✅ Trade logged!")
                                st.session_state[f'log_trade_{i}'] = False
                                time.sleep(1)
                                st.rerun()

def render_enhanced_strike_recs(levels: Dict, symbol: str):
    """Render enhanced strike recommendations with Monte Carlo"""
    st.header("🎯 Enhanced Strike Recommendations")
    
    recs = generate_enhanced_strike_recommendations(levels, symbol)
    
    st.info(f"**Primary Direction:** {recs['primary_direction']}")
    st.metric("Current Regime", recs['current_regime'])
    
    for rec in recs['recommendations']:
        with st.expander(f"{rec['type']} - Confidence: {rec['confidence']}%"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**Strikes:** {rec['strikes']}")
                st.markdown(f"**Entry Zone:** {rec['entry_zone']}")
                st.markdown(f"**Target 1:** ${rec['target_1']:.2f}")
                st.markdown(f"**Stop Loss:** ${rec['stop_loss']:.2f}")
                st.markdown(f"**DTE:** {rec['dte']}")
            
            with col2:
                # Black-Scholes Greeks
                if 'black_scholes' in rec:
                    bs = rec['black_scholes']
                    st.markdown("**Greeks:**")
                    st.write(f"Price: ${bs['price']:.2f}")
                    st.write(f"Delta: {bs['delta']:.3f}")
                    st.write(f"Gamma: {bs['gamma']:.4f}")
                    st.write(f"Theta: ${bs['theta']:.3f}/day")
            
            # Monte Carlo
            if 'monte_carlo' in rec:
                mc = rec['monte_carlo']
                st.markdown("**Monte Carlo Analysis:**")
                st.write(f"Expected Price: ${mc['mean_price']:.2f}")
                st.write(f"95% Range: ${mc['percentile_5']:.2f} - ${mc['percentile_95']:.2f}")
                st.write(f"Prob Above Current: {mc['probability_above_current']*100:.1f}%")
                
                if 'probability_target' in rec:
                    st.write(f"Prob Hit Target: {rec['probability_target']:.1f}%")

def render_enhanced_weekly_plan(levels: Dict, symbol: str, econ_regime: Dict):
    """Render enhanced weekly plan"""
    st.header("📆 Weekly Trading Plan")
    
    plan = generate_enhanced_weekly_plan(levels, symbol, econ_regime)
    
    st.info(f"Generated: {plan['generated_at']} | Current Price: ${plan['current_price']:.2f}")
    
    for day, details in plan['days'].items():
        with st.expander(f"**{day}** - {details['strategy']}", expanded=(day == datetime.now().strftime('%A'))):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**Action:** {details['action']}")
                st.markdown(f"**Projected Price:** {details.get('projected_price', 'N/A')}")
                
                if 'confidence_range' in details:
                    st.markdown(f"**95% Range:** {details['confidence_range']}")
                if 'monte_carlo_prob' in details:
                    st.markdown(f"**Prob Above Current:** {details['monte_carlo_prob']}")
            
            with col2:
                if 'entry_zone' in details:
                    st.markdown(f"**Entry:** {details['entry_zone']}")
                if 'target' in details:
                    st.markdown(f"**Target:** {details['target']}")
                if 'position_size' in details:
                    st.markdown(f"**Size:** {details['position_size']}")
                if 'position_breakdown' in details:
                    st.caption(details['position_breakdown'])
            
            if 'notes' in details:
                st.warning(f"📝 {details['notes']}")

def render_active_trades():
    """Render active trades"""
    st.header("📋 Active Positions")
    
    df_open = get_open_trades()
    
    if len(df_open) == 0:
        st.info("No active positions")
        return
    
    for idx, trade in df_open.iterrows():
        with st.expander(f"{trade['symbol']} - {trade['direction']} ${trade['strike']:.0f}"):
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.write(f"**Setup:** {trade['setup_type']}")
                st.write(f"**Expiration:** {trade['expiration']}")
                st.write(f"**Contracts:** {trade['contracts']}")
                st.write(f"**Entry:** ${trade['entry_price']:.2f}")
            
            with col2:
                exit_price = st.number_input("Exit Price", min_value=0.01,
                                            value=float(trade['entry_price']),
                                            key=f"exit_{trade['id']}")
            
            with col3:
                if st.button("Close", key=f"close_{trade['id']}"):
                    if close_trade(trade['id'], exit_price):
                        st.success("✅ Closed!")
                        time.sleep(1)
                        st.rerun()

def render_chat_interface(context_data: Dict = None):
    """Render chat interface"""
    st.markdown("---")
    st.subheader("💬 Ask Your Co-Pilot")
    
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    for message in st.session_state.chat_history[-5:]:  # Last 5 messages
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("Ask about GEX, setups, Greeks, or market conditions..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            # Context-aware response
            if context_data:
                response = f"Analyzing your question about {prompt}...\n\n"
                response += f"Current Context: {context_data.get('symbol', 'N/A')} at ${context_data.get('current_price', 0):.2f}\n"
                response += f"Net GEX: {context_data.get('net_gex', 0)/1e9:.2f}B\n\n"
                response += "This is a placeholder response. Integrate with Claude API for full functionality."
            else:
                response = f"I understand you're asking: '{prompt}'. This requires Claude API integration."
            
            st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application"""
    
    init_database()
    
    # Sidebar
    symbol, account_size, risk_pct, econ_regime = render_sidebar()
    st.session_state['current_symbol'] = symbol
    
    # Fetch GEX data
    with st.spinner(f"Fetching GEX data for {symbol}..."):
        raw_gex = fetch_gex_data(symbol)
        
        if raw_gex:
            gex_data = parse_gex_data(raw_gex)
            setups = detect_setups(gex_data, econ_regime)
            
            # Tabs
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 GEX Overview",
                "🎯 Setups",
                "🎲 Enhanced Recs",
                "📆 Weekly Plan",
                "📋 Positions"
            ])
            
            with tab1:
                render_gex_overview(gex_data)
                render_chat_interface({
                    'symbol': symbol,
                    'current_price': gex_data['current_price'],
                    'net_gex': gex_data['total_net_gex']
                })
            
            with tab2:
                render_setup_recommendations(setups, symbol)
                render_chat_interface({
                    'symbol': symbol,
                    'current_price': gex_data['current_price']
                })
            
            with tab3:
                render_enhanced_strike_recs(gex_data, symbol)
                render_chat_interface({
                    'symbol': symbol,
                    'current_price': gex_data['current_price']
                })
            
            with tab4:
                render_enhanced_weekly_plan(gex_data, symbol, econ_regime)
                render_chat_interface({
                    'symbol': symbol,
                    'current_price': gex_data['current_price']
                })
            
            with tab5:
                render_active_trades()
                # No chat in trade tracker tab
        
        else:
            st.error("❌ Unable to fetch GEX data")

# ============================================================================
# PART 4: API INTEGRATIONS & HELPER FUNCTIONS
# ============================================================================
# This part contains all the actual API integrations that make the UI work
# Add this after Part 3 to complete the system
# ============================================================================

import os
from typing import Optional

# ============================================================================
# TRADINGVOLATILITY.NET API INTEGRATION
# ============================================================================

class TradingVolatilityAPI:
    """Real integration with TradingVolatility.net API"""
    
    def __init__(self, username: str, api_key: str):
        self.username = username
        self.api_key = api_key
        self.base_url = "https://stocks.tradingvolatility.net/api"
        
    def get_gex_data(self, symbol: str) -> Optional[Dict]:
        """
        Fetch GEX data from TradingVolatility API
        
        Endpoint: /gex/{symbol}
        Returns: Complete gamma exposure data with strikes
        """
        try:
            url = f"{self.base_url}/gex/{symbol}"
            headers = {
                'X-API-Username': self.username,
                'X-API-Key': self.api_key
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_tradingvolatility_response(data)
            else:
                st.error(f"TradingVolatility API error: {response.status_code}")
                return None
                
        except Exception as e:
            st.error(f"Error fetching from TradingVolatility: {e}")
            return None
    
    def _parse_tradingvolatility_response(self, data: Dict) -> Dict:
        """Parse TradingVolatility.net response format"""
        try:
            # TradingVolatility returns nested structure
            symbol_key = list(data.keys())[0]  # First key is usually the symbol
            symbol_data = data[symbol_key]
            
            strikes = []
            call_gex = []
            put_gex = []
            net_gex_list = []
            
            # Parse strike-level data
            for strike_info in symbol_data.get('strikes', []):
                strike = strike_info.get('strike', 0)
                c_gex = strike_info.get('call_gamma_dollars', 0)
                p_gex = strike_info.get('put_gamma_dollars', 0)
                
                strikes.append(strike)
                call_gex.append(c_gex)
                put_gex.append(p_gex)
                net_gex_list.append(c_gex + p_gex)
            
            # Find gamma flip point
            cumsum = np.cumsum(net_gex_list)
            flip_idx = np.argmin(np.abs(cumsum))
            flip_point = strikes[flip_idx] if flip_idx < len(strikes) else None
            
            # Find walls
            call_wall_idx = np.argmax(call_gex) if call_gex else 0
            put_wall_idx = np.argmin(put_gex) if put_gex else 0
            
            return {
                'strikes': strikes,
                'call_gex': call_gex,
                'put_gex': put_gex,
                'net_gex': net_gex_list,
                'total_net_gex': sum(net_gex_list),
                'flip_point': flip_point,
                'call_wall': strikes[call_wall_idx] if strikes else None,
                'put_wall': strikes[put_wall_idx] if strikes else None,
                'current_price': symbol_data.get('spot_price', symbol_data.get('price', 0)),
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            st.error(f"Error parsing TradingVolatility data: {e}")
            return None
    
    def get_net_gex_summary(self, symbol: str) -> Optional[Dict]:
        """
        Get summary GEX metrics
        Endpoint: /netgamma/{symbol}
        """
        try:
            url = f"{self.base_url}/netgamma/{symbol}"
            headers = {
                'X-API-Username': self.username,
                'X-API-Key': self.api_key
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            st.error(f"Error fetching net GEX: {e}")
            return None

# ============================================================================
# CLAUDE API INTEGRATION
# ============================================================================

def call_claude_api(messages: List[Dict], api_key: str, context: Dict = None) -> str:
    """
    Call Claude API with GEX context for intelligent responses
    
    Args:
        messages: List of conversation messages
        api_key: Anthropic API key
        context: Current GEX data context
    
    Returns:
        Claude's response as string
    """
    try:
        import anthropic
        
        client = anthropic.Anthropic(api_key=api_key)
        
        # Build context-aware system prompt
        system_prompt = """You are an expert GEX (Gamma Exposure) trading co-pilot. 
You help traders make decisions based on options gamma exposure, dealer positioning, 
and market microstructure.

You have deep knowledge of:
- Gamma flip points and dealer hedging flows
- Call walls and put support levels
- Negative vs positive GEX regimes
- Options Greeks (delta, gamma, theta, vega)
- Risk management and position sizing
- Day-of-week trading patterns
- Market folklore and trading psychology

Always provide:
1. Clear, actionable advice
2. Risk considerations
3. Specific entry/exit criteria when relevant
4. Confidence levels for recommendations
"""
        
        # Add current context if available
        if context:
            context_msg = f"""
Current Market Context:
- Symbol: {context.get('symbol')}
- Price: ${context.get('current_price', 0):.2f}
- Net GEX: {context.get('net_gex', 0)/1e9:.2f}B
- Flip Point: ${context.get('flip_point', 0):.2f}
- Call Wall: ${context.get('call_wall', 0):.2f}
- Put Wall: ${context.get('put_wall', 0):.2f}
- Day: {context.get('day', 'Unknown')}
- Time: {context.get('time', 'Unknown')}

Use this context to provide specific, relevant advice.
"""
            messages = [{"role": "user", "content": context_msg}] + messages
        
        # Call Claude API
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=system_prompt,
            messages=messages
        )
        
        return response.content[0].text
        
    except Exception as e:
        return f"Error calling Claude API: {e}\n\nPlease check your API key in the sidebar."

# ============================================================================
# SMS/TWILIO ALERTS
# ============================================================================

def send_sms_alert(message: str, to_phone: str = None) -> bool:
    """
    Send SMS alert for high-confidence setups
    
    Args:
        message: Alert message to send
        to_phone: Phone number (format: +1234567890)
    
    Returns:
        True if sent successfully
    """
    if not TWILIO_AVAILABLE:
        st.warning("Twilio not installed. Install with: pip install twilio")
        return False
    
    try:
        # Get Twilio credentials from session state or environment
        account_sid = st.session_state.get('twilio_sid') or os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = st.session_state.get('twilio_token') or os.getenv('TWILIO_AUTH_TOKEN')
        from_phone = st.session_state.get('twilio_from') or os.getenv('TWILIO_FROM_PHONE')
        to_phone = to_phone or st.session_state.get('alert_phone') or os.getenv('ALERT_PHONE')
        
        if not all([account_sid, auth_token, from_phone, to_phone]):
            st.warning("⚠️ Configure Twilio credentials in sidebar for SMS alerts")
            return False
        
        client = Client(account_sid, auth_token)
        
        message = client.messages.create(
            body=message,
            from_=from_phone,
            to=to_phone
        )
        
        return message.sid is not None
        
    except Exception as e:
        st.error(f"SMS alert error: {e}")
        return False

# ============================================================================
# ENHANCED RISK CALCULATIONS
# ============================================================================

def calculate_risk_reward(entry_price: float, target_price: float, 
                          stop_price: float, contracts: int = 1) -> Dict:
    """Calculate risk/reward metrics for a trade"""
    
    risk_per_contract = abs(entry_price - stop_price) * 100
    reward_per_contract = abs(target_price - entry_price) * 100
    
    total_risk = risk_per_contract * contracts
    total_reward = reward_per_contract * contracts
    
    risk_reward_ratio = reward_per_contract / risk_per_contract if risk_per_contract > 0 else 0
    
    return {
        'risk_per_contract': risk_per_contract,
        'reward_per_contract': reward_per_contract,
        'total_risk': total_risk,
        'total_reward': total_reward,
        'risk_reward_ratio': risk_reward_ratio,
        'breakeven_win_rate': 1 / (1 + risk_reward_ratio) * 100 if risk_reward_ratio > 0 else 50
    }

def calculate_position_pnl(entry_price: float, current_price: float,
                          contracts: int, direction: str = 'LONG') -> Dict:
    """Calculate current P&L for an open position"""
    
    if direction.upper() in ['LONG', 'CALL', 'PUT']:
        pnl = (current_price - entry_price) * contracts * 100
    else:  # SHORT
        pnl = (entry_price - current_price) * contracts * 100
    
    pnl_pct = ((current_price / entry_price) - 1) * 100 if direction.upper() in ['LONG', 'CALL', 'PUT'] else ((entry_price / current_price) - 1) * 100
    
    return {
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'status': 'PROFIT' if pnl > 0 else 'LOSS' if pnl < 0 else 'BREAKEVEN'
    }

# ============================================================================
# PERFORMANCE ANALYTICS
# ============================================================================

def analyze_performance_by_setup(trades_df: pd.DataFrame) -> Dict:
    """Analyze performance by setup type"""
    if len(trades_df) == 0:
        return {}
    
    closed_trades = trades_df[trades_df['status'] == 'CLOSED'].copy()
    
    if len(closed_trades) == 0:
        return {}
    
    # Group by setup type
    setup_stats = {}
    
    for setup_type in closed_trades['setup_type'].unique():
        setup_trades = closed_trades[closed_trades['setup_type'] == setup_type]
        wins = setup_trades[setup_trades['pnl'] > 0]
        
        setup_stats[setup_type] = {
            'total_trades': len(setup_trades),
            'win_rate': len(wins) / len(setup_trades) * 100 if len(setup_trades) > 0 else 0,
            'avg_pnl': setup_trades['pnl'].mean(),
            'total_pnl': setup_trades['pnl'].sum(),
            'avg_win': wins['pnl'].mean() if len(wins) > 0 else 0,
            'best_trade': setup_trades['pnl'].max(),
            'worst_trade': setup_trades['pnl'].min()
        }
    
    return setup_stats

def analyze_performance_by_day(trades_df: pd.DataFrame) -> Dict:
    """Analyze performance by day of week"""
    if len(trades_df) == 0:
        return {}
    
    closed_trades = trades_df[trades_df['status'] == 'CLOSED'].copy()
    
    if len(closed_trades) == 0:
        return {}
    
    # Convert to datetime and extract day
    closed_trades['entry_date'] = pd.to_datetime(closed_trades['entry_date'])
    closed_trades['day_of_week'] = closed_trades['entry_date'].dt.day_name()
    
    # Group by day
    day_stats = {}
    
    for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
        day_trades = closed_trades[closed_trades['day_of_week'] == day]
        
        if len(day_trades) > 0:
            wins = day_trades[day_trades['pnl'] > 0]
            
            day_stats[day] = {
                'total_trades': len(day_trades),
                'win_rate': len(wins) / len(day_trades) * 100,
                'avg_pnl': day_trades['pnl'].mean(),
                'total_pnl': day_trades['pnl'].sum()
            }
    
    return day_stats

# ============================================================================
# TRADE JOURNAL EXPORT
# ============================================================================

def export_trade_journal() -> Optional[pd.DataFrame]:
    """Export complete trade journal as DataFrame"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT * FROM trades ORDER BY entry_date DESC",
            conn
        )
        conn.close()
        return df
    except:
        return None

def export_to_csv(df: pd.DataFrame, filename: str = "trade_journal.csv"):
    """Export trade journal to CSV"""
    try:
        df.to_csv(filename, index=False)
        return True
    except:
        return False

# ============================================================================
# CONFIGURATION MANAGER
# ============================================================================

def save_api_config(tradingvol_username: str, tradingvol_key: str,
                    claude_key: str, twilio_config: Dict = None):
    """Save API configuration to session state"""
    st.session_state['tradingvol_username'] = tradingvol_username
    st.session_state['tradingvol_key'] = tradingvol_key
    st.session_state['claude_key'] = claude_key
    
    if twilio_config:
        st.session_state['twilio_sid'] = twilio_config.get('sid')
        st.session_state['twilio_token'] = twilio_config.get('token')
        st.session_state['twilio_from'] = twilio_config.get('from_phone')
        st.session_state['alert_phone'] = twilio_config.get('to_phone')
    
    st.session_state['api_configured'] = True

def load_api_config() -> Dict:
    """Load API configuration from session state"""
    return {
        'tradingvol_username': st.session_state.get('tradingvol_username'),
        'tradingvol_key': st.session_state.get('tradingvol_key'),
        'claude_key': st.session_state.get('claude_key'),
        'api_configured': st.session_state.get('api_configured', False)
    }

# ============================================================================
# RENDER API CONFIGURATION UI
# ============================================================================

def render_api_configuration():
    """Render API configuration panel in sidebar - uses Streamlit secrets"""
    
    with st.sidebar.expander("⚙️ API Configuration", expanded=not st.session_state.get('api_configured', False)):
        
        # Debug button to check secrets
        if st.button("🔍 Debug: Check Secrets"):
            st.write("**Available secrets:**")
            if hasattr(st, 'secrets'):
                for key in st.secrets:
                    # Show key names but not values for security
                    st.write(f"- {key}: {'*' * 10}")
            else:
                st.write("No secrets object found")
            
            st.write("**Session state keys:**")
            st.write(f"- Username: {'SET' if st.session_state.get('tradingvol_username') else 'NOT SET'}")
            st.write(f"- API Key: {'SET' if st.session_state.get('tradingvol_key') else 'NOT SET'}")
            st.write(f"- Claude Key: {'SET' if st.session_state.get('claude_key') else 'NOT SET'}")
            st.write(f"- FRED Key: {'SET' if st.session_state.get('fred_key') else 'NOT SET'}")
        
        # Show status if loaded from secrets
        if st.session_state.get('secrets_loaded'):
            st.success("✅ API keys loaded from secrets")
            st.caption("Keys are hidden for security")
        
        st.markdown("### TradingVolatility.net")
        
        tradingvol_username = st.text_input(
            "Username",
            value=st.session_state.get('tradingvol_username', ''),
            help="Your TradingVolatility username",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        tradingvol_key = st.text_input(
            "API Key",
            value="*" * 20 if st.session_state.get('tradingvol_key') else '',
            type="password",
            help="Your TradingVolatility API key",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        st.markdown("---")
        st.markdown("### Claude AI")
            
        claude_key = st.text_input(
            "Claude API Key",
            value="*" * 20 if st.session_state.get('claude_key') else '',
            type="password",
            help="Your Anthropic Claude API key",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        st.markdown("---")
        st.markdown("### FRED Economic Data")
        
        fred_key = st.text_input(
            "FRED API Key",
            value="*" * 20 if st.session_state.get('fred_key') else '',
            type="password",
            help="Your FRED API key for economic data",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        st.markdown("---")
        st.markdown("### SMS Alerts (Optional)")
        
        twilio_sid = st.text_input(
            "Twilio Account SID",
            value="*" * 20 if st.session_state.get('twilio_sid') else '',
            type="password",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        twilio_token = st.text_input(
            "Twilio Auth Token",
            value="*" * 20 if st.session_state.get('twilio_token') else '',
            type="password",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        twilio_from = st.text_input(
            "From Phone",
            value=st.session_state.get('twilio_from', ''),
            help="Format: +1234567890",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        alert_phone = st.text_input(
            "Your Phone",
            value=st.session_state.get('alert_phone', ''),
            help="Where to send alerts",
            disabled=st.session_state.get('secrets_loaded', False)
        )
        
        # Manual override option
        if st.session_state.get('secrets_loaded'):
            st.info("📌 API keys loaded from secrets file")
        else:
            st.warning("⚠️ Could not load from secrets - enter manually")
            if st.button("💾 Save Configuration", use_container_width=True):
                # Allow manual entry even if secrets don't load
                if tradingvol_username and tradingvol_key:
                    st.session_state['tradingvol_username'] = tradingvol_username
                    st.session_state['tradingvol_key'] = tradingvol_key
                    st.session_state['claude_key'] = claude_key
                    st.session_state['fred_key'] = fred_key
                    st.session_state['api_configured'] = True
                    
                    if twilio_sid:
                        st.session_state['twilio_sid'] = twilio_sid
                        st.session_state['twilio_token'] = twilio_token
                        st.session_state['twilio_from'] = twilio_from
                        st.session_state['alert_phone'] = alert_phone
                    
                    st.success("✅ Configuration saved!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Please enter at least username and API key")

# ============================================================================
# ENHANCED FETCH FUNCTION WITH REAL API
# ============================================================================

def fetch_gex_data_enhanced(symbol: str) -> Optional[Dict]:
    """Enhanced fetch using real TradingVolatility API"""
    
    config = load_api_config()
    
    if not config['api_configured']:
        st.warning("⚠️ Configure TradingVolatility API in sidebar")
        return None
    
    try:
        # Initialize API client
        api = TradingVolatilityAPI(
            username=config['tradingvol_username'],
            api_key=config['tradingvol_key']
        )
        
        # Fetch GEX data
        gex_data = api.get_gex_data(symbol)
        
        if gex_data:
            # Save to history
            save_gex_history(symbol, gex_data)
            return gex_data
        
        return None
        
    except Exception as e:
        st.error(f"Error fetching GEX data: {e}")
        return None

def save_gex_history(symbol: str, gex_data: Dict):
    """Save GEX data to history table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''INSERT INTO gex_history 
                    (symbol, current_price, net_gex, flip_point, call_wall, put_wall, regime, data_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (symbol, gex_data['current_price'], gex_data['total_net_gex'],
                   gex_data['flip_point'], gex_data['call_wall'], gex_data['put_wall'],
                   'MOVE' if gex_data['total_net_gex'] < 0 else 'CHOP',
                   json.dumps(gex_data)))
        
        conn.commit()
        conn.close()
    except:
        pass

# ============================================================================
# COMPONENT STATUS DISPLAY
# ============================================================================

def render_component_status_panel():
    """Render all 10 components status"""
    with st.sidebar.expander("🔧 System Components"):
        
        # Check each component
        timing = TimingIntelligence()
        current_day = timing.get_current_day_strategy()
        wed_check = timing.is_wed_3pm_approaching()
        regime = RegimeFilter.check_trading_safety()
        execution = ExecutionAnalyzer.get_execution_window()
        
        components = [
            ("MM Behavior", "✅"),
            ("Timing", "✅" if wed_check['status'] != 'CRITICAL' else "⚠️"),
            ("Catalyst", "✅"),
            ("Magnitude", "✅"),
            ("Options", "✅"),
            ("Risk Mgmt", "✅"),
            ("Regime Filter", "✅" if regime['safe_to_trade'] else "🔴"),
            ("Execution", "✅" if execution['quality'] != 'CLOSED' else "🔴"),
            ("Statistical", "✅"),
            ("Learning", "✅")
        ]
        
        for name, status in components:
            st.write(f"{status} {name}")
        
        st.markdown("---")
        st.caption(f"Day Strategy: {current_day['action']}")
        st.caption(f"Execution: {execution['quality']}")

# ============================================================================
# UPDATE MAIN APP TO USE REAL APIs
# ============================================================================

def load_secrets_on_startup():
    """Load API keys from Streamlit secrets on app startup"""
    if 'secrets_loaded' not in st.session_state:
        try:
            # Debug: Show what secrets are available
            # st.write("Available secrets:", list(st.secrets.keys()))
            
            # Try multiple possible secret structures
            # Option 1: Nested structure
            if 'tradingvolatility' in st.secrets:
                st.session_state['tradingvol_username'] = st.secrets['tradingvolatility'].get('username', '')
                st.session_state['tradingvol_key'] = st.secrets['tradingvolatility'].get('api_key', '')
            # Option 2: Flat structure with underscore
            elif 'tradingvolatility_username' in st.secrets:
                st.session_state['tradingvol_username'] = st.secrets['tradingvolatility_username']
                st.session_state['tradingvol_key'] = st.secrets['tradingvolatility_api_key']
            # Option 3: Simple flat structure
            elif 'username' in st.secrets:
                st.session_state['tradingvol_username'] = st.secrets['username']
                st.session_state['tradingvol_key'] = st.secrets['api_key']
            
            # Load Claude API key - try multiple formats
            if 'claude' in st.secrets:
                st.session_state['claude_key'] = st.secrets['claude'].get('api_key', '')
            elif 'claude_api_key' in st.secrets:
                st.session_state['claude_key'] = st.secrets['claude_api_key']
            elif 'ANTHROPIC_API_KEY' in st.secrets:
                st.session_state['claude_key'] = st.secrets['ANTHROPIC_API_KEY']
            
            # Load FRED API key - try multiple formats
            if 'fred' in st.secrets:
                st.session_state['fred_key'] = st.secrets['fred'].get('api_key', '')
            elif 'fred_api_key' in st.secrets:
                st.session_state['fred_key'] = st.secrets['fred_api_key']
            elif 'FRED_API_KEY' in st.secrets:
                st.session_state['fred_key'] = st.secrets['FRED_API_KEY']
            
            # Load Twilio credentials (optional) - try multiple formats
            if 'twilio' in st.secrets:
                st.session_state['twilio_sid'] = st.secrets['twilio'].get('account_sid', '')
                st.session_state['twilio_token'] = st.secrets['twilio'].get('auth_token', '')
                st.session_state['twilio_from'] = st.secrets['twilio'].get('from_phone', '')
                st.session_state['alert_phone'] = st.secrets['twilio'].get('to_phone', '')
            elif 'twilio_account_sid' in st.secrets:
                st.session_state['twilio_sid'] = st.secrets.get('twilio_account_sid', '')
                st.session_state['twilio_token'] = st.secrets.get('twilio_auth_token', '')
                st.session_state['twilio_from'] = st.secrets.get('twilio_from_phone', '')
                st.session_state['alert_phone'] = st.secrets.get('twilio_to_phone', '')
            
            # Mark as configured if we have the essential keys
            if (st.session_state.get('tradingvol_username') and 
                st.session_state.get('tradingvol_key')):
                st.session_state['api_configured'] = True
                st.session_state['secrets_loaded'] = True
                return True
            else:
                # Debug: Show what was loaded
                # st.write("Username loaded:", st.session_state.get('tradingvol_username', 'NOT FOUND'))
                # st.write("API Key loaded:", 'EXISTS' if st.session_state.get('tradingvol_key') else 'NOT FOUND')
                # st.write("FRED Key loaded:", 'EXISTS' if st.session_state.get('fred_key') else 'NOT FOUND')
                return False
                
        except Exception as e:
            st.error(f"Error loading secrets: {e}")
            # Try to be more helpful
            st.info("Make sure your secrets.toml has the correct structure")
            return False
    return st.session_state.get('api_configured', False)

def main_enhanced():
    """Enhanced main application with real API integrations"""
    
    init_database()
    
    # Debug mode - uncomment to see what's happening with secrets
    # st.write("Debug: Available secrets keys:", list(st.secrets.keys()) if hasattr(st, 'secrets') else "No secrets found")
    
    # Load secrets immediately on startup
    secrets_loaded = load_secrets_on_startup()
    
    # If secrets didn't load, try one more simple approach
    if not secrets_loaded:
        # Direct assignment from Streamlit Cloud secrets manager format
        if hasattr(st, 'secrets'):
            # Get any format of the keys
            for key in st.secrets:
                if 'username' in key.lower():
                    st.session_state['tradingvol_username'] = st.secrets[key]
                elif 'api_key' in key.lower() and 'claude' not in key.lower():
                    st.session_state['tradingvol_key'] = st.secrets[key]
                elif 'claude' in key.lower() or 'anthropic' in key.lower():
                    st.session_state['claude_key'] = st.secrets[key]
            
            # Check again if we got the essentials
            if (st.session_state.get('tradingvol_username') and 
                st.session_state.get('tradingvol_key')):
                st.session_state['api_configured'] = True
                secrets_loaded = True
    
    # Render API configuration
    render_api_configuration()
    
    # Original sidebar + component status
    symbol, account_size, risk_pct, econ_regime = render_sidebar()
    render_component_status_panel()
    
    st.session_state['current_symbol'] = symbol
    
    # Check if APIs are configured
    config = load_api_config()
    
    if not config['api_configured'] and not secrets_loaded:
        st.warning("⚠️ Please configure your API keys in the sidebar to get started")
        st.info("Or add them to your `.streamlit/secrets.toml` file")
        st.stop()
    
    # Fetch GEX data using REAL API
    with st.spinner(f"Fetching GEX data for {symbol} from TradingVolatility.net..."):
        gex_data = fetch_gex_data_enhanced(symbol)
        
        if gex_data:
            setups = detect_setups(gex_data, econ_regime)
            
            # Check for high-confidence setups and send alerts
            for setup in setups:
                if setup['confidence'] >= 75 and st.session_state.get('alert_phone'):
                    alert_msg = f"🚨 High-confidence {setup['type']} detected for {symbol}! Confidence: {setup['confidence']}%"
                    send_sms_alert(alert_msg)
            
            # Original tabs (from Part 3)
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 GEX Overview",
                "🎯 Setups",
                "🎲 Enhanced Recs",
                "📆 Weekly Plan",
                "📋 Positions"
            ])
            
            with tab1:
                render_gex_overview(gex_data)
                render_chat_interface({
                    'symbol': symbol,
                    'current_price': gex_data['current_price'],
                    'net_gex': gex_data['total_net_gex'],
                    'flip_point': gex_data.get('flip_point'),
                    'call_wall': gex_data.get('call_wall'),
                    'put_wall': gex_data.get('put_wall')
                })
            
            with tab2:
                render_setup_recommendations(setups, symbol)
                render_chat_interface({'symbol': symbol})
            
            with tab3:
                render_enhanced_strike_recs(gex_data, symbol)
                render_chat_interface({'symbol': symbol})
            
            with tab4:
                render_enhanced_weekly_plan(gex_data, symbol, econ_regime)
                render_chat_interface({'symbol': symbol})
            
            with tab5:
                render_active_trades()
                
                # Performance analytics
                st.markdown("---")
                st.subheader("📊 Performance Analytics")
                
                all_trades = export_trade_journal()
                
                if all_trades is not None and len(all_trades) > 0:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**By Setup Type**")
                        setup_stats = analyze_performance_by_setup(all_trades)
                        for setup, stats in setup_stats.items():
                            st.write(f"{setup}: {stats['win_rate']:.1f}% WR, ${stats['total_pnl']:,.0f} P&L")
                    
                    with col2:
                        st.markdown("**By Day of Week**")
                        day_stats = analyze_performance_by_day(all_trades)
                        for day, stats in day_stats.items():
                            st.write(f"{day}: {stats['win_rate']:.1f}% WR, ${stats['total_pnl']:,.0f} P&L")
                    
                    if st.button("📥 Export Trade Journal"):
                        if export_to_csv(all_trades):
                            st.success("✅ Exported to trade_journal.csv")
        else:
            st.error("❌ Unable to fetch GEX data. Check your API configuration.")

# ============================================================================
# RUN APPLICATION - FIXED: Only one execution block
# ============================================================================

if __name__ == "__main__":
    # Use the enhanced version with API integrations
    main_enhanced()
    
    st.markdown("---")
    st.caption("GEX Trading Co-Pilot v5.0 COMPLETE | All 10 Components + Real API Integration | © 2025")

# ============================================================================
# END OF COMPLETE SYSTEM
# Total Lines: ~2300
# ============================================================================

"""
STREAMLIT SECRETS CONFIGURATION
================================

Create a file called .streamlit/secrets.toml in your project directory with:

[tradingvolatility]
username = "your_tradingvolatility_username"
api_key = "your_tradingvolatility_api_key"

[claude]
api_key = "your_anthropic_api_key"

[fred]
api_key = "your_fred_api_key"

[twilio]  # Optional
account_sid = "your_twilio_account_sid"
auth_token = "your_twilio_auth_token"
from_phone = "+1234567890"
to_phone = "+0987654321"

OR use flat structure:

username = "your_tradingvolatility_username"
api_key = "your_tradingvolatility_api_key"
claude_api_key = "your_anthropic_api_key"
fred_api_key = "your_fred_api_key"

The app will automatically load these on startup!
"""
