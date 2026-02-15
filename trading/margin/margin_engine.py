"""
Margin Calculation Engine - Core margin metrics for all market types.

Provides 13 core calculations for any position across stock futures,
crypto futures, and crypto perpetual futures.

CRITICAL: This is a real-money trading system. Every calculation must handle
edge cases correctly. When in doubt, be MORE conservative.

Exchange-specific liquidation formulas are isolated into separate methods
so they can be individually validated and updated.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from trading.margin.margin_config import (
    MarketType,
    MarginMode,
    MarketConfig,
    BotMarginConfig,
    LiquidationMethod,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


@dataclass
class PositionMarginMetrics:
    """Complete margin metrics for a single position."""
    # Identity
    position_id: str
    bot_name: str
    symbol: str
    side: str                           # "long" or "short"

    # Position details
    quantity: float                     # Contracts or coin quantity
    entry_price: float
    current_price: float
    contract_multiplier: float

    # Core margin calculations (13 metrics)
    notional_value: float               # 1. position_notional_value
    initial_margin_required: float      # 2. initial_margin_required
    maintenance_margin_required: float  # 3. maintenance_margin_required
    unrealized_pnl: float              # 10. unrealized_pnl
    liquidation_price: Optional[float]  # 8. distance_to_liquidation_price
    distance_to_liq_pct: Optional[float] # 9. distance_to_liquidation_percent

    # Funding (perps only)
    funding_rate: Optional[float] = None
    funding_cost_projection_daily: Optional[float] = None
    funding_cost_projection_30d: Optional[float] = None

    # Metadata
    market_type: str = ""
    exchange: str = ""
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "bot_name": self.bot_name,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "contract_multiplier": self.contract_multiplier,
            "notional_value": round(self.notional_value, 2),
            "initial_margin_required": round(self.initial_margin_required, 2),
            "maintenance_margin_required": round(self.maintenance_margin_required, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "liquidation_price": round(self.liquidation_price, 2) if self.liquidation_price else None,
            "distance_to_liq_pct": round(self.distance_to_liq_pct, 4) if self.distance_to_liq_pct else None,
            "funding_rate": self.funding_rate,
            "funding_cost_projection_daily": (
                round(self.funding_cost_projection_daily, 4)
                if self.funding_cost_projection_daily else None
            ),
            "funding_cost_projection_30d": (
                round(self.funding_cost_projection_30d, 2)
                if self.funding_cost_projection_30d else None
            ),
            "market_type": self.market_type,
            "exchange": self.exchange,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class AccountMarginMetrics:
    """Aggregate margin metrics for a bot's account."""
    bot_name: str
    account_equity: float

    # Aggregated margin (4, 5, 6, 7)
    total_margin_used: float            # 4. margin_used
    available_margin: float             # 5. available_margin
    margin_usage_pct: float             # 6. margin_usage_percent
    margin_ratio: float                 # 7. margin_ratio (equity / maint margin)

    # Derived metrics (11, 12)
    effective_leverage: float           # 11. effective_leverage
    max_additional_notional: float      # 12. max_position_size

    # Risk summary
    total_unrealized_pnl: float
    total_notional_value: float
    position_count: int
    health_status: str                  # HEALTHY, WARNING, DANGER, CRITICAL

    # Per-position details
    positions: List[PositionMarginMetrics] = field(default_factory=list)

    # Funding costs (perps only, metric 13)
    total_funding_cost_daily: Optional[float] = None
    total_funding_cost_30d: Optional[float] = None

    # Thresholds used
    warning_threshold: float = 60.0
    danger_threshold: float = 80.0
    critical_threshold: float = 90.0

    # Metadata
    market_type: str = ""
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bot_name": self.bot_name,
            "account_equity": round(self.account_equity, 2),
            "total_margin_used": round(self.total_margin_used, 2),
            "available_margin": round(self.available_margin, 2),
            "margin_usage_pct": round(self.margin_usage_pct, 2),
            "margin_ratio": round(self.margin_ratio, 4),
            "effective_leverage": round(self.effective_leverage, 4),
            "max_additional_notional": round(self.max_additional_notional, 2),
            "total_unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "total_notional_value": round(self.total_notional_value, 2),
            "position_count": self.position_count,
            "health_status": self.health_status,
            "positions": [p.to_dict() for p in self.positions],
            "total_funding_cost_daily": (
                round(self.total_funding_cost_daily, 4)
                if self.total_funding_cost_daily else None
            ),
            "total_funding_cost_30d": (
                round(self.total_funding_cost_30d, 2)
                if self.total_funding_cost_30d else None
            ),
            "warning_threshold": self.warning_threshold,
            "danger_threshold": self.danger_threshold,
            "critical_threshold": self.critical_threshold,
            "market_type": self.market_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class PreTradeCheckResult:
    """Result of a pre-trade margin check."""
    approved: bool
    reason: str
    available_margin: float
    margin_required: float
    new_margin_usage_pct: float
    new_effective_leverage: float
    liquidation_price: Optional[float] = None
    distance_to_liq_pct: Optional[float] = None
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "available_margin": round(self.available_margin, 2),
            "margin_required": round(self.margin_required, 2),
            "new_margin_usage_pct": round(self.new_margin_usage_pct, 2),
            "new_effective_leverage": round(self.new_effective_leverage, 4),
            "liquidation_price": round(self.liquidation_price, 2) if self.liquidation_price else None,
            "distance_to_liq_pct": (
                round(self.distance_to_liq_pct, 4) if self.distance_to_liq_pct else None
            ),
            "violations": self.violations,
        }


@dataclass
class ScenarioResult:
    """Result of a margin scenario simulation."""
    scenario_description: str
    current_margin_usage_pct: float
    projected_margin_usage_pct: float
    current_liq_distance_pct: Optional[float]
    projected_liq_distance_pct: Optional[float]
    would_trigger_liquidation: bool
    would_trigger_margin_call: bool
    price_to_liquidation: Optional[float] = None
    max_adverse_move_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_description": self.scenario_description,
            "current_margin_usage_pct": round(self.current_margin_usage_pct, 2),
            "projected_margin_usage_pct": round(self.projected_margin_usage_pct, 2),
            "current_liq_distance_pct": (
                round(self.current_liq_distance_pct, 4)
                if self.current_liq_distance_pct else None
            ),
            "projected_liq_distance_pct": (
                round(self.projected_liq_distance_pct, 4)
                if self.projected_liq_distance_pct else None
            ),
            "would_trigger_liquidation": self.would_trigger_liquidation,
            "would_trigger_margin_call": self.would_trigger_margin_call,
            "price_to_liquidation": (
                round(self.price_to_liquidation, 2) if self.price_to_liquidation else None
            ),
            "max_adverse_move_pct": (
                round(self.max_adverse_move_pct, 4) if self.max_adverse_move_pct else None
            ),
        }


class MarginEngine:
    """Core margin calculation engine for all market types.

    Handles stock futures, crypto futures, and crypto perpetual futures
    with market-type-specific calculation logic.

    Usage:
        engine = MarginEngine(bot_margin_config)

        # Calculate metrics for all positions
        metrics = engine.calculate_account_metrics(account_equity, positions)

        # Pre-trade check
        result = engine.check_pre_trade(account_equity, positions, proposed_trade)

        # Scenario simulation
        scenario = engine.simulate_price_move(account_equity, positions, price_change_pct=-5.0)
    """

    def __init__(self, bot_config: BotMarginConfig):
        self.bot_config = bot_config
        self.market_config = bot_config.market_config

    # =========================================================================
    # CORE CALCULATIONS (13 metrics)
    # =========================================================================

    def calc_notional_value(
        self, quantity: float, current_price: float
    ) -> float:
        """1. Position Notional Value.

        = quantity × current_price × contract_multiplier

        For stock futures: 2 ES contracts @ 6000 = 2 × 6000 × 50 = $600,000
        For crypto perps: 0.5 BTC @ 100,000 = 0.5 × 100,000 × 1 = $50,000
        For options: defined by spread width, not notional
        """
        if quantity <= 0 or current_price <= 0:
            return 0.0
        return abs(quantity) * current_price * self.market_config.contract_multiplier

    def calc_initial_margin(
        self, quantity: float, current_price: float, leverage: Optional[float] = None
    ) -> float:
        """2. Initial Margin Required.

        Stock futures: contracts × initial_margin_per_contract
        Crypto futures: same as stock futures (CME uses per-contract)
        Crypto perps: notional_value / leverage (or notional × initial_margin_rate)
        Options: max loss of the spread (handled separately)
        """
        if quantity <= 0:
            return 0.0

        mc = self.market_config
        abs_qty = abs(quantity)

        if mc.is_margin_per_contract:
            # Fixed $ per contract (CME futures)
            return abs_qty * mc.initial_margin_rate
        else:
            # Percentage of notional (crypto perps)
            notional = self.calc_notional_value(abs_qty, current_price)
            if mc.market_type == MarketType.CRYPTO_PERPETUAL:
                eff_leverage = leverage or self.bot_config.effective_leverage
                if eff_leverage > 0:
                    return notional / eff_leverage
            # Default: use initial_margin_rate as percentage
            if mc.initial_margin_rate > 0:
                return notional * mc.initial_margin_rate
            return notional  # No leverage (spot)

    def calc_maintenance_margin(
        self, quantity: float, current_price: float
    ) -> float:
        """3. Maintenance Margin Required.

        Stock futures: contracts × maintenance_margin_per_contract
        Crypto futures: same pattern
        Crypto perps: notional × maintenance_margin_rate
        """
        if quantity <= 0:
            return 0.0

        mc = self.market_config
        abs_qty = abs(quantity)

        if mc.is_margin_per_contract:
            return abs_qty * mc.maintenance_margin_rate
        else:
            notional = self.calc_notional_value(abs_qty, current_price)
            if mc.maintenance_margin_rate > 0:
                return notional * mc.maintenance_margin_rate
            return notional

    def calc_margin_used(
        self, positions: List[Dict[str, Any]]
    ) -> float:
        """4. Total Margin Used across all positions.

        = sum of initial_margin_required for all open positions
        """
        total = 0.0
        for pos in positions:
            qty = abs(float(pos.get("quantity", 0)))
            price = float(pos.get("current_price", 0) or pos.get("entry_price", 0))
            leverage = pos.get("leverage")
            total += self.calc_initial_margin(qty, price, leverage)
        return total

    def calc_available_margin(
        self, account_equity: float, margin_used: float
    ) -> float:
        """5. Available Margin.

        = account_equity - margin_used
        Can be negative (margin call territory).
        """
        return account_equity - margin_used

    def calc_margin_usage_pct(
        self, margin_used: float, account_equity: float
    ) -> float:
        """6. Margin Usage Percent.

        = (margin_used / account_equity) × 100
        Returns 0 if no equity, 100+ if margin exceeds equity.
        """
        if account_equity <= 0:
            return 100.0 if margin_used > 0 else 0.0
        return (margin_used / account_equity) * 100.0

    def calc_margin_ratio(
        self, account_equity: float, total_maintenance_margin: float
    ) -> float:
        """7. Margin Ratio.

        = account_equity / maintenance_margin_required
        < 1.0 = liquidation territory
        > 1.5 = generally safe
        """
        if total_maintenance_margin <= 0:
            return float('inf') if account_equity > 0 else 0.0
        return account_equity / total_maintenance_margin

    def calc_liquidation_price(
        self,
        side: str,
        entry_price: float,
        quantity: float,
        account_equity: float,
        total_maintenance_margin_other: float,
        leverage: Optional[float] = None,
    ) -> Optional[float]:
        """8. Liquidation Price.

        Exchange-specific formulas. These are SIMPLIFIED approximations.
        For production accuracy, use exchange-specific calculators.

        For LONG positions: price where equity falls below maintenance margin
        For SHORT positions: price where equity rises above account capacity

        Args:
            side: "long" or "short"
            entry_price: Position entry price
            quantity: Position size (contracts or coins)
            account_equity: Total account equity
            total_maintenance_margin_other: Maintenance margin used by OTHER positions
            leverage: Explicit leverage (for perps)

        Returns:
            Liquidation price or None if not applicable (e.g., spot trading)
        """
        mc = self.market_config
        abs_qty = abs(quantity)

        if mc.market_type == MarketType.CRYPTO_SPOT:
            return None  # No liquidation on spot

        if abs_qty <= 0 or entry_price <= 0:
            return None

        is_long = side.lower() == "long"

        # Available equity for this position's maintenance
        equity_for_position = account_equity - total_maintenance_margin_other

        if mc.market_type in (MarketType.STOCK_FUTURES, MarketType.CRYPTO_FUTURES):
            return self._calc_liq_price_futures(
                is_long, entry_price, abs_qty, equity_for_position
            )
        elif mc.market_type == MarketType.CRYPTO_PERPETUAL:
            eff_leverage = leverage or self.bot_config.effective_leverage
            return self._calc_liq_price_perpetual(
                is_long, entry_price, abs_qty, equity_for_position, eff_leverage
            )
        elif mc.market_type == MarketType.OPTIONS:
            return self._calc_liq_price_options(
                is_long, entry_price, abs_qty, equity_for_position
            )

        return None

    def _calc_liq_price_futures(
        self,
        is_long: bool,
        entry_price: float,
        quantity: float,
        equity_for_position: float,
    ) -> Optional[float]:
        """Liquidation price for CME futures (stock & crypto futures).

        For CME: Liquidation occurs when account equity falls below
        maintenance margin. Daily mark-to-market means P&L is settled daily.

        Liq price = entry_price - (equity_available - maint_margin) / (qty * multiplier) [LONG]
        Liq price = entry_price + (equity_available - maint_margin) / (qty * multiplier) [SHORT]
        """
        mc = self.market_config
        maint_margin = quantity * mc.maintenance_margin_rate if mc.is_margin_per_contract else 0
        multiplier = mc.contract_multiplier

        if quantity * multiplier == 0:
            return None

        # How much the price can move before equity = maintenance margin
        max_adverse_move = (equity_for_position - maint_margin) / (quantity * multiplier)

        if max_adverse_move < 0:
            # Already in liquidation territory
            return entry_price if is_long else entry_price

        if is_long:
            liq_price = entry_price - max_adverse_move
        else:
            liq_price = entry_price + max_adverse_move

        # Liquidation price can't be negative
        return max(0.0, liq_price)

    def _calc_liq_price_perpetual(
        self,
        is_long: bool,
        entry_price: float,
        quantity: float,
        equity_for_position: float,
        leverage: float,
    ) -> Optional[float]:
        """Liquidation price for crypto perpetual futures.

        Simplified formula (varies by exchange):
        For LONG: liq_price = entry_price × (1 - 1/leverage + maintenance_rate)
        For SHORT: liq_price = entry_price × (1 + 1/leverage - maintenance_rate)

        More accurate: accounts for wallet balance relative to position size.
        liq_price = entry_price - direction * (equity_for_position - maint_margin) / (qty * multiplier)
        """
        mc = self.market_config
        multiplier = mc.contract_multiplier

        if quantity * multiplier == 0 or leverage <= 0:
            return None

        notional = quantity * entry_price * multiplier
        maint_margin = notional * mc.maintenance_margin_rate

        # Max adverse move before liquidation
        denominator = quantity * multiplier
        if denominator == 0:
            return None

        max_adverse_move = (equity_for_position - maint_margin) / denominator

        if is_long:
            liq_price = entry_price - max_adverse_move
        else:
            liq_price = entry_price + max_adverse_move

        return max(0.0, liq_price)

    def _calc_liq_price_options(
        self,
        is_long: bool,
        entry_price: float,
        quantity: float,
        equity_for_position: float,
    ) -> Optional[float]:
        """Liquidation price for options positions.

        For defined-risk spreads (Iron Condors), max loss is predetermined.
        Liquidation in the traditional sense doesn't apply - the position
        has a defined max loss equal to (spread_width - credit) * contracts * multiplier.

        Returns None since options spreads don't have a liquidation price
        in the futures sense.
        """
        return None

    def calc_distance_to_liquidation_pct(
        self, current_price: float, liquidation_price: Optional[float]
    ) -> Optional[float]:
        """9. Distance to Liquidation Percent.

        = |current_price - liquidation_price| / current_price × 100
        """
        if liquidation_price is None or current_price <= 0:
            return None
        return abs(current_price - liquidation_price) / current_price * 100.0

    def calc_unrealized_pnl(
        self,
        side: str,
        entry_price: float,
        current_price: float,
        quantity: float,
    ) -> float:
        """10. Unrealized P&L.

        = (current_price - entry_price) × quantity × contract_multiplier × direction
        """
        if quantity <= 0 or entry_price <= 0 or current_price <= 0:
            return 0.0

        direction = 1.0 if side.lower() == "long" else -1.0
        multiplier = self.market_config.contract_multiplier
        return (current_price - entry_price) * abs(quantity) * multiplier * direction

    def calc_effective_leverage(
        self, total_notional: float, account_equity: float
    ) -> float:
        """11. Effective Leverage.

        = total_notional_value / account_equity
        Shows actual leverage exposure regardless of margin mode.
        """
        if account_equity <= 0:
            return float('inf') if total_notional > 0 else 0.0
        return total_notional / account_equity

    def calc_max_position_size(
        self, available_margin: float, current_price: float, leverage: Optional[float] = None
    ) -> float:
        """12. Max Additional Position Size.

        Given current available margin, how many more contracts/coins can be opened.

        For stock futures: available_margin / initial_margin_per_contract
        For crypto perps: (available_margin × leverage) / (price × multiplier)
        """
        mc = self.market_config

        if available_margin <= 0 or current_price <= 0:
            return 0.0

        if mc.is_margin_per_contract:
            if mc.initial_margin_rate <= 0:
                return 0.0
            return available_margin / mc.initial_margin_rate
        else:
            eff_leverage = leverage or self.bot_config.effective_leverage
            if mc.contract_multiplier <= 0:
                return 0.0
            # Notional capacity = available_margin × leverage
            notional_capacity = available_margin * eff_leverage
            # Quantity = notional / (price × multiplier)
            return notional_capacity / (current_price * mc.contract_multiplier)

    def calc_funding_cost_projection(
        self,
        notional_value: float,
        funding_rate: float,
        side: str,
        projection_days: int = 30,
    ) -> Tuple[float, float]:
        """13. Funding Cost Projection (perpetuals only).

        = notional_value × funding_rate × periods_per_day × projection_days

        Funding rate is positive: longs pay shorts
        Funding rate is negative: shorts pay longs

        Returns:
            Tuple of (daily_cost, projected_cost)
            Negative = you pay, Positive = you receive
        """
        mc = self.market_config
        if not mc.has_funding_rate or funding_rate is None:
            return (0.0, 0.0)

        if mc.funding_interval_hours <= 0:
            return (0.0, 0.0)

        periods_per_day = 24.0 / mc.funding_interval_hours
        is_long = side.lower() == "long"

        # Funding payment per period
        # Positive rate: longs pay shorts
        # If you're long and rate is positive, you pay
        direction = -1.0 if is_long else 1.0
        payment_per_period = notional_value * funding_rate * direction

        daily_cost = payment_per_period * periods_per_day
        projected_cost = daily_cost * projection_days

        return (daily_cost, projected_cost)

    # =========================================================================
    # AGGREGATE CALCULATIONS
    # =========================================================================

    def calculate_position_metrics(
        self,
        position: Dict[str, Any],
        account_equity: float,
        total_maint_margin_other: float = 0.0,
    ) -> PositionMarginMetrics:
        """Calculate all margin metrics for a single position.

        Args:
            position: Dict with keys: position_id, symbol, side, quantity,
                      entry_price, current_price, leverage (optional),
                      funding_rate (optional)
            account_equity: Total account equity
            total_maint_margin_other: Maintenance margin used by other positions

        Returns:
            PositionMarginMetrics with all calculated values
        """
        pos_id = position.get("position_id", "unknown")
        symbol = position.get("symbol", "")
        side = position.get("side", "long")
        qty = abs(float(position.get("quantity", 0)))
        entry = float(position.get("entry_price", 0))
        current = float(position.get("current_price", 0) or entry)
        leverage = position.get("leverage")
        funding_rate = position.get("funding_rate")

        notional = self.calc_notional_value(qty, current)
        initial_margin = self.calc_initial_margin(qty, current, leverage)
        maint_margin = self.calc_maintenance_margin(qty, current)
        unrealized = self.calc_unrealized_pnl(side, entry, current, qty)
        liq_price = self.calc_liquidation_price(
            side, entry, qty, account_equity, total_maint_margin_other, leverage
        )
        dist_to_liq = self.calc_distance_to_liquidation_pct(current, liq_price)

        # Funding projections (perps only)
        funding_daily = None
        funding_30d = None
        if self.market_config.has_funding_rate and funding_rate is not None:
            funding_daily, funding_30d = self.calc_funding_cost_projection(
                notional, funding_rate, side, projection_days=30
            )

        return PositionMarginMetrics(
            position_id=pos_id,
            bot_name=self.bot_config.bot_name,
            symbol=symbol,
            side=side,
            quantity=qty,
            entry_price=entry,
            current_price=current,
            contract_multiplier=self.market_config.contract_multiplier,
            notional_value=notional,
            initial_margin_required=initial_margin,
            maintenance_margin_required=maint_margin,
            unrealized_pnl=unrealized,
            liquidation_price=liq_price,
            distance_to_liq_pct=dist_to_liq,
            funding_rate=funding_rate,
            funding_cost_projection_daily=funding_daily,
            funding_cost_projection_30d=funding_30d,
            market_type=self.market_config.market_type.value,
            exchange=self.market_config.exchange,
            timestamp=datetime.now(CENTRAL_TZ),
        )

    def calculate_account_metrics(
        self,
        account_equity: float,
        positions: List[Dict[str, Any]],
    ) -> AccountMarginMetrics:
        """Calculate aggregate margin metrics for a bot's account.

        Args:
            account_equity: Total account equity (balance + unrealized P&L)
            positions: List of position dicts, each with:
                position_id, symbol, side, quantity, entry_price,
                current_price, leverage (optional), funding_rate (optional)

        Returns:
            AccountMarginMetrics with all aggregated values
        """
        now = datetime.now(CENTRAL_TZ)

        if not positions:
            return AccountMarginMetrics(
                bot_name=self.bot_config.bot_name,
                account_equity=account_equity,
                total_margin_used=0.0,
                available_margin=account_equity,
                margin_usage_pct=0.0,
                margin_ratio=float('inf'),
                effective_leverage=0.0,
                max_additional_notional=account_equity,
                total_unrealized_pnl=0.0,
                total_notional_value=0.0,
                position_count=0,
                health_status="HEALTHY",
                positions=[],
                warning_threshold=self.bot_config.warning_threshold_pct,
                danger_threshold=self.bot_config.danger_threshold_pct,
                critical_threshold=self.bot_config.critical_threshold_pct,
                market_type=self.market_config.market_type.value,
                timestamp=now,
            )

        # First pass: calculate total maintenance margin for liquidation calcs
        total_maint = 0.0
        for pos in positions:
            qty = abs(float(pos.get("quantity", 0)))
            price = float(pos.get("current_price", 0) or pos.get("entry_price", 0))
            total_maint += self.calc_maintenance_margin(qty, price)

        # Second pass: calculate per-position metrics
        position_metrics = []
        total_margin_used = 0.0
        total_notional = 0.0
        total_unrealized = 0.0
        total_funding_daily = 0.0
        total_funding_30d = 0.0

        for pos in positions:
            qty = abs(float(pos.get("quantity", 0)))
            price = float(pos.get("current_price", 0) or pos.get("entry_price", 0))

            # Other positions' maintenance margin (for liquidation calc)
            this_maint = self.calc_maintenance_margin(qty, price)
            other_maint = total_maint - this_maint

            metrics = self.calculate_position_metrics(
                pos, account_equity, other_maint
            )
            position_metrics.append(metrics)

            total_margin_used += metrics.initial_margin_required
            total_notional += metrics.notional_value
            total_unrealized += metrics.unrealized_pnl

            if metrics.funding_cost_projection_daily is not None:
                total_funding_daily += metrics.funding_cost_projection_daily
            if metrics.funding_cost_projection_30d is not None:
                total_funding_30d += metrics.funding_cost_projection_30d

        available = self.calc_available_margin(account_equity, total_margin_used)
        usage_pct = self.calc_margin_usage_pct(total_margin_used, account_equity)
        ratio = self.calc_margin_ratio(account_equity, total_maint)
        eff_leverage = self.calc_effective_leverage(total_notional, account_equity)

        # Max additional position capacity
        max_additional = 0.0
        if available > 0:
            # Use a representative price (average of current positions)
            avg_price = (
                total_notional / (sum(
                    abs(float(p.get("quantity", 0))) * self.market_config.contract_multiplier
                    for p in positions
                ) or 1)
            )
            if avg_price > 0:
                max_additional = self.calc_max_position_size(available, avg_price)

        # Determine health status
        health = self._determine_health_status(usage_pct)

        return AccountMarginMetrics(
            bot_name=self.bot_config.bot_name,
            account_equity=account_equity,
            total_margin_used=total_margin_used,
            available_margin=available,
            margin_usage_pct=usage_pct,
            margin_ratio=ratio,
            effective_leverage=eff_leverage,
            max_additional_notional=max_additional,
            total_unrealized_pnl=total_unrealized,
            total_notional_value=total_notional,
            position_count=len(positions),
            health_status=health,
            positions=position_metrics,
            total_funding_cost_daily=total_funding_daily if total_funding_daily != 0 else None,
            total_funding_cost_30d=total_funding_30d if total_funding_30d != 0 else None,
            warning_threshold=self.bot_config.warning_threshold_pct,
            danger_threshold=self.bot_config.danger_threshold_pct,
            critical_threshold=self.bot_config.critical_threshold_pct,
            market_type=self.market_config.market_type.value,
            timestamp=now,
        )

    # =========================================================================
    # PRE-TRADE MARGIN CHECK
    # =========================================================================

    def check_pre_trade(
        self,
        account_equity: float,
        existing_positions: List[Dict[str, Any]],
        proposed_trade: Dict[str, Any],
    ) -> PreTradeCheckResult:
        """Check if a proposed trade can be opened within margin limits.

        This is the highest-value safety feature. Call BEFORE placing any order.

        Args:
            account_equity: Current account equity
            existing_positions: List of current open positions
            proposed_trade: Dict with: symbol, side, quantity, entry_price,
                           leverage (optional)

        Returns:
            PreTradeCheckResult with approval status and details
        """
        violations = []

        # Calculate current margin state
        current_margin_used = self.calc_margin_used(existing_positions)
        current_available = self.calc_available_margin(account_equity, current_margin_used)

        # Calculate margin for proposed trade
        qty = abs(float(proposed_trade.get("quantity", 0)))
        price = float(proposed_trade.get("entry_price", 0))
        side = proposed_trade.get("side", "long")
        leverage = proposed_trade.get("leverage")

        trade_margin = self.calc_initial_margin(qty, price, leverage)
        trade_notional = self.calc_notional_value(qty, price)

        # New totals if trade is placed
        new_margin_used = current_margin_used + trade_margin
        new_available = account_equity - new_margin_used
        new_usage_pct = self.calc_margin_usage_pct(new_margin_used, account_equity)

        # New effective leverage
        current_notional = sum(
            self.calc_notional_value(
                abs(float(p.get("quantity", 0))),
                float(p.get("current_price", 0) or p.get("entry_price", 0))
            )
            for p in existing_positions
        )
        new_total_notional = current_notional + trade_notional
        new_eff_leverage = self.calc_effective_leverage(new_total_notional, account_equity)

        # Calculate liquidation price for the new position
        total_maint_other = sum(
            self.calc_maintenance_margin(
                abs(float(p.get("quantity", 0))),
                float(p.get("current_price", 0) or p.get("entry_price", 0))
            )
            for p in existing_positions
        )
        liq_price = self.calc_liquidation_price(
            side, price, qty, account_equity, total_maint_other, leverage
        )
        dist_to_liq = self.calc_distance_to_liquidation_pct(price, liq_price)

        # --- HARD LIMIT CHECKS ---

        # Check 1: Sufficient margin
        if trade_margin > current_available:
            violations.append(
                f"Insufficient margin: need ${trade_margin:.2f}, "
                f"have ${current_available:.2f}"
            )

        # Check 2: Max margin usage
        max_usage = self.bot_config.max_margin_usage_pct
        if new_usage_pct > max_usage:
            violations.append(
                f"Margin usage would be {new_usage_pct:.1f}%, "
                f"exceeds max {max_usage:.1f}%"
            )

        # Check 3: Liquidation distance
        min_liq_dist = self.bot_config.min_liquidation_distance_pct
        if dist_to_liq is not None and dist_to_liq < min_liq_dist:
            violations.append(
                f"Liquidation distance {dist_to_liq:.2f}% "
                f"below minimum {min_liq_dist:.1f}%"
            )

        # Check 4: Max effective leverage
        max_lev = self.bot_config.max_effective_leverage
        if new_eff_leverage > max_lev:
            violations.append(
                f"Effective leverage would be {new_eff_leverage:.1f}x, "
                f"exceeds max {max_lev:.1f}x"
            )

        # Check 5: Single position margin concentration
        max_single_pct = self.bot_config.max_single_position_margin_pct
        if account_equity > 0:
            position_margin_pct = (trade_margin / account_equity) * 100
            if position_margin_pct > max_single_pct:
                violations.append(
                    f"Single position uses {position_margin_pct:.1f}% of equity, "
                    f"exceeds max {max_single_pct:.1f}%"
                )

        approved = len(violations) == 0
        reason = "Trade approved" if approved else "; ".join(violations)

        return PreTradeCheckResult(
            approved=approved,
            reason=reason,
            available_margin=current_available,
            margin_required=trade_margin,
            new_margin_usage_pct=new_usage_pct,
            new_effective_leverage=new_eff_leverage,
            liquidation_price=liq_price,
            distance_to_liq_pct=dist_to_liq,
            violations=violations,
        )

    # =========================================================================
    # SCENARIO SIMULATION
    # =========================================================================

    def simulate_price_move(
        self,
        account_equity: float,
        positions: List[Dict[str, Any]],
        price_change_pct: float,
    ) -> ScenarioResult:
        """Simulate what happens if prices move by a given percentage.

        Args:
            account_equity: Current account equity
            positions: Current open positions
            price_change_pct: Price change to simulate (e.g., -5.0 for 5% drop)

        Returns:
            ScenarioResult with projected margin impact
        """
        if not positions:
            return ScenarioResult(
                scenario_description=f"Price move {price_change_pct:+.1f}%",
                current_margin_usage_pct=0.0,
                projected_margin_usage_pct=0.0,
                current_liq_distance_pct=None,
                projected_liq_distance_pct=None,
                would_trigger_liquidation=False,
                would_trigger_margin_call=False,
            )

        # Current state
        current_metrics = self.calculate_account_metrics(account_equity, positions)

        # Simulate price change - create modified positions
        factor = 1.0 + (price_change_pct / 100.0)
        modified_positions = []
        for pos in positions:
            mod_pos = dict(pos)
            current_price = float(pos.get("current_price", 0) or pos.get("entry_price", 0))
            mod_pos["current_price"] = current_price * factor
            modified_positions.append(mod_pos)

        # Calculate P&L impact on equity
        pnl_change = 0.0
        for orig, mod in zip(positions, modified_positions):
            side = orig.get("side", "long")
            entry = float(orig.get("entry_price", 0))
            qty = abs(float(orig.get("quantity", 0)))
            orig_price = float(orig.get("current_price", 0) or entry)
            new_price = float(mod["current_price"])

            orig_pnl = self.calc_unrealized_pnl(side, entry, orig_price, qty)
            new_pnl = self.calc_unrealized_pnl(side, entry, new_price, qty)
            pnl_change += (new_pnl - orig_pnl)

        projected_equity = account_equity + pnl_change
        projected_metrics = self.calculate_account_metrics(projected_equity, modified_positions)

        # Find closest liquidation
        min_liq_dist_current = None
        min_liq_dist_projected = None
        for pm in current_metrics.positions:
            if pm.distance_to_liq_pct is not None:
                if min_liq_dist_current is None or pm.distance_to_liq_pct < min_liq_dist_current:
                    min_liq_dist_current = pm.distance_to_liq_pct
        for pm in projected_metrics.positions:
            if pm.distance_to_liq_pct is not None:
                if min_liq_dist_projected is None or pm.distance_to_liq_pct < min_liq_dist_projected:
                    min_liq_dist_projected = pm.distance_to_liq_pct

        would_liquidate = (
            min_liq_dist_projected is not None and min_liq_dist_projected <= 0
        ) or projected_equity <= 0

        would_margin_call = projected_metrics.margin_ratio < (
            self.market_config.margin_call_threshold_pct / 100.0
        )

        return ScenarioResult(
            scenario_description=f"Price move {price_change_pct:+.1f}%",
            current_margin_usage_pct=current_metrics.margin_usage_pct,
            projected_margin_usage_pct=projected_metrics.margin_usage_pct,
            current_liq_distance_pct=min_liq_dist_current,
            projected_liq_distance_pct=min_liq_dist_projected,
            would_trigger_liquidation=would_liquidate,
            would_trigger_margin_call=would_margin_call,
            max_adverse_move_pct=min_liq_dist_current,
        )

    def simulate_add_contracts(
        self,
        account_equity: float,
        positions: List[Dict[str, Any]],
        additional_quantity: float,
        price: float,
        side: str = "long",
    ) -> ScenarioResult:
        """Simulate adding more contracts/coins to see margin impact."""
        current_metrics = self.calculate_account_metrics(account_equity, positions)

        # Create the proposed position
        proposed = {
            "position_id": "simulated",
            "symbol": "simulated",
            "side": side,
            "quantity": additional_quantity,
            "entry_price": price,
            "current_price": price,
        }

        all_positions = positions + [proposed]
        projected_metrics = self.calculate_account_metrics(account_equity, all_positions)

        min_liq_current = None
        min_liq_projected = None
        for pm in current_metrics.positions:
            if pm.distance_to_liq_pct is not None:
                if min_liq_current is None or pm.distance_to_liq_pct < min_liq_current:
                    min_liq_current = pm.distance_to_liq_pct
        for pm in projected_metrics.positions:
            if pm.distance_to_liq_pct is not None:
                if min_liq_projected is None or pm.distance_to_liq_pct < min_liq_projected:
                    min_liq_projected = pm.distance_to_liq_pct

        return ScenarioResult(
            scenario_description=f"Add {additional_quantity} {side} @ {price}",
            current_margin_usage_pct=current_metrics.margin_usage_pct,
            projected_margin_usage_pct=projected_metrics.margin_usage_pct,
            current_liq_distance_pct=min_liq_current,
            projected_liq_distance_pct=min_liq_projected,
            would_trigger_liquidation=(
                min_liq_projected is not None and min_liq_projected <= 0
            ),
            would_trigger_margin_call=projected_metrics.margin_ratio < 1.2,
        )

    def simulate_leverage_change(
        self,
        account_equity: float,
        positions: List[Dict[str, Any]],
        new_leverage: float,
    ) -> ScenarioResult:
        """Simulate changing leverage to see margin impact."""
        current_metrics = self.calculate_account_metrics(account_equity, positions)

        # Modify all positions with new leverage
        modified = [dict(p) for p in positions]
        for m in modified:
            m["leverage"] = new_leverage

        projected_metrics = self.calculate_account_metrics(account_equity, modified)

        min_liq_current = None
        min_liq_projected = None
        for pm in current_metrics.positions:
            if pm.distance_to_liq_pct is not None:
                if min_liq_current is None or pm.distance_to_liq_pct < min_liq_current:
                    min_liq_current = pm.distance_to_liq_pct
        for pm in projected_metrics.positions:
            if pm.distance_to_liq_pct is not None:
                if min_liq_projected is None or pm.distance_to_liq_pct < min_liq_projected:
                    min_liq_projected = pm.distance_to_liq_pct

        return ScenarioResult(
            scenario_description=f"Change leverage to {new_leverage}x",
            current_margin_usage_pct=current_metrics.margin_usage_pct,
            projected_margin_usage_pct=projected_metrics.margin_usage_pct,
            current_liq_distance_pct=min_liq_current,
            projected_liq_distance_pct=min_liq_projected,
            would_trigger_liquidation=(
                min_liq_projected is not None and min_liq_projected <= 0
            ),
            would_trigger_margin_call=projected_metrics.margin_ratio < 1.2,
        )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _determine_health_status(self, margin_usage_pct: float) -> str:
        """Determine health status based on margin usage percentage."""
        if margin_usage_pct >= self.bot_config.critical_threshold_pct:
            return "CRITICAL"
        elif margin_usage_pct >= self.bot_config.danger_threshold_pct:
            return "DANGER"
        elif margin_usage_pct >= self.bot_config.warning_threshold_pct:
            return "WARNING"
        return "HEALTHY"

    @staticmethod
    def health_status_to_color(status: str) -> str:
        """Map health status to display color."""
        return {
            "HEALTHY": "green",
            "WARNING": "yellow",
            "DANGER": "orange",
            "CRITICAL": "red",
        }.get(status, "gray")
