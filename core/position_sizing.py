"""
Probability-Based Position Sizing Calculator
Optimizes position size based on confidence level and account risk parameters
"""

from utils.console_output import st
from typing import Dict
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


def display_position_sizing(setup: Dict, account_size: float, risk_percent: float, key_suffix: str = ""):
    """Display position sizing calculator for a trading setup"""

    st.subheader(f"💰 Position Sizing: {setup.get('strategy', 'Unknown')}")

    confidence = setup.get('confidence', 50)
    option_premium = setup.get('option_premium', 2.50)

    # Determine max loss per contract
    max_loss = None
    if 'max_risk' in setup:
        # Extract dollar amount from string like "$420"
        max_risk_str = str(setup['max_risk']).replace('$', '').replace(',', '')
