"""
Quant Module Integration with AlphaGEX

This module integrates quant enhancements with the existing AlphaGEX system:

1. Walk-Forward Optimizer -> Validates backtest results
2. Monte Carlo Kelly -> Safer position sizing in position_sizer.py
3. Oracle Advisor -> Primary decision maker (replaced ML Regime Classifier and Ensemble)

Note: ML Regime Classifier and Ensemble Strategy were removed in January 2025.
Oracle is now the sole decision authority for all trading bots.

Usage:
    from quant.integration import QuantEnhancedTrader

    trader = QuantEnhancedTrader("SPY")
    recommendation = trader.get_enhanced_recommendation(market_data)

Author: AlphaGEX Quant
Date: 2025-12-03 (Updated: 2026-01)
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Import quant modules - with graceful fallbacks for removed modules
ML_REGIME_AVAILABLE = False
ENSEMBLE_AVAILABLE = False

# ML Regime Classifier - REMOVED, Oracle handles this now
try:
    from .ml_regime_classifier import (
        MLRegimeClassifier,
        get_ml_regime_prediction,
        train_regime_classifier,
        MLPrediction
    )
    ML_REGIME_AVAILABLE = True
except ImportError:
    # Stub classes for removed module
    MLRegimeClassifier = None
    MLPrediction = None
    def get_ml_regime_prediction(*args, **kwargs):
        return None
    def train_regime_classifier(*args, **kwargs):
        return None

# Walk-Forward Optimizer (still active)
try:
    from .walk_forward_optimizer import (
        WalkForwardOptimizer,
        run_walk_forward_validation,
        WalkForwardResult
    )
except ImportError:
    WalkForwardOptimizer = None
    WalkForwardResult = None
    def run_walk_forward_validation(*args, **kwargs):
        return None

# Ensemble Strategy - REMOVED, Oracle is sole authority
try:
    from .ensemble_strategy import (
        EnsembleStrategyWeighter,
        get_ensemble_signal,
        EnsembleSignal,
        StrategySignal
    )
    ENSEMBLE_AVAILABLE = True
except ImportError:
    # Stub classes for removed module
    EnsembleStrategyWeighter = None
    EnsembleSignal = None
    StrategySignal = None
    def get_ensemble_signal(*args, **kwargs):
        return None

# Monte Carlo Kelly (still active)
try:
    from .monte_carlo_kelly import (
        MonteCarloKelly,
        get_safe_position_size,
        validate_current_sizing,
        KellyStressTest
    )
except ImportError:
    MonteCarloKelly = None
    KellyStressTest = None
    def get_safe_position_size(*args, **kwargs):
        return 0.02  # Default 2%
    def validate_current_sizing(*args, **kwargs):
        return True

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


@dataclass
class QuantRecommendation:
    """Complete trading recommendation from quant system"""
    timestamp: datetime
    symbol: str

    # Signal
    action: str  # BUY_CALLS, BUY_PUTS, SELL_PREMIUM, STAY_FLAT
    confidence: float
    should_trade: bool

    # Position sizing
    position_size_pct: float
    position_value: float
    kelly_safe: float
    kelly_optimal: float

    # Risk metrics
    prob_ruin: float
    var_95: float
    uncertainty_level: str

    # Component analysis
    ml_prediction: Optional[Dict]
    ensemble_signal: Optional[Dict]
    walk_forward_valid: bool

    # Reasoning
    reasoning: str
    warnings: List[str]

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'action': self.action,
            'confidence': round(self.confidence, 1),
            'should_trade': self.should_trade,
            'position_size_pct': round(self.position_size_pct, 2),
            'position_value': round(self.position_value, 2),
            'kelly_safe': round(self.kelly_safe, 3),
            'prob_ruin': round(self.prob_ruin, 2),
            'var_95': round(self.var_95, 1),
            'uncertainty_level': self.uncertainty_level,
            'walk_forward_valid': self.walk_forward_valid,
            'reasoning': self.reasoning,
            'warnings': self.warnings
        }


class QuantEnhancedTrader:
    """
    Enhanced trader integrating all quant modules.

    This class wraps the existing AlphaGEX trading logic with:
    1. ML-based regime detection (replaces hard-coded thresholds)
    2. Ensemble signal combination (reduces single-strategy risk)
    3. Walk-forward validated parameters (prevents overfitting)
    4. Monte Carlo position sizing (prevents ruin from Kelly overconfidence)
    """

    def __init__(
        self,
        symbol: str = "SPY",
        account_size: float = 10000,
        max_risk_pct: float = 15.0
    ):
        self.symbol = symbol
        self.account_size = account_size
        self.max_risk_pct = max_risk_pct

        # Initialize quant components
        self.ml_classifier = MLRegimeClassifier(symbol)
        self.ensemble_weighter = EnsembleStrategyWeighter(symbol)
        self.walk_forward = WalkForwardOptimizer(symbol)
        self.monte_carlo = MonteCarloKelly()

        # Track strategy stats for Kelly calculation
        self.strategy_stats = self._load_strategy_stats()

    def _load_strategy_stats(self) -> Dict:
        """Load strategy statistics from database or defaults"""
        default_stats = {
            'win_rate': 0.55,
            'avg_win': 10.0,
            'avg_loss': 12.0,
            'total_trades': 20
        }

        if not DB_AVAILABLE:
            return default_stats

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl_percent > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(CASE WHEN pnl_percent > 0 THEN pnl_percent END) as avg_win,
                    AVG(CASE WHEN pnl_percent <= 0 THEN ABS(pnl_percent) END) as avg_loss
                FROM paper_trades
                WHERE symbol = %s
                  AND (exit_date IS NOT NULL OR status IN ('closed', 'expired'))
                  AND entry_date >= NOW() - INTERVAL '180 days'
            """, (self.symbol,))

            row = c.fetchone()
            conn.close()

            if row and row[0] > 10:
                return {
                    'win_rate': (row[1] or 0) / row[0] if row[0] > 0 else 0.55,
                    'avg_win': row[2] or 10.0,
                    'avg_loss': row[3] or 12.0,
                    'total_trades': row[0]
                }

        except Exception as e:
            print(f"Could not load strategy stats: {e}")

        return default_stats

    def _check_walk_forward_validity(self) -> bool:
        """
        Check if current strategy parameters are walk-forward validated.

        Queries the walk_forward_results table to see if:
        1. There's a recent walk-forward analysis (within 30 days)
        2. The strategy passed robustness checks (degradation < 20%, OOS win rate > 50%)

        Returns:
            True if walk-forward validated or no validation data exists (assume valid)
            False if validation failed
        """
        if not DB_AVAILABLE:
            return True  # No DB, assume valid

        try:
            conn = get_connection()
            c = conn.cursor()

            # Check for recent walk-forward results
            c.execute("""
                SELECT
                    strategy_name,
                    is_avg_win_rate,
                    oos_avg_win_rate,
                    degradation_pct,
                    is_robust,
                    analysis_date
                FROM walk_forward_results
                WHERE symbol = %s
                  AND analysis_date >= NOW() - INTERVAL '30 days'
                ORDER BY analysis_date DESC
                LIMIT 1
            """, (self.symbol,))

            row = c.fetchone()
            conn.close()

            if row is None:
                # No walk-forward data - assume valid but log warning
                return True

            # Check robustness criteria:
            # 1. OOS win rate > 50%
            # 2. Degradation < 20% (OOS not much worse than IS)
            # 3. Explicitly marked as robust
            is_robust = row[4]  # is_robust column
            oos_win_rate = row[2] or 0
            degradation = row[3] or 100

            if is_robust and oos_win_rate > 50 and degradation < 20:
                return True

            # Strategy failed walk-forward validation
            return False

        except Exception as e:
            # On error, assume valid to not block trading
            print(f"Could not check walk-forward validity: {e}")
            return True

    def get_ml_prediction(
        self,
        gex_data: Dict,
        vix: float,
        iv_rank: float
    ) -> MLPrediction:
        """Get ML-based regime prediction"""
        # Extract features from GEX data
        net_gex = gex_data.get('net_gex', 0)
        flip_point = gex_data.get('flip_point', 0)
        spot_price = gex_data.get('spot_price', 0)

        # Calculate derived features
        gex_normalized = net_gex / 1e9 if net_gex != 0 else 1.0
        gex_percentile = gex_data.get('gex_percentile', 50)
        distance_to_flip = ((spot_price - flip_point) / flip_point * 100) if flip_point > 0 else 0

        return get_ml_regime_prediction(
            symbol=self.symbol,
            gex_normalized=gex_normalized,
            gex_percentile=gex_percentile,
            gex_change_1d=gex_data.get('gex_change_1d', 0),
            gex_change_5d=gex_data.get('gex_change_5d', 0),
            vix=vix,
            vix_percentile=gex_data.get('vix_percentile', 50),
            vix_change_1d=gex_data.get('vix_change_1d', 0),
            iv_rank=iv_rank,
            iv_hv_ratio=gex_data.get('iv_hv_ratio', 1.0),
            distance_to_flip=distance_to_flip,
            momentum_1h=gex_data.get('momentum_1h', 0),
            momentum_4h=gex_data.get('momentum_4h', 0),
            above_20ma=gex_data.get('above_20ma', True),
            above_50ma=gex_data.get('above_50ma', True),
            regime_duration=gex_data.get('regime_duration', 5),
            day_of_week=datetime.now().weekday(),
            days_to_opex=gex_data.get('days_to_opex', 15)
        )

    def get_ensemble_signal(
        self,
        gex_data: Dict,
        ml_prediction: MLPrediction,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None
    ) -> EnsembleSignal:
        """Get ensemble signal combining all strategies"""
        return get_ensemble_signal(
            symbol=self.symbol,
            gex_data={
                'recommended_action': gex_data.get('recommended_action', 'STAY_FLAT'),
                'confidence': gex_data.get('confidence', 50),
                'reasoning': gex_data.get('reasoning', '')
            },
            psychology_data=psychology_data,
            rsi_data=rsi_data,
            vol_surface_data=vol_surface_data,
            ml_prediction={
                'predicted_action': ml_prediction.predicted_action.value,
                'confidence': ml_prediction.confidence,
                'is_trained': ml_prediction.is_trained
            },
            current_regime=gex_data.get('gamma_regime', 'UNKNOWN')
        )

    def get_safe_position_size(self) -> Dict:
        """Get Monte Carlo validated position size"""
        return get_safe_position_size(
            win_rate=self.strategy_stats['win_rate'],
            avg_win=self.strategy_stats['avg_win'],
            avg_loss=self.strategy_stats['avg_loss'],
            sample_size=self.strategy_stats['total_trades'],
            account_size=self.account_size,
            max_risk_pct=self.max_risk_pct
        )

    def get_enhanced_recommendation(
        self,
        gex_data: Dict,
        vix: float = 20.0,
        iv_rank: float = 50.0,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None
    ) -> QuantRecommendation:
        """
        Get complete trading recommendation with all quant enhancements.

        This is the MAIN ENTRY POINT for the quant system.

        Args:
            gex_data: GEX data dict with net_gex, flip_point, spot_price, etc.
            vix: Current VIX level
            iv_rank: Current IV rank (0-100)
            psychology_data: Optional psychology trap data
            rsi_data: Optional RSI multi-timeframe data
            vol_surface_data: Optional vol surface analysis

        Returns:
            QuantRecommendation with action, sizing, and risk metrics
        """
        warnings = []

        # 1. Get ML prediction
        try:
            ml_prediction = self.get_ml_prediction(gex_data, vix, iv_rank)
            ml_dict = {
                'action': ml_prediction.predicted_action.value,
                'confidence': ml_prediction.confidence,
                'is_trained': ml_prediction.is_trained
            }
            if not ml_prediction.is_trained:
                warnings.append("ML model not trained - using rule-based fallback")
        except Exception as e:
            ml_prediction = None
            ml_dict = None
            warnings.append(f"ML prediction failed: {str(e)}")

        # 2. Get ensemble signal
        try:
            ensemble = self.get_ensemble_signal(
                gex_data, ml_prediction, psychology_data, rsi_data, vol_surface_data
            )
            ensemble_dict = ensemble.to_dict()
        except Exception as e:
            ensemble = None
            ensemble_dict = None
            warnings.append(f"Ensemble signal failed: {str(e)}")

        # 3. Get safe position size
        try:
            sizing = self.get_safe_position_size()
        except Exception as e:
            sizing = {
                'position_size_pct': 5.0,
                'position_value': self.account_size * 0.05,
                'kelly_safe': 0.05,
                'kelly_optimal': 0.10,
                'prob_ruin': 5.0,
                'var_95': 20.0,
                'uncertainty_level': 'high',
                'recommendation': 'Error calculating sizing'
            }
            warnings.append(f"Position sizing failed: {str(e)}")

        # 4. Determine action
        if ensemble and ensemble.should_trade:
            if ensemble.final_signal in [StrategySignal.STRONG_BUY, StrategySignal.BUY]:
                action = "BUY_CALLS"
            elif ensemble.final_signal in [StrategySignal.STRONG_SELL, StrategySignal.SELL]:
                action = "BUY_PUTS"
            else:
                action = "STAY_FLAT"
            confidence = ensemble.confidence
            should_trade = True
        elif ml_prediction and ml_prediction.confidence > 70:
            action = ml_prediction.predicted_action.value
            confidence = ml_prediction.confidence
            should_trade = True
        else:
            action = gex_data.get('recommended_action', 'STAY_FLAT')
            confidence = gex_data.get('confidence', 50)
            should_trade = confidence >= 65

        # 5. Adjust position size based on ensemble conviction
        if ensemble:
            position_multiplier = ensemble.position_size_multiplier
        else:
            position_multiplier = 0.75  # Conservative without ensemble

        adjusted_size_pct = sizing['position_size_pct'] * position_multiplier
        adjusted_value = self.account_size * (adjusted_size_pct / 100)

        # 6. Check for warnings
        if sizing['prob_ruin'] > 5:
            warnings.append(f"High ruin probability: {sizing['prob_ruin']:.1f}%")
        if sizing['uncertainty_level'] == 'high':
            warnings.append("High uncertainty - limited trade history")
        if self.strategy_stats['total_trades'] < 20:
            warnings.append(f"Small sample size: only {self.strategy_stats['total_trades']} trades")

        # 7. Build reasoning
        reasoning_parts = []
        if ml_prediction:
            reasoning_parts.append(f"ML: {ml_prediction.predicted_action.value} ({ml_prediction.confidence:.0f}%)")
        if ensemble:
            reasoning_parts.append(f"Ensemble: {ensemble.final_signal.value} ({ensemble.confidence:.0f}%)")
        reasoning_parts.append(f"Safe Kelly: {sizing['kelly_safe']:.1f}%")
        reasoning_parts.append(f"Uncertainty: {sizing['uncertainty_level']}")

        # Walk-forward validation check
        # Checks database for recent walk-forward results to ensure strategy is robust
        walk_forward_valid = self._check_walk_forward_validity()

        return QuantRecommendation(
            timestamp=datetime.now(),
            symbol=self.symbol,
            action=action,
            confidence=confidence,
            should_trade=should_trade and len(warnings) < 3,
            position_size_pct=adjusted_size_pct,
            position_value=adjusted_value,
            kelly_safe=sizing['kelly_safe'],
            kelly_optimal=sizing['kelly_optimal'],
            prob_ruin=sizing['prob_ruin'],
            var_95=sizing['var_95'],
            uncertainty_level=sizing['uncertainty_level'],
            ml_prediction=ml_dict,
            ensemble_signal=ensemble_dict,
            walk_forward_valid=walk_forward_valid,
            reasoning=" | ".join(reasoning_parts),
            warnings=warnings
        )

    def update_strategy_stats(self, pnl_pct: float, regime: str):
        """Update strategy statistics after a trade"""
        # Update ensemble weighter
        self.ensemble_weighter.record_trade_outcome(
            strategy_name=self.symbol,
            pnl_pct=pnl_pct,
            regime=regime
        )

        # Reload stats
        self.strategy_stats = self._load_strategy_stats()


# Convenience functions for direct use
def get_quant_recommendation(
    symbol: str = "SPY",
    account_size: float = 10000,
    gex_data: Dict = None,
    vix: float = 20.0,
    iv_rank: float = 50.0
) -> QuantRecommendation:
    """
    Get quant-enhanced trading recommendation.

    Example:
        rec = get_quant_recommendation(
            symbol="SPY",
            account_size=25000,
            gex_data={
                'net_gex': -1.5e9,
                'flip_point': 580,
                'spot_price': 575,
                'recommended_action': 'BUY_CALLS',
                'confidence': 70
            },
            vix=22,
            iv_rank=65
        )

        if rec.should_trade:
            print(f"Action: {rec.action}")
            print(f"Position: {rec.position_size_pct:.1f}% = ${rec.position_value:.2f}")
            print(f"Prob of ruin: {rec.prob_ruin:.1f}%")
    """
    trader = QuantEnhancedTrader(symbol, account_size)
    return trader.get_enhanced_recommendation(
        gex_data=gex_data or {},
        vix=vix,
        iv_rank=iv_rank
    )


def validate_and_size_trade(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    sample_size: int,
    current_kelly_pct: float,
    account_size: float
) -> Dict:
    """
    Validate current sizing and get safe alternative.

    Returns:
        Dict with is_safe, recommended_size, and risk metrics
    """
    # Validate current
    validation = validate_current_sizing(
        current_kelly_pct=current_kelly_pct,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        sample_size=sample_size
    )

    # Get safe size
    safe_sizing = get_safe_position_size(
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        sample_size=sample_size,
        account_size=account_size
    )

    return {
        'current_is_safe': validation['is_safe'],
        'current_risk_level': validation['risk_level'],
        'current_warning': validation['warning'],
        'recommended_kelly_pct': safe_sizing['kelly_safe'],
        'recommended_position_value': safe_sizing['position_value'],
        'prob_ruin_at_current': validation['prob_ruin_at_current'],
        'prob_ruin_at_recommended': safe_sizing['prob_ruin']
    }


if __name__ == "__main__":
    print("=" * 60)
    print("Quant Integration Test")
    print("=" * 60)

    # Test with sample data
    rec = get_quant_recommendation(
        symbol="SPY",
        account_size=25000,
        gex_data={
            'net_gex': -1.5e9,
            'flip_point': 580,
            'spot_price': 575,
            'gex_percentile': 25,
            'recommended_action': 'BUY_CALLS',
            'confidence': 72,
            'gamma_regime': 'NEGATIVE'
        },
        vix=24,
        iv_rank=68
    )

    print(f"\nQuant Recommendation:")
    print(f"  Action: {rec.action}")
    print(f"  Confidence: {rec.confidence:.1f}%")
    print(f"  Should Trade: {rec.should_trade}")
    print(f"\nPosition Sizing:")
    print(f"  Size: {rec.position_size_pct:.1f}% of account")
    print(f"  Value: ${rec.position_value:.2f}")
    print(f"  Kelly Safe: {rec.kelly_safe:.1f}%")
    print(f"  Kelly Optimal: {rec.kelly_optimal:.1f}%")
    print(f"\nRisk Metrics:")
    print(f"  Prob of Ruin: {rec.prob_ruin:.1f}%")
    print(f"  95% VaR: {rec.var_95:.1f}%")
    print(f"  Uncertainty: {rec.uncertainty_level}")
    print(f"\nWalk-Forward Valid: {rec.walk_forward_valid}")
    print(f"\nReasoning: {rec.reasoning}")

    if rec.warnings:
        print(f"\nWarnings:")
        for w in rec.warnings:
            print(f"  - {w}")
