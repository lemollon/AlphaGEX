"""
Probability-Based Position Sizing Calculator
Optimizes position size based on confidence level and account risk parameters

UI rendering has been removed - use the backend API for sizing views.
"""

from typing import Dict, Optional
import plotly.graph_objects as go


def calculate_optimal_position_size(
    account_size: float,
    risk_percent: float,
    setup_confidence: int,
    option_premium: float,
    max_loss_per_contract: float = None
) -> Dict:
    """
    Calculate optimal position size based on Kelly Criterion adjusted for confidence

    Parameters:
    - account_size: Total account value
    - risk_percent: Max % of account to risk (e.g., 2.0 for 2%)
    - setup_confidence: Setup confidence 0-100
    - option_premium: Cost per option contract
    - max_loss_per_contract: Maximum loss per contract (for spreads)

    Returns:
    - Dictionary with sizing recommendations
    """

    # Base risk amount (what you'd risk at 100% confidence)
    base_risk_amount = account_size * (risk_percent / 100)

    # Adjust risk based on confidence (Kelly-style)
    # Higher confidence = larger size, lower confidence = smaller size
    confidence_multiplier = setup_confidence / 100

    # Adjusted risk amount
    adjusted_risk_amount = base_risk_amount * confidence_multiplier

    # Calculate number of contracts
    if max_loss_per_contract:
        # For spreads with defined max loss
        num_contracts = int(adjusted_risk_amount / max_loss_per_contract)
    else:
        # For long options (max loss = premium paid)
        num_contracts = int(adjusted_risk_amount / (option_premium * 100))

    # Ensure at least 1 contract if we have any risk
    num_contracts = max(1, num_contracts) if adjusted_risk_amount > 0 else 0

    # Calculate actual dollar amounts
    if max_loss_per_contract:
        total_risk = num_contracts * max_loss_per_contract
        premium_outlay = num_contracts * option_premium * 100  # Approx for spread
    else:
        total_risk = num_contracts * option_premium * 100
        premium_outlay = total_risk

    # Risk as % of account
    risk_pct_of_account = (total_risk / account_size * 100) if account_size > 0 else 0

    return {
        'num_contracts': num_contracts,
        'total_risk': total_risk,
        'premium_outlay': premium_outlay,
        'risk_pct_of_account': risk_pct_of_account,
        'confidence_multiplier': confidence_multiplier,
        'base_risk_amount': base_risk_amount,
        'adjusted_risk_amount': adjusted_risk_amount
    }


def calculate_position_size_for_setup(
    setup: Dict,
    account_size: float,
    risk_percent: float
) -> Dict:
    """
    Calculate position sizing for a trading setup

    Parameters:
    - setup: Trading setup dict with 'confidence', 'option_premium', 'max_risk'
    - account_size: Total account value
    - risk_percent: Max % of account to risk

    Returns:
    - Dictionary with full sizing details
    """
    confidence = setup.get('confidence', 50)
    option_premium = setup.get('option_premium', 2.50)

    # Determine max loss per contract
    max_loss = None
    if 'max_risk' in setup:
        # Extract dollar amount from string like "$420"
        max_risk_str = str(setup['max_risk']).replace('$', '').replace(',', '')
        try:
            max_loss = float(max_risk_str)
        except ValueError:
            max_loss = None

    # Calculate sizing
    sizing = calculate_optimal_position_size(
        account_size=account_size,
        risk_percent=risk_percent,
        setup_confidence=confidence,
        option_premium=option_premium,
        max_loss_per_contract=max_loss
    )

    return {
        'strategy': setup.get('strategy', 'Unknown'),
        'confidence': confidence,
        'option_premium': option_premium,
        'max_loss_per_contract': max_loss,
        **sizing
    }


def create_position_sizing_chart(sizing: Dict) -> go.Figure:
    """
    Create visual representation of position sizing

    Parameters:
    - sizing: Result from calculate_optimal_position_size or calculate_position_size_for_setup

    Returns:
    - Plotly figure
    """
    fig = go.Figure()

    # Risk bar
    fig.add_trace(go.Bar(
        x=['Base Risk', 'Adjusted Risk', 'Total Risk'],
        y=[
            sizing.get('base_risk_amount', 0),
            sizing.get('adjusted_risk_amount', 0),
            sizing.get('total_risk', 0)
        ],
        marker_color=['#636EFA', '#EF553B', '#00CC96'],
        text=[
            f"${sizing.get('base_risk_amount', 0):.2f}",
            f"${sizing.get('adjusted_risk_amount', 0):.2f}",
            f"${sizing.get('total_risk', 0):.2f}"
        ],
        textposition='auto'
    ))

    fig.update_layout(
        title=f"Position Sizing Breakdown - {sizing.get('num_contracts', 0)} Contracts",
        yaxis_title="Dollar Amount ($)",
        template="plotly_dark",
        height=350
    )

    return fig


def get_kelly_optimal_size(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate Kelly Criterion optimal position size

    Parameters:
    - win_rate: Win rate as decimal (0.0 to 1.0)
    - avg_win: Average winning trade profit
    - avg_loss: Average losing trade loss (positive number)

    Returns:
    - Optimal fraction of bankroll to risk (0.0 to 1.0)
    """
    if avg_loss <= 0:
        return 0.0

    # Kelly formula: f* = (bp - q) / b
    # where b = win/loss ratio, p = win rate, q = 1-p
    b = avg_win / avg_loss if avg_loss > 0 else 0
    p = win_rate
    q = 1 - p

    kelly = (b * p - q) / b if b > 0 else 0

    # Clamp between 0 and 1
    return max(0.0, min(1.0, kelly))


def get_half_kelly_size(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Calculate half-Kelly position size (more conservative)

    Parameters:
    - win_rate: Win rate as decimal (0.0 to 1.0)
    - avg_win: Average winning trade profit
    - avg_loss: Average losing trade loss (positive number)

    Returns:
    - Half-Kelly fraction of bankroll to risk
    """
    full_kelly = get_kelly_optimal_size(win_rate, avg_win, avg_loss)
    return full_kelly / 2


def validate_position_size(
    account_size: float,
    position_risk: float,
    max_risk_percent: float = 5.0
) -> Dict:
    """
    Validate a position size against risk limits

    Parameters:
    - account_size: Total account value
    - position_risk: Dollar risk of the position
    - max_risk_percent: Maximum allowed risk as % of account

    Returns:
    - Dictionary with validation result
    """
    risk_percent = (position_risk / account_size * 100) if account_size > 0 else 0
    is_valid = risk_percent <= max_risk_percent

    return {
        'is_valid': is_valid,
        'position_risk': position_risk,
        'risk_percent': risk_percent,
        'max_risk_percent': max_risk_percent,
        'message': f"Risk {risk_percent:.2f}% is {'within' if is_valid else 'exceeds'} limit of {max_risk_percent}%"
    }
