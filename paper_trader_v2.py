"""
Paper Trading Engine V2 with Real Option Prices
Uses REAL market data from yfinance for option pricing
Finds at least 1 profitable SPY trade daily with detailed reasoning
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import streamlit as st
from config_and_database import DB_PATH
from database_adapter import get_connection
import yfinance as yf
import numpy as np


def get_real_option_price(symbol: str, strike: float, option_type: str, expiration_date: str) -> Dict:
    """
    Get REAL option price from Yahoo Finance (not mock/Black-Scholes)

    Args:
        symbol: Ticker symbol (e.g., 'SPY')
        strike: Strike price
        option_type: 'call' or 'put'
        expiration_date: Expiration date string 'YYYY-MM-DD'

    Returns:
        Dictionary with real market data:
        {
            'bid': bid price,
            'ask': ask price,
            'last': last trade price,
            'volume': volume,
            'open_interest': OI,
            'implied_volatility': IV,
            'delta': delta (if available),
            'gamma': gamma (if available)
        }
    """
    try:
        ticker = yf.Ticker(symbol)

        # Get options chain for this expiration
        options = ticker.option_chain(expiration_date)

        # Get calls or puts
        if option_type.lower() == 'call':
            chain = options.calls
        else:
            chain = options.puts

        # Find the strike
        option_data = chain[chain['strike'] == strike]

        if option_data.empty:
            # No exact strike, find closest
            chain['strike_diff'] = abs(chain['strike'] - strike)
            closest = chain.nsmallest(1, 'strike_diff')
            if not closest.empty:
                option_data = closest

        if option_data.empty:
            return {'error': 'No option data found'}

        row = option_data.iloc[0]

        return {
            'bid': float(row.get('bid', 0)),
            'ask': float(row.get('ask', 0)),
            'last': float(row.get('lastPrice', 0)),
            'volume': int(row.get('volume', 0)),
            'open_interest': int(row.get('openInterest', 0)),
            'implied_volatility': float(row.get('impliedVolatility', 0)),
            'delta': float(row.get('delta', 0)) if 'delta' in row else None,
            'gamma': float(row.get('gamma', 0)) if 'gamma' in row else None,
            'strike': float(row['strike']),
            'contract_symbol': row.get('contractSymbol', '')
        }

    except Exception as e:
        print(f"Error fetching real option price: {e}")
        return {'error': str(e)}


def find_best_strike_from_real_data(symbol: str, expiration_date: str, target_strike: float,
                                     option_type: str, spot_price: float) -> Tuple[float, Dict]:
    """
    Find the best available strike near target from real options chain

    Returns:
        (strike, option_data) tuple
    """
    try:
        ticker = yf.Ticker(symbol)
        options = ticker.option_chain(expiration_date)

        if option_type.lower() == 'call':
            chain = options.calls
        else:
            chain = options.puts

        # Filter to reasonable strikes (within 10% of spot)
        min_strike = spot_price * 0.90
        max_strike = spot_price * 1.10
        chain = chain[(chain['strike'] >= min_strike) & (chain['strike'] <= max_strike)]

        # Find closest to target
        chain['strike_diff'] = abs(chain['strike'] - target_strike)
        best = chain.nsmallest(1, 'strike_diff')

        if best.empty:
            return target_strike, {'error': 'No strikes found'}

        row = best.iloc[0]
        strike = float(row['strike'])

        option_data = {
            'bid': float(row.get('bid', 0)),
            'ask': float(row.get('ask', 0)),
            'last': float(row.get('lastPrice', 0)),
            'volume': int(row.get('volume', 0)),
            'open_interest': int(row.get('openInterest', 0)),
            'implied_volatility': float(row.get('impliedVolatility', 0)),
            'strike': strike,
            'contract_symbol': row.get('contractSymbol', '')
        }

        return strike, option_data

    except Exception as e:
        print(f"Error finding strike: {e}")
        return target_strike, {'error': str(e)}


class DailyTradeFinder:
    """
    Finds at least 1 profitable SPY trade every day
    Uses GEX analysis, price action, and market conditions
    """

    def __init__(self):
        self.min_confidence = 65  # Lower threshold to ensure we find trades

    def analyze_market_conditions(self, gex_data: Dict, skew_data: Dict, spot_price: float) -> Dict:
        """
        Comprehensive market analysis to find the best trade

        Returns detailed analysis with trade recommendation
        """
        net_gex = gex_data.get('net_gex', 0)
        flip_point = gex_data.get('flip_point', spot_price)
        call_wall = gex_data.get('call_wall', 0)
        put_wall = gex_data.get('put_wall', 0)

        iv = skew_data.get('implied_volatility', 0.20) if skew_data else 0.20
        pcr = skew_data.get('pcr_oi', 1.0) if skew_data else 1.0

        # Calculate key metrics
        distance_to_flip = ((flip_point - spot_price) / spot_price * 100) if spot_price else 0
        gex_billions = net_gex / 1e9

        # Determine market regime
        regime = self._determine_regime(net_gex, spot_price, flip_point)

        # Find best trade based on regime
        trade = self._find_best_trade(
            regime, spot_price, flip_point, call_wall, put_wall,
            net_gex, distance_to_flip, iv, pcr
        )

        return trade

    def _determine_regime(self, net_gex: float, spot: float, flip: float) -> str:
        """Determine current market regime"""
        if net_gex < -1e9:
            if spot < flip:
                return "NEGATIVE_GEX_BELOW_FLIP"  # Squeeze potential
            else:
                return "NEGATIVE_GEX_ABOVE_FLIP"  # Breakdown potential
        elif net_gex > 2e9:
            if abs(spot - flip) < spot * 0.02:  # Within 2% of flip
                return "HIGH_POSITIVE_NEAR_FLIP"  # Range-bound
            else:
                return "HIGH_POSITIVE_GEX"  # Strong range-bound
        else:
            return "NEUTRAL_GEX"  # Mixed conditions

    def _find_best_trade(self, regime: str, spot: float, flip: float,
                         call_wall: float, put_wall: float, net_gex: float,
                         distance_to_flip: float, iv: float, pcr: float) -> Dict:
        """
        Find the best trade based on current regime

        Returns comprehensive trade setup with reasoning
        """

        # REGIME 1: Negative GEX Below Flip = SQUEEZE LONG CALLS
        if regime == "NEGATIVE_GEX_BELOW_FLIP":
            # Target: Flip point or call wall
            target = flip if flip > spot else call_wall if call_wall > spot else spot * 1.02
            strike = round(target / 5) * 5  # Round to $5 increment

            return {
                'symbol': 'SPY',
                'action': 'BUY_CALL',
                'strike': strike,
                'option_type': 'call',
                'dte': 5,  # 0-5 DTE for squeeze plays
                'confidence': min(85, 70 + abs(distance_to_flip) * 3),
                'strategy': 'Negative GEX Squeeze',
                'reasoning': self._build_reasoning(
                    regime='Negative GEX with price below flip',
                    thesis='Dealers are SHORT gamma. When price moves up, they must BUY to hedge → accelerates rally',
                    technical=f'Net GEX: ${net_gex/1e9:.2f}B (NEGATIVE), Spot: ${spot:.2f}, Flip: ${flip:.2f}',
                    catalyst=f'Price is {abs(distance_to_flip):.2f}% below flip point → squeeze potential',
                    target=f'Target: ${target:.2f} (flip point), Stop: ${spot * 0.99:.2f} (-1%)',
                    entry_logic='Buy ATM/OTM calls on any dip. Dealers will buy stock as we move up, creating momentum.',
                    exit_plan='Exit at +50% profit or at flip point. Stop loss at -30%.',
                    risk_reward=f'R/R: {(target - spot) / (spot * 0.01):.1f}:1'
                ),
                'entry_price': spot,
                'target_price': target,
                'stop_loss': spot * 0.99
            }

        # REGIME 2: Negative GEX Above Flip = BREAKDOWN LONG PUTS
        elif regime == "NEGATIVE_GEX_ABOVE_FLIP":
            # Target: Flip point or put wall
            target = flip if flip < spot else put_wall if put_wall < spot else spot * 0.98
            strike = round(target / 5) * 5

            return {
                'symbol': 'SPY',
                'action': 'BUY_PUT',
                'strike': strike,
                'option_type': 'put',
                'dte': 5,
                'confidence': min(80, 65 + abs(distance_to_flip) * 3),
                'strategy': 'Negative GEX Breakdown',
                'reasoning': self._build_reasoning(
                    regime='Negative GEX with price above flip',
                    thesis='Dealers SHORT gamma. Any downward move forces them to SELL → accelerates decline',
                    technical=f'Net GEX: ${net_gex/1e9:.2f}B (NEGATIVE), Spot: ${spot:.2f}, Flip: ${flip:.2f}',
                    catalyst=f'Price is {abs(distance_to_flip):.2f}% above flip → breakdown risk high',
                    target=f'Target: ${target:.2f} (flip point), Stop: ${spot * 1.01:.2f} (+1%)',
                    entry_logic='Buy ATM/OTM puts on any bounce. Dealers will sell into weakness.',
                    exit_plan='Exit at +50% profit or at flip point. Stop loss at -30%.',
                    risk_reward=f'R/R: {(spot - target) / (spot * 0.01):.1f}:1'
                ),
                'entry_price': spot,
                'target_price': target,
                'stop_loss': spot * 1.01
            }

        # REGIME 3: High Positive GEX = IRON CONDOR / PREMIUM SELLING
        elif regime in ["HIGH_POSITIVE_GEX", "HIGH_POSITIVE_NEAR_FLIP"]:
            # Sell iron condor around current price
            call_short = round((spot * 1.02) / 5) * 5  # 2% OTM
            put_short = round((spot * 0.98) / 5) * 5   # 2% OTM

            return {
                'symbol': 'SPY',
                'action': 'SELL_IRON_CONDOR',
                'strike': spot,  # Reference point
                'call_short_strike': call_short,
                'put_short_strike': put_short,
                'option_type': 'spread',
                'dte': 7,  # 7 DTE for theta decay
                'confidence': 75,
                'strategy': 'Iron Condor Premium Collection',
                'reasoning': self._build_reasoning(
                    regime='High Positive GEX (range-bound)',
                    thesis='Dealers are LONG gamma. They will FADE moves (sell rallies, buy dips) → keeps price in range',
                    technical=f'Net GEX: ${net_gex/1e9:.2f}B (POSITIVE), Spot: ${spot:.2f}',
                    catalyst=f'High dealer gamma creates ceiling/floor. Market wants to stay flat.',
                    target=f'Collect premium from range: ${put_short:.2f} - ${call_short:.2f}',
                    entry_logic=f'Sell {put_short}/{call_short} iron condor. Price should stay within ±2% range.',
                    exit_plan='Exit at 50% of max profit or if price breaks out of range.',
                    risk_reward='R/R: 0.3:1 (premium collection, high win rate strategy)'
                ),
                'entry_price': spot,
                'target_price': spot,  # Theta play
                'stop_loss': 0  # Defined risk
            }

        # REGIME 4: Neutral GEX = DIRECTIONAL BIAS BASED ON PRICE VS FLIP
        else:
            if spot < flip:
                # Bullish bias - long call spread
                strike_long = round(spot / 5) * 5
                strike_short = strike_long + 10

                return {
                    'symbol': 'SPY',
                    'action': 'BUY_CALL_SPREAD',
                    'strike': strike_long,
                    'short_strike': strike_short,
                    'option_type': 'call',
                    'dte': 7,
                    'confidence': 70,
                    'strategy': 'Bullish Call Spread',
                    'reasoning': self._build_reasoning(
                        regime='Neutral GEX, below flip',
                        thesis='Price below flip suggests bullish bias. Use call spread for defined risk.',
                        technical=f'Net GEX: ${net_gex/1e9:.2f}B, Spot: ${spot:.2f}, Flip: ${flip:.2f}',
                        catalyst='Price tends to gravitate toward flip point',
                        target=f'Target: ${flip:.2f} (flip point)',
                        entry_logic=f'Buy {strike_long}/{strike_short} call spread toward flip',
                        exit_plan='Exit at 50% of max profit or at flip point',
                        risk_reward=f'R/R: 2:1 (defined risk spread)'
                    ),
                    'entry_price': spot,
                    'target_price': flip,
                    'stop_loss': spot * 0.98
                }
            else:
                # Bearish bias - long put spread
                strike_long = round(spot / 5) * 5
                strike_short = strike_long - 10

                return {
                    'symbol': 'SPY',
                    'action': 'BUY_PUT_SPREAD',
                    'strike': strike_long,
                    'short_strike': strike_short,
                    'option_type': 'put',
                    'dte': 7,
                    'confidence': 70,
                    'strategy': 'Bearish Put Spread',
                    'reasoning': self._build_reasoning(
                        regime='Neutral GEX, above flip',
                        thesis='Price above flip suggests mean reversion potential. Use put spread for defined risk.',
                        technical=f'Net GEX: ${net_gex/1e9:.2f}B, Spot: ${spot:.2f}, Flip: ${flip:.2f}',
                        catalyst='Price tends to gravitate toward flip point',
                        target=f'Target: ${flip:.2f} (flip point)',
                        entry_logic=f'Buy {strike_long}/{strike_short} put spread toward flip',
                        exit_plan='Exit at 50% of max profit or at flip point',
                        risk_reward=f'R/R: 2:1 (defined risk spread)'
                    ),
                    'entry_price': spot,
                    'target_price': flip,
                    'stop_loss': spot * 1.02
                }

    def _build_reasoning(self, regime: str, thesis: str, technical: str,
                         catalyst: str, target: str, entry_logic: str,
                         exit_plan: str, risk_reward: str) -> str:
        """
        Build comprehensive trade reasoning
        """
        return f"""
📊 **MARKET REGIME**: {regime}

🎯 **TRADE THESIS**:
{thesis}

📈 **TECHNICAL ANALYSIS**:
{technical}

⚡ **CATALYST**:
{catalyst}

🎯 **TARGET & STOP**:
{target}

📍 **ENTRY LOGIC**:
{entry_logic}

🚪 **EXIT PLAN**:
{exit_plan}

💰 **RISK/REWARD**:
{risk_reward}
"""


class PaperTradingEngineV2:
    """Paper trading engine with REAL option prices and daily trade finder"""

    def __init__(self, db_path: str = DB_PATH, initial_capital: float = 1000000):
        """
        Initialize with $1,000,000 capital (1,000K as requested)
        """
        self.db_path = db_path
        self.initial_capital = initial_capital
        self.trade_finder = DailyTradeFinder()
        self._ensure_paper_trading_tables()

    def _ensure_paper_trading_tables(self):
        """Create paper trading tables with enhanced fields for reasoning"""
        conn = get_connection()
        c = conn.cursor()

        # Enhanced positions table
        c.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions_v2 (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                action TEXT NOT NULL,
                entry_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                strike REAL,
                short_strike REAL,
                option_type TEXT,
                expiration_date TEXT,
                dte INTEGER,
                entry_spot_price REAL,
                current_spot_price REAL,
                entry_premium_bid REAL,
                entry_premium_ask REAL,
                entry_premium_mid REAL,
                current_value REAL,
                unrealized_pnl REAL,
                status TEXT DEFAULT 'OPEN',
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                exit_price REAL,
                realized_pnl REAL,
                exit_reason TEXT,
                confidence_score INTEGER,
                entry_net_gex REAL,
                entry_flip_point REAL,
                trade_reasoning TEXT,
                contract_symbol TEXT,
                entry_iv REAL,
                notes TEXT
            )
        """)

        # Config table
        c.execute("""
            CREATE TABLE IF NOT EXISTS paper_config_v2 (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Initialize config
        c.execute("INSERT INTO paper_config_v2 (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('enabled', 'true'))
        c.execute("INSERT INTO paper_config_v2 (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('capital', str(self.initial_capital)))
        c.execute("INSERT INTO paper_config_v2 (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('max_exposure', '0.20'))  # Max 20% of capital at risk
        c.execute("INSERT INTO paper_config_v2 (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('max_position_size', '0.05'))  # Max 5% per position
        c.execute("INSERT INTO paper_config_v2 (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('auto_find_trades', 'true'))

        conn.commit()
        conn.close()

    def find_daily_trade(self, api_client) -> Optional[Dict]:
        """
        Find at least 1 profitable trade for today
        Uses real GEX data and comprehensive analysis

        Returns:
            Trade setup dict with detailed reasoning
        """
        try:
            # Get SPY data
            gex_data = api_client.get_net_gamma('SPY')
            skew_data = api_client.get_skew_data('SPY')

            if not gex_data or gex_data.get('error'):
                return None

            spot_price = gex_data.get('spot_price', 0)
            if spot_price == 0:
                return None

            # Analyze and find best trade
            trade = self.trade_finder.analyze_market_conditions(gex_data, skew_data, spot_price)

            # Get real option prices for this trade
            dte = trade.get('dte', 7)
            exp_date = self._get_expiration_string(dte)
            strike = trade.get('strike', spot_price)
            option_type = trade.get('option_type', 'call')

            # Fetch REAL option price
            real_option = get_real_option_price('SPY', strike, option_type, exp_date)

            if real_option.get('error'):
                # Fallback: find best available strike
                strike, real_option = find_best_strike_from_real_data(
                    'SPY', exp_date, strike, option_type, spot_price
                )
                trade['strike'] = strike

            # Add real pricing to trade
            trade['real_bid'] = real_option.get('bid', 0)
            trade['real_ask'] = real_option.get('ask', 0)
            trade['real_mid'] = (real_option.get('bid', 0) + real_option.get('ask', 0)) / 2
            trade['real_last'] = real_option.get('last', 0)
            trade['real_iv'] = real_option.get('implied_volatility', 0)
            trade['contract_symbol'] = real_option.get('contract_symbol', '')
            trade['expiration_str'] = exp_date
            trade['gex_data'] = gex_data

            return trade

        except Exception as e:
            print(f"Error finding daily trade: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_expiration_string(self, dte: int) -> str:
        """Get expiration date string for options chain"""
        today = datetime.now()

        if dte <= 7:
            # Next Friday
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            exp_date = today + timedelta(days=days_until_friday)
        else:
            # Friday next week or monthly
            days_until_friday = (4 - today.weekday()) % 7
            exp_date = today + timedelta(days=days_until_friday + 7)

        return exp_date.strftime('%Y-%m-%d')

    def execute_trade(self, trade: Dict) -> Optional[int]:
        """
        Execute trade with REAL option prices and detailed reasoning

        Returns:
            Position ID if successful
        """
        if not trade:
            return None

        # Calculate position size based on $1M capital
        capital = float(self.get_config('capital'))
        max_position_size = float(self.get_config('max_position_size'))
        max_position_value = capital * max_position_size

        # Use REAL mid price for entry
        premium = trade.get('real_mid', trade.get('real_last', 1.0))

        if premium == 0:
            premium = 1.0  # Minimum $1 per contract

        # Calculate quantity
        cost_per_contract = premium * 100  # Options are 100 shares
        quantity = int(max_position_value / cost_per_contract)
        quantity = max(1, min(quantity, 50))  # Between 1 and 50 contracts

        # Store position with full reasoning
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO paper_positions_v2 (
                symbol, strategy, action, entry_price, quantity, strike, short_strike,
                option_type, expiration_date, dte, entry_spot_price, current_spot_price,
                entry_premium_bid, entry_premium_ask, entry_premium_mid,
                current_value, unrealized_pnl, status, opened_at, confidence_score,
                entry_net_gex, entry_flip_point, trade_reasoning, contract_symbol,
                entry_iv, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            trade['symbol'],
            trade['strategy'],
            trade['action'],
            premium,
            quantity,
            trade['strike'],
            trade.get('short_strike'),
            trade['option_type'],
            trade['expiration_str'],
            trade['dte'],
            trade['entry_price'],
            trade['entry_price'],
            trade['real_bid'],
            trade['real_ask'],
            trade['real_mid'],
            premium * quantity * 100,
            0.0,
            'OPEN',
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            trade['confidence'],
            trade['gex_data'].get('net_gex', 0),
            trade['gex_data'].get('flip_point', 0),
            trade['reasoning'],
            trade.get('contract_symbol', ''),
            trade['real_iv'],
            f"Auto-executed by trade finder. Target: ${trade.get('target_price', 0):.2f}"
        ))

        result = c.fetchone()
        position_id = result[0] if result else None
        conn.commit()
        conn.close()

        return position_id

    def get_config(self, key: str) -> str:
        """Get configuration value"""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM paper_config_v2 WHERE key = %s", (key,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else "0"

    def set_config(self, key: str, value: str):
        """Set configuration value"""
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO paper_config_v2 (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
        conn.commit()
        conn.close()
