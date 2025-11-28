"""
Real-Time Alerts System
Monitor key levels and market conditions with intelligent polling
"""

import streamlit as st
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import pandas as pd


class Alert:
    """Individual alert definition"""

    def __init__(self, alert_type: str, symbol: str, condition: str, threshold: float, current_value: float = None):
        self.alert_type = alert_type  # 'flip_proximity', 'wall_break', 'gex_regime', 'iv_spike'
        self.symbol = symbol
        self.condition = condition
        self.threshold = threshold
        self.current_value = current_value
        self.triggered = False
        self.trigger_time = None

    def check(self, current_data: Dict) -> Tuple[bool, str]:
        """
        Check if alert should trigger

        Returns:
            (triggered: bool, message: str)
        """

        if self.alert_type == 'flip_proximity':
            spot = current_data.get('spot_price', 0)
            flip = current_data.get('flip_point', 0)
            distance_pct = abs((flip - spot) / spot * 100) if spot else 999

            if distance_pct <= self.threshold:
                return True, f"🎯 {self.symbol}: Price ${spot:.2f} is within {distance_pct:.2f}% of flip point ${flip:.2f}!"

        elif self.alert_type == 'wall_break':
            spot = current_data.get('spot_price', 0)
            call_wall = current_data.get('call_wall', 0)
            put_wall = current_data.get('put_wall', 0)

            if call_wall and spot >= call_wall:
                return True, f"🚀 {self.symbol}: CALL WALL BROKEN! Price ${spot:.2f} above ${call_wall:.2f}"
            if put_wall and spot <= put_wall:
                return True, f"📉 {self.symbol}: PUT WALL BROKEN! Price ${spot:.2f} below ${put_wall:.2f}"

        elif self.alert_type == 'gex_regime':
            net_gex = current_data.get('net_gex', 0)

            if self.condition == 'flip_negative' and net_gex < 0:
                return True, f"⚡ {self.symbol}: GEX REGIME CHANGE! Net GEX turned NEGATIVE (${net_gex/1e9:.2f}B)"
            elif self.condition == 'flip_positive' and net_gex > 0:
                return True, f"🛡️ {self.symbol}: GEX REGIME CHANGE! Net GEX turned POSITIVE (${net_gex/1e9:.2f}B)"

        elif self.alert_type == 'iv_spike':
            iv = current_data.get('iv', 0)

            if iv > self.threshold:
                return True, f"📈 {self.symbol}: IV SPIKE! Implied Vol at {iv:.1f}% (threshold: {self.threshold:.1f}%)"

        return False, ""

    def to_dict(self) -> Dict:
        """Convert alert to dictionary for storage"""
        return {
            'type': self.alert_type,
            'symbol': self.symbol,
            'condition': self.condition,
            'threshold': self.threshold,
            'current_value': self.current_value,
            'triggered': self.triggered,
            'trigger_time': self.trigger_time
        }


class AlertManager:
    """Manage and monitor alerts"""

    def __init__(self):
        if 'active_alerts' not in st.session_state:
            st.session_state.active_alerts = []
        if 'triggered_alerts' not in st.session_state:
            st.session_state.triggered_alerts = []
        if 'alert_history' not in st.session_state:
            st.session_state.alert_history = []

    def add_alert(self, alert: Alert):
        """Add new alert to monitoring"""
        st.session_state.active_alerts.append(alert)

    def remove_alert(self, index: int):
        """Remove alert by index"""
        if 0 <= index < len(st.session_state.active_alerts):
            st.session_state.active_alerts.pop(index)

    def check_alerts(self, market_data: Dict) -> List[str]:
        """
        Check all active alerts against current data

        Returns:
            List of triggered alert messages
        """
        triggered_messages = []

        for alert in st.session_state.active_alerts:
            if alert.symbol == market_data.get('symbol', ''):
                triggered, message = alert.check(market_data)

                if triggered and not alert.triggered:
                    # New trigger
                    alert.triggered = True
                    alert.trigger_time = datetime.now()
                    triggered_messages.append(message)

                    # Move to triggered list
                    st.session_state.triggered_alerts.append(alert.to_dict())

                    # Add to history
                    st.session_state.alert_history.append({
                        'time': datetime.now(),
                        'message': message,
                        'alert': alert.to_dict()
                    })

        # Remove triggered alerts from active list
        st.session_state.active_alerts = [a for a in st.session_state.active_alerts if not a.triggered]

        return triggered_messages

    def get_active_count(self) -> int:
        """Get count of active alerts"""
        return len(st.session_state.active_alerts)

    def get_triggered_count(self) -> int:
        """Get count of triggered alerts (last 24h)"""
        cutoff = datetime.now() - timedelta(hours=24)
        recent = [a for a in st.session_state.alert_history if a['time'] > cutoff]
        return len(recent)


def display_alert_dashboard():
    """Main alerts dashboard"""

    st.header("🔔 Real-Time Alerts")

    manager = AlertManager()

    # Alert stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Active Alerts", manager.get_active_count())
    with col2:
        st.metric("Triggered (24h)", manager.get_triggered_count())
    with col3:
        last_check = st.session_state.get('last_alert_check', 'Never')
        if isinstance(last_check, datetime):
            time_str = last_check.strftime('%H:%M:%S')
        else:
            time_str = last_check
        st.metric("Last Check", time_str)

    # Recent triggered alerts
    if st.session_state.triggered_alerts:
        st.subheader("🎯 Recently Triggered")
        for idx, alert_dict in enumerate(st.session_state.triggered_alerts[-5:]):  # Show last 5
            st.success(f"{alert_dict.get('symbol', 'N/A')}: {alert_dict.get('type', 'Unknown')} alert triggered")

    # Create new alert
    st.subheader("➕ Create New Alert")

    with st.form("new_alert_form"):
        col1, col2 = st.columns(2)

        with col1:
            symbol = st.text_input("Symbol", value="SPY").upper()
            alert_type = st.selectbox(
                "Alert Type",
                options=[
                    'flip_proximity',
                    'wall_break',
                    'gex_regime',
                    'iv_spike'
                ],
                format_func=lambda x: {
                    'flip_proximity': '🎯 Price Near Flip Point',
                    'wall_break': '🚀 Wall Break',
                    'gex_regime': '⚡ GEX Regime Change',
                    'iv_spike': '📈 IV Spike'
                }[x]
            )

        with col2:
            if alert_type == 'flip_proximity':
                threshold = st.slider("Distance to Flip (%)", 0.1, 5.0, 1.0, 0.1)
                condition = 'within'
            elif alert_type == 'wall_break':
                condition = st.selectbox("Direction", ['call_wall', 'put_wall'])
                threshold = 0
            elif alert_type == 'gex_regime':
                condition = st.selectbox("Change To", ['flip_negative', 'flip_positive'])
                threshold = 0
            elif alert_type == 'iv_spike':
                threshold = st.slider("IV Threshold (%)", 10.0, 100.0, 50.0, 5.0)
                condition = 'above'

        submitted = st.form_submit_button("🔔 Create Alert")

        if submitted:
            new_alert = Alert(
                alert_type=alert_type,
                symbol=symbol,
                condition=condition,
                threshold=threshold
            )
            manager.add_alert(new_alert)
            st.success(f"✅ Alert created for {symbol}")
            st.rerun()

    # Active alerts list
    if st.session_state.active_alerts:
        st.subheader("📋 Active Alerts")

        for idx, alert in enumerate(st.session_state.active_alerts):
            col1, col2 = st.columns([5, 1])

            with col1:
                alert_desc = f"{alert.symbol} - {alert.alert_type}"
                if alert.alert_type == 'flip_proximity':
                    alert_desc += f" (within {alert.threshold}%)"
                elif alert.alert_type == 'iv_spike':
                    alert_desc += f" (above {alert.threshold}%)"

                st.text(alert_desc)

            with col2:
                if st.button("🗑️", key=f"remove_alert_{idx}"):
                    manager.remove_alert(idx)
                    st.rerun()


def display_alert_monitor_widget(current_data: Dict):
    """
    Lightweight alert monitor widget for sidebar

    Args:
        current_data: Current market data to check against alerts
    """

    manager = AlertManager()

    # Check alerts
    triggered = manager.check_alerts(current_data)
    st.session_state.last_alert_check = datetime.now()

    # Display triggered alerts
    if triggered:
        st.sidebar.warning(f"🔔 {len(triggered)} Alert(s) Triggered!")
        for message in triggered:
            st.sidebar.success(message)

    # Alert summary
    active_count = manager.get_active_count()
    if active_count > 0:
        st.sidebar.info(f"👁️ Monitoring {active_count} alerts")


def display_alert_settings():
    """Alert system settings"""

    st.sidebar.subheader("🔔 Alert Settings")

    # Enable/disable alerts
    alerts_enabled = st.sidebar.checkbox(
        "Enable Alerts",
        value=True,
        help="Monitor active alerts and display notifications"
    )

    if alerts_enabled:
        # Check frequency
        check_frequency = st.sidebar.slider(
            "Check Every (minutes)",
            min_value=1,
            max_value=30,
            value=5,
            help="How often to check alerts (fewer checks = fewer API calls)"
        )

        # Sound notifications (future feature)
        sound_enabled = st.sidebar.checkbox(
            "Sound Notifications",
            value=False,
            help="Play sound when alert triggers (future feature)"
        )

        return {
            'enabled': True,
            'check_frequency': check_frequency,
            'sound': sound_enabled
        }

    return {'enabled': False}


def create_alert_presets(symbol: str) -> List[Alert]:
    """
    Create preset alerts for common scenarios

    Args:
        symbol: Ticker symbol

    Returns:
        List of preset Alert objects
    """

    presets = [
        Alert(
            alert_type='flip_proximity',
            symbol=symbol,
            condition='within',
            threshold=1.0  # Within 1% of flip
        ),
        Alert(
            alert_type='wall_break',
            symbol=symbol,
            condition='call_wall',
            threshold=0
        ),
        Alert(
            alert_type='wall_break',
            symbol=symbol,
            condition='put_wall',
            threshold=0
        ),
        Alert(
            alert_type='gex_regime',
            symbol=symbol,
            condition='flip_negative',
            threshold=0
        ),
        Alert(
            alert_type='iv_spike',
            symbol=symbol,
            condition='above',
            threshold=50.0  # IV above 50%
        )
    ]

    return presets


def display_quick_alert_setup(symbol: str):
    """Quick one-click alert setup for current symbol"""

    with st.expander(f"⚡ Quick Alerts for {symbol}"):
        st.markdown("One-click setup for common alert scenarios:")

        manager = AlertManager()
        presets = create_alert_presets(symbol)

        cols = st.columns(2)

        for idx, preset in enumerate(presets):
            with cols[idx % 2]:
                preset_name = {
                    'flip_proximity': '🎯 Near Flip (1%)',
                    'wall_break': f"🚀 {preset.condition.replace('_', ' ').title()}",
                    'gex_regime': f"⚡ GEX → {preset.condition.split('_')[1].title()}",
                    'iv_spike': '📈 IV Spike (50%+)'
                }.get(f"{preset.alert_type}", "Alert")

                if st.button(preset_name, key=f"preset_{idx}", use_container_width=True):
                    manager.add_alert(preset)
                    st.success(f"✅ {preset_name} activated!")
                    st.rerun()
