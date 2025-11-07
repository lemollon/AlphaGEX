"""
LangChain Tools for AlphaGEX

This module defines LangChain tools that wrap AlphaGEX functionality,
allowing Claude to use function calling to access market data and analysis.
"""

from langchain.tools import tool
from typing import Dict, Optional, List
from datetime import datetime
import os

# Import AlphaGEX core classes
try:
    from core_classes_and_engines import (
        TradingVolatilityAPI,
        GEXAnalyzer,
        TradingStrategy,
        MarketRegimeAnalyzer,
        RiskManager
    )
    from intelligence_and_strategies import (
        RealOptionsChainFetcher,
        GreeksCalculator,
        PositionSizingCalculator,
        FREDIntegration,
        TradingRAG
    )
except ImportError:
    # Graceful degradation if imports fail
    print("Warning: Some AlphaGEX modules not available. Tools will have limited functionality.")


# ============================================================================
# GEX DATA TOOLS
# ============================================================================

@tool
def get_gex_data(symbol: str) -> Dict:
    """
    Fetch current Gamma Exposure (GEX) data for a symbol.

    This tool retrieves dealer gamma positioning, flip points, and gamma walls
    from the Trading Volatility API.

    Args:
        symbol: Stock symbol (e.g., 'SPY', 'QQQ', 'IWM')

    Returns:
        Dictionary containing:
        - net_gex: Net dealer gamma exposure in billions
        - flip_point: Zero gamma crossover price
        - call_wall: Major resistance level
        - put_wall: Major support level
        - dealer_positioning: SHORT_GAMMA or LONG_GAMMA
    """
    try:
        api_key = os.getenv("TRADING_VOLATILITY_API_KEY", "")
        if not api_key:
            return {"error": "Trading Volatility API key not found"}

        api = TradingVolatilityAPI(api_key)
        data = api.fetch_gex_data(symbol)

        if not data:
            return {"error": f"No GEX data available for {symbol}"}

        return {
            "symbol": symbol,
            "net_gex": data.get("net_gex", 0),
            "flip_point": data.get("flip_point", 0),
            "call_wall": data.get("call_wall", 0),
            "put_wall": data.get("put_wall", 0),
            "call_wall_strength": data.get("call_wall_gamma", 0),
            "put_wall_strength": data.get("put_wall_gamma", 0),
            "dealer_positioning": "SHORT_GAMMA" if data.get("net_gex", 0) < 0 else "LONG_GAMMA",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to fetch GEX data: {str(e)}"}


@tool
def analyze_gex_regime(symbol: str, current_price: float) -> Dict:
    """
    Analyze the current GEX regime and Market Maker state.

    This tool determines what state the Market Makers are in based on
    dealer gamma positioning and provides trading implications.

    Args:
        symbol: Stock symbol (e.g., 'SPY')
        current_price: Current spot price of the underlying

    Returns:
        Dictionary containing:
        - market_maker_state: One of PANICKING, TRAPPED, HUNTING, DEFENDING, NEUTRAL
        - confidence: Confidence level 0-1
        - trading_implication: What this means for trading
        - expected_behavior: How dealers will likely behave
        - volatility_risk: Risk of volatility expansion
    """
    try:
        # Get GEX data first
        gex_data = get_gex_data(symbol)
        if "error" in gex_data:
            return gex_data

        net_gex = gex_data["net_gex"]
        flip_point = gex_data["flip_point"]

        # Determine Market Maker state
        if net_gex < -3.0:
            state = "PANICKING"
            confidence = 0.90
            implication = "Dealers are trapped short gamma. They will buy ANY rally aggressively."
            behavior = "Forced buying on upside moves, creating explosive rallies"
            vol_risk = "EXTREME"
        elif net_gex < -2.0:
            state = "TRAPPED"
            confidence = 0.85
            implication = "Dealers are short gamma but not panicking yet. Prefer upside."
            behavior = "Will buy rallies to hedge, selling dips less aggressively"
            vol_risk = "ELEVATED"
        elif net_gex < -1.0:
            state = "HUNTING"
            confidence = 0.60
            implication = "Dealers are mildly short gamma. Wait for directional confirmation."
            behavior = "Mixed behavior, look for directional signals"
            vol_risk = "MODERATE"
        elif net_gex > 1.0:
            state = "DEFENDING"
            confidence = 0.75
            implication = "Dealers are long gamma. They will fade moves and defend range."
            behavior = "Sell rallies and buy dips to stay hedged"
            vol_risk = "LOW"
        else:
            state = "NEUTRAL"
            confidence = 0.50
            implication = "Balanced positioning. Market can go either way."
            behavior = "No strong dealer bias"
            vol_risk = "MODERATE"

        # Check proximity to flip point
        distance_to_flip = abs(current_price - flip_point) / current_price * 100

        if distance_to_flip < 0.5:
            state = "FLIP_POINT_CRITICAL"
            confidence = 0.95
            implication = "URGENT: Price is at the flip point. Regime change imminent!"
            behavior = "Explosive move likely as dealers switch from buying to selling or vice versa"
            vol_risk = "EXTREME"

        return {
            "symbol": symbol,
            "current_price": current_price,
            "net_gex_billions": net_gex,
            "flip_point": flip_point,
            "distance_to_flip_pct": round(distance_to_flip, 2),
            "market_maker_state": state,
            "confidence": confidence,
            "trading_implication": implication,
            "expected_behavior": behavior,
            "volatility_risk": vol_risk,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to analyze GEX regime: {str(e)}"}


# ============================================================================
# OPTIONS DATA TOOLS
# ============================================================================

@tool
def get_option_chain(symbol: str, expiration: str) -> Dict:
    """
    Fetch option chain data for a specific expiration.

    Args:
        symbol: Stock symbol (e.g., 'SPY')
        expiration: Expiration date in YYYY-MM-DD format

    Returns:
        Dictionary containing option chain with strikes, bids, asks, IVs
    """
    try:
        fetcher = RealOptionsChainFetcher()
        chain = fetcher.fetch_option_chain(symbol, expiration)

        if not chain:
            return {"error": f"No option chain data for {symbol} expiring {expiration}"}

        return {
            "symbol": symbol,
            "expiration": expiration,
            "chain": chain,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to fetch option chain: {str(e)}"}


@tool
def calculate_option_greeks(
    symbol: str,
    strike: float,
    expiration: str,
    option_type: str,
    spot_price: float,
    iv: Optional[float] = None
) -> Dict:
    """
    Calculate option Greeks (Delta, Gamma, Theta, Vega).

    Args:
        symbol: Stock symbol
        strike: Strike price
        expiration: Expiration date (YYYY-MM-DD)
        option_type: 'call' or 'put'
        spot_price: Current stock price
        iv: Implied volatility (optional, will fetch if not provided)

    Returns:
        Dictionary with delta, gamma, theta, vega, rho
    """
    try:
        calculator = GreeksCalculator()
        greeks = calculator.calculate_greeks(
            spot=spot_price,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            iv=iv
        )

        return {
            "symbol": symbol,
            "strike": strike,
            "expiration": expiration,
            "type": option_type,
            "spot_price": spot_price,
            "greeks": greeks,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to calculate Greeks: {str(e)}"}


# ============================================================================
# POSITION SIZING TOOLS
# ============================================================================

@tool
def calculate_position_size(
    account_size: float,
    win_rate: float,
    risk_reward_ratio: float,
    max_risk_pct: float = 5.0,
    kelly_fraction: str = "half"
) -> Dict:
    """
    Calculate optimal position size using Kelly Criterion.

    Args:
        account_size: Total account value in dollars
        win_rate: Expected win rate (0-1, e.g., 0.65 for 65%)
        risk_reward_ratio: R:R ratio (e.g., 2.5 for 2.5:1)
        max_risk_pct: Maximum % of account to risk (default 5%)
        kelly_fraction: 'full', 'half', or 'quarter' Kelly

    Returns:
        Dictionary with recommended position size and risk metrics
    """
    try:
        calculator = PositionSizingCalculator()
        sizing = calculator.calculate_kelly(
            account_size=account_size,
            win_rate=win_rate,
            avg_win=risk_reward_ratio,
            avg_loss=1.0,
            kelly_fraction=kelly_fraction
        )

        # Apply max risk limit
        max_risk_dollars = account_size * (max_risk_pct / 100)

        return {
            "account_size": account_size,
            "kelly_fraction": kelly_fraction,
            "recommended_position_pct": sizing.get("position_pct", 0),
            "recommended_position_dollars": sizing.get("position_size", 0),
            "max_risk_dollars": max_risk_dollars,
            "max_risk_pct": max_risk_pct,
            "win_rate": win_rate,
            "risk_reward_ratio": risk_reward_ratio,
            "risk_of_ruin": sizing.get("risk_of_ruin", 0),
            "expected_growth_rate": sizing.get("expected_growth", 0),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to calculate position size: {str(e)}"}


# ============================================================================
# MARKET DATA TOOLS
# ============================================================================

@tool
def get_economic_data() -> Dict:
    """
    Fetch current economic indicators (VIX, Treasury yields, Fed rates).

    Returns:
        Dictionary containing:
        - vix: Current VIX level
        - treasury_10y: 10-year Treasury yield
        - fed_funds_rate: Federal Funds rate
        - dollar_index: DXY value
    """
    try:
        fred = FREDIntegration()
        data = fred.get_current_indicators()

        return {
            "vix": data.get("VIX", 0),
            "treasury_10y": data.get("DGS10", 0),
            "fed_funds_rate": data.get("DFF", 0),
            "dollar_index": data.get("DTWEXBGS", 0),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to fetch economic data: {str(e)}"}


@tool
def get_volatility_regime() -> Dict:
    """
    Determine the current volatility regime.

    Returns:
        Dictionary with volatility classification and trading implications
    """
    try:
        econ_data = get_economic_data()
        if "error" in econ_data:
            return econ_data

        vix = econ_data.get("vix", 20)

        if vix < 15:
            regime = "LOW"
            implication = "Low volatility environment. Premium selling strategies work well."
            risk = "Complacency - watch for sudden volatility spikes"
        elif vix < 20:
            regime = "NORMAL"
            implication = "Normal volatility. Balanced approach to directional and theta strategies."
            risk = "Standard market risk"
        elif vix < 30:
            regime = "ELEVATED"
            implication = "Elevated volatility. Directional strategies and vol plays preferred."
            risk = "Higher overnight risk and gap risk"
        else:
            regime = "EXTREME"
            implication = "Extreme volatility. High premium but high risk. Use small positions."
            risk = "EXTREME - significant gap risk and whipsaw risk"

        return {
            "vix_level": vix,
            "volatility_regime": regime,
            "trading_implication": implication,
            "risk_warning": risk,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to determine vol regime: {str(e)}"}


# ============================================================================
# HISTORICAL ANALYSIS TOOLS
# ============================================================================

@tool
def find_similar_trades(
    strategy_type: str,
    market_maker_state: str,
    limit: int = 10
) -> Dict:
    """
    Find similar historical trades using RAG.

    Args:
        strategy_type: Type of strategy (e.g., 'NEGATIVE_GEX_SQUEEZE')
        market_maker_state: MM state (e.g., 'TRAPPED')
        limit: Maximum number of similar trades to return

    Returns:
        Dictionary with similar historical trades and their outcomes
    """
    try:
        rag = TradingRAG()
        similar_trades = rag.find_similar_setups(
            strategy=strategy_type,
            mm_state=market_maker_state,
            limit=limit
        )

        if not similar_trades:
            return {
                "message": f"No historical trades found for {strategy_type} in {market_maker_state} state",
                "trades": []
            }

        # Calculate aggregate statistics
        total_trades = len(similar_trades)
        winners = sum(1 for t in similar_trades if t.get("profit_loss", 0) > 0)
        win_rate = winners / total_trades if total_trades > 0 else 0

        avg_return = sum(t.get("return_pct", 0) for t in similar_trades) / total_trades if total_trades > 0 else 0

        return {
            "strategy_type": strategy_type,
            "market_maker_state": market_maker_state,
            "total_similar_trades": total_trades,
            "win_rate": round(win_rate, 3),
            "avg_return_pct": round(avg_return, 2),
            "trades": similar_trades[:limit],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to find similar trades: {str(e)}"}


# ============================================================================
# RISK MANAGEMENT TOOLS
# ============================================================================

@tool
def validate_trade_risk(
    position_size_dollars: float,
    account_size: float,
    max_loss_dollars: float,
    current_portfolio_delta: float = 0,
    proposed_delta: float = 0
) -> Dict:
    """
    Validate if a trade meets risk management criteria.

    Args:
        position_size_dollars: Size of proposed position
        account_size: Total account value
        max_loss_dollars: Maximum possible loss on trade
        current_portfolio_delta: Current portfolio delta exposure
        proposed_delta: Delta of proposed trade

    Returns:
        Dictionary with risk validation and approval/rejection
    """
    try:
        # Calculate risk metrics
        position_pct = (position_size_dollars / account_size) * 100
        max_loss_pct = (max_loss_dollars / account_size) * 100
        new_delta = current_portfolio_delta + proposed_delta

        # Risk limits
        MAX_POSITION_PCT = 25.0  # Max 25% per position
        MAX_LOSS_PCT = 5.0       # Max 5% account risk per trade
        MAX_PORTFOLIO_DELTA = 2.0  # Max portfolio delta of +/-2.0

        # Validation checks
        checks = []
        approved = True

        if position_pct > MAX_POSITION_PCT:
            checks.append(f"FAIL: Position size {position_pct:.1f}% exceeds limit of {MAX_POSITION_PCT}%")
            approved = False
        else:
            checks.append(f"PASS: Position size {position_pct:.1f}% within limit")

        if max_loss_pct > MAX_LOSS_PCT:
            checks.append(f"FAIL: Max loss {max_loss_pct:.1f}% exceeds limit of {MAX_LOSS_PCT}%")
            approved = False
        else:
            checks.append(f"PASS: Max loss {max_loss_pct:.1f}% within limit")

        if abs(new_delta) > MAX_PORTFOLIO_DELTA:
            checks.append(f"WARN: Portfolio delta {new_delta:.2f} exceeds recommended limit of +/-{MAX_PORTFOLIO_DELTA}")
        else:
            checks.append(f"PASS: Portfolio delta {new_delta:.2f} within limit")

        return {
            "approved": approved,
            "position_size_pct": round(position_pct, 2),
            "max_loss_pct": round(max_loss_pct, 2),
            "portfolio_delta_before": current_portfolio_delta,
            "portfolio_delta_after": new_delta,
            "validation_checks": checks,
            "recommendation": "Trade approved" if approved else "Trade rejected - exceeds risk limits",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Failed to validate trade risk: {str(e)}"}


# ============================================================================
# TOOL COLLECTIONS
# ============================================================================

# List of all available tools
ALL_TOOLS = [
    get_gex_data,
    analyze_gex_regime,
    get_option_chain,
    calculate_option_greeks,
    calculate_position_size,
    get_economic_data,
    get_volatility_regime,
    find_similar_trades,
    validate_trade_risk
]

# Tool collections for specific use cases
MARKET_ANALYSIS_TOOLS = [
    get_gex_data,
    analyze_gex_regime,
    get_economic_data,
    get_volatility_regime
]

TRADE_PLANNING_TOOLS = [
    get_option_chain,
    calculate_option_greeks,
    calculate_position_size,
    find_similar_trades,
    validate_trade_risk
]

RISK_MANAGEMENT_TOOLS = [
    calculate_position_size,
    validate_trade_risk
]
