"""
Margin Calculator for all market types.

Pure calculation module - takes inputs, returns results.
No API calls, no database access, no side effects.
The calling bot provides current prices, positions, and equity.
"""

from typing import Dict, Any, Optional


# =============================================================================
# HEALTH STATUS THRESHOLDS
# =============================================================================

def _health_from_usage(usage_pct: float) -> str:
    """Determine margin health from usage percentage."""
    if usage_pct >= 85:
        return "CRITICAL"
    if usage_pct >= 70:
        return "DANGER"
    if usage_pct >= 50:
        return "WARNING"
    return "HEALTHY"


# =============================================================================
# CME / STOCK / CRYPTO FUTURES (fixed $ margin per contract)
# =============================================================================

class MarginCalculator:
    """Universal margin calculator for all market types."""

    @staticmethod
    def calculate_futures_margin(
        entry_price: float,
        current_price: float,
        contracts: int,
        side: str,
        point_value: float,
        initial_margin_per_contract: float,
        maintenance_margin_per_contract: float,
        account_equity: float,
    ) -> Dict[str, Any]:
        """Calculate margin metrics for CME-style futures (fixed $ per contract).

        Args:
            entry_price: Position entry price.
            current_price: Current market price.
            contracts: Number of contracts held.
            side: "long" or "short".
            point_value: Dollar value per full point move per contract
                         (e.g. $5 for MES, 0.1 for /MBT).
            initial_margin_per_contract: CME initial margin requirement.
            maintenance_margin_per_contract: CME maintenance margin requirement.
            account_equity: Total account equity (capital + realized P&L).

        Returns:
            Dict with all margin metrics.
        """
        direction = 1 if side.lower() in ("long", "buy") else -1

        # Notional value: price * point_value * contracts
        notional_value = current_price * point_value * contracts

        # Margin requirements
        initial_margin_required = initial_margin_per_contract * contracts
        maintenance_margin_required = maintenance_margin_per_contract * contracts

        # Unrealized P&L: (current - entry) * point_value * direction * contracts
        unrealized_pnl = (current_price - entry_price) * point_value * direction * contracts

        # Effective equity (including unrealized)
        effective_equity = account_equity + unrealized_pnl
        margin_available = max(0.0, effective_equity - initial_margin_required)
        margin_usage_pct = (initial_margin_required / effective_equity * 100) if effective_equity > 0 else 100.0
        effective_leverage = (notional_value / effective_equity) if effective_equity > 0 else 0.0

        # Liquidation price: where equity drops to maintenance margin
        # For LONG: entry - ((equity - maint_margin) / (contracts * point_value))
        # For SHORT: entry + ((equity - maint_margin) / (contracts * point_value))
        equity_buffer = effective_equity - maintenance_margin_required
        price_buffer = equity_buffer / (contracts * point_value) if (contracts * point_value) > 0 else 0

        if direction == 1:
            liquidation_price = entry_price - price_buffer
        else:
            liquidation_price = entry_price + price_buffer

        # Distance to liquidation
        if current_price > 0:
            distance_to_liq_pct = abs(current_price - liquidation_price) / current_price * 100
            distance_to_liq_usd = abs(current_price - liquidation_price) * point_value * contracts
        else:
            distance_to_liq_pct = 0.0
            distance_to_liq_usd = 0.0

        health = _health_from_usage(margin_usage_pct)
        # Override to CRITICAL if close to liquidation
        if distance_to_liq_pct < 5 and contracts > 0:
            health = "CRITICAL"

        return {
            "notional_value": round(notional_value, 2),
            "initial_margin_required": round(initial_margin_required, 2),
            "maintenance_margin_required": round(maintenance_margin_required, 2),
            "margin_used": round(initial_margin_required, 2),
            "available_margin": round(margin_available, 2),
            "margin_usage_pct": round(margin_usage_pct, 1),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "effective_leverage": round(effective_leverage, 2),
            "liquidation_price": round(liquidation_price, 2),
            "distance_to_liquidation_pct": round(distance_to_liq_pct, 1),
            "distance_to_liquidation_usd": round(distance_to_liq_usd, 2),
            "margin_health": health,
        }

    @staticmethod
    def calculate_perpetual_margin(
        entry_price: float,
        current_price: float,
        quantity: float,
        side: str,
        leverage: float,
        margin_mode: str,
        maintenance_margin_rate: float,
        account_equity: float,
        position_margin: Optional[float] = None,
        funding_rate: float = 0.0,
        funding_interval_hours: float = 8.0,
    ) -> Dict[str, Any]:
        """Calculate margin metrics for perpetual futures (percentage-based).

        Args:
            entry_price: Position entry price.
            current_price: Current market price.
            quantity: Position size in asset units (e.g. 0.5 BTC).
            side: "long" or "short".
            leverage: Effective leverage (e.g. 10 for 10x).
            margin_mode: "isolated" or "cross".
            maintenance_margin_rate: Exchange maintenance margin rate (e.g. 0.004).
            account_equity: Total account equity.
            position_margin: For isolated mode, the margin allocated to this position.
                            If None, calculated as notional / leverage.
            funding_rate: Current funding rate per interval (e.g. 0.0001 = 0.01%).
            funding_interval_hours: Hours between funding (usually 8).

        Returns:
            Dict with all margin metrics plus funding projections.
        """
        direction = 1 if side.lower() in ("long", "buy") else -1

        # Notional value
        notional_value = current_price * quantity

        # Initial margin (what you put up to open)
        initial_margin_rate = 1.0 / leverage if leverage > 0 else 1.0
        initial_margin_required = notional_value * initial_margin_rate

        # Maintenance margin
        maintenance_margin_required = notional_value * maintenance_margin_rate

        # Position margin (for isolated mode)
        if position_margin is None:
            position_margin = initial_margin_required

        # Unrealized P&L
        unrealized_pnl = (current_price - entry_price) * quantity * direction

        # Effective equity depends on margin mode
        if margin_mode.lower() == "isolated":
            effective_equity = position_margin + unrealized_pnl
            margin_base = position_margin
        else:
            # Cross mode: entire account is margin
            effective_equity = account_equity + unrealized_pnl
            margin_base = account_equity

        margin_available = max(0.0, effective_equity - maintenance_margin_required)
        margin_usage_pct = (initial_margin_required / margin_base * 100) if margin_base > 0 else 100.0
        effective_leverage_calc = (notional_value / effective_equity) if effective_equity > 0 else 0.0

        # Liquidation price for perpetuals (simplified)
        # LONG isolated: entry * (1 - initial_margin_rate + maintenance_margin_rate)
        # SHORT isolated: entry * (1 + initial_margin_rate - maintenance_margin_rate)
        if margin_mode.lower() == "isolated":
            if direction == 1:
                liquidation_price = entry_price * (1 - initial_margin_rate + maintenance_margin_rate)
            else:
                liquidation_price = entry_price * (1 + initial_margin_rate - maintenance_margin_rate)
        else:
            # Cross mode: use account equity buffer
            equity_buffer = account_equity - maintenance_margin_required
            price_buffer = (equity_buffer / quantity) if quantity > 0 else 0
            if direction == 1:
                liquidation_price = entry_price - price_buffer
            else:
                liquidation_price = entry_price + price_buffer

        # Distance to liquidation
        if current_price > 0:
            distance_to_liq_pct = abs(current_price - liquidation_price) / current_price * 100
        else:
            distance_to_liq_pct = 0.0

        # Funding cost projections
        # Funding rate is applied to notional value. Positive rate: longs pay shorts.
        notional_at_entry = entry_price * quantity
        funding_cost_per_interval = notional_at_entry * funding_rate * direction * -1
        intervals_per_day = 24.0 / funding_interval_hours if funding_interval_hours > 0 else 3.0
        funding_cost_daily = funding_cost_per_interval * intervals_per_day
        funding_cost_30d = funding_cost_daily * 30

        health = _health_from_usage(margin_usage_pct)
        if distance_to_liq_pct < 5 and quantity > 0:
            health = "CRITICAL"

        return {
            "notional_value": round(notional_value, 2),
            "initial_margin_required": round(initial_margin_required, 2),
            "maintenance_margin_required": round(maintenance_margin_required, 2),
            "margin_used": round(initial_margin_required, 2),
            "available_margin": round(margin_available, 2),
            "margin_usage_pct": round(margin_usage_pct, 1),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "effective_leverage": round(effective_leverage_calc, 2),
            "liquidation_price": round(liquidation_price, 2),
            "distance_to_liquidation_pct": round(distance_to_liq_pct, 1),
            "margin_health": health,
            # Perpetual-specific fields
            "leverage": leverage,
            "margin_mode": margin_mode,
            "funding_rate": funding_rate,
            "funding_cost_8h": round(funding_cost_per_interval, 4),
            "funding_cost_daily": round(funding_cost_daily, 4),
            "funding_cost_30d_projected": round(funding_cost_30d, 2),
        }

    @staticmethod
    def aggregate_positions(
        position_margins: list,
        account_equity: float,
        market_type: str,
    ) -> Dict[str, Any]:
        """Aggregate margin metrics across multiple positions.

        Args:
            position_margins: List of dicts from calculate_*_margin().
            account_equity: Total account equity.
            market_type: "stock_futures", "crypto_futures", or "crypto_perp".

        Returns:
            Summary dict with totals and overall health.
        """
        if not position_margins:
            return {
                "has_positions": False,
                "account_equity": round(account_equity, 2),
                "margin_used": 0,
                "available_margin": round(account_equity, 2),
                "margin_usage_pct": 0.0,
                "total_unrealized_pnl": 0.0,
                "total_notional": 0.0,
                "effective_leverage": 0.0,
                "position_count": 0,
                "margin_health": "HEALTHY",
                "positions": [],
                "market_type": market_type,
            }

        total_margin_used = sum(p["initial_margin_required"] for p in position_margins)
        total_maintenance = sum(p["maintenance_margin_required"] for p in position_margins)
        total_unrealized = sum(p["unrealized_pnl"] for p in position_margins)
        total_notional = sum(p["notional_value"] for p in position_margins)
        total_funding_daily = None
        total_funding_30d = None

        if market_type == "crypto_perp":
            total_funding_daily = sum(p.get("funding_cost_daily", 0) for p in position_margins)
            total_funding_30d = sum(p.get("funding_cost_30d_projected", 0) for p in position_margins)

        effective_equity = account_equity + total_unrealized
        margin_available = max(0.0, effective_equity - total_margin_used)
        margin_usage_pct = (total_margin_used / effective_equity * 100) if effective_equity > 0 else 100.0
        effective_leverage = (total_notional / effective_equity) if effective_equity > 0 else 0.0

        # Overall health is the worst of individual positions
        health = _health_from_usage(margin_usage_pct)
        for p in position_margins:
            if p.get("margin_health") == "CRITICAL":
                health = "CRITICAL"
                break
            if p.get("margin_health") == "DANGER" and health not in ("CRITICAL",):
                health = "DANGER"

        result = {
            "has_positions": True,
            "account_equity": round(effective_equity, 2),
            "margin_used": round(total_margin_used, 2),
            "maintenance_margin": round(total_maintenance, 2),
            "available_margin": round(margin_available, 2),
            "margin_usage_pct": round(margin_usage_pct, 1),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "total_notional": round(total_notional, 2),
            "effective_leverage": round(effective_leverage, 2),
            "position_count": len(position_margins),
            "margin_health": health,
            "positions": position_margins,
            "market_type": market_type,
        }

        if total_funding_daily is not None:
            result["total_funding_cost_daily"] = round(total_funding_daily, 4)
            result["total_funding_cost_30d"] = round(total_funding_30d, 2)

        return result
