"""
AlphaGEX Quant Module - Production-Grade Enhancements

This module contains four key improvements:
1. ML Regime Classifier - Replaces hard-coded GEX thresholds with trained models
2. Walk-Forward Optimizer - Automated train/test validation to prevent overfitting
3. Ensemble Strategy Weighting - Probabilistic blending of multiple strategies
4. Monte Carlo Position Sizing - Stress testing for Kelly criterion

Author: AlphaGEX Quant Team
Date: 2025-12-03
"""

# Check for required dependencies
_DEPENDENCIES_AVAILABLE = True
_MISSING_DEPS = []

try:
    import numpy as np
except ImportError:
    _DEPENDENCIES_AVAILABLE = False
    _MISSING_DEPS.append('numpy')

try:
    import pandas as pd
except ImportError:
    _DEPENDENCIES_AVAILABLE = False
    _MISSING_DEPS.append('pandas')

try:
    from scipy import stats
except ImportError:
    _DEPENDENCIES_AVAILABLE = False
    _MISSING_DEPS.append('scipy')

# Only import if dependencies are available
if _DEPENDENCIES_AVAILABLE:
    from .ml_regime_classifier import (
        MLRegimeClassifier,
        train_regime_classifier,
        get_ml_regime_prediction,
    )

    from .walk_forward_optimizer import (
        WalkForwardOptimizer,
        WalkForwardResult,
        run_walk_forward_validation,
    )

    from .ensemble_strategy import (
        EnsembleStrategyWeighter,
        get_ensemble_signal,
        EnsembleSignal,
    )

    from .monte_carlo_kelly import (
        MonteCarloKelly,
        KellyStressTest,
        get_safe_position_size,
    )

    from .integration import (
        QuantEnhancedTrader,
        get_quant_recommendation,
        validate_and_size_trade,
        QuantRecommendation,
    )

    __all__ = [
        # ML Regime
        'MLRegimeClassifier',
        'train_regime_classifier',
        'get_ml_regime_prediction',
        # Walk-Forward
        'WalkForwardOptimizer',
        'WalkForwardResult',
        'run_walk_forward_validation',
        # Ensemble
        'EnsembleStrategyWeighter',
        'get_ensemble_signal',
        'EnsembleSignal',
        # Monte Carlo
        'MonteCarloKelly',
        'KellyStressTest',
        'get_safe_position_size',
        # Integration
        'QuantEnhancedTrader',
        'get_quant_recommendation',
        'validate_and_size_trade',
        'QuantRecommendation',
    ]
else:
    # Provide helpful error message
    print(f"Warning: Quant module requires: {', '.join(_MISSING_DEPS)}")
    print("Install with: pip install numpy pandas scipy scikit-learn")

    __all__ = []

    # Stub classes that raise helpful errors
    class _MissingDependencyError:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                f"Quant module requires: {', '.join(_MISSING_DEPS)}. "
                "Install with: pip install numpy pandas scipy scikit-learn"
            )

    MLRegimeClassifier = _MissingDependencyError
    WalkForwardOptimizer = _MissingDependencyError
    EnsembleStrategyWeighter = _MissingDependencyError
    MonteCarloKelly = _MissingDependencyError
    QuantEnhancedTrader = _MissingDependencyError

    def train_regime_classifier(*args, **kwargs):
        raise ImportError(f"Quant module requires: {', '.join(_MISSING_DEPS)}")

    def get_ml_regime_prediction(*args, **kwargs):
        raise ImportError(f"Quant module requires: {', '.join(_MISSING_DEPS)}")

    def get_ensemble_signal(*args, **kwargs):
        raise ImportError(f"Quant module requires: {', '.join(_MISSING_DEPS)}")

    def get_safe_position_size(*args, **kwargs):
        raise ImportError(f"Quant module requires: {', '.join(_MISSING_DEPS)}")

    def get_quant_recommendation(*args, **kwargs):
        raise ImportError(f"Quant module requires: {', '.join(_MISSING_DEPS)}")

    def validate_and_size_trade(*args, **kwargs):
        raise ImportError(f"Quant module requires: {', '.join(_MISSING_DEPS)}")
