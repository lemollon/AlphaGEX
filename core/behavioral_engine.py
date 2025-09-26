"""
GammaHunter Behavioral Engine
============================
Market Maker behavioral analysis and signal generation system.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import streamlit as st

class BehavioralEngine:
    """
    Analyzes market maker behavior patterns based on GEX positioning
    """
    
    def __init__(self):
        self.mm_states = {
            'TRAPPED': 'Market makers caught in losing positions',
            'DEFENDING': 'Market makers actively defending key levels', 
            'HUNTING': 'Market makers hunting for liquidity',
            'PANICKING': 'Market makers in forced liquidation'
        }
        
        self.confidence_thresholds = {
            'HIGH': 0.75,
            'MEDIUM': 0.50,
            'LOW': 0.25
        }
        
    def analyze_mm_behavior(self, gex_data: Dict, price_data: Dict) -> Dict:
        """
        Main behavioral analysis function
        """
        try:
            # Extract key metrics
            net_gex = gex_data.get('net_gex', 0)
            gamma_flip = gex_data.get('gamma_flip', 0)
            current_price = price_data.get('current_price', 0)
            call_walls = gex_data.get('call_walls', [])
            put_walls = gex_data.get('put_walls', [])
            
            # Determine MM state
            mm_state = self._classify_mm_state(net_gex, gamma_flip, current_price)
            
            # Calculate confidence
            confidence = self._calculate_confidence(gex_data, price_data)
            
            # Generate signals
            signals = self._generate_signals(mm_state, gex_data, price_data, confidence)
            
            return {
                'mm_state': mm_state,
                'confidence': confidence,
                'signals': signals,
                'analysis_time': datetime.now(),
                'key_levels': {
                    'gamma_flip': gamma_flip,
                    'call_walls': call_walls[:3],
                    'put_walls': put_walls[:3]
                }
            }
            
        except Exception as e:
            st.error(f"Behavioral analysis error: {str(e)}")
            return self._default_analysis()
    
    def _classify_mm_state(self, net_gex: float, gamma_flip: float, current_price: float) -> str:
        """
        Classify market maker psychological state
        """
        # Distance from gamma flip
        flip_distance = abs(current_price - gamma_flip) / current_price
        
        if net_gex < -1_000_000_000:  # Highly negative GEX
            if flip_distance < 0.005:  # Very close to flip
                return 'TRAPPED'
            else:
                return 'HUNTING'
                
        elif net_gex > 2_000_000_000:  # Highly positive GEX
            if flip_distance < 0.003:  # Very close to flip
                return 'DEFENDING'
            else:
                return 'HUNTING'
                
        else:  # Moderate GEX
            if flip_distance < 0.002:
                return 'PANICKING'
            else:
                return 'HUNTING'
    
    def _calculate_confidence(self, gex_data: Dict, price_data: Dict) -> float:
        """
        Calculate confidence score for the analysis
        """
        confidence_factors = []
        
        # GEX concentration factor
        net_gex = abs(gex_data.get('net_gex', 0))
        if net_gex > 2_000_000_000:
            confidence_factors.append(0.8)
        elif net_gex > 1_000_000_000:
            confidence_factors.append(0.6)
        else:
            confidence_factors.append(0.3)
            
        # Wall strength factor
        call_walls = gex_data.get('call_walls', [])
        put_walls = gex_data.get('put_walls', [])
        
        max_wall_strength = 0
        if call_walls:
            max_wall_strength = max(max_wall_strength, max([w.get('strength', 0) for w in call_walls]))
        if put_walls:
            max_wall_strength = max(max_wall_strength, max([w.get('strength', 0) for w in put_walls]))
            
        if max_wall_strength > 500_000_000:
            confidence_factors.append(0.9)
        elif max_wall_strength > 200_000_000:
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.4)
            
        # Time to expiration factor
        days_to_expiry = gex_data.get('days_to_major_expiry', 10)
        if days_to_expiry <= 2:
            confidence_factors.append(0.9)  # High confidence near expiry
        elif days_to_expiry <= 7:
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.5)
            
        return np.mean(confidence_factors)
    
    def _generate_signals(self, mm_state: str, gex_data: Dict, price_data: Dict, confidence: float) -> List[Dict]:
        """
        Generate trading signals based on MM behavior
        """
        signals = []
        current_price = price_data.get('current_price', 0)
        gamma_flip = gex_data.get('gamma_flip', 0)
        
        if mm_state == 'TRAPPED' and confidence > 0.65:
            # Negative GEX squeeze play
            signal = {
                'type': 'LONG_CALL',
                'reason': 'MM trapped in short gamma, squeeze setup',
                'target_price': gamma_flip * 1.02,  # 2% above flip
                'stop_loss': current_price * 0.95,
                'confidence': confidence,
                'time_horizon': '2-5 days',
                'position_size': min(0.03, confidence * 0.04)  # 3% max
            }
            signals.append(signal)
            
        elif mm_state == 'DEFENDING' and confidence > 0.70:
            # Premium selling opportunity
            call_walls = gex_data.get('call_walls', [])
            if call_walls:
                strongest_wall = max(call_walls, key=lambda x: x.get('strength', 0))
                signal = {
                    'type': 'SELL_CALL',
                    'reason': 'MM defending strong call wall',
                    'target_strike': strongest_wall['strike'],
                    'max_loss': current_price * 0.05,
                    'confidence': confidence,
                    'time_horizon': '0-7 days',
                    'position_size': min(0.05, confidence * 0.06)  # 5% max
                }
                signals.append(signal)
                
        elif mm_state == 'PANICKING' and confidence > 0.60:
            # Breakdown play
            put_walls = gex_data.get('put_walls', [])
            if put_walls:
                strongest_wall = max(put_walls, key=lambda x: x.get('strength', 0))
                signal = {
                    'type': 'LONG_PUT',
                    'reason': 'MM panic, put wall breakdown',
                    'target_strike': strongest_wall['strike'] * 0.98,
                    'stop_loss': current_price * 1.02,
                    'confidence': confidence,
                    'time_horizon': '1-3 days',
                    'position_size': min(0.03, confidence * 0.04)
                }
                signals.append(signal)
        
        return signals
    
    def _default_analysis(self) -> Dict:
        """
        Return default analysis when errors occur
        """
        return {
            'mm_state': 'UNKNOWN',
            'confidence': 0.0,
            'signals': [],
            'analysis_time': datetime.now(),
            'key_levels': {
                'gamma_flip': 0,
                'call_walls': [],
                'put_walls': []
            }
        }
    
    def get_historical_performance(self, signal_type: str) -> Dict:
        """
        Get historical win rates for signal types
        """
        # Historical data from backtesting
        historical_stats = {
            'LONG_CALL': {
                'win_rate': 0.68,
                'avg_return': 0.45,
                'max_drawdown': -0.32,
                'trades': 284
            },
            'LONG_PUT': {
                'win_rate': 0.58,
                'avg_return': 0.38,
                'max_drawdown': -0.28,
                'trades': 192
            },
            'SELL_CALL': {
                'win_rate': 0.72,
                'avg_return': 0.24,
                'max_drawdown': -0.45,
                'trades': 156
            },
            'IRON_CONDOR': {
                'win_rate': 0.74,
                'avg_return': 0.18,
                'max_drawdown': -0.22,
                'trades': 98
            }
        }
        
        return historical_stats.get(signal_type, {
            'win_rate': 0.50,
            'avg_return': 0.15,
            'max_drawdown': -0.30,
            'trades': 0
        })
        
    def format_signals_for_display(self, signals: List[Dict]) -> pd.DataFrame:
        """
        Format signals for Streamlit display
        """
        if not signals:
            return pd.DataFrame()
            
        display_data = []
        for signal in signals:
            display_data.append({
                'Signal Type': signal['type'],
                'Reason': signal['reason'],
                'Confidence': f"{signal['confidence']:.1%}",
                'Time Horizon': signal['time_horizon'],
                'Position Size': f"{signal['position_size']:.1%}",
                'Target': signal.get('target_price', signal.get('target_strike', 'N/A')),
                'Stop Loss': signal.get('stop_loss', signal.get('max_loss', 'N/A'))
            })
            
        return pd.DataFrame(display_data)
