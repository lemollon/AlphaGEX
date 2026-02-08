"""
Scan Explainer - Claude AI-Powered Decision Explanations

Generates human-readable explanations for every FORTRESS and SOLOMON scan decision.
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
    """Signal information from ML/Prophet"""
    source: str  # "ML", "Prophet", "GEX", "None"
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

        # Parse the response - expect format with SUMMARY:, EXPLANATION:, WHAT_WOULD_TRIGGER_TRADE:, MARKET_INSIGHT:
        lines = explanation_text.strip().split('\n')
        summary = ""
        full_explanation = ""
        what_would_trigger = ""
        market_insight = ""

        current_section = None
        for line in lines:
            line = line.strip()
            if line.startswith("SUMMARY:"):
                current_section = "summary"
                summary = line.replace("SUMMARY:", "").strip()
            elif line.startswith("EXPLANATION:"):
                current_section = "explanation"
                full_explanation = line.replace("EXPLANATION:", "").strip()
            elif line.startswith("WHAT_WOULD_TRIGGER_TRADE:"):
                current_section = "trigger"
                what_would_trigger = line.replace("WHAT_WOULD_TRIGGER_TRADE:", "").strip()
            elif line.startswith("MARKET_INSIGHT:"):
                current_section = "insight"
                market_insight = line.replace("MARKET_INSIGHT:", "").strip()
            elif line and current_section:
                # Append to current section
                if current_section == "summary":
                    summary += " " + line
                elif current_section == "explanation":
                    full_explanation += " " + line
                elif current_section == "trigger":
                    what_would_trigger += " " + line
                elif current_section == "insight":
                    market_insight += " " + line

        # If parsing failed, use the whole response
        if not summary:
            summary = explanation_text[:200] if len(explanation_text) > 200 else explanation_text
        if not full_explanation:
            full_explanation = explanation_text

        # Build comprehensive explanation with all sections
        comprehensive_explanation = full_explanation.strip()
        if what_would_trigger:
            comprehensive_explanation += f"\n\n**What Would Trigger Trade:** {what_would_trigger.strip()}"
        if market_insight:
            comprehensive_explanation += f"\n\n**Market Insight:** {market_insight.strip()}"

        return {
            "summary": summary.strip(),
            "full_explanation": comprehensive_explanation,
            "what_would_trigger": what_would_trigger.strip(),
            "market_insight": market_insight.strip()
        }

    except Exception as e:
        print(f"Claude explanation failed: {e}, using fallback")
        return _generate_fallback_explanation(context)


def _build_explanation_prompt(context: ScanContext) -> str:
    """Build the prompt for Claude to explain the decision"""

    bot_desc = "FORTRESS (Aggressive Iron Condor - sells 0DTE iron condors once per day)" if context.bot_name == "FORTRESS" else "SOLOMON (Directional Spreads - trades up to 5x/day based on GEX signals)"

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

    # PRE-CALCULATE trigger prices for R:R ratio (Claude is bad at math!)
    rr_trigger_info = ""
    if context.market.call_wall and context.market.put_wall and context.market.underlying_price:
        call_wall = context.market.call_wall
        put_wall = context.market.put_wall
        spot = context.market.underlying_price

        # For BULLISH 1.5:1: 1.5 = (call_wall - x) / (x - put_wall) => x = (call_wall + 1.5*put_wall) / 2.5
        bullish_target = (call_wall + 1.5 * put_wall) / 2.5
        # For BEARISH 1.5:1: 1.5 = (x - put_wall) / (call_wall - x) => x = (1.5*call_wall + put_wall) / 2.5
        bearish_target = (1.5 * call_wall + put_wall) / 2.5

        # Current R:R calculations
        reward_bullish = call_wall - spot
        risk_bullish = spot - put_wall
        current_rr_bullish = reward_bullish / risk_bullish if risk_bullish > 0 else 0

        reward_bearish = spot - put_wall
        risk_bearish = call_wall - spot
        current_rr_bearish = reward_bearish / risk_bearish if risk_bearish > 0 else 0

        rr_trigger_info = f"""
PRE-CALCULATED R:R TRIGGER PRICES (use these exact numbers):
- Current BULLISH R:R: {current_rr_bullish:.2f}:1 (need 1.5:1)
- Current BEARISH R:R: {current_rr_bearish:.2f}:1 (need 1.5:1)
- For BULLISH 1.5:1 R:R: Price needs to be at ${bullish_target:.2f} (current: ${spot:.2f})
- For BEARISH 1.5:1 R:R: Price needs to be at ${bearish_target:.2f} (current: ${spot:.2f})"""

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

    prompt = f"""You are COUNSELOR, explaining a trading bot's decision to a human trader who needs to understand exactly what happened and why.

Bot: {bot_desc}
Scan #{context.scan_number}
Decision: {context.decision_type.value}
{market_str}
{signal_str}
{checks_str}
{trade_str}
{error_str}
{rr_trigger_info}

Provide a clear, detailed explanation in this EXACT format:

SUMMARY: [One sentence explaining what happened and the main reason why - be specific with numbers]

EXPLANATION: [3-4 sentences with specific numbers explaining the decision. For NO_TRADE, explain which check failed and the exact values. For TRADED, explain why conditions were favorable.]

WHAT_WOULD_TRIGGER_TRADE: [If NO_TRADE and R:R failed: Use the EXACT pre-calculated trigger prices from above - do NOT calculate your own! If TRADED: "N/A - trade executed"]

MARKET_INSIGHT: [One sentence of actionable insight - what to watch for next scan, or pattern you notice in the data]

Rules:
- Use ACTUAL numbers from the data (prices, percentages, ratios)
- Be direct and specific - traders want facts, not fluff
- CRITICAL: For R:R failures, use the PRE-CALCULATED trigger prices provided above - do NOT make up prices!
- For signal failures: state exact confidence/probability that's missing
- Always explain the WHY behind the decision"""

    return prompt


def _generate_fallback_explanation(context: ScanContext) -> Dict[str, str]:
    """Generate explanation without Claude API (rule-based fallback)"""

    bot_name = context.bot_name
    decision = context.decision_type
    market = context.market

    if decision == DecisionType.MARKET_CLOSED:
        return {
            "summary": f"{bot_name} scan skipped - market is closed",
            "full_explanation": f"The market is currently closed. {bot_name} only trades during market hours (FORTRESS: 8:30 AM - 3:55 PM CT, SOLOMON: 8:30 AM - 3:00 PM CT). No trading decisions are made outside these windows.",
            "what_would_trigger": "Market needs to open. Trading window starts at 8:30 AM CT for both FORTRESS and SOLOMON.",
            "market_insight": "Pre-market futures and overnight news should be reviewed before trading window opens."
        }

    if decision == DecisionType.BEFORE_WINDOW:
        return {
            "summary": f"{bot_name} scan skipped - before trading window",
            "full_explanation": f"Current time is before {bot_name}'s trading window. Both FORTRESS and SOLOMON start at 8:30 AM CT when the market opens. The bot is waiting for the trading window to open.",
            "what_would_trigger": f"Wait for trading window to open. {bot_name} will start scanning automatically.",
            "market_insight": "Early session often has higher volatility - first 30 minutes after open tend to set the day's range."
        }

    if decision == DecisionType.AFTER_WINDOW:
        return {
            "summary": f"{bot_name} scan skipped - after trading window",
            "full_explanation": f"Current time is after {bot_name}'s trading window. FORTRESS ends at 3:55 PM CT, SOLOMON ends at 3:00 PM CT. No new trades will be opened today.",
            "what_would_trigger": "N/A - trading window closed for today. Bot will resume tomorrow at market open.",
            "market_insight": "Review today's performance and prepare for tomorrow's session."
        }

    if decision == DecisionType.ERROR:
        return {
            "summary": f"{bot_name} scan failed - {context.error_message or 'unknown error'}",
            "full_explanation": f"An error occurred during the scan: {context.error_message or 'Unknown error'}. This prevented the bot from evaluating trading conditions. The error should be investigated.",
            "what_would_trigger": "Error needs to be resolved. Check API connections, credentials, and data availability.",
            "market_insight": "Monitor error logs and retry on next scan interval."
        }

    if decision == DecisionType.NO_TRADE:
        # Find the first failed check
        failed_check = None
        if context.checks:
            for check in context.checks:
                if not check.passed:
                    failed_check = check
                    break

        what_trigger = ""
        if failed_check:
            summary = f"{bot_name} NO_TRADE - {failed_check.name} failed ({failed_check.actual_value} vs required {failed_check.required_value})"
            explanation = f"Trade not taken because {failed_check.name} check failed. "
            explanation += f"Actual value: {failed_check.actual_value}, Required: {failed_check.required_value}. "
            if failed_check.explanation:
                explanation += failed_check.explanation
            explanation += f" Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."

            # Generate specific trigger based on which check failed
            if "rr_ratio" in failed_check.name.lower() or "risk" in failed_check.name.lower():
                if market.call_wall and market.put_wall:
                    # Calculate where price would need to be for 1.5:1 R:R
                    wall_range = market.call_wall - market.put_wall
                    bullish_trigger = market.put_wall + (wall_range * 0.4)  # 40% up from put wall = 1.5:1
                    bearish_trigger = market.call_wall - (wall_range * 0.4)  # 40% down from call wall = 1.5:1
                    what_trigger = f"For BULLISH: Price needs to drop to ~${bullish_trigger:.2f} (closer to put wall ${market.put_wall:.2f}). For BEARISH: Price needs to rise to ~${bearish_trigger:.2f} (closer to call wall ${market.call_wall:.2f})."
                else:
                    what_trigger = f"Need better R:R ratio. Current: {failed_check.actual_value}, Required: {failed_check.required_value}."
            elif "confidence" in failed_check.name.lower():
                what_trigger = f"Signal confidence needs to increase from {failed_check.actual_value} to at least {failed_check.required_value}."
            elif "prophet" in failed_check.name.lower():
                what_trigger = f"Prophet needs to change recommendation from {failed_check.actual_value} to TRADE."
            else:
                what_trigger = f"{failed_check.name} needs to change from {failed_check.actual_value} to meet threshold {failed_check.required_value}."

        elif context.signal and context.signal.advice in ["SKIP_TODAY", "STAY_OUT"]:
            summary = f"{bot_name} NO_TRADE - {context.signal.source} advised against trading"
            explanation = f"Trade not taken because {context.signal.source} recommended {context.signal.advice}. "
            if context.signal.reasoning:
                explanation += f"Reason: {context.signal.reasoning}. "
            explanation += f"Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."
            what_trigger = f"{context.signal.source} needs to change recommendation. Watch for changing market conditions."
        else:
            summary = f"{bot_name} NO_TRADE - conditions not met"
            explanation = f"Trade not taken because entry conditions were not satisfied. "
            explanation += f"Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}."
            what_trigger = "Entry conditions need to align. Continue monitoring on next scan."

        market_insight = ""
        if market.vix < 15:
            market_insight = f"VIX at {market.vix:.1f} is low - premium may be insufficient for iron condors. Higher VIX = more premium."
        elif market.vix > 25:
            market_insight = f"VIX at {market.vix:.1f} is elevated - wider spreads needed but higher premium available."
        else:
            market_insight = f"VIX at {market.vix:.1f} is normal range. Watch for GEX wall levels for directional bias."

        return {
            "summary": summary,
            "full_explanation": explanation,
            "what_would_trigger": what_trigger,
            "market_insight": market_insight
        }

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

        return {
            "summary": summary,
            "full_explanation": explanation,
            "what_would_trigger": "N/A - trade executed successfully.",
            "market_insight": "Monitor position for exit signals. Watch for price approaching GEX walls."
        }

    if decision == DecisionType.SKIP:
        summary = f"{bot_name} SKIP - already traded today"
        explanation = f"{bot_name} has already executed its daily trade. FORTRESS trades once per day maximum. The bot will resume scanning tomorrow."
        return {
            "summary": summary,
            "full_explanation": explanation,
            "what_would_trigger": "N/A - daily trade limit reached. Bot monitors existing position until close.",
            "market_insight": "Focus on managing the open position. Watch for exit signals."
        }

    # Default
    return {
        "summary": f"{bot_name} scan completed - {decision.value}",
        "full_explanation": f"Scan completed with outcome: {decision.value}. Market conditions: {market.underlying_symbol} at ${market.underlying_price:.2f}, VIX at {market.vix:.1f}.",
        "what_would_trigger": "Continue monitoring market conditions.",
        "market_insight": "Review scan details for specific requirements."
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
    Convenience function to explain an FORTRESS decision.

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
        bot_name="FORTRESS",
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


def explain_solomon_decision(
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
    Convenience function to explain an SOLOMON decision.

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
        bot_name="SOLOMON",
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
