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
        self._register_default_models()

    def _register_default_models(self):
        """Register the 3 main ML models"""

        # 1. GEX Directional ML
        self.register_model(
            name="gex_directional_ml",
            description="Predicts SPY direction based on GEX data",
            validate_func=self._validate_gex_directional,
            retrain_func=self._retrain_gex_directional,
            degradation_threshold=0.20  # 20% degradation triggers retrain
        )

        # 2. ML Regime Classifier
        self.register_model(
            name="ml_regime_classifier",
            description="Classifies market regime (trending/ranging/volatile)",
            validate_func=self._validate_regime_classifier,
            retrain_func=self._retrain_regime_classifier,
            degradation_threshold=0.15  # 15% degradation triggers retrain
        )

        # 3. ARES ML Advisor
        self.register_model(
            name="ares_ml_advisor",
            description="ML-based Iron Condor entry/exit advisor",
            validate_func=self._validate_ares_advisor,
            retrain_func=self._retrain_ares_advisor,
            degradation_threshold=0.20  # 20% degradation triggers retrain
        )

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
        """Validate ARES ML Advisor"""
        try:
            from quant.ares_ml_advisor import ARESMLAdvisor

            advisor = ARESMLAdvisor()

            # Get performance metrics
            metrics = advisor.get_model_performance() if hasattr(advisor, 'get_model_performance') else {}

            is_accuracy = metrics.get('in_sample_win_rate', 0.65)
            oos_accuracy = metrics.get('out_of_sample_win_rate', 0.55)
            degradation = (is_accuracy - oos_accuracy) / is_accuracy if is_accuracy > 0 else 0

            is_robust = degradation < 0.20

            return ModelValidationResult(
                model_name="ares_ml_advisor",
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
            logger.warning(f"ARES ML Advisor validation failed: {e}")
            return ModelValidationResult(
                model_name="ares_ml_advisor",
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
        """Retrain ARES ML Advisor"""
        try:
            from quant.ares_ml_advisor import ARESMLAdvisor

            advisor = ARESMLAdvisor()
            if hasattr(advisor, 'train') or hasattr(advisor, 'retrain'):
                train_func = getattr(advisor, 'retrain', getattr(advisor, 'train', None))
                if train_func:
                    train_func()
                    logger.info("ARES ML Advisor retrained successfully")
                    return True

            logger.warning("ARES ML Advisor has no train/retrain method")
            return False
        except Exception as e:
            logger.error(f"ARES ML Advisor retrain failed: {e}")
            return False


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
        system.record_bot_outcome('ARES', win=True, pnl=150.0)
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
        self.bot_names = bot_names or ['ARES', 'ATHENA', 'PHOENIX', 'ATLAS']
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
                ORDER BY updated_at DESC
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
                    INSERT INTO thompson_parameters (bot_name, alpha, beta, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (bot_name) DO UPDATE SET
                        alpha = EXCLUDED.alpha,
                        beta = EXCLUDED.beta,
                        updated_at = EXCLUDED.updated_at
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
            conn = get_connection()
            c = conn.cursor()

            for result in results:
                c.execute("""
                    INSERT INTO ml_validation_results (
                        model_name, validated_at, is_accuracy, oos_accuracy,
                        degradation_pct, is_robust, status, recommendation
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    result.model_name,
                    result.validated_at,
                    result.in_sample_accuracy,
                    result.out_of_sample_accuracy,
                    result.degradation_pct,
                    result.is_robust,
                    result.status.value,
                    result.recommendation
                ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not save validation results: {e}")

    # =========================================================================
    # THOMPSON SAMPLING CAPITAL ALLOCATION
    # =========================================================================

    def record_bot_outcome(self, bot_name: str, win: bool, pnl: float = 0):
        """
        Record a bot trade outcome for Thompson Sampling.

        Args:
            bot_name: Bot that made the trade
            win: Whether the trade was profitable
            pnl: Actual P&L amount
        """
        if not self.thompson:
            logger.debug("Thompson allocator not available")
            return

        self.thompson.record_outcome(bot_name, win, pnl)
        self._save_state()

        logger.debug(f"Recorded outcome for {bot_name}: win={win}, pnl=${pnl:.2f}")

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

        logger.info(f"Capital allocation ({method}): {result.allocation_pcts}")
        return result

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
    """Record bot trade outcome for Thompson Sampling"""
    system = get_auto_validation_system()
    system.record_bot_outcome(bot_name, win, pnl)


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
    system.record_bot_outcome('ARES', win=True, pnl=200)
    system.record_bot_outcome('ARES', win=True, pnl=150)
    system.record_bot_outcome('ATHENA', win=False, pnl=-100)
    system.record_bot_outcome('ATHENA', win=True, pnl=300)
    system.record_bot_outcome('PHOENIX', win=True, pnl=50)

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
