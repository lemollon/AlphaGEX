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
    
    def get_options_chain(self, days_to_expiry: int = 30, max_retries: int = 3) -> pd.DataFrame:
        """
        Fetch complete options chain with Greeks
        Includes retry logic for rate limiting
        """
        import time

        for attempt in range(max_retries):
            try:
                # Update spot price first
                self.get_spot_price()

                # Get available expiration dates with retry
                print(f"Attempt {attempt + 1}/{max_retries}: Fetching options expirations for {self.symbol}...")
                expirations = self.ticker.options

                if not expirations or len(expirations) == 0:
                    print(f"⚠️ No expirations found for {self.symbol}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        print(f"Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return pd.DataFrame()

                print(f"✓ Found {len(expirations)} expirations: {expirations[:5]}")

                # Filter expirations within our timeframe
                target_date = datetime.now(pytz.UTC) + timedelta(days=days_to_expiry)
                valid_expirations = []

                for exp_str in expirations:
                    exp_date = datetime.strptime(exp_str, '%Y-%m-%d')
                    if exp_date <= target_date:
                        valid_expirations.append(exp_str)

                # Limit to first 5 expirations for performance
                valid_expirations = valid_expirations[:5] if len(valid_expirations) > 5 else valid_expirations
                print(f"✓ Using {len(valid_expirations)} valid expirations")

                all_options = []

                for exp in valid_expirations:
                    try:
                        # Get options chain
                        print(f"  Fetching options for {exp}...")
                        options = self.ticker.option_chain(exp)
                        exp_date = datetime.strptime(exp, '%Y-%m-%d')
                        dte = (exp_date - datetime.now(pytz.UTC).replace(tzinfo=None)).days

                        # Process calls
                        calls = options.calls.copy()
                        if len(calls) == 0:
                            print(f"  ⚠️ No calls found for {exp}")
                            continue

                        calls['optionType'] = 'call'
                        calls['expiration'] = exp
                        calls['dte'] = dte

                        # Process puts
                        puts = options.puts.copy()
                        if len(puts) == 0:
                            print(f"  ⚠️ No puts found for {exp}")
                            continue

                        puts['optionType'] = 'put'
                        puts['expiration'] = exp
                        puts['dte'] = dte

                        # Calculate Greeks for both
                        calls = self.calculate_greeks(calls)
                        puts = self.calculate_greeks(puts)

                        all_options.append(calls)
                        all_options.append(puts)
                        print(f"  ✓ Loaded {len(calls)} calls, {len(puts)} puts")

                    except Exception as e:
                        print(f"  Error processing expiration {exp}: {e}")
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

                    print(f"✓ Options chain loaded: {len(self.options_chain)} total options")
                    return self.options_chain
                else:
                    print(f"⚠️ No options data collected")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return pd.DataFrame()

            except Exception as e:
                print(f"Error fetching options chain (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    import traceback
                    traceback.print_exc()
                    return pd.DataFrame()

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
        Calculate GEX for each strike (vectorized for 50-100x performance improvement)
        GEX = Spot Price × Gamma × Open Interest × Contract Multiplier
        """
        self.options_data = options_data.copy()
        self.spot_price = spot_price

        # Vectorized calculation - much faster than iterrows()
        df = self.options_data.copy()

        # Fill missing values
        df['gamma'] = df.get('gamma', pd.Series([0] * len(df), index=df.index)).fillna(0)
        df['openinterest'] = df.get('openinterest', pd.Series([0] * len(df), index=df.index)).fillna(0)
        df['optiontype'] = df.get('optiontype', pd.Series(['call'] * len(df), index=df.index)).fillna('call')

        # Calculate base GEX for all options (vectorized)
        df['gex'] = spot_price * df['gamma'] * df['openinterest'] * 100

        # Negate GEX for puts (dealers are long gamma when they sell puts)
        put_mask = df['optiontype'] == 'put'
        df.loc[put_mask, 'gex'] = -df.loc[put_mask, 'gex']

        # Select and rename columns for output
        self.gex_profile = df[['strike', 'gex', 'optiontype', 'gamma', 'openinterest']].copy()
        self.gex_profile.columns = ['strike', 'gex', 'type', 'gamma', 'oi']

        # Add expiration if available
        if 'expiration' in df.columns:
            self.gex_profile['expiration'] = df['expiration']
        else:
            self.gex_profile['expiration'] = 'N/A'

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
        
        # Find top 3 call walls (resistance) - using .iloc instead of .iterrows()
        if not call_gex.empty:
            call_walls = call_gex.nlargest(3, 'gex')
            for i in range(len(call_walls)):
                row = call_walls.iloc[i]
                distance = (row['strike'] - self.spot_price) / self.spot_price * 100
                self.key_levels[f'call_wall_{i+1}'] = GEXLevel(
                    strike=row['strike'],
                    gex_value=row['gex'],
                    level_type='call_wall',
                    strength=row['gex_pct'],
                    distance_from_spot=distance
                )

        # Find top 3 put walls (support) - using .iloc instead of .iterrows()
        if not put_gex.empty:
            put_gex['abs_gex'] = put_gex['gex'].abs()
            put_walls = put_gex.nlargest(3, 'abs_gex')
            for i in range(len(put_walls)):
                row = put_walls.iloc[i]
                distance = (row['strike'] - self.spot_price) / self.spot_price * 100
                self.key_levels[f'put_wall_{i+1}'] = GEXLevel(
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

        # Vectorized vanna calculation (50-100x faster than iterrows)
        df = self.options_data.copy()

        # Fill missing values
        df['vega'] = df.get('vega', pd.Series([0] * len(df), index=df.index)).fillna(0)
        df['gamma'] = df.get('gamma', pd.Series([0] * len(df), index=df.index)).fillna(0)
        df['openinterest'] = df.get('openinterest', pd.Series([0] * len(df), index=df.index)).fillna(0)

        # Vectorized vanna calculation
        df['vanna'] = df['vega'] * df['gamma'] * df['openinterest'] * 100

        return df['vanna'].sum()


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
    API wrapper for fetching GEX data from Trading Volatility API
    With built-in rate limiting to prevent API limit errors

    IMPORTANT: Rate limiting and circuit breaker state is SHARED across ALL instances
    to prevent multiple instances from overwhelming the API
    """

    # CLASS-LEVEL (SHARED) rate limiting state - applies to ALL instances
    _shared_last_request_time = 0
    _shared_min_request_interval = 15.0  # 15 SECONDS between requests
    _shared_circuit_breaker_active = False
    _shared_circuit_breaker_until = 0
    _shared_consecutive_rate_limit_errors = 0
    _shared_api_call_count = 0
    _shared_api_call_count_minute = 0
    _shared_minute_reset_time = 0

    # CLASS-LEVEL (SHARED) response cache - shared across ALL instances
    _shared_response_cache = {}
    _shared_cache_duration = 300  # Cache for 5 MINUTES (300 seconds)

    def __init__(self):
        import streamlit as st
        import time
        import os

        # Read username/API key from environment variables (for Render) or secrets (for local)
        # Priority: ENV VAR > st.secrets > empty string
        self.api_key = os.getenv("TV_USERNAME") or os.getenv("tv_username", "")
        if not self.api_key:
            try:
                self.api_key = st.secrets.get("tv_username", "")
            except:
                self.api_key = ""

        # Read endpoint from environment variables or secrets (with fallback)
        self.endpoint = os.getenv("ENDPOINT") or os.getenv("endpoint", "")
        if not self.endpoint:
            try:
                self.endpoint = st.secrets.get("endpoint",
                               st.secrets.get("api_key",
                               "https://stocks.tradingvolatility.net/api"))
            except:
                self.endpoint = "https://stocks.tradingvolatility.net/api"

        self.last_response = None  # Store last API response for profile data

        # Initialize shared minute reset time if not set
        if TradingVolatilityAPI._shared_minute_reset_time == 0:
            TradingVolatilityAPI._shared_minute_reset_time = time.time() + 60

    def _wait_for_rate_limit(self):
        """Enforce rate limiting by waiting between requests + circuit breaker (SHARED across all instances)"""
        import time
        current_time = time.time()

        # Check circuit breaker (SHARED)
        if TradingVolatilityAPI._shared_circuit_breaker_active:
            if current_time < TradingVolatilityAPI._shared_circuit_breaker_until:
                wait_time = TradingVolatilityAPI._shared_circuit_breaker_until - current_time
                print(f"⚠️ Circuit breaker active, waiting {wait_time:.0f} more seconds...")
                time.sleep(wait_time)
            else:
                # Circuit breaker expired, reset
                TradingVolatilityAPI._shared_circuit_breaker_active = False
                TradingVolatilityAPI._shared_consecutive_rate_limit_errors = 0
                print("✅ Circuit breaker reset")

        # Reset minute counter if needed (SHARED)
        if current_time >= TradingVolatilityAPI._shared_minute_reset_time:
            TradingVolatilityAPI._shared_api_call_count_minute = 0
            TradingVolatilityAPI._shared_minute_reset_time = current_time + 60

        time_since_last = current_time - TradingVolatilityAPI._shared_last_request_time

        if time_since_last < TradingVolatilityAPI._shared_min_request_interval:
            wait_time = TradingVolatilityAPI._shared_min_request_interval - time_since_last
            time.sleep(wait_time)

        TradingVolatilityAPI._shared_last_request_time = time.time()

        # Increment counters (SHARED)
        TradingVolatilityAPI._shared_api_call_count += 1
        TradingVolatilityAPI._shared_api_call_count_minute += 1

    def _handle_rate_limit_error(self):
        """Handle API rate limit error with exponential backoff (SHARED across all instances)"""
        import time
        TradingVolatilityAPI._shared_consecutive_rate_limit_errors += 1

        # Exponential backoff: 30s, 60s, 120s, 300s
        backoff_times = [30, 60, 120, 300]
        backoff_index = min(TradingVolatilityAPI._shared_consecutive_rate_limit_errors - 1, len(backoff_times) - 1)
        backoff_seconds = backoff_times[backoff_index]

        # Activate circuit breaker (SHARED)
        TradingVolatilityAPI._shared_circuit_breaker_active = True
        TradingVolatilityAPI._shared_circuit_breaker_until = time.time() + backoff_seconds

        print(f"🚨 API RATE LIMIT HIT ({TradingVolatilityAPI._shared_consecutive_rate_limit_errors}x) - Circuit breaker active for {backoff_seconds}s")

    def _reset_rate_limit_errors(self):
        """Reset rate limit error counter on successful request (SHARED across all instances)"""
        if TradingVolatilityAPI._shared_consecutive_rate_limit_errors > 0:
            TradingVolatilityAPI._shared_consecutive_rate_limit_errors = 0
            print("✅ API calls successful again")

    def get_api_usage_stats(self) -> dict:
        """Get current API usage statistics (SHARED across all instances)"""
        import time
        return {
            'total_calls': TradingVolatilityAPI._shared_api_call_count,
            'calls_this_minute': TradingVolatilityAPI._shared_api_call_count_minute,
            'cache_size': len(TradingVolatilityAPI._shared_response_cache),
            'time_until_minute_reset': max(0, int(TradingVolatilityAPI._shared_minute_reset_time - time.time()))
        }

    def _get_cache_key(self, endpoint: str, symbol: str) -> str:
        """Generate cache key for API responses"""
        return f"{endpoint}_{symbol}"

    def _get_cached_response(self, cache_key: str):
        """Get cached response if still valid (SHARED cache across all instances)"""
        import time
        if cache_key in TradingVolatilityAPI._shared_response_cache:
            cached_data, timestamp = TradingVolatilityAPI._shared_response_cache[cache_key]
            if time.time() - timestamp < TradingVolatilityAPI._shared_cache_duration:
                return cached_data
        return None

    def _cache_response(self, cache_key: str, data):
        """Cache API response with timestamp (SHARED cache across all instances)"""
        import time
        TradingVolatilityAPI._shared_response_cache[cache_key] = (data, time.time())

    def _calculate_walls_from_strike_data(self, strike_data, st):
        """
        Try to extract call wall and put wall from strike-level data
        Handles various data formats: list of dicts, dict of arrays, etc.
        Returns (call_wall, put_wall) as floats
        """
        try:
            call_wall = 0
            put_wall = 0

            # Format 1: List of strike objects with gamma values
            if isinstance(strike_data, list):
                st.write(f"  Parsing list format with {len(strike_data)} strikes...")
                max_call_gamma = 0
                max_put_gamma = 0

                for strike_obj in strike_data:
                    if isinstance(strike_obj, dict):
                        # Look for strike price and gamma values
                        strike = strike_obj.get('strike', strike_obj.get('strike_price', 0))

                        # Try different field names for call/put gamma
                        call_gamma = abs(float(strike_obj.get('call_gamma', strike_obj.get('call_gex', strike_obj.get('calls', 0)))))
                        put_gamma = abs(float(strike_obj.get('put_gamma', strike_obj.get('put_gex', strike_obj.get('puts', 0)))))

                        if call_gamma > max_call_gamma:
                            max_call_gamma = call_gamma
                            call_wall = float(strike)

                        if put_gamma > max_put_gamma:
                            max_put_gamma = put_gamma
                            put_wall = float(strike)

                if call_wall and put_wall:
                    st.success(f"  ✅ Calculated from strike list: Call Wall ${call_wall:.2f}, Put Wall ${put_wall:.2f}")
                    return call_wall, put_wall

            # Format 2: Dict with strike keys and gamma values
            elif isinstance(strike_data, dict):
                st.write(f"  Parsing dict format with {len(strike_data)} entries...")

                # Check if keys are strike prices
                try:
                    # Try to parse first key as a number
                    first_key = list(strike_data.keys())[0]
                    float(first_key)  # Will throw if not a number

                    # Keys are strikes, values might be gamma or dict with call/put
                    max_call_gamma = 0
                    max_put_gamma = 0

                    for strike_key, value in strike_data.items():
                        strike = float(strike_key)

                        if isinstance(value, dict):
                            call_gamma = abs(float(value.get('call', value.get('call_gamma', value.get('calls', 0)))))
                            put_gamma = abs(float(value.get('put', value.get('put_gamma', value.get('puts', 0)))))
                        else:
                            # Value is just a number - might be total gamma
                            continue

                        if call_gamma > max_call_gamma:
                            max_call_gamma = call_gamma
                            call_wall = strike

                        if put_gamma > max_put_gamma:
                            max_put_gamma = put_gamma
                            put_wall = strike

                    if call_wall and put_wall:
                        st.success(f"  ✅ Calculated from strike dict: Call Wall ${call_wall:.2f}, Put Wall ${put_wall:.2f}")
                        return call_wall, put_wall

                except (ValueError, IndexError):
                    # Keys are not strikes, might be field names
                    st.write("  Dict keys are not strikes, checking for call/put arrays...")

            return 0, 0

        except Exception as e:
            st.warning(f"  ⚠️ Could not parse strike data: {e}")
            return 0, 0

    def get_net_gamma(self, symbol: str) -> Dict:
        """Fetch net gamma exposure data from Trading Volatility API with rate limiting"""
        import streamlit as st
        import requests

        try:
            if not self.api_key:
                st.error("❌ Trading Volatility username not found in secrets!")
                st.warning("Add 'tv_username' to your Streamlit secrets")
                return {'error': 'API key not configured'}

            # Check cache first
            cache_key = self._get_cache_key('gex/latest', symbol)
            cached_data = self._get_cached_response(cache_key)
            if cached_data:
                # Use cached response
                self.last_response = cached_data
                json_response = cached_data
            else:
                # Wait for rate limit before making request
                self._wait_for_rate_limit()

                # Call Trading Volatility API
                response = requests.get(
                    self.endpoint + '/gex/latest',
                    params={
                        'ticker': symbol,
                        'username': self.api_key,
                        'format': 'json'
                    },
                    headers={'Accept': 'application/json'},
                    timeout=60  # Increased from 30 to handle slower API responses
                )

                if response.status_code != 200:
                    st.error(f"❌ Trading Volatility API returned status {response.status_code}")
                    return {'error': f'API returned {response.status_code}'}

                # Check for rate limit error in response text
                if "API limit exceeded" in response.text:
                    st.error(f"⚠️ API Rate Limit Hit - Circuit breaker activating")
                    self._handle_rate_limit_error()
                    return {'error': 'API rate limit exceeded'}

                # Check if response has content before parsing JSON
                if not response.text or len(response.text.strip()) == 0:
                    st.error(f"❌ Trading Volatility API returned empty response")
                    st.warning(f"URL: {response.url}")
                    return {'error': 'Empty response from API'}

                # Try to parse JSON with better error handling
                try:
                    json_response = response.json()
                except ValueError as json_err:
                    # Check if error message contains rate limit info
                    if "API limit exceeded" in response.text:
                        st.error(f"⚠️ API Rate Limit - Backing off for 30+ seconds")
                        self._handle_rate_limit_error()
                        return {'error': 'API rate limit exceeded'}
                    else:
                        st.error(f"❌ Invalid JSON from Trading Volatility API")
                        st.warning(f"Response text (first 200 chars): {response.text[:200]}")
                        return {'error': f'Invalid JSON: {str(json_err)}'}

                # Success! Reset error counter
                self._reset_rate_limit_errors()

                # Cache the response
                self._cache_response(cache_key, json_response)

                # Store the full response for get_gex_profile to use
                self.last_response = json_response

            # Parse nested response - data is under the ticker symbol
            ticker_data = json_response.get(symbol, {})

            if not ticker_data:
                st.error(f"❌ No data found for {symbol} in API response")
                return {'error': 'No ticker data in response'}

            # Extract aggregate metrics from Trading Volatility API
            call_wall = 0
            put_wall = 0

            result = {
                'symbol': symbol,
                'spot_price': float(ticker_data.get('price', 0)),
                'net_gex': float(ticker_data.get('skew_adjusted_gex', 0)),
                'flip_point': float(ticker_data.get('gex_flip_price', 0)),
                'call_wall': float(call_wall) if call_wall else 0,
                'put_wall': float(put_wall) if put_wall else 0,
                'put_call_ratio': float(ticker_data.get('put_call_ratio_open_interest', 0)),
                'implied_volatility': float(ticker_data.get('implied_volatility', 0)),
                'collection_date': ticker_data.get('collection_date', ''),
                'raw_data': ticker_data
            }

            return result

        except Exception as e:
            import traceback
            error_msg = f"Error fetching data from Trading Volatility API: {e}"
            st.error(f"❌ {error_msg}")
            print(error_msg)
            traceback.print_exc()
            return {'error': str(e)}

    def get_gex_profile(self, symbol: str) -> Dict:
        """Get detailed GEX profile using Trading Volatility /gex/gammaOI endpoint with rate limiting"""
        import streamlit as st
        import requests

        try:
            if not self.api_key:
                st.error("❌ Trading Volatility username not found in secrets!")
                return {}

            # Check cache first
            cache_key = self._get_cache_key('gex/gammaOI', symbol)
            cached_data = self._get_cached_response(cache_key)
            if cached_data:
                json_response = cached_data
            else:
                # Wait for rate limit before making request
                self._wait_for_rate_limit()

                # Call Trading Volatility /gex/gammaOI endpoint for strike-level data
                response = requests.get(
                    self.endpoint + '/gex/gammaOI',
                    params={
                        'ticker': symbol,
                        'username': self.api_key,
                        'format': 'json'
                    },
                    headers={'Accept': 'application/json'},
                    timeout=30
                )

                if response.status_code != 200:
                    st.error(f"❌ gammaOI endpoint returned status {response.status_code}")
                    return {}

                # Check for rate limit error in response text
                if "API limit exceeded" in response.text:
                    st.error(f"⚠️ API Rate Limit Hit - Circuit breaker activating")
                    self._handle_rate_limit_error()
                    return {}

                # Check if response has content before parsing JSON
                if not response.text or len(response.text.strip()) == 0:
                    st.error(f"❌ gammaOI endpoint returned empty response")
                    return {}

                # Try to parse JSON with better error handling
                try:
                    json_response = response.json()
                except ValueError as json_err:
                    # Check if error message contains rate limit info
                    if "API limit exceeded" in response.text:
                        st.error(f"⚠️ API Rate Limit - Backing off for 30+ seconds")
                        self._handle_rate_limit_error()
                        return {}
                    else:
                        st.error(f"❌ Invalid JSON from gammaOI endpoint")
                        st.warning(f"Response text (first 200 chars): {response.text[:200]}")
                        return {}

                # Success! Reset error counter
                self._reset_rate_limit_errors()

                # Cache the response
                self._cache_response(cache_key, json_response)

            ticker_data = json_response.get(symbol, {})

            if not ticker_data:
                st.error(f"❌ No data found for {symbol} in gammaOI response")
                return {}

            # Check if gammaOI includes aggregate fields (to avoid separate /gex/latest call)
            has_aggregate_data = all(field in ticker_data for field in ['implied_volatility', 'gex_flip_price', 'skew_adjusted_gex'])

            # Extract gamma_array (strike-level data)
            gamma_array = ticker_data.get('gamma_array', [])

            if not gamma_array or len(gamma_array) == 0:
                st.warning(f"⚠️ No gamma_array found in response")
                return {}

            # Parse strike-level data
            strikes_data = []
            max_call_gamma = 0
            max_put_gamma = 0
            call_wall = 0
            put_wall = 0

            for strike_obj in gamma_array:
                # Skip empty objects
                if not strike_obj or 'strike' not in strike_obj:
                    continue

                strike = float(strike_obj['strike'])
                call_gamma = abs(float(strike_obj.get('call_gamma', 0)))
                put_gamma = abs(float(strike_obj.get('put_gamma', 0)))

                strikes_data.append({
                    'strike': strike,
                    'call_gamma': call_gamma,
                    'put_gamma': put_gamma
                })

                # Track max gamma for walls
                if call_gamma > max_call_gamma:
                    max_call_gamma = call_gamma
                    call_wall = strike

                if put_gamma > max_put_gamma:
                    max_put_gamma = put_gamma
                    put_wall = strike

            # Get spot price and flip point
            spot_price = float(ticker_data.get('price', 0))

            # Get implied volatility - try gammaOI first, then fall back to last_response
            implied_vol = 0.20  # Default 20% IV
            if 'implied_volatility' in ticker_data:
                # gammaOI includes aggregate data - use it directly!
                implied_vol = float(ticker_data.get('implied_volatility', 0.20))
            elif self.last_response:
                # Fall back to /gex/latest response if gammaOI doesn't include it
                last_ticker_data = self.last_response.get(symbol, {})
                implied_vol = float(last_ticker_data.get('implied_volatility', 0.20))

            # 7-day expected move: spot * IV * sqrt(7/252)
            import math
            seven_day_std = spot_price * implied_vol * math.sqrt(7 / 252)
            min_strike = spot_price - seven_day_std
            max_strike = spot_price + seven_day_std

            # Filter strikes to +/- 7 day std range
            strikes_data_filtered = [s for s in strikes_data if min_strike <= s['strike'] <= max_strike]

            # Calculate flip point from gamma_array (where net gamma crosses zero)
            flip_point = 0
            for i in range(len(gamma_array) - 1):
                if 'net_gamma_$_at_strike' in gamma_array[i] and 'net_gamma_$_at_strike' in gamma_array[i + 1]:
                    net_gamma_current = float(gamma_array[i].get('net_gamma_$_at_strike', 0))
                    net_gamma_next = float(gamma_array[i + 1].get('net_gamma_$_at_strike', 0))

                    # Check for sign change (zero crossing)
                    if net_gamma_current * net_gamma_next < 0:
                        strike_current = float(gamma_array[i]['strike'])
                        strike_next = float(gamma_array[i + 1]['strike'])
                        # Linear interpolation
                        flip_point = strike_current + (strike_next - strike_current) * (
                            -net_gamma_current / (net_gamma_next - net_gamma_current)
                        )
                        break

            profile = {
                'strikes': strikes_data_filtered,  # Use filtered strikes
                'spot_price': spot_price,
                'flip_point': flip_point if flip_point else spot_price,
                'call_wall': call_wall,
                'put_wall': put_wall,
                'symbol': symbol
            }

            # If gammaOI includes aggregate data, add it to profile to avoid separate /gex/latest call
            if has_aggregate_data:
                profile['aggregate_from_gammaOI'] = {
                    'net_gex': float(ticker_data.get('skew_adjusted_gex', 0)),
                    'implied_volatility': float(ticker_data.get('implied_volatility', 0)),
                    'put_call_ratio': float(ticker_data.get('put_call_ratio_open_interest', 0)),
                    'collection_date': ticker_data.get('collection_date', '')
                }

            return profile

        except Exception as e:
            import traceback
            error_msg = f"Error getting GEX profile from gammaOI: {str(e)}"
            st.error(f"❌ {error_msg}")
            st.code(traceback.format_exc())
            print(error_msg)
            traceback.print_exc()
            return {}

    def get_historical_gamma(self, symbol: str, days_back: int = 5) -> List[Dict]:
        """Fetch historical gamma data from Trading Volatility API with rate limiting"""
        import streamlit as st
        import requests
        from datetime import datetime, timedelta

        try:
            if not self.api_key:
                st.error("❌ Trading Volatility username not found in secrets!")
                return []

            # Check cache first (cache key includes symbol + days_back) - USING SHARED CACHE
            cache_key = f"history_{symbol}_{days_back}"
            if cache_key in TradingVolatilityAPI._shared_response_cache:
                cached_data, cached_time = TradingVolatilityAPI._shared_response_cache[cache_key]
                if time.time() - cached_time < TradingVolatilityAPI._shared_cache_duration:
                    print(f"✓ Using cached historical data for {symbol} (age: {time.time() - cached_time:.0f}s)")
                    return cached_data

            # RATE LIMITING: Wait before making API call
            self._wait_for_rate_limit()

            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            # Call Trading Volatility /gex/history endpoint
            response = requests.get(
                self.endpoint + '/gex/history',
                params={
                    'ticker': symbol,
                    'username': self.api_key,
                    'format': 'json',
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d')
                },
                headers={'Accept': 'application/json'},
                timeout=30
            )

            if response.status_code != 200:
                # Silently handle errors - don't display to user
                # The history endpoint is optional and errors shouldn't break the UI
                print(f"History endpoint returned status {response.status_code} for {symbol}")
                return []

            # Check if response has content before parsing JSON
            if not response.text or len(response.text.strip()) == 0:
                # Silently handle empty response
                print(f"History endpoint returned empty response for {symbol}")
                return []

            # Check for rate limit error BEFORE parsing JSON
            if "API limit exceeded" in response.text or "rate limit" in response.text.lower():
                # Silently handle rate limit - don't spam UI
                print(f"History endpoint rate limit hit for {symbol}")
                self._handle_rate_limit_error()
                return []

            # Try to parse JSON with better error handling
            try:
                json_response = response.json()
            except ValueError as json_err:
                # Check if error is due to rate limiting
                if "API limit exceeded" in response.text:
                    # Silently handle rate limit
                    print(f"History endpoint rate limit (JSON parse) for {symbol}")
                    self._handle_rate_limit_error()
                else:
                    # Silently handle invalid JSON
                    print(f"Invalid JSON from history endpoint: {str(json_err)}")
                return []

            history_data = json_response.get(symbol, [])
            result = history_data if isinstance(history_data, list) else []

            # Cache the successful result (USING SHARED CACHE)
            TradingVolatilityAPI._shared_response_cache[cache_key] = (result, time.time())
            self._reset_rate_limit_errors()  # Success, reset error counter

            return result

        except Exception as e:
            print(f"Error fetching historical gamma: {e}")
            return []

    def get_yesterday_data(self, symbol: str) -> Dict:
        """Get yesterday's GEX data for day-over-day comparison

        Uses date-based caching - yesterday's data is immutable for a given date,
        so we cache it for the entire day (until midnight when the date changes).
        This minimizes API calls to once per symbol per day.
        """
        import streamlit as st
        import time
        from datetime import datetime

        # Date-based cache key - includes today's date
        # Yesterday's data for 2025-10-26 is immutable, so cache remains valid all day
        today_date = datetime.now().strftime('%Y-%m-%d')
        cache_key = f"yesterday_{symbol}_{today_date}"

        # Check if we have cached data for today's date
        if cache_key in TradingVolatilityAPI._shared_response_cache:
            cached_data, cached_time = TradingVolatilityAPI._shared_response_cache[cache_key]
            # Cache is valid for the entire day (no time expiration check needed)
            # It will naturally expire when date changes and cache key changes
            print(f"✓ Using cached yesterday data for {symbol} from {today_date}")
            return cached_data

        # Fetch from API - only happens once per symbol per day
        print(f"⚡ Fetching yesterday data for {symbol} (will cache for entire day)")
        history = self.get_historical_gamma(symbol, days_back=2)

        if len(history) >= 2:
            # Return second most recent (yesterday)
            result = history[-2]
            # Cache with today's date - valid until tomorrow
            TradingVolatilityAPI._shared_response_cache[cache_key] = (result, time.time())
            return result
        elif len(history) == 1:
            # Only have today's data
            empty_result = {}
            TradingVolatilityAPI._shared_response_cache[cache_key] = (empty_result, time.time())
            return empty_result
        else:
            return {}

    def calculate_day_over_day_changes(self, current_data: Dict, yesterday_data: Dict) -> Dict:
        """Calculate day-over-day changes in key GEX metrics"""
        if not yesterday_data:
            return {}

        changes = {}

        metrics = [
            ('flip_point', 'gex_flip_price'),
            ('net_gex', 'skew_adjusted_gex'),
            ('implied_volatility', 'implied_volatility'),
            ('put_call_ratio', 'put_call_ratio_open_interest'),
            ('rating', 'rating'),
            ('gamma_formation', 'gamma_formation')
        ]

        for current_key, yesterday_key in metrics:
            current_val = float(current_data.get(current_key, 0))
            yesterday_val = float(yesterday_data.get(yesterday_key, 0))

            if yesterday_val != 0:
                change = current_val - yesterday_val
                pct_change = (change / yesterday_val) * 100

                # Determine trend
                if abs(pct_change) < 0.5:
                    trend = '→'  # Flat
                elif change > 0:
                    trend = '↑'  # Up
                else:
                    trend = '↓'  # Down

                changes[current_key] = {
                    'current': current_val,
                    'yesterday': yesterday_val,
                    'change': change,
                    'pct_change': pct_change,
                    'trend': trend
                }

        return changes

    def get_skew_data(self, symbol: str) -> Dict:
        """Fetch latest skew data from Trading Volatility API with aggressive rate limiting"""
        import streamlit as st
        import requests

        try:
            if not self.api_key:
                return {}

            # Check cache first (2-minute cache)
            cache_key = self._get_cache_key('skew/latest', symbol)
            cached_data = self._get_cached_response(cache_key)
            if cached_data:
                return cached_data.get(symbol, {})

            # Wait for rate limit before making request (includes circuit breaker check)
            self._wait_for_rate_limit()

            response = requests.get(
                self.endpoint + '/skew/latest',
                params={
                    'ticker': symbol,
                    'username': self.api_key,
                    'format': 'json'
                },
                headers={'Accept': 'application/json'},
                timeout=30
            )

            if response.status_code != 200:
                return {}

            # Check for rate limit error in response text
            if "API limit exceeded" in response.text:
                st.error(f"⚠️ API Rate Limit Hit - Using cached data for next few minutes")
                self._handle_rate_limit_error()
                # Return empty dict, let caller handle gracefully
                return {}

            # Check if response has content before parsing JSON
            if not response.text or len(response.text.strip()) == 0:
                st.warning(f"⚠️ Skew endpoint returned empty response - skipping for now")
                return {}

            # Try to parse JSON with better error handling
            try:
                json_response = response.json()
            except ValueError as json_err:
                # Check if error message contains rate limit info
                if "API limit exceeded" in response.text:
                    st.error(f"⚠️ API Rate Limit - Backing off for 30+ seconds")
                    self._handle_rate_limit_error()
                else:
                    st.warning(f"⚠️ Invalid JSON from skew endpoint - skipping")
                return {}

            # Success! Reset error counter
            self._reset_rate_limit_errors()

            # Cache the response for 2 minutes
            self._cache_response(cache_key, json_response)

            skew_data = json_response.get(symbol, {})

            return skew_data

        except Exception as e:
            st.error(f"❌ Error fetching skew data: {e}")
            print(f"Error fetching skew data: {e}")
            return {}

    def get_historical_skew(self, symbol: str, days_back: int = 30) -> List[Dict]:
        """Fetch historical skew data from Trading Volatility API"""
        import streamlit as st
        import requests
        from datetime import datetime, timedelta

        try:
            if not self.api_key:
                return []

            # Wait for rate limit before making request
            self._wait_for_rate_limit()

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            response = requests.get(
                self.endpoint + '/skew/history',
                params={
                    'ticker': symbol,
                    'username': self.api_key,
                    'format': 'json',
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d')
                },
                headers={'Accept': 'application/json'},
                timeout=30
            )

            if response.status_code != 200:
                return []

            # Check for rate limit error in response text
            if "API limit exceeded" in response.text:
                st.warning(f"⚠️ API Rate Limit Hit (skew history) - Circuit breaker activating")
                self._handle_rate_limit_error()
                return []

            # Check if response has content before parsing JSON
            if not response.text or len(response.text.strip()) == 0:
                return []

            # Try to parse JSON with better error handling
            try:
                json_response = response.json()
            except ValueError as json_err:
                # Check if error is due to rate limiting
                if "API limit exceeded" in response.text:
                    st.warning(f"⚠️ API Rate Limit - Backing off for 30+ seconds")
                    self._handle_rate_limit_error()
                else:
                    print(f"Invalid JSON from historical skew endpoint: {str(json_err)}")
                return []

            # Success! Reset error counter
            self._reset_rate_limit_errors()

            history_data = json_response.get(symbol, [])

            return history_data if isinstance(history_data, list) else []

        except Exception as e:
            print(f"Error fetching historical skew: {e}")
            return []

    def get_gex_levels(self, symbol: str) -> Dict:
        """
        Fetch GEX levels (GEX_0, GEX_1, GEX_2, GEX_3) and STD levels from Trading Volatility API
        These levels represent key gamma support/resistance zones where dealers hedge heavily
        """
        import streamlit as st
        import requests

        try:
            if not self.api_key:
                return {}

            # Check cache first (5-minute cache like other endpoints)
            cache_key = self._get_cache_key('gex/levels', symbol)
            cached_data = self._get_cached_response(cache_key)
            if cached_data:
                return cached_data

            # Wait for rate limit before making request
            self._wait_for_rate_limit()

            response = requests.get(
                self.endpoint + '/gex/levels',
                params={
                    'ticker': symbol,
                    'username': self.api_key,
                    'format': 'json'
                },
                headers={'Accept': 'application/json'},
                timeout=30
            )

            if response.status_code != 200:
                st.warning(f"⚠️ GEX Levels endpoint returned status {response.status_code}")
                return {}

            # Check for rate limit error
            if "API limit exceeded" in response.text:
                st.error(f"⚠️ API Rate Limit Hit")
                self._handle_rate_limit_error()
                return {}

            if not response.text or len(response.text.strip()) == 0:
                return {}

            try:
                json_response = response.json()
            except ValueError:
                if "API limit exceeded" in response.text:
                    self._handle_rate_limit_error()
                return {}

            # Success! Reset error counter
            self._reset_rate_limit_errors()

            # Cache the response
            self._cache_response(cache_key, json_response)

            # Debug: Log the raw response structure
            print(f"DEBUG GEX Levels API Response for {symbol}: {json_response}")

            # Parse the response - API may return data directly or nested under symbol
            # Try direct access first, then nested
            ticker_data = json_response if isinstance(json_response, dict) and 'GEX_0' in json_response else json_response.get(symbol, {})

            if not ticker_data:
                st.warning(f"⚠️ No GEX Levels data found for {symbol}. API Response: {json_response}")
                return {}

            # Extract levels with better error handling
            def safe_float(value, default=0):
                """Safely convert to float"""
                try:
                    return float(value) if value not in [None, '', 'null'] else default
                except (ValueError, TypeError):
                    return default

            levels = {
                'gex_flip': safe_float(ticker_data.get('gex_flip') or ticker_data.get('Gex Flip')),
                'gex_0': safe_float(ticker_data.get('GEX_0')),
                'gex_1': safe_float(ticker_data.get('GEX_1')),
                'gex_2': safe_float(ticker_data.get('GEX_2')),
                'gex_3': safe_float(ticker_data.get('GEX_3')),
                'std_1day_pos': safe_float(ticker_data.get('+1STD (1-day)')),
                'std_1day_neg': safe_float(ticker_data.get('-1STD (1-day)')),
                'std_7day_pos': safe_float(ticker_data.get('+1STD (7-day)')),
                'std_7day_neg': safe_float(ticker_data.get('-1STD (7-day)')),
                'symbol': symbol
            }

            print(f"DEBUG Parsed GEX Levels: {levels}")
            return levels

        except Exception as e:
            st.error(f"❌ Error fetching GEX levels: {e}")
            print(f"Error fetching GEX levels: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_gamma_by_expiration(self, symbol: str, expiration: str = '1') -> Dict:
        """
        Fetch gamma data for a specific expiration date

        Args:
            symbol: Ticker symbol (e.g., 'SPY')
            expiration: Expiration identifier:
                - '0' = combined (all expirations)
                - '1' = nearest expiration
                - '2' = nearest monthly expiration
                - '2024-10-30' = specific date (YYYY-MM-DD format)

        Returns:
            Dict with gamma_array showing strike-level gamma for that expiration
        """
        import streamlit as st
        import requests

        try:
            if not self.api_key:
                return {}

            # Check cache first (5-minute cache)
            cache_key = self._get_cache_key(f'gex/gamma_exp_{expiration}', symbol)
            cached_data = self._get_cached_response(cache_key)
            if cached_data:
                return cached_data

            # Wait for rate limit before making request
            self._wait_for_rate_limit()

            response = requests.get(
                self.endpoint + '/gex/gamma',
                params={
                    'ticker': symbol,
                    'username': self.api_key,
                    'exp': expiration,
                    'format': 'json'
                },
                headers={'Accept': 'application/json'},
                timeout=30
            )

            if response.status_code != 200:
                return {}

            # Check for rate limit error
            if "API limit exceeded" in response.text:
                self._handle_rate_limit_error()
                return {}

            if not response.text or len(response.text.strip()) == 0:
                return {}

            try:
                json_response = response.json()
            except ValueError:
                if "API limit exceeded" in response.text:
                    self._handle_rate_limit_error()
                return {}

            # Success! Reset error counter
            self._reset_rate_limit_errors()

            # Cache the response
            self._cache_response(cache_key, json_response)

            ticker_data = json_response.get(symbol, {})

            if not ticker_data:
                return {}

            # Calculate total gamma for this expiration
            gamma_array = ticker_data.get('gamma_array', [])
            total_gamma = sum(abs(float(strike.get('gamma', 0))) for strike in gamma_array if strike)

            result = {
                'symbol': symbol,
                'expiration': expiration,
                'expiry_date': ticker_data.get('expiry', 'unknown'),
                'price': float(ticker_data.get('price', 0)),
                'collection_date': ticker_data.get('collection_date', ''),
                'gamma_array': gamma_array,
                'total_gamma': total_gamma
            }

            return result

        except Exception as e:
            print(f"Error fetching gamma by expiration: {e}")
            import traceback
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
            final_prices = []
            all_price_paths = []
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

                # Calculate price path - include starting price
                price_path = spot_price * np.exp(np.cumsum(np.insert(daily_returns, 0, 0)))
                all_price_paths.append(price_path)
                final_prices.append(price_path[-1])

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
            final_prices = np.array(final_prices)
            all_price_paths = np.array(all_price_paths)

            # Sample some paths for visualization (max 100 paths)
            sample_indices = np.linspace(0, self.num_simulations - 1, min(100, self.num_simulations), dtype=int)
            price_paths_sample = all_price_paths[sample_indices]

            result = {
                'probability_hit_flip': (hit_flip_count / self.num_simulations) * 100,
                'probability_hit_wall': (hit_wall_count / self.num_simulations) * 100,
                'expected_final_price': np.mean(final_prices),
                'median_final_price': np.median(final_prices),
                'std_final_price': np.std(final_prices),
                'max_gain_percent': np.percentile(max_gains, 95),  # 95th percentile
                'avg_gain_percent': np.mean(max_gains),
                'final_price_distribution': final_prices.tolist(),
                'price_paths_sample': price_paths_sample,
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
