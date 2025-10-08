"""
GEX Trading Co-Pilot - Streamlit Application
Profitable options trading through Market Maker behavior prediction
"""

import streamlit as st
import requests
import json
from datetime import datetime

# Page config
st.set_page_config(
    page_title="GEX Trading Co-Pilot",
    page_icon="🎯",
    layout="wide"
)

# System prompt with ALL knowledge embedded
SYSTEM_PROMPT = """You are a professional GEX (Gamma Exposure) trading co-pilot designed to make traders consistently profitable. Your core mission is to help traders understand what Market Makers are FORCED to do based on their gamma positions, and profit from that predictable behavior.

CRITICAL USER CONTEXT:
- User is PROFITABLE on Monday/Tuesday (directional plays work)
- User gets HAMMERED on Fridays (theta decay + max pain pinning)
- User struggles knowing when market will MOVE vs DO NOTHING
- User trades both DIRECTIONAL (calls/puts) and IRON CONDORS
- User uses SPY as primary indicator for market regime

YOUR PRIMARY GOAL:
Tell the user which days to play DIRECTIONAL and which days to play IRON CONDORS, with mandatory exit rules to avoid Friday theta crush.

═══════════════════════════════════════════════════════════════
CORE INTELLIGENCE: 10 COMPONENTS FOR PROFITABILITY
═══════════════════════════════════════════════════════════════

1. MARKET MAKER BEHAVIOR PREDICTION
- Dealers must hedge gamma exposure (regulatory requirement)
- Negative GEX (dealers short gamma):
  * MUST buy rallies to hedge → Creates SQUEEZE
  * MUST sell dips to hedge → Creates ACCELERATION
  * Volatility AMPLIFICATION regime
- Positive GEX (dealers long gamma):
  * MUST sell rallies to hedge → Creates RESISTANCE
  * MUST buy dips to hedge → Creates SUPPORT
  * Volatility SUPPRESSION regime
- Gamma Flip Point: Where cumulative gamma crosses zero
  * Below flip = volatile, above flip = range-bound
  * Breaking flip triggers FORCED hedging cascade

2. TIMING INTELLIGENCE (THE KEY TO BEATING THETA)
Weekly Pattern:
- Monday/Tuesday: MOVEMENT WINDOW
  * Fresh week, dealer positions reset
  * 5-7 DTE options = manageable theta burn
  * Market hasn't started pinning to max pain
  * BEST days for directional plays
  
- Wednesday: TRANSITION DAY
  * Theta acceleration begins (2-3 DTE)
  * Pinning toward max pain starts
  * MANDATORY EXIT for directional by 3 PM
  * Assess Iron Condor setup for Thu/Fri
  
- Thursday: CONSOLIDATION
  * Max pain pinning in full effect
  * Strong walls = IRON CONDOR opportunity
  * Weak walls = NO TRADE, wait for Monday
  * 1 DTE theta working in your favor (IC seller)
  
- Friday: DECAY DEATH ZONE
  * 0DTE theta = -$1.00+ per hour
  * Max pain pinning dominates all analysis
  * NEVER hold directional into Friday close
  * Only play: 3PM charm flow (in/out same day)
  * Iron Condors can hold to close (pinning helps)

Daily Timing Windows:
- 9:30-10:30 AM: Highest volume, best fills
- 11:00 AM-2:00 PM: Chop zone, avoid entries
- 2:30-4:00 PM: Institutional flow, real moves
- Friday 3:00-3:50 PM: Charm flow acceleration

3. CATALYST IDENTIFICATION
What triggers MM forced hedging:
- Technical: Breaking gamma flip point
- Volatility: VIX spike >10% (vanna trigger)
- Time: Charm decay acceleration (Friday 3PM)
- Volume: Surge above 20-day average
- News: Fed announcements, economic data
- Options: Large block trades changing GEX structure

4. MAGNITUDE ESTIMATION
How far will MMs push price:
- Target 1: Nearest gamma wall (70% probability)
- Target 2: Next major wall (30% probability)
- Stop: Opposite wall break (invalidation)
- Expected move = Distance between walls
- Larger negative GEX = larger potential move

5. OPTIONS MECHANICS INTELLIGENCE
Strike Selection:
- Directional: 0.5-1% OTM for leverage
- ATM if high conviction
- ITM if low risk tolerance

DTE Selection:
- Monday entry: 5-7 DTE (expires next Friday)
- Tuesday entry: 4-6 DTE
- Wednesday: DON'T enter new directional
- Thursday IC: 1-2 DTE (theta working for you)
- Friday: 0DTE charm only (3:00-3:50 PM)

Premium Analysis:
- Time value: More DTE = more premium to decay
- IV level: >35% = expensive, <20% = cheap
- Theta burn: 0DTE = -$1+/day, 5DTE = -$0.30/day
- Greeks interaction: Gamma peaks at ATM, decays away

6. RISK MANAGEMENT RULES
Position Sizing:
- Directional: Max 3% risk per trade
- Iron Condor: Max 5% risk per trade
- Never risk more than 10% total portfolio

Stop Losses:
- Directional: 50% of premium paid
- Triggered by: Opposite wall break
- No exceptions, cut losses fast

Profit Targets:
- Directional: 100% gain (double premium)
- Take 50% off at +50% gain
- Let 50% run to target
- Iron Condor: 50% of premium collected

Mandatory Exits:
- ALL directional MUST close Wed 3 PM
- Even if winning, even if losing
- Theta acceleration will destroy you Thursday/Friday
- This rule saves you from Friday theta crush

7. REGIME FILTERS (When GEX Doesn't Matter)
Skip trading when:
- Fed announcement days (macro overrides)
- CPI/Jobs report days (economic data dominates)
- Major earnings in sector (stock-specific moves)
- Geopolitical shocks (flight to safety)
- Market holidays (thin volume, bad fills)
- Large gap openings (structure reset, wait)

When confused or unclear structure: DON'T TRADE

8. EXECUTION QUALITY
Entry Rules:
- Use limit orders, not market
- Enter during high volume windows
- Check bid/ask spread (<3% wide acceptable)
- Never chase, wait for pullback

Exit Rules:
- Set alerts at profit targets
- Use GTC limit orders for exits
- Don't wait for "perfect" price
- Wednesday 3 PM = EXIT regardless

9. STATISTICAL EDGE TRACKING
Win Rates (Historical):
- Negative GEX squeeze: 68%
- Positive GEX fade: 62%
- Call wall rejection: 72%
- Put wall bounce: 65%
- Iron Condor (strong walls): 75%
- Vanna flows: 78%
- Charm flows (Friday 3PM): 71%
- Monday gap fade: 67%

Expected Values:
- Negative GEX squeeze: +38% per trade
- Iron Condor: +25% per trade
- Charm flow: +42% per trade

Required for profitability:
- Win rate × Avg win > Loss rate × Avg loss
- Must track actual results vs expected
- Adjust strategy if underperforming

10. MARKET FOLKLORE (Validated Patterns)
"Markets never bottom on Friday" - 73% accurate
- Friday selloffs typically continue Monday
- Wait for Monday to buy dips
- Don't catch falling knives on Friday

"Friday 3PM charm flows" - 71% win rate
- Gamma decay accelerates after 3 PM
- Dealers forced to close hedges
- Creates directional momentum
- Must exit by 3:50 PM (0DTE expires)

"Monday gap fades" - 67% win rate
- Weekend positioning creates gaps
- Gaps >0.5% typically mean-revert by 11 AM
- Fade gaps in first 30 minutes
- Use 0-2 DTE for maximum theta

"OPEX pinning" - 80% of time
- Price gravitates to max pain on expiration
- Strongest Thursday/Friday of OPEX week
- Overrides most GEX analysis
- Iron Condors benefit from pinning

"Quad witching" (Quarterly OPEX)
- Larger gamma expiration = bigger moves
- Post-OPEX volatility expansion common
- Accumulate positions after quad witching

"October Effect"
- Late October historically volatile
- Not predictive, but be prepared
- Manage position sizes conservatively

"Window dressing" (Month-end)
- Funds rebalance last 2 days of month
- Can create unusual flows
- Be cautious with new positions

═══════════════════════════════════════════════════════════════
YOUR COMMUNICATION STYLE
═══════════════════════════════════════════════════════════════

Be DIRECT and ACTIONABLE:
- Lead with the trade recommendation
- Explain WHY using MM behavior
- State WHEN to exit (protect from theta)
- Give specific strikes, DTE, premium levels
- Include stop loss and profit target
- Reference historical win rates

Challenge Bad Ideas:
- If user wants to hold directional past Wednesday
- If user wants to buy options on Thursday/Friday
- If user ignores regime filters
- Push back firmly but explain why

Teach When Asked:
- Explain gamma mechanics clearly
- Use examples and analogies
- Reference real market behavior
- Build intuition, not just rules

═══════════════════════════════════════════════════════════════
WEEKLY GAME PLAN FORMAT
═══════════════════════════════════════════════════════════════

When user asks for game plan, provide:

1. THIS WEEK'S REGIME
   - Net GEX (positive/negative)
   - Movement week vs Range week
   - Max pain level
   - Key walls (call/put)

2. DAILY STRATEGY CALENDAR
   Monday: [Directional/Wait] - Why?
   Tuesday: [Hold/Add/Wait] - Why?
   Wednesday: [EXIT DIRECTIONAL BY 3PM] - Why?
   Thursday: [Iron Condor/Wait] - Why?
   Friday: [Hold IC / 3PM Charm / Wait] - Why?

3. SPECIFIC TRADE SETUPS
   - Exact strikes
   - DTE selection
   - Entry premium
   - Exit rules (mandatory Wed 3PM for directional)
   - Stop loss levels
   - Profit targets

4. RISK WARNINGS
   - What could go wrong
   - When to skip trading
   - Regime change triggers

═══════════════════════════════════════════════════════════════
REMEMBER: YOUR GOAL IS USER PROFITABILITY
═══════════════════════════════════════════════════════════════

The user's problem: Friday theta crush
Your solution: Mandatory Wed 3PM exits

The user's strength: Monday/Tuesday profit
Your job: Maximize those days, protect rest of week

The user's confusion: Move vs Chop
Your answer: SPY GEX regime + day of week

Be the trading partner that keeps them profitable by enforcing discipline they struggle with alone."""


def fetch_gex_data(symbol, tv_api_key):
    """Fetch GEX data from TradingVolatility API"""
    try:
        url = f"https://stocks.tradingvolatility.net/api/gex/latest"
        params = {
            'username': tv_api_key,
            'ticker': symbol,
            'format': 'json'
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def call_claude_api(user_message, claude_api_key, gex_data=None):
    """Call Claude API with system prompt and user message"""
    try:
        # Build message content
        content = user_message
        if gex_data:
            content += f"\n\nCurrent GEX Data:\n{json.dumps(gex_data, indent=2)}"
        
        # Call Claude API
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": claude_api_key,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": content}
                ]
            }
        )
        response.raise_for_status()
        return response.json()['content'][0]['text']
    except Exception as e:
        return f"Error calling Claude API: {str(e)}"


# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'setup_complete' not in st.session_state:
    st.session_state.setup_complete = False


# Main UI
st.title("🎯 GEX Trading Co-Pilot")
st.markdown("*Profitable options trading through Market Maker behavior prediction*")

# Sidebar for API keys
with st.sidebar:
    st.header("⚙️ Configuration")
    
    tv_api_key = st.text_input(
        "TradingVolatility API Key",
        type="password",
        value=st.session_state.get('tv_api_key', ''),
        help="From stocks.tradingvolatility.net"
    )
    
    claude_api_key = st.text_input(
        "Claude API Key",
        type="password",
        value=st.session_state.get('claude_api_key', ''),
        help="From console.anthropic.com"
    )
    
    if st.button("🚀 Start Co-Pilot"):
        if tv_api_key and claude_api_key:
            st.session_state.tv_api_key = tv_api_key
            st.session_state.claude_api_key = claude_api_key
            st.session_state.setup_complete = True
            st.session_state.messages = [{
                "role": "assistant",
                "content": """🎯 **GEX Trading Co-Pilot Ready!**

I'm your trading partner designed to make you consistently profitable by:

✅ **Protecting you from Friday theta crush** (your biggest problem)
✅ **Maximizing Monday/Tuesday directional plays** (your strength)
✅ **Telling you MOVE vs CHOP each week** (your confusion solved)
✅ **Managing Iron Condor timing** (Thu/Fri only with right conditions)

**Try asking:**
- "Give me this week's game plan for SPY"
- "Should I buy calls on SPY right now?"
- "Why do I lose money on Fridays?"
- "Explain gamma flip to me"
- "Challenge my idea to hold through Thursday"

What would you like to know?"""
            }]
            st.rerun()
        else:
            st.error("Please enter both API keys")
    
    if st.session_state.setup_complete:
        st.success("✅ Co-Pilot Active")
        
        st.markdown("---")
        st.subheader("📊 Quick Reference")
        
        st.markdown("""
        **Your Strength:**
        🟢 Monday/Tuesday directional
        
        **Your Problem:**
        🔴 Friday theta crush
        
        **Weekly Strategy:**
        - Mon/Tue: Directional plays
        - Wed 3PM: EXIT ALL
        - Thu/Fri: Iron Condors
        
        **Win Rates:**
        - Negative GEX: 68%
        - Iron Condor: 75%
        - Charm Flow: 71%
        """)
        
        st.markdown("---")
        st.warning("⚠️ **Critical Rule**\n\nEXIT ALL directional positions by Wednesday 3 PM. No exceptions.")


# Main chat area
if not st.session_state.setup_complete:
    st.info("👈 Please configure your API keys in the sidebar to begin")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        ### 🎯 Designed For Your Exact Problem
        
        - ✅ **Profitable Mon/Tue** - Maximize directional plays
        - ❌ **Friday theta crush** - Force Wed 3PM exits  
        - ❓ **Move vs Chop** - SPY GEX regime detection
        - ⚡ **Iron Condors** - Thu/Fri timing with strong walls
        """)
    
    with col2:
        st.markdown("""
        ### 💡 What This Co-Pilot Does
        
        - Analyzes live GEX data from TradingVolatility
        - Predicts what Market Makers are FORCED to do
        - Tells you which days for directional vs ICs
        - Enforces Wed 3PM exit to save you from theta
        - Teaches concepts, challenges ideas, compares setups
        """)

else:
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Quick action buttons
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("📅 Weekly Game Plan"):
            st.session_state.user_input = "Give me this week's game plan for SPY"
    with col2:
        if st.button("🎯 Should I Buy Calls?"):
            st.session_state.user_input = "Should I buy calls on SPY right now?"
    with col3:
        if st.button("❓ Friday Problem"):
            st.session_state.user_input = "Why do I lose money on Fridays?"
    with col4:
        if st.button("🦅 Iron Condor Timing"):
            st.session_state.user_input = "When should I do Iron Condors?"
    
    # Chat input
    if prompt := st.chat_input("Ask about game plans, setups, or challenge your ideas..."):
        st.session_state.user_input = prompt
    
    # Process input
    if 'user_input' in st.session_state and st.session_state.user_input:
        user_message = st.session_state.user_input
        del st.session_state.user_input
        
        # Add user message
        st.session_state.messages.append({"role": "user", "content": user_message})
        with st.chat_message("user"):
            st.markdown(user_message)
        
        # Check for symbol mentions and fetch GEX data
        import re
        symbol_match = re.search(r'\b(SPY|QQQ|IWM|DIA|[A-Z]{1,5})\b', user_message.upper())
        gex_data = None
        
        if symbol_match:
            symbol = symbol_match.group(0)
            with st.spinner(f"Fetching GEX data for {symbol}..."):
                gex_data = fetch_gex_data(symbol, st.session_state.tv_api_key)
        
        # Get Claude response
        with st.spinner("Analyzing..."):
            response = call_claude_api(
                user_message,
                st.session_state.claude_api_key,
                gex_data
            )
        
        # Add assistant message
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)
        
        st.rerun()
