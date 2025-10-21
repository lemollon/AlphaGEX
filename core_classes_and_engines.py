# core_classes_and_engines.py
"""
Core Classes and Engines for AlphaGEX Trading System
Handles GEX calculations, data fetching, and trading strategy logic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import yfinance as yf
from typing import Dict, List, Tuple, Optional
import requests
from scipy import stats
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

# Explicit exports for import clarity
__all__ = [
    'GEXLevel',
    'TradeSetup',
    'OptionsDataFetcher',
    'GEXAnalyzer',
    'TradingStrategy',
    'MarketRegimeAnalyzer',
    'RiskManager',
    'TradingVolatilityAPI',
    'MonteCarloEngine',
    'BlackScholesPricer'
]


@dataclass
class GEXLevel:
    """Data class for important GEX levels"""
    strike: float
    gex_value: float
    level_type: str  # 'call_wall', 'put_wall', 'gamma_flip'
    strength: float  # Percentage of total gamma at this level
    distance_from_spot: float  # Percentage distance


@dataclass
class TradeSetup:
    """Data class for trade setups"""
    strategy_type: str
    action: str
    entry_price: float
    target_price: float
    stop_loss: float
    confidence_score: float
    risk_reward_ratio: float
    expiration: str
    strike: float
    notes: str


class OptionsDataFetcher:
    """
    Fetches and processes options data from Yahoo Finance
    Handles multiple expirations and calculates Greeks
    """
    
    def __init__(self, symbol: str = 'SPY'):
        self.symbol = symbol.upper()
        self.ticker = yf.Ticker(self.symbol)
        self.spot_price = None
        self.risk_free_rate = 0.045  # Current approximate risk-free rate
        self.options_chain = None
        self.raw_data_cache = {}
        
    def get_spot_price(self) -> float:
        """Fetch current spot price"""
        try:
            # Get intraday data for more recent price
            data = self.ticker.history(period="1d", interval="1m")
            if not data.empty:
                self.spot_price = float(data['Close'].iloc[-1])
            else:
                # Fallback to daily data
                data = self.ticker.history(period="5d")
                self.spot_price = float(data['Close'].iloc[-1])
            return self.spot_price
        except Exception as e:
            print(f"Error fetching spot price: {e}")
            # Return last known price or default
            return self.spot_price if self.spot_price else 100.0
    
    def calculate_greeks(self, option_data: pd.DataFrame, spot: float = None) -> pd.DataFrame:
        """
        Calculate Greeks for options
        Simplified calculation - in production, use proper Black-Scholes
        """
        if spot is None:
            spot = self.spot_price
            
        option_data = option_data.copy()
        
        # Calculate moneyness
        option_data['moneyness'] = option_data['strike'] / spot
        
        # Simplified gamma calculation based on moneyness and DTE
        # Gamma is highest ATM and decreases as we move away
        for idx, row in option_data.iterrows():
            strike = row['strike']
            dte = row.get('dte', 5)
            iv = row.get('impliedVolatility', 0.20)
            
            # Distance from ATM
            atm_distance = abs(1 - row['moneyness'])
            
            # Simplified gamma: highest at ATM, decreases with distance
            # Also decreases with time (gamma is highest near expiration)
            base_gamma = 0.05 * np.exp(-atm_distance * 10)  # Peak at ATM
            time_factor = 1 / np.sqrt(max(dte, 0.5))  # Increases as expiration approaches
            vol_factor = 1 / max(iv, 0.1)  # Higher vol = lower gamma
            
            gamma = base_gamma * time_factor * vol_factor * 0.01  # Scale down
            option_data.at[idx, 'gamma'] = gamma
            
            # Calculate other Greeks (simplified)
            if row.get('optionType') == 'call':
                delta = 0.5 + 0.5 * stats.norm.cdf((np.log(spot/strike) + 0.5*iv**2*dte/365) / (iv*np.sqrt(dte/365)))
            else:
                delta = -0.5 + 0.5 * stats.norm.cdf((np.log(spot/strike) + 0.5*iv**2*dte/365) / (iv*np.sqrt(dte/365)))
            
            option_data.at[idx, 'delta'] = delta
            option_data.at[idx, 'theta'] = -0.01 * gamma * spot * iv  # Simplified theta
            option_data.at[idx, 'vega'] = 0.01 * gamma * spot * np.sqrt(dte/365)  # Simplified vega
        
        return option_data
    
    def get_options_chain(self, days_to_expiry: int = 30) -> pd.DataFrame:
        """
        Fetch complete options chain with Greeks
        """
        try:
            # Update spot price first
            self.get_spot_price()
            
            # Get available expiration dates
            expirations = self.ticker.options
            
            # Filter expirations within our timeframe
            target_date = datetime.now(pytz.UTC) + timedelta(days=days_to_expiry)
            valid_expirations = []
            
            for exp_str in expirations:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d')
                if exp_date <= target_date:
                    valid_expirations.append(exp_str)
            
            # Limit to first 5 expirations for performance
            valid_expirations = valid_expirations[:5] if len(valid_expirations) > 5 else valid_expirations
            
            all_options = []
            
            for exp in valid_expirations:
                try:
                    # Cache key
                    cache_key = f"{self.symbol}_{exp}"
                    
                    # Get options chain
                    options = self.ticker.option_chain(exp)
                    exp_date = datetime.strptime(exp, '%Y-%m-%d')
                    dte = (exp_date - datetime.now(pytz.UTC).replace(tzinfo=None)).days
                    
                    # Process calls
                    calls = options.calls.copy()
                    calls['optionType'] = 'call'
                    calls['expiration'] = exp
                    calls['dte'] = dte
                    
                    # Process puts
                    puts = options.puts.copy()
                    puts['optionType'] = 'put'
                    puts['expiration'] = exp
                    puts['dte'] = dte
                    
                    # Calculate Greeks for both
                    calls = self.calculate_greeks(calls)
                    puts = self.calculate_greeks(puts)
                    
                    all_options.append(calls)
                    all_options.append(puts)
                    
                except Exception as e:
                    print(f"Error processing expiration {exp}: {e}")
                    continue
            
            if all_options:
                self.options_chain = pd.concat(all_options, ignore_index=True)
                
                # Clean and standardize column names
                self.options_chain.columns = [col.lower() for col in self.options_chain.columns]
                
                # Ensure required columns exist
                required_cols = ['strike', 'optiontype', 'openinterest', 'volume', 
                                'impliedvolatility', 'gamma', 'delta', 'expiration', 'dte']
                
                for col in required_cols:
                    if col not in self.options_chain.columns:
                        self.options_chain[col] = 0
                
                # Fill NaN values
                self.options_chain = self.options_chain.fillna(0)
                
                return self.options_chain
            else:
                return pd.DataFrame()
                
        except Exception as e:
            print(f"Error fetching options chain: {e}")
            return pd.DataFrame()
    
    def get_option_flow(self) -> pd.DataFrame:
        """
        Get unusual options activity
        Identifies high volume/OI ratio trades
        """
        if self.options_chain is None or self.options_chain.empty:
            return pd.DataFrame()
        
        flow = self.options_chain.copy()
        
        # Calculate volume/OI ratio
        flow['volume_oi_ratio'] = flow['volume'] / (flow['openinterest'] + 1)
        
        # Filter for unusual activity (volume > 2x OI)
        unusual = flow[flow['volume_oi_ratio'] > 2].copy()
        
        # Calculate dollar volume
        unusual['dollar_volume'] = unusual['volume'] * unusual.get('lastprice', 1) * 100
        
        # Sort by dollar volume
        unusual = unusual.sort_values('dollar_volume', ascending=False)
        
        return unusual[['strike', 'optiontype', 'expiration', 'volume', 
                       'openinterest', 'volume_oi_ratio', 'dollar_volume']].head(20)


class GEXAnalyzer:
    """
    Calculates Gamma Exposure (GEX) metrics and identifies key levels
    """
    
    def __init__(self, symbol: str = 'SPY'):
        self.symbol = symbol.upper()
        self.spot_price = None
        self.options_data = None
        self.gex_profile = None
        self.key_levels = {}
        self.net_gex = 0
        self.gamma_flip = None
        
        # Market-specific thresholds
        self.thresholds = {
            'SPY': {'negative_squeeze': -1e9, 'positive_breakdown': 2e9, 'high_positive': 3e9},
            'QQQ': {'negative_squeeze': -5e8, 'positive_breakdown': 1e9, 'high_positive': 1.5e9},
            'IWM': {'negative_squeeze': -2e8, 'positive_breakdown': 5e8, 'high_positive': 8e8}
        }
    
    def calculate_gex(self, options_data: pd.DataFrame, spot_price: float) -> pd.DataFrame:
        """
        Calculate GEX for each strike
        GEX = Spot Price × Gamma × Open Interest × Contract Multiplier
        """
        self.options_data = options_data.copy()
        self.spot_price = spot_price
        
        gex_data = []
        
        for _, row in self.options_data.iterrows():
            strike = row['strike']
            gamma = row.get('gamma', 0)
            oi = row.get('openinterest', 0)
            option_type = row.get('optiontype', 'call')
            
            # GEX calculation
            # Calls: positive GEX (dealers are short gamma when they sell calls)
            # Puts: negative GEX (dealers are long gamma when they sell puts)
            if option_type == 'call':
                gex = spot_price * gamma * oi * 100
            else:  # put
                gex = -spot_price * gamma * oi * 100
            
            gex_data.append({
                'strike': strike,
                'gex': gex,
                'type': option_type,
                'gamma': gamma,
                'oi': oi,
                'expiration': row.get('expiration', 'N/A')
            })
        
        self.gex_profile = pd.DataFrame(gex_data)
        return self.gex_profile
    
    def aggregate_gex_by_strike(self) -> pd.DataFrame:
        """
        Aggregate GEX across all expirations for each strike
        """
        if self.gex_profile is None:
            return pd.DataFrame()
        
        # Group by strike and sum GEX
        strike_gex = self.gex_profile.groupby('strike').agg({
            'gex': 'sum',
            'gamma': 'sum',
            'oi': 'sum'
        }).reset_index()
        
        # Sort by strike
        strike_gex = strike_gex.sort_values('strike')
        
        # Calculate cumulative GEX
        strike_gex['cumulative_gex'] = strike_gex['gex'].cumsum()
        
        # Calculate percentage of total gamma at each strike
        total_abs_gex = strike_gex['gex'].abs().sum()
        strike_gex['gex_pct'] = (strike_gex['gex'].abs() / total_abs_gex * 100) if total_abs_gex > 0 else 0
        
        return strike_gex
    
    def find_gamma_flip(self) -> float:
        """
        Find the Gamma Flip Point (zero gamma level)
        This is where cumulative GEX crosses zero
        """
        strike_gex = self.aggregate_gex_by_strike()
        
        if strike_gex.empty:
            self.gamma_flip = self.spot_price
            return self.gamma_flip
        
        # Find where cumulative GEX changes sign
        positive_cum = strike_gex[strike_gex['cumulative_gex'] > 0]
        negative_cum = strike_gex[strike_gex['cumulative_gex'] < 0]
        
        if not positive_cum.empty and not negative_cum.empty:
            # Find the strikes around the zero crossing
            last_negative = negative_cum['strike'].iloc[-1] if not negative_cum.empty else 0
            first_positive = positive_cum['strike'].iloc[0] if not positive_cum.empty else 0
            
            # Interpolate between strikes
            if last_negative > 0 and first_positive > 0:
                # Linear interpolation
                neg_gex = strike_gex[strike_gex['strike'] == last_negative]['cumulative_gex'].iloc[0]
                pos_gex = strike_gex[strike_gex['strike'] == first_positive]['cumulative_gex'].iloc[0]
                
                # Weighted average based on distance from zero
                weight_neg = abs(pos_gex) / (abs(neg_gex) + abs(pos_gex))
                weight_pos = abs(neg_gex) / (abs(neg_gex) + abs(pos_gex))
                
                self.gamma_flip = last_negative * weight_neg + first_positive * weight_pos
            else:
                self.gamma_flip = self.spot_price
        else:
            # If all GEX is one-sided, flip is at the extreme
            if strike_gex['cumulative_gex'].iloc[-1] > 0:
                self.gamma_flip = strike_gex['strike'].min()
            else:
                self.gamma_flip = strike_gex['strike'].max()
        
        return self.gamma_flip
    
    def identify_key_levels(self) -> Dict[str, GEXLevel]:
        """
        Identify key support/resistance levels based on gamma concentration
        """
        strike_gex = self.aggregate_gex_by_strike()
        
        if strike_gex.empty:
            return {}
        
        self.key_levels = {}
        
        # Calculate net GEX
        self.net_gex = strike_gex['gex'].sum()
        
        # Find gamma flip
        self.find_gamma_flip()
        
        # Separate calls and puts
        call_gex = strike_gex[strike_gex['gex'] > 0].copy()
        put_gex = strike_gex[strike_gex['gex'] < 0].copy()
        
        # Find top 3 call walls (resistance)
        if not call_gex.empty:
            call_walls = call_gex.nlargest(3, 'gex')
            for i, (_, row) in enumerate(call_walls.iterrows(), 1):
                distance = (row['strike'] - self.spot_price) / self.spot_price * 100
                self.key_levels[f'call_wall_{i}'] = GEXLevel(
                    strike=row['strike'],
                    gex_value=row['gex'],
                    level_type='call_wall',
                    strength=row['gex_pct'],
                    distance_from_spot=distance
                )
        
        # Find top 3 put walls (support)
        if not put_gex.empty:
            put_gex['abs_gex'] = put_gex['gex'].abs()
            put_walls = put_gex.nlargest(3, 'abs_gex')
            for i, (_, row) in enumerate(put_walls.iterrows(), 1):
                distance = (row['strike'] - self.spot_price) / self.spot_price * 100
                self.key_levels[f'put_wall_{i}'] = GEXLevel(
                    strike=row['strike'],
                    gex_value=row['gex'],
                    level_type='put_wall',
                    strength=row['gex_pct'],
                    distance_from_spot=distance
                )
        
        # Add gamma flip level
        if self.gamma_flip:
            distance = (self.gamma_flip - self.spot_price) / self.spot_price * 100
            self.key_levels['gamma_flip'] = GEXLevel(
                strike=self.gamma_flip,
                gex_value=0,
                level_type='gamma_flip',
                strength=100,  # Most important level
                distance_from_spot=distance
            )
        
        return self.key_levels
    
    def calculate_charm(self) -> pd.DataFrame:
        """
        Calculate Charm (gamma decay over time)
        Shows how GEX will change as time passes
        """
        if self.gex_profile is None:
            return pd.DataFrame()
        
        charm_data = []
        
        for exp in self.gex_profile['expiration'].unique():
            exp_data = self.gex_profile[self.gex_profile['expiration'] == exp]
            
            # Calculate charm for this expiration
            # Simplified: charm increases as we approach expiration
            exp_date = pd.to_datetime(exp)
            dte = (exp_date - datetime.now(pytz.UTC).replace(tzinfo=None)).days
            
            if dte > 0:
                daily_charm = exp_data['gex'].sum() / dte  # Daily decay
                
                charm_data.append({
                    'expiration': exp,
                    'dte': dte,
                    'total_gex': exp_data['gex'].sum(),
                    'daily_charm': daily_charm,
                    'weekend_charm': daily_charm * 2.5  # Weekend decay
                })
        
        return pd.DataFrame(charm_data)
    
    def calculate_vanna(self) -> float:
        """
        Calculate Vanna (sensitivity of gamma to volatility changes)
        Positive vanna = gamma increases with vol
        """
        if self.options_data is None:
            return 0
        
        # Simplified vanna calculation
        # Weight by vega and gamma
        total_vanna = 0
        
        for _, row in self.options_data.iterrows():
            vega = row.get('vega', 0)
            gamma = row.get('gamma', 0)
            oi = row.get('openinterest', 0)
            
            # Vanna approximation
            vanna = vega * gamma * oi * 100
            total_vanna += vanna
        
        return total_vanna


class TradingStrategy:
    """
    Implements trading strategies based on GEX analysis
    """
    
    def __init__(self, gex_analyzer: GEXAnalyzer):
        self.gex = gex_analyzer
        self.setups = []
        
    def analyze_all_setups(self) -> List[TradeSetup]:
        """
        Run all strategy checks and return ranked setups
        """
        self.setups = []
        
        # Check squeeze plays
        squeeze_setups = self.identify_squeeze_setups()
        self.setups.extend(squeeze_setups)
        
        # Check premium selling opportunities
        premium_setups = self.identify_premium_selling()
        self.setups.extend(premium_setups)
        
        # Check iron condor setups
        condor_setups = self.identify_iron_condors()
        self.setups.extend(condor_setups)
        
        # Sort by confidence score
        self.setups.sort(key=lambda x: x.confidence_score, reverse=True)
        
        return self.setups
    
    def identify_squeeze_setups(self) -> List[TradeSetup]:
        """
        Identify squeeze play opportunities
        """
        setups = []
        
        if not self.gex.net_gex or not self.gex.gamma_flip:
            return setups
        
        spot = self.gex.spot_price
        flip = self.gex.gamma_flip
        net_gex = self.gex.net_gex
        
        # Get thresholds for this symbol
        thresholds = self.gex.thresholds.get(
            self.gex.symbol,
            {'negative_squeeze': -1e9, 'positive_breakdown': 2e9}
        )
        
        # Negative GEX Squeeze (Long Calls)
        if net_gex < thresholds['negative_squeeze']:
            distance_to_flip = (flip - spot) / spot * 100
            
            if -1.5 <= distance_to_flip <= -0.5:
                # Find nearest call strike above current price
                if self.gex.options_data is not None:
                    calls = self.gex.options_data[
                        (self.gex.options_data['optiontype'] == 'call') &
                        (self.gex.options_data['strike'] >= spot) &
                        (self.gex.options_data['dte'] <= 5)
                    ]
                    
                    if not calls.empty:
                        target_strike = calls['strike'].min()
                        
                        confidence = min(70 + abs(distance_to_flip) * 10, 90)
                        
                        setup = TradeSetup(
                            strategy_type="Negative GEX Squeeze",
                            action="BUY CALL",
                            entry_price=spot,
                            target_price=flip,
                            stop_loss=spot * 0.99,  # 1% stop
                            confidence_score=confidence,
                            risk_reward_ratio=abs(flip - spot) / (spot * 0.01),
                            expiration="2-5 DTE",
                            strike=target_strike,
                            notes=f"Net GEX: ${net_gex/1e9:.2f}B, Distance to flip: {distance_to_flip:.2f}%"
                        )
                        setups.append(setup)
        
        # Positive GEX Breakdown (Long Puts)
        if net_gex > thresholds['positive_breakdown']:
            distance_to_flip = (spot - flip) / spot * 100
            
            if 0 <= distance_to_flip <= 0.3:
                # Find nearest put strike below current price
                if self.gex.options_data is not None:
                    puts = self.gex.options_data[
                        (self.gex.options_data['optiontype'] == 'put') &
                        (self.gex.options_data['strike'] <= spot) &
                        (self.gex.options_data['dte'] <= 7)
                    ]
                    
                    if not puts.empty:
                        target_strike = puts['strike'].max()
                        
                        confidence = min(65 + distance_to_flip * 50, 85)
                        
                        # Find nearest call wall for stop loss
                        call_wall = None
                        for level_name, level in self.gex.key_levels.items():
                            if 'call_wall' in level_name:
                                call_wall = level.strike
                                break
                        
                        stop = call_wall if call_wall else spot * 1.01
                        
                        setup = TradeSetup(
                            strategy_type="Positive GEX Breakdown",
                            action="BUY PUT",
                            entry_price=spot,
                            target_price=flip,
                            stop_loss=stop,
                            confidence_score=confidence,
                            risk_reward_ratio=abs(spot - flip) / abs(stop - spot),
                            expiration="3-7 DTE",
                            strike=target_strike,
                            notes=f"Net GEX: ${net_gex/1e9:.2f}B, Near gamma flip: {distance_to_flip:.2f}%"
                        )
                        setups.append(setup)
        
        # Gamma Wall Compression Setup
        call_wall = self.gex.key_levels.get('call_wall_1')
        put_wall = self.gex.key_levels.get('put_wall_1')
        
        if call_wall and put_wall:
            wall_spread = abs(call_wall.strike - put_wall.strike) / spot * 100
            
            if wall_spread < 2:  # Less than 2% between walls
                # Check which wall we're closer to
                distance_to_call = (call_wall.strike - spot) / spot * 100
                distance_to_put = (spot - put_wall.strike) / spot * 100
                
                if abs(distance_to_put) < abs(distance_to_call):
                    # Closer to put wall, consider long calls
                    setup = TradeSetup(
                        strategy_type="Gamma Wall Compression",
                        action="BUY CALL",
                        entry_price=spot,
                        target_price=call_wall.strike,
                        stop_loss=put_wall.strike * 0.99,
                        confidence_score=75,
                        risk_reward_ratio=abs(call_wall.strike - spot) / abs(spot - put_wall.strike * 0.99),
                        expiration="0-2 DTE",
                        strike=spot,  # ATM
                        notes=f"Wall compression: {wall_spread:.2f}% spread, near put wall"
                    )
                else:
                    # Closer to call wall, consider long puts
                    setup = TradeSetup(
                        strategy_type="Gamma Wall Compression",
                        action="BUY PUT",
                        entry_price=spot,
                        target_price=put_wall.strike,
                        stop_loss=call_wall.strike * 1.01,
                        confidence_score=75,
                        risk_reward_ratio=abs(spot - put_wall.strike) / abs(call_wall.strike * 1.01 - spot),
                        expiration="0-2 DTE",
                        strike=spot,  # ATM
                        notes=f"Wall compression: {wall_spread:.2f}% spread, near call wall"
                    )
                
                setups.append(setup)
        
        return setups
    
    def identify_premium_selling(self) -> List[TradeSetup]:
        """
        Identify premium selling opportunities
        """
        setups = []
        
        if not self.gex.net_gex or not self.gex.key_levels:
            return setups
        
        spot = self.gex.spot_price
        net_gex = self.gex.net_gex
        
        # Get thresholds
        thresholds = self.gex.thresholds.get(
            self.gex.symbol,
            {'high_positive': 3e9}
        )
        
        # Call selling at resistance
        call_wall = self.gex.key_levels.get('call_wall_1')
        if call_wall and net_gex > thresholds['high_positive']:
            distance_to_wall = (call_wall.strike - spot) / spot * 100
            
            if 0.5 <= distance_to_wall <= 2:  # Between 0.5% and 2% away
                # Verify wall strength
                if call_wall.strength > 10:  # At least 10% of total gamma
                    setup = TradeSetup(
                        strategy_type="Call Premium Selling",
                        action="SELL CALL",
                        entry_price=spot,
                        target_price=spot,  # Theta play
                        stop_loss=call_wall.strike * 1.01,
                        confidence_score=70 + min(call_wall.strength, 20),
                        risk_reward_ratio=1.5,  # Premium dependent
                        expiration="0-2 DTE",
                        strike=call_wall.strike,
                        notes=f"Strong call wall at ${call_wall.strike:.2f}, Net GEX: ${net_gex/1e9:.2f}B"
                    )
                    setups.append(setup)
        
        # Put selling at support
        put_wall = self.gex.key_levels.get('put_wall_1')
        if put_wall and net_gex > 0:  # Positive GEX environment
            distance_to_wall = (spot - put_wall.strike) / spot * 100
            
            if 1 <= distance_to_wall <= 3:  # Between 1% and 3% away
                # Verify wall strength
                if put_wall.strength > 10:
                    setup = TradeSetup(
                        strategy_type="Put Premium Selling",
                        action="SELL PUT",
                        entry_price=spot,
                        target_price=spot,  # Theta play
                        stop_loss=put_wall.strike * 0.98,
                        confidence_score=65 + min(put_wall.strength, 20),
                        risk_reward_ratio=1.5,  # Premium dependent
                        expiration="2-5 DTE",
                        strike=put_wall.strike,
                        notes=f"Strong put wall at ${put_wall.strike:.2f}, Positive GEX environment"
                    )
                    setups.append(setup)
        
        return setups
    
    def identify_iron_condors(self) -> List[TradeSetup]:
        """
        Identify iron condor opportunities
        """
        setups = []
        
        if not self.gex.key_levels:
            return setups
        
        spot = self.gex.spot_price
        net_gex = self.gex.net_gex
        
        # Need positive GEX for iron condors
        if net_gex <= 0:
            return setups
        
        call_wall = self.gex.key_levels.get('call_wall_1')
        put_wall = self.gex.key_levels.get('put_wall_1')
        
        if call_wall and put_wall:
            wall_spread = (call_wall.strike - put_wall.strike) / spot * 100
            
            # Ideal spread between 3-5%
            if 3 <= wall_spread <= 5:
                # Calculate expected range
                upper_short = call_wall.strike
                lower_short = put_wall.strike
                
                # Wings 1-2% beyond walls
                upper_long = upper_short * 1.015
                lower_long = lower_short * 0.985
                
                # Check for concentration at walls
                wall_concentration = call_wall.strength + put_wall.strength
                
                if wall_concentration > 20:  # At least 20% of gamma at walls
                    # Determine bias based on gamma distribution
                    call_gamma = abs(call_wall.gex_value)
                    put_gamma = abs(put_wall.gex_value)
                    
                    if put_gamma > call_gamma * 1.2:
                        condor_type = "Broken Wing (Bullish)"
                        notes = f"Put-heavy gamma ({put_gamma/call_gamma:.1f}x), wider put spread"
                    elif call_gamma > put_gamma * 1.2:
                        condor_type = "Broken Wing (Bearish)"
                        notes = f"Call-heavy gamma ({call_gamma/put_gamma:.1f}x), wider call spread"
                    else:
                        condor_type = "Standard Iron Condor"
                        notes = f"Balanced gamma distribution"
                    
                    setup = TradeSetup(
                        strategy_type=condor_type,
                        action="SELL IC",
                        entry_price=spot,
                        target_price=spot,  # Theta play
                        stop_loss=0,  # Defined risk
                        confidence_score=60 + min(wall_concentration, 30),
                        risk_reward_ratio=1.5,  # Credit dependent
                        expiration="5-10 DTE",
                        strike=0,  # Multiple strikes
                        notes=f"Short: ${lower_short:.0f}/{upper_short:.0f}, Long: ${lower_long:.0f}/{upper_long:.0f}. {notes}"
                    )
                    setups.append(setup)
        
        return setups
    
    def calculate_position_size(self, setup: TradeSetup, account_size: float) -> Dict[str, float]:
        """
        Calculate appropriate position size based on risk parameters
        """
        position_info = {}
        
        # Base risk per trade
        if "Squeeze" in setup.strategy_type:
            max_risk = account_size * 0.03  # 3% for squeeze plays
        elif "Selling" in setup.strategy_type:
            max_risk = account_size * 0.05  # 5% for premium selling
        else:  # Iron Condors
            max_risk = account_size * 0.02  # 2% for condors
        
        # Adjust for confidence
        confidence_multiplier = setup.confidence_score / 100
        adjusted_risk = max_risk * confidence_multiplier
        
        position_info['max_risk'] = adjusted_risk
        position_info['position_size'] = adjusted_risk  # Simplified
        position_info['as_percent'] = (adjusted_risk / account_size) * 100
        
        return position_info


class MarketRegimeAnalyzer:
    """
    Analyzes overall market regime based on GEX and other factors
    """
    
    def __init__(self, gex_analyzer: GEXAnalyzer):
        self.gex = gex_analyzer
        
    def get_regime(self) -> Dict[str, any]:
        """
        Determine current market regime
        """
        regime = {
            'type': 'Unknown',
            'volatility_expectation': 'Normal',
            'trending_bias': 'Neutral',
            'confidence': 0,
            'description': ''
        }
        
        if not self.gex.net_gex:
            return regime
        
        net_gex = self.gex.net_gex
        spot = self.gex.spot_price
        flip = self.gex.gamma_flip if self.gex.gamma_flip else spot
        
        # Determine regime based on net GEX
        if net_gex > 2e9:  # High positive GEX
            regime['type'] = 'Volatility Suppression'
            regime['volatility_expectation'] = 'Low'
            regime['description'] = 'Dealers long gamma, will hedge by selling rallies and buying dips'
            regime['confidence'] = min(70 + (net_gex / 1e9) * 5, 95)
        elif net_gex < -1e9:  # High negative GEX
            regime['type'] = 'Volatility Amplification'
            regime['volatility_expectation'] = 'High'
            regime['description'] = 'Dealers short gamma, will hedge by buying rallies and selling dips'
            regime['confidence'] = min(70 + abs(net_gex / 1e9) * 5, 95)
        else:
            regime['type'] = 'Transitional'
            regime['volatility_expectation'] = 'Normal'
            regime['description'] = 'Mixed dealer positioning, potential for regime change'
            regime['confidence'] = 50
        
        # Determine trending bias
        distance_to_flip = (spot - flip) / spot * 100
        
        if distance_to_flip > 1:
            regime['trending_bias'] = 'Bullish' if net_gex > 0 else 'Bearish continuation'
        elif distance_to_flip < -1:
            regime['trending_bias'] = 'Bearish' if net_gex > 0 else 'Bullish reversal potential'
        else:
            regime['trending_bias'] = 'Neutral - Near gamma flip'
        
        return regime
    
    def get_intraday_outlook(self) -> Dict[str, any]:
        """
        Generate intraday trading outlook
        """
        outlook = {
            'primary_range': {},
            'breakout_levels': {},
            'fade_levels': {},
            'risk_level': 'Medium',
            'recommended_strategy': ''
        }
        
        if not self.gex.key_levels:
            return outlook
        
        spot = self.gex.spot_price
        
        # Find primary range
        call_wall = self.gex.key_levels.get('call_wall_1')
        put_wall = self.gex.key_levels.get('put_wall_1')
        
        if call_wall and put_wall:
            outlook['primary_range'] = {
                'upper': call_wall.strike,
                'lower': put_wall.strike,
                'strength': 'Strong' if (call_wall.strength + put_wall.strength) > 30 else 'Moderate'
            }
        
        # Breakout levels
        if call_wall:
            outlook['breakout_levels']['upside'] = call_wall.strike * 1.005
        if put_wall:
            outlook['breakout_levels']['downside'] = put_wall.strike * 0.995
        
        # Fade levels (where to sell/buy)
        regime = self.get_regime()
        if regime['type'] == 'Volatility Suppression':
            outlook['fade_levels']['sell'] = call_wall.strike if call_wall else spot * 1.01
            outlook['fade_levels']['buy'] = put_wall.strike if put_wall else spot * 0.99
            outlook['recommended_strategy'] = 'Fade moves at gamma walls'
        elif regime['type'] == 'Volatility Amplification':
            outlook['recommended_strategy'] = 'Momentum following with tight stops'
            outlook['risk_level'] = 'High'
        else:
            outlook['recommended_strategy'] = 'Wait for clearer setup'
        
        return outlook


class RiskManager:
    """
    Manages position risk and portfolio exposure
    """

    def __init__(self, account_size: float = 100000):
        self.account_size = account_size
        self.positions = []
        self.daily_pnl = 0
        self.max_daily_loss = account_size * 0.02  # 2% max daily loss

    def check_new_position(self, setup: TradeSetup) -> Dict[str, any]:
        """
        Verify if new position meets risk criteria
        """
        risk_check = {
            'approved': False,
            'reason': '',
            'current_exposure': 0,
            'available_risk': 0
        }

        # Calculate current exposure
        current_exposure = sum([p.get('risk', 0) for p in self.positions])
        risk_check['current_exposure'] = current_exposure

        # Check daily loss limit
        if self.daily_pnl <= -self.max_daily_loss:
            risk_check['reason'] = 'Daily loss limit reached'
            return risk_check

        # Check position limits
        strategy_positions = [p for p in self.positions if p['strategy'] == setup.strategy_type]
        if len(strategy_positions) >= 3:
            risk_check['reason'] = 'Maximum positions for this strategy'
            return risk_check

        # Calculate available risk
        max_portfolio_risk = self.account_size * 0.10  # 10% max portfolio risk
        available_risk = max_portfolio_risk - current_exposure
        risk_check['available_risk'] = available_risk

        # Approve if within limits
        if available_risk > 0:
            risk_check['approved'] = True
            risk_check['reason'] = 'Position approved'
        else:
            risk_check['reason'] = 'Portfolio risk limit reached'

        return risk_check


class TradingVolatilityAPI:
    """
    API wrapper for fetching GEX data and options information
    """

    def __init__(self):
        self.options_fetcher = None
        self.gex_analyzer = None

    def get_net_gamma(self, symbol: str) -> Dict:
        """Fetch net gamma exposure data for a symbol"""
        import streamlit as st
        try:
            st.write(f"🔍 get_net_gamma: Initializing fetcher for {symbol}")
            # Initialize fetcher
            self.options_fetcher = OptionsDataFetcher(symbol)

            st.write(f"🔍 get_net_gamma: Getting spot price...")
            # Get spot price
            spot = self.options_fetcher.get_spot_price()
            st.write(f"✓ Spot price: ${spot:.2f}")

            st.write(f"🔍 get_net_gamma: Fetching options chain...")
            # Get options chain
            options_chain = self.options_fetcher.get_options_chain()
            st.write(f"📊 Options chain: {len(options_chain)} rows, empty: {options_chain.empty}")

            if options_chain.empty:
                st.error(f"❌ OPTIONS CHAIN IS EMPTY! This is why gex_analyzer is None!")
                st.warning("💡 The yfinance API might not be returning options data. This could be due to API limits, network issues, or the symbol having no options.")
                return {'error': 'No options data available', 'spot_price': spot}

            st.write(f"🔍 get_net_gamma: Creating GEXAnalyzer...")
            # Analyze GEX
            self.gex_analyzer = GEXAnalyzer(symbol)
            gex_profile = self.gex_analyzer.calculate_gex(options_chain, spot)
            st.write(f"✓ GEXAnalyzer created, gex_profile has {len(gex_profile)} rows")

            key_levels = self.gex_analyzer.identify_key_levels()

            # Build response
            result = {
                'symbol': symbol,
                'spot_price': spot,
                'net_gex': self.gex_analyzer.net_gex,
                'flip_point': self.gex_analyzer.gamma_flip,
                'call_wall': key_levels.get('call_wall_1').strike if key_levels.get('call_wall_1') else 0,
                'put_wall': key_levels.get('put_wall_1').strike if key_levels.get('put_wall_1') else 0,
            }

            st.success(f"✅ get_net_gamma completed successfully!")
            return result

        except Exception as e:
            import streamlit as st
            import traceback
            error_msg = f"Error fetching data: {e}"
            st.error(f"❌ {error_msg}")
            st.code(traceback.format_exc())
            print(error_msg)
            traceback.print_exc()
            return {'error': str(e)}

    def get_gex_profile(self, symbol: str) -> Dict:
        """Get detailed GEX profile for visualization"""
        import streamlit as st
        try:
            st.write(f"🔍 DEBUG: Starting get_gex_profile for {symbol}")

            if self.gex_analyzer is None:
                st.write("⚠️ DEBUG: gex_analyzer is None, calling get_net_gamma...")
                # Fetch data first
                result = self.get_net_gamma(symbol)
                st.write(f"📊 DEBUG: get_net_gamma returned: {result.keys() if result else 'None'}")

            if self.gex_analyzer is None:
                st.error("❌ DEBUG: gex_analyzer is STILL None after fetch!")
                return {}

            if self.gex_analyzer.gex_profile is None:
                st.error("❌ DEBUG: gex_analyzer.gex_profile is None!")
                return {}

            # Get the raw GEX profile data
            gex_df = self.gex_analyzer.gex_profile
            st.write(f"📈 DEBUG: gex_profile type: {type(gex_df)}, empty: {gex_df.empty if hasattr(gex_df, 'empty') else 'N/A'}")

            if gex_df.empty:
                st.error(f"❌ DEBUG: gex_profile DataFrame is empty for {symbol}!")
                return {}

            st.success(f"✅ DEBUG: gex_profile has {len(gex_df)} rows!")

            # Separate calls and puts, then aggregate by strike
            calls = gex_df[gex_df['type'] == 'call'].groupby('strike')['gex'].sum()
            puts = gex_df[gex_df['type'] == 'put'].groupby('strike')['gex'].sum()

            # Get all unique strikes
            all_strikes = sorted(set(calls.index) | set(puts.index))

            # Build the strikes data structure expected by visualization
            strikes_data = []
            for strike in all_strikes:
                call_gamma = calls.get(strike, 0)
                put_gamma = puts.get(strike, 0)

                strikes_data.append({
                    'strike': strike,
                    'call_gamma': abs(call_gamma),  # Call gamma as positive
                    'put_gamma': abs(put_gamma)     # Put gamma as positive (will be negated in viz)
                })

            # Convert to dict format for visualization
            profile = {
                'strikes': strikes_data,
                'spot_price': self.gex_analyzer.spot_price,
                'flip_point': self.gex_analyzer.gamma_flip
            }

            return profile

        except Exception as e:
            import streamlit as st
            import traceback
            error_msg = f"Error getting GEX profile: {str(e)}"
            st.error(f"❌ {error_msg}")
            st.code(traceback.format_exc())
            print(error_msg)
            traceback.print_exc()
            return {}


class MonteCarloEngine:
    """
    Monte Carlo simulation engine for options and squeeze plays
    """

    def __init__(self, num_simulations: int = 10000):
        self.num_simulations = num_simulations

    def simulate_squeeze_play(self,
                              spot_price: float,
                              flip_point: float,
                              call_wall: float,
                              volatility: float = 0.20,
                              days: int = 5) -> Dict:
        """
        Run Monte Carlo simulation for a squeeze play scenario
        """
        try:
            # Convert days to years for calculations
            time_horizon = days / 252

            # Generate random price paths
            np.random.seed(42)  # For reproducibility

            # GBM parameters
            drift = 0  # Assume no drift for short-term
            vol = volatility

            # Simulate price paths
            price_paths = []
            hit_flip_count = 0
            hit_wall_count = 0
            max_gains = []

            for _ in range(self.num_simulations):
                # Generate daily returns
                daily_returns = np.random.normal(
                    drift / 252,
                    vol / np.sqrt(252),
                    days
                )

                # Calculate price path
                price_path = spot_price * np.exp(np.cumsum(daily_returns))
                price_paths.append(price_path[-1])

                # Check if hit flip point
                if max(price_path) >= flip_point:
                    hit_flip_count += 1

                # Check if hit call wall
                if max(price_path) >= call_wall:
                    hit_wall_count += 1

                # Calculate max gain
                max_price = max(price_path)
                max_gain_pct = (max_price - spot_price) / spot_price * 100
                max_gains.append(max_gain_pct)

            # Calculate statistics
            final_prices = np.array(price_paths)

            result = {
                'probability_hit_flip': (hit_flip_count / self.num_simulations) * 100,
                'probability_hit_wall': (hit_wall_count / self.num_simulations) * 100,
                'expected_final_price': np.mean(final_prices),
                'median_final_price': np.median(final_prices),
                'std_final_price': np.std(final_prices),
                'max_gain_percent': np.percentile(max_gains, 95),  # 95th percentile
                'avg_gain_percent': np.mean(max_gains),
                'final_price_distribution': final_prices.tolist(),
            }

            return result

        except Exception as e:
            print(f"Monte Carlo simulation error: {e}")
            return {}


class BlackScholesPricer:
    """
    Black-Scholes option pricing model
    """

    def __init__(self, risk_free_rate: float = 0.045):
        self.risk_free_rate = risk_free_rate

    def calculate_option_price(self,
                              spot: float,
                              strike: float,
                              time_to_expiry: float,
                              volatility: float,
                              option_type: str = 'call') -> Dict:
        """
        Calculate option price using Black-Scholes
        """
        try:
            from scipy.stats import norm

            # Black-Scholes formula
            d1 = (np.log(spot / strike) + (self.risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / (volatility * np.sqrt(time_to_expiry))
            d2 = d1 - volatility * np.sqrt(time_to_expiry)

            if option_type.lower() == 'call':
                price = spot * norm.cdf(d1) - strike * np.exp(-self.risk_free_rate * time_to_expiry) * norm.cdf(d2)
                delta = norm.cdf(d1)
            else:  # put
                price = strike * np.exp(-self.risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
                delta = -norm.cdf(-d1)

            # Calculate Greeks
            gamma = norm.pdf(d1) / (spot * volatility * np.sqrt(time_to_expiry))
            vega = spot * norm.pdf(d1) * np.sqrt(time_to_expiry) / 100  # Per 1% vol change
            theta = (-spot * norm.pdf(d1) * volatility / (2 * np.sqrt(time_to_expiry))
                    - self.risk_free_rate * strike * np.exp(-self.risk_free_rate * time_to_expiry) * norm.cdf(d2 if option_type.lower() == 'call' else -d2)) / 365

            return {
                'price': price,
                'delta': delta,
                'gamma': gamma,
                'vega': vega,
                'theta': theta,
                'd1': d1,
                'd2': d2
            }

        except Exception as e:
            print(f"Black-Scholes pricing error: {e}")
            return {}
