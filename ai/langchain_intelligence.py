"""
LangChain-Powered Intelligence for AlphaGEX

This module provides an enhanced Claude AI integration using LangChain,
featuring agent-based workflows, structured outputs, and memory management.
"""

from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chains import LLMChain
from typing import Dict, List, Optional, Any
from datetime import datetime
import os
import json

# Import AlphaGEX components
from .langchain_models import (
    TradeRecommendation,
    MarketRegimeAnalysis,
    RiskAssessment,
    ConceptExplanation,
    PsychologicalAssessment,
    TradePostMortem,
    MarketMakerState,
    StrategyType
)
from .langchain_tools import (
    ALL_TOOLS,
    MARKET_ANALYSIS_TOOLS,
    TRADE_PLANNING_TOOLS,
    RISK_MANAGEMENT_TOOLS
)


class LangChainIntelligence:
    """
    Enhanced Claude AI integration using LangChain.

    Features:
    - Agent-based workflows with tool calling
    - Structured outputs with Pydantic validation
    - Conversation memory management
    - Composable prompt templates
    - Automatic retry and error handling
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-haiku-4-5-20251001",  # Haiku 4.5 (Oct 2025)
        temperature: float = 0.7,
        max_tokens: int = 4096
    ):
        """
        Initialize LangChain Intelligence

        Args:
            api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
            model: Claude model to use
            temperature: Model temperature (0-1)
            max_tokens: Maximum tokens in response
        """
        # Get API key
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY env variable.")

        # Initialize Claude model
        self.llm = ChatAnthropic(
            anthropic_api_key=self.api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

        # Initialize memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="output"
        )

        # Initialize agents (created on-demand)
        self._market_analysis_agent = None
        self._trade_planning_agent = None
        self._risk_management_agent = None

    # ========================================================================
    # AGENT CREATION
    # ========================================================================

    def _get_market_analysis_agent(self) -> AgentExecutor:
        """Create or get the market analysis agent"""
        if self._market_analysis_agent is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self._get_market_analysis_system_prompt()),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])

            agent = create_tool_calling_agent(self.llm, MARKET_ANALYSIS_TOOLS, prompt)
            self._market_analysis_agent = AgentExecutor(
                agent=agent,
                tools=MARKET_ANALYSIS_TOOLS,
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=5
            )

        return self._market_analysis_agent

    def _get_trade_planning_agent(self) -> AgentExecutor:
        """Create or get the trade planning agent"""
        if self._trade_planning_agent is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self._get_trade_planning_system_prompt()),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])

            agent = create_tool_calling_agent(self.llm, TRADE_PLANNING_TOOLS, prompt)
            self._trade_planning_agent = AgentExecutor(
                agent=agent,
                tools=TRADE_PLANNING_TOOLS,
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=10
            )

        return self._trade_planning_agent

    def _get_risk_management_agent(self) -> AgentExecutor:
        """Create or get the risk management agent"""
        if self._risk_management_agent is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self._get_risk_management_system_prompt()),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])

            agent = create_tool_calling_agent(self.llm, RISK_MANAGEMENT_TOOLS, prompt)
            self._risk_management_agent = AgentExecutor(
                agent=agent,
                tools=RISK_MANAGEMENT_TOOLS,
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=5
            )

        return self._risk_management_agent

    # ========================================================================
    # SYSTEM PROMPTS (Composable Templates)
    # ========================================================================

    def _get_base_system_prompt(self) -> str:
        """Base system prompt for all agents"""
        return """You are an expert options trading analyst specializing in Gamma Exposure (GEX) analysis and Market Maker behavior prediction.

Your expertise includes:
- Gamma Exposure (GEX) analysis and dealer positioning
- Options Greeks and their impact on trading
- Market Maker behavioral states and forced hedging
- Risk management and position sizing
- Real-time market regime analysis

Current time: {current_time}
Day of week: {day_of_week}

You provide data-driven, objective analysis with clear reasoning."""

    def _get_market_analysis_system_prompt(self) -> str:
        """System prompt for market analysis agent"""
        base = self._get_base_system_prompt()
        return base + """

MARKET ANALYSIS FOCUS:
Your task is to analyze current market conditions using GEX data, volatility indicators, and economic context.

Key responsibilities:
1. Fetch and interpret GEX data (net gamma, flip points, walls)
2. Determine Market Maker state (PANICKING, TRAPPED, HUNTING, DEFENDING, NEUTRAL)
3. Assess volatility regime using VIX and economic indicators
4. Identify key price levels and their significance
5. Explain dealer positioning and expected behavior

Use the available tools to gather data before making assessments.
Always provide confidence scores and explain your reasoning."""

    def _get_trade_planning_system_prompt(self) -> str:
        """System prompt for trade planning agent"""
        base = self._get_base_system_prompt()
        return base + """

TRADE PLANNING FOCUS:
Your task is to develop specific trade recommendations based on market analysis.

Key responsibilities:
1. Identify high-probability trade setups based on GEX regime
2. Select appropriate strikes and expirations
3. Calculate position sizing using Kelly Criterion
4. Define entry, target, and stop prices
5. Validate trade against historical similar setups
6. Ensure risk/reward meets minimum thresholds (R:R > 1.5:1)

Day-of-Week Trading Rules:
- Monday: Fresh week positioning, directional bias
- Tuesday: BEST directional day, most aggressive
- Wednesday: EXIT DAY - close directional positions by 3 PM
- Thursday: Late week momentum plays
- Friday: Gamma expiration, volatility expansion

Strategy Win Rates (from backtesting):
- NEGATIVE_GEX_SQUEEZE: 68% win rate, 3.0:1 R:R
- POSITIVE_GEX_BREAKDOWN: 62% win rate, 2.5:1 R:R
- FLIP_POINT_EXPLOSION: 75% win rate, 2.0:1 R:R
- IRON_CONDOR: 72% win rate, 0.3:1 R:R
- PREMIUM_SELLING: 65% win rate, 0.5:1 R:R

Use tools to fetch option chains, calculate Greeks, and validate against historical patterns."""

    def _get_risk_management_system_prompt(self) -> str:
        """System prompt for risk management agent"""
        base = self._get_base_system_prompt()
        return base + """

RISK MANAGEMENT FOCUS:
Your task is to validate trades against risk management criteria and prevent catastrophic losses.

Key responsibilities:
1. Validate position sizing (max 25% per trade)
2. Verify max loss limits (max 5% account risk per trade)
3. Check portfolio delta exposure
4. Identify potential risks (volatility, time decay, directional)
5. Suggest hedging strategies if needed
6. REJECT trades that violate risk rules

Risk Limits (HARD LIMITS - DO NOT EXCEED):
- Max position size: 25% of account
- Max risk per trade: 5% of account
- Max portfolio delta: +/- 2.0
- Min R:R ratio: 1.5:1 for directional, 0.3:1 for theta

You are the FINAL GATEKEEPER. When in doubt, REJECT the trade."""

    # ========================================================================
    # MAIN INTELLIGENCE METHODS
    # ========================================================================

    def analyze_market(
        self,
        symbol: str = "SPY",
        user_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze current market conditions using the market analysis agent.

        Args:
            symbol: Stock symbol to analyze
            user_query: Optional specific user question

        Returns:
            Dictionary with market analysis and recommendations
        """
        try:
            agent = self._get_market_analysis_agent()

            # Build input
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
            day_of_week = datetime.now().strftime("%A")

            input_text = f"""Analyze current market conditions for {symbol}.

Current time: {current_time}
Day of week: {day_of_week}

Please:
1. Fetch current GEX data
2. Analyze the GEX regime and Market Maker state
3. Check volatility regime (VIX level)
4. Provide trading implications

"""
            if user_query:
                input_text += f"\nUser question: {user_query}"

            # Run agent
            result = agent.invoke({
                "input": input_text,
                "chat_history": self.memory.chat_memory.messages
            })

            # Save to memory
            self.memory.save_context(
                {"input": input_text},
                {"output": result["output"]}
            )

            return {
                "success": True,
                "analysis": result["output"],
                "timestamp": current_time
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def create_trade_plan(
        self,
        symbol: str,
        account_size: float,
        current_price: float,
        user_preferences: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a structured trade plan using the trade planning agent.

        Args:
            symbol: Stock symbol
            account_size: Account size in dollars
            current_price: Current stock price
            user_preferences: Optional trading preferences

        Returns:
            Dictionary with trade recommendation
        """
        try:
            agent = self._get_trade_planning_agent()

            # Build input
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
            day_of_week = datetime.now().strftime("%A")

            input_text = f"""Create a trade plan for {symbol}.

Current price: ${current_price}
Account size: ${account_size:,.2f}
Current time: {current_time}
Day of week: {day_of_week}

Please:
1. Analyze current GEX regime
2. Identify the best strategy for current conditions
3. Find optimal strikes and expirations
4. Calculate position sizing (Kelly Criterion)
5. Define entry, target, and stop prices
6. Check similar historical trades for validation

"""
            if user_preferences:
                input_text += f"\nUser preferences: {json.dumps(user_preferences, indent=2)}"

            # Run agent
            result = agent.invoke({
                "input": input_text,
                "chat_history": self.memory.chat_memory.messages
            })

            # Save to memory
            self.memory.save_context(
                {"input": input_text},
                {"output": result["output"]}
            )

            return {
                "success": True,
                "trade_plan": result["output"],
                "timestamp": current_time
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def validate_trade(
        self,
        trade_details: Dict,
        account_size: float,
        current_portfolio_delta: float = 0
    ) -> Dict[str, Any]:
        """
        Validate a trade using the risk management agent.

        Args:
            trade_details: Trade details dictionary
            account_size: Account size in dollars
            current_portfolio_delta: Current portfolio delta

        Returns:
            Dictionary with risk validation result
        """
        try:
            agent = self._get_risk_management_agent()

            input_text = f"""Validate this trade against risk management criteria:

Trade Details:
{json.dumps(trade_details, indent=2)}

Account Size: ${account_size:,.2f}
Current Portfolio Delta: {current_portfolio_delta:.2f}

Please:
1. Check position size limits
2. Verify max loss limits
3. Assess portfolio delta impact
4. Identify key risks
5. APPROVE or REJECT the trade

"""
            # Run agent
            result = agent.invoke({
                "input": input_text,
                "chat_history": self.memory.chat_memory.messages
            })

            # Save to memory
            self.memory.save_context(
                {"input": input_text},
                {"output": result["output"]}
            )

            return {
                "success": True,
                "validation": result["output"],
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def get_structured_recommendation(
        self,
        symbol: str,
        account_size: float,
        current_price: float
    ) -> Optional[TradeRecommendation]:
        """
        Get a fully structured and validated trade recommendation.

        This method orchestrates all three agents to produce a Pydantic-validated
        trade recommendation with guaranteed structure.

        Args:
            symbol: Stock symbol
            account_size: Account size
            current_price: Current stock price

        Returns:
            TradeRecommendation object or None if no valid trade
        """
        try:
            # Set up parser for structured output
            parser = PydanticOutputParser(pydantic_object=TradeRecommendation)

            # Create specialized chain for structured output
            prompt = ChatPromptTemplate.from_messages([
                ("system", self._get_trade_planning_system_prompt() + "\n\n{format_instructions}"),
                ("human", "{input}")
            ])

            chain = prompt | self.llm | parser

            # Build input
            input_text = f"""Create a structured trade recommendation for {symbol}.

Current price: ${current_price}
Account size: ${account_size:,.2f}
Current time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

First, analyze the market using available context, then provide a complete trade recommendation
in the required JSON format."""

            # Run chain
            recommendation = chain.invoke({
                "input": input_text,
                "format_instructions": parser.get_format_instructions()
            })

            return recommendation

        except Exception as e:
            print(f"Failed to generate structured recommendation: {e}")
            return None

    # ========================================================================
    # MEMORY MANAGEMENT
    # ========================================================================

    def clear_memory(self):
        """Clear conversation memory"""
        self.memory.clear()

    def get_conversation_history(self) -> List[Dict]:
        """Get conversation history"""
        messages = self.memory.chat_memory.messages
        return [
            {
                "role": "human" if isinstance(msg, HumanMessage) else "ai",
                "content": msg.content
            }
            for msg in messages
        ]

    def save_conversation(self, filepath: str):
        """Save conversation history to file"""
        history = self.get_conversation_history()
        with open(filepath, 'w') as f:
            json.dump(history, f, indent=2)

    def load_conversation(self, filepath: str):
        """Load conversation history from file"""
        with open(filepath, 'r') as f:
            history = json.load(f)

        self.clear_memory()
        for msg in history:
            if msg["role"] == "human":
                self.memory.chat_memory.add_message(HumanMessage(content=msg["content"]))
            else:
                self.memory.chat_memory.add_message(AIMessage(content=msg["content"]))


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_quick_market_analysis(symbol: str = "SPY", api_key: Optional[str] = None) -> str:
    """
    Quick market analysis without full agent setup.

    Args:
        symbol: Stock symbol
        api_key: Anthropic API key

    Returns:
        Market analysis text
    """
    intelligence = LangChainIntelligence(api_key=api_key)
    result = intelligence.analyze_market(symbol=symbol)

    if result["success"]:
        return result["analysis"]
    else:
        return f"Error: {result['error']}"


def get_trade_recommendation(
    symbol: str,
    account_size: float,
    current_price: float,
    api_key: Optional[str] = None
) -> Optional[TradeRecommendation]:
    """
    Get a structured trade recommendation.

    Args:
        symbol: Stock symbol
        account_size: Account size
        current_price: Current price
        api_key: Anthropic API key

    Returns:
        TradeRecommendation object
    """
    intelligence = LangChainIntelligence(api_key=api_key)
    return intelligence.get_structured_recommendation(symbol, account_size, current_price)
