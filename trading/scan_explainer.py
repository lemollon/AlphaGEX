"""
Scan Explainer - Claude AI-Powered Decision Explanations

Generates human-readable explanations for every ARES and ATHENA scan decision.
This is the KEY to understanding WHY a bot did or didn't trade.

Every scan gets a detailed explanation including:
- What market conditions were observed
- What checks passed or failed (with specific values)
- WHY the decision was made
- What would need to change for a different outcome
"""

import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
import anthropic


class DecisionType(Enum):
    """Types of trading decisions"""
    TRADED = "TRADED"
    NO_TRADE = "NO_TRADE"
    SKIP = "SKIP"
    ERROR = "ERROR"
    MARKET_CLOSED = "MARKET_CLOSED"
    BEFORE_WINDOW = "BEFORE_WINDOW"
    AFTER_WINDOW = "AFTER_WINDOW"


@dataclass
class CheckDetail:
    """Detailed information about a single check"""
    name: str
    passed: bool
    actual_value: str
    required_value: str
    explanation: str


@dataclass
class MarketContext:
    """Complete market context at time of scan"""
    underlying_symbol: str
    underlying_price: float
    vix: float
    expected_move: Optional[float] = None
    net_gex: Optional[float] = None
    gex_regime: Optional[str] = None
    call_wall: Optional[float] = None
    put_wall: Optional[float] = None
    distance_to_call_wall_pct: Optional[float] = None
    distance_to_put_wall_pct: Optional[float] = None
    flip_point: Optional[float] = None


@dataclass
class SignalContext:
    """Signal information from ML/Oracle"""
    source: str  # "ML", "Oracle", "GEX", "None"
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL", "NONE"
    confidence: Optional[float] = None
    win_probability: Optional[float] = None
    advice: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class ScanContext:
    """Complete context for a scan decision"""
    bot_name: str
    scan_number: int
    decision_type: DecisionType
    market: MarketContext
    signal: Optional[SignalContext] = None
    checks: Optional[List[CheckDetail]] = None
    trade_details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


def generate_scan_explanation(context: ScanContext) -> Dict[str, str]:
    """
    Generate a Claude AI explanation for a scan decision.

    Returns:
        {
            "summary": "One-line human summary",
            "full_explanation": "Detailed multi-paragraph explanation"
        }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        # Fallback to rule-based explanation if no API key
        return _generate_fallback_explanation(context)

    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = _build_explanation_prompt(context)

        response = client.messages.create(
            model="claude-3-haiku-20240307",  # Fast and cheap for quick explanations
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        explanation_text = response.content[0].text

        # Parse the response - expect format with SUMMARY: and EXPLANATION:
        lines = explanation_text.strip().split('\n')
        summary = ""
        full_explanation = ""

        in_explanation = False
        for line in lines:
            if line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
            elif line.startswith("EXPLANATION:"):
                in_explanation = True
                full_explanation = line.replace("EXPLANATION:", "").strip()
            elif in_explanation:
                full_explanation += " " + line.strip()

        # If parsing failed, use the whole response
        if not summary:
            summary = explanation_text[:200] if len(explanation_text) > 200 else explanation_text
        if not full_explanation:
            full_explanation = explanation_text

        return {
            "summary": summary,
            "full_explanation": full_explanation.strip()
        }

    except Exception as e:
        print(f"Claude explanation failed: {e}, using fallback")
        return _generate_fallback_explanation(context)


def _build_explanation_prompt(context: ScanContext) -> str:
    """Build the prompt for Claude to explain the decision"""

    bot_desc = "ARES (Aggressive Iron Condor - sells 0DTE iron condors once per day)" if context.bot_name == "ARES" else "ATHENA (Directional Spreads - trades up to 5x/day based on GEX signals)"

    # Build market context string
    market_str = f"""
Market Conditions:
- {context.market.underlying_symbol}: ${context.market.underlying_price:.2f}
- VIX: {context.market.vix:.1f}"""

    if context.market.expected_move:
        market_str += f"\n- Expected Move: ${context.market.expected_move:.2f}"
    if context.market.net_gex:
        market_str += f"\n- Net GEX: ${context.market.net_gex:,.0f}"
    if context.market.gex_regime:
        market_str += f"\n- GEX Regime: {context.market.gex_regime}"
    if context.market.call_wall:
        market_str += f"\n- Call Wall (resistance): ${context.market.call_wall:.2f}"
    if context.market.put_wall:
        market_str += f"\n- Put Wall (support): ${context.market.put_wall:.2f}"
    if context.market.distance_to_call_wall_pct:
        market_str += f"\n- Distance to Call Wall: {context.market.distance_to_call_wall_pct:.1f}%"
    if context.market.distance_to_put_wall_pct:
        market_str += f"\n- Distance to Put Wall: {context.market.distance_to_put_wall_pct:.1f}%"

    # Build signal context string
    signal_str = ""
    if context.signal:
        signal_str = f"""
Signal Information:
- Source: {context.signal.source}
- Direction: {context.signal.direction}"""
        if context.signal.confidence:
            signal_str += f"\n- Confidence: {context.signal.confidence*100:.0f}%"
        if context.signal.win_probability:
            signal_str += f"\n- Win Probability: {context.signal.win_probability*100:.0f}%"
        if context.signal.advice:
            signal_str += f"\n- Advice: {context.signal.advice}"
        if context.signal.reasoning:
            signal_str += f"\n- Reasoning: {context.signal.reasoning}"

    # Build checks string
    checks_str = ""
    if context.checks:
        checks_str = "\nChecks Performed:"
        for check in context.checks:
            status = "PASSED" if check.passed else "FAILED"
            checks_str += f"\n- {check.name}: {status}"
            checks_str += f"\n  Actual: {check.actual_value}, Required: {check.required_value}"
            if check.explanation:
                checks_str += f"\n  Note: {check.explanation}"

    # Build trade details string
    trade_str = ""
    if context.trade_details:
        trade_str = "\nTrade Details:"
        for key, value in context.trade_details.items():
            trade_str += f"\n- {key}: {value}"

    # Build error string
    error_str = ""
    if context.error_message:
        error_str = f"\nError: {context.error_message}"

    prompt = f"""You are explaining a trading bot's decision to a human trader who needs to understand exactly what happened and why.

Bot: {bot_desc}
Scan #{context.scan_number}
Decision: {context.decision_type.value}
{market_str}
{signal_str}
{checks_str}
{trade_str}
{error_str}

Provide a clear, concise explanation in this EXACT format:

SUMMARY: [One sentence explaining what happened and the main reason why]
EXPLANATION: [2-3 sentences with specific numbers explaining the decision. If NO_TRADE, explain what check failed and what would need to change. If TRADED, explain why conditions were favorable. Be specific with prices and percentages.]

Focus on the WHY. Use actual numbers from the data provided. Be direct and informative."""

    return prompt


def _generate_fallback_explanation(context: ScanContext) -> Dict[str, str]:
    """Generate explanation without Claude API (rule-based fallback)"""

    bot_name = context.bot_name
    decision = context.decision_type
    market = context.market

    if decision == DecisionType.MARKET_CLOSED:
        return {
            "summary": f"{bot_name} scan skipped - market is closed",
            "full_explanation": f"The market is currently closed. {bot_name} only trades during market hours (ARES: 9:35 AM - 3:55 PM CT, ATHENA: 8:30 AM - 3:00 PM CT). No trading decisions are made outside these windows."
        }

    if decision == DecisionType.BEFORE_WINDOW:
        return {
            "summary": f"{bot_name} scan skipped - before trading window",
            "full_explanation": f"Current time is before {bot_name}'s trading window. ARES starts at 9:35 AM CT, ATHENA starts at 8:30 AM CT. The bot is waiting for the trading window to open."
        }

    if decision == DecisionType.AFTER_WINDOW:
        return {
            "summary": f"{bot_name} scan skipped - after trading window",
            "full_explanation": f"Current time is after {bot_name}'s trading window. ARES ends at 3:55 PM CT, ATHENA ends at 3:00 PM CT. No new trades will be opened today."
        }

    if decision == DecisionType.ERROR:
        return {
            "summary": f"{bot_name} scan failed - {context.error_message or 'unknown error'}",
            "full_explanation": f"An error occurred during the scan: {context.error_message or 'Unknown error'}. This prevented the bot from evaluating trading conditions. The error should be investigated."
        }

    if decision == DecisionType.NO_TRADE:
        # Find the first failed check
        failed_check = None
        if context.checks:
            for check in context.checks:
                if not check.passed:
                    failed_check = check
                    break

        if failed_check:
            summary = f"{bot_name} NO_TRADE - {failed_check.name} failed"
            explanation = f"Trade not taken because {failed_check.name} check failed. "
            explanation += f"Actual value: {failed_check.actual_value}, Required: {failed_check.required_value}. "
            if failed_check.explanation:
                explanation += failed_check.explanation
            explanation += f" Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."
        elif context.signal and context.signal.advice in ["SKIP_TODAY", "STAY_OUT"]:
            summary = f"{bot_name} NO_TRADE - {context.signal.source} advised against trading"
            explanation = f"Trade not taken because {context.signal.source} recommended {context.signal.advice}. "
            if context.signal.reasoning:
                explanation += f"Reason: {context.signal.reasoning}. "
            explanation += f"Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."
        else:
            summary = f"{bot_name} NO_TRADE - conditions not met"
            explanation = f"Trade not taken because entry conditions were not satisfied. "
            explanation += f"Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."

        return {"summary": summary, "full_explanation": explanation}

    if decision == DecisionType.TRADED:
        trade = context.trade_details or {}
        summary = f"{bot_name} TRADED - {trade.get('strategy', 'position')} opened"

        explanation = f"Trade executed: {trade.get('strategy', 'Unknown strategy')}. "
        if trade.get('contracts'):
            explanation += f"Size: {trade.get('contracts')} contracts. "
        if trade.get('premium_collected'):
            explanation += f"Premium: ${trade.get('premium_collected'):.2f}. "
        if trade.get('max_risk'):
            explanation += f"Max risk: ${trade.get('max_risk'):.2f}. "

        if context.signal:
            explanation += f"Signal from {context.signal.source}: {context.signal.direction}"
            if context.signal.confidence:
                explanation += f" ({context.signal.confidence*100:.0f}% confidence)"
            explanation += ". "

        explanation += f"Market: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."

        return {"summary": summary, "full_explanation": explanation}

    if decision == DecisionType.SKIP:
        summary = f"{bot_name} SKIP - already traded today"
        explanation = f"{bot_name} has already executed its daily trade. ARES trades once per day maximum. The bot will resume scanning tomorrow."
        return {"summary": summary, "full_explanation": explanation}

    # Default
    return {
        "summary": f"{bot_name} scan completed - {decision.value}",
        "full_explanation": f"Scan completed with outcome: {decision.value}. Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."
    }


def explain_ares_decision(
    scan_number: int,
    outcome: str,
    underlying_price: float,
    vix: float,
    checks: List[Dict],
    signal_source: Optional[str] = None,
    signal_direction: Optional[str] = None,
    signal_confidence: Optional[float] = None,
    signal_win_prob: Optional[float] = None,
    oracle_advice: Optional[str] = None,
    oracle_reasoning: Optional[str] = None,
    expected_move: Optional[float] = None,
    net_gex: Optional[float] = None,
    call_wall: Optional[float] = None,
    put_wall: Optional[float] = None,
    trade_details: Optional[Dict] = None,
    error_message: Optional[str] = None
) -> Dict[str, str]:
    """
    Convenience function to explain an ARES decision.

    Returns:
        {"summary": "...", "full_explanation": "..."}
    """
    # Convert checks to CheckDetail objects
    check_details = []
    for check in checks:
        check_details.append(CheckDetail(
            name=check.get("check_name", "Unknown"),
            passed=check.get("passed", False),
            actual_value=str(check.get("value", "N/A")),
            required_value=str(check.get("threshold", "N/A")),
            explanation=check.get("reason", "")
        ))

    # Calculate distances if we have walls
    dist_call = None
    dist_put = None
    if call_wall and underlying_price:
        dist_call = ((call_wall - underlying_price) / underlying_price) * 100
    if put_wall and underlying_price:
        dist_put = ((underlying_price - put_wall) / underlying_price) * 100

    context = ScanContext(
        bot_name="ARES",
        scan_number=scan_number,
        decision_type=DecisionType(outcome),
        market=MarketContext(
            underlying_symbol="SPX",
            underlying_price=underlying_price,
            vix=vix,
            expected_move=expected_move,
            net_gex=net_gex,
            call_wall=call_wall,
            put_wall=put_wall,
            distance_to_call_wall_pct=dist_call,
            distance_to_put_wall_pct=dist_put
        ),
        signal=SignalContext(
            source=signal_source or "None",
            direction=signal_direction or "NONE",
            confidence=signal_confidence,
            win_probability=signal_win_prob,
            advice=oracle_advice,
            reasoning=oracle_reasoning
        ) if signal_source else None,
        checks=check_details if check_details else None,
        trade_details=trade_details,
        error_message=error_message
    )

    return generate_scan_explanation(context)


def explain_athena_decision(
    scan_number: int,
    outcome: str,
    underlying_price: float,
    vix: float,
    checks: List[Dict],
    signal_source: Optional[str] = None,
    signal_direction: Optional[str] = None,
    signal_confidence: Optional[float] = None,
    signal_win_prob: Optional[float] = None,
    net_gex: Optional[float] = None,
    gex_regime: Optional[str] = None,
    call_wall: Optional[float] = None,
    put_wall: Optional[float] = None,
    risk_reward_ratio: Optional[float] = None,
    trade_details: Optional[Dict] = None,
    error_message: Optional[str] = None
) -> Dict[str, str]:
    """
    Convenience function to explain an ATHENA decision.

    Returns:
        {"summary": "...", "full_explanation": "..."}
    """
    # Convert checks to CheckDetail objects
    check_details = []
    for check in checks:
        check_details.append(CheckDetail(
            name=check.get("check_name", "Unknown"),
            passed=check.get("passed", False),
            actual_value=str(check.get("value", "N/A")),
            required_value=str(check.get("threshold", "N/A")),
            explanation=check.get("reason", "")
        ))

    # Add R:R to checks if provided
    if risk_reward_ratio is not None:
        check_details.append(CheckDetail(
            name="Risk:Reward Ratio",
            passed=risk_reward_ratio >= 1.5,
            actual_value=f"{risk_reward_ratio:.2f}:1",
            required_value="1.5:1 minimum",
            explanation="Uses GEX walls as natural profit targets and stop levels"
        ))

    # Calculate distances if we have walls
    dist_call = None
    dist_put = None
    if call_wall and underlying_price:
        dist_call = ((call_wall - underlying_price) / underlying_price) * 100
    if put_wall and underlying_price:
        dist_put = ((underlying_price - put_wall) / underlying_price) * 100

    context = ScanContext(
        bot_name="ATHENA",
        scan_number=scan_number,
        decision_type=DecisionType(outcome),
        market=MarketContext(
            underlying_symbol="SPY",
            underlying_price=underlying_price,
            vix=vix,
            net_gex=net_gex,
            gex_regime=gex_regime,
            call_wall=call_wall,
            put_wall=put_wall,
            distance_to_call_wall_pct=dist_call,
            distance_to_put_wall_pct=dist_put
        ),
        signal=SignalContext(
            source=signal_source or "None",
            direction=signal_direction or "NONE",
            confidence=signal_confidence,
            win_probability=signal_win_prob
        ) if signal_source else None,
        checks=check_details if check_details else None,
        trade_details=trade_details,
        error_message=error_message
    )

    return generate_scan_explanation(context)
