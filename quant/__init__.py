"""
AlphaGEX Quant Module - Production-Grade Enhancements

This module contains key improvements:
1. Walk-Forward Optimizer - Automated train/test validation to prevent overfitting
2. Monte Carlo Position Sizing - Stress testing for Kelly criterion
3. Oracle Advisor - Primary decision maker for all bots
4. GEX Probability Models (ORION) - ML predictions for ARGUS/HYPERION

Note: ML Regime Classifier and Ensemble Strategy were removed in January 2025.
Oracle is now the sole decision authority for all trading bots.

Author: AlphaGEX Quant Team
Date: 2025-12-03 (Updated: 2026-01)
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

# Track what's available
__all__ = []

# Only import if dependencies are available
if _DEPENDENCIES_AVAILABLE:
    # Walk-Forward Optimizer (still active)
    try:
        from .walk_forward_optimizer import (
            WalkForwardOptimizer,
            WalkForwardResult,
            run_walk_forward_validation,
        )
        __all__.extend([
            'WalkForwardOptimizer',
            'WalkForwardResult',
            'run_walk_forward_validation',
        ])
    except ImportError:
        pass

    # Monte Carlo Kelly (still active)
    try:
        from .monte_carlo_kelly import (
            MonteCarloKelly,
            KellyStressTest,
            get_safe_position_size,
        )
        __all__.extend([
            'MonteCarloKelly',
            'KellyStressTest',
            'get_safe_position_size',
        ])
    except ImportError:
        pass

    # Integration module (still active)
    try:
        from .integration import (
            QuantEnhancedTrader,
            get_quant_recommendation,
            validate_and_size_trade,
            QuantRecommendation,
        )
        __all__.extend([
            'QuantEnhancedTrader',
            'get_quant_recommendation',
            'validate_and_size_trade',
            'QuantRecommendation',
        ])
    except ImportError:
        pass

    # GEX Probability Models / ORION (active)
    try:
        from .gex_probability_models import (
            GEXProbabilityModels,
            GEXSignalGenerator,
        )
        __all__.extend([
            'GEXProbabilityModels',
            'GEXSignalGenerator',
        ])
    except ImportError:
        pass

    # Oracle Advisor (primary decision maker)
    try:
        from .oracle_advisor import OracleAdvisor
        __all__.append('OracleAdvisor')
    except ImportError:
        pass

    # REMOVED modules (January 2025):
    # - ml_regime_classifier: Oracle handles regime decisions
    # - ensemble_strategy: Oracle is sole authority

else:
    # Provide helpful error message
    print(f"Warning: Quant module requires: {', '.join(_MISSING_DEPS)}")
    print("Install with: pip install numpy pandas scipy scikit-learn")
