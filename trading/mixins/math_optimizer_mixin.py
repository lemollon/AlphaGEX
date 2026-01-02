"""
Math Optimizer Integration Mixin for Trading Bots
=================================================

Provides mathematical optimization capabilities for all trading bots:
- HMM Regime Detection (gate trading decisions)
- Kalman Filter (smooth Greeks)
- Thompson Sampling (capital allocation)
- Convex Optimizer (strike selection)
- HJB Exit Optimizer (exit timing)
- MDP Trade Sequencer (trade ordering)

All decisions are logged to Solomon's audit trail.

Usage:
    from trading.mixins.math_optimizer_mixin import MathOptimizerMixin

    class MyBot(MathOptimizerMixin):
        def __init__(self):
            self._init_math_optimizers("MY_BOT")

        def before_trade(self):
            # Check if regime is favorable
            if not self.math_should_trade():
                return False

            # Get optimized strike
            strike = self.math_optimize_strike(...)
            ...

        def check_exit(self, position):
            return self.math_should_exit(position)

Author: AlphaGEX Quant Team
Date: January 2025
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Central timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Lazy imports to avoid circular dependencies
_math_optimizer = None
_math_available = None


def _get_math_optimizer():
    """Lazy load math optimizer to avoid import issues"""
    global _math_optimizer, _math_available

    if _math_available is not None:
        return _math_optimizer if _math_available else None

    try:
        from core.math_optimizers import get_math_optimizer
        _math_optimizer = get_math_optimizer()
        _math_available = True
        logger.info("Math Optimizer loaded successfully")
        return _math_optimizer
    except ImportError as e:
        _math_available = False
        logger.warning(f"Math Optimizer not available: {e}")
        return None


class MathOptimizerMixin:
    """
    Mixin class providing mathematical optimization for trading bots.

    Integrates 6 algorithms:
    1. HMM Regime Detection - Gates trading based on regime probability
    2. Kalman Filter - Smooths Greeks for better signals
    3. Thompson Sampling - Dynamic capital allocation
    4. Convex Optimizer - Scenario-aware strike selection
    5. HJB Exit Optimizer - Optimal exit timing
    6. MDP Trade Sequencer - Optimal trade ordering

    All decisions are logged to Solomon for full audit trail.
    """

    def _init_math_optimizers(self, bot_name: str, enabled: bool = True):
        """
        Initialize math optimizer integration for this bot.

        Args:
            bot_name: The bot identifier (ARES, ATHENA, PHOENIX, ATLAS)
            enabled: Whether to enable optimizers (default True)
        """
        self._math_bot_name = bot_name
        self._math_enabled = enabled
        self._math_optimizer = None

        # Configuration thresholds
        self._math_config = {
            # HMM Regime
            'min_regime_confidence': 0.60,  # Minimum confidence to trade
            'favorable_regimes': [
                'TRENDING_BULLISH', 'TRENDING_BEARISH', 'MEAN_REVERTING', 'LOW_VOLATILITY'
            ],
            'avoid_regimes': ['HIGH_VOLATILITY', 'GAMMA_SQUEEZE'],

            # Thompson Sampling
            'use_thompson_allocation': True,
            'min_allocation_pct': 0.10,  # Minimum 10% allocation to trade

            # Convex Strike Optimizer
            'use_strike_optimization': True,
            'min_improvement_pct': 1.0,  # Only use optimized if 1%+ better

            # HJB Exit
            'use_hjb_exit': True,
            'exit_check_interval_minutes': 5,

            # MDP Sequencer
            'use_mdp_sequencing': True,
            'max_concurrent_trades': 3
        }

        # Stats tracking
        self._math_stats = {
            'regime_gates_triggered': 0,
            'strikes_optimized': 0,
            'exits_optimized': 0,
            'trades_sequenced': 0
        }

        # Initialize optimizer
        if enabled:
            self._math_optimizer = _get_math_optimizer()
            if self._math_optimizer:
                logger.info(f"{bot_name}: Math optimizers initialized and enabled")
            else:
                logger.warning(f"{bot_name}: Math optimizers requested but not available")

    @property
    def math_optimizer(self):
        """Get the math optimizer instance"""
        if self._math_optimizer is None:
            self._math_optimizer = _get_math_optimizer()
        return self._math_optimizer

    # =========================================================================
    # HMM REGIME DETECTION
    # =========================================================================

    def math_update_regime(self, market_data: Dict[str, float]) -> Dict:
        """
        Update regime detection with current market data.

        Args:
            market_data: Dict with keys like 'vix', 'net_gamma', 'momentum', etc.

        Returns:
            Dict with regime info: {regime, probability, confidence, should_trade}
        """
        if not self._math_enabled or not self.math_optimizer:
            return {'regime': 'UNKNOWN', 'probability': 0.5, 'confidence': 0, 'should_trade': True}

        try:
            regime_state = self.math_optimizer.hmm_regime.update(market_data)

            # Determine if we should trade based on regime
            regime_name = regime_state.regime.value
            should_trade = (
                regime_state.confidence >= self._math_config['min_regime_confidence'] and
                regime_name in self._math_config['favorable_regimes'] and
                regime_name not in self._math_config['avoid_regimes']
            )

            if not should_trade:
                self._math_stats['regime_gates_triggered'] += 1

            result = {
                'regime': regime_name,
                'probability': regime_state.probability,
                'confidence': regime_state.confidence,
                'should_trade': should_trade,
                'all_probabilities': self.math_optimizer.hmm_regime.get_regime_probabilities()
            }

            logger.debug(f"{self._math_bot_name}: Regime={regime_name} (prob={regime_state.probability:.2%}), trade={should_trade}")

            return result

        except Exception as e:
            logger.error(f"{self._math_bot_name}: Regime update failed: {e}")
            return {'regime': 'ERROR', 'probability': 0, 'confidence': 0, 'should_trade': True}

    def math_should_trade_regime(self, market_data: Dict[str, float] = None) -> Tuple[bool, str]:
        """
        Check if current regime allows trading.

        Args:
            market_data: Optional market data to update regime first

        Returns:
            Tuple of (should_trade, reason)
        """
        if not self._math_enabled or not self.math_optimizer:
            return True, "Math optimizers disabled"

        if market_data:
            regime_info = self.math_update_regime(market_data)
        else:
            # Use current regime belief
            probs = self.math_optimizer.hmm_regime.get_regime_probabilities()
            max_regime = max(probs, key=probs.get)
            max_prob = probs[max_regime]

            regime_info = {
                'regime': max_regime,
                'probability': max_prob,
                'confidence': max_prob,
                'should_trade': max_regime in self._math_config['favorable_regimes']
            }

        if regime_info['should_trade']:
            return True, f"Favorable regime: {regime_info['regime']} ({regime_info['probability']:.0%})"
        else:
            return False, f"Unfavorable regime: {regime_info['regime']} ({regime_info['probability']:.0%})"

    # =========================================================================
    # KALMAN FILTER - GREEKS SMOOTHING
    # =========================================================================

    def math_smooth_greeks(self, raw_greeks: Dict[str, float]) -> Dict[str, float]:
        """
        Smooth raw Greeks using Kalman filter.

        Args:
            raw_greeks: Dict with 'delta', 'gamma', 'theta', 'vega', etc.

        Returns:
            Dict with smoothed Greek values
        """
        if not self._math_enabled or not self.math_optimizer:
            return raw_greeks

        try:
            self.math_optimizer.kalman_greeks.update(raw_greeks)
            smoothed = self.math_optimizer.kalman_greeks.get_smoothed_greeks()

            logger.debug(f"{self._math_bot_name}: Smoothed Greeks - delta: {raw_greeks.get('delta', 0):.4f} → {smoothed.get('delta', 0):.4f}")

            return smoothed

        except Exception as e:
            logger.error(f"{self._math_bot_name}: Greeks smoothing failed: {e}")
            return raw_greeks

    # =========================================================================
    # THOMPSON SAMPLING - CAPITAL ALLOCATION
    # =========================================================================

    def math_get_allocation(self, total_capital: float = 100000) -> Dict[str, float]:
        """
        Get Thompson Sampling allocation for all bots.

        Args:
            total_capital: Total capital to allocate

        Returns:
            Dict with bot -> allocation amount
        """
        if not self._math_enabled or not self.math_optimizer:
            # Equal allocation fallback
            bots = ['ARES', 'ATHENA', 'PHOENIX', 'ATLAS']
            return {bot: total_capital / len(bots) for bot in bots}

        try:
            allocation = self.math_optimizer.thompson.sample_allocation(total_capital)

            # Convert percentages to dollar amounts
            dollar_allocations = {
                bot: alloc * total_capital
                for bot, alloc in allocation.allocations.items()
            }

            logger.info(f"Thompson allocation: {', '.join(f'{b}:${a:,.0f}' for b, a in dollar_allocations.items())}")

            return dollar_allocations

        except Exception as e:
            logger.error(f"Thompson allocation failed: {e}")
            bots = ['ARES', 'ATHENA', 'PHOENIX', 'ATLAS']
            return {bot: total_capital / len(bots) for bot in bots}

    def math_get_my_allocation(self, total_capital: float = 100000) -> float:
        """Get this bot's allocated capital"""
        allocations = self.math_get_allocation(total_capital)
        return allocations.get(self._math_bot_name, total_capital / 4)

    def math_record_outcome(self, win: bool, pnl: float):
        """
        Record trade outcome for Thompson Sampling learning.

        Args:
            win: Whether trade was profitable
            pnl: Actual P&L amount
        """
        if not self._math_enabled or not self.math_optimizer:
            return

        try:
            self.math_optimizer.thompson.record_outcome(self._math_bot_name, win, pnl)
            logger.info(f"{self._math_bot_name}: Recorded outcome win={win}, pnl=${pnl:.2f} to Thompson")
        except Exception as e:
            logger.error(f"{self._math_bot_name}: Failed to record Thompson outcome: {e}")

    # =========================================================================
    # CONVEX OPTIMIZER - STRIKE SELECTION
    # =========================================================================

    def math_optimize_strike(
        self,
        available_strikes: List[Dict],
        spot_price: float,
        target_delta: float,
        delta_tolerance: float = 0.05,
        time_to_expiry: float = 1.0
    ) -> Dict:
        """
        Optimize strike selection using convex optimization.

        Args:
            available_strikes: List of {strike, delta, gamma, theta} dicts
            spot_price: Current underlying price
            target_delta: Target delta
            delta_tolerance: Acceptable delta deviation
            time_to_expiry: Days until expiration

        Returns:
            Dict with optimized strike info
        """
        if not self._math_enabled or not self.math_optimizer or not self._math_config['use_strike_optimization']:
            # Fallback: pick closest to target delta
            if not available_strikes:
                return {'strike': None, 'optimized': False}

            closest = min(available_strikes, key=lambda s: abs(abs(s.get('delta', 0)) - target_delta))
            return {
                'strike': closest['strike'],
                'delta': closest.get('delta'),
                'optimized': False,
                'reason': 'Fallback to closest delta'
            }

        try:
            result = self.math_optimizer.convex_strike.optimize(
                available_strikes=available_strikes,
                spot_price=spot_price,
                target_delta=target_delta,
                delta_tolerance=delta_tolerance,
                time_to_expiry=time_to_expiry
            )

            # Check if optimization provides meaningful improvement
            use_optimized = result.improvement_pct >= self._math_config['min_improvement_pct']

            if use_optimized:
                self._math_stats['strikes_optimized'] += 1
                logger.info(
                    f"{self._math_bot_name}: Strike optimized {result.original_strike} → {result.optimized_strike} "
                    f"({result.improvement_pct:.1f}% improvement)"
                )

            return {
                'strike': result.optimized_strike if use_optimized else result.original_strike,
                'original_strike': result.original_strike,
                'optimized_strike': result.optimized_strike,
                'improvement_pct': result.improvement_pct,
                'optimized': use_optimized,
                'reason': f"Convex optimization: {result.improvement_pct:.1f}% better" if use_optimized else "Below improvement threshold"
            }

        except Exception as e:
            logger.error(f"{self._math_bot_name}: Strike optimization failed: {e}")
            if not available_strikes:
                return {'strike': None, 'optimized': False}
            closest = min(available_strikes, key=lambda s: abs(abs(s.get('delta', 0)) - target_delta))
            return {
                'strike': closest['strike'],
                'optimized': False,
                'reason': f'Optimization error: {e}'
            }

    # =========================================================================
    # HJB EXIT OPTIMIZER
    # =========================================================================

    def math_should_exit(
        self,
        current_pnl: float,
        max_profit: float,
        entry_time: datetime,
        expiry_time: datetime,
        current_volatility: float = 0.15,
        theta_per_hour: float = 0
    ) -> Dict:
        """
        Check if position should be exited using HJB optimization.

        Args:
            current_pnl: Current unrealized P&L
            max_profit: Maximum possible profit
            entry_time: When position was opened
            expiry_time: When position expires
            current_volatility: Current implied volatility
            theta_per_hour: Expected theta decay per hour

        Returns:
            Dict with exit recommendation
        """
        if not self._math_enabled or not self.math_optimizer or not self._math_config['use_hjb_exit']:
            # Fallback: simple percentage targets
            pnl_pct = current_pnl / max_profit if max_profit > 0 else 0
            should_exit = pnl_pct >= 0.50 or pnl_pct <= -1.0

            return {
                'should_exit': should_exit,
                'pnl_pct': pnl_pct,
                'reason': 'Fixed target' if should_exit else 'Below target',
                'optimized': False
            }

        try:
            signal = self.math_optimizer.hjb_exit.should_exit(
                current_pnl=current_pnl,
                max_profit=max_profit,
                entry_time=entry_time,
                expiry_time=expiry_time,
                current_volatility=current_volatility,
                theta_per_hour=theta_per_hour
            )

            if signal.should_exit:
                self._math_stats['exits_optimized'] += 1
                logger.info(f"{self._math_bot_name}: HJB exit signal: {signal.reason}")

            return {
                'should_exit': signal.should_exit,
                'pnl_pct': signal.current_pnl_pct,
                'optimal_boundary': signal.optimal_boundary,
                'expected_future_value': signal.expected_future_value,
                'reason': signal.reason,
                'optimized': True
            }

        except Exception as e:
            logger.error(f"{self._math_bot_name}: HJB exit check failed: {e}")
            pnl_pct = current_pnl / max_profit if max_profit > 0 else 0
            return {
                'should_exit': pnl_pct >= 0.50 or pnl_pct <= -1.0,
                'pnl_pct': pnl_pct,
                'reason': f'HJB error, fallback: {e}',
                'optimized': False
            }

    # =========================================================================
    # MDP TRADE SEQUENCER
    # =========================================================================

    def math_sequence_trades(
        self,
        pending_trades: List[Dict],
        existing_positions: List[Dict] = None,
        market_regime: str = None
    ) -> Dict:
        """
        Optimize sequence of pending trades.

        Args:
            pending_trades: List of trade signals
            existing_positions: Current open positions
            market_regime: Current market regime

        Returns:
            Dict with optimized trade sequence
        """
        if not self._math_enabled or not self.math_optimizer or not self._math_config['use_mdp_sequencing']:
            return {
                'trades': pending_trades[:self._math_config['max_concurrent_trades']],
                'skipped': [],
                'optimized': False
            }

        try:
            # Get current regime if not provided
            if not market_regime:
                probs = self.math_optimizer.hmm_regime.get_regime_probabilities()
                market_regime = max(probs, key=probs.get)

            result = self.math_optimizer.mdp_sequencer.sequence_trades(
                pending_trades=pending_trades,
                existing_positions=existing_positions or [],
                market_regime=market_regime,
                max_trades=self._math_config['max_concurrent_trades']
            )

            self._math_stats['trades_sequenced'] += len(pending_trades)

            logger.info(
                f"{self._math_bot_name}: MDP sequencing: {len(pending_trades)} → {len(result.optimized_order)} trades"
            )

            return {
                'trades': result.optimized_order,
                'skipped': result.skipped_trades,
                'original_ev': result.expected_value_original,
                'optimized_ev': result.expected_value_optimized,
                'reason': result.reason,
                'optimized': True
            }

        except Exception as e:
            logger.error(f"{self._math_bot_name}: Trade sequencing failed: {e}")
            return {
                'trades': pending_trades[:self._math_config['max_concurrent_trades']],
                'skipped': [],
                'reason': f'Sequencing error: {e}',
                'optimized': False
            }

    # =========================================================================
    # FULL ANALYSIS PIPELINE
    # =========================================================================

    def math_full_analysis(self, market_data: Dict, greeks: Dict = None) -> Dict:
        """
        Run full market analysis using all algorithms.

        Args:
            market_data: Market observation data
            greeks: Optional Greeks data

        Returns:
            Comprehensive analysis result
        """
        if not self._math_enabled or not self.math_optimizer:
            return {'enabled': False, 'reason': 'Math optimizers disabled'}

        try:
            data = {**market_data}
            if greeks:
                data['greeks'] = greeks

            result = self.math_optimizer.analyze_market(data)
            result['bot'] = self._math_bot_name
            result['stats'] = self._math_stats.copy()

            return result

        except Exception as e:
            logger.error(f"{self._math_bot_name}: Full analysis failed: {e}")
            return {'enabled': True, 'error': str(e)}

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def math_set_config(self, key: str, value: Any):
        """Set a math optimizer configuration value"""
        if key in self._math_config:
            self._math_config[key] = value
            logger.info(f"{self._math_bot_name}: Math config {key} = {value}")

    def math_get_config(self) -> Dict:
        """Get current math optimizer configuration"""
        return self._math_config.copy()

    def math_get_stats(self) -> Dict:
        """Get math optimizer usage statistics"""
        return {
            'bot': self._math_bot_name,
            'enabled': self._math_enabled,
            'optimizer_available': self.math_optimizer is not None,
            'stats': self._math_stats.copy()
        }

    def math_enable(self):
        """Enable math optimizers"""
        self._math_enabled = True
        self._math_optimizer = _get_math_optimizer()
        logger.info(f"{self._math_bot_name}: Math optimizers ENABLED")

    def math_disable(self):
        """Disable math optimizers"""
        self._math_enabled = False
        logger.info(f"{self._math_bot_name}: Math optimizers DISABLED")
