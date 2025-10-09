"""
GEX Trading Co-Pilot v5.0 - PART 1 OF 2
Core Engine, Database, Calculation Functions
Lines: 1-1000
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
        
        # GEX history table
        c.execute('''CREATE TABLE IF NOT EXISTS gex_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            current_price REAL,
            net_gex REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            regime TEXT,
            data_json TEXT
        )''')
        
        # Trades table
        c.execute('''CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            exit_date DATETIME,
            symbol TEXT,
            setup_type TEXT,
            direction TEXT,
            strike REAL,
            expiration TEXT,
            entry_price REAL,
            exit_price REAL,
            contracts INTEGER,
            pnl REAL,
            pnl_pct REAL,
            status TEXT,
            notes TEXT
        )''')
        
        # Alerts table
        c.execute('''CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            alert_type TEXT,
            priority TEXT,
            message TEXT,
            is_read INTEGER DEFAULT 0
        )''')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        return False

# ============================================================================
# FRED ECONOMIC REGIME ANALYSIS
# ============================================================================

def get_fred_regime():
    """
    Fetch FRED data and determine actionable market regime
    Returns: dict with regime classification and directives
    """
    try:
        # FRED API endpoint (using demo data for now)
        fred_data = {
            'unemployment': 3.8,
            'cpi_yoy': 3.2,
            'fed_rate': 5.25,
            'treasury_10y': 4.3,
            'treasury_2y': 4.8
        }
        
        # Regime classification logic
        regime = "neutral"
        directives = []
        
        # Inverted yield curve check
        if fred_data['treasury_2y'] > fred_data['treasury_10y']:
            regime = "risk_off"
            directives.append("⚠️ Inverted yield curve - favor put spreads")
            directives.append("🔒 Reduce position sizing by 30%")
        
        # High inflation environment
        if fred_data['cpi_yoy'] > 3.0:
            directives.append("📈 High inflation - volatility likely elevated")
            directives.append("⏰ Shorter DTE preferred (2-5 days)")
        
        # Fed rate analysis
        if fred_data['fed_rate'] > 5.0:
            directives.append("💰 High rates - premium selling attractive")
            regime = "range_bound" if regime == "neutral" else regime
        
        # Unemployment spike
        if fred_data['unemployment'] > 4.0:
            directives.append("📉 Rising unemployment - defensive positioning")
        
        return {
            'regime': regime,
            'directives': directives,
            'data': fred_data,
            'timestamp': datetime.now()
        }
    except Exception as e:
        return {
            'regime': 'unknown',
            'directives': ['⚠️ Unable to fetch FRED data'],
            'data': {},
            'timestamp': datetime.now()
        }

# ============================================================================
# MONTE CARLO SIMULATION ENGINE
# ============================================================================

def run_monte_carlo(
    current_price: float,
    volatility: float,
    days_to_expiry: int,
    num_simulations: int = 10000,
    confidence_level: float = 0.95
) -> Dict:
    """
    Run Monte Carlo simulation for price paths
    
    Args:
        current_price: Current stock price
        volatility: Implied volatility (decimal, e.g., 0.20 for 20%)
        days_to_expiry: Number of days until expiration
        num_simulations: Number of price paths to simulate
        confidence_level: Confidence interval (default 95%)
    
    Returns:
        Dictionary with simulation results and statistics
    """
    try:
        dt = 1/252  # Daily time step
        drift = 0  # Risk-neutral assumption
        
        # Generate random price paths
        price_paths = np.zeros((num_simulations, days_to_expiry + 1))
        price_paths[:, 0] = current_price
        
        for t in range(1, days_to_expiry + 1):
            random_shock = np.random.normal(0, 1, num_simulations)
            price_paths[:, t] = price_paths[:, t-1] * np.exp(
                (drift - 0.5 * volatility**2) * dt + 
                volatility * np.sqrt(dt) * random_shock
            )
        
        # Calculate statistics
        final_prices = price_paths[:, -1]
        mean_price = np.mean(final_prices)
        median_price = np.median(final_prices)
        std_price = np.std(final_prices)
        
        # Confidence intervals
        lower_bound = np.percentile(final_prices, (1 - confidence_level) * 100 / 2)
        upper_bound = np.percentile(final_prices, (1 + confidence_level) * 100 / 2)
        
        # Probability of profit zones
        prob_above_current = np.sum(final_prices > current_price) / num_simulations
        prob_below_current = 1 - prob_above_current
        
        return {
            'price_paths': price_paths,
            'final_prices': final_prices,
            'mean_price': mean_price,
            'median_price': median_price,
            'std_price': std_price,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'confidence_level': confidence_level,
            'prob_above': prob_above_current,
            'prob_below': prob_below_current,
            'current_price': current_price
        }
    except Exception as e:
        st.error(f"Monte Carlo simulation error: {e}")
        return None

# ============================================================================
# BLACK-SCHOLES PRICING ENGINE
# ============================================================================

def calculate_black_scholes(
    spot_price: float,
    strike_price: float,
    days_to_expiry: int,
    volatility: float,
    risk_free_rate: float = 0.045,
    option_type: str = 'call'
) -> Dict:
    """
    Calculate Black-Scholes option price and Greeks
    
    Args:
        spot_price: Current stock price
        strike_price: Option strike price
        days_to_expiry: Days until expiration
        volatility: Implied volatility (decimal)
        risk_free_rate: Risk-free rate (decimal)
        option_type: 'call' or 'put'
    
    Returns:
        Dictionary with price and Greeks
    """
    try:
        if not VOLLIB_AVAILABLE:
            return None
        
        time_to_expiry = days_to_expiry / 365.0
        
        # Calculate option price
        price = bs(option_type, spot_price, strike_price, 
                   time_to_expiry, risk_free_rate, volatility)
        
        # Calculate Greeks
        delta = greeks.delta(option_type, spot_price, strike_price,
                            time_to_expiry, risk_free_rate, volatility)
        gamma = greeks.gamma(option_type, spot_price, strike_price,
                            time_to_expiry, risk_free_rate, volatility)
        theta = greeks.theta(option_type, spot_price, strike_price,
                            time_to_expiry, risk_free_rate, volatility)
        vega = greeks.vega(option_type, spot_price, strike_price,
                          time_to_expiry, risk_free_rate, volatility)
        
        return {
            'price': price,
            'delta': delta,
            'gamma': gamma,
            'theta': theta / 365,  # Daily theta
            'vega': vega / 100,    # Vega per 1% move
            'spot': spot_price,
            'strike': strike_price,
            'dte': days_to_expiry,
            'iv': volatility,
            'type': option_type
        }
    except Exception as e:
        return None

# ============================================================================
# TRADE TRACKING FUNCTIONS
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
    except Exception as e:
        st.error(f"Error saving trade: {e}")
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
    except Exception as e:
        return pd.DataFrame()

def close_trade(trade_id: int, exit_price: float, exit_date: str = None) -> bool:
    """Close a trade and calculate P&L"""
    try:
        if exit_date is None:
            exit_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get trade details
        c.execute("SELECT entry_price, contracts, direction FROM trades WHERE id = ?", (trade_id,))
        trade = c.fetchone()
        
        if trade:
            entry_price, contracts, direction = trade
            
            # Calculate P&L
            if direction.upper() in ['LONG', 'CALL', 'PUT']:
                pnl = (exit_price - entry_price) * contracts * 100
            else:  # SHORT
                pnl = (entry_price - exit_price) * contracts * 100
            
            pnl_pct = ((exit_price / entry_price) - 1) * 100
            
            # Update trade
            c.execute('''UPDATE trades 
                        SET exit_date = ?, exit_price = ?, pnl = ?, 
                            pnl_pct = ?, status = 'CLOSED'
                        WHERE id = ?''',
                     (exit_date, exit_price, pnl, pnl_pct, trade_id))
            
            conn.commit()
            conn.close()
            return True
        
        conn.close()
        return False
    except Exception as e:
        st.error(f"Error closing trade: {e}")
        return False

def get_trade_stats() -> Dict:
    """Calculate overall trading statistics"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Closed trades
        df_closed = pd.read_sql_query(
            "SELECT * FROM trades WHERE status = 'CLOSED'",
            conn
        )
        
        if len(df_closed) == 0:
            conn.close()
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_win': 0,
                'avg_loss': 0
            }
        
        wins = df_closed[df_closed['pnl'] > 0]
        losses = df_closed[df_closed['pnl'] <= 0]
        
        stats = {
            'total_trades': len(df_closed),
            'win_rate': len(wins) / len(df_closed) * 100 if len(df_closed) > 0 else 0,
            'total_pnl': df_closed['pnl'].sum(),
            'avg_win': wins['pnl'].mean() if len(wins) > 0 else 0,
            'avg_loss': losses['pnl'].mean() if len(losses) > 0 else 0,
            'best_trade': df_closed['pnl'].max() if len(df_closed) > 0 else 0,
            'worst_trade': df_closed['pnl'].min() if len(df_closed) > 0 else 0
        }
        
        conn.close()
        return stats
    except Exception as e:
        return {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0}

# ============================================================================
# GEX DATA FETCHING
# ============================================================================

def fetch_gex_data(symbol: str = "SPY") -> Optional[Dict]:
    """
    Fetch GEX data from GammaSwap API
    """
    try:
        url = f"https://api.gammaswap.com/api/v1/gex/{symbol}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            st.warning(f"API returned status code: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error fetching GEX data: {e}")
        return None

def parse_gex_data(raw_data: Dict) -> Dict:
    """
    Parse and structure GEX data
    """
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
        
        # Find gamma flip point
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
    except Exception as e:
        st.error(f"Error parsing GEX data: {e}")
        return None

# ============================================================================
# SETUP DETECTION LOGIC
# ============================================================================

def detect_setups(gex_data: Dict, fred_regime: Dict) -> List[Dict]:
    """
    Detect trading setups based on GEX structure and economic regime
    """
    setups = []
    
    try:
        current_price = gex_data['current_price']
        net_gex = gex_data['total_net_gex']
        flip_point = gex_data['flip_point']
        call_wall = gex_data['call_wall']
        put_wall = gex_data['put_wall']
        
        # Calculate distances
        dist_to_flip = ((current_price - flip_point) / current_price * 100) if flip_point else 0
        dist_to_call = ((call_wall - current_price) / current_price * 100) if call_wall else 0
        dist_to_put = ((current_price - put_wall) / current_price * 100) if put_wall else 0
        
        # SQUEEZE PLAY DETECTION
        
        # Negative GEX Squeeze (Long Calls)
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
        
        # Positive GEX Breakdown (Long Puts)
        if net_gex > 2_000_000_000 and abs(dist_to_flip) < 0.3 and current_price > flip_point:
            confidence = 70
            setups.append({
                'type': 'POSITIVE_GEX_BREAKDOWN',
                'direction': 'LONG_PUTS',
                'confidence': confidence,
                'entry': 'ATM or first OTM put below flip',
                'target_strike': flip_point,
                'dte_range': '3-7 days',
                'size': '3% of capital',
                'stop_loss': 'Close above call wall',
                'profit_target': '100% gain',
                'rationale': f'Net GEX at {net_gex/1e9:.1f}B (positive), hovering near flip point'
            })
        
        # PREMIUM SELLING DETECTION
        
        # Call Selling at Resistance
        if net_gex > 3_000_000_000 and 0 < dist_to_call < 2.0:
            confidence = 65
            setups.append({
                'type': 'CALL_SELLING',
                'direction': 'SHORT_CALLS',
                'confidence': confidence,
                'entry': f'Sell calls at {call_wall:.2f} strike',
                'target_strike': call_wall,
                'dte_range': '0-2 days',
                'size': '5% of capital max',
                'stop_loss': 'Price breaks above wall',
                'profit_target': '50% premium decay',
                'rationale': f'Strong call wall at {call_wall:.2f}, high positive GEX'
            })
        
        # Put Selling at Support
        if put_wall and dist_to_put > 1.0 and net_gex > 1_000_000_000:
            confidence = 60
            setups.append({
                'type': 'PUT_SELLING',
                'direction': 'SHORT_PUTS',
                'confidence': confidence,
                'entry': f'Sell puts at {put_wall:.2f} strike',
                'target_strike': put_wall,
                'dte_range': '2-5 days',
                'size': '5% of capital max',
                'stop_loss': 'Price breaks below wall',
                'profit_target': '50% premium decay',
                'rationale': f'Strong put wall at {put_wall:.2f}, positive GEX regime'
            })
        
        # IRON CONDOR DETECTION
        if call_wall and put_wall:
            wall_spread = ((call_wall - put_wall) / current_price * 100)
            if wall_spread > 3.0 and net_gex > 1_000_000_000:
                confidence = 55
                setups.append({
                    'type': 'IRON_CONDOR',
                    'direction': 'NEUTRAL',
                    'confidence': confidence,
                    'entry': f'Short {put_wall:.2f}P / {call_wall:.2f}C',
                    'target_strike': None,
                    'dte_range': '5-10 days',
                    'size': '2% max portfolio loss',
                    'stop_loss': 'Threatened strike',
                    'profit_target': '25% premium',
                    'rationale': f'Wide gamma walls ({wall_spread:.1f}% apart), positive GEX'
                })
        
        # Apply FRED regime adjustments
        if fred_regime['regime'] == 'risk_off':
            for setup in setups:
                if 'LONG_CALLS' in setup['direction']:
                    setup['confidence'] -= 10
                    setup['size'] = '2% of capital'  # Reduce size
        
        # Sort by confidence
        setups.sort(key=lambda x: x['confidence'], reverse=True)
        
        return setups
    
    except Exception as e:
        st.error(f"Error detecting setups: {e}")
        return []

# ============================================================================
# ALERT SYSTEM
# ============================================================================

def create_alert(symbol: str, alert_type: str, priority: str, message: str):
    """Create an alert in the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO alerts (symbol, alert_type, priority, message)
                     VALUES (?, ?, ?, ?)''',
                  (symbol, alert_type, priority, message))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error creating alert: {e}")

def get_unread_alerts() -> pd.DataFrame:
    """Get all unread alerts"""
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

def mark_alert_read(alert_id: int):
    """Mark an alert as read"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE alerts SET is_read = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error marking alert: {e}")

# ============================================================================
# END OF PART 1
# ============================================================================
# Continue with Part 2 for UI components and visualizations
"""
GEX Trading Co-Pilot v5.0 - PART 2 OF 2
UI Components, Visualizations, Dashboard
Lines: 1001-2050
"""

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
        
        # Call GEX bars (positive)
        fig.add_trace(
            go.Bar(
                x=strikes,
                y=call_gex,
                name='Call GEX',
                marker_color='rgba(0, 255, 0, 0.6)',
                hovertemplate='Strike: $%{x}<br>Call GEX: %{y:,.0f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Put GEX bars (negative)
        fig.add_trace(
            go.Bar(
                x=strikes,
                y=put_gex,
                name='Put GEX',
                marker_color='rgba(255, 0, 0, 0.6)',
                hovertemplate='Strike: $%{x}<br>Put GEX: %{y:,.0f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Current price line
        fig.add_vline(
            x=current_price,
            line_dash="dash",
            line_color="white",
            annotation_text=f"Current: ${current_price:.2f}",
            annotation_position="top",
            row=1, col=1
        )
        
        # Gamma flip point
        if gex_data.get('flip_point'):
            fig.add_vline(
                x=gex_data['flip_point'],
                line_dash="dot",
                line_color="yellow",
                annotation_text=f"Flip: ${gex_data['flip_point']:.2f}",
                annotation_position="bottom",
                row=1, col=1
            )
        
        # Net GEX line chart
        fig.add_trace(
            go.Scatter(
                x=strikes,
                y=net_gex,
                name='Net GEX',
                line=dict(color='cyan', width=2),
                fill='tozeroy',
                hovertemplate='Strike: $%{x}<br>Net GEX: %{y:,.0f}<extra></extra>'
            ),
            row=2, col=1
        )
        
        # Zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
        
        # Layout
        fig.update_layout(
            height=700,
            showlegend=True,
            hovermode='x unified',
            template='plotly_dark',
            title_text=f"GEX Profile - Net: {gex_data['total_net_gex']/1e9:.2f}B",
            title_font_size=20
        )
        
        fig.update_xaxes(title_text="Strike Price", row=2, col=1)
        fig.update_yaxes(title_text="Gamma Exposure", row=1, col=1)
        fig.update_yaxes(title_text="Net GEX", row=2, col=1)
        
        return fig
    except Exception as e:
        st.error(f"Error creating GEX chart: {e}")
        return go.Figure()

def create_monte_carlo_chart(mc_results: Dict) -> go.Figure:
    """Create Monte Carlo simulation visualization"""
    try:
        fig = go.Figure()
        
        # Plot sample paths (first 100)
        sample_paths = mc_results['price_paths'][:100]
        days = range(sample_paths.shape[1])
        
        for path in sample_paths:
            fig.add_trace(
                go.Scatter(
                    x=list(days),
                    y=path,
                    mode='lines',
                    line=dict(width=0.5, color='rgba(100, 100, 255, 0.1)'),
                    showlegend=False,
                    hoverinfo='skip'
                )
            )
        
        # Add mean path
        mean_path = np.mean(mc_results['price_paths'], axis=0)
        fig.add_trace(
            go.Scatter(
                x=list(days),
                y=mean_path,
                mode='lines',
                name='Mean Path',
                line=dict(width=3, color='yellow')
            )
        )
        
        # Add confidence bands
        upper_band = np.percentile(mc_results['price_paths'], 97.5, axis=0)
        lower_band = np.percentile(mc_results['price_paths'], 2.5, axis=0)
        
        fig.add_trace(
            go.Scatter(
                x=list(days),
                y=upper_band,
                mode='lines',
                name='95% Upper',
                line=dict(width=2, dash='dash', color='green'),
                showlegend=True
            )
        )
        
        fig.add_trace(
            go.Scatter(
                x=list(days),
                y=lower_band,
                mode='lines',
                name='95% Lower',
                line=dict(width=2, dash='dash', color='red'),
                fill='tonexty',
                fillcolor='rgba(100, 100, 100, 0.2)',
                showlegend=True
            )
        )
        
        # Layout
        fig.update_layout(
            title='Monte Carlo Price Simulation (10,000 Paths)',
            xaxis_title='Days',
            yaxis_title='Price',
            template='plotly_dark',
            height=500,
            hovermode='x'
        )
        
        return fig
    except Exception as e:
        st.error(f"Error creating Monte Carlo chart: {e}")
        return go.Figure()

def create_greeks_chart(greeks_data: Dict) -> go.Figure:
    """Create Greeks visualization"""
    try:
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Delta', 'Gamma', 'Theta', 'Vega'),
            specs=[[{"type": "indicator"}, {"type": "indicator"}],
                   [{"type": "indicator"}, {"type": "indicator"}]]
        )
        
        # Delta
        fig.add_trace(
            go.Indicator(
                mode="number+delta",
                value=greeks_data['delta'],
                number={'valueformat': '.3f'},
                delta={'reference': 0.5 if greeks_data['type'] == 'call' else -0.5},
                title={'text': "Delta"}
            ),
            row=1, col=1
        )
        
        # Gamma
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=greeks_data['gamma'],
                number={'valueformat': '.4f'},
                title={'text': "Gamma"}
            ),
            row=1, col=2
        )
        
        # Theta
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=greeks_data['theta'],
                number={'valueformat': '.3f', 'prefix': '$'},
                title={'text': "Theta (daily)"}
            ),
            row=2, col=1
        )
        
        # Vega
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=greeks_data['vega'],
                number={'valueformat': '.3f', 'prefix': '$'},
                title={'text': "Vega (per 1%)"}
            ),
            row=2, col=2
        )
        
        fig.update_layout(
            template='plotly_dark',
            height=400,
            showlegend=False
        )
        
        return fig
    except Exception as e:
        st.error(f"Error creating Greeks chart: {e}")
        return go.Figure()

# ============================================================================
# STREAMLIT UI COMPONENTS
# ============================================================================

def render_sidebar():
    """Render sidebar with controls and settings"""
    with st.sidebar:
        st.title("🎯 GEX Co-Pilot v5.0")
        st.markdown("---")
        
        # Symbol selection
        symbol = st.selectbox(
            "📊 Symbol",
            ["SPY", "QQQ", "IWM", "DIA", "TSLA", "AAPL", "NVDA"],
            index=0
        )
        
        # Refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
        
        st.markdown("---")
        
        # Position sizing calculator
        st.subheader("💰 Position Sizing")
        account_size = st.number_input(
            "Account Size ($)",
            min_value=1000,
            max_value=10000000,
            value=50000,
            step=1000
        )
        
        risk_pct = st.slider(
            "Risk per Trade (%)",
            min_value=1.0,
            max_value=5.0,
            value=2.0,
            step=0.5
        )
        
        max_position = account_size * (risk_pct / 100)
        st.metric("Max Position Size", f"${max_position:,.0f}")
        
        st.markdown("---")
        
        # Trade stats
        st.subheader("📈 Performance")
        stats = get_trade_stats()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Win Rate", f"{stats['win_rate']:.1f}%")
            st.metric("Total Trades", stats['total_trades'])
        with col2:
            st.metric("Total P&L", f"${stats['total_pnl']:,.0f}")
            st.metric("Avg Win", f"${stats['avg_win']:,.0f}")
        
        return symbol, account_size, risk_pct

def render_gex_overview(gex_data: Dict, fred_regime: Dict):
    """Render main GEX overview section"""
    st.header("📊 Gamma Exposure Overview")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        net_gex_b = gex_data['total_net_gex'] / 1e9
        st.metric(
            "Net GEX",
            f"{net_gex_b:.2f}B",
            delta="Positive" if net_gex_b > 0 else "Negative"
        )
    
    with col2:
        if gex_data['flip_point']:
            dist_to_flip = ((gex_data['current_price'] - gex_data['flip_point']) / 
                           gex_data['current_price'] * 100)
            st.metric(
                "Gamma Flip",
                f"${gex_data['flip_point']:.2f}",
                delta=f"{dist_to_flip:.2f}%"
            )
    
    with col3:
        if gex_data['call_wall']:
            st.metric("Call Wall", f"${gex_data['call_wall']:.2f}")
    
    with col4:
        if gex_data['put_wall']:
            st.metric("Put Wall", f"${gex_data['put_wall']:.2f}")
    
    # FRED regime banner
    if fred_regime['regime'] != 'neutral':
        regime_color = {
            'risk_off': '🔴',
            'range_bound': '🟡',
            'risk_on': '🟢'
        }
        st.info(f"{regime_color.get(fred_regime['regime'], '⚪')} **Economic Regime: {fred_regime['regime'].upper()}**")
        
        if fred_regime['directives']:
            with st.expander("📋 Actionable Directives"):
                for directive in fred_regime['directives']:
                    st.write(f"- {directive}")
    
    # GEX Profile Chart
    fig = create_gex_profile_chart(gex_data)
    st.plotly_chart(fig, use_container_width=True)

def render_setup_recommendations(setups: List[Dict]):
    """Render trading setup recommendations"""
    st.header("🎯 Trading Setups")
    
    if not setups:
        st.warning("No high-confidence setups detected at this time.")
        return
    
    for i, setup in enumerate(setups[:3]):  # Top 3 setups
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
                
                # Trade logging form
                if st.session_state.get(f'log_trade_{i}'):
                    with st.form(key=f'trade_form_{i}'):
                        strike = st.number_input("Strike", value=setup.get('target_strike', 0))
                        expiration = st.date_input("Expiration")
                        entry_price = st.number_input("Entry Price", min_value=0.01, value=1.0)
                        contracts = st.number_input("Contracts", min_value=1, value=1)
                        notes = st.text_area("Notes")
                        
                        if st.form_submit_button("Save Trade"):
                            trade_data = {
                                'symbol': st.session_state.get('current_symbol', 'SPY'),
                                'setup_type': setup['type'],
                                'direction': setup['direction'],
                                'strike': strike,
                                'expiration': expiration.strftime('%Y-%m-%d'),
                                'entry_price': entry_price,
                                'contracts': contracts,
                                'notes': notes
                            }
                            
                            if save_trade(trade_data):
                                st.success("✅ Trade logged successfully!")
                                st.session_state[f'log_trade_{i}'] = False
                                time.sleep(1)
                                st.rerun()

def render_monte_carlo_section(current_price: float):
    """Render Monte Carlo simulation section"""
    st.header("🎲 Monte Carlo Simulation")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        volatility = st.slider("Implied Volatility", 0.1, 0.8, 0.25, 0.05) 
    with col2:
        dte = st.slider("Days to Expiry", 1, 30, 7)
    with col3:
        num_sims = st.selectbox("Simulations", [1000, 5000, 10000], index=2)
    
    if st.button("🚀 Run Simulation", use_container_width=True):
        with st.spinner("Running Monte Carlo simulation..."):
            mc_results = run_monte_carlo(current_price, volatility, dte, num_sims)
            
            if mc_results:
                # Display results
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Expected Price", f"${mc_results['mean_price']:.2f}")
                with col2:
                    st.metric("95% Lower", f"${mc_results['lower_bound']:.2f}")
                with col3:
                    st.metric("95% Upper", f"${mc_results['upper_bound']:.2f}")
                with col4:
                    st.metric("Prob Above Current", f"{mc_results['prob_above']*100:.1f}%")
                
                # Chart
                fig = create_monte_carlo_chart(mc_results)
                st.plotly_chart(fig, use_container_width=True)
                
                # Distribution
                fig_dist = go.Figure()
                fig_dist.add_trace(
                    go.Histogram(
                        x=mc_results['final_prices'],
                        nbinsx=50,
                        name='Price Distribution',
                        marker_color='rgba(0, 150, 255, 0.6)'
                    )
                )
                fig_dist.add_vline(
                    x=current_price,
                    line_dash="dash",
                    line_color="yellow",
                    annotation_text="Current"
                )
                fig_dist.update_layout(
                    title='Final Price Distribution',
                    xaxis_title='Price',
                    yaxis_title='Frequency',
                    template='plotly_dark',
                    height=400
                )
                st.plotly_chart(fig_dist, use_container_width=True)

def render_greeks_calculator(current_price: float):
    """Render Black-Scholes Greeks calculator"""
    st.header("📐 Greeks Calculator")
    
    if not VOLLIB_AVAILABLE:
        st.warning("⚠️ Install py_vollib to enable Greeks calculator: `pip install py_vollib`")
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        option_type = st.radio("Option Type", ["call", "put"])
        strike = st.number_input("Strike Price", value=current_price, step=1.0)
    
    with col2:
        dte = st.number_input("Days to Expiry", min_value=1, max_value=365, value=30)
        volatility = st.slider("Implied Vol", 0.1, 1.0, 0.25, 0.01)
    
    with col3:
        risk_free = st.slider("Risk-Free Rate", 0.0, 0.1, 0.045, 0.005)
    
    if st.button("Calculate Greeks", use_container_width=True):
        greeks_data = calculate_black_scholes(
            current_price, strike, dte, volatility, risk_free, option_type
        )
        
        if greeks_data:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.metric("Option Price", f"${greeks_data['price']:.2f}")
                st.metric("Delta", f"{greeks_data['delta']:.4f}")
                st.metric("Gamma", f"{greeks_data['gamma']:.4f}")
            
            with col2:
                st.metric("Theta (daily)", f"${greeks_data['theta']:.3f}")
                st.metric("Vega (per 1%)", f"${greeks_data['vega']:.3f}")
            
            # Greeks visualization
            fig = create_greeks_chart(greeks_data)
            st.plotly_chart(fig, use_container_width=True)

def render_active_trades():
    """Render active trades management"""
    st.header("📋 Active Positions")
    
    df_open = get_open_trades()
    
    if len(df_open) == 0:
        st.info("No active positions")
        return
    
    for idx, trade in df_open.iterrows():
        with st.expander(
            f"{trade['symbol']} - {trade['direction']} ${trade['strike']:.0f} "
            f"(Entry: ${trade['entry_price']:.2f})"
        ):
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.write(f"**Setup Type:** {trade['setup_type']}")
                st.write(f"**Expiration:** {trade['expiration']}")
                st.write(f"**Contracts:** {trade['contracts']}")
                st.write(f"**Entry Date:** {trade['entry_date']}")
                if trade['notes']:
                    st.write(f"**Notes:** {trade['notes']}")
            
            with col2:
                exit_price = st.number_input(
                    "Exit Price",
                    min_value=0.01,
                    value=float(trade['entry_price']),
                    key=f"exit_{trade['id']}"
                )
            
            with col3:
                if st.button("Close Position", key=f"close_{trade['id']}"):
                    if close_trade(trade['id'], exit_price):
                        st.success("✅ Position closed!")
                        time.sleep(1)
                        st.rerun()

def render_alerts():
    """Render alerts section"""
    st.header("🔔 Active Alerts")
    
    df_alerts = get_unread_alerts()
    
    if len(df_alerts) == 0:
        st.success("No active alerts")
        return
    
    for idx, alert in df_alerts.iterrows():
        priority_color = {
            'HIGH': '🔴',
            'MEDIUM': '🟡',
            'LOW': '🟢'
        }
        
        col1, col2 = st.columns([4, 1])
        
        with col1:
            st.markdown(
                f"{priority_color.get(alert['priority'], '⚪')} "
                f"**{alert['alert_type']}** - {alert['symbol']}"
            )
            st.write(alert['message'])
            st.caption(f"🕐 {alert['timestamp']}")
        
        with col2:
            if st.button("Mark Read", key=f"alert_{alert['id']}"):
                mark_alert_read(alert['id'])
                st.rerun()

def render_chat_interface():
    """Render AI chat assistant"""
    st.header("💬 AI Trading Assistant")
    
    # Initialize chat history
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask about GEX, setups, or market conditions..."):
        # Add user message
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate response (placeholder - integrate with Claude API)
        with st.chat_message("assistant"):
            response = f"I understand you're asking about: '{prompt}'. This feature requires Claude API integration. Check the system instructions for implementation details."
            st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point"""
    
    # Initialize database
    init_database()
    
    # Render sidebar and get settings
    symbol, account_size, risk_pct = render_sidebar()
    st.session_state['current_symbol'] = symbol
    
    # Fetch data
    with st.spinner(f"Fetching GEX data for {symbol}..."):
        raw_gex = fetch_gex_data(symbol)
        
        if raw_gex:
            gex_data = parse_gex_data(raw_gex)
            fred_regime = get_fred_regime()
            setups = detect_setups(gex_data, fred_regime)
            
            # Main tabs
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 GEX Overview",
                "🎯 Setups",
                "🎲 Monte Carlo",
                "📐 Greeks",
                "📋 Positions"
            ])
            
            with tab1:
                render_gex_overview(gex_data, fred_regime)
                render_chat_interface()
            
            with tab2:
                render_setup_recommendations(setups)
                render_chat_interface()
            
            with tab3:
                render_monte_carlo_section(gex_data['current_price'])
                render_chat_interface()
            
            with tab4:
                render_greeks_calculator(gex_data['current_price'])
                render_chat_interface()
            
            with tab5:
                render_active_trades()
                render_alerts()
        
        else:
            st.error("❌ Unable to fetch GEX data. Please check your connection and try again.")

# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    main()
    
    # Footer
    st.markdown("---")
    st.caption("GEX Trading Co-Pilot v5.0 | Built with Streamlit & Python | © 2025")

# ============================================================================
# END OF PART 2 - APPLICATION COMPLETE
# ============================================================================
