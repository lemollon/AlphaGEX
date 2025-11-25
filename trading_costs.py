"""
Trading Costs Model - Slippage and Commission Calculator
=========================================================

This module implements realistic trading cost modeling for options trading.

Key Features:
1. Slippage based on bid/ask spread and order size
2. Commission per contract (configurable)
3. Market impact estimation for large orders
4. SPX vs ETF-specific cost profiles

CRITICAL: Without this, backtests overstate returns by 15-30%
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class SymbolType(Enum):
    ETF = "etf"           # SPY, QQQ - 100 shares per contract
    INDEX = "index"       # SPX, NDX - cash settled, different multiplier
    STOCK = "stock"       # Individual stocks


@dataclass
class TradingCostsConfig:
    """Configuration for trading costs"""

    # Commission per contract (typical for retail brokers)
    # $0 for commission-free brokers, $0.65 typical, $1.00+ for full service
    commission_per_contract: float = 0.65

    # Minimum commission per order
    min_commission: float = 0.0

    # Slippage model parameters
    # For buying: pay above mid by this fraction of spread
    # For selling: receive below mid by this fraction of spread
    spread_capture_pct: float = 0.5  # 50% means you get mid-price (optimistic)

    # Market impact for larger orders (basis points per contract)
    # SPY options have deep liquidity, SPX slightly less
    market_impact_bp_per_contract: float = 0.1

    # Maximum market impact cap (basis points)
    max_market_impact_bp: float = 50.0

    # Regulatory fees (per contract)
    # SEC fee: ~$0.02 per $1000 of principal (on sells)
    # FINRA TAF: $0.000119 per share traded (applies to options)
    # OCC clearing fee: ~$0.02-0.05 per contract
    regulatory_fee_per_contract: float = 0.05


# Default configurations for different trader types
RETAIL_COSTS = TradingCostsConfig(
    commission_per_contract=0.65,
    spread_capture_pct=0.4,  # Retail often gets worse fills
    market_impact_bp_per_contract=0.2,
    regulatory_fee_per_contract=0.05
)

PAPER_TRADING_COSTS = TradingCostsConfig(
    commission_per_contract=0.50,  # Simulate some friction
    spread_capture_pct=0.5,  # Assume mid-price for paper
    market_impact_bp_per_contract=0.1,
    regulatory_fee_per_contract=0.03
)

INSTITUTIONAL_COSTS = TradingCostsConfig(
    commission_per_contract=0.10,  # Volume discounts
    spread_capture_pct=0.6,  # Better fills from algos
    market_impact_bp_per_contract=0.05,
    regulatory_fee_per_contract=0.02
)

# SPX-specific costs (typically higher spreads)
SPX_COSTS = TradingCostsConfig(
    commission_per_contract=0.65,
    spread_capture_pct=0.45,  # SPX has wider spreads
    market_impact_bp_per_contract=0.15,
    regulatory_fee_per_contract=0.05
)


class TradingCostsCalculator:
    """
    Calculate realistic trading costs for options trades.

    This MUST be used for all trade executions to get accurate P&L.
    """

    def __init__(self, config: TradingCostsConfig = None):
        self.config = config or PAPER_TRADING_COSTS

    def calculate_entry_price(
        self,
        bid: float,
        ask: float,
        contracts: int,
        side: OrderSide = OrderSide.BUY,
        symbol_type: SymbolType = SymbolType.ETF
    ) -> Tuple[float, Dict]:
        """
        Calculate the realistic entry price including slippage.

        For BUYING options:
        - You pay somewhere between mid and ask
        - Larger orders incur more slippage

        For SELLING options (writing/closing):
        - You receive somewhere between bid and mid
        - Larger orders get worse prices

        Args:
            bid: Best bid price
            ask: Best ask price
            contracts: Number of contracts
            side: BUY or SELL
            symbol_type: ETF, INDEX, or STOCK

        Returns:
            (execution_price, cost_breakdown)
        """
        if bid <= 0 or ask <= 0:
            return 0.0, {'error': 'Invalid bid/ask prices'}

        mid = (bid + ask) / 2
        spread = ask - bid
        spread_pct = (spread / mid * 100) if mid > 0 else 0

        # Calculate base slippage from spread
        if side == OrderSide.BUY:
            # Buying: pay above mid
            # spread_capture_pct of 0.5 = mid price
            # spread_capture_pct of 0.4 = 60% toward ask
            spread_slippage = spread * (1 - self.config.spread_capture_pct)
            base_price = mid + (spread_slippage / 2)
        else:
            # Selling: receive below mid
            spread_slippage = spread * (1 - self.config.spread_capture_pct)
            base_price = mid - (spread_slippage / 2)

        # Calculate market impact for size
        market_impact_bp = min(
            contracts * self.config.market_impact_bp_per_contract,
            self.config.max_market_impact_bp
        )
        market_impact_pct = market_impact_bp / 10000

        if side == OrderSide.BUY:
            market_impact = base_price * market_impact_pct
            execution_price = base_price + market_impact
        else:
            market_impact = base_price * market_impact_pct
            execution_price = base_price - market_impact

        # Ensure price stays within bid-ask (no price improvement assumption)
        if side == OrderSide.BUY:
            execution_price = min(execution_price, ask * 1.01)  # Max 1% over ask
        else:
            execution_price = max(execution_price, bid * 0.99)  # Min 1% under bid

        # Calculate total slippage from mid
        slippage = abs(execution_price - mid)
        slippage_pct = (slippage / mid * 100) if mid > 0 else 0

        cost_breakdown = {
            'bid': bid,
            'ask': ask,
            'mid': mid,
            'spread': spread,
            'spread_pct': spread_pct,
            'spread_slippage': spread_slippage / 2,
            'market_impact_bp': market_impact_bp,
            'market_impact_dollars': market_impact,
            'execution_price': execution_price,
            'slippage_from_mid': slippage,
            'slippage_pct': slippage_pct,
            'side': side.value
        }

        return execution_price, cost_breakdown

    def calculate_commission(self, contracts: int) -> Dict:
        """
        Calculate commission for a trade.

        Args:
            contracts: Number of contracts

        Returns:
            Commission breakdown dict
        """
        base_commission = contracts * self.config.commission_per_contract
        commission = max(base_commission, self.config.min_commission)
        regulatory_fees = contracts * self.config.regulatory_fee_per_contract

        total = commission + regulatory_fees

        return {
            'base_commission': commission,
            'regulatory_fees': regulatory_fees,
            'total_commission': total,
            'per_contract': total / contracts if contracts > 0 else 0
        }

    def calculate_total_entry_cost(
        self,
        bid: float,
        ask: float,
        contracts: int,
        side: OrderSide = OrderSide.BUY,
        symbol_type: SymbolType = SymbolType.ETF,
        multiplier: int = 100
    ) -> Dict:
        """
        Calculate total cost to enter a position including all fees.

        Args:
            bid: Best bid price
            ask: Best ask price
            contracts: Number of contracts
            side: BUY or SELL
            symbol_type: ETF, INDEX, or STOCK
            multiplier: Contract multiplier (100 for most, 100 for SPX)

        Returns:
            Complete cost breakdown
        """
        # Get execution price with slippage
        execution_price, slippage_breakdown = self.calculate_entry_price(
            bid, ask, contracts, side, symbol_type
        )

        if 'error' in slippage_breakdown:
            return slippage_breakdown

        # Get commissions
        commission_breakdown = self.calculate_commission(contracts)

        # Calculate total premium
        premium = execution_price * contracts * multiplier

        # Total cost
        total_cost = premium + commission_breakdown['total_commission']

        # Cost per contract (for easy comparison)
        cost_per_contract = total_cost / contracts if contracts > 0 else 0

        return {
            'execution_price': execution_price,
            'theoretical_mid': slippage_breakdown['mid'],
            'slippage': slippage_breakdown,
            'commission': commission_breakdown,
            'premium': premium,
            'total_cost': total_cost,
            'cost_per_contract': cost_per_contract,
            'multiplier': multiplier,
            'contracts': contracts,
            'side': side.value
        }

    def calculate_exit_proceeds(
        self,
        bid: float,
        ask: float,
        contracts: int,
        entry_side: OrderSide,
        symbol_type: SymbolType = SymbolType.ETF,
        multiplier: int = 100
    ) -> Dict:
        """
        Calculate proceeds from closing a position.

        Args:
            bid: Current best bid
            ask: Current best ask
            contracts: Number of contracts to close
            entry_side: Original entry side (determines exit side)
            symbol_type: ETF, INDEX, or STOCK
            multiplier: Contract multiplier

        Returns:
            Complete proceeds breakdown
        """
        # Exit is opposite of entry
        exit_side = OrderSide.SELL if entry_side == OrderSide.BUY else OrderSide.BUY

        # Get execution price with slippage
        execution_price, slippage_breakdown = self.calculate_entry_price(
            bid, ask, contracts, exit_side, symbol_type
        )

        if 'error' in slippage_breakdown:
            return slippage_breakdown

        # Get commissions (always pay commission on exit too)
        commission_breakdown = self.calculate_commission(contracts)

        # Calculate gross proceeds
        gross_proceeds = execution_price * contracts * multiplier

        # Net proceeds after commission
        net_proceeds = gross_proceeds - commission_breakdown['total_commission']

        return {
            'execution_price': execution_price,
            'theoretical_mid': slippage_breakdown['mid'],
            'slippage': slippage_breakdown,
            'commission': commission_breakdown,
            'gross_proceeds': gross_proceeds,
            'net_proceeds': net_proceeds,
            'multiplier': multiplier,
            'contracts': contracts,
            'side': exit_side.value
        }

    def calculate_round_trip_pnl(
        self,
        entry_bid: float,
        entry_ask: float,
        exit_bid: float,
        exit_ask: float,
        contracts: int,
        entry_side: OrderSide = OrderSide.BUY,
        symbol_type: SymbolType = SymbolType.ETF,
        multiplier: int = 100
    ) -> Dict:
        """
        Calculate the complete P&L for a round-trip trade.

        This is the REAL P&L including all costs.

        Args:
            entry_bid/ask: Bid/ask at entry
            exit_bid/ask: Bid/ask at exit
            contracts: Number of contracts
            entry_side: BUY (long) or SELL (short/write)
            symbol_type: Type of underlying
            multiplier: Contract multiplier

        Returns:
            Complete P&L breakdown
        """
        # Calculate entry cost
        entry = self.calculate_total_entry_cost(
            entry_bid, entry_ask, contracts, entry_side, symbol_type, multiplier
        )

        if 'error' in entry:
            return entry

        # Calculate exit proceeds
        exit_result = self.calculate_exit_proceeds(
            exit_bid, exit_ask, contracts, entry_side, symbol_type, multiplier
        )

        if 'error' in exit_result:
            return exit_result

        # Calculate P&L
        if entry_side == OrderSide.BUY:
            # Long position: profit when price goes up
            gross_pnl = exit_result['gross_proceeds'] - entry['premium']
            total_costs = entry['commission']['total_commission'] + exit_result['commission']['total_commission']
            total_slippage = (entry['slippage']['slippage_from_mid'] + exit_result['slippage']['slippage_from_mid']) * contracts * multiplier
        else:
            # Short position: profit when price goes down
            gross_pnl = entry['premium'] - exit_result['gross_proceeds']
            total_costs = entry['commission']['total_commission'] + exit_result['commission']['total_commission']
            total_slippage = (entry['slippage']['slippage_from_mid'] + exit_result['slippage']['slippage_from_mid']) * contracts * multiplier

        net_pnl = gross_pnl - total_costs

        # Calculate what P&L would have been with mid prices and no costs
        theoretical_entry = entry['slippage']['mid']
        theoretical_exit = exit_result['slippage']['mid']
        if entry_side == OrderSide.BUY:
            theoretical_pnl = (theoretical_exit - theoretical_entry) * contracts * multiplier
        else:
            theoretical_pnl = (theoretical_entry - theoretical_exit) * contracts * multiplier

        # How much did costs eat into P&L?
        cost_drag = theoretical_pnl - net_pnl
        cost_drag_pct = (cost_drag / abs(theoretical_pnl) * 100) if theoretical_pnl != 0 else 0

        return {
            'entry': entry,
            'exit': exit_result,
            'gross_pnl': gross_pnl,
            'total_commission': total_costs,
            'total_slippage': total_slippage,
            'net_pnl': net_pnl,
            'theoretical_pnl': theoretical_pnl,
            'cost_drag': cost_drag,
            'cost_drag_pct': cost_drag_pct,
            'pnl_per_contract': net_pnl / contracts if contracts > 0 else 0
        }


def get_costs_calculator(symbol: str = 'SPY', trader_type: str = 'paper') -> TradingCostsCalculator:
    """
    Factory function to get appropriate costs calculator for a symbol and trader type.

    Args:
        symbol: Trading symbol (SPY, SPX, QQQ, etc.)
        trader_type: 'paper', 'retail', 'institutional'

    Returns:
        Configured TradingCostsCalculator
    """
    # Select base config by trader type
    if trader_type == 'institutional':
        config = INSTITUTIONAL_COSTS
    elif trader_type == 'retail':
        config = RETAIL_COSTS
    else:
        config = PAPER_TRADING_COSTS

    # Adjust for symbol-specific characteristics
    if symbol.upper() in ['SPX', 'NDX', 'RUT']:
        # Index options have wider spreads
        config = TradingCostsConfig(
            commission_per_contract=config.commission_per_contract,
            spread_capture_pct=config.spread_capture_pct - 0.05,  # Worse fills
            market_impact_bp_per_contract=config.market_impact_bp_per_contract + 0.05,
            regulatory_fee_per_contract=config.regulatory_fee_per_contract
        )

    return TradingCostsCalculator(config)


# Module-level singleton for default usage
_default_calculator = None

def get_default_calculator() -> TradingCostsCalculator:
    """Get the default trading costs calculator (singleton)"""
    global _default_calculator
    if _default_calculator is None:
        _default_calculator = TradingCostsCalculator(PAPER_TRADING_COSTS)
    return _default_calculator


def apply_slippage_to_entry(
    bid: float,
    ask: float,
    contracts: int = 1,
    side: str = 'buy',
    symbol: str = 'SPY'
) -> Tuple[float, Dict]:
    """
    Convenience function to apply slippage to an entry price.

    Args:
        bid: Best bid
        ask: Best ask
        contracts: Number of contracts
        side: 'buy' or 'sell'
        symbol: Trading symbol

    Returns:
        (adjusted_price, details)
    """
    calc = get_costs_calculator(symbol)
    order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
    return calc.calculate_entry_price(bid, ask, contracts, order_side)


def apply_slippage_to_exit(
    bid: float,
    ask: float,
    contracts: int = 1,
    original_side: str = 'buy',
    symbol: str = 'SPY'
) -> Tuple[float, Dict]:
    """
    Convenience function to apply slippage to an exit price.

    Args:
        bid: Current best bid
        ask: Current best ask
        contracts: Number of contracts
        original_side: Original entry side ('buy' = selling to close)
        symbol: Trading symbol

    Returns:
        (adjusted_price, details)
    """
    calc = get_costs_calculator(symbol)
    # Exit is opposite of entry
    exit_side = OrderSide.SELL if original_side.lower() == 'buy' else OrderSide.BUY
    return calc.calculate_entry_price(bid, ask, contracts, exit_side)


if __name__ == '__main__':
    # Example usage and validation
    print("=" * 60)
    print("TRADING COSTS CALCULATOR - EXAMPLES")
    print("=" * 60)

    calc = TradingCostsCalculator(PAPER_TRADING_COSTS)

    # Example 1: SPY option entry
    print("\n1. BUYING 5 SPY CALLS")
    print("-" * 40)
    entry = calc.calculate_total_entry_cost(
        bid=2.50,
        ask=2.55,
        contracts=5,
        side=OrderSide.BUY
    )
    print(f"Bid: ${entry['slippage']['bid']:.2f}")
    print(f"Ask: ${entry['slippage']['ask']:.2f}")
    print(f"Mid: ${entry['slippage']['mid']:.2f}")
    print(f"Execution Price: ${entry['execution_price']:.4f}")
    print(f"Slippage from Mid: ${entry['slippage']['slippage_from_mid']:.4f} ({entry['slippage']['slippage_pct']:.2f}%)")
    print(f"Premium: ${entry['premium']:.2f}")
    print(f"Commission: ${entry['commission']['total_commission']:.2f}")
    print(f"Total Cost: ${entry['total_cost']:.2f}")

    # Example 2: Round trip P&L comparison
    print("\n2. ROUND TRIP P&L (Entry $2.52, Exit $2.80)")
    print("-" * 40)
    pnl = calc.calculate_round_trip_pnl(
        entry_bid=2.50,
        entry_ask=2.55,
        exit_bid=2.78,
        exit_ask=2.82,
        contracts=5
    )
    print(f"Entry Price (with slippage): ${pnl['entry']['execution_price']:.4f}")
    print(f"Exit Price (with slippage): ${pnl['exit']['execution_price']:.4f}")
    print(f"Theoretical P&L (mid-to-mid): ${pnl['theoretical_pnl']:.2f}")
    print(f"Actual Net P&L: ${pnl['net_pnl']:.2f}")
    print(f"Total Commissions: ${pnl['total_commission']:.2f}")
    print(f"Total Slippage: ${pnl['total_slippage']:.2f}")
    print(f"Cost Drag: ${pnl['cost_drag']:.2f} ({pnl['cost_drag_pct']:.1f}% of theoretical)")

    # Example 3: Wide spread scenario
    print("\n3. WIDE SPREAD SCENARIO (20% spread)")
    print("-" * 40)
    wide_entry = calc.calculate_total_entry_cost(
        bid=1.00,
        ask=1.25,
        contracts=1,
        side=OrderSide.BUY
    )
    print(f"Bid: ${wide_entry['slippage']['bid']:.2f}")
    print(f"Ask: ${wide_entry['slippage']['ask']:.2f}")
    print(f"Spread: {wide_entry['slippage']['spread_pct']:.1f}%")
    print(f"Mid: ${wide_entry['slippage']['mid']:.2f}")
    print(f"Execution Price: ${wide_entry['execution_price']:.4f}")
    print(f"Slippage: {wide_entry['slippage']['slippage_pct']:.2f}%")

    print("\n" + "=" * 60)
    print("CRITICAL: Always use this module for realistic P&L!")
    print("=" * 60)
