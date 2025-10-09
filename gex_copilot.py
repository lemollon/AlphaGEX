"""
GEX Trading Co-Pilot v3.0 - WITH COMPLETE VISUALIZATIONS
Includes: GEX profiles, wall charts, flip point visualization, performance tracking
"""

import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import List, Dict
import re

# Page config
st.set_page_config(
    page_title="GEX Trading Co-Pilot",
    page_icon="🎯",
    layout="wide"
)

# System prompt (same as before)
SYSTEM_PROMPT = """You are an ACTIONABLE GEX trading co-pilot. You ALWAYS give SPECIFIC recommendations with EXACT strikes, prices, and entry/exit rules.

When user asks for "game plan" or analysis, you MUST provide:
1. SPECIFIC strike prices (e.g., "Buy SPY 570 calls" not "buy calls")
2. EXACT premium targets (e.g., "$2.40" not "reasonable premium")
3. PRECISE entry/exit rules (e.g., "Enter at $567, exit at $572")
4. ACTUAL numbers from the GEX data provided

USER CONTEXT:
- Profitable Mon/Tue (directional), loses on Fri (theta crush)
- Needs SPECIFIC actionable trades with VISUALS
- Has live GEX data with charts showing structure

RESPONSE RULES:
1. ALWAYS use the GEX data provided
2. ALWAYS give specific strikes (SPY 570 calls, not "OTM calls")
3. ALWAYS give exact premiums ($2.40, not "$2-3")
4. ALWAYS explain using MM forced behavior
5. Reference the VISUAL charts shown to user
6. NEVER ask user to check anything

WEEKLY GAME PLAN MUST INCLUDE:
- Current market structure (from GEX chart)
- Daily strategy with EXACT strikes
- Reference visual levels (flip point, walls)
- Wednesday 3PM exit rule enforcement
- Risk/reward visually shown

CORE MECHANICS:
- Negative GEX: Dealers SHORT gamma → buy rallies/sell dips = AMPLIFICATION
- Positive GEX: Dealers LONG gamma → sell rallies/buy dips = SUPPRESSION
- Gamma Flip: Crossing triggers FORCED hedging
- Wed 3PM: Theta acceleration kills directional
- Win Rates: Negative GEX 68%, IC 75%, Charm 71%

BE PRESCRIPTIVE. Give exact trades user can execute immediately."""


class TradeTracker:
    def __init__(self):
        if 'trades' not in st.session_state:
            st.session_state.trades = []
    
    def log_trade(self, trade_data: Dict):
        st.session_state.trades.append({
            **trade_data,
            'timestamp': datetime.now().isoformat(),
            'outcome': None
        })
    
    def update_outcome(self, trade_id: int, outcome: Dict):
        if trade_id < len(st.session_state.trades):
            st.session_state.trades[trade_id].update({
                'outcome': outcome,
                'closed_at': datetime.now().isoformat()
            })
    
    def get_performance_stats(self) -> Dict:
        trades = [t for t in st.session_state.trades if t.get('outcome')]
        if not trades:
            return {'total_trades': 0}
        
        wins = sum(1 for t in trades if (t.get('outcome') or {}).get('profit', 0) > 0)
        total = len(trades)
        total_pnl = sum((t.get('outcome') or {}).get('profit', 0) for t in trades)
        
        return {
            'total_trades': total,
            'win_rate': wins / total if total > 0 else 0,
            'total_pnl': total_pnl,
            'avg_win': total_pnl / wins if wins > 0 else 0,
            'expected_value': total_pnl / total if total > 0 else 0
        }


def fetch_gex_data(symbol, tv_username):
    """Fetch GEX data from TradingVolatility API"""
    try:
        url = "https://stocks.tradingvolatility.net/api/gex/latest"
        params = {'username': tv_username, 'ticker': symbol, 'format': 'json'}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def create_gex_profile_chart(gex_data, symbol):
    """Create interactive GEX profile visualization"""
    if not gex_data or 'error' in gex_data or symbol not in gex_data:
        return None
    
    data = gex_data[symbol]
    gamma_array = data.get('gamma_array', [])
    
    if not gamma_array:
        return None
    
    # Parse gamma data
    strikes = [g['strike'] for g in gamma_array if 'strike' in g]
    gammas = [g['gamma'] for g in gamma_array if 'gamma' in g]
    
    if not strikes or not gammas:
        return None
    
    # Get current price
    current_price = float(data.get('price', strikes[len(strikes)//2]))
    
    # Calculate flip point (where gamma crosses zero)
    cumulative_gamma = 0
    flip_point = None
    for i, gamma in enumerate(gammas):
        cumulative_gamma += gamma
        if i > 0 and cumulative_gamma * (cumulative_gamma - gammas[i-1]) < 0:
            flip_point = strikes[i]
            break
    
    # Find walls (max positive and negative gamma)
    max_call_gamma = max(gammas)
    max_put_gamma = min(gammas)
    call_wall = strikes[gammas.index(max_call_gamma)]
    put_wall = strikes[gammas.index(max_put_gamma)]
    
    # Create figure
    fig = go.Figure()
    
    # Add gamma bars
    colors = ['green' if g > 0 else 'red' for g in gammas]
    fig.add_trace(go.Bar(
        x=strikes,
        y=gammas,
        marker_color=colors,
        name='Gamma Exposure',
        text=[f"${g/1e6:.1f}M" for g in gammas],
        textposition='outside',
        hovertemplate='Strike: $%{x}<br>Gamma: $%{y:,.0f}<extra></extra>'
    ))
    
    # Add current price line
    fig.add_vline(
        x=current_price,
        line_dash="solid",
        line_color="blue",
        line_width=3,
        annotation_text=f"Current: ${current_price:.2f}",
        annotation_position="top"
    )
    
    # Add flip point
    if flip_point:
        fig.add_vline(
            x=flip_point,
            line_dash="dash",
            line_color="yellow",
            line_width=2,
            annotation_text=f"Flip: ${flip_point:.2f}",
            annotation_position="bottom"
        )
    
    # Add walls
    fig.add_vline(
        x=call_wall,
        line_dash="dot",
        line_color="green",
        line_width=2,
        annotation_text=f"Call Wall: ${call_wall:.2f}",
        annotation_position="top right"
    )
    
    fig.add_vline(
        x=put_wall,
        line_dash="dot",
        line_color="red",
        line_width=2,
        annotation_text=f"Put Wall: ${put_wall:.2f}",
        annotation_position="bottom left"
    )
    
    # Layout
    fig.update_layout(
        title=f"{symbol} Gamma Exposure Profile",
        xaxis_title="Strike Price",
        yaxis_title="Gamma Exposure ($)",
        hovermode='x unified',
        height=500,
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    
    # Add zero line
    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=1)
    
    return fig, {
        'current_price': current_price,
        'flip_point': flip_point,
        'call_wall': call_wall,
        'put_wall': put_wall,
        'net_gex': sum(gammas),
        'max_call_gamma': max_call_gamma,
        'max_put_gamma': max_put_gamma
    }


def create_key_levels_chart(levels_data, symbol):
    """Create visual summary of key price levels"""
    fig = go.Figure()
    
    current = levels_data['current_price']
    flip = levels_data['flip_point']
    call_wall = levels_data['call_wall']
    put_wall = levels_data['put_wall']
    
    # Create horizontal bar showing levels
    fig.add_trace(go.Scatter(
        x=[put_wall, current, flip, call_wall],
        y=[1, 1, 1, 1],
        mode='markers+text',
        marker=dict(
            size=[30, 40, 30, 30],
            color=['red', 'blue', 'yellow', 'green'],
            symbol=['triangle-down', 'circle', 'diamond', 'triangle-up']
        ),
        text=[
            f"Put Wall<br>${put_wall:.2f}",
            f"Current<br>${current:.2f}",
            f"Flip<br>${flip:.2f}" if flip else "",
            f"Call Wall<br>${call_wall:.2f}"
        ],
        textposition='top center',
        textfont=dict(size=12, color='white'),
        hoverinfo='text',
        hovertext=[
            f"Put Support: ${put_wall:.2f}",
            f"Current Price: ${current:.2f}",
            f"Gamma Flip: ${flip:.2f}" if flip else "",
            f"Call Resistance: ${call_wall:.2f}"
        ]
    ))
    
    # Add range lines
    fig.add_shape(
        type="line",
        x0=put_wall, y0=1, x1=call_wall, y1=1,
        line=dict(color="white", width=2)
    )
    
    # Layout
    fig.update_layout(
        title=f"{symbol} Key Price Levels",
        xaxis_title="Price",
        yaxis=dict(visible=False),
        height=200,
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white'),
        margin=dict(l=20, r=20, t=60, b=40)
    )
    
    return fig


def create_performance_chart(tracker):
    """Create performance tracking visualization"""
    stats = tracker.get_performance_stats()
    
    if stats['total_trades'] == 0:
        return None
    
    # Create metrics visualization
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=('Win Rate', 'Total P&L', 'Expected Value'),
        specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}]]
    )
    
    # Win Rate gauge
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=stats['win_rate'] * 100,
        title={'text': "Win Rate %"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "green" if stats['win_rate'] > 0.6 else "orange"},
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 50
            }
        }
    ), row=1, col=1)
    
    # Total P&L
    fig.add_trace(go.Indicator(
        mode="number+delta",
        value=stats['total_pnl'],
        title={'text': "Total P&L"},
        number={'prefix': "$"},
        delta={'reference': 0}
    ), row=1, col=2)
    
    # Expected Value
    fig.add_trace(go.Indicator(
        mode="number+delta",
        value=stats['expected_value'],
        title={'text': "Exp Value/Trade"},
        number={'prefix': "$"},
        delta={'reference': 0}
    ), row=1, col=3)
    
    fig.update_layout(
        height=300,
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='white')
    )
    
    return fig


def call_claude_api(messages: List[Dict], claude_api_key: str, gex_data: Dict = None, levels_data: Dict = None) -> str:
    """Call Claude API with GEX data and visual context"""
    try:
        if gex_data and 'error' not in gex_data and levels_data:
            last_message = messages[-1]['content']
            
            gex_summary = f"""
LIVE GEX DATA WITH VISUAL ANALYSIS:

Current Market Structure:
- Symbol: {list(gex_data.keys())[0]}
- Current Price: ${levels_data['current_price']:.2f}
- Net GEX: ${levels_data['net_gex']/1e9:.2f}B ({"NEGATIVE - Squeeze environment" if levels_data['net_gex'] < 0 else "POSITIVE - Range-bound"})

Key Levels (VISIBLE IN CHART):
- Put Wall (Support): ${levels_data['put_wall']:.2f} | Gamma: ${levels_data['max_put_gamma']/1e6:.1f}M
- Gamma Flip Point: ${levels_data['flip_point']:.2f} (Critical level)
- Call Wall (Resistance): ${levels_data['call_wall']:.2f} | Gamma: ${levels_data['max_call_gamma']/1e6:.1f}M

Distance Analysis:
- Current to Flip: {((levels_data['current_price'] - levels_data['flip_point']) / levels_data['current_price'] * 100):.2f}%
- Current to Call Wall: {((levels_data['call_wall'] - levels_data['current_price']) / levels_data['current_price'] * 100):.2f}%
- Current to Put Wall: {((levels_data['current_price'] - levels_data['put_wall']) / levels_data['current_price'] * 100):.2f}%

The user can SEE these levels in the chart above. Reference them specifically in your recommendations.

Full Data:
{json.dumps(gex_data, indent=2)}
"""
            messages[-1]['content'] = f"{last_message}\n\n{gex_summary}"
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": claude_api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 3000,
                "system": [
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                "messages": messages
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()['content'][0]['text']
    except Exception as e:
        return f"Error: {str(e)}"


# Initialize
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'setup_complete' not in st.session_state:
    st.session_state.setup_complete = False
if 'trades' not in st.session_state:
    st.session_state.trades = []
if 'current_gex_chart' not in st.session_state:
    st.session_state.current_gex_chart = None
if 'current_levels' not in st.session_state:
    st.session_state.current_levels = None

tracker = TradeTracker()

# Get credentials
TV_USERNAME = None
CLAUDE_API_KEY = None

try:
    TV_USERNAME = st.secrets["tradingvolatility_username"]
    CLAUDE_API_KEY = st.secrets["claude_api_key"]
    st.session_state.setup_complete = True
except:
    st.session_state.setup_complete = False

# Main UI
st.title("🎯 GEX Trading Co-Pilot v3.0")
st.markdown("*Visual GEX analysis with specific trade recommendations*")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    
    if not st.session_state.setup_complete:
        st.warning("⚠️ Configure secrets")
        with st.expander("Setup"):
            tv_user = st.text_input("TV Username", type="password")
            claude_key = st.text_input("Claude Key", type="password")
            if st.button("Connect") and tv_user and claude_key:
                TV_USERNAME = tv_user
                CLAUDE_API_KEY = claude_key
                st.session_state.setup_complete = True
                st.rerun()
    else:
        st.success("✅ Connected")
        
        # Performance
        st.markdown("---")
        st.subheader("📊 Performance")
        stats = tracker.get_performance_stats()
        
        if stats['total_trades'] > 0:
            col1, col2 = st.columns(2)
            col1.metric("Win Rate", f"{stats['win_rate']:.1%}")
            col2.metric("P&L", f"${stats['total_pnl']:,.0f}")
        else:
            st.info("No trades")
        
        st.markdown("---")
        st.warning("⚠️ EXIT by Wed 3PM")

# Main Interface
if not st.session_state.setup_complete:
    st.info("Configure API keys in sidebar")
else:
    # Visual Display Area
    viz_col1, viz_col2 = st.columns([2, 1])
    
    with viz_col1:
        if st.session_state.current_gex_chart:
            st.plotly_chart(st.session_state.current_gex_chart, use_container_width=True)
    
    with viz_col2:
        if st.session_state.current_levels:
            # Key metrics
            levels = st.session_state.current_levels
            st.metric("Current Price", f"${levels['current_price']:.2f}")
            st.metric("Net GEX", f"${levels['net_gex']/1e9:.2f}B")
            
            col1, col2 = st.columns(2)
            col1.metric("Call Wall", f"${levels['call_wall']:.2f}")
            col2.metric("Put Wall", f"${levels['put_wall']:.2f}")
            
            if levels['flip_point']:
                st.metric("Gamma Flip", f"${levels['flip_point']:.2f}")
                
                # Distance indicator
                distance = ((levels['current_price'] - levels['flip_point']) / levels['current_price'] * 100)
                if abs(distance) < 0.5:
                    st.warning(f"⚠️ {abs(distance):.2f}% from flip!")
                else:
                    st.info(f"📍 {distance:.2f}% from flip")
    
    st.markdown("---")
    
    # Chat Messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # Quick Action Buttons
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("📅 SPY Game Plan"):
            st.session_state.user_input = "Give me this week's complete game plan for SPY with specific strikes based on the chart"
    with col2:
        if st.button("🎯 Trade Now?"):
            st.session_state.user_input = "Based on the current GEX chart, should I enter a trade right now? Give exact strike"
    with col3:
        if st.button("📊 QQQ Analysis"):
            st.session_state.user_input = "Show me QQQ GEX chart and give me a trade setup"
    with col4:
        if st.button("🦅 IC Setup?"):
            st.session_state.user_input = "Is there an Iron Condor setup? Show me the chart and exact strikes"
    
    # Chat Input
    if prompt := st.chat_input("Ask for analysis with visuals..."):
        st.session_state.user_input = prompt
    
    # Process Input
    if 'user_input' in st.session_state and st.session_state.user_input:
        user_message = st.session_state.user_input
        del st.session_state.user_input
        
        st.session_state.messages.append({"role": "user", "content": user_message})
        
        with st.chat_message("user"):
            st.markdown(user_message)
        
        # Detect symbol and fetch data
        symbol_match = re.search(r'\b(SPY|QQQ|IWM|DIA)\b', user_message.upper())
        symbol = symbol_match.group(0) if symbol_match else 'SPY'
        
        with st.spinner(f"📊 Fetching {symbol} GEX data and creating charts..."):
            gex_data = fetch_gex_data(symbol, TV_USERNAME)
            
            if 'error' not in gex_data:
                # Create visualizations
                chart_result = create_gex_profile_chart(gex_data, symbol)
                
                if chart_result:
                    chart, levels = chart_result
                    st.session_state.current_gex_chart = chart
                    st.session_state.current_levels = levels
                    
                    # Display charts immediately
                    st.plotly_chart(chart, use_container_width=True)
                    
                    # Show key levels
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Net GEX", f"${levels['net_gex']/1e9:.2f}B")
                    col2.metric("Distance to Flip", f"{((levels['current_price'] - levels['flip_point']) / levels['current_price'] * 100):.2f}%")
                    col3.metric("Range", f"${levels['put_wall']:.0f}-${levels['call_wall']:.0f}")
        
        # Build message history
        claude_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in st.session_state.messages
        ]
        
        # Get response with visual context
        with st.spinner("💬 Analyzing chart and generating recommendations..."):
            response = call_claude_api(
                claude_messages,
                CLAUDE_API_KEY,
                gex_data,
                st.session_state.current_levels
            )
        
        st.session_state.messages.append({"role": "assistant", "content": response})
        
        with st.chat_message("assistant"):
            st.markdown(response)
        
        # Log trade
        if any(word in response.lower() for word in ['buy', 'sell', 'entry']):
            tracker.log_trade({
                'recommendation': response,
                'symbol': symbol,
                'gex_data': gex_data,
                'levels': st.session_state.current_levels
            })
        
        st.rerun()

# Performance Chart (if trades exist)
if tracker.get_performance_stats()['total_trades'] > 0:
    with st.expander("📈 View Performance Dashboard"):
        perf_chart = create_performance_chart(tracker)
        if perf_chart:
            st.plotly_chart(perf_chart, use_container_width=True)
