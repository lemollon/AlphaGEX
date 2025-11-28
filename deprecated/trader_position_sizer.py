"""
Position Sizing Module for Autonomous Trading
==============================================

Extracted from autonomous_paper_trader.py to reduce class complexity.

This module handles:
- Kelly Criterion position sizing
- VIX stress factor adjustments
- Capital availability calculations
- Position value limits

Author: AlphaGEX
Date: 2025-11-27
"""

import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

from database_adapter import get_connection

logger = logging.getLogger(__name__)


@dataclass
class PositionSizingResult:
    """Result of position sizing calculation"""
    contracts: int
    blocked: bool
    methodology: str
    kelly_pct: float
    raw_kelly: float
    adjusted_kelly: float
    adjustment_type: str
    vix_stress_factor: float
    vix_stress_level: str
    current_vix: float
    max_position_value: float
    final_position_value: float
    cost_per_contract: float
    block_reason: Optional[str] = None
    backtest_params: Optional[Dict] = None


class TraderPositionSizer:
    """
    Position sizing using Kelly Criterion with VIX stress adjustments.

    VIX Thresholds (22/28/35) are MORE CONSERVATIVE than config (20/30/40).
    This is INTENTIONAL - traders reduce size EARLIER for safety.
    See tests/test_vix_configuration.py for validation.
    """

    # VIX stress thresholds (more conservative than config)
    VIX_ELEVATED_THRESHOLD = 22  # Config uses 20
    VIX_HIGH_THRESHOLD = 28      # Config uses 30
    VIX_EXTREME_THRESHOLD = 35   # Config uses 40

    # Position limits
    MAX_KELLY_PCT = 0.20         # 20% max Kelly
    MIN_KELLY_PCT = 0.005        # 0.5% min Kelly
    MAX_POSITION_PCT = 0.25      # 25% of capital max
    MAX_CONTRACTS_SPY = 10       # Liquidity constraint

    def __init__(self, get_capital_func, get_vix_func, get_strategy_stats_func):
        """
        Initialize position sizer.

        Args:
            get_capital_func: Function to get total capital
            get_vix_func: Function to get current VIX
            get_strategy_stats_func: Function to get strategy backtest stats
        """
        self.get_capital = get_capital_func
        self.get_vix = get_vix_func
        self.get_strategy_stats = get_strategy_stats_func

    def get_available_capital(self) -> float:
        """Calculate available capital after accounting for open positions."""
        total_capital = self.get_capital()

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(ABS(entry_price * contracts * 100)), 0) as used
                FROM autonomous_open_positions
            """)
            result = cursor.fetchone()
            used_capital = float(result[0]) if result else 0
            conn.close()

            return max(0, total_capital - used_capital)
        except Exception as e:
            logger.warning(f"Error getting available capital: {e}")
            return total_capital * 0.8  # Assume 80% available

    def get_vix_stress_factor(self, current_vix: float) -> Tuple[float, str]:
        """
        Get VIX-based position reduction factor.

        Returns:
            (stress_factor, stress_level) - e.g., (0.5, 'high')
        """
        if current_vix >= self.VIX_EXTREME_THRESHOLD:
            return 0.25, 'extreme'  # 75% reduction
        elif current_vix >= self.VIX_HIGH_THRESHOLD:
            return 0.50, 'high'     # 50% reduction
        elif current_vix >= self.VIX_ELEVATED_THRESHOLD:
            return 0.75, 'elevated' # 25% reduction
        else:
            return 1.0, 'normal'

    def calculate_kelly(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Calculate raw Kelly criterion.

        Kelly = W - (1-W)/R where R = avg_win/avg_loss

        Returns:
            Kelly fraction (can be negative if edge is negative)
        """
        if avg_loss <= 0:
            avg_loss = 12.0  # Conservative default

        risk_reward = avg_win / avg_loss

        if risk_reward <= 0:
            return -1.0  # Invalid setup

        return win_rate - ((1 - win_rate) / risk_reward)

    def calculate_position_size(
        self,
        strategy_name: str,
        entry_price: float,
        confidence: int = 70,
        max_contracts: int = None
    ) -> PositionSizingResult:
        """
        Calculate position size using Kelly Criterion from backtest data.

        This mirrors the SPX trader's Kelly-based sizing:
        1. Look up backtest stats for strategy
        2. Calculate Kelly fraction
        3. Apply adjustments (half-Kelly for proven, quarter-Kelly for unproven)
        4. Apply VIX stress factor
        5. Return contracts and sizing details

        Args:
            strategy_name: Name of strategy for backtest lookup
            entry_price: Option entry price
            confidence: Trade confidence (0-100)
            max_contracts: Optional contract limit (default MAX_CONTRACTS_SPY)

        Returns:
            PositionSizingResult with contracts and details
        """
        if max_contracts is None:
            max_contracts = self.MAX_CONTRACTS_SPY

        available = self.get_available_capital()
        total_capital = self.get_capital()

        # Get backtest params
        params = self.get_strategy_stats(strategy_name)
        win_rate = params.get('win_rate', 0.55)
        avg_win = params.get('avg_win', 8.0)
        avg_loss = params.get('avg_loss', 12.0)
        is_proven = params.get('is_proven', False)

        # Apply defaults for missing values
        if avg_win <= 0:
            avg_win = 8.0
        if avg_loss <= 0:
            avg_loss = 12.0

        # Calculate Kelly
        kelly = self.calculate_kelly(win_rate, avg_win, avg_loss)

        # CRITICAL: Negative Kelly = negative expected value = BLOCK TRADE
        if kelly <= 0:
            logger.warning(
                f"Kelly criterion negative ({kelly:.2%}) for {strategy_name} - "
                f"WR={win_rate:.0%}, R/R={avg_win/avg_loss:.2f} - BLOCKING TRADE"
            )
            return PositionSizingResult(
                contracts=0,
                blocked=True,
                methodology='Kelly-Backtest-VIX',
                kelly_pct=0,
                raw_kelly=kelly,
                adjusted_kelly=0,
                adjustment_type='blocked',
                vix_stress_factor=1.0,
                vix_stress_level='normal',
                current_vix=self.get_vix(),
                max_position_value=0,
                final_position_value=0,
                cost_per_contract=entry_price * 100,
                block_reason=f'Negative Kelly ({kelly:.2%}) indicates negative expected value',
                backtest_params=params
            )

        # Apply Kelly fraction based on proven status
        if is_proven:
            adjusted_kelly = kelly * 0.5  # Half-Kelly for proven
            adjustment_type = 'half-kelly'
        else:
            adjusted_kelly = kelly * 0.25  # Quarter-Kelly for unproven
            adjustment_type = 'quarter-kelly'

        # Cap Kelly
        final_kelly = max(self.MIN_KELLY_PCT, min(self.MAX_KELLY_PCT, adjusted_kelly))

        # Calculate position value
        max_position_value = available * final_kelly

        # Apply confidence adjustment (0.5-1.0 range)
        confidence_factor = (confidence / 100) * 0.5 + 0.5

        # Apply VIX stress factor
        current_vix = self.get_vix()
        vix_stress_factor, vix_stress_level = self.get_vix_stress_factor(current_vix)

        if vix_stress_level != 'normal':
            logger.warning(
                f"VIX {vix_stress_level.upper()} ({current_vix:.1f}): "
                f"Position size reduced by {(1-vix_stress_factor)*100:.0f}%"
            )

        # Apply all adjustments
        position_value = max_position_value * confidence_factor * vix_stress_factor

        # Cap at max position percentage
        position_value = min(position_value, total_capital * self.MAX_POSITION_PCT)

        # Calculate contracts
        cost_per_contract = entry_price * 100
        if cost_per_contract <= 0:
            contracts = 0
            raw_contracts = 0
        else:
            raw_contracts = int(position_value / cost_per_contract)
            contracts = min(raw_contracts, max_contracts)

        logger.info(
            f"Kelly sizing for {strategy_name}: {contracts} contracts "
            f"(Kelly={final_kelly:.1%}, {adjustment_type}, "
            f"WR={win_rate:.0%}, proven={is_proven})"
        )

        return PositionSizingResult(
            contracts=contracts,
            blocked=False,
            methodology='Kelly-Backtest-VIX',
            kelly_pct=final_kelly * 100,
            raw_kelly=kelly,
            adjusted_kelly=adjusted_kelly,
            adjustment_type=adjustment_type,
            vix_stress_factor=vix_stress_factor,
            vix_stress_level=vix_stress_level,
            current_vix=current_vix,
            max_position_value=max_position_value,
            final_position_value=position_value,
            cost_per_contract=cost_per_contract,
            backtest_params=params
        )


def create_position_sizer(trader_instance) -> TraderPositionSizer:
    """
    Factory function to create a position sizer from a trader instance.

    Args:
        trader_instance: AutonomousPaperTrader instance

    Returns:
        TraderPositionSizer configured with trader's functions
    """
    return TraderPositionSizer(
        get_capital_func=lambda: float(trader_instance.get_config('capital')),
        get_vix_func=trader_instance._get_vix,
        get_strategy_stats_func=trader_instance.get_strategy_stats_for_pattern
    )
