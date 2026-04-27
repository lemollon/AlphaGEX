# core_classes_and_engines.py
"""
Core Classes and Engines for AlphaGEX Trading System
Handles GEX calculations, data fetching, and trading strategy logic
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Tuple, Optional
import requests
from scipy import stats
from dataclasses import dataclass
import time
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Import intelligent rate limiter
try:
    from utils.rate_limiter import trading_volatility_limiter
    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False
    print("⚠️ rate_limiter.py not found - using fallback rate limiting")

# Optional imports
try:
    import yfinance as yf
except ImportError:
    yf = None

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
            if not data.empty and len(data) > 0:
                self.spot_price = float(data['Close'].iloc[-1])
            else:
                # Fallback to daily data
                data = self.ticker.history(period="5d")
                if not data.empty and len(data) > 0:
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

        # PERFORMANCE FIX: Vectorized Greeks calculation (was using iterrows)
        # Get arrays for vectorized computation
        strikes = option_data['strike'].values
        dte_values = option_data.get('dte', pd.Series([5] * len(option_data))).fillna(5).values
        iv_values = option_data.get('impliedVolatility', pd.Series([0.20] * len(option_data))).fillna(0.20).values
        moneyness = option_data['moneyness'].values
        option_types = option_data.get('optionType', pd.Series(['call'] * len(option_data))).values

        # Distance from ATM (vectorized)
        atm_distance = np.abs(1 - moneyness)

        # Simplified gamma: highest at ATM, decreases with distance (vectorized)
        base_gamma = 0.05 * np.exp(-atm_distance * 10)  # Peak at ATM
        time_factor = 1 / np.sqrt(np.maximum(dte_values, 0.5))  # Increases as expiration approaches
        vol_factor = 1 / np.maximum(iv_values, 0.1)  # Higher vol = lower gamma

        gamma_values = base_gamma * time_factor * vol_factor * 0.01  # Scale down
        option_data['gamma'] = gamma_values

        # Delta calculation (vectorized)
        # d1 = (ln(S/K) + 0.5*σ²*T) / (σ*√T)
        sqrt_dte = np.sqrt(np.maximum(dte_values, 0.5) / 365)
        d1 = (np.log(spot / strikes) + 0.5 * iv_values**2 * dte_values / 365) / (iv_values * sqrt_dte)

        # Delta depends on option type (vectorized)
        is_call = np.array([ot == 'call' for ot in option_types])
        delta_call = 0.5 + 0.5 * stats.norm.cdf(d1)
        delta_put = -0.5 + 0.5 * stats.norm.cdf(d1)
        delta_values = np.where(is_call, delta_call, delta_put)

        option_data['delta'] = delta_values
        option_data['theta'] = -0.01 * gamma_values * spot * iv_values  # Simplified theta (vectorized)
        option_data['vega'] = 0.01 * gamma_values * spot * sqrt_dte  # Simplified vega (vectorized)

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
                neg_gex_df = strike_gex[strike_gex['strike'] == last_negative]['cumulative_gex']
                pos_gex_df = strike_gex[strike_gex['strike'] == first_positive]['cumulative_gex']

                if neg_gex_df.empty or pos_gex_df.empty:
                    self.gamma_flip = self.spot_price
                    return self.gamma_flip

                neg_gex = neg_gex_df.iloc[0]
                pos_gex = pos_gex_df.iloc[0]

                # Weighted average based on distance from zero
                denom = abs(neg_gex) + abs(pos_gex)
                if denom == 0:
                    weight_neg = weight_pos = 0.5
                else:
                    weight_neg = abs(pos_gex) / denom
                    weight_pos = abs(neg_gex) / denom
                
                self.gamma_flip = last_negative * weight_neg + first_positive * weight_pos
            else:
                self.gamma_flip = self.spot_price
        else:
            # If all GEX is one-sided, flip is at the extreme
            if strike_gex.empty or len(strike_gex) == 0:
                self.gamma_flip = self.spot_price
            elif strike_gex['cumulative_gex'].iloc[-1] > 0:
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

    def analyze_strike_volume_activity(self) -> pd.DataFrame:
        """
        Analyze volume activity at high open interest strikes to detect dealer hedging

        This identifies WHERE dealers are actively hedging by comparing volume to OI
        at strikes with significant positioning.

        Returns:
            DataFrame with columns:
            - strike: Option strike price
            - open_interest: Total OI at strike
            - volume: Today's volume at strike
            - volume_oi_ratio: Volume/OI ratio (>2.0 = active hedging)
            - gex: Gamma exposure at strike
            - distance_from_spot: Distance from current price (%)
            - hedging_intensity: Classification of hedging activity
            - interpretation: Human-readable explanation
        """
        if self.options_data is None or self.options_data.empty:
            return pd.DataFrame()

        # Aggregate by strike
        strike_analysis = self.options_data.groupby('strike').agg({
            'open_interest': 'sum',
            'volume': 'sum',
            'gex': 'sum'
        }).reset_index()

        # Calculate volume/OI ratio
        strike_analysis['volume_oi_ratio'] = strike_analysis['volume'] / (strike_analysis['open_interest'] + 1)

        # Distance from spot
        strike_analysis['distance_from_spot'] = (
            (strike_analysis['strike'] - self.spot_price) / self.spot_price
        ) * 100

        # Calculate OI percentile (identify high OI strikes)
        strike_analysis['oi_percentile'] = strike_analysis['open_interest'].rank(pct=True) * 100

        # Classify hedging intensity
        def classify_hedging(row):
            vol_oi = row['volume_oi_ratio']
            oi_pct = row['oi_percentile']

            # Only consider strikes with significant OI (top 20%)
            if oi_pct < 80:
                return 'low_oi', 'Low open interest - not significant for hedging analysis'

            # Analyze volume/OI ratio at high OI strikes
            if vol_oi > 5.0:
                return 'extreme', 'EXTREME hedging activity - dealers actively adjusting positions'
            elif vol_oi > 3.0:
                return 'heavy', 'Heavy hedging - significant dealer rebalancing happening'
            elif vol_oi > 2.0:
                return 'moderate', 'Moderate hedging - dealers responding to price movement'
            elif vol_oi > 1.0:
                return 'light', 'Light activity - normal turnover, not aggressive hedging'
            else:
                return 'minimal', 'Minimal activity - no significant dealer hedging detected'

        strike_analysis[['hedging_intensity', 'interpretation']] = strike_analysis.apply(
            classify_hedging, axis=1, result_type='expand'
        )

        # Sort by volume/OI ratio (most active first)
        strike_analysis = strike_analysis.sort_values('volume_oi_ratio', ascending=False)

        # Only return strikes with significant OI (top 20%) for cleaner output
        high_oi_strikes = strike_analysis[strike_analysis['oi_percentile'] >= 80].copy()

        return high_oi_strikes[[
            'strike', 'open_interest', 'volume', 'volume_oi_ratio',
            'gex', 'distance_from_spot', 'hedging_intensity', 'interpretation'
        ]]

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
    # Import config for rate limiting (4 seconds instead of 20 - matches API quota)
    try:
        from config import RateLimitConfig
        _shared_min_request_interval = RateLimitConfig.MIN_REQUEST_INTERVAL
    except ImportError:
        _shared_min_request_interval = 4.0  # Fallback to 4 seconds
    _shared_circuit_breaker_active = False
    _shared_circuit_breaker_until = 0
    _shared_consecutive_rate_limit_errors = 0
    _shared_api_call_count = 0
    _shared_cache_duration = 300  # Cache responses for 5 minutes (300 seconds)
    _shared_api_call_count_minute = 0
    _shared_minute_reset_time = 0

    # CLASS-LEVEL (SHARED) response cache - shared across ALL instances
    _shared_response_cache = {}
    # NOTE: Cache duration is now DYNAMIC based on weekend vs weekday
    # See _get_cache_duration() method for details

    def __init__(self):
        import time
        import os

        # Read API key from environment variables (Render deployment)
        # NO STREAMLIT - This is a FastAPI + React app, not Streamlit!
        # Support multiple env var names for flexibility
        self.api_key = (
            os.getenv("TRADING_VOLATILITY_API_KEY") or
            os.getenv("TRADINGVOL_API_KEY") or  # Short form used in some configs
            os.getenv("TV_USERNAME") or
            os.getenv("tv_username") or
            ""
        )

        # Fallback: Load from secrets.toml for LOCAL DEVELOPMENT ONLY
        if not self.api_key:
            try:
                import toml
                secrets_path = os.path.join(os.path.dirname(__file__), 'secrets.toml')
                if os.path.exists(secrets_path):
                    secrets = toml.load(secrets_path)
                    self.api_key = (
                        secrets.get("tradingvolatility_username") or
                        secrets.get("tv_username") or
                        secrets.get("TRADING_VOLATILITY_API_KEY") or
                        ""
                    )
            except (FileNotFoundError, Exception):
                pass  # Secrets file not available, using env vars

        # Read endpoint from environment variables with fallback
        self.endpoint = (
            os.getenv("TRADING_VOLATILITY_ENDPOINT") or
            os.getenv("ENDPOINT") or
            "https://stocks.tradingvolatility.net/api"
        )

        # v2 API: Bearer token (Stripe sub_xxx style identifier from TV billing).
        # The v1 query-param auth is deprecated as of TV's January 2026 migration.
        # We accept TRADING_VOLATILITY_API_TOKEN as the canonical name; we do NOT fall
        # back to TRADING_VOLATILITY_API_KEY/TV_USERNAME because those typically hold
        # the legacy username (e.g. "I-RWFNBLR2S1DP"), which v2 will reject with 401/403.
        self.v2_token = os.getenv("TRADING_VOLATILITY_API_TOKEN") or ""

        # Local-dev fallback via secrets.toml
        if not self.v2_token:
            try:
                import toml
                secrets_path = os.path.join(os.path.dirname(__file__), 'secrets.toml')
                if os.path.exists(secrets_path):
                    secrets = toml.load(secrets_path)
                    self.v2_token = (
                        secrets.get("trading_volatility_api_token") or
                        secrets.get("TRADING_VOLATILITY_API_TOKEN") or
                        ""
                    )
            except Exception:
                pass

        # v2 base URL (separate env so the v1 endpoint can stay during transition)
        self.v2_base_url = (
            os.getenv("TRADING_VOLATILITY_V2_BASE_URL") or
            "https://stocks.tradingvolatility.net/api/v2"
        )

        if not self.v2_token:
            print("⚠️ TRADING_VOLATILITY_API_TOKEN not set. v2 API calls will return 'no_token' errors.")
            print("   Set this env var to your TV Bearer token (sub_xxx from billing page).")

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

    def _get_cache_duration(self) -> int:
        """
        Get dynamic cache duration based on market hours

        Cache Strategy (aligned with market close/open):
        - MARKET CLOSED PERIOD (Fri 4pm ET - Mon 9:30am ET): 24 hours
          * Friday after 4pm ET (3pm CT)
          * Saturday all day
          * Sunday all day
          * Monday before 9:30am ET (8:30am CT)
        - MARKET OPEN (Mon-Fri 9:30am-4pm ET): 5 minutes (active trading)
        - OVERNIGHT (Mon-Thu 4pm-9:30am): 4 hours (market opens next day)

        Returns:
            Cache duration in seconds
        """
        from datetime import datetime
        import pytz

        from zoneinfo import ZoneInfo
        ct_tz = ZoneInfo("America/Chicago")
        now_ct = datetime.now(ct_tz)
        day_of_week = now_ct.weekday()  # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday

        current_hour = now_ct.hour
        current_minute = now_ct.minute
        current_minutes = current_hour * 60 + current_minute

        market_open_minutes = 8 * 60 + 30  # 8:30 AM CT
        market_close_minutes = 15 * 60     # 3:00 PM CT

        # === FULL WEEKEND PERIOD: Friday close through Monday open ===

        # Saturday or Sunday: Market closed, cache for 24 hours
        if day_of_week in [5, 6]:
            return 86400  # 24 hours

        # Friday after 4pm ET (3pm CT): Market closed until Monday, cache for 24 hours
        if day_of_week == 4 and current_minutes >= market_close_minutes:
            return 86400  # 24 hours

        # Monday before 9:30am ET: Market still closed, cache for 24 hours
        if day_of_week == 0 and current_minutes < market_open_minutes:
            return 86400  # 24 hours

        # === TRADING HOURS: Fresh data needed ===

        # During trading hours (Mon-Fri 9:30am-4pm ET): Cache for 5 minutes
        if market_open_minutes <= current_minutes < market_close_minutes:
            return 300  # 5 minutes

        # === OVERNIGHT PERIOD (Mon-Thu after close): Market opens next day ===

        # After hours (Mon-Thu 4pm onwards): Cache for 4 hours
        return 14400  # 4 hours

    def _get_cache_key(self, endpoint: str, symbol: str) -> str:
        """Generate cache key for API responses"""
        return f"{endpoint}_{symbol}"

    def _get_cached_response(self, cache_key: str):
        """Get cached response if still valid (SHARED cache across all instances)"""
        import time
        if cache_key in TradingVolatilityAPI._shared_response_cache:
            cached_data, timestamp = TradingVolatilityAPI._shared_response_cache[cache_key]
            cache_duration = self._get_cache_duration()
            if time.time() - timestamp < cache_duration:
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
                print(f"  Parsing list format with {len(strike_data)} strikes...")
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
                    print(f"  ✅ Calculated from strike list: Call Wall ${call_wall:.2f}, Put Wall ${put_wall:.2f}")
                    return call_wall, put_wall

            # Format 2: Dict with strike keys and gamma values
            elif isinstance(strike_data, dict):
                print(f"  Parsing dict format with {len(strike_data)} entries...")

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
                        print(f"  ✅ Calculated from strike dict: Call Wall ${call_wall:.2f}, Put Wall ${put_wall:.2f}")
                        return call_wall, put_wall

                except (ValueError, IndexError):
                    # Keys are not strikes, might be field names
                    print("  Dict keys are not strikes, checking for call/put arrays...")

            return 0, 0

        except Exception as e:
            print(f"  ⚠️ Could not parse strike data: {e}")
            return 0, 0

    # ==========================================================================
    # v2 API LAYER (added Apr 2026 — migration from v1 query-param auth)
    #
    # v2 uses Bearer auth and a nested response schema. Internal `_v2_*` methods
    # are the raw transport layer; public methods (get_net_gamma, get_gex_levels,
    # etc.) are translation wrappers that consume these and re-shape responses
    # into the v1 dict shapes that 15+ existing call sites expect.
    # ==========================================================================

    def _v2_request(self, path: str, params: dict = None, cache: bool = True) -> Dict:
        """
        Make a request to the Trading Volatility v2 API.

        Args:
            path: Path component starting with '/' (e.g. '/tickers/SPY/market-structure').
            params: Optional query parameters.
            cache: Whether to use the shared response cache (default True). Cache TTL
                follows _get_cache_duration() and is shared with v1 caching.

        Returns:
            On success: parsed JSON response (dict).
            On failure: dict with 'error' key. Never raises — callers can branch on
            'error' presence cleanly.

        Failure modes signaled via 'error' key:
            - 'no_token' — TRADING_VOLATILITY_API_TOKEN env var unset
            - 'rate_limit_timeout' — local rate limiter could not acquire slot
            - 'rate_limit (status_code)' — TV server returned rate-limit response
            - 'unauthorized' — 401 (bad/expired Bearer token)
            - 'forbidden: ...' — 403 (subscription does not cover resource)
            - 'not_found: ...' — 404
            - 'http_NNN: ...' — other non-200 status
            - 'request_exception: ...' — network failure
            - 'invalid_json: ...' — server returned non-JSON
            - 'empty_response' — server returned 200 with no body
        """
        import requests

        if not self.v2_token:
            return {'error': 'no_token'}

        path_norm = path if path.startswith('/') else '/' + path

        # Cache key — keep stable ordering of params so cache hits work
        params_norm = dict(sorted((params or {}).items()))
        cache_key = f"v2:{path_norm}:{params_norm}"

        if cache:
            cached = self._get_cached_response(cache_key)
            if cached is not None:
                return cached

        # Use the shared rate limiter (same instance as v1) — TV's per-account
        # quotas apply across both API versions, so sharing is correct.
        if RATE_LIMITER_AVAILABLE:
            if not trading_volatility_limiter.wait_if_needed(timeout=60):
                return {'error': 'rate_limit_timeout'}
        else:
            self._wait_for_rate_limit()

        url = f"{self.v2_base_url.rstrip('/')}{path_norm}"

        try:
            response = requests.get(
                url,
                params=params_norm or None,
                headers={
                    'Authorization': f'Bearer {self.v2_token}',
                    'Accept': 'application/json',
                },
                timeout=120,
            )
        except requests.exceptions.RequestException as e:
            return {'error': f'request_exception: {e!r}'}

        # Server-side rate-limit detection
        if response.status_code == 429:
            self._handle_rate_limit_error()
            return {'error': 'rate_limit (429)'}

        if response.status_code == 401:
            return {'error': 'unauthorized: invalid bearer token'}

        if response.status_code == 403:
            try:
                err = response.json()
                msg = err.get('error', {}).get('message', response.text[:200])
            except Exception:
                msg = response.text[:200]
            return {'error': f'forbidden: {msg}'}

        if response.status_code == 404:
            return {'error': f'not_found: {path_norm}'}

        if response.status_code == 304:
            # Conditional GET match. We don't currently send If-None-Match, so this
            # shouldn't happen, but if it does and we have a cached value, return it.
            cached = self._get_cached_response(cache_key)
            return cached if cached is not None else {'error': 'http_304_no_cache'}

        if response.status_code != 200:
            text_lower = response.text.lower()
            if 'rate' in text_lower or 'limit exceeded' in text_lower:
                self._handle_rate_limit_error()
                return {'error': f'rate_limit ({response.status_code})'}
            return {'error': f'http_{response.status_code}: {response.text[:200]}'}

        if not response.text or not response.text.strip():
            return {'error': 'empty_response'}

        try:
            data = response.json()
        except ValueError as e:
            return {'error': f'invalid_json: {e!r}'}

        self._reset_rate_limit_errors()

        if cache:
            self._cache_response(cache_key, data)

        return data

    # ---- Raw v2 endpoint methods (1:1 with documented routes) ----

    def _v2_ticker_state(self, symbol: str, include: str = None) -> Dict:
        """GET /tickers/{ticker} — canonical compact ticker state snapshot."""
        params = {'include': include} if include else None
        return self._v2_request(f"/tickers/{symbol}", params)

    def _v2_market_structure(self, symbol: str, include: str = None) -> Dict:
        """GET /tickers/{ticker}/market-structure — assembled interpretation layer."""
        params = {'include': include} if include else None
        return self._v2_request(f"/tickers/{symbol}/market-structure", params)

    def _v2_explain(self, symbol: str, view: str = None) -> Dict:
        """GET /tickers/{ticker}/explain — deterministic plain-English summary + tags."""
        params = {'view': view} if view else None
        return self._v2_request(f"/tickers/{symbol}/explain", params)

    def _v2_levels(self, symbol: str) -> Dict:
        """GET /tickers/{ticker}/levels — gamma flip + GEX_0..GEX_4 + ±1σ levels."""
        return self._v2_request(f"/tickers/{symbol}/levels")

    def _v2_gamma_curve(self, symbol: str, exp: str = "combined", realtime: bool = False) -> Dict:
        """GET /tickers/{ticker}/curves/gamma — strike-level net gamma curve.

        exp: 'combined' | 'nearest' | 'first_weekly' | 'first_monthly' | 'YYYY-MM-DD'
        realtime: True forces a fresh pull (only valid during trading hours).
        """
        params = {'exp': exp}
        if realtime:
            params['realtime'] = 'true'
        # Realtime/dated pulls bypass cache so the user gets fresh data
        use_cache = not realtime and exp in ('combined', 'nearest', 'first_weekly', 'first_monthly')
        return self._v2_request(f"/tickers/{symbol}/curves/gamma", params, cache=use_cache)

    def _v2_gamma_expirations(self, symbol: str) -> Dict:
        """GET /tickers/{ticker}/curves/gamma/expirations — multi-bucket gamma decomposition."""
        return self._v2_request(f"/tickers/{symbol}/curves/gamma/expirations")

    def _v2_gex_by_strike(self, symbol: str, exp: str = "combined") -> Dict:
        """GET /tickers/{ticker}/curves/gex_by_strike — net GEX with call/put contributions."""
        return self._v2_request(f"/tickers/{symbol}/curves/gex_by_strike", {'exp': exp})

    def _v2_series(self, symbol: str, metrics, window: str = "180d") -> Dict:
        """GET /tickers/{ticker}/series — historical metric time series.

        metrics: list of metric keys (see TV spec metric_catalog) OR comma-separated string.
        window: '30d' | '180d' | '1y' | '2y' etc.
        """
        if isinstance(metrics, (list, tuple)):
            metrics_str = ','.join(metrics)
        else:
            metrics_str = str(metrics)
        return self._v2_request(
            f"/tickers/{symbol}/series",
            {'metrics': metrics_str, 'window': window},
        )

    def _v2_options_volume(self, symbol: str, exp: str) -> Dict:
        """GET /tickers/{ticker}/options/volume — strike-by-strike volume for one expiry."""
        return self._v2_request(f"/tickers/{symbol}/options/volume", {'exp': exp})

    def _v2_trade_setup(self, symbol: str) -> Dict:
        """GET /agent/trade-setup/{ticker} — compact trader-facing recommendation payload."""
        return self._v2_request(f"/agent/trade-setup/{symbol}")

    def _v2_top_setups(self, filters: dict = None) -> Dict:
        """GET /top-setups — cross-ticker ranking by opportunity_score.

        filters: optional dict with keys per spec (limit, min_score, regime, trade_bias,
                 trend_state, momentum_state, realized_vol_state, recommended_direction,
                 price_min, price_max, iv_rank_min, iv_rank_max, ivAtMaxDelta_min,
                 ivAtMaxDelta_max, ttl).
        """
        return self._v2_request("/top-setups", filters)

    def get_net_gamma(self, symbol: str) -> Dict:
        """Fetch net gamma exposure data via TV v2 API.

        Returns a dict with v1-compatible keys so existing call sites need
        no changes:
            symbol, spot_price, net_gex, flip_point, call_wall, put_wall,
            put_call_ratio, implied_volatility, collection_date, raw_data

        Also includes v2-only enrichment fields that older callers ignore:
            speculative_interest_score, call_regime, expected_move_pct_1d,
            expected_move_pct_1w, pct_gamma_expiring, structure_regime,
            signal, bias, headline, tags, drivers, api_version

        Internally calls /tickers/{symbol}/market-structure (primary) and
        /tickers/{symbol}/curves/gex_by_strike (walls). v1 also made up
        to 2 calls when walls weren't in the snapshot, so rate-limit
        pressure is unchanged.

        IV note: /market-structure does not surface ATM IV. We return 0.0
        here for compatibility with v1 callers that already tolerated 0
        IV from fallback paths. Callers that need real IV should use
        get_skew_data() or read 'put_call_25d_iv_premium_pct' from
        raw_data.supporting_factors.
        """
        if not self.v2_token:
            return {'error': 'API key not configured (TRADING_VOLATILITY_API_TOKEN unset)'}

        try:
            ms = self._v2_market_structure(symbol)
            if 'error' in ms:
                err = ms['error']
                # Surface rate-limit failures with the legacy error string so
                # callers that branch on 'rate_limit' continue to work.
                if 'rate_limit' in err:
                    return {'error': 'rate_limit'}
                return {'error': f'market_structure: {err}'}

            # v2 envelopes payload under 'data'; tolerate flat too.
            ms_data = ms.get('data', ms)
            ms_meta = ms.get('meta', {}) or {}

            if not isinstance(ms_data, dict) or not ms_data:
                return {'error': 'No ticker data in response'}

            key_levels = ms_data.get('key_levels', {}) or {}
            sf = ms_data.get('supporting_factors', {}) or {}
            drivers = ms_data.get('drivers', {}) or {}

            spot_price = float(key_levels.get('spot') or sf.get('spot') or 0)
            flip_point = float(key_levels.get('gamma_flip') or sf.get('gamma_flip') or 0)
            net_gex = float(sf.get('gamma_notional_per_1pct_move_usd') or 0)
            pcr_oi = float(sf.get('pcr_oi') or 0)
            spec_score = float(sf.get('speculative_interest_score') or 0)
            call_regime = sf.get('call_regime') or ''
            em_1d_pct = float(sf.get('expected_move_pct_1d') or 0)
            em_1w_pct = float(sf.get('expected_move_pct_1w') or 0)
            pct_gamma_expiring = float(sf.get('pct_gamma_expiring_nearest_expiry') or 0)

            # ATM IV is not in /market-structure. v1 callers tolerated 0
            # from fallback paths; we preserve that behavior here.
            atm_iv = 0.0

            # Walls + per-side totals — single extra call to /curves/gex_by_strike.
            # Matches v1 2-call pattern when walls were missing from snapshot.
            call_wall = None
            put_wall = None
            total_call_gex = 0.0
            total_put_gex = 0.0
            try:
                strikes_resp = self._v2_gex_by_strike(symbol, exp='combined')
                if 'error' not in strikes_resp:
                    strikes_data = strikes_resp.get('data', strikes_resp)
                    points = strikes_data.get('points', []) or []
                    max_call_gex = 0.0
                    max_put_gex = 0.0
                    for p in points:
                        if not isinstance(p, dict):
                            continue
                        s = float(p.get('strike', 0) or 0)
                        c_raw = float(p.get('call', 0) or 0)
                        pu_raw = float(p.get('put', 0) or 0)
                        c = abs(c_raw)
                        pu = abs(pu_raw)
                        total_call_gex += c_raw
                        total_put_gex += pu_raw
                        if c > max_call_gex:
                            max_call_gex = c
                            call_wall = s
                        if pu > max_put_gex:
                            max_put_gex = pu
                            put_wall = s
                    if call_wall and put_wall:
                        print(f"✅ {symbol} walls (v2): Call ${call_wall:.2f}, Put ${put_wall:.2f}")
            except Exception as wall_err:
                print(f"⚠️ {symbol} wall fetch failed: {wall_err}")

            collection_date = ms_meta.get('asof') or ms_data.get('asof') or ''

            # Derived fields callers use:
            #  - distance_to_flip_pct: from sf.distance_to_flip_pct (v2 spec) OR derived
            #    from data.derived.dist_to_gex_flip_pct on the raw /tickers/X response.
            #    /market-structure exposes it under supporting_factors per spec.
            #  - gex_regime: classical "spot vs flip" regime classifier.
            #    POSITIVE when spot > flip, NEGATIVE when spot < flip, NEUTRAL otherwise.
            #    Many callers (SOLOMON, FAITH, scheduler, AI routes) read this with
            #    a 'NEUTRAL' or 'UNKNOWN' default. v1 didn't populate it explicitly
            #    either, but populating it from v2 here removes dependence on default.
            distance_to_flip_pct = float(
                sf.get('distance_to_flip_pct')
                or ms_data.get('derived', {}).get('dist_to_gex_flip_pct')
                or 0
            )
            if spot_price > 0 and flip_point > 0:
                if spot_price > flip_point:
                    gex_regime = 'POSITIVE'
                elif spot_price < flip_point:
                    gex_regime = 'NEGATIVE'
                else:
                    gex_regime = 'NEUTRAL'
            else:
                gex_regime = 'UNKNOWN'

            result = {
                # ---- v1-compatible keys (do not rename; many callers read these) ----
                'symbol': symbol,
                'spot_price': spot_price,
                'net_gex': net_gex,
                'flip_point': flip_point,
                'call_wall': call_wall,
                'put_wall': put_wall,
                'put_call_ratio': pcr_oi,
                'implied_volatility': atm_iv,
                'collection_date': collection_date,
                'raw_data': ms_data,
                # ---- Fields many callers read with a default (now populated explicitly) ----
                'gex_regime': gex_regime,                  # POSITIVE / NEGATIVE / NEUTRAL / UNKNOWN
                'distance_to_flip_pct': distance_to_flip_pct,
                'total_call_gex': total_call_gex,
                'total_put_gex': total_put_gex,
                'call_gex': total_call_gex,                # alias used by some callers
                'put_gex': total_put_gex,
                # ---- v2-only enrichment (back-compat: callers ignore unknown keys) ----
                'speculative_interest_score': spec_score,
                'call_regime': call_regime,
                'expected_move_pct_1d': em_1d_pct,
                'expected_move_pct_1w': em_1w_pct,
                'pct_gamma_expiring': pct_gamma_expiring,
                'structure_regime': ms_data.get('structure_regime', ''),
                'signal': ms_data.get('signal', ''),
                'bias': ms_data.get('bias', ''),
                'headline': ms_data.get('headline', ''),
                'tags': ms_data.get('tags', []) or [],
                'drivers': drivers,
                'api_version': 'v2',
            }

            # Retained for backward compat with callers that read last_response
            # (e.g. older paths in get_gex_profile / scan helpers).
            self.last_response = ms_data
            return result

        except Exception as e:
            import traceback
            error_msg = f"Error fetching data from Trading Volatility API (v2): {e}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            return {'error': str(e)}

    def get_gex_profile(self, symbol: str, expiration: str = None) -> Dict:
        """Detailed strike-level GEX profile via TV v2 API.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')
            expiration: Optional expiration filter:
                - None or '1' or 'nearest' → nearest expiration (mapped to 'nearest')
                - '2' or 'first_monthly' → first monthly (mapped to 'first_monthly')
                - 'first_weekly' → first weekly
                - 'YYYY-MM-DD' → specific date
                - 'combined' → all expirations combined

        Returns v1-compatible dict shape:
            symbol, spot_price, flip_point, call_wall, put_wall,
            strikes (list of {strike, call_gamma, put_gamma, total_gamma,
                              call_oi, put_oi, put_call_ratio}),
            _debug (cache + raw-strike diagnostics),
            aggregate_from_gammaOI (when v2 supplies aggregate fields)

        Empty dict {} on error. {'error': 'rate_limit', 'message': ...} on rate limit.

        v2 caveat: /curves/gex_by_strike does not return per-strike open interest;
        call_oi/put_oi/put_call_ratio fields are present (for v1 caller compat) but
        always 0. Callers that need OI must call /tickers/{symbol}/options/volume.
        """
        if not self.v2_token:
            return {}

        # Map v1 expiration codes to v2 exp parameter values
        exp_map = {
            '1': 'nearest',
            '2': 'first_monthly',
            'nearest': 'nearest',
            'first_monthly': 'first_monthly',
            'first_weekly': 'first_weekly',
            'combined': 'combined',
            None: 'combined',
        }
        exp_v2 = exp_map.get(expiration, expiration)  # passthrough for YYYY-MM-DD

        try:
            resp = self._v2_gex_by_strike(symbol, exp=exp_v2)
            if 'error' in resp:
                err = resp['error']
                if 'rate_limit' in err:
                    return {'error': 'rate_limit', 'message': err}
                if 'no_token' in err:
                    return {}
                # All other errors → empty dict to match v1
                print(f"⚠️ get_gex_profile v2 error for {symbol}: {err}")
                return {}

            data = resp.get('data', resp)
            if not isinstance(data, dict) or not data:
                return {}

            points = data.get('points', []) or []
            if not points:
                print(f"⚠️ /curves/gex_by_strike for {symbol} returned no points")
                return {}

            spot_price = float(data.get('price', 0) or 0)
            totals = data.get('totals', {}) or {}
            flip_from_totals = float(totals.get('gex_flip_price', 0) or 0)

            # Build full unfiltered strikes_data and find walls in unfiltered range first.
            strikes_data = []
            max_call_gamma_all = 0.0
            max_put_gamma_all = 0.0
            call_wall_all = 0.0
            put_wall_all = 0.0

            for p in points:
                if not isinstance(p, dict) or 'strike' not in p:
                    continue
                try:
                    strike = float(p['strike'])
                except (TypeError, ValueError):
                    continue
                # v2 'call' / 'put' may be signed (call usually +, put usually -)
                try:
                    call_raw = float(p.get('call', 0) or 0)
                except (TypeError, ValueError):
                    call_raw = 0.0
                try:
                    put_raw = float(p.get('put', 0) or 0)
                except (TypeError, ValueError):
                    put_raw = 0.0

                call_gamma = abs(call_raw)
                put_gamma = abs(put_raw)
                # v2 also gives 'net' directly; prefer it over reconstructing
                try:
                    total_gamma = float(p.get('net', call_raw + put_raw))
                except (TypeError, ValueError):
                    total_gamma = call_raw + put_raw

                strikes_data.append({
                    'strike': strike,
                    'call_gamma': call_gamma,
                    'put_gamma': put_gamma,
                    'total_gamma': total_gamma,
                    'call_oi': 0.0,    # v2 gex_by_strike does not include OI; see method docstring
                    'put_oi': 0.0,
                    'put_call_ratio': 0.0,
                })

                if call_gamma > max_call_gamma_all:
                    max_call_gamma_all = call_gamma
                    call_wall_all = strike
                if put_gamma > max_put_gamma_all:
                    max_put_gamma_all = put_gamma
                    put_wall_all = strike

            # Determine IV for the ±7-day std filter window (v1 used 0.20 default).
            # If a previous /market-structure call cached IV-adjacent data, use it;
            # otherwise default to 20% so the filter window math is conservative.
            try:
                from config import ImpliedVolatilityConfig
                implied_vol = ImpliedVolatilityConfig.DEFAULT_IV
            except ImportError:
                implied_vol = 0.20
            try:
                if isinstance(self.last_response, dict):
                    sf = self.last_response.get('supporting_factors', {}) or {}
                    pcr_iv_pct = sf.get('put_call_25d_iv_premium_pct')
                    if pcr_iv_pct is not None:
                        # Not actually IV — kept as a flag that we have ms data.
                        # Real IV must come from get_skew_data(); use default for the filter.
                        pass
            except Exception:
                pass

            import math
            seven_day_std = spot_price * implied_vol * math.sqrt(7 / 252) if spot_price > 0 else 0
            if seven_day_std > 0:
                min_strike = spot_price - seven_day_std
                max_strike = spot_price + seven_day_std
                strikes_data_filtered = [
                    s for s in strikes_data if min_strike <= s['strike'] <= max_strike
                ]
            else:
                strikes_data_filtered = strikes_data
                min_strike, max_strike = 0, 0

            # Recompute walls within filtered range
            max_call_filt = 0.0
            max_put_filt = 0.0
            call_wall_filt = call_wall_all
            put_wall_filt = put_wall_all
            for s in strikes_data_filtered:
                if s['call_gamma'] > max_call_filt:
                    max_call_filt = s['call_gamma']
                    call_wall_filt = s['strike']
                if s['put_gamma'] > max_put_filt:
                    max_put_filt = s['put_gamma']
                    put_wall_filt = s['strike']

            # Flip point: prefer v2 totals.gex_flip_price; otherwise compute zero-crossing.
            flip_point = flip_from_totals
            if not flip_point:
                # Sign-change interpolation on the filtered series
                arr = strikes_data_filtered if strikes_data_filtered else strikes_data
                for i in range(len(arr) - 1):
                    s_curr = arr[i]['strike']
                    s_next = arr[i + 1]['strike']
                    n_curr = arr[i]['total_gamma']
                    n_next = arr[i + 1]['total_gamma']
                    if n_curr * n_next < 0:
                        flip_point = s_curr + (s_next - s_curr) * (
                            -n_curr / (n_next - n_curr)
                        )
                        break
            if not flip_point:
                flip_point = spot_price

            first_raw = points[0] if points else {}

            profile = {
                'symbol': symbol,
                'spot_price': spot_price,
                'flip_point': flip_point,
                'call_wall': call_wall_filt,
                'put_wall': put_wall_filt,
                'strikes': strikes_data_filtered,
                '_debug': {
                    'used_cache': False,    # v2 cache hits are transparent inside _v2_request
                    'total_strikes_before_filter': len(strikes_data),
                    'total_strikes_after_filter': len(strikes_data_filtered),
                    'filter_min_strike': min_strike,
                    'filter_max_strike': max_strike,
                    'wall_unfiltered_call': call_wall_all,
                    'wall_unfiltered_put': put_wall_all,
                    'raw_api_first_strike': {
                        'strike': first_raw.get('strike'),
                        'call_gamma': first_raw.get('call', 0),
                        'put_gamma': first_raw.get('put', 0),
                        'call_gamma_type': type(first_raw.get('call')).__name__,
                        'put_gamma_type': type(first_raw.get('put')).__name__,
                    },
                    'processed_first_strike': strikes_data[0] if strikes_data else {},
                    'api_version': 'v2',
                },
            }

            # Aggregate fields from v2 totals (mirror v1's `aggregate_from_gammaOI`).
            if totals:
                profile['aggregate_from_gammaOI'] = {
                    'net_gex': float(totals.get('gex_value_per_1pct', 0) or 0),
                    'implied_volatility': 0.0,   # not surfaced in gex_by_strike; see method docstring
                    'put_call_ratio': float(totals.get('put_call_oi', 0) or 0),
                    'collection_date': data.get('asof', '') or '',
                }

            return profile

        except Exception as e:
            import traceback
            print(f"❌ Error getting GEX profile (v2): {e}")
            traceback.print_exc()
            return {}

    def get_historical_gamma(self, symbol: str, days_back: int = 5) -> List[Dict]:
        """Fetch historical gamma data via TV v2 /series endpoint.

        Returns a list of per-day dicts with keys callers expect (see
        backtest/backtest_options_strategies.py:184 for date-field detection):
            date              — YYYY-MM-DD timestamp string
            collection_date   — same as date (alias for v1 caller compat)
            gex_flip          — gamma flip price level
            net_gex           — gex_usd_per_1_pct_move
            pcr_oi            — put/call open interest ratio
            iv_rank           — IV rank 0-100

        Empty list [] on error (matches v1).
        """
        if not self.v2_token:
            return []

        try:
            window = f"{max(days_back, 1)}d"
            metrics = ['price', 'gex_flip', 'gex_usd_per_1_pct_move', 'pcr_oi', 'iv_rank', 'atm_iv']

            resp = self._v2_series(symbol, metrics, window=window)
            if 'error' in resp:
                print(f"history endpoint error for {symbol}: {resp['error']}")
                return []

            data = resp.get('data', resp)
            if not isinstance(data, dict):
                return []

            # /series may return either:
            # (a) data.points = [{t: '...', metric_a: x, metric_b: y, ...}, ...]
            # (b) data.series = {'metric_a': [...], 'metric_b': [...], 't': [...]}
            # Handle both.
            points = data.get('points') or []
            series_dict = data.get('series') or {}

            result = []

            if points and isinstance(points, list):
                for pt in points:
                    if not isinstance(pt, dict):
                        continue
                    ts = pt.get('t') or pt.get('timestamp') or pt.get('date') or ''
                    # Truncate to YYYY-MM-DD if it's a longer ISO string
                    if isinstance(ts, str) and len(ts) >= 10:
                        date_str = ts[:10]
                    else:
                        date_str = str(ts)
                    result.append({
                        'date': date_str,
                        'collection_date': date_str,
                        'price': float(pt.get('price', 0) or 0),
                        'gex_flip': float(pt.get('gex_flip', 0) or 0),
                        'net_gex': float(pt.get('gex_usd_per_1_pct_move', 0) or 0),
                        'pcr_oi': float(pt.get('pcr_oi', 0) or 0),
                        'put_call_ratio_open_interest': float(pt.get('pcr_oi', 0) or 0),
                        'iv_rank': float(pt.get('iv_rank', 0) or 0),
                        'atm_iv': float(pt.get('atm_iv', 0) or 0),
                        'implied_volatility': float(pt.get('atm_iv', 0) or 0),
                    })
            elif series_dict and isinstance(series_dict, dict):
                # Series-of-arrays form. Use 't' array as the timestamp axis.
                t_arr = series_dict.get('t') or series_dict.get('timestamps') or []
                length = len(t_arr) if t_arr else 0
                if length:
                    for i in range(length):
                        ts = t_arr[i] if i < len(t_arr) else ''
                        if isinstance(ts, str) and len(ts) >= 10:
                            date_str = ts[:10]
                        else:
                            date_str = str(ts)

                        def _safe(name, default=0.0):
                            arr = series_dict.get(name, [])
                            try:
                                return float(arr[i]) if i < len(arr) and arr[i] is not None else default
                            except (TypeError, ValueError):
                                return default

                        result.append({
                            'date': date_str,
                            'collection_date': date_str,
                            'price': _safe('price'),
                            'gex_flip': _safe('gex_flip'),
                            'net_gex': _safe('gex_usd_per_1_pct_move'),
                            'pcr_oi': _safe('pcr_oi'),
                            'put_call_ratio_open_interest': _safe('pcr_oi'),
                            'iv_rank': _safe('iv_rank'),
                            'atm_iv': _safe('atm_iv'),
                            'implied_volatility': _safe('atm_iv'),
                        })

            return result

        except Exception as e:
            print(f"Error fetching historical gamma (v2): {e}")
            return []

    def get_yesterday_data(self, symbol: str) -> Dict:
        """Get yesterday's GEX data for day-over-day comparison

        Uses date-based caching - yesterday's data is immutable for a given date,
        so we cache it for the entire day (until midnight when the date changes).
        This minimizes API calls to once per symbol per day.
        """
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
        """Fetch latest skew data via TV v2 API.

        Returns v1-compatible flat dict with these keys (callers read these):
            put_call_ratio  — from supporting_factors.pcr_oi
            skew            — approximate put/call IV ratio (≈ 1 + premium_pct/100);
                              v1 callers compare to 1.1/0.9 thresholds for PUT_HEAVY/
                              CALL_HEAVY classification
            iv_rank         — from /series metric (latest point), 0-100 scale, default 50
            symbol

        Plus v2-only enrichment:
            put_call_25d_iv_premium_pct — exact value (percent units per TV spec)
            pcr_volume                  — put/call volume ratio
            api_version='v2'

        Empty dict {} on error (matches v1).
        """
        if not self.v2_token:
            return {}

        try:
            ms = self._v2_market_structure(symbol)
            if 'error' in ms:
                return {}

            ms_data = ms.get('data', ms)
            sf = ms_data.get('supporting_factors', {}) or {}

            premium_pct = float(sf.get('put_call_25d_iv_premium_pct', 0) or 0)

            result = {
                'symbol': symbol,
                'put_call_ratio': float(sf.get('pcr_oi', 0) or 0),
                # v1's 'skew' was a ratio (put_iv / call_iv) ~0.9-1.1.
                # v2's put_call_25d_iv_premium_pct is the spread in percent points.
                # Approximate the legacy ratio so existing 1.1/0.9 thresholds in
                # backend/api/routes/ai_intelligence_routes.py:567 still work
                # directionally: positive premium → ratio > 1, negative → ratio < 1.
                'skew': 1.0 + premium_pct / 100.0,
                # v2 enrichment (callers can use exact values directly)
                'put_call_25d_iv_premium_pct': premium_pct,
                'pcr_volume': float(sf.get('pcr_volume', 0) or 0),
                'api_version': 'v2',
            }

            # IV rank from /series (extra call; cached so back-to-back calls reuse).
            iv_rank_default = 50.0
            try:
                series = self._v2_series(symbol, ['iv_rank'], window='5d')
                if 'error' not in series:
                    series_data = series.get('data', series)
                    points = series_data.get('points', []) or []
                    if points:
                        last_pt = points[-1]
                        if isinstance(last_pt, dict):
                            result['iv_rank'] = float(last_pt.get('iv_rank', iv_rank_default) or iv_rank_default)
                        else:
                            result['iv_rank'] = iv_rank_default
                    else:
                        result['iv_rank'] = iv_rank_default
                else:
                    result['iv_rank'] = iv_rank_default
            except Exception:
                result['iv_rank'] = iv_rank_default

            return result

        except Exception as e:
            print(f"❌ Error fetching skew data (v2): {e}")
            return {}

    def get_historical_skew(self, symbol: str, days_back: int = 30) -> List[Dict]:
        """Fetch historical skew data from Trading Volatility API"""
        import requests
        from datetime import datetime, timedelta

        try:
            if not self.api_key:
                return []

            # Use intelligent rate limiter if available
            if RATE_LIMITER_AVAILABLE:
                if not trading_volatility_limiter.wait_if_needed(timeout=60):
                    print("❌ Rate limit timeout - circuit breaker active")
                    return []
            else:
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
                timeout=120
            )

            if response.status_code != 200:
                return []

            # Check for rate limit error in response text
            if "API limit exceeded" in response.text:
                print(f"⚠️ API Rate Limit Hit (skew history) - Circuit breaker activating")
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
                    print(f"⚠️ API Rate Limit - Backing off for 30+ seconds")
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
        """Fetch GEX levels via TV v2 API.

        Returns the same flat dict shape as v1 so existing callers continue to work:
            symbol, gex_flip, gex_0..gex_4, std_1day_pos/neg, std_7day_pos/neg

        Empty dict {} on error (matches v1 behavior — many callers branch on
        empty-dict-returned).

        Falls back to /market-structure.key_levels for sigma bands when v2
        /levels response doesn't include them.
        """
        if not self.v2_token:
            return {}

        def safe_float(value, default=0.0):
            try:
                if value in (None, '', 'null'):
                    return default
                return float(value)
            except (ValueError, TypeError):
                return default

        try:
            resp = self._v2_levels(symbol)
            if 'error' in resp:
                print(f"⚠️ get_gex_levels v2 error for {symbol}: {resp['error']}")
                return {}

            data = resp.get('data', resp)
            if not isinstance(data, dict) or not data:
                return {}

            sigma = data.get('sigma_levels') or data.get('sigma') or {}
            if not isinstance(sigma, dict):
                sigma = {}

            levels = {
                'symbol': symbol,
                'gex_flip': safe_float(
                    data.get('gex_flip') or data.get('Gex Flip') or data.get('gamma_flip')
                ),
                'gex_0': safe_float(data.get('GEX_0') or data.get('gex_0')),
                'gex_1': safe_float(data.get('GEX_1') or data.get('gex_1')),
                'gex_2': safe_float(data.get('GEX_2') or data.get('gex_2')),
                'gex_3': safe_float(data.get('GEX_3') or data.get('gex_3')),
                'gex_4': safe_float(data.get('GEX_4') or data.get('gex_4')),
                'std_1day_pos': safe_float(
                    data.get('+1STD (1-day)') or data.get('price_plus_1_day_std')
                    or sigma.get('plus_1sigma_1d')
                ),
                'std_1day_neg': safe_float(
                    data.get('-1STD (1-day)') or data.get('price_minus_1_day_std')
                    or sigma.get('minus_1sigma_1d')
                ),
                'std_7day_pos': safe_float(
                    data.get('+1STD (7-day)') or data.get('price_plus_7_day_std')
                    or sigma.get('plus_1sigma_1w')
                ),
                'std_7day_neg': safe_float(
                    data.get('-1STD (7-day)') or data.get('price_minus_7_day_std')
                    or sigma.get('minus_1sigma_1w')
                ),
            }

            # If sigma bands or flip weren't in /levels, fall back to /market-structure.key_levels.
            # /market-structure has documented `key_levels.{gamma_flip, plus/minus_1sigma_1d/1w/1m, spot}`.
            need_fallback = (
                not levels['std_1day_pos'] or not levels['std_7day_pos']
                or not levels['gex_flip']
            )
            if need_fallback:
                try:
                    ms = self._v2_market_structure(symbol)
                    if 'error' not in ms:
                        ms_data = ms.get('data', ms)
                        kl = ms_data.get('key_levels', {}) or {}
                        if not levels['gex_flip']:
                            levels['gex_flip'] = safe_float(kl.get('gamma_flip'))
                        if not levels['std_1day_pos']:
                            levels['std_1day_pos'] = safe_float(kl.get('plus_1sigma_1d'))
                        if not levels['std_1day_neg']:
                            levels['std_1day_neg'] = safe_float(kl.get('minus_1sigma_1d'))
                        if not levels['std_7day_pos']:
                            levels['std_7day_pos'] = safe_float(kl.get('plus_1sigma_1w'))
                        if not levels['std_7day_neg']:
                            levels['std_7day_neg'] = safe_float(kl.get('minus_1sigma_1w'))
                except Exception:
                    pass  # fallback is best-effort

            return levels

        except Exception as e:
            print(f"❌ Error fetching GEX levels (v2): {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_gamma_by_expiration(self, symbol: str, expiration: str = '1') -> Dict:
        """Fetch gamma data for a specific expiration via TV v2 /curves/gamma.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')
            expiration: Expiration identifier:
                - '0' or 'combined' → all expirations combined
                - '1' or 'nearest' → nearest expiration
                - '2' or 'first_monthly' → first monthly expiration
                - 'first_weekly' → first weekly
                - 'YYYY-MM-DD' → specific date

        Returns v1-compatible dict shape:
            symbol, expiration, expiry_date, price, collection_date,
            gamma_array (list of {strike, gamma}), total_gamma
        Empty dict {} on error.
        """
        if not self.v2_token:
            return {}

        # Map v1 codes to v2 exp values
        exp_map = {
            '0': 'combined',
            '1': 'nearest',
            '2': 'first_monthly',
            'combined': 'combined',
            'nearest': 'nearest',
            'first_monthly': 'first_monthly',
            'first_weekly': 'first_weekly',
        }
        exp_v2 = exp_map.get(expiration, expiration)  # passthrough for YYYY-MM-DD

        try:
            resp = self._v2_gamma_curve(symbol, exp=exp_v2)
            if 'error' in resp:
                print(f"gamma_by_expiration v2 error for {symbol} (exp={exp_v2}): {resp['error']}")
                return {}

            data = resp.get('data', resp)
            if not isinstance(data, dict) or not data:
                return {}

            points = data.get('points', []) or []

            # v2 points have {strike, gamma}; preserve as v1 gamma_array shape
            gamma_array = []
            total_gamma = 0.0
            for p in points:
                if not isinstance(p, dict) or 'strike' not in p:
                    continue
                try:
                    strike = float(p['strike'])
                    gamma_val = float(p.get('gamma', 0) or 0)
                except (TypeError, ValueError):
                    continue
                gamma_array.append({'strike': strike, 'gamma': gamma_val})
                total_gamma += abs(gamma_val)

            return {
                'symbol': symbol,
                'expiration': expiration,
                'expiry_date': data.get('expiry', 'unknown') or 'unknown',
                'price': float(data.get('price', 0) or 0),
                'collection_date': data.get('asof', '') or '',
                'gamma_array': gamma_array,
                'total_gamma': total_gamma,
                'api_version': 'v2',
            }

        except Exception as e:
            print(f"Error fetching gamma by expiration (v2): {e}")
            import traceback
            traceback.print_exc()
            return {}

    # ==========================================================================
    # NEW v2 PUBLIC METHODS — expose richer v2 data that has no v1 equivalent.
    # These do NOT have backward-compat shape constraints; they return whatever
    # the v2 API natively returns (lightly normalized).
    # ==========================================================================

    def get_market_structure(self, symbol: str) -> Dict:
        """Full /tickers/{symbol}/market-structure response.

        Returns the assembled v2 interpretation layer:
            headline, signal, bias, structure_regime, expected_behavior,
            tags[], confidence, drivers{flip_context, gamma_tone, sentiment,
            skew_tone}, key_levels{spot, gamma_flip, plus/minus_1sigma_*},
            supporting_factors{call_regime, distance_to_flip_pct,
            expected_move_pct_1d/1w, gamma_flip, gamma_notional_per_1pct_move_usd,
            pcr_oi, pcr_volume, pct_gamma_expiring_nearest_expiry,
            put_call_25d_iv_premium_pct, speculative_interest_score, spot}

        Returns {} on error; populated dict on success.
        """
        if not self.v2_token:
            return {}
        try:
            resp = self._v2_market_structure(symbol)
            if 'error' in resp:
                return {}
            return resp.get('data', resp) or {}
        except Exception as e:
            print(f"Error fetching market structure (v2): {e}")
            return {}

    def get_trade_setup(self, symbol: str) -> Dict:
        """Compact trader-facing trade setup payload from /agent/trade-setup/{symbol}.

        Returns dict with v2 trade_recommendation enums:
            trade_bias, opportunity_score, opportunity_tier, trade_type,
            direction, structures[], entry_trigger, stop_description,
            target_description, risk{...}, caution_flags[], agent_summary

        Returns {} on error.
        """
        if not self.v2_token:
            return {}
        try:
            resp = self._v2_trade_setup(symbol)
            if 'error' in resp:
                return {}
            return resp.get('data', resp) or {}
        except Exception as e:
            print(f"Error fetching trade setup (v2): {e}")
            return {}

    def get_top_setups(self, filters: dict = None) -> Dict:
        """Cross-ticker ranking of opportunities from /top-setups.

        Args:
            filters: optional dict with keys per spec (limit, min_score, regime,
                     trade_bias, trend_state, momentum_state, realized_vol_state,
                     recommended_direction, price_min/max, iv_rank_min/max,
                     ivAtMaxDelta_min/max, ttl).

        Returns dict with v2 envelope: {data: {items[]}, meta: {...}}.
        Returns {} on error.
        """
        if not self.v2_token:
            return {}
        try:
            resp = self._v2_top_setups(filters)
            if 'error' in resp:
                return {}
            return resp
        except Exception as e:
            print(f"Error fetching top setups (v2): {e}")
            return {}

    def get_explain(self, symbol: str, view: str = None) -> Dict:
        """Deterministic plain-English regime explanation from /tickers/{symbol}/explain."""
        if not self.v2_token:
            return {}
        try:
            resp = self._v2_explain(symbol, view=view)
            if 'error' in resp:
                return {}
            return resp.get('data', resp) or {}
        except Exception as e:
            print(f"Error fetching explain (v2): {e}")
            return {}

    def get_current_week_gamma_intelligence(self, symbol: str, current_vix: float = 0) -> Dict:
        """
        Get comprehensive gamma expiration intelligence for CURRENT CALENDAR WEEK ONLY
        Returns 3 views: Daily Impact, Weekly Evolution, Volatility Potential
        Every metric includes actionable money-making strategies with strikes & expirations

        Args:
            symbol: Ticker symbol (e.g., 'SPY')
            current_vix: Current VIX level for context-aware adjustments (optional)

        Returns:
            Dict with 3 views + money-making strategies + tracking data
        """
        from datetime import datetime, timedelta
        import pytz

        # EVIDENCE-BASED THRESHOLDS (from research)
        THRESHOLDS = {
            'daily_impact': {
                'minimal': 5,      # Background noise
                'moderate': 15,    # Validated in production
                'elevated': 30,    # Validated in production
            },
            'volatility_potential': {
                'low': 15,
                'moderate': 40,
                'high': 60,
            },
            'weekly_evolution': {
                'low': 30,
                'moderate': 60,
                'high': 80,
            }
        }

        try:
            # Get current time in CT (Texas Central Time)
            from zoneinfo import ZoneInfo
            current_time = datetime.now(ZoneInfo("America/Chicago"))
            current_weekday = current_time.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
            current_hour = current_time.hour
            current_date_str = current_time.strftime('%Y-%m-%d')

            # Determine calendar week boundaries and edge cases
            is_weekend = current_weekday >= 5
            is_friday_after_close = current_weekday == 4 and current_hour >= 16

            # Calculate Mon-Fri of current calendar week
            if is_weekend:
                # Weekend: Show next week
                days_to_monday = (7 - current_weekday)  # Days until next Monday
                week_start = current_time + timedelta(days=days_to_monday)
                edge_case = 'WEEKEND'
            elif is_friday_after_close:
                # Friday after close: Show current week summary + next week preview
                days_since_monday = current_weekday
                week_start = current_time - timedelta(days=days_since_monday)
                edge_case = 'FRIDAY_AFTER_CLOSE'
            else:
                # Normal trading hours: Show current week (Mon-Fri)
                days_since_monday = current_weekday
                week_start = current_time - timedelta(days=days_since_monday)
                edge_case = None

            # Set week_end to Friday
            week_end = week_start + timedelta(days=4)

            # Build list of trading days for current week
            trading_days = []
            for i in range(5):  # Mon-Fri
                day = week_start + timedelta(days=i)
                # Skip actual weekends (shouldn't happen with our logic, but safety check)
                if day.weekday() < 5:
                    trading_days.append({
                        'date': day.strftime('%Y-%m-%d'),
                        'day_name': day.strftime('%A'),
                        'day_abbr': day.strftime('%a'),
                        'is_today': day.strftime('%Y-%m-%d') == current_date_str,
                        'datetime': day
                    })

            # Fetch gamma data for each trading day
            gamma_by_day = []
            for day_info in trading_days:
                gamma_data = self.get_gamma_by_expiration(symbol, day_info['date'])

                if gamma_data and gamma_data.get('total_gamma', 0) > 0:
                    gamma_by_day.append({
                        **day_info,
                        'total_gamma': gamma_data['total_gamma'],
                        'expiry_date': gamma_data.get('expiry_date'),
                        'has_expiration': True  # Assume if we have gamma data, there's expiration
                    })
                else:
                    # No expiration this day
                    gamma_by_day.append({
                        **day_info,
                        'total_gamma': 0,
                        'expiry_date': None,
                        'has_expiration': False
                    })

            # If no gamma data at all, return empty structure
            if not gamma_by_day or sum(d['total_gamma'] for d in gamma_by_day) == 0:
                return {
                    'error': 'No gamma data available for current week',
                    'symbol': symbol,
                    'week_start': week_start.strftime('%Y-%m-%d'),
                    'week_end': week_end.strftime('%Y-%m-%d')
                }

            # Sort by date
            gamma_by_day = sorted(gamma_by_day, key=lambda x: x['date'])

            # Find today's index
            today_idx = next((i for i, d in enumerate(gamma_by_day) if d['is_today']), 0)

            # =================================================================
            # VIEW 1: DAILY IMPACT (Today → Tomorrow)
            # =================================================================
            today_data = gamma_by_day[today_idx] if today_idx < len(gamma_by_day) else gamma_by_day[0]

            # Calculate today's total available gamma (today + all future days this week)
            today_total_gamma = sum(d['total_gamma'] for d in gamma_by_day[today_idx:])

            # Calculate tomorrow's total available gamma (all future days after today)
            tomorrow_total_gamma = sum(d['total_gamma'] for d in gamma_by_day[today_idx + 1:]) if today_idx + 1 < len(gamma_by_day) else 0

            # Gamma expiring today
            expiring_today = today_data['total_gamma'] if today_data['has_expiration'] else 0

            # Calculate impact percentage
            impact_pct = (expiring_today / today_total_gamma * 100) if today_total_gamma > 0 else 0

            # Context-aware threshold adjustment
            threshold_multiplier = 1.0
            context_notes = []

            # Friday adjustment (lower thresholds)
            if today_data['day_name'] == 'Friday':
                threshold_multiplier = 0.67  # 30% becomes 20%
                context_notes.append("Friday expiration - thresholds lowered")

            # VIX adjustment (if provided)
            if current_vix > 20:
                threshold_multiplier *= 0.75  # Further lower in high-vol environment
                context_notes.append(f"High VIX ({current_vix:.1f}) - thresholds lowered")

            # Determine risk level with context-aware thresholds
            adjusted_thresholds = {k: v * threshold_multiplier for k, v in THRESHOLDS['daily_impact'].items()}

            if impact_pct >= adjusted_thresholds['elevated']:
                risk_level = 'EXTREME'
                risk_color = '#FF4444'
            elif impact_pct >= adjusted_thresholds['moderate']:
                risk_level = 'ELEVATED'
                risk_color = '#FFB800'
            elif impact_pct >= adjusted_thresholds['minimal']:
                risk_level = 'MODERATE'
                risk_color = '#00D4FF'
            else:
                risk_level = 'MINIMAL'
                risk_color = '#00FF88'

            # Generate money-making strategies for View 1
            daily_strategies = []

            if impact_pct >= adjusted_thresholds['elevated']:
                # EXTREME decay - high-conviction plays
                daily_strategies.extend([
                    {
                        'name': 'Fade the Close',
                        'priority': 'HIGH',
                        'description': 'Buy directional options at 3:45pm, sell tomorrow morning',
                        'strike': '0.4 delta (first OTM) in trend direction',
                        'expiration': '0DTE or 1DTE',
                        'entry_time': f'{today_data["day_name"]} 3:45pm',
                        'exit_time': f'Tomorrow morning if gap move occurs',
                        'risk': '30% stop loss',
                        'position_size': '2-3% account risk',
                        'rationale': f'Tomorrow loses {impact_pct:.0f}% gamma support - moves will be sharper without dealer hedging'
                    },
                    {
                        'name': 'ATM Straddle into Expiration',
                        'priority': 'MEDIUM',
                        'description': 'Buy volatility, not direction',
                        'strike': 'ATM (0.5 delta both sides)',
                        'expiration': '1DTE or 2DTE',
                        'entry_time': f'{today_data["day_name"]} 3:30pm',
                        'exit_time': f'Tomorrow morning on gap or quick move',
                        'risk': 'Defined (premium paid)',
                        'position_size': '1-2% account risk',
                        'rationale': f'Gamma expiration creates volatility vacuum - expect {impact_pct:.0f}% regime shift overnight'
                    }
                ])
            elif impact_pct >= adjusted_thresholds['moderate']:
                # MODERATE decay - selective plays
                daily_strategies.append({
                    'name': 'Selective Directional',
                    'priority': 'MEDIUM',
                    'description': 'Only if clear trend + technical setup',
                    'strike': '0.4-0.5 delta in trend direction',
                    'expiration': '1DTE',
                    'entry_time': f'{today_data["day_name"]} afternoon if setup appears',
                    'exit_time': 'Next day on 20-30% profit',
                    'risk': '25% stop loss',
                    'position_size': '1-2% account risk',
                    'rationale': f'{impact_pct:.0f}% decay is meaningful but not extreme - wait for confirmation'
                })
            else:
                # LOW decay - avoid fighting the gamma
                daily_strategies.append({
                    'name': 'Avoid Directional Trades',
                    'priority': 'LOW',
                    'description': 'Gamma still strong - market will mean-revert',
                    'strike': 'N/A',
                    'expiration': 'N/A',
                    'entry_time': 'Do not enter',
                    'exit_time': 'N/A',
                    'risk': 'N/A',
                    'position_size': '0% (no trade)',
                    'rationale': f'Only {impact_pct:.0f}% decay - dealers still actively hedging, range-bound likely'
                })

            daily_impact = {
                'today_total_gamma': today_total_gamma,
                'tomorrow_total_gamma': tomorrow_total_gamma,
                'expiring_today': expiring_today,
                'impact_pct': impact_pct,
                'risk_level': risk_level,
                'risk_color': risk_color,
                'context_notes': context_notes,
                'threshold_multiplier': threshold_multiplier,
                'adjusted_thresholds': adjusted_thresholds,
                'strategies': daily_strategies
            }

            # =================================================================
            # VIEW 2: WEEKLY EVOLUTION (Monday Baseline → Friday End)
            # =================================================================

            monday_baseline = sum(d['total_gamma'] for d in gamma_by_day)
            friday_end = gamma_by_day[-1]['total_gamma'] if gamma_by_day else 0
            total_decay_pct = ((monday_baseline - friday_end) / monday_baseline * 100) if monday_baseline > 0 else 0

            # Build daily breakdown
            daily_breakdown = []
            cumulative_gamma = monday_baseline

            for i, day in enumerate(gamma_by_day):
                pct_of_week = (cumulative_gamma / monday_baseline * 100) if monday_baseline > 0 else 0
                change_from_previous = None

                if i > 0:
                    prev_cumulative = daily_breakdown[i-1]['cumulative_gamma']
                    change_from_previous = ((cumulative_gamma - prev_cumulative) / prev_cumulative * 100) if prev_cumulative > 0 else 0

                daily_breakdown.append({
                    'day': day['day_abbr'],
                    'day_name': day['day_name'],
                    'date': day['date'],
                    'cumulative_gamma': cumulative_gamma,
                    'pct_of_week': pct_of_week,
                    'change_from_previous': change_from_previous,
                    'is_today': day['is_today'],
                    'has_expiration': day['has_expiration']
                })

                # Subtract this day's expiring gamma for next day
                if day['has_expiration']:
                    cumulative_gamma -= day['total_gamma']

            # Determine decay pattern
            first_half_decay = daily_breakdown[2]['pct_of_week'] if len(daily_breakdown) > 2 else 100  # Wed %
            if first_half_decay < 60:  # Lost >40% by Wednesday
                decay_pattern = 'FRONT_LOADED'
            elif first_half_decay > 80:  # Lost <20% by Wednesday
                decay_pattern = 'BACK_LOADED'
            else:
                decay_pattern = 'BALANCED'

            # Generate weekly strategies
            weekly_strategies = {}

            if total_decay_pct >= THRESHOLDS['weekly_evolution']['high']:
                # HIGH decay week (>80%) - Major OPEX week
                weekly_strategies = {
                    'early_week': {
                        'name': 'Aggressive Theta Farming (Mon-Wed)',
                        'description': 'Sell premium while gamma is strong',
                        'strategy_type': 'Iron Condor or Credit Spreads',
                        'strikes': '0.15-0.20 delta wings (far OTM) - use GEX levels for short strikes',
                        'expiration': 'Friday (this week)',
                        'entry_time': 'Monday morning or Tuesday morning',
                        'exit_time': 'Wednesday close (take 50-60% profit)',
                        'position_size': '3-5% account risk per spread',
                        'rationale': f'Week starts with {daily_breakdown[0]["pct_of_week"]:.0f}% of gamma - high mean-reversion, options will decay fast'
                    },
                    'late_week': {
                        'name': 'Delta Buying (Thu-Fri)',
                        'description': 'Switch to directional momentum plays',
                        'strategy_type': 'Long Calls or Puts',
                        'strikes': 'ATM or first OTM (0.5-0.6 delta) based on Wednesday close direction',
                        'expiration': 'Next week (1 week DTE)',
                        'entry_time': 'Thursday morning',
                        'exit_time': 'Friday close or hold through weekend if strong trend',
                        'position_size': '2-3% account risk',
                        'rationale': f'By Thursday, only {daily_breakdown[3]["pct_of_week"]:.0f}% gamma remains - low hedging = directional moves'
                    },
                    'size_management': {
                        'name': 'Dynamic Position Sizing',
                        'description': 'Adjust size based on gamma regime through week',
                        'monday_tuesday': '100% normal size (gamma protects you)',
                        'wednesday': '75% size (transition)',
                        'thursday_friday': '50% size (gamma gone, vol spikes)',
                        'rationale': f'Risk management: {total_decay_pct:.0f}% weekly decay means vol will increase significantly late week'
                    }
                }
            elif total_decay_pct >= THRESHOLDS['weekly_evolution']['moderate']:
                # MODERATE decay week (60-80%)
                weekly_strategies = {
                    'early_week': {
                        'name': 'Moderate Premium Selling (Mon-Tue)',
                        'description': 'Smaller position sizes, tighter strikes',
                        'strategy_type': 'Credit Spreads',
                        'strikes': '0.20-0.25 delta wings (closer to money)',
                        'expiration': 'Friday',
                        'entry_time': 'Monday morning',
                        'exit_time': 'Wednesday close',
                        'position_size': '2-3% account risk',
                        'rationale': f'{total_decay_pct:.0f}% weekly decay is moderate - some gamma support but not extreme'
                    },
                    'late_week': {
                        'name': 'Cautious Approach (Thu-Fri)',
                        'description': 'Reduce exposure or sit out',
                        'strategy_type': 'Close existing, minimal new trades',
                        'strikes': 'If trading: 0.5 delta only',
                        'expiration': 'Next week',
                        'entry_time': 'Only on A+ setups',
                        'exit_time': 'Quick scalps only',
                        'position_size': '1% account risk max',
                        'rationale': f'Moderate decay means some vol increase expected - be selective late week'
                    }
                }
            else:
                # LOW decay week (<60%)
                weekly_strategies = {
                    'all_week': {
                        'name': 'Standard Trading (All Week)',
                        'description': 'Normal gamma structure, trade as usual',
                        'strategy_type': 'Any strategy',
                        'strikes': 'Based on normal technical analysis',
                        'expiration': 'Any',
                        'entry_time': 'Based on setups',
                        'exit_time': 'Based on targets',
                        'position_size': 'Normal sizing',
                        'rationale': f'Only {total_decay_pct:.0f}% weekly decay - gamma structure stays relatively stable all week'
                    }
                }

            weekly_evolution = {
                'monday_baseline': monday_baseline,
                'friday_end': friday_end,
                'total_decay_pct': total_decay_pct,
                'decay_pattern': decay_pattern,
                'daily_breakdown': daily_breakdown,
                'strategies': weekly_strategies
            }

            # =================================================================
            # VIEW 3: VOLATILITY POTENTIAL (Relative Risk by Day)
            # =================================================================

            volatility_by_day = []
            max_vol_pct = 0
            highest_risk_day = None

            for i, day in enumerate(gamma_by_day):
                # Daily total available = this day + all future days
                daily_total_available = sum(d['total_gamma'] for d in gamma_by_day[i:])
                daily_expiring = day['total_gamma'] if day['has_expiration'] else 0

                vol_pct = (daily_expiring / daily_total_available * 100) if daily_total_available > 0 else 0

                # Determine risk level
                if vol_pct >= THRESHOLDS['volatility_potential']['high']:
                    day_risk_level = 'EXTREME'
                    day_risk_color = '#FF4444'
                elif vol_pct >= THRESHOLDS['volatility_potential']['moderate']:
                    day_risk_level = 'HIGH'
                    day_risk_color = '#FFB800'
                elif vol_pct >= THRESHOLDS['volatility_potential']['low']:
                    day_risk_level = 'MODERATE'
                    day_risk_color = '#00D4FF'
                else:
                    day_risk_level = 'LOW'
                    day_risk_color = '#00FF88'

                volatility_by_day.append({
                    'day': day['day_abbr'],
                    'day_name': day['day_name'],
                    'date': day['date'],
                    'expiring_gamma': daily_expiring,
                    'total_available': daily_total_available,
                    'vol_pct': vol_pct,
                    'risk_level': day_risk_level,
                    'risk_color': day_risk_color,
                    'is_today': day['is_today'],
                    'has_expiration': day['has_expiration']
                })

                if vol_pct > max_vol_pct:
                    max_vol_pct = vol_pct
                    highest_risk_day = volatility_by_day[-1]

            # Generate strategies for highest risk day
            highest_risk_day_strategies = []

            if highest_risk_day and highest_risk_day['vol_pct'] >= THRESHOLDS['volatility_potential']['high']:
                # EXTREME volatility day
                highest_risk_day_strategies = [
                    {
                        'name': 'Pre-Expiration Volatility Scalp',
                        'priority': 'HIGH',
                        'description': 'Capture chaos of gamma expiration, not direction',
                        'strategy_type': 'ATM Straddle',
                        'strike': 'ATM straddle (0.5 delta both sides)',
                        'expiration': f'0DTE (expiring {highest_risk_day["day_name"]})',
                        'entry_time': f'{highest_risk_day["day_name"]} 10:00-11:00am',
                        'exit_time': f'{highest_risk_day["day_name"]} 2:00-3:00pm (BEFORE 4pm expiration)',
                        'risk': 'Defined (premium paid)',
                        'position_size': '2-3% account risk',
                        'rationale': f'{highest_risk_day["day_name"]} has {highest_risk_day["vol_pct"]:.0f}% gamma decay - massive expiration creates intraday volatility spike. Exit before pin risk at 4pm.'
                    },
                    {
                        'name': 'Post-Expiration Directional Positioning',
                        'priority': 'MEDIUM',
                        'description': 'Position day-before for explosive move day-after',
                        'strategy_type': 'Long Calls or Puts',
                        'strike': '0.4-0.5 delta in expected direction (use technical analysis)',
                        'expiration': '1DTE or 2DTE',
                        'entry_time': f'Day before ({highest_risk_day["day_name"]}) at 3:45pm',
                        'exit_time': f'Next day morning if profit target hit',
                        'risk': '30% stop loss',
                        'position_size': '2% account risk',
                        'rationale': f'After {highest_risk_day["day_name"]} gamma expires, next day will have explosive moves in prevailing trend direction'
                    },
                    {
                        'name': 'The Avoidance Strategy',
                        'priority': 'LOW',
                        'description': 'Sometimes the best trade is no trade',
                        'strategy_type': 'Cash / Sidelines',
                        'strike': 'N/A',
                        'expiration': 'N/A',
                        'entry_time': 'Close all positions day before',
                        'exit_time': 'Re-enter next Monday',
                        'risk': '0% (no positions)',
                        'position_size': '0% (cash)',
                        'rationale': f'{highest_risk_day["day_name"]} shows {highest_risk_day["vol_pct"]:.0f}% decay - if you\'re uncomfortable with chaos, sit out and preserve capital'
                    }
                ]

            volatility_potential = {
                'by_day': volatility_by_day,
                'highest_risk_day': highest_risk_day,
                'strategies': highest_risk_day_strategies
            }

            # =================================================================
            # TRACKING & LOGGING (for future correlation analysis)
            # =================================================================

            tracking_data = {
                'timestamp': current_time.isoformat(),
                'symbol': symbol,
                'vix': current_vix,
                'gamma_decay_pct': impact_pct,
                'weekly_decay_pct': total_decay_pct,
                'risk_level': risk_level,
                'highest_risk_day_name': highest_risk_day['day_name'] if highest_risk_day else None,
                'highest_risk_day_pct': highest_risk_day['vol_pct'] if highest_risk_day else 0,
                # Will be filled in by tracking system:
                'actual_price_move_pct': None,  # To be filled next day
                'actual_intraday_range_pct': None  # To be filled EOD
            }

            # =================================================================
            # RETURN COMPLETE STRUCTURE
            # =================================================================

            return {
                'success': True,
                'symbol': symbol,
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': week_end.strftime('%Y-%m-%d'),
                'current_day': today_data['day_name'],
                'current_date': current_date_str,
                'is_weekend': is_weekend,
                'is_friday_after_close': is_friday_after_close,
                'edge_case': edge_case,

                # Three views
                'daily_impact': daily_impact,
                'weekly_evolution': weekly_evolution,
                'volatility_potential': volatility_potential,

                # Tracking for correlation analysis
                'tracking': tracking_data,

                # Metadata
                'thresholds_used': THRESHOLDS,
                'context_aware': True,
                'generated_at': current_time.isoformat()
            }

        except Exception as e:
            import traceback
            print(f"Error in get_current_week_gamma_intelligence: {e}")
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'symbol': symbol
            }

    def get_option_data(self, symbol: str) -> Dict:
        """
        Alias for get_net_gamma - provides option/gamma data for a symbol.

        This method exists for backward compatibility with code that may
        reference get_option_data instead of get_net_gamma.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')

        Returns:
            Dict with net gamma exposure data including spot_price, net_gex,
            flip_point, call_wall, put_wall, etc.
        """
        return self.get_net_gamma(symbol)


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

    def simulate_iron_condor(self,
                            spot_price: float,
                            call_short: float,
                            call_long: float,
                            put_short: float,
                            put_long: float,
                            days: int = 30,
                            volatility: float = 0.15) -> Dict:
        """
        Run Monte Carlo simulation for an iron condor strategy
        Iron condor wins when final price stays between short strikes
        """
        try:
            # Generate random price paths
            np.random.seed(42)  # For reproducibility

            # GBM parameters for neutral market assumption
            drift = 0  # Assume no drift for iron condor
            vol = volatility

            # Simulate final prices
            final_prices = []
            win_count = 0

            for _ in range(self.num_simulations):
                # Generate daily returns
                daily_returns = np.random.normal(
                    drift / 252,
                    vol / np.sqrt(252),
                    days
                )

                # Calculate final price
                final_price = spot_price * np.exp(np.sum(daily_returns))
                final_prices.append(final_price)

                # Iron condor wins if price stays between short strikes
                if put_short <= final_price <= call_short:
                    win_count += 1

            # Calculate statistics
            final_prices = np.array(final_prices)
            win_probability = (win_count / self.num_simulations) * 100

            result = {
                'win_probability': win_probability,
                'expected_final_price': np.mean(final_prices),
                'median_final_price': np.median(final_prices),
                'std_final_price': np.std(final_prices),
                'prob_above_call': np.sum(final_prices > call_short) / self.num_simulations * 100,
                'prob_below_put': np.sum(final_prices < put_short) / self.num_simulations * 100,
            }

            return result

        except Exception as e:
            print(f"Iron condor simulation error: {e}")
            # Return default values to avoid crashes
            return {
                'win_probability': 70.0,  # Default reasonable win rate
                'expected_final_price': spot_price,
                'median_final_price': spot_price,
                'std_final_price': spot_price * 0.05,
                'prob_above_call': 15.0,
                'prob_below_put': 15.0,
            }


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
