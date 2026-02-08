"""
OMEGA Integration Mixin for Trading Bots
=========================================

This mixin provides OMEGA Orchestrator integration for all trading bots.
It replaces direct calls to Oracle, ML Advisor, and CircuitBreaker with
the unified OMEGA decision flow.

USAGE:
    class MyTradingBot(OmegaIntegrationMixin, BaseTradingBot):
        def execute_trade(self):
            # Use OMEGA for trading decisions
            decision = self.omega_get_trading_decision(
                gex_data=self.get_gex_data(),
                features=self.build_ml_features()
            )

            if decision.final_decision in [TradingDecision.TRADE_FULL, TradingDecision.TRADE_REDUCED]:
                # Execute trade with OMEGA-provided parameters
                self.open_position(
                    risk_pct=decision.final_risk_pct,
                    size_multiplier=decision.final_position_size_multiplier,
                    put_strike=decision.oracle_adaptation.suggested_put_strike,
                    call_strike=decision.oracle_adaptation.suggested_call_strike
                )

MIGRATION FROM OLD SYSTEM:
    OLD:
        if self.circuit_breaker.can_trade():
            advice = oracle.get_ares_advice(context)
            if advice.advice != TradingAdvice.SKIP_TODAY:
                self.execute_trade(advice)

    NEW:
        decision = self.omega_get_trading_decision(gex_data, features)
        if decision.final_decision in [TradingDecision.TRADE_FULL, TradingDecision.TRADE_REDUCED]:
            self.execute_trade_with_omega(decision)

Author: AlphaGEX Quant Team
Date: January 2025
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from zoneinfo import ZoneInfo

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class OmegaIntegrationMixin:
    """
    Mixin that provides OMEGA Orchestrator integration for trading bots.

    Attributes expected on the class:
        - bot_name: str (e.g., 'ARES', 'ATHENA')
        - capital: float (current capital)

    This mixin replaces:
        - CircuitBreaker checks (now handled by Proverbs layer in OMEGA)
        - Direct Oracle calls (now routed through OMEGA's layered decision)
        - ML Advisor calls (now the PRIMARY decision in OMEGA)
    """

    # Cache the OMEGA instance
    _omega_instance = None

    def _get_omega(self):
        """Get or create OMEGA Orchestrator instance"""
        if self._omega_instance is None:
            try:
                from core.omega_orchestrator import get_omega_orchestrator
                capital = getattr(self, 'capital', 100000)
                self._omega_instance = get_omega_orchestrator(capital)
            except ImportError as e:
                logger.error(f"Failed to import OMEGA Orchestrator: {e}")
                return None
        return self._omega_instance

    def omega_get_trading_decision(
        self,
        gex_data: Dict,
        features: Dict,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None,
        current_regime: str = "UNKNOWN"
    ) -> Optional[Any]:
        """
        Get trading decision from OMEGA Orchestrator.

        This is the main entry point for all trading decisions.
        It replaces direct calls to:
            - circuit_breaker.can_trade()
            - oracle.get_ares_advice()
            - ml_advisor.predict()

        Args:
            gex_data: GEX analysis data
            features: ML features dict
            psychology_data: Optional psychology trap data
            rsi_data: Optional RSI multi-timeframe data
            vol_surface_data: Optional vol surface data
            current_regime: Current market regime

        Returns:
            OmegaDecision with complete decision and transparency
        """
        omega = self._get_omega()
        if omega is None:
            logger.error("OMEGA Orchestrator not available")
            return None

        bot_name = getattr(self, 'bot_name', 'UNKNOWN')

        try:
            decision = omega.get_trading_decision(
                bot_name=bot_name,
                gex_data=gex_data,
                features=features,
                psychology_data=psychology_data,
                rsi_data=rsi_data,
                vol_surface_data=vol_surface_data,
                current_regime=current_regime
            )
            return decision
        except Exception as e:
            logger.error(f"OMEGA decision failed for {bot_name}: {e}")
            return None

    def omega_record_outcome(
        self,
        was_win: bool,
        pnl: float
    ) -> Optional[Dict]:
        """
        Record trade outcome to OMEGA for feedback loops.

        This updates:
            - Proverbs (consecutive loss tracking)
            - Auto-retrain monitor (Gap 1)
            - Thompson allocator (Gap 2)
            - Equity scaler (Gap 10)

        Args:
            was_win: Whether the trade was profitable
            pnl: Actual P&L from the trade

        Returns:
            Dict with feedback loop results
        """
        omega = self._get_omega()
        if omega is None:
            return None

        bot_name = getattr(self, 'bot_name', 'UNKNOWN')

        try:
            return omega.record_trade_outcome(
                bot_name=bot_name,
                was_win=was_win,
                pnl=pnl
            )
        except Exception as e:
            logger.error(f"OMEGA outcome recording failed for {bot_name}: {e}")
            return None

    def omega_can_trade(self) -> bool:
        """
        Check if trading is allowed via OMEGA (Proverbs layer).

        This replaces: circuit_breaker.can_trade()

        Returns:
            True if trading is allowed, False otherwise
        """
        omega = self._get_omega()
        if omega is None:
            logger.warning("OMEGA not available, defaulting to allow trade")
            return True

        bot_name = getattr(self, 'bot_name', 'UNKNOWN')

        try:
            # Get Proverbs verdict directly
            verdict = omega._check_proverbs(bot_name)
            return verdict.can_trade
        except Exception as e:
            logger.error(f"OMEGA Proverbs check failed for {bot_name}: {e}")
            return True  # Default to allow on error

    def omega_get_capital_allocation(self) -> float:
        """
        Get Thompson Sampling capital allocation for this bot.

        Returns:
            Allocation percentage (0.0 to 1.0)
        """
        omega = self._get_omega()
        if omega is None:
            return 0.25  # Default equal allocation

        bot_name = getattr(self, 'bot_name', 'UNKNOWN')

        try:
            thompson = omega._get_thompson_allocator()
            if thompson:
                allocation = thompson.sample_allocation()
                return allocation.allocations.get(bot_name, 0.25)
        except Exception as e:
            logger.error(f"Thompson allocation failed for {bot_name}: {e}")

        return 0.25  # Default

    def omega_get_equity_multiplier(self, base_risk_pct: float) -> Dict:
        """
        Get equity compound scaling for position sizing.

        Args:
            base_risk_pct: Base risk percentage

        Returns:
            Dict with multiplier and adjusted risk
        """
        omega = self._get_omega()
        if omega is None:
            return {
                'multiplier': 1.0,
                'adjusted_risk_pct': base_risk_pct,
                'reason': 'OMEGA not available'
            }

        try:
            return omega.equity_scaler.get_position_multiplier(base_risk_pct)
        except Exception as e:
            logger.error(f"Equity scaling failed: {e}")
            return {
                'multiplier': 1.0,
                'adjusted_risk_pct': base_risk_pct,
                'reason': f'Error: {e}'
            }

    def omega_check_correlation(
        self,
        direction: str,
        proposed_exposure_pct: float
    ) -> Dict:
        """
        Check if a new position would violate correlation limits.

        Args:
            direction: BULLISH, BEARISH, or NEUTRAL
            proposed_exposure_pct: Proposed exposure percentage

        Returns:
            Dict with allowed status and adjusted exposure
        """
        omega = self._get_omega()
        if omega is None:
            return {
                'allowed': True,
                'reason': 'OMEGA not available',
                'adjusted_exposure': proposed_exposure_pct
            }

        bot_name = getattr(self, 'bot_name', 'UNKNOWN')

        try:
            return omega.correlation_enforcer.check_new_position(
                bot_name=bot_name,
                direction=direction,
                proposed_exposure_pct=proposed_exposure_pct
            )
        except Exception as e:
            logger.error(f"Correlation check failed: {e}")
            return {
                'allowed': True,
                'reason': f'Error: {e}',
                'adjusted_exposure': proposed_exposure_pct
            }

    def omega_register_position(
        self,
        direction: str,
        exposure_pct: float,
        underlying: str = "SPY"
    ) -> None:
        """
        Register an active position for correlation tracking.

        Args:
            direction: BULLISH, BEARISH, or NEUTRAL
            exposure_pct: Exposure percentage
            underlying: Underlying symbol
        """
        omega = self._get_omega()
        if omega is None:
            return

        bot_name = getattr(self, 'bot_name', 'UNKNOWN')

        try:
            omega.correlation_enforcer.register_position(
                bot_name=bot_name,
                direction=direction,
                exposure_pct=exposure_pct,
                underlying=underlying
            )
        except Exception as e:
            logger.error(f"Position registration failed: {e}")

    def omega_close_position(self) -> None:
        """Remove position from correlation tracking"""
        omega = self._get_omega()
        if omega is None:
            return

        bot_name = getattr(self, 'bot_name', 'UNKNOWN')

        try:
            omega.correlation_enforcer.close_position(bot_name)
        except Exception as e:
            logger.error(f"Position close tracking failed: {e}")

    def omega_get_status(self) -> Optional[Dict]:
        """Get comprehensive OMEGA status"""
        omega = self._get_omega()
        if omega is None:
            return None

        try:
            return omega.get_status()
        except Exception as e:
            logger.error(f"OMEGA status failed: {e}")
            return None

    # =========================================================================
    # MIGRATION HELPERS
    # =========================================================================

    def migrate_from_circuit_breaker(self):
        """
        Helper to migrate from CircuitBreaker to OMEGA.

        Logs deprecation warning and returns OMEGA-based can_trade.
        """
        import warnings
        warnings.warn(
            "CircuitBreaker is deprecated. Use omega_can_trade() instead. "
            "See trading/circuit_breaker.py for migration guide.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.omega_can_trade()

    def migrate_from_oracle(
        self,
        context: Any,
        **kwargs
    ) -> Optional[Any]:
        """
        Helper to migrate from direct Oracle calls to OMEGA.

        Converts MarketContext to OMEGA format and returns decision.
        """
        import warnings
        warnings.warn(
            "Direct Oracle calls are deprecated. Use omega_get_trading_decision() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        # Convert MarketContext to feature dict
        features = {
            'vix': getattr(context, 'vix', 20),
            'vix_percentile_30d': getattr(context, 'vix_percentile_30d', 50),
            'vix_change_1d': getattr(context, 'vix_change_1d', 0),
            'day_of_week': getattr(context, 'day_of_week', 2),
            'price_change_1d': getattr(context, 'price_change_1d', 0),
            'expected_move_pct': getattr(context, 'expected_move_pct', 1),
            'win_rate_30d': getattr(context, 'win_rate_30d', 0.68),
            'gex_normalized': getattr(context, 'gex_normalized', 0),
            'gex_regime_positive': 1 if str(getattr(context, 'gex_regime', '')).upper() == 'POSITIVE' else 0,
            'gex_distance_to_flip_pct': getattr(context, 'gex_distance_to_flip_pct', 0),
            'gex_between_walls': 1 if getattr(context, 'gex_between_walls', True) else 0
        }

        gex_data = {
            'regime': str(getattr(context, 'gex_regime', 'NEUTRAL')),
            'net_gamma': getattr(context, 'gex_net', 0),
            'put_wall': getattr(context, 'gex_put_wall', 0),
            'call_wall': getattr(context, 'gex_call_wall', 0),
            'flip_point': getattr(context, 'gex_flip_point', 0)
        }

        return self.omega_get_trading_decision(
            gex_data=gex_data,
            features=features,
            current_regime=str(getattr(context, 'gex_regime', 'UNKNOWN'))
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_omega_enabled_bot(base_class, bot_name: str, capital: float = 100000):
    """
    Factory function to create an OMEGA-enabled bot class.

    Args:
        base_class: The original bot class
        bot_name: Name of the bot (ARES, ATHENA, etc.)
        capital: Initial capital

    Returns:
        New class with OMEGA integration

    Example:
        OmegaAres = create_omega_enabled_bot(AresTrader, 'ARES', 100000)
        bot = OmegaAres()
        decision = bot.omega_get_trading_decision(gex_data, features)
    """
    class OmegaBot(OmegaIntegrationMixin, base_class):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('bot_name', bot_name)
            kwargs.setdefault('capital', capital)
            super().__init__(*args, **kwargs)
            self.bot_name = bot_name
            self.capital = capital

    OmegaBot.__name__ = f"Omega{base_class.__name__}"
    return OmegaBot


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Example of how a bot would use this mixin
    class ExampleBot(OmegaIntegrationMixin):
        def __init__(self):
            self.bot_name = "ARES"
            self.capital = 100000

        def run_trading_cycle(self):
            # Build mock data
            gex_data = {
                'regime': 'POSITIVE',
                'net_gamma': 100,
                'put_wall': 580,
                'call_wall': 600
            }

            features = {
                'vix': 18.0,
                'vix_percentile_30d': 45.0,
                'vix_change_1d': -0.5,
                'day_of_week': 2,
                'price_change_1d': 0.3,
                'expected_move_pct': 1.2,
                'win_rate_30d': 0.68,
                'gex_normalized': 0.5,
                'gex_regime_positive': 1,
                'gex_distance_to_flip_pct': 2.0,
                'gex_between_walls': 1
            }

            # Get OMEGA decision
            decision = self.omega_get_trading_decision(
                gex_data=gex_data,
                features=features,
                current_regime='POSITIVE'
            )

            if decision:
                print(f"\n=== OMEGA DECISION ===")
                print(f"Final: {decision.final_decision.value}")
                print(f"Risk: {decision.final_risk_pct:.2f}%")
                print(f"Size: {decision.final_position_size_multiplier:.0%}")
                print("\nDecision Path:")
                for step in decision.decision_path:
                    print(f"  {step}")
            else:
                print("No decision available")

    # Run example
    logging.basicConfig(level=logging.INFO)
    bot = ExampleBot()
    bot.run_trading_cycle()
