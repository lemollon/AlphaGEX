"""
GEXIS Extended Thinking - Deep reasoning for complex trading decisions.

Uses Claude's Extended Thinking capability for:
- Complex strike selection analysis
- Multi-factor trade evaluation
- Risk assessment with detailed reasoning

Extended Thinking improves accuracy on complex decisions by 54%.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Central Time zone
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")


@dataclass
class ThinkingResult:
    """Result from extended thinking analysis."""
    thinking: str  # Claude's reasoning process
    conclusion: str  # Final answer/recommendation
    confidence: float  # 0-1 confidence level
    factors_considered: List[str] = field(default_factory=list)
    duration_ms: int = 0
    tokens_used: int = 0


def analyze_with_extended_thinking(
    prompt: str,
    context: Dict[str, Any],
    thinking_budget: int = 5000,
    api_key: Optional[str] = None
) -> Optional[ThinkingResult]:
    """
    Analyze a complex trading decision using Claude's Extended Thinking.

    Extended Thinking allows Claude to reason through complex problems
    step-by-step before providing an answer, improving accuracy significantly.

    Args:
        prompt: The analysis question/task
        context: Market context (GEX, VIX, positions, etc.)
        thinking_budget: Token budget for thinking (min 1024, recommended 5000-10000)
        api_key: Optional API key override

    Returns:
        ThinkingResult with reasoning and conclusion
    """
    try:
        import anthropic
        import time

        api_key = api_key or os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("Extended Thinking: No API key available")
            return None

        client = anthropic.Anthropic(api_key=api_key)

        # Build context string
        context_str = json.dumps(context, indent=2, default=str)

        system_prompt = """You are GEXIS, an expert options trading AI assistant.
You are analyzing a complex trading decision that requires careful reasoning.

Think through this systematically:
1. Assess the current market conditions
2. Evaluate the risks and opportunities
3. Consider multiple scenarios
4. Provide a clear, actionable recommendation

Be thorough but practical. Focus on factors that actually matter for the decision."""

        full_prompt = f"""## Market Context
{context_str}

## Analysis Request
{prompt}

Provide your analysis with:
1. Key factors considered
2. Your reasoning process
3. Clear recommendation with confidence level (0-100%)
4. Any important caveats or conditions"""

        start_time = time.time()

        # Use Extended Thinking
        response = client.messages.create(
            model="claude-sonnet-4-5-20250514",  # Sonnet 4.5 with extended thinking
            max_tokens=8000,
            thinking={
                "type": "enabled",
                "budget_tokens": max(1024, thinking_budget)
            },
            messages=[
                {"role": "user", "content": full_prompt}
            ],
            system=system_prompt
        )

        duration_ms = int((time.time() - start_time) * 1000)

        # Extract thinking and response
        thinking_content = ""
        response_content = ""

        for block in response.content:
            if block.type == "thinking":
                thinking_content = block.thinking
            elif block.type == "text":
                response_content = block.text

        # Parse confidence from response
        confidence = 0.7  # Default
        if "confidence" in response_content.lower():
            import re
            match = re.search(r'(\d{1,3})%?\s*confidence', response_content.lower())
            if match:
                confidence = int(match.group(1)) / 100

        # Extract factors
        factors = []
        if "factors" in response_content.lower() or "considered" in response_content.lower():
            lines = response_content.split('\n')
            for line in lines:
                if line.strip().startswith(('-', '•', '*', '1.', '2.', '3.')):
                    factor = line.strip().lstrip('-•*0123456789. ')
                    if len(factor) > 10 and len(factor) < 200:
                        factors.append(factor)

        return ThinkingResult(
            thinking=thinking_content,
            conclusion=response_content,
            confidence=confidence,
            factors_considered=factors[:10],  # Limit to 10 factors
            duration_ms=duration_ms,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens if hasattr(response, 'usage') else 0
        )

    except Exception as e:
        logger.error(f"Extended Thinking error: {e}")
        return None


def analyze_strike_selection(
    symbol: str,
    current_price: float,
    target_strikes: List[float],
    gex_data: Dict[str, Any],
    vix: float,
    strategy: str = "iron_condor",
    api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Use Extended Thinking for complex strike selection decisions.

    This is particularly useful for:
    - Edge cases where multiple strikes look viable
    - High VIX environments with unusual risk profiles
    - Gamma exposure near flip points

    Args:
        symbol: Underlying symbol
        current_price: Current price of underlying
        target_strikes: List of candidate strikes to evaluate
        gex_data: Gamma exposure data
        vix: Current VIX level
        strategy: Strategy type (iron_condor, spread, etc.)

    Returns:
        Dict with recommended strikes and reasoning
    """
    context = {
        "symbol": symbol,
        "current_price": current_price,
        "candidate_strikes": target_strikes,
        "gex": {
            "net_gex": gex_data.get("net_gex", 0),
            "flip_point": gex_data.get("flip_point", 0),
            "call_wall": gex_data.get("call_wall", 0),
            "put_wall": gex_data.get("put_wall", 0),
            "regime": gex_data.get("regime", "unknown")
        },
        "vix": vix,
        "strategy": strategy,
        "timestamp": datetime.now(CENTRAL_TZ).isoformat()
    }

    prompt = f"""For a {strategy} trade on {symbol} at ${current_price:.2f}:

Candidate strikes: {target_strikes}

Which strikes would you recommend and why?

Consider:
1. Distance from gamma walls (call_wall at {gex_data.get('call_wall')}, put_wall at {gex_data.get('put_wall')})
2. Position relative to flip point ({gex_data.get('flip_point')})
3. VIX at {vix} - implications for expected move
4. GEX regime: {gex_data.get('regime')}
5. Risk/reward tradeoffs for each strike option

Recommend the optimal strike(s) with confidence level."""

    result = analyze_with_extended_thinking(
        prompt=prompt,
        context=context,
        thinking_budget=8000,  # More budget for complex strike analysis
        api_key=api_key
    )

    if result:
        return {
            "recommended_strikes": result.factors_considered[:4],  # Top recommendations
            "reasoning": result.conclusion,
            "thinking_process": result.thinking,
            "confidence": result.confidence,
            "analysis_duration_ms": result.duration_ms,
            "context_used": context
        }

    return None


def evaluate_trade_setup(
    trade_setup: Dict[str, Any],
    market_context: Dict[str, Any],
    historical_performance: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Deep evaluation of a trade setup using Extended Thinking.

    Use this for trades that:
    - Are near the edge of entry criteria
    - Have conflicting signals
    - Occur in unusual market conditions

    Args:
        trade_setup: The proposed trade details
        market_context: Current market conditions
        historical_performance: Optional historical win rate data

    Returns:
        Evaluation with TAKE/SKIP recommendation and reasoning
    """
    context = {
        "trade": trade_setup,
        "market": market_context,
        "history": historical_performance or {},
        "timestamp": datetime.now(CENTRAL_TZ).isoformat()
    }

    prompt = """Evaluate this trade setup:

Should we TAKE or SKIP this trade?

Analyze:
1. Does this setup align with our edge?
2. What is the risk/reward profile?
3. Are there any red flags or concerns?
4. What conditions would need to change for a different decision?

Provide a clear TAKE or SKIP recommendation with confidence level and key reasons."""

    result = analyze_with_extended_thinking(
        prompt=prompt,
        context=context,
        thinking_budget=6000,
        api_key=api_key
    )

    if result:
        # Parse recommendation
        recommendation = "SKIP"  # Default to conservative
        if "take" in result.conclusion.lower()[:200]:
            recommendation = "TAKE"

        return {
            "recommendation": recommendation,
            "confidence": result.confidence,
            "reasoning": result.conclusion,
            "thinking_process": result.thinking,
            "factors": result.factors_considered,
            "duration_ms": result.duration_ms
        }

    return None


# Module initialization
logger.info("GEXIS Extended Thinking module loaded - deep reasoning enabled")
