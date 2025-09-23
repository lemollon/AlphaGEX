"""
GammaHunter Behavioral Engine
============================

Market maker behavioral analysis and signal generation.
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, time
from enum import Enum

from config import (
    MarketMakerState, SignalType, 
    GEX_THRESHOLD_LARGE_NEGATIVE, GEX_THRESHOLD_LARGE_POSITIVE,
    WALL_MIN_THRESHOLD, EXPECTED_WIN_RATES, MARKET_WISDOM
)
from core.logger import log_error, log_decision

@dataclass
class GammaLevel:
    strike: float
    gamma_exposure: float
    open_interest: int
    volume: int
    is_wall: bool = False
    wall_strength: float = 0.0

@dataclass
class GEXProfile:
    symbol: str
    spot_price: float
    net_gex: float
    gamma_flip_point: float
    call_walls: List[GammaLevel]
    put_walls: List[GammaLevel]
    timestamp: datetime

@dataclass
class TradingSignal:
    signal_type: SignalType
    symbol: str
    confidence_score: float
    entry_strikes: List[float]
    target_dte: int
    reasoning_steps: List[str]
    supporting_evidence: List[str]
    contrary_evidence: List[str]
    risk_factors: List[str]
    expected_win_rate: float
    max_loss_percent: float
    target_profit_percent: float
    market_maker_state: MarketMakerState
    time_sensitivity: str

class GammaCalculator:
    """Gamma exposure calculations"""
    
    def calculate_gex_for_strike(self, spot_price: float, gamma: float, 
                                open_interest: int, is_call: bool) -> float:
        """Calculate gamma exposure for single strike"""
        base_gex = spot_price * gamma * open_interest * 100
        return base_gex if is_call else -base_gex
    
    def find_gamma_flip_point(self, strikes_and_gex: List[Tuple[float, float]]) -> float:
        """Find gamma flip point where cumulative GEX crosses zero"""
        sorted_strikes = sorted(strikes_and_gex, key=lambda x: x[0])
        
        cumulative_gex = 0
        for strike, gex in sorted_strikes:
            cumulative_gex += gex
            if cumulative_gex >= 0:
                return strike
        
        return sorted_strikes[-1][0] if sorted_strikes else 0.0
    
    def identify_gamma_walls(self, gamma_levels: List[GammaLevel]) -> Tuple[List[GammaLevel], List[GammaLevel]]:
        """Identify significant call and put walls"""
        
        call_walls = []
        put_walls = []
        
        for level in gamma_levels:
            abs_gex = abs(level.gamma_exposure)
            
            if abs_gex >= WALL_MIN_THRESHOLD:
                wall_strength = min(100, (abs_gex / WALL_MIN_THRESHOLD) * 20)
                level.is_wall = True
                level.wall_strength = wall_strength
                
                if level.gamma_exposure > 0:
                    call_walls.append(level)
                else:
                    put_walls.append(level)
        
        call_walls.sort(key=lambda x: x.gamma_exposure, reverse=True)
        put_walls.sort(key=lambda x: abs(x.gamma_exposure), reverse=True)
        
        return call_walls[:5], put_walls[:5]

class MarketMakerAnalyzer:
    """Market maker behavior analysis"""
    
    def __init__(self):
        self.market_wisdom = MARKET_WISDOM
    
    def analyze_mm_psychology(self, profile: GEXProfile) -> MarketMakerState:
        """Determine market maker psychological state"""
        
        net_gex = profile.net_gex
        spot = profile.spot_price
        flip_point = profile.gamma_flip_point
        
        # TRAPPED: Dealers short gamma and vulnerable
        if net_gex < GEX_THRESHOLD_LARGE_NEGATIVE and spot < flip_point:
            return MarketMakerState.TRAPPED
        
        # DEFENDING: Large positive GEX, managing ranges
        if net_gex > GEX_THRESHOLD_LARGE_POSITIVE:
            return MarketMakerState.DEFENDING
        
        # PANICKING: Extreme negative with volatility
        if net_gex < GEX_THRESHOLD_LARGE_NEGATIVE * 1.5:
            return MarketMakerState.PANICKING
        
        # HUNTING: Moderate GEX
        if -500_000_000 < net_gex < 1_000_000_000:
            return MarketMakerState.HUNTING
        
        return MarketMakerState.NEUTRAL
    
    def assess_vulnerability_score(self, profile: GEXProfile, mm_state: MarketMakerState) -> float:
        """Score MM vulnerability (0-100)"""
        
        base_score = 0
        
        # GEX magnitude
        if abs(profile.net_gex) > 2_000_000_000:
            base_score += 30
        elif abs(profile.net_gex) > 1_000_000_000:
            base_score += 20
        
        # Distance from flip
        distance = abs(profile.spot_price - profile.gamma_flip_point) / profile.spot_price
        if distance < 0.005:
            base_score += 25
        elif distance < 0.01:
            base_score += 15
        
        # Wall proximity
        if profile.call_walls or profile.put_walls:
            nearest_wall_distance = float('inf')
            for wall in profile.call_walls + profile.put_walls:
                dist = abs(profile.spot_price - wall.strike) / profile.spot_price
                nearest_wall_distance = min(nearest_wall_distance, dist)
            
            if nearest_wall_distance < 0.01:
                base_score += 20
        
        # State multipliers
        multipliers = {
            MarketMakerState.TRAPPED: 1.3,
            MarketMakerState.PANICKING: 1.5,
            MarketMakerState.DEFENDING: 0.8,
            MarketMakerState.HUNTING: 1.0,
            MarketMakerState.NEUTRAL: 0.7
        }
        
        return min(100, base_score * multipliers[mm_state])

class SignalGenerator:
    """Trading signal generation"""
    
    def __init__(self, analyzer: MarketMakerAnalyzer, calculator: GammaCalculator):
        self.analyzer = analyzer
        self.calculator = calculator
    
    def generate_signal(self, profile: GEXProfile) -> TradingSignal:
        """Generate comprehensive trading signal"""
        
        mm_state = self.analyzer.analyze_mm_psychology(profile)
        vulnerability = self.analyzer.assess_vulnerability_score(profile, mm_state)
        
        signal_type, confidence, reasoning, supporting, contrary = \
            self._analyze_setup_patterns(profile, mm_state, vulnerability)
        
        entry_strikes, target_dte = self._calculate_entries(profile, signal_type)
        risk_factors = self._assess_risks(profile, signal_type)
        win_rate = self._estimate_win_rate(signal_type, mm_state, vulnerability)
        max_loss, target_profit = self._calculate_risk_reward(signal_type, vulnerability)
        time_sensitivity = self._assess_timing()
        
        signal = TradingSignal(
            signal_type=signal_type,
            symbol=profile.symbol,
            confidence_score=confidence,
            entry_strikes=entry_strikes,
            target_dte=target_dte,
            reasoning_steps=reasoning,
            supporting_evidence=supporting,
            contrary_evidence=contrary,
            risk_factors=risk_factors,
            expected_win_rate=win_rate,
            max_loss_percent=max_loss,
            target_profit_percent=target_profit,
            market_maker_state=mm_state,
            time_sensitivity=time_sensitivity
        )
        
        # Log the decision
        log_decision(
            decision_type="signal_generation",
            confidence_score=confidence,
            reasoning_steps=reasoning,
            supporting_evidence=supporting,
            contrary_evidence=contrary,
            final_recommendation=f"{signal_type.value} - {confidence:.0f}% confidence"
        )
        
        return signal
    
    def _analyze_setup_patterns(self, profile: GEXProfile, mm_state: MarketMakerState,
                               vulnerability: float) -> Tuple[SignalType, float, List[str], List[str], List[str]]:
        """Analyze specific gamma setup patterns"""
        
        reasoning = []
        supporting = []
        contrary = []
        
        net_gex = profile.net_gex
        spot = profile.spot_price
        flip = profile.gamma_flip_point
        
        # Negative GEX Squeeze (Long Calls)
        if (net_gex < GEX_THRESHOLD_LARGE_NEGATIVE and 
            spot < flip and 
            mm_state == MarketMakerState.TRAPPED):
            
            reasoning.extend([
                f"Net GEX at {net_gex/1e9:.1f}B indicates dealers short gamma",
                f"Price {spot:.2f} below flip point {flip:.2f}",
                "Market makers trapped and must buy rallies",
                "Classic negative gamma squeeze setup"
            ])
            
            supporting.extend([
                f"Historical win rate: {EXPECTED_WIN_RATES['long_calls']:.0%}",
                f"MM vulnerability: {vulnerability:.0f}/100",
                "Negative gamma amplifies upward moves"
            ])
            
            confidence = 75 + min(20, vulnerability * 0.2)
            return SignalType.LONG_CALLS, confidence, reasoning, supporting, contrary
        
        # Positive GEX Breakdown (Long Puts)
        elif (net_gex > GEX_THRESHOLD_LARGE_POSITIVE and 
              abs(spot - flip) / spot < 0.005):
            
            reasoning.extend([
                f"Large positive GEX {net_gex/1e9:.1f}B creating resistance",
                f"Price hovering near flip point {flip:.2f}",
                "Breakdown below flip triggers dealer selling"
            ])
            
            supporting.extend([
                f"Vulnerability: {vulnerability:.0f}/100",
                "Positive GEX provides support until broken"
            ])
            
            confidence = 65 + (vulnerability * 0.15)
            return SignalType.LONG_PUTS, confidence, reasoning, supporting, contrary
        
        # Iron Condor Setup
        elif (1_000_000_000 < net_gex < 3_000_000_000 and 
              profile.call_walls and profile.put_walls):
            
            call_wall = profile.call_walls[0]
            put_wall = profile.put_walls[0]
            wall_distance = (call_wall.strike - put_wall.strike) / spot
            
            if 0.03 < wall_distance < 0.08:
                reasoning.extend([
                    f"Positive GEX {net_gex/1e9:.1f}B supports range trading",
                    f"Strong walls at {call_wall.strike:.2f} and {put_wall.strike:.2f}",
                    f"Range width {wall_distance*100:.1f}% ideal for Iron Condor"
                ])
                
                supporting.extend([
                    f"Wall strengths: {call_wall.wall_strength:.0f} / {put_wall.wall_strength:.0f}",
                    f"Historical IC win rate: {EXPECTED_WIN_RATES['iron_condor']:.0%}"
                ])
                
                confidence = 70 + min(call_wall.wall_strength, put_wall.wall_strength) * 0.15
                return SignalType.IRON_CONDOR, confidence, reasoning, supporting, contrary
        
        # No clear setup
        reasoning.append("No high-confidence GEX setup identified")
        contrary.append("Market conditions don't meet criteria for core strategies")
        
        return SignalType.NO_SIGNAL, 30, reasoning, supporting, contrary
    
    def _calculate_entries(self, profile: GEXProfile, signal_type: SignalType) -> Tuple[List[float], int]:
        """Calculate optimal entry strikes and DTE"""
        
        spot = profile.spot_price
        entry_strikes = []
        target_dte = 7
        
        if signal_type == SignalType.LONG_CALLS:
            flip_point = profile.gamma_flip_point
            if spot < flip_point:
                entry_strikes = [flip_point, flip_point * 1.01]
            else:
                entry_strikes = [spot, spot * 1.02]
            target_dte = 3
        
        elif signal_type == SignalType.LONG_PUTS:
            flip_point = profile.gamma_flip_point
            entry_strikes = [spot, flip_point * 0.99]
            target_dte = 5
        
        elif signal_type == SignalType.IRON_CONDOR:
            if profile.call_walls and profile.put_walls:
                call_wall = profile.call_walls[0].strike
                put_wall = profile.put_walls[0].strike
                entry_strikes = [put_wall * 0.98, put_wall, call_wall, call_wall * 1.02]
                target_dte = 14
        
        return entry_strikes, target_dte
    
    def _assess_risks(self, profile: GEXProfile, signal_type: SignalType) -> List[str]:
        """Identify risk factors"""
        
        risks = []
        
        if abs(profile.net_gex) < 500_000_000:
            risks.append("Low GEX magnitude - signals less reliable")
        
        if signal_type == SignalType.IRON_CONDOR:
            if not profile.call_walls or not profile.put_walls:
                risks.append("Weak gamma walls - range may not hold")
        
        current_time = datetime.now()
        if current_time.weekday() == 4:  # Friday
            risks.append("Friday afternoon - limited development time")
        
        return risks
    
    def _estimate_win_rate(self, signal_type: SignalType, mm_state: MarketMakerState, 
                         vulnerability: float) -> float:
        """Estimate win rate based on historical patterns"""
        
        base_rate = EXPECTED_WIN_RATES.get(signal_type.value, 0.50)
        
        # Adjust for MM state
        adjustments = {
            MarketMakerState.TRAPPED: 0.10,
            MarketMakerState.PANICKING: 0.08,
            MarketMakerState.DEFENDING: -0.05,
            MarketMakerState.HUNTING: 0.02,
            MarketMakerState.NEUTRAL: 0.00
        }
        
        # Vulnerability adjustment
        vulnerability_adj = (vulnerability - 50) * 0.002
        
        final_rate = base_rate + adjustments[mm_state] + vulnerability_adj
        return max(0.40, min(0.85, final_rate))
    
    def _calculate_risk_reward(self, signal_type: SignalType, vulnerability: float) -> Tuple[float, float]:
        """Calculate risk/reward parameters"""
        
        if signal_type in [SignalType.LONG_CALLS, SignalType.LONG_PUTS]:
            max_loss = 2.0 + (vulnerability * 0.02)
            target_profit = max_loss * 2.5
        elif signal_type == SignalType.IRON_CONDOR:
            max_loss = 1.5
            target_profit = max_loss * 0.75
        else:
            max_loss = 0.0
            target_profit = 0.0
        
        return max_loss, target_profit
    
    def _assess_timing(self) -> str:
        """Assess timing sensitivity"""
        current_time = datetime.now()
        
        if current_time.weekday() == 4:  # Friday
            return "immediate"
        else:
            return "within_hour"

class BehavioralEngine:
    """Main behavioral analysis engine"""
    
    def __init__(self):
        self.calculator = GammaCalculator()
        self.analyzer = MarketMakerAnalyzer()
        self.signal_generator = SignalGenerator(self.analyzer, self.calculator)
    
    def analyze_symbol(self, symbol: str, api_data: Dict[str, Any]) -> Tuple[GEXProfile, TradingSignal]:
        """Complete analysis pipeline for a symbol"""
        
        try:
            spot_price = api_data.get("spot_price", 0)
            net_gex = api_data.get("net_gex", 0)
            gamma_flip = api_data.get("gamma_flip_price", spot_price)
            
            # Build gamma levels
            gamma_levels = []
            strikes_data = api_data.get("strikes", [])
            
            for strike_info in strikes_data:
                level = GammaLevel(
                    strike=strike_info.get("strike", 0),
                    gamma_exposure=strike_info.get("gex", 0),
                    open_interest=strike_info.get("open_interest", 0),
                    volume=strike_info.get("volume", 0)
                )
                gamma_levels.append(level)
            
            call_walls, put_walls = self.calculator.identify_gamma_walls(gamma_levels)
            
            profile = GEXProfile(
                symbol=symbol,
                spot_price=spot_price,
                net_gex=net_gex,
                gamma_flip_point=gamma_flip,
                call_walls=call_walls,
                put_walls=put_walls,
                timestamp=datetime.now(timezone.utc)
            )
            
            signal = self.signal_generator.generate_signal(profile)
            return profile, signal
            
        except Exception as e:
            error_id = log_error("behavioral_analysis", e, {"symbol": symbol})
            
            # Return neutral results on error
            neutral_profile = GEXProfile(
                symbol=symbol,
                spot_price=0,
                net_gex=0,
                gamma_flip_point=0,
                call_walls=[],
                put_walls=[],
                timestamp=datetime.now(timezone.utc)
            )
            
            no_signal = TradingSignal(
                signal_type=SignalType.NO_SIGNAL,
                symbol=symbol,
                confidence_score=0,
                entry_strikes=[],
                target_dte=0,
                reasoning_steps=[f"Analysis failed: {error_id}"],
                supporting_evidence=[],
                contrary_evidence=[],
                risk_factors=["Analysis error"],
                expected_win_rate=0.5,
                max_loss_percent=0,
                target_profit_percent=0,
                market_maker_state=MarketMakerState.NEUTRAL,
                time_sensitivity="end_of_day"
            )
            
            return neutral_profile, no_signal
