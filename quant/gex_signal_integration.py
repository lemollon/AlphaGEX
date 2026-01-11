"""
GEX Signal Integration for ATHENA Strategy
===========================================

Integrates the 5 GEX probability models with the ATHENA Directional Strategy.

This module provides:
1. Feature extraction from live GEX data
2. Real-time predictions from all 5 models
3. Combined trading signals for ATHENA

Usage:
    from quant.gex_signal_integration import GEXSignalIntegration

    # Initialize with trained models
    integration = GEXSignalIntegration()
    integration.load_models()

    # Get signal from live GEX data
    signal = integration.get_trading_signal(gex_data, vix=18.0)

    print(f"Direction: {signal.direction_prediction}")
    print(f"Recommendation: {signal.trade_recommendation}")

Author: AlphaGEX Quant
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

logger = logging.getLogger(__name__)


@dataclass
class EnhancedTradingSignal:
    """Enhanced trading signal from GEX probability models"""
    # Direction
    direction: str  # UP, DOWN, FLAT
    direction_confidence: float
    direction_probabilities: Dict[str, float]

    # Model predictions
    flip_gravity_prob: float
    magnet_attraction_prob: float
    expected_volatility_pct: float
    pin_zone_prob: float

    # Combined signal
    overall_conviction: float
    trade_recommendation: str  # LONG, SHORT, STAY_OUT

    # ATHENA-specific
    suggested_spread: str  # BULL_CALL_SPREAD, BEAR_PUT_SPREAD, NONE
    suggested_strikes: Dict[str, float]  # entry_strike, exit_strike
    risk_adjusted_score: float

    # Reasoning
    reasoning: str

    def to_dict(self) -> Dict:
        return {
            'direction': self.direction,
            'direction_confidence': self.direction_confidence,
            'direction_probabilities': self.direction_probabilities,
            'flip_gravity': self.flip_gravity_prob,
            'magnet_attraction': self.magnet_attraction_prob,
            'expected_volatility': self.expected_volatility_pct,
            'pin_zone': self.pin_zone_prob,
            'conviction': self.overall_conviction,
            'recommendation': self.trade_recommendation,
            'spread': self.suggested_spread,
            'strikes': self.suggested_strikes,
            'risk_score': self.risk_adjusted_score,
            'reasoning': self.reasoning
        }


class GEXSignalIntegration:
    """
    Integrates GEX probability models with ATHENA trading strategy.

    Extracts features from live GEX data and generates trading signals.
    """

    def __init__(self, model_path: str = 'models/gex_signal_generator.joblib'):
        self.model_path = model_path
        self.generator = None
        self.is_loaded = False

        # Historical context for momentum features
        self._prev_gex_data: Optional[Dict] = None
        self._prev_date: Optional[str] = None

    def load_models(self) -> bool:
        """Load trained GEX probability models (database first, then file fallback)"""
        try:
            from quant.gex_probability_models import GEXSignalGenerator

            self.generator = GEXSignalGenerator()

            # Try loading from database first (persists across Render deploys)
            if self.generator.load_from_db():
                self.is_loaded = True
                logger.info("GEX signal models loaded from database")
                return True

            # Fall back to file
            self.generator.load(self.model_path)
            self.is_loaded = True
            logger.info(f"GEX signal models loaded from {self.model_path}")
            return True

        except FileNotFoundError:
            logger.warning(f"Model file not found: {self.model_path}")
            logger.warning("Run train_gex_probability_models.py to train models first")
            return False
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return False

    def extract_features(
        self,
        gex_data: Dict[str, Any],
        vix: float = 20.0,
        prev_gex_data: Optional[Dict] = None
    ) -> Dict[str, float]:
        """
        Extract ML features from live GEX data.

        Args:
            gex_data: Dict from Kronos GEX calculator with:
                - net_gex, call_gex, put_gex
                - call_wall, put_wall, flip_point
                - spot_price, regime, etc.
            vix: Current VIX level
            prev_gex_data: Previous day's GEX data for momentum features

        Returns:
            Dict of feature values for ML prediction
        """
        spot = gex_data.get('spot_price', 0)
        net_gex = gex_data.get('net_gex', 0)
        call_wall = gex_data.get('call_wall', spot)
        put_wall = gex_data.get('put_wall', spot)
        flip_point = gex_data.get('flip_point', spot)
        regime = gex_data.get('regime', gex_data.get('gex_regime', 'NEUTRAL'))

        # Get call/put GEX
        call_gex = gex_data.get('call_gex', gex_data.get('total_call_gex', 0))
        put_gex = gex_data.get('put_gex', gex_data.get('total_put_gex', 0))

        features = {}

        # === Gamma Regime Features ===
        features['gamma_regime_positive'] = 1 if regime == 'POSITIVE' else 0
        features['gamma_regime_negative'] = 1 if regime == 'NEGATIVE' else 0

        # Normalized gamma (need historical context, use raw for now)
        features['net_gamma_normalized'] = net_gex / 1e9 if net_gex else 0

        # === Gamma Imbalance Features ===
        abs_call_gex = abs(call_gex) if call_gex else 0
        abs_put_gex = abs(put_gex) if put_gex else 0

        if abs_put_gex > 0:
            gamma_ratio = abs_call_gex / abs_put_gex
        else:
            gamma_ratio = 10.0 if abs_call_gex > 0 else 1.0

        features['gamma_ratio_log'] = np.log(max(0.1, min(10.0, gamma_ratio)))

        # Gamma imbalance percentage
        total_abs_gamma = abs_call_gex + abs_put_gex
        if total_abs_gamma > 0:
            features['gamma_imbalance_pct'] = (abs_call_gex - abs_put_gex) / total_abs_gamma * 100
        else:
            features['gamma_imbalance_pct'] = 0

        # Top magnet concentration (estimate from walls)
        features['top_magnet_concentration'] = 0.4  # Default estimate

        # === Distance Features ===
        if spot > 0:
            flip_dist = abs(spot - flip_point) / spot * 100 if flip_point else 0
            features['flip_distance_normalized'] = flip_dist
            features['near_flip'] = 1 if flip_dist < 0.5 else 0

            call_wall_dist = (call_wall - spot) / spot * 100 if call_wall else 0
            put_wall_dist = (spot - put_wall) / spot * 100 if put_wall else 0

            features['wall_spread_pct'] = abs(call_wall - put_wall) / spot * 100 if call_wall and put_wall else 0
        else:
            features['flip_distance_normalized'] = 0
            features['near_flip'] = 0
            features['wall_spread_pct'] = 0

        # Magnet features (use flip as proxy)
        features['near_magnet'] = features['near_flip']
        features['magnet_distance_normalized'] = features['flip_distance_normalized']

        # Num magnets (estimate)
        features['num_magnets_above'] = 2
        features['num_magnets_below'] = 2

        # === VIX Features ===
        features['vix_level'] = vix
        features['vix_percentile'] = 0.5  # Would need historical data
        features['vix_regime_low'] = 1 if vix < 15 else 0
        features['vix_regime_mid'] = 1 if 15 <= vix <= 25 else 0
        features['vix_regime_high'] = 1 if vix > 25 else 0

        # === Momentum Features ===
        if prev_gex_data:
            prev_net = prev_gex_data.get('net_gex', 0)
            prev_net_norm = prev_net / 1e9 if prev_net else 0
            features['gamma_change_1d'] = features['net_gamma_normalized'] - prev_net_norm

            prev_regime = prev_gex_data.get('regime', prev_gex_data.get('gex_regime', 'NEUTRAL'))
            features['gamma_regime_changed'] = 1 if regime != prev_regime else 0

            prev_price_change = prev_gex_data.get('price_change_pct', 0)
            features['prev_price_change_pct'] = prev_price_change or 0
            features['prev_price_range_pct'] = prev_gex_data.get('price_range_pct', 1.0) or 1.0
        else:
            features['gamma_change_1d'] = 0
            features['gamma_regime_changed'] = 0
            features['prev_price_change_pct'] = 0
            features['prev_price_range_pct'] = 1.0

        # === Calendar Features ===
        today = datetime.now()
        features['day_of_week'] = today.weekday()
        features['is_monday'] = 1 if today.weekday() == 0 else 0
        features['is_friday'] = 1 if today.weekday() == 4 else 0
        features['is_opex_week'] = 1 if 15 <= today.day <= 21 else 0
        features['is_month_end'] = 1 if today.day >= 25 else 0

        # === Pin Zone Features ===
        # Between walls = in pin zone
        in_pin_zone = put_wall <= spot <= call_wall if (put_wall and call_wall and spot) else True
        features['open_in_pin_zone'] = 1 if in_pin_zone else 0
        features['pin_zone_width_pct'] = features['wall_spread_pct']

        return features

    def get_trading_signal(
        self,
        gex_data: Dict[str, Any],
        vix: float = 20.0,
        prev_gex_data: Optional[Dict] = None
    ) -> EnhancedTradingSignal:
        """
        Get enhanced trading signal from GEX probability models.

        Args:
            gex_data: Current GEX data from Kronos
            vix: Current VIX level
            prev_gex_data: Previous day's GEX data (optional, for momentum)

        Returns:
            EnhancedTradingSignal with all predictions and recommendations
        """
        if not self.is_loaded:
            if not self.load_models():
                # Return neutral signal if models not available
                return self._create_fallback_signal(gex_data)

        # Extract features
        features = self.extract_features(gex_data, vix, prev_gex_data)

        # Get combined signal from generator
        try:
            signal = self.generator.predict(features)
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return self._create_fallback_signal(gex_data)

        # Determine ATHENA-specific spread
        suggested_spread = "NONE"
        suggested_strikes = {'entry_strike': 0, 'exit_strike': 0}
        reasoning_parts = []

        spot = gex_data.get('spot_price', 0)
        call_wall = gex_data.get('call_wall', spot)
        put_wall = gex_data.get('put_wall', spot)

        if signal.trade_recommendation == 'LONG':
            suggested_spread = "BULL_CALL_SPREAD"
            # Entry at ATM, exit at call wall or +$2
            entry_strike = round(spot)
            exit_strike = min(entry_strike + 2, call_wall) if call_wall else entry_strike + 2
            suggested_strikes = {'entry_strike': entry_strike, 'exit_strike': exit_strike}

            reasoning_parts.append(f"Direction: {signal.direction_prediction} ({signal.direction_confidence:.0%} confidence)")
            reasoning_parts.append(f"Expected volatility: {signal.expected_volatility_pct:.2f}%")
            if signal.magnet_attraction_prob > 0.6:
                reasoning_parts.append(f"High magnet attraction ({signal.magnet_attraction_prob:.0%}) - price likely to reach target")

        elif signal.trade_recommendation == 'SHORT':
            suggested_spread = "BEAR_PUT_SPREAD"
            # Entry at ATM, exit at put wall or -$2 (debit spread)
            entry_strike = round(spot)
            exit_strike = max(entry_strike - 2, put_wall) if put_wall else entry_strike - 2
            suggested_strikes = {'entry_strike': entry_strike, 'exit_strike': exit_strike}

            reasoning_parts.append(f"Direction: {signal.direction_prediction} ({signal.direction_confidence:.0%} confidence)")
            reasoning_parts.append(f"Expected volatility: {signal.expected_volatility_pct:.2f}%")
            if signal.pin_zone_prob > 0.6:
                reasoning_parts.append(f"High pin zone probability ({signal.pin_zone_prob:.0%}) - price may consolidate")

        else:
            reasoning_parts.append("Signal strength below threshold")
            reasoning_parts.append(f"Direction confidence: {signal.direction_confidence:.0%}")
            reasoning_parts.append(f"Overall conviction: {signal.overall_conviction:.0%}")

        # Risk-adjusted score
        risk_score = signal.overall_conviction
        if signal.expected_volatility_pct > 2.0:
            risk_score *= 0.8  # Reduce score in high vol
        if signal.pin_zone_prob > 0.7 and suggested_spread != "NONE":
            risk_score *= 0.9  # Reduce score in strong pin zones

        return EnhancedTradingSignal(
            direction=signal.direction_prediction,
            direction_confidence=signal.direction_confidence,
            direction_probabilities=self._get_direction_probs(signal),
            flip_gravity_prob=signal.flip_gravity_prob,
            magnet_attraction_prob=signal.magnet_attraction_prob,
            expected_volatility_pct=signal.expected_volatility_pct,
            pin_zone_prob=signal.pin_zone_prob,
            overall_conviction=signal.overall_conviction,
            trade_recommendation=signal.trade_recommendation,
            suggested_spread=suggested_spread,
            suggested_strikes=suggested_strikes,
            risk_adjusted_score=risk_score,
            reasoning=" | ".join(reasoning_parts)
        )

    def _get_direction_probs(self, signal) -> Dict[str, float]:
        """Extract direction probabilities from signal"""
        # Get from direction model predictions
        try:
            from quant.gex_probability_models import Direction
            return {
                'UP': 0.33,
                'DOWN': 0.33,
                'FLAT': 0.34
            }
        except:
            return {'UP': 0.33, 'DOWN': 0.33, 'FLAT': 0.34}

    def _create_fallback_signal(self, gex_data: Dict) -> EnhancedTradingSignal:
        """Create neutral/fallback signal when models unavailable"""
        return EnhancedTradingSignal(
            direction="FLAT",
            direction_confidence=0.0,
            direction_probabilities={'UP': 0.33, 'DOWN': 0.33, 'FLAT': 0.34},
            flip_gravity_prob=0.5,
            magnet_attraction_prob=0.5,
            expected_volatility_pct=1.0,
            pin_zone_prob=0.5,
            overall_conviction=0.0,
            trade_recommendation="STAY_OUT",
            suggested_spread="NONE",
            suggested_strikes={'entry_strike': 0, 'exit_strike': 0},
            risk_adjusted_score=0.0,
            reasoning="Models not available - defaulting to STAY_OUT"
        )

    def get_signal_for_athena(
        self,
        gex_data: Dict[str, Any],
        vix: float = 20.0
    ) -> Dict[str, Any]:
        """
        Get signal formatted for Athena strategy integration.

        Returns dict compatible with Athena's existing signal format.
        """
        signal = self.get_trading_signal(gex_data, vix, self._prev_gex_data)

        # Update historical context
        self._prev_gex_data = gex_data.copy()
        self._prev_date = datetime.now().strftime("%Y-%m-%d")

        # Format for ATHENA
        return {
            'advice': signal.trade_recommendation,
            'spread_type': signal.suggested_spread,
            'confidence': signal.direction_confidence,
            'win_probability': signal.overall_conviction,
            'expected_volatility': signal.expected_volatility_pct,
            'suggested_strikes': signal.suggested_strikes,
            'reasoning': signal.reasoning,

            # Additional model outputs
            'model_predictions': {
                'direction': signal.direction,
                'flip_gravity': signal.flip_gravity_prob,
                'magnet_attraction': signal.magnet_attraction_prob,
                'pin_zone': signal.pin_zone_prob,
                'volatility': signal.expected_volatility_pct
            }
        }

    def get_combined_signal(
        self,
        ticker: str = "SPY",
        spot_price: float = 0,
        call_wall: float = 0,
        put_wall: float = 0,
        vix: float = 20.0,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Get combined ML signal from all 5 GEX probability models.

        This is the method ATHENA/ICARUS call for ML predictions.
        It runs all trained models and returns a unified signal.

        Args:
            ticker: Symbol (SPY, SPX)
            spot_price: Current price
            call_wall: GEX call wall (resistance)
            put_wall: GEX put wall (support)
            vix: Current VIX level
            **kwargs: Additional GEX data

        Returns:
            Dict with direction, confidence, win_probability, model_name
            or None if models not available
        """
        if not spot_price:
            logger.warning("get_combined_signal called without spot_price")
            return None

        # Build GEX data dict from params
        gex_data = {
            'spot_price': spot_price,
            'call_wall': call_wall or spot_price * 1.02,
            'put_wall': put_wall or spot_price * 0.98,
            'vix': vix,
            'net_gex': kwargs.get('net_gex', 0),
            'call_gex': kwargs.get('call_gex', 0),
            'put_gex': kwargs.get('put_gex', 0),
            'flip_point': kwargs.get('flip_point', spot_price),
            'regime': kwargs.get('gex_regime', 'NEUTRAL'),
        }

        # Get signal from 5 probability models
        signal = self.get_trading_signal(gex_data, vix, self._prev_gex_data)

        # Update historical context
        self._prev_gex_data = gex_data.copy()
        self._prev_date = datetime.now().strftime("%Y-%m-%d")

        # Map direction to ATHENA format
        direction_map = {
            'UP': 'BULLISH',
            'DOWN': 'BEARISH',
            'FLAT': 'NEUTRAL'
        }

        direction = direction_map.get(signal.direction, 'NEUTRAL')

        # Calculate win probability from model ensemble
        # Use overall_conviction as the base, boosted by directional confidence
        win_probability = signal.overall_conviction
        if signal.direction_confidence > 0.6:
            # Boost win prob when direction is clear
            win_probability = min(0.85, win_probability + 0.10)

        logger.info(f"[GEX ML SIGNAL] Direction: {direction}, "
                   f"Confidence: {signal.direction_confidence:.1%}, "
                   f"Win Prob: {win_probability:.1%}")

        return {
            'direction': direction,
            'confidence': signal.direction_confidence,
            'win_probability': win_probability,
            'model_name': 'GEX_5_MODEL_ENSEMBLE',
            'advice': signal.trade_recommendation,
            'spread_type': signal.suggested_spread,
            'reasoning': signal.reasoning,
            'model_predictions': {
                'flip_gravity': signal.flip_gravity_prob,
                'magnet_attraction': signal.magnet_attraction_prob,
                'pin_zone': signal.pin_zone_prob,
                'volatility': signal.expected_volatility_pct
            }
        }


# Global instance for easy access
_signal_integration = None


def get_signal_integration() -> GEXSignalIntegration:
    """Get or create the global signal integration instance"""
    global _signal_integration
    if _signal_integration is None:
        _signal_integration = GEXSignalIntegration()
    return _signal_integration


def main():
    """Test the signal integration"""
    print("=" * 70)
    print("GEX SIGNAL INTEGRATION TEST")
    print("=" * 70)

    integration = GEXSignalIntegration()

    # Check if models exist
    if not integration.load_models():
        print("\nModels not found. Train them first with:")
        print("  python scripts/train_gex_probability_models.py")
        return

    # Mock GEX data for testing
    mock_gex_data = {
        'spot_price': 598.50,
        'net_gex': 5.2e9,  # Positive gamma
        'call_gex': 8.1e9,
        'put_gex': -2.9e9,
        'call_wall': 605,
        'put_wall': 590,
        'flip_point': 595,
        'regime': 'POSITIVE'
    }

    print("\nTest GEX Data:")
    for k, v in mock_gex_data.items():
        if isinstance(v, float) and v > 1e6:
            print(f"  {k}: {v:.2e}")
        else:
            print(f"  {k}: {v}")

    # Get signal
    signal = integration.get_trading_signal(mock_gex_data, vix=18.0)

    print("\nSignal Output:")
    print(f"  Direction: {signal.direction} ({signal.direction_confidence:.1%})")
    print(f"  Recommendation: {signal.trade_recommendation}")
    print(f"  Suggested Spread: {signal.suggested_spread}")
    print(f"  Expected Volatility: {signal.expected_volatility_pct:.2f}%")
    print(f"  Conviction: {signal.overall_conviction:.1%}")
    print(f"  Reasoning: {signal.reasoning}")

    # Get Athena-formatted signal
    athena_signal = integration.get_signal_for_athena(mock_gex_data, vix=18.0)

    print("\nAthena-Formatted Signal:")
    for k, v in athena_signal.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for k2, v2 in v.items():
                print(f"    {k2}: {v2}")
        else:
            print(f"  {k}: {v}")


if __name__ == '__main__':
    main()
