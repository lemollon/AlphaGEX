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
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

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
    """Advanced AI integration for market analysis"""
    
    def __init__(self):
        self.api_key = st.secrets.get("claude_api_key", "")
        self.model = "claude-3-5-sonnet-20241022"
        self.conversation_history = []
        self.fred = FREDIntegration()
        
        if not self.api_key:
            st.warning("Claude API key not found in secrets. Using fallback analysis.")
    
    def analyze_market(self, market_data: Dict, user_query: str) -> str:
        """Generate intelligent market analysis with RAG context"""
        
        if not self.api_key:
            return self._fallback_analysis_with_rag(market_data, user_query)
        
        context = self._build_context(market_data)
        
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
            Current Market Data:
            {json.dumps(context, indent=2)}
            
            YOUR PERSONAL TRADING HISTORY:
            {rag_context}
            
            BEST STRATEGIES RIGHT NOW:
            {json.dumps(best_strategies, indent=2)}
            
            PROFITABLE ZONES:
            {json.dumps(zones, indent=2)}
            
            User's Specific Question: {user_query}
            
            IMPORTANT: 
            1. Answer with SPECIFIC strikes, prices, and times
            2. Reference the user's ACTUAL trading history
            3. Give exact entry/exit levels
            4. Include personal win rates
            5. Be aggressive about profit opportunities
            6. If data shows a pattern, STATE IT CLEARLY
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
        
        fred_data = self.fred.get_economic_data()
        regime = self.fred.get_regime(fred_data)
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
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
        """Enhanced fallback analysis with RAG that actually answers the question"""
        
        rag = TradingRAG()
        rag_context = rag.build_context_for_claude(market_data, user_query)
        personal_stats = rag.get_personal_stats()
        
        optimizer = MultiStrategyOptimizer()
        best_strategies = optimizer.get_best_strategy(market_data)
        
        calculator = DynamicLevelCalculator()
        zones = calculator.get_profitable_zones(market_data)
        
        net_gex = market_data.get('net_gex', 0)
        spot = market_data.get('spot_price', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        mm_state = self._determine_mm_state(net_gex)
        query_lower = user_query.lower()
        
        if "what" in query_lower and "trade" in query_lower:
            if best_strategies['best']:
                best = best_strategies['best']
                response = f"""
📊 **SPECIFIC TRADE RECOMMENDATION**

Based on current GEX of ${net_gex/1e9:.1f}B and YOUR trading history:

**BEST TRADE: {best['name']}**
{best['action']}

**YOUR PERSONAL STATS:**
{rag_context}

**Why THIS Trade:**
- Expected Value: ${best['expected_value']:.2f}
- YOUR Success Rate: {best['probability']:.1f}%
- Historical Performance: {best['your_historical']}
- Premium: ${best['premium']:.2f}

**Profitable Entry Zone:**
{zones['current_opportunity']}

**Alternative Options:**
"""
                for i, strategy in enumerate(best_strategies.get('all_options', [])[1:3], 1):
                    response += f"\n{i+1}. {strategy['name']}: EV ${strategy['expected_value']:.2f}"
                
                return response
            else:
                return "❌ No high-probability setups right now. Wait for better entry."
        
        return f"""
📊 **Personalized Market Analysis**

**Current State: {mm_state}**
- Net GEX: ${net_gex/1e9:.2f}B
- Key Levels: Flip ${flip:.2f}, Calls ${call_wall:.2f}, Puts ${put_wall:.2f}

**YOUR TRADING HISTORY:**
{rag_context}

**BEST OPPORTUNITY NOW:**
{best_strategies.get('recommendation', 'Wait for setup')}

Ask me specific questions about YOUR performance!
"""
    
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
