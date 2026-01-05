"""
SOLOMON AI Analyst - Claude-Powered Trade Analysis
===================================================

Uses Claude AI to analyze trading performance and provide intelligent
recommendations for the Solomon feedback loop.

Features:
- Analyze WHY a bot is underperforming
- Suggest specific parameter adjustments
- Provide reasoning for proposals
- Weekend market analysis and Monday predictions
- Cross-bot pattern recognition

Author: AlphaGEX Quant
Date: 2024-12
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Claude AI
try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    anthropic = None
    logger.info("Anthropic SDK not available for Solomon AI analysis")


@dataclass
class AnalysisResult:
    """Result of Claude AI analysis"""
    analysis_type: str
    bot_name: str
    summary: str
    findings: List[str]
    recommendations: List[str]
    confidence: float  # 0-1
    reasoning: str
    suggested_actions: List[Dict]
    raw_response: str
    timestamp: datetime

    def to_dict(self) -> Dict:
        return {
            'analysis_type': self.analysis_type,
            'bot_name': self.bot_name,
            'summary': self.summary,
            'findings': self.findings,
            'recommendations': self.recommendations,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'suggested_actions': self.suggested_actions,
            'timestamp': self.timestamp.isoformat()
        }


class SolomonAIAnalyst:
    """
    Claude-powered AI analyst for Solomon feedback loop.

    Provides deep analysis of trading performance and intelligent
    recommendations for improvements.
    """

    def __init__(self):
        self.client = None
        logger.info("[SOLOMON AI] Initializing Solomon AI Analyst...")
        if CLAUDE_AVAILABLE:
            api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
                logger.info("[SOLOMON AI] Claude API client initialized successfully")
                logger.info("[SOLOMON AI] Model: claude-sonnet-4-20250514")
            else:
                logger.warning("[SOLOMON AI] No Anthropic API key found - AI analysis will use fallback mode")
        else:
            logger.warning("[SOLOMON AI] Anthropic SDK not available - AI analysis disabled")

    def is_available(self) -> bool:
        """Check if AI analysis is available"""
        return self.client is not None

    def _call_claude(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """Make a Claude API call"""
        if not self.client:
            logger.debug("[SOLOMON AI] Claude client not available, skipping API call")
            return None

        try:
            logger.info("[SOLOMON AI] Making Claude API call...")
            logger.debug(f"[SOLOMON AI]   System prompt length: {len(system_prompt)} chars")
            logger.debug(f"[SOLOMON AI]   User prompt length: {len(user_prompt)} chars")
            logger.debug(f"[SOLOMON AI]   Max tokens: {max_tokens}")

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            response_text = response.content[0].text
            logger.info(f"[SOLOMON AI] Claude API call successful - response: {len(response_text)} chars")
            return response_text
        except Exception as e:
            logger.error(f"[SOLOMON AI] Claude API error: {e}")
            logger.error(f"[SOLOMON AI]   Request details - max_tokens: {max_tokens}, system_prompt_len: {len(system_prompt)}")
            return None

    def analyze_performance_drop(
        self,
        bot_name: str,
        recent_trades: List[Dict],
        historical_stats: Dict,
        market_conditions: Dict
    ) -> Optional[AnalysisResult]:
        """
        Analyze why a bot's performance has dropped.

        Args:
            bot_name: Name of the bot
            recent_trades: List of recent trade data
            historical_stats: Historical performance metrics
            market_conditions: Current market conditions (VIX, regime, etc.)

        Returns:
            AnalysisResult with findings and recommendations
        """
        logger.info(f"[SOLOMON AI] Analyzing performance drop for {bot_name}")
        logger.info(f"[SOLOMON AI]   Recent trades: {len(recent_trades)}")
        logger.info(f"[SOLOMON AI]   Previous win rate: {historical_stats.get('prev_win_rate', 'N/A')}%")
        logger.info(f"[SOLOMON AI]   Current win rate: {historical_stats.get('recent_win_rate', 'N/A')}%")
        logger.info(f"[SOLOMON AI]   Degradation: {historical_stats.get('degradation_pct', 'N/A')}%")
        logger.info(f"[SOLOMON AI]   VIX: {market_conditions.get('vix', 'N/A')}")
        logger.info(f"[SOLOMON AI]   GEX Regime: {market_conditions.get('gex_regime', 'N/A')}")

        if not self.client:
            logger.info(f"[SOLOMON AI] Using fallback analysis (Claude not available)")
            return self._fallback_analysis(bot_name, recent_trades, historical_stats)

        system_prompt = """You are Solomon, an expert trading system analyst for the AlphaGEX platform.
Your role is to analyze trading bot performance and provide actionable recommendations.

You analyze:
- ARES: Aggressive 0DTE Iron Condor strategy on SPX
- ATHENA: GEX-based directional spreads
- PEGASUS: SPX Iron Condor
- PHOENIX: 0DTE SPY/SPX options

Provide your analysis in JSON format with these fields:
{
    "summary": "One sentence summary of the issue",
    "findings": ["Finding 1", "Finding 2", ...],
    "recommendations": ["Recommendation 1", "Recommendation 2", ...],
    "confidence": 0.0-1.0,
    "reasoning": "Detailed explanation of your analysis",
    "suggested_actions": [
        {"action": "ADJUST_PARAMETER", "parameter": "name", "current": "X", "suggested": "Y", "reason": "why"},
        {"action": "KILL_SWITCH", "reason": "why"},
        {"action": "ROLLBACK", "to_version": "X", "reason": "why"}
    ]
}"""

        # Build trade summary
        trade_summary = self._summarize_trades(recent_trades)

        user_prompt = f"""Analyze the performance drop for {bot_name}:

## Recent Trades (Last 10)
{json.dumps(trade_summary, indent=2)}

## Historical Performance
- Previous 30-day win rate: {historical_stats.get('prev_win_rate', 'N/A')}%
- Current 7-day win rate: {historical_stats.get('recent_win_rate', 'N/A')}%
- Degradation: {historical_stats.get('degradation_pct', 'N/A')}%
- Average P&L per trade (historical): ${historical_stats.get('avg_pnl', 0):.2f}
- Current streak: {historical_stats.get('streak', 'N/A')}

## Current Market Conditions
- VIX: {market_conditions.get('vix', 'N/A')}
- GEX Regime: {market_conditions.get('gex_regime', 'N/A')}
- SPX Price: ${market_conditions.get('spx_price', 'N/A')}
- Trend: {market_conditions.get('trend', 'N/A')}

What is causing the performance drop? What should we do about it?
Focus on actionable recommendations specific to this bot's strategy."""

        response = self._call_claude(system_prompt, user_prompt)

        if not response:
            logger.info(f"[SOLOMON AI] No response from Claude, using fallback analysis for {bot_name}")
            return self._fallback_analysis(bot_name, recent_trades, historical_stats)

        try:
            # Parse JSON response
            # Find JSON in response (Claude sometimes adds text around it)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
            else:
                data = json.loads(response)

            result = AnalysisResult(
                analysis_type="PERFORMANCE_DROP",
                bot_name=bot_name,
                summary=data.get('summary', 'Analysis complete'),
                findings=data.get('findings', []),
                recommendations=data.get('recommendations', []),
                confidence=data.get('confidence', 0.5),
                reasoning=data.get('reasoning', ''),
                suggested_actions=data.get('suggested_actions', []),
                raw_response=response,
                timestamp=datetime.now(CENTRAL_TZ)
            )

            # Enhanced logging of analysis results
            logger.info(f"[SOLOMON AI] Analysis complete for {bot_name}")
            logger.info(f"[SOLOMON AI]   Summary: {result.summary}")
            logger.info(f"[SOLOMON AI]   Confidence: {result.confidence:.0%}")
            logger.info(f"[SOLOMON AI]   Findings: {len(result.findings)}")
            for i, finding in enumerate(result.findings[:3], 1):
                logger.info(f"[SOLOMON AI]     {i}. {finding}")
            logger.info(f"[SOLOMON AI]   Recommendations: {len(result.recommendations)}")
            for i, rec in enumerate(result.recommendations[:3], 1):
                logger.info(f"[SOLOMON AI]     {i}. {rec}")
            logger.info(f"[SOLOMON AI]   Suggested actions: {len(result.suggested_actions)}")
            for action in result.suggested_actions:
                logger.info(f"[SOLOMON AI]     - {action.get('action', 'UNKNOWN')}: {action.get('reason', 'No reason')}")

            return result
        except json.JSONDecodeError:
            logger.warning(f"[SOLOMON AI] Could not parse Claude response as JSON for {bot_name}")
            return AnalysisResult(
                analysis_type="PERFORMANCE_DROP",
                bot_name=bot_name,
                summary="Analysis complete (unstructured response)",
                findings=[],
                recommendations=[],
                confidence=0.5,
                reasoning=response,
                suggested_actions=[],
                raw_response=response,
                timestamp=datetime.now(CENTRAL_TZ)
            )

    def _summarize_trades(self, trades: List[Dict]) -> List[Dict]:
        """Summarize trades for analysis"""
        summary = []
        for trade in trades[:10]:  # Last 10 trades
            summary.append({
                'date': trade.get('trade_date', trade.get('open_date', 'N/A')),
                'outcome': trade.get('outcome', 'N/A'),
                'pnl': trade.get('realized_pnl', trade.get('net_pnl', 0)),
                'entry_price': trade.get('underlying_at_entry', trade.get('spot_price', 'N/A')),
                'vix': trade.get('vix_at_entry', trade.get('vix', 'N/A')),
                'strategy': trade.get('strategy', 'N/A')
            })
        return summary

    def _fallback_analysis(
        self,
        bot_name: str,
        recent_trades: List[Dict],
        historical_stats: Dict
    ) -> AnalysisResult:
        """Provide basic analysis when Claude is not available"""
        logger.info(f"[SOLOMON AI FALLBACK] Running fallback analysis for {bot_name}")
        findings = []
        recommendations = []
        suggested_actions = []

        # Basic pattern detection
        losses = [t for t in recent_trades if t.get('realized_pnl', t.get('net_pnl', 0)) < 0]
        wins = [t for t in recent_trades if t.get('realized_pnl', t.get('net_pnl', 0)) > 0]
        logger.info(f"[SOLOMON AI FALLBACK]   Trade analysis: {len(wins)} wins, {len(losses)} losses")

        if len(losses) > len(wins):
            findings.append(f"More losses ({len(losses)}) than wins ({len(wins)}) in recent period")

        # Check for consecutive losses
        consecutive = 0
        for trade in recent_trades:
            if trade.get('realized_pnl', trade.get('net_pnl', 0)) < 0:
                consecutive += 1
            else:
                break
        if consecutive >= 3:
            findings.append(f"{consecutive} consecutive losses detected")
            recommendations.append("Consider pausing trading to reassess market conditions")
            if consecutive >= 5:
                suggested_actions.append({
                    "action": "KILL_SWITCH",
                    "reason": f"{consecutive} consecutive losses"
                })

        # Check degradation
        degradation = historical_stats.get('degradation_pct', 0)
        if degradation > 20:
            findings.append(f"Significant degradation: {degradation:.1f}%")
            recommendations.append("Consider rolling back to previous version")
            suggested_actions.append({
                "action": "ROLLBACK",
                "reason": f"Performance degraded by {degradation:.1f}%"
            })

        result = AnalysisResult(
            analysis_type="PERFORMANCE_DROP",
            bot_name=bot_name,
            summary=f"Basic analysis for {bot_name}: {len(findings)} issues found",
            findings=findings,
            recommendations=recommendations,
            confidence=0.6,
            reasoning="Automated pattern detection (Claude not available)",
            suggested_actions=suggested_actions,
            raw_response="",
            timestamp=datetime.now(CENTRAL_TZ)
        )

        logger.info(f"[SOLOMON AI FALLBACK] Fallback analysis complete for {bot_name}")
        logger.info(f"[SOLOMON AI FALLBACK]   Issues found: {len(findings)}")
        for finding in findings:
            logger.info(f"[SOLOMON AI FALLBACK]     - {finding}")
        logger.info(f"[SOLOMON AI FALLBACK]   Recommendations: {len(recommendations)}")
        logger.info(f"[SOLOMON AI FALLBACK]   Suggested actions: {len(suggested_actions)}")
        for action in suggested_actions:
            logger.warning(f"[SOLOMON AI FALLBACK]     - {action.get('action')}: {action.get('reason')}")

        return result

    def generate_proposal_reasoning(
        self,
        bot_name: str,
        proposal_type: str,
        current_value: Dict,
        proposed_value: Dict,
        supporting_metrics: Dict
    ) -> str:
        """
        Generate detailed reasoning for a proposal using Claude.

        Returns a well-written explanation for why this change is recommended.
        """
        if not self.client:
            return self._fallback_proposal_reasoning(proposal_type, current_value, proposed_value)

        system_prompt = """You are Solomon, writing proposal justifications for trading system changes.
Write clear, concise explanations that a human reviewer can quickly understand.
Focus on the WHY - what problem does this solve and what improvement is expected?
Keep it to 2-3 paragraphs maximum."""

        user_prompt = f"""Write a proposal justification for {bot_name}:

Proposal Type: {proposal_type}

Current Configuration:
{json.dumps(current_value, indent=2)}

Proposed Configuration:
{json.dumps(proposed_value, indent=2)}

Supporting Metrics:
{json.dumps(supporting_metrics, indent=2)}

Write a clear explanation of why this change is recommended."""

        response = self._call_claude(system_prompt, user_prompt, max_tokens=500)
        return response or self._fallback_proposal_reasoning(proposal_type, current_value, proposed_value)

    def _fallback_proposal_reasoning(
        self,
        proposal_type: str,
        current_value: Dict,
        proposed_value: Dict
    ) -> str:
        """Generate basic proposal reasoning without Claude"""
        changes = []
        for key in set(list(current_value.keys()) + list(proposed_value.keys())):
            curr = current_value.get(key)
            prop = proposed_value.get(key)
            if curr != prop:
                changes.append(f"- {key}: {curr} → {prop}")

        change_text = "\n".join(changes) if changes else "No specific changes identified"

        return f"""This {proposal_type.lower().replace('_', ' ')} is recommended based on recent performance analysis.

Changes proposed:
{change_text}

Review the supporting metrics and approve if the changes align with risk tolerance."""

    def weekend_market_analysis(self, market_data: Dict, bot_performance: Dict) -> Optional[AnalysisResult]:
        """
        Perform weekend analysis to prepare for Monday trading.

        Analyzes:
        - VIX futures and expected volatility
        - Major events coming up
        - Each bot's recent performance
        - Recommendations for Monday
        """
        logger.info(f"[SOLOMON AI] Performing weekend market analysis...")
        logger.info(f"[SOLOMON AI]   Target date: Monday {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')}")
        logger.info(f"[SOLOMON AI]   VIX: {market_data.get('vix', 'N/A')}")
        logger.info(f"[SOLOMON AI]   VIX Futures: {market_data.get('vix_futures', 'N/A')}")
        logger.info(f"[SOLOMON AI]   Bots to analyze: {list(bot_performance.keys())}")

        if not self.client:
            logger.warning("[SOLOMON AI] Claude not available for weekend analysis")
            return None

        system_prompt = """You are Solomon, providing weekend market analysis for the AlphaGEX trading system.
Your job is to prepare the team for Monday trading by analyzing:
1. Current market conditions and expected volatility
2. Each bot's recent performance
3. Specific recommendations for each bot on Monday

Provide analysis in JSON format:
{
    "summary": "Market outlook summary",
    "market_outlook": "bullish/bearish/neutral",
    "volatility_expectation": "high/medium/low",
    "findings": ["Finding 1", ...],
    "bot_recommendations": {
        "ARES": {"action": "TRADE/PAUSE/REDUCE_SIZE", "reason": "why"},
        "ATHENA": {"action": "...", "reason": "..."},
        "PEGASUS": {"action": "...", "reason": "..."},
        "PHOENIX": {"action": "...", "reason": "..."}
    },
    "suggested_actions": [...]
}"""

        user_prompt = f"""Perform weekend analysis for Monday {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')}:

## Current Market Data
- VIX: {market_data.get('vix', 'N/A')}
- VIX Futures (Monday): {market_data.get('vix_futures', 'N/A')}
- SPX: ${market_data.get('spx_price', 'N/A')}
- SPY: ${market_data.get('spy_price', 'N/A')}
- 10Y Yield: {market_data.get('yield_10y', 'N/A')}%

## Bot Performance (Last 5 Trading Days)
{json.dumps(bot_performance, indent=2)}

## Known Events Next Week
{json.dumps(market_data.get('events', []), indent=2)}

What should we do on Monday? Be specific about each bot."""

        response = self._call_claude(system_prompt, user_prompt)

        if not response:
            return None

        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
            else:
                data = json.loads(response)

            return AnalysisResult(
                analysis_type="WEEKEND_ANALYSIS",
                bot_name="ALL",
                summary=data.get('summary', 'Weekend analysis complete'),
                findings=data.get('findings', []),
                recommendations=[],
                confidence=0.7,
                reasoning=f"Market outlook: {data.get('market_outlook', 'N/A')}, Volatility: {data.get('volatility_expectation', 'N/A')}",
                suggested_actions=data.get('suggested_actions', []),
                raw_response=response,
                timestamp=datetime.now(CENTRAL_TZ)
            )
        except json.JSONDecodeError:
            return None

    def analyze_cross_bot_patterns(self, all_trades: Dict[str, List[Dict]]) -> Optional[AnalysisResult]:
        """
        Analyze patterns across all bots to find correlations.

        Example: "When ARES loses, ATHENA also loses 70% of the time"
        """
        if not self.client:
            return None

        system_prompt = """You are Solomon, analyzing patterns across multiple trading bots.
Look for correlations:
- Do certain bots fail together?
- Are there common market conditions when all bots struggle?
- Can one bot's performance predict another's?

Provide analysis in JSON format:
{
    "summary": "Cross-bot analysis summary",
    "correlations": [
        {"bots": ["BOT1", "BOT2"], "pattern": "description", "strength": "high/medium/low"}
    ],
    "systemic_risks": ["Risk 1", ...],
    "recommendations": ["Recommendation 1", ...],
    "suggested_actions": [...]
}"""

        user_prompt = f"""Analyze cross-bot patterns:

## Recent Trades by Bot
{json.dumps({bot: self._summarize_trades(trades) for bot, trades in all_trades.items()}, indent=2)}

Find correlations and systemic patterns."""

        response = self._call_claude(system_prompt, user_prompt)

        if not response:
            return None

        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            data = json.loads(response[json_start:json_end])

            return AnalysisResult(
                analysis_type="CROSS_BOT_ANALYSIS",
                bot_name="ALL",
                summary=data.get('summary', 'Cross-bot analysis complete'),
                findings=data.get('systemic_risks', []),
                recommendations=data.get('recommendations', []),
                confidence=0.6,
                reasoning=str(data.get('correlations', [])),
                suggested_actions=data.get('suggested_actions', []),
                raw_response=response,
                timestamp=datetime.now(CENTRAL_TZ)
            )
        except json.JSONDecodeError:
            return None

    def analyze_time_of_day_patterns(self, bot_name: str, trades: List[Dict]) -> Optional[Dict]:
        """
        Analyze performance by time of day.

        Returns optimal trading windows and times to avoid.
        """
        if not self.client:
            return self._fallback_time_analysis(trades)

        system_prompt = """You are Solomon, analyzing trading performance by time of day.
Identify:
- Best performing time windows
- Worst performing time windows
- Recommended trading schedule adjustments

Provide analysis in JSON format:
{
    "best_windows": [{"start": "HH:MM", "end": "HH:MM", "win_rate": X}],
    "worst_windows": [{"start": "HH:MM", "end": "HH:MM", "win_rate": X}],
    "recommendation": "Suggested schedule adjustment",
    "confidence": 0.0-1.0
}"""

        # Group trades by hour
        hourly_stats = {}
        for trade in trades:
            entry_time = trade.get('entry_time', trade.get('open_date', ''))
            if entry_time:
                try:
                    if isinstance(entry_time, str):
                        dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    else:
                        dt = entry_time
                    hour = dt.hour
                    if hour not in hourly_stats:
                        hourly_stats[hour] = {'wins': 0, 'losses': 0, 'total_pnl': 0}

                    pnl = trade.get('realized_pnl', trade.get('net_pnl', 0))
                    if pnl > 0:
                        hourly_stats[hour]['wins'] += 1
                    else:
                        hourly_stats[hour]['losses'] += 1
                    hourly_stats[hour]['total_pnl'] += pnl
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug(f"Could not parse entry_time for trade: {e}")
                    continue

        user_prompt = f"""Analyze time-of-day performance for {bot_name}:

## Hourly Statistics
{json.dumps(hourly_stats, indent=2)}

Identify optimal trading windows."""

        response = self._call_claude(system_prompt, user_prompt, max_tokens=500)

        if response:
            try:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                return json.loads(response[json_start:json_end])
            except (json.JSONDecodeError, ValueError, IndexError) as e:
                logger.debug(f"Could not parse time analysis response as JSON: {e}")

        return self._fallback_time_analysis(trades)

    def _fallback_time_analysis(self, trades: List[Dict]) -> Dict:
        """Basic time analysis without Claude"""
        return {
            "best_windows": [],
            "worst_windows": [],
            "recommendation": "Insufficient data for time analysis",
            "confidence": 0.3
        }


# Singleton
_analyst: Optional[SolomonAIAnalyst] = None


def get_analyst() -> SolomonAIAnalyst:
    """Get or create AI analyst singleton"""
    global _analyst
    if _analyst is None:
        _analyst = SolomonAIAnalyst()
    return _analyst
