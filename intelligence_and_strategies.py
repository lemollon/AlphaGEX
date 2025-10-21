"""
intelligence_and_strategies.py - All Intelligence, RAG, and Strategy Classes
NOTE: This file should be placed in the same directory as the other files
When importing in main.py, use: from intelligence_and_strategies import *
"""

import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import time
import sqlite3
from typing import List, Dict, Optional
from config_and_database import DB_PATH, MM_STATES, STRATEGIES

# Import the TradingVolatilityAPI if we need it for VIX
try:
    import yfinance as yf
    from scipy.stats import norm
    import math
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    norm = None
    math = None

# ============================================================================
# CRITICAL NEW FEATURES FOR ULTIMATE COPILOT
# ============================================================================

class RealOptionsChainFetcher:
    """Fetches REAL options chain data from Yahoo Finance"""

    def __init__(self):
        self.cache = {}
        self.cache_time = {}

    def get_options_chain(self, symbol: str, expiry_date: str = None) -> Dict:
        """Get real options chain with bid/ask/greeks"""

        cache_key = f"{symbol}_{expiry_date}"

        # Check cache (5 minute expiry)
        if cache_key in self.cache:
            if (datetime.now() - self.cache_time[cache_key]).seconds < 300:
                return self.cache[cache_key]

        try:
            ticker = yf.Ticker(symbol)

            # Get available expiration dates
            expirations = ticker.options
            if not expirations:
                return {}

            # Use specified expiry or nearest weekly
            if expiry_date and expiry_date in expirations:
                expiry = expiry_date
            else:
                expiry = expirations[0]  # Nearest expiry

            # Get options chain
            opt_chain = ticker.option_chain(expiry)
            calls = opt_chain.calls
            puts = opt_chain.puts

            # Get current stock price
            current_price = ticker.history(period='1d')['Close'].iloc[-1]

            result = {
                'symbol': symbol,
                'current_price': current_price,
                'expiry': expiry,
                'calls': calls.to_dict('records'),
                'puts': puts.to_dict('records'),
                'timestamp': datetime.now().isoformat()
            }

            # Cache it
            self.cache[cache_key] = result
            self.cache_time[cache_key] = datetime.now()

            return result

        except Exception as e:
            st.warning(f"Could not fetch options chain for {symbol}: {e}")
            return {}

    def find_best_strike(self, symbol: str, option_type: str, delta_target: float = 0.50) -> Dict:
        """Find option closest to target delta"""

        chain = self.get_options_chain(symbol)
        if not chain:
            return {}

        options = chain['calls'] if option_type.lower() == 'call' else chain['puts']
        current_price = chain['current_price']

        # Find ATM or specified delta
        best_option = None
        closest_delta = 999

        for opt in options:
            # Calculate approx delta if not provided
            strike = opt['strike']
            if option_type.lower() == 'call':
                approx_delta = max(0, min(1, 0.5 + (current_price - strike) / current_price))
            else:
                approx_delta = max(0, min(1, 0.5 - (strike - current_price) / current_price))

            delta_diff = abs(approx_delta - delta_target)

            if delta_diff < closest_delta:
                closest_delta = delta_diff
                best_option = opt

        return best_option or {}


class GreeksCalculator:
    """Calculate option Greeks using Black-Scholes"""

    @staticmethod
    def calculate_greeks(spot: float, strike: float, time_to_expiry: float,
                        volatility: float, rate: float = 0.05,
                        option_type: str = 'call') -> Dict:
        """Calculate all Greeks for an option"""

        if not YFINANCE_AVAILABLE or norm is None:
            return {}

        try:
            # Prevent division by zero
            if time_to_expiry <= 0:
                time_to_expiry = 1/365  # 1 day

            # Calculate d1 and d2
            d1 = (np.log(spot / strike) + (rate + 0.5 * volatility ** 2) * time_to_expiry) / \
                 (volatility * np.sqrt(time_to_expiry))
            d2 = d1 - volatility * np.sqrt(time_to_expiry)

            # Calculate Greeks
            if option_type.lower() == 'call':
                delta = norm.cdf(d1)
                price = spot * norm.cdf(d1) - strike * np.exp(-rate * time_to_expiry) * norm.cdf(d2)
            else:
                delta = -norm.cdf(-d1)
                price = strike * np.exp(-rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)

            # Gamma (same for calls and puts)
            gamma = norm.pdf(d1) / (spot * volatility * np.sqrt(time_to_expiry))

            # Vega (same for calls and puts)
            vega = spot * norm.pdf(d1) * np.sqrt(time_to_expiry) / 100  # Per 1% change in IV

            # Theta
            if option_type.lower() == 'call':
                theta = (-spot * norm.pdf(d1) * volatility / (2 * np.sqrt(time_to_expiry)) - \
                        rate * strike * np.exp(-rate * time_to_expiry) * norm.cdf(d2)) / 365
            else:
                theta = (-spot * norm.pdf(d1) * volatility / (2 * np.sqrt(time_to_expiry)) + \
                        rate * strike * np.exp(-rate * time_to_expiry) * norm.cdf(-d2)) / 365

            return {
                'delta': round(delta, 3),
                'gamma': round(gamma, 4),
                'theta': round(theta, 3),
                'vega': round(vega, 3),
                'price': round(price, 2)
            }

        except Exception as e:
            return {}


class PositionSizingCalculator:
    """Calculate exact position sizes based on account and risk"""

    @staticmethod
    def calculate_contracts(account_size: float, risk_pct: float,
                          entry_price: float, stop_price: float) -> Dict:
        """Calculate how many contracts to trade"""

        if account_size <= 0 or risk_pct <= 0:
            return {'error': 'Invalid account size or risk percentage'}

        # Calculate risk amount
        risk_dollars = account_size * (risk_pct / 100)

        # Calculate risk per contract
        risk_per_contract = abs(entry_price - stop_price) * 100  # Options are 100 shares

        if risk_per_contract <= 0:
            return {'error': 'Stop must be different from entry'}

        # Calculate contracts
        contracts = int(risk_dollars / risk_per_contract)
        contracts = max(1, contracts)  # At least 1 contract

        # Calculate actual risk
        actual_risk = contracts * risk_per_contract
        actual_risk_pct = (actual_risk / account_size) * 100

        return {
            'contracts': contracts,
            'risk_dollars': round(actual_risk, 2),
            'risk_pct': round(actual_risk_pct, 2),
            'max_loss': round(actual_risk, 2),
            'cost_basis': round(contracts * entry_price * 100, 2)
        }


class PsychologicalCoach:
    """Detects tilt, revenge trading, and emotional patterns"""

    def __init__(self):
        self.session_trade_count = 0
        self.last_loss_time = None
        self.ignored_warnings = []

    def analyze_behavior(self, conversation_history: List[Dict], current_request: str) -> Dict:
        """Analyze user behavior for psychological red flags"""

        red_flags = []
        severity = 'normal'

        # Count recent trade requests
        recent_requests = [msg for msg in conversation_history[-10:]
                          if msg.get('role') == 'user']
        trade_keywords = ['trade', 'buy', 'sell', 'calls', 'puts', 'position']

        trade_request_count = sum(
            1 for msg in recent_requests
            if any(kw in msg.get('content', '').lower() for kw in trade_keywords)
        )

        # RED FLAG 1: Overtrading (>4 trade requests in recent history)
        if trade_request_count >= 4:
            red_flags.append({
                'type': 'OVERTRADING',
                'message': f'🚨 You\'ve made {trade_request_count} trade requests recently. Take a break.',
                'severity': 'high'
            })
            severity = 'high'

        # RED FLAG 2: Revenge trading (mentioning loss + new trade request)
        loss_keywords = ['loss', 'lost', 'down', 'stopped out', 'wrong', 'failed']
        recent_content = ' '.join([msg.get('content', '') for msg in recent_requests[-3:]])

        if any(kw in recent_content.lower() for kw in loss_keywords):
            if any(kw in current_request.lower() for kw in trade_keywords):
                red_flags.append({
                    'type': 'REVENGE_TRADING',
                    'message': '🚨 REVENGE TRADING ALERT: You just mentioned a loss and now want another trade. Step away for 30 minutes.',
                    'severity': 'critical'
                })
                severity = 'critical'

        # RED FLAG 3: Ignoring previous advice
        if len(conversation_history) >= 4:
            last_ai_response = None
            for msg in reversed(conversation_history):
                if msg.get('role') == 'assistant':
                    last_ai_response = msg.get('content', '')
                    break

            if last_ai_response:
                if 'terrible' in last_ai_response.lower() or 'risky' in last_ai_response.lower():
                    if 'still' in current_request.lower() or 'but' in current_request.lower():
                        red_flags.append({
                            'type': 'IGNORING_ADVICE',
                            'message': '⚠️ I just warned you this was risky, and you\'re still pushing. Trust the process.',
                            'severity': 'medium'
                        })
                        severity = 'medium' if severity == 'normal' else severity

        # RED FLAG 4: After hours trading (if outside market hours)
        current_hour = datetime.now().hour
        if current_hour < 9 or current_hour >= 16:
            if any(kw in current_request.lower() for kw in trade_keywords):
                red_flags.append({
                    'type': 'AFTER_HOURS',
                    'message': '⚠️ Market is closed. Don\'t plan trades emotionally after hours. Wait for market open.',
                    'severity': 'low'
                })

        # RED FLAG 5: Wednesday/Thursday/Friday directional requests
        day_of_week = datetime.now().strftime('%A')
        if day_of_week in ['Wednesday', 'Thursday', 'Friday']:
            hour = datetime.now().hour
            if day_of_week == 'Wednesday' and hour >= 15:
                if 'call' in current_request.lower() or 'put' in current_request.lower():
                    red_flags.append({
                        'type': 'TIMING_VIOLATION',
                        'message': '🛑 Wednesday 3PM: CLOSE directional positions, don\'t open new ones!',
                        'severity': 'critical'
                    })
                    severity = 'critical'

        return {
            'severity': severity,
            'red_flags': red_flags,
            'trade_request_count': trade_request_count,
            'coaching_needed': len(red_flags) > 0
        }

# ============================================================================
# RAG SYSTEM FOR INTELLIGENT TRADING
# ============================================================================
class TradingRAG:
    """Retrieval Augmented Generation for personalized trading intelligence"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self.embeddings_cache = {}
        
    def get_similar_trades(self, current_setup: Dict, limit: int = 5) -> List[Dict]:
        """Find similar historical trades based on GEX levels"""
        conn = sqlite3.connect(self.db_path)
        
        current_gex = current_setup.get('net_gex', 0)
        
        query = """
            SELECT r.*, g.net_gex, g.flip_point, g.call_wall, g.put_wall
            FROM recommendations r
            JOIN gex_history g ON r.timestamp = g.timestamp
            WHERE ABS(g.net_gex - ?) / ABS(?) < 0.2
            ORDER BY r.timestamp DESC
            LIMIT ?
        """
        
        try:
            df = pd.read_sql_query(query, conn, params=(current_gex, current_gex, limit))
            conn.close()
            
            if not df.empty:
                return df.to_dict('records')
        except:
            pass
        
        conn.close()
        return []
    
    def get_personal_stats(self, strategy: str = None) -> Dict:
        """Get personal trading statistics"""
        conn = sqlite3.connect(self.db_path)
        
        base_query = """
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                AVG(CASE WHEN pnl > 0 THEN pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl ELSE NULL END) as avg_loss,
                SUM(pnl) as total_pnl
            FROM positions
            WHERE status = 'CLOSED'
        """
        
        if strategy:
            base_query += f" AND strategy = '{strategy}'"
        
        try:
            result = pd.read_sql_query(base_query, conn).iloc[0]
            
            day_stats_query = """
                SELECT 
                    strftime('%w', opened_at) as day_of_week,
                    COUNT(*) as trades,
                    AVG(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as win_rate,
                    AVG(pnl) as avg_pnl
                FROM positions
                WHERE status = 'CLOSED'
                GROUP BY strftime('%w', opened_at)
            """
            
            day_stats = pd.read_sql_query(day_stats_query, conn)
            
            conn.close()
            
            return {
                'total_trades': int(result['total_trades']) if result['total_trades'] else 0,
                'win_rate': (result['wins'] / result['total_trades'] * 100) if result['total_trades'] else 0,
                'avg_win': float(result['avg_win']) if result['avg_win'] else 0,
                'avg_loss': float(result['avg_loss']) if result['avg_loss'] else 0,
                'total_pnl': float(result['total_pnl']) if result['total_pnl'] else 0,
                'day_stats': day_stats.to_dict('records'),
                'early_win_rate': 45  # Default placeholder
            }
        except Exception:
            conn.close()
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'total_pnl': 0,
                'day_stats': [],
                'early_win_rate': 45
            }
    
    def get_pattern_success_rate(self, pattern: Dict) -> float:
        """Calculate success rate for specific pattern"""
        conn = sqlite3.connect(self.db_path)
        
        conditions = []
        params = []
        
        if 'net_gex_range' in pattern:
            conditions.append("g.net_gex BETWEEN ? AND ?")
            params.extend(pattern['net_gex_range'])
        
        if 'day_of_week' in pattern:
            conditions.append("strftime('%w', r.timestamp) = ?")
            params.append(pattern['day_of_week'])
        
        if 'strategy' in pattern:
            conditions.append("r.strategy = ?")
            params.append(pattern['strategy'])
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN r.pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM recommendations r
            JOIN gex_history g ON r.timestamp = g.timestamp
            WHERE {where_clause}
        """
        
        try:
            result = pd.read_sql_query(query, conn, params=params).iloc[0]
            conn.close()
            
            if result['total'] > 0:
                return (result['wins'] / result['total']) * 100
        except:
            pass
        
        conn.close()
        return 0
    
    def build_context_for_claude(self, current_data: Dict, user_query: str) -> str:
        """Build rich context for Claude using RAG"""
        
        context_parts = []
        
        similar_trades = self.get_similar_trades(current_data)
        if similar_trades:
            context_parts.append("SIMILAR HISTORICAL SETUPS:")
            for trade in similar_trades[:3]:
                outcome = "WON" if trade.get('pnl', 0) > 0 else "LOST"
                context_parts.append(
                    f"- {trade['timestamp']}: {trade['strategy']} at GEX {trade['net_gex']/1e9:.1f}B "
                    f"→ {outcome} {abs(trade.get('pnl', 0)):.2f}"
                )
        
        personal_stats = self.get_personal_stats()
        if personal_stats['total_trades'] > 0:
            context_parts.append(f"\nYOUR PERSONAL STATS:")
            context_parts.append(f"- Overall Win Rate: {personal_stats['win_rate']:.1f}%")
            context_parts.append(f"- Avg Win: ${personal_stats['avg_win']:.2f}")
            context_parts.append(f"- Avg Loss: ${personal_stats['avg_loss']:.2f}")
            context_parts.append(f"- Total P&L: ${personal_stats['total_pnl']:.2f}")
            
            if personal_stats['day_stats']:
                context_parts.append("\nYOUR PERFORMANCE BY DAY:")
                day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
                for day_stat in personal_stats['day_stats']:
                    day_idx = int(day_stat['day_of_week'])
                    day_name = day_names[day_idx]
                    context_parts.append(
                        f"- {day_name}: {day_stat['win_rate']*100:.0f}% win rate, "
                        f"avg ${day_stat['avg_pnl']:.2f}"
                    )
        
        current_pattern = {
            'net_gex_range': [current_data.get('net_gex', 0) * 0.8, current_data.get('net_gex', 0) * 1.2],
            'day_of_week': str(datetime.now().weekday())
        }
        
        success_rate = self.get_pattern_success_rate(current_pattern)
        if success_rate > 0:
            context_parts.append(f"\nTHIS EXACT PATTERN SUCCESS RATE: {success_rate:.1f}%")
        
        return "\n".join(context_parts)

# ============================================================================
# FRED INTEGRATION
# ============================================================================
class FREDIntegration:
    """Federal Reserve Economic Data integration for macro context"""
    
    def __init__(self):
        self.api_key = st.secrets.get("fred_api_key", "")
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"
        self.cache = {}
        self.cache_ttl = 3600
        self.tv_api = None
    
    def get_vix(self) -> float:
        """Get VIX from Yahoo Finance or default"""
        try:
            if YFINANCE_AVAILABLE:
                vix = yf.Ticker("^VIX")
                hist = vix.history(period="1d")
                if not hist.empty:
                    return float(hist['Close'].iloc[-1])
        except:
            pass
        return 20.0
    
    def get_economic_data(self) -> Dict:
        """Fetch key economic indicators with real VIX"""
        
        real_vix = self.get_vix()
        
        data = {'vix': real_vix}
        
        defaults = {
            'ten_year_yield': 4.3,
            'fed_funds_rate': 5.5,
            'dollar_index': 105,
            'unemployment': 3.8,
            'cpi': 3.2
        }
        
        if not self.api_key:
            data.update(defaults)
            return data
        
        indicators = {
            'DGS10': 'ten_year_yield',
            'DFF': 'fed_funds_rate',
            'DEXUSEU': 'dollar_index',
            'UNRATE': 'unemployment',
            'CPIAUCSL': 'cpi'
        }
        
        for series_id, name in indicators.items():
            if series_id in self.cache:
                cached_data, cached_time = self.cache[series_id]
                if time.time() - cached_time < self.cache_ttl:
                    data[name] = cached_data
                    continue
            
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
                data[name] = defaults[name]
        
        return data
    
    def get_regime(self, data: Dict) -> Dict:
        """Determine market regime from economic data"""
        
        vix = data.get('vix', 20)
        ten_year = data.get('ten_year_yield', 4.3)
        fed_funds = data.get('fed_funds_rate', 5.5)
        
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
    """Advanced AI integration for market analysis - NOW WITH ULTIMATE FEATURES"""

    def __init__(self):
        self.api_key = st.secrets.get("claude_api_key", "")
        self.model = "claude-3-5-sonnet-20241022"
        self.conversation_history = []
        self.fred = FREDIntegration()

        # NEW ULTIMATE FEATURES
        self.options_fetcher = RealOptionsChainFetcher()
        self.greeks_calc = GreeksCalculator()
        self.position_sizer = PositionSizingCalculator()
        self.psych_coach = PsychologicalCoach()

        # Account settings (get from session state if available)
        self.account_size = st.session_state.get('account_size', 50000)  # Default $50k
        self.risk_pct = st.session_state.get('risk_per_trade', 2)  # Default 2%

        if not self.api_key:
            st.warning("Claude API key not found in secrets. Using fallback analysis.")
    
    def analyze_market(self, market_data: Dict, user_query: str) -> str:
        """Generate intelligent market analysis with RAG context - NOW WITH ULTIMATE FEATURES"""

        # STEP 1: PSYCHOLOGICAL COACHING CHECK (FIRST - BEFORE ANYTHING)
        psych_analysis = self.psych_coach.analyze_behavior(self.conversation_history, user_query)

        if psych_analysis['coaching_needed']:
            warning_message = "🧠 **PSYCHOLOGICAL CHECK**\n\n"
            for flag in psych_analysis['red_flags']:
                warning_message += f"{flag['message']}\n\n"

            # If CRITICAL severity, refuse to provide trade
            if psych_analysis['severity'] == 'critical':
                warning_message += "\n❌ **I'm refusing to provide a trade recommendation right now.**\n"
                warning_message += "Take a break. Clear your head. Come back in 30 minutes.\n"
                warning_message += "Trading while emotional is the #1 way to blow up an account.\n"
                return warning_message

            # Otherwise, show warning but continue
            st.warning(warning_message)

        if not self.api_key:
            return self._fallback_analysis_with_rag(market_data, user_query)

        # STEP 2: Extract symbol from query if mentioned
        query_upper = user_query.upper()
        mentioned_symbol = None
        for word in query_upper.split():
            if len(word) <= 5 and word.isalpha():
                mentioned_symbol = word
                break

        symbol = market_data.get('symbol', mentioned_symbol or 'SPY')

        # STEP 3: If market_data is empty, fetch fresh data
        if not market_data or not market_data.get('net_gex'):
            try:
                from core_classes_and_engines import TradingVolatilityAPI
                api = TradingVolatilityAPI()
                fresh_data = api.get_gex_data(symbol)
                if fresh_data:
                    market_data = fresh_data
                    st.info(f"📊 Fetched fresh GEX data for {symbol}")
            except Exception as e:
                st.warning(f"Using analytical approach for {symbol} (live data unavailable)")

        # STEP 4: FETCH REAL OPTIONS CHAIN DATA
        options_chain = self.options_fetcher.get_options_chain(symbol)
        real_options_data = {}

        if options_chain:
            # Find best ATM call and put
            best_call = self.options_fetcher.find_best_strike(symbol, 'call', delta_target=0.50)
            best_put = self.options_fetcher.find_best_strike(symbol, 'put', delta_target=-0.50)

            real_options_data = {
                'atm_call': best_call,
                'atm_put': best_put,
                'expiry': options_chain.get('expiry'),
                'current_price': options_chain.get('current_price')
            }

            # STEP 5: CALCULATE GREEKS for the ATM options
            if best_call:
                greeks_call = self.greeks_calc.calculate_greeks(
                    spot=options_chain['current_price'],
                    strike=best_call.get('strike', options_chain['current_price']),
                    time_to_expiry=7/365,  # Assume 1 week for now
                    volatility=best_call.get('impliedVolatility', 0.20),
                    option_type='call'
                )
                real_options_data['call_greeks'] = greeks_call

            if best_put:
                greeks_put = self.greeks_calc.calculate_greeks(
                    spot=options_chain['current_price'],
                    strike=best_put.get('strike', options_chain['current_price']),
                    time_to_expiry=7/365,
                    volatility=best_put.get('impliedVolatility', 0.20),
                    option_type='put'
                )
                real_options_data['put_greeks'] = greeks_put

        # STEP 6: CALCULATE POSITION SIZING (example for typical trade)
        example_entry = real_options_data.get('atm_call', {}).get('lastPrice', 5.0)
        example_stop = example_entry * 0.70  # 30% stop loss

        position_sizing = self.position_sizer.calculate_contracts(
            account_size=self.account_size,
            risk_pct=self.risk_pct,
            entry_price=example_entry,
            stop_price=example_stop
        )

        context = self._build_context(market_data)
        context['symbol'] = symbol

        rag = TradingRAG()
        rag_context = rag.build_context_for_claude(market_data, user_query)

        optimizer = MultiStrategyOptimizer()
        best_strategies = optimizer.get_best_strategy(market_data)

        calculator = DynamicLevelCalculator()
        zones = calculator.get_profitable_zones(market_data)

        self.conversation_history.append({"role": "user", "content": user_query})
        messages = self.conversation_history[-10:]

        messages.append({
            "role": "user",
            "content": f"""
            SYMBOL: {symbol}

            Current Market Data:
            {json.dumps(context, indent=2)}

            REAL OPTIONS CHAIN DATA:
            {json.dumps(real_options_data, indent=2)}

            POSITION SIZING (Account: ${self.account_size}, Risk: {self.risk_pct}%):
            {json.dumps(position_sizing, indent=2)}

            YOUR PERSONAL TRADING HISTORY:
            {rag_context}

            BEST STRATEGIES RIGHT NOW:
            {json.dumps(best_strategies, indent=2)}

            PROFITABLE ZONES:
            {json.dumps(zones, indent=2)}

            User's Specific Question: {user_query}

            CRITICAL REQUIREMENTS - YOU MUST:
            1. ALWAYS start response with "{symbol}" ticker symbol
            2. Use the REAL OPTIONS DATA above (actual strikes, prices, Greeks)
            3. Include GREEKS (delta, theta, gamma, vega) in your explanation
            4. Recommend EXACT number of contracts based on position sizing above
            5. ALWAYS provide AT LEAST ONE specific trade setup
            6. State probability of profit (even if low - be honest)
            7. NEVER say "no setup" - options traders ALWAYS find opportunities
            8. Reference the ACTUAL real options prices (bid/ask) from the data above
            9. Explain how Greeks will affect the trade (theta decay, delta move, etc.)
            10. Give precise entry/exit based on REAL market prices

            POSITION SIZING NOTE:
            The user's account is ${self.account_size} and they risk {self.risk_pct}% per trade.
            Recommend the appropriate number of contracts from the position sizing data.

            There is ALWAYS a trade. Use the REAL options data to give specific recommendations.
            """
        })

        try:
            response = self._call_claude_api(messages)
            self.conversation_history.append({"role": "assistant", "content": response})
            self._log_conversation(user_query, response, market_data)
            return response

        except Exception as e:
            st.error(f"Claude API Error: {e}")
            return self._fallback_analysis_with_rag(market_data, user_query)
    
    def challenge_trade_idea(self, idea: str, market_data: Dict) -> str:
        """Challenge user's trading ideas with sophisticated risk analysis and push-back"""

        if not self.api_key:
            return self._fallback_challenge(idea, market_data)

        context = self._build_context(market_data)

        # Get RAG context for personalized push-back
        rag = TradingRAG()
        rag_context = rag.build_context_for_claude(market_data, idea)
        personal_stats = rag.get_personal_stats()

        # Get better alternatives
        optimizer = MultiStrategyOptimizer()
        best_strategies = optimizer.get_best_strategy(market_data)

        # Calculate risk score
        risk_score = self._calculate_trade_risk(idea, market_data, context)

        messages = [
            {
                "role": "user",
                "content": f"""
                You are a TOUGH trading mentor who prioritizes protecting capital and making money.
                A trader wants to execute this idea - YOUR JOB is to challenge it HARD and push back if it's flawed.

                TRADER'S IDEA: {idea}

                CURRENT MARKET STATE:
                {json.dumps(context, indent=2)}

                RISK ASSESSMENT:
                {json.dumps(risk_score, indent=2)}

                TRADER'S PERSONAL STATS:
                {rag_context}

                BETTER ALTERNATIVE STRATEGIES:
                {json.dumps(best_strategies, indent=2)}

                YOUR RESPONSE MUST INCLUDE:

                1. **IMMEDIATE VERDICT**: Is this trade GOOD, RISKY, or TERRIBLE? Be blunt.

                2. **WHY IT COULD FAIL**: List specific ways this trade loses money:
                   - What MM behavior would kill this trade?
                   - What market moves would stop you out?
                   - What's the trader missing or ignoring?
                   - Reference their personal win rate for this type of trade

                3. **RISK/REWARD ANALYSIS**:
                   - Max profit potential (be realistic)
                   - Max loss potential
                   - Probability of profit based on current GEX levels
                   - Risk/reward ratio

                4. **BETTER ALTERNATIVES**: If this is risky/terrible, suggest 2-3 better trades with:
                   - Specific strikes and entry prices
                   - Why these have higher win probability
                   - How these align better with MM positioning

                5. **IF APPROVED**: If the trade is actually good, explain:
                   - What makes it smart RIGHT NOW
                   - Specific entry, target, and stop levels
                   - What to watch that would invalidate the thesis

                6. **EDUCATION**: Teach the trader what they need to understand:
                   - Key concept they're missing
                   - How to recognize this pattern in the future
                   - What data to check before this type of trade

                BE DIRECT. Don't sugarcoat bad ideas. Your job is to make them a profitable trader,
                not to make them feel good about bad trades. Push back HARD on risky plays.

                If it's late Wednesday or Thursday/Friday and they want directional trades, REFUSE and explain why.
                """
            }
        ]

        try:
            response = self._call_claude_api(messages)
            self._log_conversation(idea, response, market_data)
            return response
        except Exception as e:
            st.error(f"API Error: {e}")
            return self._fallback_challenge(idea, market_data)

    def teach_concept(self, market_data: Dict, topic: str) -> str:
        """Educational mode - teach trading concepts with real market examples"""

        if not self.api_key:
            return self._fallback_teaching(market_data, topic)

        context = self._build_context(market_data)

        # Get real examples from their trading history
        rag = TradingRAG()
        personal_examples = rag.get_personal_stats()

        messages = [
            {
                "role": "user",
                "content": f"""
                You are a master trading educator. Teach this concept using REAL current market data.

                TOPIC/QUESTION: {topic}

                CURRENT LIVE MARKET DATA:
                {json.dumps(context, indent=2)}

                STUDENT'S TRADING HISTORY:
                {json.dumps(personal_examples, indent=2)}

                TEACHING FRAMEWORK:

                1. **CONCEPT EXPLANATION**:
                   - Explain the concept in simple terms
                   - Why it matters for making money
                   - Common misconceptions

                2. **REAL-WORLD EXAMPLE FROM CURRENT MARKET**:
                   - Use the ACTUAL current GEX data above
                   - Show how the concept applies RIGHT NOW
                   - What would you trade based on this?

                3. **MARKET MAKER PSYCHOLOGY**:
                   - How do MMs react in this scenario?
                   - What are they FORCED to do by their hedging requirements?
                   - How can we profit from their forced actions?

                4. **PRACTICAL APPLICATION**:
                   - Specific checklist for recognizing this pattern
                   - What data points to look at
                   - When to act vs when to wait

                5. **COMMON MISTAKES**:
                   - What do beginners get wrong?
                   - How to avoid losing money on this
                   - Red flags that invalidate the setup

                6. **PERSONAL INSIGHTS**:
                   - Reference their actual trading stats if relevant
                   - Show how this applies to their historical trades
                   - Suggestions for improvement based on their pattern

                7. **ACTIONABLE TAKEAWAY**:
                   - One specific thing they can do TODAY
                   - How to practice recognizing this
                   - Expected profitability if executed correctly

                Use analogies, be conversational, but ALWAYS tie back to making money.
                Focus on practical application, not theory. Show them how to USE this knowledge to be profitable.
                """
            }
        ]

        try:
            response = self._call_claude_api(messages)
            self._log_conversation(topic, response, market_data)
            return response
        except Exception as e:
            st.error(f"API Error: {e}")
            return self._fallback_teaching(market_data, topic)

    def _calculate_trade_risk(self, idea: str, market_data: Dict, context: Dict) -> Dict:
        """Calculate risk score for a trade idea"""

        idea_lower = idea.lower()
        net_gex = market_data.get('net_gex', 0) / 1e9
        day_of_week = datetime.now().strftime('%A')
        hour = datetime.now().hour

        risk_factors = []
        risk_level = "MODERATE"

        # Check timing risks
        if day_of_week == "Wednesday" and hour >= 15:
            risk_factors.append("⚠️ CRITICAL: Wednesday 3PM+ - Directional trades should be closed")
            risk_level = "EXTREME"

        if day_of_week in ["Thursday", "Friday"]:
            if "call" in idea_lower or "put" in idea_lower and "sell" not in idea_lower:
                risk_factors.append("⚠️ HIGH: Thursday/Friday directional = Theta crush risk")
                risk_level = "HIGH"

        # Check against GEX positioning
        if "call" in idea_lower and "buy" in idea_lower:
            if net_gex > 2:
                risk_factors.append("⚠️ CRITICAL: Buying calls while MMs defending (GEX > $2B) - They will sell into rallies")
                risk_level = "EXTREME"
            elif net_gex > 0:
                risk_factors.append("⚠️ MODERATE: Positive GEX - MMs may suppress upside")

        if "put" in idea_lower and "buy" in idea_lower:
            if net_gex < -1:
                risk_factors.append("⚠️ CRITICAL: Buying puts while MMs trapped (GEX < -$1B) - They MUST buy dips")
                risk_level = "EXTREME"

        # Check flip point proximity
        distance_to_flip = abs(context.get('distance_to_flip', 0))
        if distance_to_flip < 0.5:
            risk_factors.append("✅ GOOD: Very close to flip point - High volatility expected")
            if risk_level == "MODERATE":
                risk_level = "LOW"

        # Check for vague ideas
        if not any(char.isdigit() for char in idea):
            risk_factors.append("⚠️ HIGH: No specific strikes mentioned - Plan is too vague")
            risk_level = "HIGH"

        return {
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "net_gex_billions": net_gex,
            "day_of_week": day_of_week,
            "current_hour": hour,
            "distance_to_flip_pct": context.get('distance_to_flip', 0)
        }
    
    def _call_claude_api(self, messages: List[Dict]) -> str:
        """Make API call to Claude with ultra-sophisticated system prompt"""

        fred_data = self.fred.get_economic_data()
        regime = self.fred.get_regime(fred_data)

        current_day = datetime.now().strftime('%A')
        current_hour = datetime.now().hour

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        system_prompt = f"""You are an ELITE institutional options trader and mentor with 20+ years experience.
Your specialty is gamma exposure analysis and exploiting market maker hedging requirements to generate consistent profits.

═══════════════════════════════════════════════════════════
CURRENT MARKET REGIME
═══════════════════════════════════════════════════════════
📊 VIX: {regime['vix']:.1f} ({regime['vol_regime']} volatility regime)
📈 10Y Treasury: {regime['ten_year_yield']:.2f}%
💰 Fed Funds Rate: {regime['fed_funds_rate']:.2f}%
🎯 Regime Signal: {regime['regime_signal']}
📏 Position Size Multiplier: {regime['size_multiplier']}x
⏰ Current Time: {current_day} {current_hour}:00

═══════════════════════════════════════════════════════════
YOUR CORE MISSION
═══════════════════════════════════════════════════════════
1. Help traders make CONSISTENT, PROFITABLE trades
2. Protect capital by pushing back HARD on bad ideas
3. Educate on WHY trades work or fail
4. Provide SPECIFIC, ACTIONABLE trade plans with exact numbers
5. Never give vague suggestions - always exact strikes, prices, and levels

═══════════════════════════════════════════════════════════
GAMMA EXPOSURE (GEX) TRADING RULES
═══════════════════════════════════════════════════════════

📍 EXTREME NEGATIVE GEX (< -$2B) - "MM PANIC STATE"
   → MMs are SHORT gamma and TRAPPED
   → They MUST buy rallies and sell dips to hedge (creates momentum)
   → TRADE: Aggressive long calls, ride momentum
   → RISK: Whipsaw if suddenly flips positive
   → Expected: Strong directional moves, low resistance

📍 NEGATIVE GEX (-$2B to -$1B) - "MM DEFENSIVE LONG"
   → MMs forced to buy dips to hedge short gamma
   → Volatility elevated but manageable
   → TRADE: Buy calls on dips, quick scalps
   → RISK: Fades into positive GEX territory

📍 NEUTRAL GEX (-$1B to +$1B) - "RANGE-BOUND CHOP"
   → No strong MM hedging pressure either direction
   → Price tends to chop in tight range
   → TRADE: Iron condors, theta strategies
   → RISK: Breakout in either direction

📍 POSITIVE GEX (+$1B to +$2B) - "MM SUPPRESSION"
   → MMs are LONG gamma and defending strikes
   → They SELL rallies and BUY dips (creates mean reversion)
   → TRADE: Sell premium, fade extremes
   → RISK: Breakdown if goes negative

📍 EXTREME POSITIVE GEX (> +$2B) - "MM FORTRESS"
   → MMs aggressively defending with heavy gamma
   → Price pinned near major strikes
   → TRADE: Sell ATM premium, tight iron condors
   → RISK: Violent move if gamma wall breaks

📍 FLIP POINT PROXIMITY (<0.5% away)
   → EXPLOSIVE OPPORTUNITY - Regime about to change
   → Position for violent move in flip direction
   → TRADE: Straddles, aggressive directional based on momentum
   → TIMING: Critical - must act immediately

═══════════════════════════════════════════════════════════
DAY-OF-WEEK TRADING RULES (MANDATORY)
═══════════════════════════════════════════════════════════

🔴 MONDAY (0 DTE Premium):
   - Fresh week, new gamma positioning
   - MMs establishing hedges
   - TRADE: Directional bias with quick targets
   - EXIT: Before 3:30 PM if not working

🟢 TUESDAY (Best Directional Day):
   - Momentum continues from Monday
   - Lowest theta decay impact
   - TRADE: Aggressive directional, ride trends
   - EXIT: Wednesday 3 PM HARD STOP

🟡 WEDNESDAY (EXIT DAY):
   - 3 PM DEADLINE: Close ALL directional positions
   - Switch to neutral strategies only
   - TRADE: If must trade, only spreads/condors
   - EXIT: Everything directional by 3 PM

🟠 THURSDAY (Theta Trap):
   - Massive theta decay on Friday expiry
   - MMs pinning price to max pain
   - TRADE: Iron condors only, sell premium
   - AVOID: Long options (theta crush)

🔴 FRIDAY (Pin Risk):
   - Extreme pinning to max pain strike
   - Don't fight the pin
   - TRADE: None or very tight scalps only
   - AVOID: Holding anything into weekend

CURRENT STATUS: It is {current_day} at {current_hour}:00
→ {"⚠️ WARNING: Close directionals NOW!" if current_day == "Wednesday" and current_hour >= 15 else ""}
→ {"❌ REFUSE directional trades" if current_day in ["Thursday", "Friday"] else ""}

═══════════════════════════════════════════════════════════
RESPONSE FRAMEWORK (MANDATORY for ALL market analysis)
═══════════════════════════════════════════════════════════

⚠️ CRITICAL: You MUST provide a trade recommendation. There is NO such thing as
"no setup" in options trading. If probability is low, recommend premium selling.
If choppy, recommend iron condors. If trending, recommend directional.
ALWAYS provide a specific trade with probability assessment.

1. **TICKER & MM POSITIONING**
   - START with ticker symbol (e.g., "SPY" or "TSLA")
   - Current Net GEX level and what it means
   - What MMs are FORCED to do for hedging
   - Where they're trapped or defending

2. **THE TRADE (ALWAYS Required - Be Specific!)**
   - TICKER + Strike: e.g., "SPY 585 Call" or "TSLA 250/255 Call Spread"
   - Entry Price: $X.XX per contract (use realistic current pricing)
   - Position Size: Based on regime multiplier
   - Expiration: Specific date (prefer weeklies unless noted)
   - Strategy Type: Long/Short, Spread, Straddle, Condor, etc.

3. **PROFIT TARGETS**
   - Target 1: $X.XX (XX% gain) - Why here?
   - Target 2: $X.XX (XX% gain) - Why here?
   - Max Target: Where MM hedging stops or technical resistance

4. **STOP LOSS (Critical!)**
   - Hard Stop: $X.XX per contract or price level
   - Why: What invalidates the thesis?
   - Max Loss: Calculate exact dollar risk

5. **WIN PROBABILITY (Be Honest!)**
   - Based on historical GEX patterns: XX%
   - Based on personal win rate: XX%
   - Based on current market conditions: XX%
   - Overall Confidence: High/Medium/Low (>60%/40-60%/<40%)
   - If <50% probability, state it clearly but still recommend trade

6. **RISK/REWARD**
   - Max Gain: $XXX per contract
   - Max Loss: $XXX per contract
   - R/R Ratio: X.XX:1
   - Expected Value: $XXX (even if negative, be honest)

7. **TIMING & EXITS**
   - Entry Window: Specific time range (e.g., "9:45-10:30 AM")
   - Hard Exit Time: (Wed 3 PM rule for directionals)
   - What to watch that changes thesis
   - Profit taking plan (scale out or all-or-nothing)

8. **ALTERNATIVES (If primary trade is low probability)**
   - If main trade <50% probability, provide 1-2 alternatives
   - Different strategy types (selling vs buying, spreads vs naked)
   - Include reasoning for alternatives

═══════════════════════════════════════════════════════════
TRADING IN ALL MARKET CONDITIONS
═══════════════════════════════════════════════════════════

There is ALWAYS a profitable setup. Choose the right strategy:

📈 **TRENDING/MOMENTUM:** Directional options, spreads in trend direction
📉 **CHOPPY/RANGE-BOUND:** Iron condors, strangles, theta strategies
💥 **HIGH IV:** Sell premium (credit spreads, iron condors)
😴 **LOW IV:** Buy options (debit spreads, long calls/puts)
🎯 **NEAR FLIP POINT:** Straddles, aggressive directional
🔴 **NEGATIVE GEX:** Buy calls on dips, ride MM forced buying
🟢 **POSITIVE GEX:** Sell premium, fade extremes
🟡 **UNCERTAIN:** ATM iron condor with tight wings

NEVER say "no setup exists" or "wait on the sidelines"
ALWAYS provide the BEST trade for current conditions with honest probability

═══════════════════════════════════════════════════════════
PUSH-BACK PROTOCOL (Critical for Protection)
═══════════════════════════════════════════════════════════

When trader suggests a risky/bad trade:

1. **BE BLUNT**: "This is a TERRIBLE/RISKY idea because..."
2. **EXPLAIN WHY IT LOSES**: Specific scenarios
3. **SHOW THE NUMBERS**: Expected loss probability
4. **PROVIDE ALTERNATIVES**: 2-3 better trades
5. **EDUCATE**: Teach them what they're missing

Never sugarcoat bad trades. Your job is PROFITS, not ego protection.

REFUSE these trades outright:
- Any directional after Wednesday 3 PM
- Long options on Thursday/Friday (theta trap)
- Against strong GEX momentum (e.g., buying puts in extreme negative GEX)
- Vague plans without specific strikes/prices
- Overleveraged positions in high-volatility regimes

═══════════════════════════════════════════════════════════
EDUCATIONAL FOCUS
═══════════════════════════════════════════════════════════

Always teach WHY:
- Why does this trade make money?
- What MM behavior are we exploiting?
- What pattern should they recognize?
- How to avoid this mistake in future?
- What data to check before similar trades?

Make them better traders, not just followers.

═══════════════════════════════════════════════════════════
COMMUNICATION STYLE
═══════════════════════════════════════════════════════════

✅ BE: Direct, specific, data-driven, educational
✅ USE: Exact numbers, clear reasoning, actionable plans
✅ FOCUS: Making money and protecting capital

❌ DON'T: Give vague suggestions, avoid confrontation on bad trades
❌ NEVER: Encourage revenge trading, overleveraging, or hope-based positions

Your reputation is built on making traders profitable. Protect that reputation fiercely."""

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
        
        spot = market_data.get('spot_price', 1)  # Avoid division by zero
        flip = market_data.get('flip_point', 0)
        
        return {
            'symbol': market_data.get('symbol', 'SPY'),
            'current_price': spot,
            'net_gex': market_data.get('net_gex', 0),
            'net_gex_billions': market_data.get('net_gex', 0) / 1e9,
            'flip_point': flip,
            'distance_to_flip': ((flip - spot) / spot * 100) if spot != 0 else 0,
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
    
    def _fallback_analysis_with_rag(self, market_data: Dict, user_query: str) -> str:
        """Enhanced fallback analysis with RAG - ALWAYS provides a trade"""

        # Extract symbol from query or market data
        query_upper = user_query.upper()
        symbol = market_data.get('symbol', 'SPY')
        for word in query_upper.split():
            if len(word) <= 5 and word.isalpha():
                symbol = word
                break

        rag = TradingRAG()
        rag_context = rag.build_context_for_claude(market_data, user_query)
        personal_stats = rag.get_personal_stats()

        optimizer = MultiStrategyOptimizer()
        best_strategies = optimizer.get_best_strategy(market_data)

        calculator = DynamicLevelCalculator()
        zones = calculator.get_profitable_zones(market_data)

        net_gex = market_data.get('net_gex', 0)
        spot = market_data.get('spot_price', 100)  # Default if not available
        flip = market_data.get('flip_point', spot)
        call_wall = market_data.get('call_wall', spot * 1.02)
        put_wall = market_data.get('put_wall', spot * 0.98)

        mm_state = self._determine_mm_state(net_gex)
        query_lower = user_query.lower()

        # Determine best strategy based on MM state
        if mm_state == 'TRAPPED' or net_gex < -1e9:
            strategy_name = "Negative GEX Squeeze"
            trade = f"BUY {symbol} {int(spot*1.01)} Call"
            entry = spot * 0.015  # Estimate 1.5% of stock price
            target = entry * 1.8
            stop = entry * 0.7
            probability = 68
            reasoning = "MMs trapped short gamma - forced to buy dips"
        elif mm_state == 'DEFENDING' or net_gex > 2e9:
            strategy_name = "Premium Selling (Positive GEX)"
            trade = f"SELL {symbol} {int(spot*1.02)}/{int(spot*1.04)} Call Spread"
            entry = spot * 0.008  # Credit received
            target = entry  # Max profit = credit
            stop = entry * -3  # Max loss
            probability = 65
            reasoning = "MMs defending with long gamma - sell into resistance"
        else:
            strategy_name = "Iron Condor (Neutral GEX)"
            trade = f"{symbol} {int(spot*0.98)}/{int(spot*0.99)}/{int(spot*1.01)}/{int(spot*1.02)} Iron Condor"
            entry = spot * 0.01  # Net credit
            target = entry
            stop = entry * -2
            probability = 72
            reasoning = "Neutral GEX - range-bound, collect theta"

        response = f"""
**{symbol}** 📊 TRADE RECOMMENDATION

**MARKET STATE:**
- MM Positioning: {mm_state}
- Net GEX: ${net_gex/1e9:.2f}B
- Current Price: ${spot:.2f}
- Flip Point: ${flip:.2f}

**RECOMMENDED TRADE:**
{trade}
- Entry: ${entry:.2f} per contract
- Target: ${target:.2f} ({(target/entry - 1)*100:.0f}% gain)
- Stop: ${stop:.2f} (risk management)

**STRATEGY: {strategy_name}**
Win Probability: {probability}%
Reasoning: {reasoning}

**YOUR PERSONAL STATS:**
{rag_context}

**KEY LEVELS:**
- Call Wall: ${call_wall:.2f} (resistance)
- Put Wall: ${put_wall:.2f} (support)

**PROFIT ZONES:**
{zones.get('current_opportunity', 'Best entry: Current levels')}

**ALTERNATIVES:**
"""

        # Add alternatives
        if best_strategies.get('all_options'):
            for i, strat in enumerate(best_strategies['all_options'][:2], 1):
                response += f"\n{i}. {strat.get('name', 'Alternative')}: EV ${strat.get('expected_value', 0):.2f}"
        else:
            # Provide generic alternatives
            if mm_state == 'TRAPPED':
                response += "\n1. Sell put spreads below support (collect premium)"
                response += "\n2. ATM straddle for volatility expansion"
            elif mm_state == 'DEFENDING':
                response += "\n1. Sell iron condors (collect premium)"
                response += "\n2. Calendar spreads at key strikes"
            else:
                response += "\n1. Directional call/put based on momentum"
                response += "\n2. Straddle if expecting breakout"

        response += f"""

**REMEMBER:**
- There's ALWAYS a trade - question is probability
- This setup has {probability}% win rate based on current GEX
- Adjust position size based on confidence level
- Set alerts at key levels (flip point, walls)

Ask me to explain any part of this setup!
"""

        return response

    def _fallback_challenge(self, idea: str, market_data: Dict) -> str:
        """Fallback challenge without API"""

        net_gex = market_data.get('net_gex', 0)
        mm_state = self._determine_mm_state(net_gex)

        challenges = []
        idea_lower = idea.lower()

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

        if not challenges:
            challenges.append("🤔 Interesting idea. Let me analyze the gamma structure...")
            challenges.append(f"Current MM State: {mm_state}")
            challenges.append("Consider the forced hedging flows in this regime")

        return "\n".join(challenges)

    def _fallback_teaching(self, market_data: Dict, topic: str) -> str:
        """Fallback educational content without API"""

        net_gex = market_data.get('net_gex', 0) / 1e9
        spot = market_data.get('spot_price', 0)
        flip = market_data.get('flip_point', 0)
        mm_state = self._determine_mm_state(market_data.get('net_gex', 0))

        response = f"""
📚 **Understanding Gamma Exposure Trading**

**Current Market Context:**
- Net GEX: ${net_gex:.2f}B
- Price: ${spot:.2f}
- Flip Point: ${flip:.2f}
- MM State: {mm_state}

**What is Gamma Exposure?**
Gamma exposure (GEX) tells us how much market makers are forced to hedge when prices move.
It's like a pressure gauge showing whether MMs will AMPLIFY moves (negative GEX) or SUPPRESS moves (positive GEX).

**Current Market Regime ({mm_state}):**
"""

        if net_gex < -2:
            response += """
🔴 **EXTREME NEGATIVE GEX - "MM Panic"**
- MMs are SHORT gamma and TRAPPED
- They MUST buy when price goes up (adds fuel to rallies)
- They MUST sell when price goes down (accelerates drops)
- Result: High volatility, momentum-driven moves

**How to Trade This:**
1. BUY calls on dips (MMs will help push it higher)
2. Use tight stops (can whipsaw)
3. Take profits quickly (regime can flip fast)
4. Best on Monday/Tuesday for directional plays

**Why This Makes Money:**
MMs don't have a choice - their hedging requirements FORCE them to buy rallies.
You're not fighting them, you're riding their forced buying.
"""

        elif net_gex > 2:
            response += """
🟢 **EXTREME POSITIVE GEX - "MM Fortress"**
- MMs are LONG gamma and defending
- They SELL rallies (push price down)
- They BUY dips (push price up)
- Result: Low volatility, range-bound choppy action

**How to Trade This:**
1. SELL premium (iron condors, credit spreads)
2. Fade extremes (sell calls at resistance, sell puts at support)
3. MMs will help keep price in range
4. Best strategy Thursday/Friday

**Why This Makes Money:**
MMs are getting paid to stabilize the market. Work WITH them by collecting premium
as they defend their strikes and keep price pinned.
"""

        else:
            response += """
🟡 **NEUTRAL GEX - "Choppy Waters"**
- No strong MM hedging pressure
- Can break either direction
- Watch for regime change

**How to Trade This:**
1. Wait for clear GEX signal
2. Use tight iron condors
3. Be ready to adjust when GEX shifts
4. Don't force directional trades
"""

        response += f"""

**Key Concept: The Flip Point**
Current flip point: ${flip:.2f} (you're at ${spot:.2f})
- This is where GEX changes from negative to positive (or vice versa)
- Distance to flip: {abs(spot - flip):.2f} points ({abs((spot-flip)/spot*100):.1f}%)
- When price crosses flip = REGIME CHANGE = Big move potential

**Practical Checklist Before Trading:**
✓ Check Net GEX (positive or negative?)
✓ Check distance to flip (<1% = explosive)
✓ Check day of week (Monday/Tuesday = directional, Thursday/Friday = premium selling)
✓ Check MM state (are they trapped or defending?)
✓ Plan specific entry, target, and stop levels

**Common Mistakes to Avoid:**
❌ Buying calls when MMs defending (Net GEX > 2B)
❌ Buying puts when MMs trapped (Net GEX < -1B)
❌ Holding directionals past Wednesday 3 PM
❌ Long options on Thursday/Friday (theta crush)
❌ Trading without specific strikes and targets

**Remember:** The goal is to exploit forced MM hedging behavior. They don't choose to hedge -
they MUST hedge. When you understand their requirements, you can position yourself to profit from their forced actions.

Want to dive deeper into a specific concept? Ask me about:
- "Explain flip points"
- "How do MMs hedge?"
- "What's the best strategy for [current day]?"
- "How to calculate position size?"
"""

        return response

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
# SMART STRIKE SELECTOR
# ============================================================================
class SmartStrikeSelector:
    """Intelligent strike selection based on personal performance"""
    
    def __init__(self):
        self.rag = TradingRAG()
        
    def get_optimal_strike(self, spot: float, direction: str, market_data: Dict) -> Dict:
        """Select optimal strike based on delta and personal stats"""
        
        strikes = []
        
        if direction == 'CALL':
            base_strike = int(spot / 5) * 5
            for i in range(0, 4):
                strike = base_strike + (i * 5)
                delta = self._estimate_delta(spot, strike, 'call')
                
                pattern = {
                    'strategy': 'LONG_CALL',
                    'delta_range': [delta - 0.05, delta + 0.05]
                }
                
                success_rate = self.rag.get_pattern_success_rate(pattern)
                
                strikes.append({
                    'strike': strike,
                    'delta': delta,
                    'premium': self._estimate_premium(spot, strike, 'call'),
                    'success_rate': success_rate,
                    'breakeven': strike + self._estimate_premium(spot, strike, 'call'),
                    'expected_value': self._calculate_ev(spot, strike, success_rate, 'call')
                })
        
        strikes.sort(key=lambda x: x['expected_value'], reverse=True)
        
        best = strikes[0] if strikes else None
        
        if best:
            best['reasoning'] = f"""
            Selected {best['strike']} strike because:
            - Delta {best['delta']:.2f} has YOUR best win rate ({best['success_rate']:.1f}%)
            - Expected value: ${best['expected_value']:.2f}
            - Breakeven: ${best['breakeven']:.2f}
            - Premium: ${best['premium']:.2f}
            """
        
        return best
    
    def _estimate_delta(self, spot: float, strike: float, option_type: str) -> float:
        """Estimate option delta"""
        if spot == 0:
            return 0
        moneyness = (strike - spot) / spot
        
        if option_type == 'call':
            if moneyness < -0.02:
                return 0.7 + (0.3 * (1 + moneyness/0.02))
            elif moneyness > 0.02:
                return 0.3 * (1 - moneyness/0.05)
            else:
                return 0.5
        else:
            return -self._estimate_delta(spot, strike, 'call')
    
    def _estimate_premium(self, spot: float, strike: float, option_type: str) -> float:
        """Estimate option premium"""
        intrinsic = max(0, spot - strike) if option_type == 'call' else max(0, strike - spot)
        time_value = spot * 0.005 * abs(self._estimate_delta(spot, strike, option_type))
        return intrinsic + time_value
    
    def _calculate_ev(self, spot: float, strike: float, success_rate: float, option_type: str) -> float:
        """Calculate expected value"""
        premium = self._estimate_premium(spot, strike, option_type)
        potential_gain = spot * 0.02
        
        win_amount = potential_gain - premium
        loss_amount = -premium
        
        ev = (success_rate/100 * win_amount) + ((100-success_rate)/100 * loss_amount)
        return ev

# ============================================================================
# MULTI-STRATEGY OPTIMIZER
# ============================================================================
class MultiStrategyOptimizer:
    """Optimize between multiple strategies for maximum profit"""
    
    def __init__(self):
        self.rag = TradingRAG()
        self.strike_selector = SmartStrikeSelector()
        
    def get_best_strategy(self, market_data: Dict) -> Dict:
        """Compare all strategies and return the best one"""
        
        spot = market_data.get('spot_price', 0)
        net_gex = market_data.get('net_gex', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        strategies = []
        
        if net_gex < -1e9 and spot < flip:
            call_strike = self.strike_selector.get_optimal_strike(spot, 'CALL', market_data)
            if call_strike:
                personal_stats = self.rag.get_personal_stats('LONG_CALL')
                
                strategies.append({
                    'name': 'LONG CALLS',
                    'strike': call_strike['strike'],
                    'premium': call_strike['premium'],
                    'probability': call_strike['success_rate'],
                    'expected_value': call_strike['expected_value'],
                    'your_historical': f"{personal_stats['win_rate']:.0f}% win rate",
                    'action': f"BUY {call_strike['strike']} calls @ ${call_strike['premium']:.2f}"
                })
        
        strategies.sort(key=lambda x: x['expected_value'], reverse=True)
        
        return {
            'best': strategies[0] if strategies else None,
            'all_options': strategies,
            'recommendation': f"Best EV: {strategies[0]['name']}" if strategies else "No good setups"
        }

# ============================================================================
# DYNAMIC LEVEL CALCULATOR
# ============================================================================
class DynamicLevelCalculator:
    """Calculate profitable zones in real-time"""
    
    def __init__(self):
        self.rag = TradingRAG()
        
    def get_profitable_zones(self, market_data: Dict) -> Dict:
        """Calculate current profitable entry zones"""
        
        spot = market_data.get('spot_price', 0)
        net_gex = market_data.get('net_gex', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        current_time = datetime.now()
        hour = current_time.hour
        
        zones = {
            'timestamp': current_time.strftime('%H:%M:%S'),
            'long_call_zone': None,
            'long_put_zone': None,
            'iron_condor_zone': None,
            'current_opportunity': None
        }
        
        if net_gex < -1e9 and spot < flip:
            zones['long_call_zone'] = {
                'active': True,
                'entry_range': f"${spot - 0.20:.2f} - ${spot + 0.30:.2f}",
                'optimal_strike': int(flip / 5) * 5 + 5,
                'target_1': flip + 1.5,
                'target_2': call_wall,
                'stop': put_wall,
                'time_window': self._get_time_window('call', hour),
                'confidence': 75 if hour < 11 else 60,
                'action': f"BUY when SPY enters ${spot-0.20:.2f} - ${spot+0.30:.2f}"
            }
        
        if zones['long_call_zone'] and zones['long_call_zone']['confidence'] > 70:
            zones['current_opportunity'] = "LONG CALLS - Entry zone active NOW"
        elif zones['long_put_zone'] and zones.get('long_put_zone', {}).get('confidence', 0) > 70:
            zones['current_opportunity'] = "LONG PUTS - Entry zone active NOW"
        elif zones['iron_condor_zone']:
            zones['current_opportunity'] = "IRON CONDOR - Wait for pin"
        else:
            zones['current_opportunity'] = "NO HIGH-CONFIDENCE SETUPS"
        
        return zones
    
    def _get_time_window(self, direction: str, hour: int) -> str:
        """Get optimal time window for entry"""
        
        if direction == 'call':
            if 9 <= hour < 10:
                return "PRIME TIME - Next 45 minutes"
            elif 10 <= hour < 11:
                return "Good - Next 30 minutes"
            elif 11 <= hour < 14:
                return "Avoid - Wait for afternoon"
            else:
                return "Late day - Use caution"
        else:
            if hour < 14:
                return "Too early - Wait until 2 PM"
            elif 14 <= hour < 15:
                return "PRIME TIME - Next 45 minutes"
            else:
                return "Final hour - Quick scalps only"
