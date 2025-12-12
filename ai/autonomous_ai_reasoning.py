"""
Autonomous Trader AI Reasoning Engine
Uses LangChain + Claude for sophisticated trade decision making

This module provides AI-powered reasoning for:
- Strike selection analysis
- Position sizing decisions
- Exit strategy recommendations
- Risk assessment
- Market regime interpretation
"""

import os
from typing import Dict, List, Optional
from datetime import datetime
import json

# Try to import LangChain and Claude (LangChain 1.0+ structure)
try:
    from langchain_core.prompts import PromptTemplate
    from langchain_classic.chains import LLMChain
    from langchain_anthropic import ChatAnthropic
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("⚠️ LangChain not available. Install with: pip install langchain langchain-anthropic langchain-core langchain-classic")


class AutonomousAIReasoning:
    """AI-powered reasoning engine for autonomous trading decisions"""

    def __init__(self):
        self.claude_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")

        if not self.claude_api_key:
            print("⚠️ Claude API key not found. Set ANTHROPIC_API_KEY or CLAUDE_API_KEY environment variable")
            self.llm = None
        elif not LANGCHAIN_AVAILABLE:
            print("⚠️ LangChain not available")
            self.llm = None
        else:
            # Initialize Claude via LangChain
            self.llm = ChatAnthropic(
                model="claude-sonnet-4-5-latest",  # Always use latest Sonnet 4.5
                anthropic_api_key=self.claude_api_key,
                temperature=0.1,  # Low temperature for consistent, logical reasoning
                max_tokens=2000
            )
            print("✅ Claude AI reasoning engine initialized (Sonnet 4.5 latest)")

    def analyze_strike_selection(self, regime: Dict, spot_price: float,
                                 alternative_strikes: List[float]) -> Dict:
        """
        Use Claude to analyze and explain strike selection

        Returns:
            {
                'recommended_strike': float,
                'reasoning': str,
                'alternative_analysis': Dict[strike, reason_why_not],
                'confidence': str,
                'warnings': List[str]
            }
        """
        if not self.llm:
            return self._fallback_strike_analysis(regime, spot_price, alternative_strikes)

        try:
            prompt = PromptTemplate(
                input_variables=["pattern", "spot", "strikes", "liberation", "magnets", "rsi"],
                template="""You are an expert options trader analyzing strike selection for SPY.

CURRENT MARKET:
- SPY Price: ${spot}
- Pattern Detected: {pattern}
- Liberation Setup: {liberation}
- Forward GEX Magnets: {magnets}
- Multi-timeframe RSI: {rsi}

STRIKE OPTIONS TO CONSIDER:
{strikes}

Analyze each strike and explain:
1. Which strike is OPTIMAL and WHY (be specific about distance from spot, proximity to gamma walls, alignment with magnets)
2. For each alternative strike, explain WHY NOT to choose it
3. What risks exist with the recommended strike
4. Confidence level (HIGH/MEDIUM/LOW) and why

Think like a professional market maker. Consider:
- Gamma exposure at each strike
- Time value decay
- Probability of profit
- Risk/reward ratio

Respond in JSON format:
{{
  "recommended_strike": <strike>,
  "reasoning": "<detailed explanation why this strike>",
  "alternatives": {{
    "<strike>": "<why not this one>",
    ...
  }},
  "confidence": "<HIGH/MEDIUM/LOW>",
  "warnings": ["<warning1>", "<warning2>"]
}}"""
            )

            chain = LLMChain(llm=self.llm, prompt=prompt)

            # Format inputs
            strikes_formatted = "\n".join([f"${strike:.0f}" for strike in alternative_strikes])

            liberation_info = "None detected"
            if regime.get('liberation_setup_detected'):
                lib_strike = regime.get('liberation_target_strike')
                lib_expiry = regime.get('liberation_expiry_date')
                liberation_info = f"Strike ${lib_strike:.0f} expiring {lib_expiry}"

            magnets_info = f"Above: ${regime.get('monthly_magnet_above', 0):.0f}, Below: ${regime.get('monthly_magnet_below', 0):.0f}"

            rsi_info = ""
            if regime.get('rsi_aligned_overbought'):
                rsi_info = "Aligned Overbought across timeframes"
            elif regime.get('rsi_aligned_oversold'):
                rsi_info = "Aligned Oversold across timeframes"
            else:
                rsi_info = "Mixed signals across timeframes"

            # Run chain
            result = chain.run(
                pattern=regime.get('primary_regime_type', 'UNKNOWN'),
                spot=f"{spot_price:.2f}",
                strikes=strikes_formatted,
                liberation=liberation_info,
                magnets=magnets_info,
                rsi=rsi_info
            )

            # Parse JSON response
            analysis = json.loads(result)

            return {
                'recommended_strike': analysis['recommended_strike'],
                'reasoning': analysis['reasoning'],
                'alternative_analysis': analysis['alternatives'],
                'confidence': analysis['confidence'],
                'warnings': analysis.get('warnings', []),
                'ai_thought_process': result,
                'langchain_chain': 'strike_selection_v1'
            }

        except Exception as e:
            print(f"⚠️ Claude strike analysis failed: {e}")
            return self._fallback_strike_analysis(regime, spot_price, alternative_strikes)

    def analyze_position_sizing(self, account_size: float, win_rate: float,
                               risk_reward: float, trade_confidence: float,
                               regime: Dict) -> Dict:
        """
        Use Claude to determine optimal position size using Kelly Criterion and risk management

        Returns:
            {
                'kelly_pct': float,
                'recommended_contracts': int,
                'sizing_rationale': str,
                'risk_warnings': List[str]
            }
        """
        if not self.llm:
            return self._fallback_position_sizing(account_size, win_rate, risk_reward, trade_confidence)

        try:
            prompt = PromptTemplate(
                input_variables=["account", "win_rate", "rr", "confidence", "pattern"],
                template="""You are an expert risk manager determining position size for an options trade.

ACCOUNT DETAILS:
- Total Capital: ${account}
- Historical Win Rate: {win_rate}%
- Risk/Reward Ratio: {rr}:1
- Trade Confidence: {confidence}%

TRADE CONTEXT:
- Pattern: {pattern}

Apply Kelly Criterion with adjustments:
1. Calculate full Kelly: (p*b - q) / b where p=win_rate, q=1-p, b=risk_reward
2. Apply fractional Kelly (1/4 to 1/2) for safety
3. Adjust based on trade confidence
4. Consider risk of ruin
5. Apply position limits (never >20% of account per trade)

Provide:
- Kelly percentage
- Recommended contracts (for SPY at ~$580, option ~$10-15)
- Detailed rationale
- Risk warnings

Respond in JSON:
{{
  "kelly_full_pct": <full kelly %>,
  "kelly_fractional_pct": <recommended fractional %>,
  "recommended_contracts": <number>,
  "max_loss_pct": <max % of account at risk>,
  "sizing_rationale": "<explanation>",
  "risk_warnings": ["<warning1>", "<warning2>"]
}}"""
            )

            chain = LLMChain(llm=self.llm, prompt=prompt)

            result = chain.run(
                account=f"{account_size:.2f}",
                win_rate=f"{win_rate:.1f}",
                rr=f"{risk_reward:.1f}",
                confidence=f"{trade_confidence:.0f}",
                pattern=regime.get('primary_regime_type', 'UNKNOWN')
            )

            sizing = json.loads(result)

            return {
                'kelly_pct': sizing['kelly_fractional_pct'],
                'recommended_contracts': sizing['recommended_contracts'],
                'sizing_rationale': sizing['sizing_rationale'],
                'risk_warnings': sizing.get('risk_warnings', []),
                'ai_thought_process': result,
                'langchain_chain': 'position_sizing_kelly_v1'
            }

        except Exception as e:
            print(f"⚠️ Claude position sizing failed: {e}")
            return self._fallback_position_sizing(account_size, win_rate, risk_reward, trade_confidence)

    def evaluate_trade_opportunity(self, regime: Dict, market_context: Dict) -> Dict:
        """
        Comprehensive trade evaluation using Claude's reasoning

        Returns:
            {
                'should_trade': bool,
                'reasoning': str,
                'confidence': str,
                'expected_outcome': str,
                'warnings': List[str]
            }
        """
        if not self.llm:
            return {'should_trade': True, 'reasoning': 'AI unavailable, using rule-based logic', 'confidence': 'MEDIUM', 'expected_outcome': 'Unknown', 'warnings': []}

        try:
            prompt = PromptTemplate(
                input_variables=["pattern", "confidence", "description", "trap", "context"],
                template="""You are an expert trader evaluating a trade opportunity.

PSYCHOLOGY TRAP ANALYSIS:
- Pattern: {pattern}
- Confidence: {confidence}%
- Description: {description}
- Psychology Trap: {trap}

MARKET CONTEXT:
{context}

Evaluate this trade:
1. Is this a high-probability setup?
2. What's the expected outcome?
3. What could go wrong?
4. Should we take this trade?

Think step-by-step like a professional trader. Consider:
- Regime validity
- Risk/reward
- Timing
- Psychology traps

Respond in JSON:
{{
  "should_trade": <true/false>,
  "reasoning": "<detailed thought process>",
  "confidence_assessment": "<HIGH/MEDIUM/LOW>",
  "expected_outcome": "<what you expect to happen>",
  "warnings": ["<warning1>", "<warning2>"]
}}"""
            )

            chain = LLMChain(llm=self.llm, prompt=prompt)

            context = f"""SPY: ${market_context['spot_price']:.2f}
Net GEX: ${market_context['net_gex']/1e9:.2f}B
VIX: {market_context['vix']:.1f}
Liberation Setup: {regime.get('liberation_setup_detected', False)}
False Floor: {regime.get('false_floor_detected', False)}"""

            result = chain.run(
                pattern=regime.get('primary_regime_type', 'UNKNOWN'),
                confidence=f"{regime.get('confidence_score', 0):.0f}",
                description=regime.get('description', 'N/A'),
                trap=regime.get('psychology_trap', 'N/A'),
                context=context
            )

            evaluation = json.loads(result)

            return {
                'should_trade': evaluation['should_trade'],
                'reasoning': evaluation['reasoning'],
                'confidence': evaluation['confidence_assessment'],
                'expected_outcome': evaluation['expected_outcome'],
                'warnings': evaluation.get('warnings', []),
                'ai_thought_process': result,
                'langchain_chain': 'trade_evaluation_v1'
            }

        except Exception as e:
            print(f"⚠️ Claude trade evaluation failed: {e}")
            return {'should_trade': True, 'reasoning': f'AI failed: {e}', 'confidence': 'MEDIUM', 'expected_outcome': 'Unknown', 'warnings': []}

    # Fallback methods when AI unavailable
    def _fallback_strike_analysis(self, regime: Dict, spot_price: float, strikes: List[float]) -> Dict:
        """Simple rule-based strike selection when AI unavailable"""
        # Choose strike closest to spot for ATM trade
        closest_strike = min(strikes, key=lambda x: abs(x - spot_price))

        return {
            'recommended_strike': closest_strike,
            'reasoning': f'Selected ${closest_strike:.0f} as it is closest to current spot ${spot_price:.2f} (AI unavailable)',
            'alternative_analysis': {str(s): 'Further from spot' for s in strikes if s != closest_strike},
            'confidence': 'MEDIUM',
            'warnings': ['AI reasoning unavailable, using rule-based selection'],
            'ai_thought_process': 'Rule-based fallback',
            'langchain_chain': 'fallback_rules'
        }

    def _fallback_position_sizing(self, account_size: float, win_rate: float,
                                  risk_reward: float, confidence: float) -> Dict:
        """Simple Kelly Criterion when AI unavailable"""
        # Kelly formula: f* = (p*b - q) / b
        p = win_rate / 100
        q = 1 - p
        b = risk_reward

        kelly_full = ((p * b) - q) / b if b > 0 else 0
        kelly_full = max(0, min(kelly_full, 1))  # Clamp 0-100%

        # Use quarter Kelly for safety
        kelly_fractional = kelly_full / 4

        # Calculate contracts (assume $15 per option, $100 multiplier)
        position_dollars = account_size * kelly_fractional
        contracts = max(1, int(position_dollars / 1500))
        contracts = min(contracts, 10)  # Max 10 contracts

        return {
            'kelly_pct': kelly_fractional * 100,
            'recommended_contracts': contracts,
            'sizing_rationale': f'Quarter Kelly: {kelly_fractional*100:.1f}% of ${account_size:.0f} = {contracts} contracts (AI unavailable)',
            'risk_warnings': ['AI unavailable, using basic Kelly Criterion'],
            'ai_thought_process': 'Rule-based Kelly fallback',
            'langchain_chain': 'fallback_kelly'
        }


# Singleton instance
_ai_reasoning_instance = None

def get_ai_reasoning() -> AutonomousAIReasoning:
    """Get singleton AI reasoning engine"""
    global _ai_reasoning_instance
    if _ai_reasoning_instance is None:
        _ai_reasoning_instance = AutonomousAIReasoning()
    return _ai_reasoning_instance
