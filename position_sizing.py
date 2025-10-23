"""
Probability-Based Position Sizing Calculator
Optimizes position size based on confidence level and account risk parameters
"""

import streamlit as st
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


def display_position_sizing(setup: Dict, account_size: float, risk_percent: float):
    """Display position sizing calculator for a trading setup"""

    st.subheader(f"💰 Position Sizing: {setup.get('strategy', 'Unknown')}")

    confidence = setup.get('confidence', 50)
    option_premium = setup.get('option_premium', 2.50)

    # Determine max loss per contract
    max_loss = None
    if 'max_risk' in setup:
        # Extract dollar amount from string like "$420"
        max_risk_str = str(setup['max_risk']).replace('$', '').replace(',', '')
        try:
            max_loss = float(max_risk_str)
        except:
            max_loss = option_premium * 100
    else:
        # For long options, max loss = premium × 100
        max_loss = option_premium * 100

    # Calculate sizing
    sizing = calculate_optimal_position_size(
        account_size=account_size,
        risk_percent=risk_percent,
        setup_confidence=confidence,
        option_premium=option_premium,
        max_loss_per_contract=max_loss
    )

    # Display in columns
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "📦 Contracts",
            f"{sizing['num_contracts']}",
            help="Number of option contracts to trade"
        )

    with col2:
        st.metric(
            "💵 Capital Required",
            f"${sizing['premium_outlay']:,.0f}",
            help="Total premium/margin required"
        )

    with col3:
        st.metric(
            "⚠️ Max Risk",
            f"${sizing['total_risk']:,.0f}",
            help="Maximum loss if trade goes against you"
        )

    with col4:
        st.metric(
            "📊 Account Risk %",
            f"{sizing['risk_pct_of_account']:.2f}%",
            help="Percentage of account at risk"
        )

    # Confidence-based sizing explanation
    with st.expander("📐 Why This Size?"):
        st.markdown(f"""
        **Probability-Based Sizing Logic:**

        - **Base Risk**: ${sizing['base_risk_amount']:,.0f} ({risk_percent}% of ${account_size:,.0f} account)
        - **Setup Confidence**: {confidence}%
        - **Confidence Multiplier**: {sizing['confidence_multiplier']:.2f}x
        - **Adjusted Risk**: ${sizing['adjusted_risk_amount']:,.0f}

        **Why adjust for confidence?**
        - Higher confidence ({confidence}%) = Larger position size
        - Lower confidence = Smaller position size
        - This maximizes long-term returns (Kelly Criterion)

        **Example:**
        - 80% confidence → Risk 80% of your normal amount
        - 60% confidence → Risk 60% of your normal amount
        - 100% confidence → Risk full amount

        **Result**: You bet bigger when edge is stronger, protecting capital on uncertain trades.
        """)

    # Risk/Reward visualization
    create_risk_reward_chart(setup, sizing)

    return sizing


def create_risk_reward_chart(setup: Dict, sizing: Dict):
    """Create visual risk/reward chart for the position"""

    max_risk = sizing['total_risk']
    risk_reward_ratio = setup.get('risk_reward', 2.0)
    max_profit = max_risk * risk_reward_ratio

    # Create scenarios
    scenarios = ['Max Loss', 'Break Even', 'Target 1', 'Max Profit']
    pnl = [-max_risk, 0, max_profit * 0.5, max_profit]
    colors = ['red', 'gray', 'lightgreen', 'green']

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=scenarios,
        y=pnl,
        marker_color=colors,
        text=[f"${val:,.0f}" for val in pnl],
        textposition='outside',
        hovertemplate='%{x}<br>P&L: $%{y:,.0f}<extra></extra>'
    ))

    fig.update_layout(
        title=f"Risk/Reward Profile - {sizing['num_contracts']} Contracts",
        yaxis_title="Profit/Loss ($)",
        template='plotly_dark',
        height=450,
        showlegend=False,
        margin=dict(t=80, b=60, l=60, r=60)
    )

    # Add break-even line
    fig.add_hline(y=0, line_dash="dash", line_color="white", line_width=1)

    st.plotly_chart(fig, use_container_width=True)


def display_position_size_controls():
    """Display position sizing settings in sidebar"""

    st.sidebar.subheader("💰 Position Sizing")

    # Get or set account settings
    if 'account_size' not in st.session_state:
        st.session_state.account_size = 50000
    if 'risk_per_trade' not in st.session_state:
        st.session_state.risk_per_trade = 2.0

    account_size = st.sidebar.number_input(
        "Account Size ($)",
        min_value=1000,
        max_value=10000000,
        value=st.session_state.account_size,
        step=1000,
        help="Your total trading account size"
    )
    st.session_state.account_size = account_size

    risk_pct = st.sidebar.slider(
        "Risk Per Trade (%)",
        min_value=0.5,
        max_value=5.0,
        value=float(st.session_state.risk_per_trade),
        step=0.5,
        help="Percentage of account to risk per trade (1-2% recommended)"
    )
    st.session_state.risk_per_trade = risk_pct

    max_risk = account_size * (risk_pct / 100)
    st.sidebar.caption(f"💡 Base risk per trade: ${max_risk:,.2f}")

    return account_size, risk_pct


def display_kelly_criterion_calculator():
    """Advanced Kelly Criterion calculator for position sizing"""

    with st.expander("🧮 Advanced: Kelly Criterion Calculator"):
        st.markdown("""
        **Kelly Criterion** = Optimal bet size for long-term wealth maximization

        Formula: `f* = (bp - q) / b`
        - p = win probability
        - q = loss probability (1 - p)
        - b = win/loss ratio (how much you win vs lose)
        """)

        col1, col2 = st.columns(2)

        with col1:
            win_rate = st.slider("Historical Win Rate (%)", 0, 100, 65, help="Your actual win rate for this strategy")
            avg_win = st.number_input("Average Win ($)", value=1000.0, help="Average profit on winning trades")

        with col2:
            loss_rate = 100 - win_rate
            avg_loss = st.number_input("Average Loss ($)", value=400.0, help="Average loss on losing trades")

        # Calculate Kelly percentage
        p = win_rate / 100
        q = loss_rate / 100
        b = avg_win / avg_loss if avg_loss > 0 else 0

        kelly_pct = (b * p - q) / b if b > 0 else 0
        kelly_pct = max(0, min(kelly_pct * 100, 100))  # Cap between 0-100%

        # Half Kelly (more conservative)
        half_kelly_pct = kelly_pct / 2

        st.markdown(f"""
        **Kelly Results:**
        - **Full Kelly**: {kelly_pct:.1f}% of account per trade
        - **Half Kelly** (recommended): {half_kelly_pct:.1f}% of account per trade

        💡 **Note**: Most traders use 1/4 to 1/2 Kelly to reduce volatility while still growing capital optimally.
        """)

        if kelly_pct > 10:
            st.warning("⚠️ Kelly suggests >10% risk. This is aggressive. Consider using Half Kelly or quarter Kelly for safer growth.")
        elif kelly_pct < 0:
            st.error("🛑 Negative Kelly = No edge. Don't take this trade!")
