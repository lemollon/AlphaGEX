"""
Intraday GEX Tracking
Monitor dealer repositioning throughout the trading day
"""

import streamlit as st
from typing import Dict, List
from datetime import datetime, time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class IntradayTracker:
    """Track GEX metrics throughout the day"""

    def __init__(self):
        # Initialize session state for intraday snapshots
        if 'intraday_snapshots' not in st.session_state:
            st.session_state.intraday_snapshots = {}  # {symbol: [snapshots]}

    def _safe_float(self, value, default=0.0):
        """Safely convert value to float, handling corrupted/invalid data"""
        try:
            # Handle None
            if value is None:
                return default

            # If already a number, convert to float
            if isinstance(value, (int, float)):
                return float(value)

            # If string, try to convert
            if isinstance(value, str):
                # Check if string looks corrupted (repeated values)
                if len(value) > 50:  # Suspiciously long number
                    return default
                return float(value)

            return default
        except (ValueError, TypeError):
            return default

    def capture_snapshot(self, symbol: str, gex_data: Dict, skew_data: Dict = None):
        """
        Capture current GEX state

        Args:
            symbol: Ticker symbol
            gex_data: Current GEX data
            skew_data: Current skew data (optional)
        """

        if symbol not in st.session_state.intraday_snapshots:
            st.session_state.intraday_snapshots[symbol] = []

        snapshot = {
            'timestamp': datetime.now(),
            'time_str': datetime.now().strftime('%H:%M'),
            'spot_price': self._safe_float(gex_data.get('spot_price', 0)),
            'net_gex': self._safe_float(gex_data.get('net_gex', 0)),
            'flip_point': self._safe_float(gex_data.get('flip_point', 0)),
            'call_wall': self._safe_float(gex_data.get('call_wall', 0)),
            'put_wall': self._safe_float(gex_data.get('put_wall', 0)),
            'iv': self._safe_float(skew_data.get('implied_volatility', 0)) * 100 if skew_data else 0.0,
            'pcr': self._safe_float(skew_data.get('pcr_oi', 0)) if skew_data else 0.0
        }

        # Check if we already have a snapshot from this minute (avoid duplicates)
        existing_times = [s['time_str'] for s in st.session_state.intraday_snapshots[symbol]]
        if snapshot['time_str'] not in existing_times:
            st.session_state.intraday_snapshots[symbol].append(snapshot)

            # Keep only today's data (clear at midnight)
            today = datetime.now().date()
            st.session_state.intraday_snapshots[symbol] = [
                s for s in st.session_state.intraday_snapshots[symbol]
                if s['timestamp'].date() == today
            ]

    def get_snapshots(self, symbol: str) -> List[Dict]:
        """Get all snapshots for a symbol"""
        return st.session_state.intraday_snapshots.get(symbol, [])

    def get_snapshot_count(self, symbol: str) -> int:
        """Get number of snapshots for a symbol"""
        return len(self.get_snapshots(symbol))

    def _validate_snapshots(self, snapshots: List[Dict]) -> List[Dict]:
        """Remove corrupted snapshots"""
        valid_snapshots = []
        for snapshot in snapshots:
            # Check if all numeric values are valid
            try:
                self._safe_float(snapshot.get('spot_price', 0))
                self._safe_float(snapshot.get('net_gex', 0))
                self._safe_float(snapshot.get('flip_point', 0))
                valid_snapshots.append(snapshot)
            except (ValueError, TypeError):
                # Skip corrupted snapshot
                continue
        return valid_snapshots

    def calculate_changes(self, symbol: str) -> Dict:
        """
        Calculate intraday changes

        Returns:
            Dictionary with change metrics
        """

        snapshots = self.get_snapshots(symbol)

        # Clean up any corrupted snapshots
        snapshots = self._validate_snapshots(snapshots)

        if len(snapshots) < 2:
            return None

        first = snapshots[0]
        latest = snapshots[-1]

        # Convert to float to handle any legacy string values
        first_net_gex = self._safe_float(first.get('net_gex', 0))
        latest_net_gex = self._safe_float(latest.get('net_gex', 0))
        first_flip = self._safe_float(first.get('flip_point', 0))
        latest_flip = self._safe_float(latest.get('flip_point', 0))
        first_spot = self._safe_float(first.get('spot_price', 0))
        latest_spot = self._safe_float(latest.get('spot_price', 0))
        first_iv = self._safe_float(first.get('iv', 0))
        latest_iv = self._safe_float(latest.get('iv', 0))
        first_pcr = self._safe_float(first.get('pcr', 0))
        latest_pcr = self._safe_float(latest.get('pcr', 0))

        changes = {
            'net_gex_change': latest_net_gex - first_net_gex,
            'net_gex_change_pct': ((latest_net_gex - first_net_gex) / abs(first_net_gex) * 100)
                                  if first_net_gex != 0 else 0,
            'flip_change': latest_flip - first_flip,
            'flip_change_pct': ((latest_flip - first_flip) / first_flip * 100)
                              if first_flip != 0 else 0,
            'price_change': latest_spot - first_spot,
            'price_change_pct': ((latest_spot - first_spot) / first_spot * 100)
                               if first_spot != 0 else 0,
            'iv_change': latest_iv - first_iv,
            'pcr_change': latest_pcr - first_pcr,
            'num_snapshots': len(snapshots),
            'first_time': first.get('time_str', 'N/A'),
            'latest_time': latest.get('time_str', 'N/A')
        }

        return changes

    def clear_snapshots(self, symbol: str = None):
        """Clear snapshots for symbol or all symbols"""
        if symbol:
            st.session_state.intraday_snapshots[symbol] = []
        else:
            st.session_state.intraday_snapshots = {}


def display_intraday_dashboard(symbol: str):
    """Display intraday tracking dashboard"""

    st.subheader(f"📊 {symbol} - Intraday GEX Tracking")

    try:
        tracker = IntradayTracker()
        snapshots = tracker.get_snapshots(symbol)

        if len(snapshots) < 2:
            st.info(f"""
            📈 **Intraday Tracking**: Need at least 2 data points to show trends.

            **How it works**:
            - Every time you refresh {symbol}, we save a snapshot
            - Compare snapshots to see how dealer positioning changes during the day
            - Identify intraday regime shifts (bullish → bearish or vice versa)

            **Current snapshots**: {len(snapshots)}
            **Need**: 2+ snapshots (refresh {symbol} again)
            """)
            return

        # Calculate changes
        changes = tracker.calculate_changes(symbol)

        if not changes:
            st.info("Need at least 2 valid snapshots to show trends. Please capture more snapshots.")
            return
    except Exception as e:
        st.error(f"⚠️ Unable to display intraday tracking: {str(e)}")
        st.warning("""
        **Data may be corrupted.** Click the button below to clear and restart tracking.
        """)
        if st.button("🗑️ Clear Corrupted Data", key="clear_corrupted"):
            tracker = IntradayTracker()
            tracker.clear_snapshots(symbol)
            st.success("✅ Data cleared! Refresh the page to start tracking again.")
            st.rerun()
        return

    # Display key changes
    st.markdown(f"**Tracking Period**: {changes['first_time']} → {changes['latest_time']} ({changes['num_snapshots']} snapshots)")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Net GEX Change",
            f"${changes['net_gex_change']/1e9:.2f}B",
            delta=f"{changes['net_gex_change_pct']:+.1f}%",
            help="How dealer positioning has shifted"
        )

    with col2:
        st.metric(
            "Flip Point Move",
            f"${changes['flip_change']:.2f}",
            delta=f"{changes['flip_change_pct']:+.2f}%",
            help="Flip point adjustment"
        )

    with col3:
        st.metric(
            "Price Move",
            f"${changes['price_change']:.2f}",
            delta=f"{changes['price_change_pct']:+.2f}%"
        )

    with col4:
        st.metric(
            "IV Change",
            f"{changes['iv_change']:+.1f}%",
            help="Implied volatility shift"
        )

    # Create intraday charts
    create_intraday_charts(snapshots)

    # Intraday insights
    display_intraday_insights(changes)

    # Clear button
    if st.button("🗑️ Clear Intraday Data"):
        tracker.clear_snapshots(symbol)
        st.rerun()


def create_intraday_charts(snapshots: List[Dict]):
    """Create visual charts of intraday changes"""

    df = pd.DataFrame(snapshots)

    # Create subplots
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            'Price vs Flip Point',
            'Net GEX Evolution',
            'Implied Volatility'
        ),
        row_heights=[0.4, 0.3, 0.3]
    )

    # Chart 1: Price vs Flip
    fig.add_trace(
        go.Scatter(
            x=df['time_str'],
            y=df['spot_price'],
            name='Spot Price',
            line=dict(color='white', width=2),
            mode='lines+markers'
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=df['time_str'],
            y=df['flip_point'],
            name='Flip Point',
            line=dict(color='orange', width=2, dash='dash'),
            mode='lines+markers'
        ),
        row=1, col=1
    )

    # Chart 2: Net GEX
    colors = ['green' if x > 0 else 'red' for x in df['net_gex']]
    fig.add_trace(
        go.Bar(
            x=df['time_str'],
            y=df['net_gex'] / 1e9,  # Billions
            name='Net GEX',
            marker_color=colors,
            opacity=0.7
        ),
        row=2, col=1
    )

    # Chart 3: IV
    fig.add_trace(
        go.Scatter(
            x=df['time_str'],
            y=df['iv'],
            name='IV',
            line=dict(color='purple', width=2),
            fill='tozeroy',
            fillcolor='rgba(128, 0, 128, 0.2)'
        ),
        row=3, col=1
    )

    # Update layout
    fig.update_layout(
        height=800,
        template='plotly_dark',
        showlegend=True,
        hovermode='x unified'
    )

    fig.update_xaxes(title_text="Time", row=3, col=1)
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Net GEX ($B)", row=2, col=1)
    fig.update_yaxes(title_text="IV (%)", row=3, col=1)

    st.plotly_chart(fig, use_container_width=True)


def display_intraday_insights(changes: Dict):
    """Display trading insights from intraday changes"""

    st.subheader("💡 Intraday Insights")

    insights = []

    # Net GEX regime shift
    if abs(changes['net_gex_change']) > 1e9:  # >$1B change
        direction = "more negative" if changes['net_gex_change'] < 0 else "more positive"
        insights.append(f"🔄 **GEX Regime Shift**: Net GEX became {direction} by ${abs(changes['net_gex_change'])/1e9:.2f}B")

        if changes['net_gex_change'] < 0:
            insights.append("  → Dealers getting SHORT gamma → More volatility expected")
        else:
            insights.append("  → Dealers getting LONG gamma → Volatility suppression")

    # Flip point movement
    if changes['flip_change_pct'] > 1.0:
        insights.append(f"📈 **Flip Rising**: Flip point moved up {changes['flip_change_pct']:.1f}% → Bullish dealer repositioning")
    elif changes['flip_change_pct'] < -1.0:
        insights.append(f"📉 **Flip Falling**: Flip point moved down {abs(changes['flip_change_pct']):.1f}% → Bearish dealer repositioning")

    # Price vs Flip divergence
    if changes['price_change_pct'] > 0 and changes['flip_change_pct'] < 0:
        insights.append("⚠️ **Divergence**: Price up but flip down → Potential reversal signal")
    elif changes['price_change_pct'] < 0 and changes['flip_change_pct'] > 0:
        insights.append("⚠️ **Divergence**: Price down but flip up → Potential bounce")

    # IV changes
    if changes['iv_change'] > 5:
        insights.append(f"📈 **IV Spiking**: IV increased {changes['iv_change']:.1f}% → Fear/uncertainty rising")
    elif changes['iv_change'] < -5:
        insights.append(f"📉 **IV Crushing**: IV decreased {abs(changes['iv_change']):.1f}% → Premium selling opportunity")

    # PCR changes
    if changes['pcr_change'] > 0.2:
        insights.append(f"🔴 **Put Buying**: PCR increased {changes['pcr_change']:+.2f} → Bearish positioning")
    elif changes['pcr_change'] < -0.2:
        insights.append(f"🟢 **Call Buying**: PCR decreased {changes['pcr_change']:+.2f} → Bullish positioning")

    # Display insights
    if insights:
        for insight in insights:
            st.markdown(insight)
    else:
        st.info("No significant intraday changes detected yet. Check back as more data accumulates.")


def should_capture_snapshot() -> bool:
    """
    Determine if we should capture a snapshot based on time of day

    Returns:
        True if it's a key time to capture data
    """

    now = datetime.now().time()

    # Key times during trading day (ET)
    key_times = [
        time(9, 30),   # Market open
        time(10, 0),   # 30 mins in
        time(11, 0),   # Mid-morning
        time(12, 0),   # Lunch
        time(13, 0),   # Post-lunch
        time(14, 0),   # 2 PM
        time(15, 0),   # 3 PM
        time(15, 45),  # 15 mins before close
    ]

    # Check if within 5 mins of a key time
    for key_time in key_times:
        key_datetime = datetime.combine(datetime.today(), key_time)
        now_datetime = datetime.combine(datetime.today(), now)
        diff = abs((now_datetime - key_datetime).total_seconds())

        if diff < 300:  # Within 5 minutes
            return True

    return False


def display_snapshot_widget(symbol: str, gex_data: Dict, skew_data: Dict = None):
    """
    Lightweight widget to capture snapshots

    Args:
        symbol: Current symbol
        gex_data: Current GEX data
        skew_data: Current skew data
    """

    tracker = IntradayTracker()

    st.sidebar.markdown("---")
    st.sidebar.subheader("📸 Intraday Tracking")

    snapshot_count = tracker.get_snapshot_count(symbol)
    st.sidebar.metric(f"{symbol} Snapshots Today", snapshot_count)

    if st.sidebar.button("📸 Capture Snapshot", help="Save current GEX state"):
        tracker.capture_snapshot(symbol, gex_data, skew_data)
        st.sidebar.success(f"✅ Snapshot saved!")
        st.rerun()

    # Auto-capture at key times
    if should_capture_snapshot():
        st.sidebar.info("⏰ Key trading time - Consider capturing a snapshot!")


def get_intraday_summary(symbol: str) -> str:
    """
    Get quick text summary of intraday changes

    Args:
        symbol: Ticker symbol

    Returns:
        Summary string
    """

    tracker = IntradayTracker()
    changes = tracker.calculate_changes(symbol)

    if not changes:
        return "No intraday data yet"

    summary = f"{symbol} Intraday: "

    if changes['net_gex_change'] < -1e9:
        summary += "GEX ↓ (more volatile), "
    elif changes['net_gex_change'] > 1e9:
        summary += "GEX ↑ (less volatile), "

    if changes['flip_change_pct'] > 1:
        summary += "Flip ↑, "
    elif changes['flip_change_pct'] < -1:
        summary += "Flip ↓, "

    if changes['iv_change'] > 5:
        summary += "IV spiking"
    elif changes['iv_change'] < -5:
        summary += "IV crushing"
    else:
        summary += "IV stable"

    return summary
