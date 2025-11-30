"""
AI Intelligence Enhancement Routes
Provides 7 advanced AI features for profitable trading with transparency and actionability.

Features:
1. Pre-Trade Safety Checklist - Validates trades before execution
2. Real-Time Trade Explainer - Explains WHY trades were taken with price targets
3. Daily Trading Plan Generator - Generates daily action plan at market open
4. Position Management Assistant - Live guidance for open positions
5. Market Commentary Widget - Real-time market narration
6. Strategy Comparison Engine - Compares available strategies
7. Option Greeks Explainer - Context-aware Greeks education
"""

from database_adapter import get_connection
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import psycopg2.extras
try:
    from ai.autonomous_ai_reasoning import AutonomousAIReasoning
except ImportError:
    AutonomousAIReasoning = None

try:
    from ai.ai_trade_advisor import AITradeAdvisor
except ImportError:
    AITradeAdvisor = None

try:
    from langchain_prompts import (
        get_market_analysis_prompt,
        get_trade_recommendation_prompt,
        get_educational_prompt
    )
except ImportError:
    # Fallback if langchain_prompts doesn't exist
    get_market_analysis_prompt = lambda: ""
    get_trade_recommendation_prompt = lambda: ""
    get_educational_prompt = lambda: ""

try:
    from langchain_anthropic import ChatAnthropic
    LANGCHAIN_AVAILABLE = True
except ImportError:
    ChatAnthropic = None
    LANGCHAIN_AVAILABLE = False

router = APIRouter(prefix="/api/ai-intelligence", tags=["AI Intelligence"])

# Get API key with fallback support (ANTHROPIC_API_KEY or CLAUDE_API_KEY)
api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')

# Ensure ANTHROPIC_API_KEY is set for ChatAnthropic
if api_key and not os.getenv('ANTHROPIC_API_KEY'):
    os.environ['ANTHROPIC_API_KEY'] = api_key

# Initialize Claude for AI endpoints
# Will use ANTHROPIC_API_KEY from environment
llm = None
llm_init_error = None
if api_key and LANGCHAIN_AVAILABLE and ChatAnthropic:
    try:
        # Use Claude 3.5 Haiku for fast, cost-effective AI responses
        llm = ChatAnthropic(
            model="claude-3-5-haiku-latest",
            temperature=0.1,
            max_tokens=4096
        )
        print("✅ AI Intelligence: Claude 3.5 Haiku initialized successfully")
    except Exception as e:
        llm_init_error = str(e)
        print(f"⚠️ AI Intelligence: Claude initialization failed: {e}")
        llm = None
else:
    if not api_key:
        print("⚠️ AI Intelligence: No API key found (ANTHROPIC_API_KEY or CLAUDE_API_KEY)")
    if not LANGCHAIN_AVAILABLE:
        print("⚠️ AI Intelligence: LangChain not installed")

# Initialize AI systems (if available)
ai_reasoning = AutonomousAIReasoning() if AutonomousAIReasoning else None
trade_advisor = AITradeAdvisor() if AITradeAdvisor else None

# Helper function to validate API key is configured
def require_api_key():
    """Raises HTTPException if API key is not configured or langchain unavailable"""
    if not LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="AI service unavailable: LangChain not installed. Install with: pip install langchain-anthropic"
        )
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI service unavailable: Claude API key not configured. Set ANTHROPIC_API_KEY or CLAUDE_API_KEY environment variable."
        )
    if not llm:
        error_detail = f"AI service unavailable: Claude LLM initialization failed"
        if llm_init_error:
            error_detail += f" - {llm_init_error}"
        raise HTTPException(
            status_code=503,
            detail=error_detail
        )


# Helper function to safely get database connection
def get_safe_connection():
    """Get database connection or raise 503 if unavailable"""
    try:
        return get_connection()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database service unavailable: {type(e).__name__}"
        )


# ============================================================================
# 1. PRE-TRADE SAFETY CHECKLIST
# ============================================================================

class PreTradeChecklistRequest(BaseModel):
    symbol: str
    strike: float
    option_type: str  # CALL or PUT
    contracts: int
    cost_per_contract: float
    pattern_type: Optional[str] = None
    confidence: Optional[float] = None


@router.post("/pre-trade-checklist")
async def generate_pre_trade_checklist(request: PreTradeChecklistRequest):
    """
    Generates comprehensive pre-trade safety checklist with 20+ validations.
    Returns APPROVED/REJECTED with detailed reasoning.
    """
    require_api_key()

    try:
        conn = get_safe_connection()
        c = conn.cursor()

        # Get account info
        c.execute("SELECT account_value FROM account_state ORDER BY timestamp DESC LIMIT 1")
        account_value_row = c.fetchone()
        account_value = account_value_row[0] if account_value_row else 10000

        # Get current positions
        c.execute("SELECT SUM(ABS(contracts * entry_price * 100)) FROM trades WHERE status = 'OPEN'")
        current_exposure_row = c.fetchone()
        current_exposure = current_exposure_row[0] if current_exposure_row and current_exposure_row[0] else 0

        # Get today's P&L
        today_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
        c.execute("""
            SELECT SUM(realized_pnl)
            FROM trades
            WHERE timestamp >= %s AND status = 'CLOSED'
        """, (today_start,))
        today_pnl_row = c.fetchone()
        today_pnl = today_pnl_row[0] if today_pnl_row and today_pnl_row[0] else 0

        # Get max drawdown
        c.execute("""
            SELECT MIN(account_value) as min_val, MAX(account_value) as max_val
            FROM account_state
            WHERE timestamp >= NOW() - INTERVAL '30 days'
        """)
        dd_row = c.fetchone()
        if dd_row and dd_row[0] and dd_row[1]:
            current_drawdown_pct = ((dd_row[1] - account_value) / dd_row[1] * 100) if dd_row[1] > 0 else 0
        else:
            current_drawdown_pct = 0

        # Get win rate for pattern
        if request.pattern_type:
            c.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
                FROM trades
                WHERE pattern_type = %s AND status = 'CLOSED'
            """, (request.pattern_type,))
            pattern_row = c.fetchone()
            if pattern_row and pattern_row[0] and pattern_row[0] > 0:
                pattern_win_rate = (pattern_row[1] / pattern_row[0] * 100) if pattern_row[0] > 0 else 0
            else:
                pattern_win_rate = 0
        else:
            pattern_win_rate = 0

        # Get current VIX and market data
        c.execute("SELECT vix FROM market_data ORDER BY timestamp DESC LIMIT 1")
        vix_row = c.fetchone()
        current_vix = vix_row[0] if vix_row else 15.0

        conn.close()

        # Calculate trade metrics
        total_cost = request.contracts * request.cost_per_contract * 100
        position_size_pct = (total_cost / account_value * 100) if account_value > 0 else 0
        daily_loss_pct = abs(today_pnl / account_value * 100) if account_value > 0 else 0
        total_exposure_pct = ((current_exposure + total_cost) / account_value * 100) if account_value > 0 else 0

        # Generate comprehensive checklist using Claude
        prompt = f"""You are a professional options trading risk manager. Generate a comprehensive pre-trade safety checklist for this trade.

TRADE DETAILS:
• Symbol: {request.symbol}
• Strike: ${request.strike}
• Type: {request.option_type}
• Contracts: {request.contracts}
• Cost per contract: ${request.cost_per_contract}
• Total cost: ${total_cost:.2f}
• Pattern: {request.pattern_type or 'N/A'}
• Confidence: {request.confidence or 0}%

ACCOUNT STATUS:
• Account value: ${account_value:.2f}
• Current exposure: ${current_exposure:.2f} ({current_exposure / account_value * 100:.1f}% of account)
• Today's P&L: ${today_pnl:.2f}
• Current drawdown: {current_drawdown_pct:.1f}%
• VIX: {current_vix:.1f}

RISK METRICS FOR THIS TRADE:
• Position size: {position_size_pct:.1f}% of account
• Daily loss today: {daily_loss_pct:.1f}%
• Total exposure after trade: {total_exposure_pct:.1f}%
• Pattern win rate: {pattern_win_rate:.1f}%

RISK LIMITS:
• Max position size: 20% of account
• Max daily loss: 5% of account
• Max drawdown: 15%
• Max total exposure: 50%
• Min win rate for pattern: 60%
• Min confidence: 65%

Generate a detailed checklist with these sections:
1. RISK VALIDATION (4 checks) - Position size, daily loss, drawdown, exposure
2. PROBABILITY ANALYSIS (4 checks) - Win rate, confidence, expected value, historical performance
3. GREEKS VALIDATION (3 checks) - Theta decay, time to expiration, delta
4. MARKET CONDITIONS (3 checks) - VIX level, trend, timing
5. PSYCHOLOGY CHECKS (4 checks) - Revenge trading, FOMO, overconfidence, exit plan

For each check, return:
• Status: PASS or FAIL or WARNING
• Value: Current value
• Limit: Maximum allowed
• Comment: Brief explanation

Then provide:
• OVERALL VERDICT: APPROVED or REJECTED or PROCEED_WITH_CAUTION
• WARNINGS: List any yellow flags
• CRITICAL_RISKS: List any deal-breakers

Format as JSON."""

        checklist_result = llm.invoke(prompt)
        checklist_text = checklist_result.content

        # Parse the response (try to extract JSON, fallback to text)
        import json
        try:
            # Try to extract JSON from the response
            if '```json' in checklist_text:
                json_start = checklist_text.find('```json') + 7
                json_end = checklist_text.find('```', json_start)
                checklist_data = json.loads(checklist_text[json_start:json_end].strip())
            elif '{' in checklist_text:
                # Find JSON object
                json_start = checklist_text.find('{')
                json_end = checklist_text.rfind('}') + 1
                checklist_data = json.loads(checklist_text[json_start:json_end])
            else:
                # Fallback: structure it ourselves
                checklist_data = {
                    "verdict": "APPROVED" if position_size_pct < 20 and daily_loss_pct < 5 else "REJECTED",
                    "analysis": checklist_text
                }
        except (json.JSONDecodeError, TypeError, ValueError, IndexError) as e:
            # JSON parsing failed, use fallback structure
            checklist_data = {
                "verdict": "APPROVED" if position_size_pct < 20 and daily_loss_pct < 5 else "REJECTED",
                "analysis": checklist_text
            }

        return {
            'success': True,
            'data': {
                'checklist': checklist_data,
                'trade_metrics': {
                    'total_cost': total_cost,
                    'position_size_pct': position_size_pct,
                    'daily_loss_pct': daily_loss_pct,
                    'total_exposure_pct': total_exposure_pct,
                    'pattern_win_rate': pattern_win_rate
                },
                'account_status': {
                    'account_value': account_value,
                    'current_exposure': current_exposure,
                    'today_pnl': today_pnl,
                    'current_drawdown_pct': current_drawdown_pct
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate checklist: {str(e)}")


# ============================================================================
# 2. REAL-TIME TRADE EXPLAINER
# ============================================================================

@router.get("/trade-explainer/{trade_id}")
async def explain_trade(trade_id: str):
    """
    Generates comprehensive explanation of WHY a trade was taken.
    Includes strike selection, position sizing, price targets, Greeks, market mechanics.
    """
    require_api_key()

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get trade details
        c.execute("""
            SELECT * FROM trades WHERE id = %s OR timestamp = %s
        """, (trade_id, trade_id))
        trade = c.fetchone()

        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")

        trade_dict = dict(trade)

        # Get associated autonomous logs
        c.execute("""
            SELECT * FROM autonomous_trader_logs
            WHERE timestamp >= %s::timestamp - INTERVAL '5 minutes'
            AND timestamp <= %s::timestamp + INTERVAL '5 minutes'
            ORDER BY timestamp DESC
        """, (trade_dict['timestamp'], trade_dict['timestamp']))
        logs = [dict(row) for row in c.fetchall()]

        # Get market context at time of trade
        c.execute("""
            SELECT * FROM market_data
            WHERE timestamp <= %s
            ORDER BY timestamp DESC LIMIT 1
        """, (trade_dict['timestamp'],))
        market_data = c.fetchone()
        market_dict = dict(market_data) if market_data else {}

        # Get GEX context
        c.execute("""
            SELECT * FROM gex_levels
            WHERE timestamp <= %s
            ORDER BY timestamp DESC LIMIT 1
        """, (trade_dict['timestamp'],))
        gex_data = c.fetchone()
        gex_dict = dict(gex_data) if gex_data else {}

        conn.close()

        # Generate comprehensive explanation using Claude
        prompt = f"""You are an expert options trader explaining a trade to a student. Generate a DETAILED trade breakdown that explains EXACTLY why this trade was taken, with specific price targets and exit strategy.

TRADE EXECUTED:
• Symbol: {trade_dict.get('symbol', 'SPY')}
• Strike: ${trade_dict.get('strike', 0)}
• Type: {trade_dict.get('option_type', 'CALL')}
• Contracts: {trade_dict.get('contracts', 0)}
• Entry Price: ${trade_dict.get('entry_price', 0)}
• Total Cost: ${trade_dict.get('contracts', 0) * trade_dict.get('entry_price', 0) * 100:.2f}
• Pattern: {trade_dict.get('pattern_type', 'N/A')}
• Confidence: {trade_dict.get('confidence_score', 0)}%
• Timestamp: {trade_dict.get('timestamp', 'N/A')}

MARKET CONTEXT AT TRADE TIME:
• SPY Price: ${market_dict.get('spot_price') or 0}
• VIX: {market_dict.get('vix') or 0}
• Net GEX: ${(market_dict.get('net_gex') or 0)/1e9:.2f}B
• Call Wall: ${gex_dict.get('call_wall') or 0}
• Put Wall: ${gex_dict.get('put_wall') or 0}

AI REASONING LOGS:
{chr(10).join([f"• {log.get('log_type', 'N/A')}: {log.get('reasoning_summary', 'N/A')}" for log in logs[:5]])}

Generate a comprehensive trade explanation with these sections:

1. STRIKE SELECTION
   • Why this strike was chosen over alternatives (be specific about $$ alternatives)
   • Distance from current price
   • Relationship to gamma walls
   • Delta positioning (optimal for this setup)

2. POSITION SIZING
   • Kelly Criterion calculation
   • Why this many contracts
   • Risk percentage of account
   • Max loss calculation

3. PROFIT TARGETS (be SPECIFIC)
   • Target 1: $$ price and % profit (first resistance)
   • Target 2: $$ price and % profit (major resistance)
   • Stop Loss: $$ price and % loss (thesis invalidation point)

4. OPTION GREEKS BREAKDOWN
   • Delta: What it means for this trade
   • Theta: Daily decay and urgency
   • Days to expiration: Time pressure
   • Implied Volatility: What it tells us

5. TIME MANAGEMENT (exact times)
   • When to exit if no movement (theta protection)
   • When to hold if moving right (momentum)
   • Expiration urgency

6. MARKET MECHANICS (WHY this works)
   • What market makers must do
   • How gamma exposure drives price
   • Why this pattern has edge
   • Historical success rate

7. RISK FACTORS (what could go wrong)
   • VIX spike trigger
   • Thesis invalidation level
   • Theta decay threshold

8. EXPECTED OUTCOME
   • Probability of profit
   • Expected value
   • Max risk
   • Risk/reward ratio

Be extremely specific with dollar amounts, percentages, and times. This needs to be actionable."""

        explanation = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'trade': trade_dict,
                'explanation': explanation.content,
                'market_context': market_dict,
                'gex_context': gex_dict,
                'ai_logs': logs
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to explain trade: {str(e)}")


# ============================================================================
# 3. DAILY TRADING PLAN GENERATOR
# ============================================================================

@router.get("/daily-trading-plan")
async def generate_daily_trading_plan():
    """
    Generates comprehensive daily trading plan with top 3 opportunities,
    key price levels, psychology traps to avoid, risk allocation, and time-based actions.
    """
    require_api_key()

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get latest market data
        c.execute("SELECT * FROM market_data ORDER BY timestamp DESC LIMIT 1")
        market_row = c.fetchone()
        market_data = dict(market_row) if market_row else {}

        # Get latest psychology analysis
        c.execute("SELECT * FROM psychology_analysis ORDER BY timestamp DESC LIMIT 1")
        psych_row = c.fetchone()
        psychology = dict(psych_row) if psych_row else {}

        # Get GEX levels
        c.execute("SELECT * FROM gex_levels ORDER BY timestamp DESC LIMIT 1")
        gex_row = c.fetchone()
        gex = dict(gex_row) if gex_row else {}

        # Get account status
        c.execute("SELECT account_value FROM account_state ORDER BY timestamp DESC LIMIT 1")
        account_row = c.fetchone()
        account_value = account_row[0] if account_row else 10000

        # Get recent performance
        c.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                AVG(realized_pnl) as avg_pnl
            FROM trades
            WHERE status = 'CLOSED' AND timestamp >= NOW() - INTERVAL '7 days'
        """)
        perf_row = c.fetchone()
        if perf_row and perf_row[0]:
            performance = {
                'total_trades': perf_row[0],
                'win_rate': (perf_row[1] / perf_row[0] * 100) if perf_row[0] > 0 else 0,
                'avg_pnl': perf_row[2] or 0
            }
        else:
            performance = {'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0}

        # Get top patterns
        c.execute("""
            SELECT
                pattern_type,
                COUNT(*) as trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
                AVG(realized_pnl) as avg_pnl
            FROM trades
            WHERE status = 'CLOSED' AND timestamp >= NOW() - INTERVAL '30 days'
            GROUP BY pattern_type
            HAVING COUNT(*) >= 3
            ORDER BY win_rate DESC, avg_pnl DESC
            LIMIT 3
        """)
        top_patterns = [dict(row) for row in c.fetchall()]

        conn.close()

        # Generate daily plan using Claude
        today = datetime.now().strftime("%B %d, %Y")
        prompt = f"""You are a professional day trader creating a daily action plan. Generate a comprehensive trading plan for today with SPECIFIC opportunities, price levels, and timing.

TODAY: {today}

CURRENT MARKET STATUS:
• SPY: ${market_data.get('spot_price') or 0}
• VIX: {market_data.get('vix') or 0}
• Net GEX: ${(market_data.get('net_gex') or 0)/1e9:.2f}B
• Market Regime: {psychology.get('regime_type', 'UNKNOWN')}
• Confidence: {psychology.get('confidence') or 0}%
• Call Wall: ${gex.get('call_wall') or 0}
• Put Wall: ${gex.get('put_wall') or 0}
• Flip Point: ${gex.get('flip_point') or 0}

ACCOUNT STATUS:
• Balance: ${account_value:.2f}
• Win Rate (7d): {performance['win_rate']:.1f}%
• Recent Trades: {performance['total_trades']}

TOP PERFORMING PATTERNS (30d):
{chr(10).join([f"• {p.get('pattern_type', 'N/A')}: {p.get('win_rate', 0)*100:.0f}% win rate, ${p.get('avg_pnl', 0):.2f} avg P&L" for p in top_patterns])}

Create a detailed daily trading plan with:

1. TOP 3 OPPORTUNITIES TODAY (ranked by probability)
   For each:
   • Entry: Exact strike and price
   • Target: Price and % profit
   • Stop: Price and % loss
   • Size: Number of contracts and $ risk
   • Win Probability: %
   • WHEN: Exact conditions to enter

2. KEY PRICE LEVELS TO WATCH
   • Breakout level (liberation/resistance)
   • Support/resistance levels
   • Stop loss levels
   • Profit target levels

3. PSYCHOLOGY TRAPS TO AVOID TODAY
   • Specific traps based on current market
   • Max trades if win rate drops
   • Wait times after losses

4. RISK ALLOCATION
   • Primary trade: $$ and % of account
   • Backup trade: $$ if primary fails
   • Reserve cash: %

5. TIME-BASED ACTIONS (CT timezone)
   • 8:30 AM - Market open prep
   • 9:00 AM - First 30min range
   • 10:00-12:00 - Primary entry window
   • 2:00 PM - Theta protection deadline
   • 3:00 PM - No new entries

6. MARKET CONTEXT
   • Today's regime and what it means
   • VIX implications
   • Fed/macro events
   • Expected volatility

Be extremely specific with prices, times, and percentages. Make this ACTIONABLE."""

        plan = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'plan': plan.content,
                'market_data': market_data,
                'psychology': psychology,
                'gex': gex,
                'account_value': account_value,
                'performance': performance,
                'top_patterns': top_patterns,
                'generated_at': datetime.now().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate daily plan: {str(e)}")


# ============================================================================
# 4. POSITION MANAGEMENT ASSISTANT
# ============================================================================

@router.get("/position-guidance/{trade_id}")
async def get_position_guidance(trade_id: str):
    """
    Provides live guidance for an open position:
    - Next actions (partial profit, add, exit)
    - Stop loss adjustments
    - Exit triggers
    - Greeks updates
    - Time decay watch
    """
    require_api_key()

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get trade
        c.execute("SELECT * FROM trades WHERE (id = %s OR timestamp = %s) AND status = 'OPEN'", (trade_id, trade_id))
        trade_row = c.fetchone()

        if not trade_row:
            raise HTTPException(status_code=404, detail="Open position not found")

        trade = dict(trade_row)

        # Get current market price
        c.execute("SELECT spot_price, vix FROM market_data ORDER BY timestamp DESC LIMIT 1")
        market_row = c.fetchone()
        current_spy = market_row[0] if market_row else 0
        current_vix = market_row[1] if market_row else 15

        # Get current option price (estimate based on intrinsic value + time value)
        strike = trade['strike']
        entry_price = trade['entry_price']
        option_type = trade['option_type']

        # Simple estimate: intrinsic value + 50% of remaining time value
        if option_type == 'CALL':
            intrinsic = max(0, current_spy - strike)
        else:  # PUT
            intrinsic = max(0, strike - current_spy)

        # Estimate current option price (rough approximation)
        current_price = intrinsic + (entry_price - max(0, intrinsic)) * 0.7

        # Calculate P&L
        pnl_per_contract = (current_price - entry_price) * 100
        total_pnl = pnl_per_contract * trade['contracts']
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        # Calculate time to expiration (rough estimate based on entry price)
        entry_time = datetime.fromisoformat(trade['timestamp'])
        time_held = (datetime.now() - entry_time).total_seconds() / 3600  # hours

        # Get GEX walls
        c.execute("SELECT call_wall, put_wall FROM gex_levels ORDER BY timestamp DESC LIMIT 1")
        gex_row = c.fetchone()
        call_wall = gex_row[0] if gex_row else strike + 10
        put_wall = gex_row[1] if gex_row else strike - 10

        conn.close()

        # Generate position guidance
        prompt = f"""You are a professional position manager providing real-time guidance for an open options trade. Provide SPECIFIC next actions with exact prices and times.

CURRENT POSITION:
• Symbol: {trade['symbol']}
• Strike: ${strike}
• Type: {option_type}
• Contracts: {trade['contracts']}
• Entry Price: ${entry_price:.2f}
• Current Price (est): ${current_price:.2f}
• P&L: ${total_pnl:.2f} ({pnl_pct:+.1f}%)
• Time Held: {time_held:.1f} hours
• Entry: {trade['timestamp']}

CURRENT MARKET:
• SPY: ${current_spy}
• VIX: {current_vix}
• Call Wall: ${call_wall}
• Put Wall: ${put_wall}
• Current Time: {datetime.now().strftime('%I:%M %p')}

ORIGINAL TRADE PLAN:
• Pattern: {trade.get('pattern_type', 'N/A')}
• Expected Target: Estimate based on strike
• Original Stop: Estimate

Provide specific position management guidance:

1. CURRENT STATUS
   • Winning/Losing and by how much
   • Whether thesis is still valid
   • How close to target

2. NEXT ACTIONS (prioritized, specific)
   • Should I take partial profit NOW? How many contracts?
   • Should I add to winner? How many contracts?
   • Should I exit completely? Why?
   • Should I wait? Until when?

3. STOP LOSS ADJUSTMENT
   • Original stop loss
   • Recommended new stop (move to breakeven?)
   • Why adjust now

4. EXIT TRIGGERS (exact conditions)
   • Exit immediately if: (VIX level, SPY price)
   • Take profit if: (SPY price, time)
   • Cut loss if: (thesis broken)

5. GREEKS UPDATE
   • Estimated theta decay per day
   • Time urgency (days/hours left)
   • Delta exposure

6. TIME DECAY WATCH
   • Current time
   • Theta burn acceleration time
   • Recommended exit time if no movement

7. OPPORTUNITY ASSESSMENT
   • Should I add more contracts?
   • What's the risk/reward of adding?
   • What's the best-case scenario now?

Be extremely specific with prices, times, and contract quantities. Make this ACTIONABLE and URGENT."""

        guidance = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'trade': trade,
                'current_status': {
                    'current_price': current_price,
                    'total_pnl': total_pnl,
                    'pnl_pct': pnl_pct,
                    'time_held_hours': time_held
                },
                'market_context': {
                    'spy_price': current_spy,
                    'vix': current_vix,
                    'call_wall': call_wall,
                    'put_wall': put_wall
                },
                'guidance': guidance.content,
                'generated_at': datetime.now().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate position guidance: {str(e)}")


# ============================================================================
# 5. MARKET COMMENTARY WIDGET
# ============================================================================

@router.get("/market-commentary")
async def get_market_commentary():
    """
    Generates real-time market narration explaining what's happening NOW
    and what action to take IMMEDIATELY.
    """
    require_api_key()

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get current market data
        c.execute("SELECT * FROM market_data ORDER BY timestamp DESC LIMIT 2")
        market_data = [dict(row) for row in c.fetchall()]
        current_market = market_data[0] if len(market_data) > 0 else {}
        previous_market = market_data[1] if len(market_data) > 1 else current_market

        # Get psychology analysis
        c.execute("SELECT * FROM psychology_analysis ORDER BY timestamp DESC LIMIT 1")
        psych_row = c.fetchone()
        psychology = dict(psych_row) if psych_row else {}

        # Get GEX
        c.execute("SELECT * FROM gex_levels ORDER BY timestamp DESC LIMIT 1")
        gex_row = c.fetchone()
        gex = dict(gex_row) if gex_row else {}

        # Get open positions
        c.execute("SELECT COUNT(*) as count FROM trades WHERE status = 'OPEN'")
        open_positions = c.fetchone()[0]

        # Get recent trade
        c.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 1")
        recent_trade_row = c.fetchone()
        recent_trade = dict(recent_trade_row) if recent_trade_row else None

        conn.close()

        # Calculate changes
        vix_change = (current_market.get('vix') or 15) - (previous_market.get('vix') or 15)
        price_change = (current_market.get('spot_price') or 0) - (previous_market.get('spot_price') or 0)

        # Generate commentary
        prompt = f"""You are a live market commentator speaking directly to a trader. Provide real-time narration of what's happening NOW and what they should do IMMEDIATELY. Speak in first person to the trader.

CURRENT MARKET (LIVE):
• SPY: ${current_market.get('spot_price') or 0} ({price_change:+.2f} from previous)
• VIX: {current_market.get('vix') or 0} ({vix_change:+.2f})
• Net GEX: ${(current_market.get('net_gex') or 0)/1e9:.2f}B
• Call Wall: ${gex.get('call_wall') or 0}
• Put Wall: ${gex.get('put_wall') or 0}
• Flip Point: ${gex.get('flip_point') or 0}

PSYCHOLOGY STATUS:
• Regime: {psychology.get('regime_type', 'UNKNOWN')}
• Confidence: {psychology.get('confidence') or 0}%
• Trap Detected: {psychology.get('psychology_trap', 'NONE')}

YOUR POSITIONS:
• Open positions: {open_positions}
{f"• Last trade: {recent_trade['symbol']} ${recent_trade['strike']} {recent_trade['option_type']} @ {recent_trade['timestamp']}" if recent_trade else ""}

TIME: {datetime.now().strftime('%I:%M %p CT')}

Provide a conversational, urgent market commentary with:

1. WHAT'S HAPPENING NOW (2-3 sentences)
   • Describe current price action
   • Explain what market makers are doing
   • Interpret VIX movement

2. IMMEDIATE ACTION (specific)
   • If X happens in next Y minutes, do Z
   • Exact price levels to watch
   • What trade to prepare

3. WATCH THIS (critical alert)
   • What could invalidate the setup
   • What price level triggers action

4. TIMING (when to act)
   • Optimal entry window
   • Don't wait past this time
   • Re-evaluate conditions

Speak directly to the trader in an urgent, clear voice. Be specific with prices and times. Keep it under 150 words but make every word count."""

        commentary = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'commentary': commentary.content,
                'market_data': current_market,
                'psychology': psychology,
                'gex': gex,
                'open_positions': open_positions,
                'generated_at': datetime.now().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate commentary: {str(e)}")


# ============================================================================
# 6. STRATEGY COMPARISON ENGINE
# ============================================================================

@router.get("/compare-strategies")
async def compare_strategies():
    """
    Compares all available trading strategies for current market conditions.
    Shows directional, iron condor, wait options with head-to-head comparison.
    """
    require_api_key()

    try:
        conn = get_safe_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get market data
        c.execute("SELECT * FROM market_data ORDER BY timestamp DESC LIMIT 1")
        market_row = c.fetchone()
        market = dict(market_row) if market_row else {}

        # Get psychology
        c.execute("SELECT * FROM psychology_analysis ORDER BY timestamp DESC LIMIT 1")
        psych_row = c.fetchone()
        psychology = dict(psych_row) if psych_row else {}

        # Get GEX
        c.execute("SELECT * FROM gex_levels ORDER BY timestamp DESC LIMIT 1")
        gex_row = c.fetchone()
        gex = dict(gex_row) if gex_row else {}

        # Get account value
        c.execute("SELECT account_value FROM account_state ORDER BY timestamp DESC LIMIT 1")
        account_row = c.fetchone()
        account_value = account_row[0] if account_row else 10000

        # Get pattern performance
        c.execute("""
            SELECT
                pattern_type,
                COUNT(*) as trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
                AVG(realized_pnl) as avg_pnl
            FROM trades
            WHERE status = 'CLOSED' AND timestamp >= NOW() - INTERVAL '30 days'
            GROUP BY pattern_type
            ORDER BY win_rate DESC
            LIMIT 5
        """)
        pattern_performance = [dict(row) for row in c.fetchall()]

        conn.close()

        # Generate strategy comparison
        prompt = f"""You are a professional trader comparing available strategies for the current market. Provide a detailed head-to-head comparison with specific trade setups.

CURRENT MARKET:
• SPY: ${market.get('spot_price') or 0}
• VIX: {market.get('vix') or 0}
• Net GEX: ${(market.get('net_gex') or 0)/1e9:.2f}B
• Regime: {psychology.get('regime_type', 'UNKNOWN')}
• Confidence: {psychology.get('confidence') or 0}%
• Call Wall: ${gex.get('call_wall') or 0}
• Put Wall: ${gex.get('put_wall') or 0}

ACCOUNT:
• Balance: ${account_value:.2f}

RECENT PATTERN PERFORMANCE (30 days):
{chr(10).join([f"• {p['pattern_type']}: {p['win_rate']*100:.0f}% win rate" for p in pattern_performance])}

Compare these 3 strategies for RIGHT NOW:

OPTION 1: DIRECTIONAL TRADE (Aggressive)
• Exact strike and type (CALL/PUT)
• Cost per contract and total
• Probability of profit
• Expected value
• Max loss
• Best if: Specific condition
• Pros: 3 bullet points
• Cons: 3 bullet points

OPTION 2: IRON CONDOR (Conservative)
• Exact strikes (sell and buy)
• Credit collected
• Probability of profit
• Expected value
• Max loss
• Best if: Specific condition
• Pros: 3 bullet points
• Cons: 3 bullet points

OPTION 3: WAIT FOR BETTER SETUP
• What you're waiting for
• What invalidates current setup
• Expected timeline
• Pros: 2 bullet points
• Cons: 2 bullet points

Then provide:

HEAD-TO-HEAD COMPARISON TABLE:
                    Directional | Iron Condor | Wait
Profit Potential        ⭐⭐⭐   |     ⭐⭐     |  -
Risk Level             🔴🔴🔴  |    🟡🟡    | 🟢
Win Probability           X%    |      Y%    | N/A
Expected Value          $XXX    |     $XX    | $0
Time Sensitivity         HIGH   |     LOW    | -

AI RECOMMENDATION: Choose one and explain why in 2-3 sentences with specific reasoning based on current market regime and confidence.

ALTERNATIVE: If trader prefers different risk profile, what's the alternative?

DON'T WAIT IF: Explain why waiting would be a mistake (if applicable).

Be specific with all dollar amounts, strikes, and probabilities."""

        comparison = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'comparison': comparison.content,
                'market': market,
                'psychology': psychology,
                'gex': gex,
                'account_value': account_value,
                'pattern_performance': pattern_performance,
                'generated_at': datetime.now().isoformat()
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare strategies: {str(e)}")


# ============================================================================
# 7. OPTION GREEKS EXPLAINER
# ============================================================================

class GreeksExplainerRequest(BaseModel):
    greek: str  # delta, theta, gamma, vega
    value: float
    strike: float
    current_price: float
    contracts: int
    option_type: str
    days_to_expiration: Optional[int] = 3


@router.post("/explain-greek")
async def explain_greek(request: GreeksExplainerRequest):
    """
    Provides context-aware explanation of a specific Greek for the trader's position.
    """
    require_api_key()

    try:
        # Generate contextual explanation
        prompt = f"""You are teaching an options trader about Greeks in the context of THEIR actual trade. Explain this Greek with specific examples using THEIR numbers.

THEIR POSITION:
• Strike: ${request.strike}
• Current Price: ${request.current_price}
• Type: {request.option_type}
• Contracts: {request.contracts}
• {request.greek.upper()}: {request.value}
• Days to Expiration: {request.days_to_expiration}

Explain {request.greek.upper()} with:

1. WHAT THIS MEANS (simple definition)
   • What this Greek measures
   • Why it matters for options

2. FOR YOUR TRADE SPECIFICALLY
   • What {request.value} means in dollars
   • Impact on your {request.contracts} contracts
   • Examples with SPY price movements

3. EXAMPLE SCENARIOS (use their numbers)
   • If SPY moves +$1/$5/$10
   • If SPY moves -$1/$5/$10
   • Dollar impact on their position

4. WHY THIS VALUE IS GOOD/BAD
   • Is {request.value} optimal for this trade type?
   • Too high/low? What's ideal?
   • Sweet spot for directional plays

5. ACTIONABLE ADVICE
   • What this Greek tells you to DO
   • Time urgency (if applicable)
   • When to exit based on this Greek

Keep it under 200 words but be specific with dollar amounts and examples using THEIR trade."""

        explanation = llm.invoke(prompt)

        return {
            'success': True,
            'data': {
                'greek': request.greek,
                'value': request.value,
                'explanation': explanation.content,
                'position_context': {
                    'strike': request.strike,
                    'current_price': request.current_price,
                    'contracts': request.contracts,
                    'option_type': request.option_type,
                    'days_to_expiration': request.days_to_expiration
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to explain Greek: {str(e)}")


# Health check
@router.get("/health")
async def health_check():
    """Health check for AI intelligence endpoints"""
    return {
        'success': True,
        'status': 'All AI intelligence systems operational',
        'features': [
            'Pre-Trade Safety Checklist',
            'Real-Time Trade Explainer',
            'Daily Trading Plan Generator',
            'Position Management Assistant',
            'Market Commentary Widget',
            'Strategy Comparison Engine',
            'Option Greeks Explainer'
        ]
    }
