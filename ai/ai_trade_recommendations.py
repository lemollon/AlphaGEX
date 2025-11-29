"""
AI-Powered Trade Recommendations using Claude Haiku 4.5
Generates specific, actionable trade recommendations based on live market data
"""

import os
from typing import Dict, List, Optional
from datetime import datetime
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage


class AITradeRecommendation:
    """Generate AI-powered trade recommendations using Claude Haiku 4.5"""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")

        # Use Claude Haiku 4.5 for fast, cost-effective recommendations
        self.llm = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            temperature=0.3,  # Low temperature for consistent, factual recommendations
            max_tokens=2000,
            anthropic_api_key=api_key
        )

    def generate_recommendation(
        self,
        symbol: str,
        current_price: float,
        regime_data: Dict,
        gamma_walls: Dict,
        vix_data: Optional[Dict],
        rsi_analysis: Dict,
        volume_ratio: float,
        expiration_analysis: Dict
    ) -> Dict:
        """
        Generate specific trade recommendation based on current market conditions

        Returns:
            {
                'narrative': str,  # AI-generated explanation
                'specific_trade': dict,  # Exact strikes, prices, targets
                'entry_triggers': list,  # Precise entry conditions
                'exit_triggers': list,  # Precise exit conditions
                'probability': float,  # Win probability
                'risk_reward': str,  # Risk/reward ratio
                'time_window': str  # Best time to enter
            }
        """

        # Extract key data
        call_wall = gamma_walls.get('call_wall')
        put_wall = gamma_walls.get('put_wall')
        net_gamma = gamma_walls.get('net_gamma', 0)
        regime_type = regime_data.get('primary_type', 'NEUTRAL')
        risk_level = regime_data.get('risk_level', 'medium')

        # Build comprehensive context for AI
        market_context = self._build_market_context(
            symbol, current_price, regime_data, gamma_walls,
            vix_data, rsi_analysis, volume_ratio, expiration_analysis
        )

        # Create prompt for Claude
        prompt = self._create_recommendation_prompt(market_context)

        # Get AI recommendation
        try:
            response = self.llm.invoke([
                SystemMessage(content="""You are an expert options trader and market structure analyst.
Your job is to generate SPECIFIC, ACTIONABLE trade recommendations based on gamma exposure, dealer positioning, and volatility regimes.

CRITICAL RULES:
1. Always provide EXACT strike prices (not ranges or "approximately")
2. Calculate precise entry/exit prices based on the data
3. Use dealer mechanics to explain WHY the trade works
4. Provide specific volume/price triggers for entry
5. Give concrete probability estimates based on historical patterns
6. Be honest - if there's no good setup, say "Wait for better conditions"
7. Focus on asymmetric risk/reward setups (2:1 minimum)
8. Include timing - when is the best entry window

Format your response as JSON with these exact keys:
- narrative: Natural language explanation of what's happening
- specific_trade: {strike, option_type, expiration, entry_price, target, stop}
- entry_triggers: List of precise conditions to enter
- exit_triggers: List of precise conditions to exit
- probability: Win probability as integer 0-100
- risk_reward: e.g. "2.5:1"
- time_window: Best entry time"""),
                HumanMessage(content=prompt)
            ])

            # Parse AI response
            recommendation = self._parse_ai_response(response.content)

            # Add metadata
            recommendation['generated_at'] = datetime.now().isoformat()
            recommendation['regime_type'] = regime_type
            recommendation['confidence'] = regime_data.get('confidence', 0)

            return recommendation

        except Exception as e:
            print(f"❌ AI recommendation error: {e}")
            return self._get_fallback_recommendation(regime_type, current_price)

    def _build_market_context(
        self,
        symbol: str,
        current_price: float,
        regime_data: Dict,
        gamma_walls: Dict,
        vix_data: Optional[Dict],
        rsi_analysis: Dict,
        volume_ratio: float,
        expiration_analysis: Dict
    ) -> str:
        """Build comprehensive market context for AI"""

        context_parts = []

        # Symbol and price
        context_parts.append(f"Symbol: {symbol}")
        context_parts.append(f"Current Price: ${current_price:.2f}")

        # Gamma walls
        call_wall = gamma_walls.get('call_wall')
        put_wall = gamma_walls.get('put_wall')
        net_gamma = gamma_walls.get('net_gamma', 0) / 1e9  # Convert to billions

        if call_wall:
            call_strike = call_wall.get('strike')
            call_dist = call_wall.get('distance_pct')
            if call_strike and call_dist:
                context_parts.append(f"Call Wall: ${call_strike:.2f} ({call_dist:+.1f}% away)")

        if put_wall:
            put_strike = put_wall.get('strike')
            put_dist = put_wall.get('distance_pct')
            if put_strike and put_dist:
                context_parts.append(f"Put Wall: ${put_strike:.2f} ({put_dist:+.1f}% away)")

        context_parts.append(f"Net Gamma: ${net_gamma:.2f}B ({'SHORT - Dealer Amplification' if net_gamma < 0 else 'LONG - Dealer Dampening'})")

        # VIX data
        if vix_data:
            vix_current = vix_data.get('current', 0)
            vix_change = vix_data.get('change_pct', 0)
            vix_ma = vix_data.get('ma_20', 0)
            spike = vix_data.get('spike_detected', False)
            context_parts.append(f"VIX: {vix_current:.2f} ({vix_change:+.2f}% change, 20MA: {vix_ma:.2f}, Spike: {spike})")

        # RSI
        rsi_score = rsi_analysis.get('score', 0)
        individual_rsi = rsi_analysis.get('individual_rsi', {})
        overbought = rsi_analysis.get('aligned_count', {}).get('overbought', 0)
        oversold = rsi_analysis.get('aligned_count', {}).get('oversold', 0)
        context_parts.append(f"RSI Score: {rsi_score:.0f} (5m: {individual_rsi.get('5m', 0):.0f}, 1h: {individual_rsi.get('1h', 0):.0f}, 1d: {individual_rsi.get('1d', 0):.0f})")
        context_parts.append(f"Overbought: {overbought}/5 timeframes, Oversold: {oversold}/5 timeframes")

        # Volume
        context_parts.append(f"Volume Ratio: {volume_ratio:.2f}x average")

        # Regime
        regime_type = regime_data.get('primary_type', 'NEUTRAL')
        confidence = regime_data.get('confidence', 0)
        risk = regime_data.get('risk_level', 'medium')
        context_parts.append(f"Regime: {regime_type} (Confidence: {confidence}%, Risk: {risk})")
        context_parts.append(f"Description: {regime_data.get('description', 'N/A')}")

        # Expiration analysis
        liberation = expiration_analysis.get('liberation_candidates', [])
        false_floors = expiration_analysis.get('false_floor_candidates', [])
        if liberation:
            context_parts.append(f"Liberation Setups: {len(liberation)} detected")
        if false_floors:
            context_parts.append(f"False Floors: {len(false_floors)} detected")

        return "\n".join(context_parts)

    def _create_recommendation_prompt(self, market_context: str) -> str:
        """Create prompt for AI"""

        return f"""Based on the following live market data, generate a specific trade recommendation:

{market_context}

Analyze the dealer positioning, gamma walls, volatility regime, and RSI setup to determine:
1. Is there a HIGH-PROBABILITY trade setup right now?
2. If YES: What EXACT option strike, expiration, entry price, target, and stop?
3. WHY does this trade work from a dealer hedging / gamma mechanics perspective?
4. What are the PRECISE entry triggers (price level + volume confirmation)?
5. What is the estimated win probability based on the setup?
6. What is the best TIME to enter this trade?

If there's NO good setup, explain what's missing and what conditions to wait for.

Return your analysis as JSON."""

    def _parse_ai_response(self, response_text: str) -> Dict:
        """Parse AI response into structured format"""
        import json

        try:
            # Try to extract JSON from response
            # Claude sometimes wraps JSON in markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            else:
                json_str = response_text.strip()

            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError, Exception):
            # Fallback: return as narrative when JSON parsing fails
            return {
                'narrative': response_text,
                'specific_trade': None,
                'entry_triggers': [],
                'exit_triggers': [],
                'probability': 0,
                'risk_reward': 'N/A',
                'time_window': 'N/A'
            }

    def _get_fallback_recommendation(self, regime_type: str, current_price: float) -> Dict:
        """Fallback recommendation if AI fails"""

        return {
            'narrative': f"AI recommendation temporarily unavailable. Current regime: {regime_type}. Review gamma walls and RSI for manual analysis.",
            'specific_trade': None,
            'entry_triggers': ["Wait for AI recommendation system to reconnect"],
            'exit_triggers': [],
            'probability': 0,
            'risk_reward': 'N/A',
            'time_window': 'N/A',
            'generated_at': datetime.now().isoformat(),
            'regime_type': regime_type,
            'confidence': 0
        }


def get_ai_recommendation(
    symbol: str,
    analysis: Dict
) -> Dict:
    """
    Convenience function to generate AI recommendation from analysis

    Args:
        symbol: Stock symbol (e.g. 'SPY')
        analysis: Full analysis dict from analyze_current_market_complete()

    Returns:
        AI-generated trade recommendation
    """

    recommender = AITradeRecommendation()

    return recommender.generate_recommendation(
        symbol=symbol,
        current_price=analysis.get('spy_price', 0),
        regime_data=analysis.get('regime', {}),
        gamma_walls=analysis.get('current_walls', {}),
        vix_data=analysis.get('vix_data'),
        rsi_analysis=analysis.get('rsi_analysis', {}),
        volume_ratio=analysis.get('volume_ratio', 1.0),
        expiration_analysis=analysis.get('expiration_analysis', {})
    )
