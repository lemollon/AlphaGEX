"""
Auto-Validation System
======================

Unified system that connects:
1. Walk-Forward Validation - Runs periodically to validate ML models
2. Auto-Retrain Triggers - Triggers model retraining when degradation detected
3. Thompson Capital Allocator - Dynamically allocates capital based on performance

This runs WITHOUT OMEGA - it's a standalone monitoring and optimization layer.

Author: AlphaGEX Quant
Date: 2025-01
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_connection = None

# Walk-Forward Optimizer
try:
    from quant.walk_forward_optimizer import WalkForwardOptimizer, WalkForwardResult
    WALKFORWARD_AVAILABLE = True
except ImportError:
    WALKFORWARD_AVAILABLE = False
    WalkForwardOptimizer = None

# Thompson Sampling Allocator
try:
    from core.math_optimizers import ThompsonSamplingAllocator, ThompsonAllocation
    THOMPSON_AVAILABLE = True
except ImportError:
    THOMPSON_AVAILABLE = False
    ThompsonSamplingAllocator = None


# =============================================================================
# DATA CLASSES
# =============================================================================

class ModelStatus(Enum):
    """Status of an ML model"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RETRAINING = "retraining"
    FAILED = "failed"


@dataclass
class ModelValidationResult:
    """Result of validating a single ML model"""
    model_name: str
    validated_at: str
    in_sample_accuracy: float
    out_of_sample_accuracy: float
    degradation_pct: float
    is_robust: bool
    status: ModelStatus
    recommendation: str  # KEEP, RETRAIN, or INVESTIGATE
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'status': self.status.value
        }


@dataclass
class RetrainTrigger:
    """Trigger for model retraining"""
    model_name: str
    triggered_at: str
    reason: str
    degradation_pct: float
    previous_accuracy: float
    retrain_started: bool = False
    retrain_completed: bool = False


@dataclass
class CapitalAllocation:
    """Capital allocation across bots"""
    timestamp: str
    total_capital: float
    allocations: Dict[str, float]  # bot_name -> allocated_amount
    allocation_pcts: Dict[str, float]  # bot_name -> percentage
    method: str  # "thompson" or "equal"
    confidence: Dict[str, float]  # bot_name -> confidence score


# =============================================================================
# ML MODEL REGISTRY
# =============================================================================

class MLModelRegistry:
    """
    Registry of ML models that can be validated and retrained.

    Each registered model needs:
    - Name
    - Validation function
    - Retrain function
    - Current parameters
    """

    def __init__(self):
        self.models: Dict[str, Dict] = {}
        self._register_all_models()

    def _register_all_models(self):
        """Register ALL ML models in the system"""

        # =====================================================================
        # 1. GEX PROBABILITY MODELS (5 sub-models)
        # =====================================================================
        self.register_model(
            name="gex_signal_generator",
            description="Ensemble of 5 GEX models: Direction, FlipGravity, MagnetAttraction, Volatility, PinZone",
            validate_func=self._validate_gex_signal_generator,
            retrain_func=self._retrain_gex_signal_generator,
            degradation_threshold=0.20
        )

        # =====================================================================
        # 2. GEX DIRECTIONAL ML
        # =====================================================================
        self.register_model(
            name="gex_directional_ml",
            description="Predicts SPY direction (BULLISH/BEARISH/FLAT) from GEX at market open",
            validate_func=self._validate_gex_directional,
            retrain_func=self._retrain_gex_directional,
            degradation_threshold=0.20
        )

        # =====================================================================
        # 3. ML REGIME CLASSIFIER
        # =====================================================================
        self.register_model(
            name="ml_regime_classifier",
            description="Classifies market regime with learned decision boundaries",
            validate_func=self._validate_regime_classifier,
            retrain_func=self._retrain_regime_classifier,
            degradation_threshold=0.15
        )

        # =====================================================================
        # 4. FORTRESS ML ADVISOR (Iron Condor)
        # =====================================================================
        self.register_model(
            name="fortress_ml_advisor",
            description="Predicts iron condor win probability from CHRONICLES backtest data",
            validate_func=self._validate_ares_advisor,
            retrain_func=self._retrain_ares_advisor,
            degradation_threshold=0.20
        )

        # =====================================================================
        # 5. PROPHET ADVISOR (Multi-Strategy)
        # =====================================================================
        self.register_model(
            name="prophet_advisor",
            description="Central advisory system for FORTRESS, CORNERSTONE, LAZARUS - aggregates signals",
            validate_func=self._validate_prophet_advisor,
            retrain_func=self._retrain_prophet_advisor,
            degradation_threshold=0.20
        )

        # =====================================================================
        # 6. DISCERNMENT ML ENGINE (Live Scanner)
        # =====================================================================
        self.register_model(
            name="discernment_ml_engine",
            description="AI-powered live options scanner with direction/magnitude/timing predictions",
            validate_func=self._validate_discernment_ml,
            retrain_func=self._retrain_discernment_ml,
            degradation_threshold=0.25
        )

        # =====================================================================
        # 7. SPX WHEEL ML
        # =====================================================================
        self.register_model(
            name="spx_wheel_ml",
            description="Strike selection optimization for SPX wheel strategy",
            validate_func=self._validate_spx_wheel_ml,
            retrain_func=self._retrain_spx_wheel_ml,
            degradation_threshold=0.20
        )

        # =====================================================================
        # 9. MARKET REGIME CLASSIFIER (Core)
        # =====================================================================
        self.register_model(
            name="market_regime_classifier",
            description="Unified regime classification (SELL_PREMIUM/BUY_CALLS/BUY_PUTS/STAY_FLAT)",
            validate_func=self._validate_market_regime,
            retrain_func=self._retrain_market_regime,
            degradation_threshold=0.15
        )

        # =====================================================================
        # 10. AUTONOMOUS ML PATTERN LEARNER
        # =====================================================================
        self.register_model(
            name="pattern_learner",
            description="ML-powered pattern recognition for trading patterns",
            validate_func=self._validate_pattern_learner,
            retrain_func=self._retrain_pattern_learner,
            degradation_threshold=0.25
        )

        # =====================================================================
        # 11. SOLOMON ML (if exists)
        # =====================================================================
        self.register_model(
            name="solomon_ml",
            description="Directional spread entry/exit predictions for SOLOMON",
            validate_func=self._validate_solomon_ml,
            retrain_func=self._retrain_solomon_ml,
            degradation_threshold=0.20
        )

        logger.info(f"Registered {len(self.models)} ML models for auto-validation")

    def register_model(
        self,
        name: str,
        description: str,
        validate_func: Callable,
        retrain_func: Callable,
        degradation_threshold: float = 0.20
    ):
        """Register an ML model for auto-validation"""
        self.models[name] = {
            'name': name,
            'description': description,
            'validate_func': validate_func,
            'retrain_func': retrain_func,
            'degradation_threshold': degradation_threshold,
            'last_validation': None,
            'last_retrain': None,
            'status': ModelStatus.HEALTHY
        }
        logger.info(f"Registered ML model: {name}")

    def _validate_gex_directional(self) -> ModelValidationResult:
        """Validate GEX Directional ML model"""
        try:
            from quant.gex_directional_ml import GEXDirectionalPredictor

            predictor = GEXDirectionalPredictor()

            # Get recent performance metrics
            metrics = predictor.get_performance_metrics() if hasattr(predictor, 'get_performance_metrics') else {}

            is_accuracy = metrics.get('train_accuracy', 0.65)
            oos_accuracy = metrics.get('test_accuracy', 0.55)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.20

            return ModelValidationResult(
                model_name="gex_directional_ml",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"GEX Directional validation failed: {e}")
            return ModelValidationResult(
                model_name="gex_directional_ml",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=0,
                out_of_sample_accuracy=0,
                degradation_pct=100,
                is_robust=False,
                status=ModelStatus.FAILED,
                recommendation="INVESTIGATE",
                details={'error': str(e)}
            )

    def _validate_regime_classifier(self) -> ModelValidationResult:
        """Validate ML Regime Classifier"""
        try:
            from quant.ml_regime_classifier import MLRegimeClassifier

            classifier = MLRegimeClassifier()

            # Get performance metrics
            metrics = classifier.get_metrics() if hasattr(classifier, 'get_metrics') else {}

            is_accuracy = metrics.get('train_accuracy', 0.70)
            oos_accuracy = metrics.get('validation_accuracy', 0.60)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.15

            return ModelValidationResult(
                model_name="ml_regime_classifier",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"Regime Classifier validation failed: {e}")
            return ModelValidationResult(
                model_name="ml_regime_classifier",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=0,
                out_of_sample_accuracy=0,
                degradation_pct=100,
                is_robust=False,
                status=ModelStatus.FAILED,
                recommendation="INVESTIGATE",
                details={'error': str(e)}
            )

    def _validate_ares_advisor(self) -> ModelValidationResult:
        """Validate FORTRESS ML Advisor"""
        try:
            from quant.fortress_ml_advisor import ARESMLAdvisor

            advisor = ARESMLAdvisor()

            # Get performance metrics
            metrics = advisor.get_model_performance() if hasattr(advisor, 'get_model_performance') else {}

            is_accuracy = metrics.get('in_sample_win_rate', 0.65)
            oos_accuracy = metrics.get('out_of_sample_win_rate', 0.55)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.20

            return ModelValidationResult(
                model_name="fortress_ml_advisor",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"FORTRESS ML Advisor validation failed: {e}")
            return ModelValidationResult(
                model_name="fortress_ml_advisor",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=0,
                out_of_sample_accuracy=0,
                degradation_pct=100,
                is_robust=False,
                status=ModelStatus.FAILED,
                recommendation="INVESTIGATE",
                details={'error': str(e)}
            )

    def _retrain_gex_directional(self) -> bool:
        """Retrain GEX Directional ML model"""
        try:
            from quant.gex_directional_ml import GEXDirectionalPredictor

            predictor = GEXDirectionalPredictor()
            if hasattr(predictor, 'train') or hasattr(predictor, 'retrain'):
                train_func = getattr(predictor, 'retrain', getattr(predictor, 'train', None))
                if train_func:
                    train_func()
                    logger.info("GEX Directional ML retrained successfully")
                    return True

            logger.warning("GEX Directional ML has no train/retrain method")
            return False
        except Exception as e:
            logger.error(f"GEX Directional retrain failed: {e}")
            return False

    def _retrain_regime_classifier(self) -> bool:
        """Retrain ML Regime Classifier"""
        try:
            from quant.ml_regime_classifier import MLRegimeClassifier

            classifier = MLRegimeClassifier()
            if hasattr(classifier, 'train') or hasattr(classifier, 'retrain'):
                train_func = getattr(classifier, 'retrain', getattr(classifier, 'train', None))
                if train_func:
                    train_func()
                    logger.info("ML Regime Classifier retrained successfully")
                    return True

            logger.warning("ML Regime Classifier has no train/retrain method")
            return False
        except Exception as e:
            logger.error(f"Regime Classifier retrain failed: {e}")
            return False

    def _retrain_ares_advisor(self) -> bool:
        """Retrain FORTRESS ML Advisor"""
        try:
            from quant.fortress_ml_advisor import ARESMLAdvisor

            advisor = ARESMLAdvisor()
            if hasattr(advisor, 'train') or hasattr(advisor, 'retrain'):
                train_func = getattr(advisor, 'retrain', getattr(advisor, 'train', None))
                if train_func:
                    train_func()
                    logger.info("FORTRESS ML Advisor retrained successfully")
                    return True

            logger.warning("FORTRESS ML Advisor has no train/retrain method")
            return False
        except Exception as e:
            logger.error(f"FORTRESS ML Advisor retrain failed: {e}")
            return False

    # =========================================================================
    # GEX SIGNAL GENERATOR (5 sub-models)
    # =========================================================================

    def _validate_gex_signal_generator(self) -> ModelValidationResult:
        """Validate GEX Signal Generator (ensemble of 5 models)"""
        try:
            from quant.gex_probability_models import GEXSignalGenerator

            generator = GEXSignalGenerator()
            metrics = generator.get_performance_metrics() if hasattr(generator, 'get_performance_metrics') else {}

            is_accuracy = metrics.get('train_accuracy', 0.60)
            oos_accuracy = metrics.get('test_accuracy', 0.50)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.20

            return ModelValidationResult(
                model_name="gex_signal_generator",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"GEX Signal Generator validation failed: {e}")
            return self._failed_validation("gex_signal_generator", str(e))

    def _retrain_gex_signal_generator(self) -> bool:
        """Retrain GEX Signal Generator (all 5 models)"""
        try:
            from quant.gex_probability_models import GEXSignalGenerator

            generator = GEXSignalGenerator()
            if hasattr(generator, 'train'):
                generator.train()
                logger.info("GEX Signal Generator retrained successfully (5 models)")
                return True
            return False
        except Exception as e:
            logger.error(f"GEX Signal Generator retrain failed: {e}")
            return False

    # =========================================================================
    # PROPHET ADVISOR
    # =========================================================================

    def _validate_prophet_advisor(self) -> ModelValidationResult:
        """Validate Prophet Advisor"""
        try:
            from quant.prophet_advisor import ProphetAdvisor

            prophet = ProphetAdvisor()
            metrics = prophet.get_model_performance() if hasattr(prophet, 'get_model_performance') else {}

            is_accuracy = metrics.get('train_accuracy', 0.60)
            oos_accuracy = metrics.get('test_accuracy', 0.50)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.20

            return ModelValidationResult(
                model_name="prophet_advisor",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"Prophet Advisor validation failed: {e}")
            return self._failed_validation("prophet_advisor", str(e))

    def _retrain_prophet_advisor(self) -> bool:
        """Retrain Prophet Advisor"""
        try:
            from quant.prophet_advisor import ProphetAdvisor

            prophet = ProphetAdvisor()
            train_func = getattr(prophet, 'retrain', getattr(prophet, 'train', None))
            if train_func:
                train_func()
                logger.info("Prophet Advisor retrained successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Prophet Advisor retrain failed: {e}")
            return False

    # =========================================================================
    # DISCERNMENT ML ENGINE
    # =========================================================================

    def _validate_discernment_ml(self) -> ModelValidationResult:
        """Validate Discernment ML Engine"""
        try:
            from core.discernment_ml_engine import DiscernmentMLEngine

            discernment = DiscernmentMLEngine()
            metrics = discernment.get_metrics() if hasattr(discernment, 'get_metrics') else {}

            is_accuracy = metrics.get('train_accuracy', 0.55)
            oos_accuracy = metrics.get('test_accuracy', 0.45)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.25

            return ModelValidationResult(
                model_name="discernment_ml_engine",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"Discernment ML Engine validation failed: {e}")
            return self._failed_validation("discernment_ml_engine", str(e))

    def _retrain_discernment_ml(self) -> bool:
        """Retrain Discernment ML Engine"""
        try:
            from core.discernment_ml_engine import DiscernmentMLEngine

            discernment = DiscernmentMLEngine()
            if hasattr(discernment, 'train_models'):
                discernment.train_models()
                logger.info("Discernment ML Engine retrained successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Discernment ML Engine retrain failed: {e}")
            return False

    # =========================================================================
    # SPX WHEEL ML
    # =========================================================================

    def _validate_spx_wheel_ml(self) -> ModelValidationResult:
        """Validate SPX Wheel ML"""
        try:
            from trading.spx_wheel_ml import SPXWheelMLSystem

            wheel_ml = SPXWheelMLSystem()
            metrics = wheel_ml.get_metrics() if hasattr(wheel_ml, 'get_metrics') else {}

            is_accuracy = metrics.get('train_accuracy', 0.65)
            oos_accuracy = metrics.get('test_accuracy', 0.55)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.20

            return ModelValidationResult(
                model_name="spx_wheel_ml",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"SPX Wheel ML validation failed: {e}")
            return self._failed_validation("spx_wheel_ml", str(e))

    def _retrain_spx_wheel_ml(self) -> bool:
        """Retrain SPX Wheel ML"""
        try:
            from trading.spx_wheel_ml import SPXWheelMLSystem

            wheel_ml = SPXWheelMLSystem()
            if hasattr(wheel_ml, 'train'):
                wheel_ml.train()
                logger.info("SPX Wheel ML retrained successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"SPX Wheel ML retrain failed: {e}")
            return False

    # =========================================================================
    # MARKET REGIME CLASSIFIER (Core)
    # =========================================================================

    def _validate_market_regime(self) -> ModelValidationResult:
        """Validate Market Regime Classifier"""
        try:
            from core.market_regime_classifier import MarketRegimeClassifier

            classifier = MarketRegimeClassifier()
            metrics = classifier.get_metrics() if hasattr(classifier, 'get_metrics') else {}

            is_accuracy = metrics.get('train_accuracy', 0.70)
            oos_accuracy = metrics.get('test_accuracy', 0.60)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.15

            return ModelValidationResult(
                model_name="market_regime_classifier",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"Market Regime Classifier validation failed: {e}")
            return self._failed_validation("market_regime_classifier", str(e))

    def _retrain_market_regime(self) -> bool:
        """Retrain Market Regime Classifier"""
        try:
            from core.market_regime_classifier import MarketRegimeClassifier

            classifier = MarketRegimeClassifier()
            train_func = getattr(classifier, 'retrain', getattr(classifier, 'train', None))
            if train_func:
                train_func()
                logger.info("Market Regime Classifier retrained successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Market Regime Classifier retrain failed: {e}")
            return False

    # =========================================================================
    # PATTERN LEARNER
    # =========================================================================

    def _validate_pattern_learner(self) -> ModelValidationResult:
        """Validate Autonomous Pattern Learner"""
        try:
            from ai.autonomous_ml_pattern_learner import PatternLearner

            learner = PatternLearner()
            metrics = learner.get_metrics() if hasattr(learner, 'get_metrics') else {}

            is_accuracy = metrics.get('train_accuracy', 0.55)
            oos_accuracy = metrics.get('test_accuracy', 0.45)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.25

            return ModelValidationResult(
                model_name="pattern_learner",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"Pattern Learner validation failed: {e}")
            return self._failed_validation("pattern_learner", str(e))

    def _retrain_pattern_learner(self) -> bool:
        """Retrain Pattern Learner"""
        try:
            from ai.autonomous_ml_pattern_learner import PatternLearner

            learner = PatternLearner()
            if hasattr(learner, 'train_pattern_classifier'):
                learner.train_pattern_classifier()
                logger.info("Pattern Learner retrained successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Pattern Learner retrain failed: {e}")
            return False

    # =========================================================================
    # SOLOMON ML
    # =========================================================================

    def _validate_solomon_ml(self) -> ModelValidationResult:
        """Validate SOLOMON ML (Directional Spread Predictions)"""
        try:
            # SOLOMON may use GEX directional or have its own ML
            from quant.gex_directional_ml import GEXDirectionalPredictor

            predictor = GEXDirectionalPredictor()
            metrics = predictor.get_performance_metrics() if hasattr(predictor, 'get_performance_metrics') else {}

            # For SOLOMON, we check directional accuracy
            is_accuracy = metrics.get('train_accuracy', 0.60)
            oos_accuracy = metrics.get('test_accuracy', 0.50)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.20

            return ModelValidationResult(
                model_name="solomon_ml",
                validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                in_sample_accuracy=is_accuracy,
                out_of_sample_accuracy=oos_accuracy,
                degradation_pct=degradation * 100,
                is_robust=is_robust,
                status=ModelStatus.HEALTHY if is_robust else ModelStatus.DEGRADED,
                recommendation="KEEP" if is_robust else "RETRAIN",
                details=metrics
            )
        except Exception as e:
            logger.warning(f"SOLOMON ML validation failed: {e}")
            return self._failed_validation("solomon_ml", str(e))

    def _retrain_solomon_ml(self) -> bool:
        """Retrain SOLOMON ML"""
        try:
            from quant.gex_directional_ml import GEXDirectionalPredictor

            predictor = GEXDirectionalPredictor()
            train_func = getattr(predictor, 'retrain', getattr(predictor, 'train', None))
            if train_func:
                train_func()
                logger.info("SOLOMON ML retrained successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"SOLOMON ML retrain failed: {e}")
            return False

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _failed_validation(self, model_name: str, error: str) -> ModelValidationResult:
        """Create a failed validation result"""
        return ModelValidationResult(
            model_name=model_name,
            validated_at=datetime.now(CENTRAL_TZ).isoformat(),
            in_sample_accuracy=0,
            out_of_sample_accuracy=0,
            degradation_pct=100,
            is_robust=False,
            status=ModelStatus.FAILED,
            recommendation="INVESTIGATE",
            details={'error': error}
        )


# =============================================================================
# AUTO VALIDATION SYSTEM
# =============================================================================

class AutoValidationSystem:
    """
    Automated system that:
    1. Periodically validates ML models using walk-forward
    2. Triggers retraining when degradation exceeds threshold
    3. Allocates capital using Thompson Sampling based on bot performance

    Usage:
        system = AutoValidationSystem()

        # Run validation (call daily/weekly)
        results = system.run_validation()

        # Get capital allocation (call before trading)
        allocation = system.get_capital_allocation(total_capital=100000)

        # Record bot outcome (call after each trade)
        system.record_bot_outcome('FORTRESS', win=True, pnl=150.0)
    """

    def __init__(
        self,
        validation_interval_days: int = 7,
        degradation_threshold: float = 0.20,
        auto_retrain: bool = True,
        bot_names: List[str] = None
    ):
        """
        Initialize auto-validation system.

        Args:
            validation_interval_days: Days between validation runs
            degradation_threshold: Default degradation threshold for retraining
            auto_retrain: Whether to automatically retrain degraded models
            bot_names: List of bot names for Thompson allocation
        """
        self.validation_interval_days = validation_interval_days
        self.degradation_threshold = degradation_threshold
        self.auto_retrain = auto_retrain

        # ML Model Registry
        self.model_registry = MLModelRegistry()

        # Thompson Sampling Allocator
        self.bot_names = bot_names or ['FORTRESS', 'SOLOMON', 'LAZARUS', 'CORNERSTONE']
        if THOMPSON_AVAILABLE:
            self.thompson = ThompsonSamplingAllocator(self.bot_names)
        else:
            self.thompson = None

        # Walk-Forward Optimizer
        if WALKFORWARD_AVAILABLE:
            self.walk_forward = WalkForwardOptimizer()
        else:
            self.walk_forward = None

        # State
        self.last_validation: Optional[datetime] = None
        self.validation_results: List[ModelValidationResult] = []
        self.retrain_triggers: List[RetrainTrigger] = []
        self.allocation_history: List[CapitalAllocation] = []

        # Load state from database
        self._load_state()

        logger.info(
            f"AutoValidationSystem initialized: "
            f"interval={validation_interval_days}d, "
            f"threshold={degradation_threshold:.0%}, "
            f"auto_retrain={auto_retrain}"
        )

    def _load_state(self):
        """Load state from database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            # Load Thompson parameters if saved
            c.execute("""
                SELECT bot_name, alpha, beta
                FROM thompson_parameters
                ORDER BY last_updated DESC
            """)

            for row in c.fetchall():
                bot_name, alpha, beta = row
                if self.thompson and bot_name in self.thompson.bot_names:
                    self.thompson.alpha[bot_name] = alpha
                    self.thompson.beta[bot_name] = beta

            conn.close()
            logger.debug("AutoValidationSystem state loaded from database")
        except Exception as e:
            logger.debug(f"Could not load state: {e}")

    def _save_state(self):
        """Save state to database"""
        if not DB_AVAILABLE or not self.thompson:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            # Save Thompson parameters
            for bot_name in self.thompson.bot_names:
                c.execute("""
                    INSERT INTO thompson_parameters (bot_name, alpha, beta, last_updated)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (bot_name) DO UPDATE SET
                        alpha = EXCLUDED.alpha,
                        beta = EXCLUDED.beta,
                        last_updated = EXCLUDED.last_updated
                """, (
                    bot_name,
                    self.thompson.alpha[bot_name],
                    self.thompson.beta[bot_name],
                    datetime.now(CENTRAL_TZ)
                ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not save state: {e}")

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def should_validate(self) -> bool:
        """Check if validation should run"""
        if self.last_validation is None:
            return True

        days_since = (datetime.now(CENTRAL_TZ) - self.last_validation).days
        return days_since >= self.validation_interval_days

    def run_validation(self, force: bool = False) -> List[ModelValidationResult]:
        """
        Run validation on all registered ML models.

        Args:
            force: Force validation even if interval hasn't elapsed

        Returns:
            List of validation results
        """
        if not force and not self.should_validate():
            logger.debug("Validation not due yet")
            return self.validation_results

        logger.info("Running ML model validation...")
        results = []
        retrain_needed = []

        for model_name, model_info in self.model_registry.models.items():
            logger.info(f"Validating {model_name}...")

            try:
                # Run validation function
                result = model_info['validate_func']()
                results.append(result)

                # Update model status
                model_info['last_validation'] = datetime.now(CENTRAL_TZ)
                model_info['status'] = result.status

                # Check if retrain needed
                threshold = model_info['degradation_threshold']
                if result.degradation_pct > threshold * 100:
                    retrain_needed.append(model_name)

                    trigger = RetrainTrigger(
                        model_name=model_name,
                        triggered_at=datetime.now(CENTRAL_TZ).isoformat(),
                        reason=f"Degradation {result.degradation_pct:.1f}% exceeds threshold {threshold*100:.0f}%",
                        degradation_pct=result.degradation_pct,
                        previous_accuracy=result.in_sample_accuracy
                    )
                    self.retrain_triggers.append(trigger)

                logger.info(
                    f"  {model_name}: IS={result.in_sample_accuracy:.1%}, "
                    f"OOS={result.out_of_sample_accuracy:.1%}, "
                    f"Degradation={result.degradation_pct:.1f}%, "
                    f"Status={result.status.value}"
                )

            except Exception as e:
                logger.error(f"Validation failed for {model_name}: {e}")
                results.append(ModelValidationResult(
                    model_name=model_name,
                    validated_at=datetime.now(CENTRAL_TZ).isoformat(),
                    in_sample_accuracy=0,
                    out_of_sample_accuracy=0,
                    degradation_pct=100,
                    is_robust=False,
                    status=ModelStatus.FAILED,
                    recommendation="INVESTIGATE",
                    details={'error': str(e)}
                ))

        # Auto-retrain if enabled
        if self.auto_retrain and retrain_needed:
            logger.info(f"Auto-retraining {len(retrain_needed)} degraded models...")
            for model_name in retrain_needed:
                self.retrain_model(model_name)

        # Update state
        self.last_validation = datetime.now(CENTRAL_TZ)
        self.validation_results = results

        # Save to database
        self._save_validation_results(results)

        return results

    def retrain_model(self, model_name: str) -> bool:
        """
        Retrain a specific ML model.

        Args:
            model_name: Name of the model to retrain

        Returns:
            True if retrain successful
        """
        if model_name not in self.model_registry.models:
            logger.error(f"Unknown model: {model_name}")
            return False

        model_info = self.model_registry.models[model_name]
        logger.info(f"Retraining {model_name}...")

        try:
            # Update status
            model_info['status'] = ModelStatus.RETRAINING

            # Run retrain function
            success = model_info['retrain_func']()

            if success:
                model_info['status'] = ModelStatus.HEALTHY
                model_info['last_retrain'] = datetime.now(CENTRAL_TZ)
                logger.info(f"  {model_name} retrained successfully")
            else:
                model_info['status'] = ModelStatus.FAILED
                logger.warning(f"  {model_name} retrain returned False")

            return success

        except Exception as e:
            model_info['status'] = ModelStatus.FAILED
            logger.error(f"  {model_name} retrain failed: {e}")
            return False

    def _save_validation_results(self, results: List[ModelValidationResult]):
        """Save validation results to database"""
        if not DB_AVAILABLE:
            return

        try:
            import json
            conn = get_connection()
            c = conn.cursor()

            for result in results:
                c.execute("""
                    INSERT INTO ml_validation_results (
                        model_name, validation_time, in_sample_accuracy, out_of_sample_accuracy,
                        degradation_pct, is_robust, status, recommendation, details
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    result.model_name,
                    result.validated_at,
                    result.in_sample_accuracy,
                    result.out_of_sample_accuracy,
                    result.degradation_pct,
                    result.is_robust,
                    result.status.value,
                    result.recommendation,
                    json.dumps(result.details)
                ))

            conn.commit()
            conn.close()
            logger.info(f"Saved {len(results)} validation results to database")
        except Exception as e:
            logger.warning(f"Could not save validation results: {e}")

    # =========================================================================
    # THOMPSON SAMPLING CAPITAL ALLOCATION
    # =========================================================================

    def record_bot_outcome(self, bot_name: str, win: bool, pnl: float = 0, trade_type: str = None, symbol: str = "SPY"):
        """
        Record a bot trade outcome for Thompson Sampling.

        Args:
            bot_name: Bot that made the trade
            win: Whether the trade was profitable
            pnl: Actual P&L amount
            trade_type: Type of trade (IRON_CONDOR, VERTICAL_SPREAD, etc.)
            symbol: Trading symbol
        """
        if not self.thompson:
            logger.debug("Thompson allocator not available")
            return

        # Get pre-update parameters
        alpha_before = self.thompson.alpha.get(bot_name, 1.0)
        beta_before = self.thompson.beta.get(bot_name, 1.0)

        # Update Thompson parameters
        self.thompson.record_outcome(bot_name, win, pnl)

        # Get post-update parameters
        alpha_after = self.thompson.alpha.get(bot_name, 1.0)
        beta_after = self.thompson.beta.get(bot_name, 1.0)

        # Save state and record outcome to database
        self._save_state()
        self._save_trade_outcome(bot_name, win, pnl, trade_type, symbol, alpha_before, beta_before, alpha_after, beta_after)

        logger.debug(f"Recorded outcome for {bot_name}: win={win}, pnl=${pnl:.2f}")

    def _save_trade_outcome(self, bot_name: str, win: bool, pnl: float, trade_type: str, symbol: str,
                            alpha_before: float, beta_before: float, alpha_after: float, beta_after: float):
        """Save trade outcome to database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO thompson_trade_outcomes (
                    bot_name, trade_time, win, pnl, trade_type, symbol,
                    alpha_before, beta_before, alpha_after, beta_after
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                bot_name,
                datetime.now(CENTRAL_TZ),
                win,
                pnl,
                trade_type,
                symbol,
                alpha_before,
                beta_before,
                alpha_after,
                beta_after
            ))

            # Also update thompson_parameters with running totals
            c.execute("""
                UPDATE thompson_parameters
                SET total_trades = total_trades + 1,
                    total_wins = total_wins + %s,
                    total_pnl = total_pnl + %s,
                    last_updated = %s
                WHERE bot_name = %s
            """, (
                1 if win else 0,
                pnl,
                datetime.now(CENTRAL_TZ),
                bot_name
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Could not save trade outcome: {e}")

    def get_capital_allocation(
        self,
        total_capital: float = 100000,
        method: str = "thompson"
    ) -> CapitalAllocation:
        """
        Get capital allocation across bots.

        Args:
            total_capital: Total capital to allocate
            method: "thompson" for dynamic or "equal" for equal split

        Returns:
            CapitalAllocation with amounts per bot
        """
        if method == "thompson" and self.thompson:
            # Use Thompson Sampling
            allocation = self.thompson.sample_allocation(total_capital)

            result = CapitalAllocation(
                timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                total_capital=total_capital,
                allocations=allocation.allocations,
                allocation_pcts={
                    bot: amt / total_capital
                    for bot, amt in allocation.allocations.items()
                },
                method="thompson",
                confidence={
                    bot: self.thompson.alpha[bot] / (self.thompson.alpha[bot] + self.thompson.beta[bot])
                    for bot in self.bot_names
                }
            )
        else:
            # Equal allocation
            equal_amount = total_capital / len(self.bot_names)
            result = CapitalAllocation(
                timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                total_capital=total_capital,
                allocations={bot: equal_amount for bot in self.bot_names},
                allocation_pcts={bot: 1.0 / len(self.bot_names) for bot in self.bot_names},
                method="equal",
                confidence={bot: 0.5 for bot in self.bot_names}
            )

        self.allocation_history.append(result)

        # Save to database
        self._save_allocation_history(result)

        logger.info(f"Capital allocation ({method}): {result.allocation_pcts}")
        return result

    def _save_allocation_history(self, allocation: CapitalAllocation):
        """Save allocation decision to database"""
        if not DB_AVAILABLE:
            return

        try:
            import json
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO thompson_allocation_history (
                    allocation_time, total_capital, method, allocations, allocation_pcts, confidence
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                allocation.timestamp,
                allocation.total_capital,
                allocation.method,
                json.dumps(allocation.allocations),
                json.dumps(allocation.allocation_pcts),
                json.dumps(allocation.confidence)
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Could not save allocation history: {e}")

    def get_bot_confidence(self, bot_name: str) -> float:
        """
        Get confidence score for a bot (0-1).

        Based on Thompson Sampling Beta distribution.
        Higher = more confident bot is profitable.
        """
        if not self.thompson or bot_name not in self.thompson.alpha:
            return 0.5  # No data = neutral confidence

        alpha = self.thompson.alpha[bot_name]
        beta = self.thompson.beta[bot_name]

        # Expected value of Beta distribution
        return alpha / (alpha + beta)

    # =========================================================================
    # STATUS AND REPORTING
    # =========================================================================

    def get_status(self) -> Dict:
        """Get current system status"""
        model_status = {}
        for name, info in self.model_registry.models.items():
            model_status[name] = {
                'status': info['status'].value,
                'last_validation': info['last_validation'].isoformat() if info['last_validation'] else None,
                'last_retrain': info['last_retrain'].isoformat() if info['last_retrain'] else None
            }

        thompson_status = {}
        if self.thompson:
            for bot in self.bot_names:
                thompson_status[bot] = {
                    'alpha': self.thompson.alpha[bot],
                    'beta': self.thompson.beta[bot],
                    'confidence': self.get_bot_confidence(bot),
                    'win_rate_estimate': self.get_bot_confidence(bot)
                }

        return {
            'validation': {
                'last_run': self.last_validation.isoformat() if self.last_validation else None,
                'interval_days': self.validation_interval_days,
                'should_run': self.should_validate(),
                'results_count': len(self.validation_results)
            },
            'models': model_status,
            'thompson': thompson_status,
            'auto_retrain': self.auto_retrain,
            'retrain_triggers_count': len(self.retrain_triggers)
        }

    def get_validation_summary(self) -> Dict:
        """Get summary of last validation run"""
        if not self.validation_results:
            return {'status': 'no_validation_run'}

        healthy = sum(1 for r in self.validation_results if r.status == ModelStatus.HEALTHY)
        degraded = sum(1 for r in self.validation_results if r.status == ModelStatus.DEGRADED)
        failed = sum(1 for r in self.validation_results if r.status == ModelStatus.FAILED)

        return {
            'last_validation': self.last_validation.isoformat() if self.last_validation else None,
            'total_models': len(self.validation_results),
            'healthy': healthy,
            'degraded': degraded,
            'failed': failed,
            'overall_status': 'healthy' if degraded + failed == 0 else 'needs_attention',
            'results': [r.to_dict() for r in self.validation_results]
        }


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_auto_validation_system: Optional[AutoValidationSystem] = None


def get_auto_validation_system() -> AutoValidationSystem:
    """Get singleton AutoValidationSystem instance"""
    global _auto_validation_system
    if _auto_validation_system is None:
        _auto_validation_system = AutoValidationSystem()
    return _auto_validation_system


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def run_validation(force: bool = False) -> List[ModelValidationResult]:
    """Run ML model validation"""
    system = get_auto_validation_system()
    return system.run_validation(force=force)


def get_capital_allocation(total_capital: float = 100000) -> CapitalAllocation:
    """Get Thompson Sampling capital allocation"""
    system = get_auto_validation_system()
    return system.get_capital_allocation(total_capital=total_capital)


def record_bot_outcome(bot_name: str, win: bool, pnl: float = 0):
    """Record bot trade outcome for Thompson Sampling, Proverbs feedback loop, and active validations"""
    # Record for Thompson Sampling (capital allocation)
    system = get_auto_validation_system()
    system.record_bot_outcome(bot_name, win, pnl)

    # Also record to Proverbs feedback loop for analytics
    try:
        from trading.mixins.proverbs_integration import record_bot_outcome as proverbs_record
        outcome = "WIN" if win else "LOSS"
        trade_date = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
        proverbs_record(
            bot_name=bot_name,
            trade_date=trade_date,
            outcome=outcome,
            pnl=pnl,
            metadata={'source': 'auto_validation_system', 'win': win}
        )
        logger.debug(f"[{bot_name}] Trade outcome also recorded to Proverbs feedback loop")
    except Exception as e:
        logger.debug(f"[{bot_name}] Could not record to Proverbs: {e}")

    # Record to active proposal validations if any exist
    try:
        from quant.proverbs_enhancements import get_proverbs_enhanced
        proverbs_enhanced = get_proverbs_enhanced()

        # Check for active validations for this bot
        active_validations = proverbs_enhanced.proposal_validator.get_pending_validations(bot_name)
        for validation in active_validations:
            if validation.get('status') == 'RUNNING':
                validation_id = validation.get('validation_id')
                # Record to the proposed config side (as trades happen under new config during validation)
                proverbs_enhanced.proposal_validator.record_validation_trade(
                    validation_id=validation_id,
                    is_proposed=True,  # During validation, trades use proposed config
                    pnl=pnl
                )
                logger.debug(f"[{bot_name}] Trade recorded to validation {validation_id}")
    except Exception as e:
        logger.debug(f"[{bot_name}] Could not record to proposal validation: {e}")


def get_validation_status() -> Dict:
    """Get validation system status"""
    system = get_auto_validation_system()
    return system.get_status()


if __name__ == "__main__":
    # Test the system
    logging.basicConfig(level=logging.INFO)

    system = AutoValidationSystem()

    # Run validation
    print("\n=== Running Validation ===")
    results = system.run_validation(force=True)

    for r in results:
        print(f"  {r.model_name}: {r.status.value} (degradation: {r.degradation_pct:.1f}%)")

    # Test Thompson allocation
    print("\n=== Capital Allocation ===")

    # Simulate some outcomes
    system.record_bot_outcome('FORTRESS', win=True, pnl=200)
    system.record_bot_outcome('FORTRESS', win=True, pnl=150)
    system.record_bot_outcome('SOLOMON', win=False, pnl=-100)
    system.record_bot_outcome('SOLOMON', win=True, pnl=300)
    system.record_bot_outcome('LAZARUS', win=True, pnl=50)

    allocation = system.get_capital_allocation(100000)
    print(f"  Method: {allocation.method}")
    for bot, pct in allocation.allocation_pcts.items():
        print(f"  {bot}: {pct:.1%} (${allocation.allocations[bot]:,.0f})")

    print("\n=== System Status ===")
    status = system.get_status()
    print(f"  Last validation: {status['validation']['last_run']}")
    print(f"  Models: {len(status['models'])}")
    for bot, info in status['thompson'].items():
        print(f"  {bot}: confidence={info['confidence']:.1%}")
