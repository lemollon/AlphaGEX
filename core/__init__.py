"""Core trading components for AlphaGEX trading system.

NOTE: This module uses lazy imports to prevent import chain failures
when heavy dependencies (pandas, numpy) are not available.
Individual modules like vix_hedge_manager can be imported directly
without loading the entire core package.
"""

# Lazy imports to prevent import chain failures
# Only load these when explicitly accessed
_lazy_imports = {
    'AutonomousPaperTrader': 'core.autonomous_paper_trader',
    'MarketRegimeClassifier': 'core.market_regime_classifier',
    'get_classifier': 'core.market_regime_classifier',
    'RegimeClassification': 'core.market_regime_classifier',
    'MarketAction': 'core.market_regime_classifier',
    'get_strategy_stats': 'core.strategy_stats',
    'update_strategy_stats': 'core.strategy_stats',
    'analyze_current_market_complete': 'core.psychology_trap_detector',
}

__all__ = list(_lazy_imports.keys())


def __getattr__(name):
    """Lazy import handler - only import when attribute is accessed."""
    if name in _lazy_imports:
        import importlib
        module_path = _lazy_imports[name]
        try:
            module = importlib.import_module(module_path)
            return getattr(module, name)
        except ImportError as e:
            # Return None instead of raising - allows partial functionality
            import warnings
            warnings.warn(f"Could not import {name} from {module_path}: {e}")
            return None
    raise AttributeError(f"module 'core' has no attribute '{name}'")
