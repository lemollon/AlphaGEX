"""
position_management_agent.py - AI Agent for Active Position Monitoring

This agent monitors your active positions and alerts when market conditions change
from entry, helping you make better exit and adjustment decisions.
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from utils.console_output import st
from database_adapter import get_connection


class PositionManagementAgent:
    """AI agent that monitors positions and detects condition changes"""

    def __init__(self):
        self._ensure_entry_columns()

    def _ensure_entry_columns(self):
        """Ensure positions table has entry condition columns (PostgreSQL)"""
        conn = get_connection()
        c = conn.cursor()

        # Add entry condition columns if they don't exist (PostgreSQL syntax)
        columns_to_add = [
            ("entry_net_gex", "REAL"),
            ("entry_flip_point", "REAL"),
            ("entry_spot_price", "REAL"),
            ("entry_regime", "TEXT")
        ]

        for col_name, col_type in columns_to_add:
            try:
                c.execute(f"ALTER TABLE positions ADD COLUMN {col_name} {col_type}")
            except Exception:
                # Column likely already exists
                conn.rollback()

        conn.commit()
        conn.close()

    def store_entry_conditions(self, position_id: int, gex_data: Dict):
        """Store entry conditions when position is opened (PostgreSQL)"""

        conn = get_connection()
        c = conn.cursor()

        net_gex = gex_data.get('net_gex', 0)
        flip_point = gex_data.get('flip_point', 0)
        spot_price = gex_data.get('spot_price', 0)

        # Determine entry regime
        regime = self._determine_regime(net_gex, spot_price, flip_point)

        c.execute("""
            UPDATE positions
            SET entry_net_gex = %s,
                entry_flip_point = %s,
                entry_spot_price = %s,
                entry_regime = %s
            WHERE id = %s
        """, (net_gex, flip_point, spot_price, regime, position_id))

        conn.commit()
        conn.close()

    def _determine_regime(self, net_gex: float, spot: float, flip: float) -> str:
        """Determine market regime from GEX data"""

        gex_regime = "Negative GEX" if net_gex < 0 else "Positive GEX"

        if spot == 0 or flip == 0:
            position_regime = "Unknown"
        elif spot > flip:
            position_regime = "Above Flip"
        elif spot < flip:
            position_regime = "Below Flip"
        else:
            position_regime = "At Flip"

        return f"{gex_regime}, {position_regime}"

    def get_active_positions_with_conditions(self) -> pd.DataFrame:
        """Get all active positions with entry conditions (PostgreSQL)"""

        conn = get_connection()

        query = """
            SELECT
                id,
                symbol,
                strategy,
                entry_price,
                quantity,
                opened_at,
                entry_net_gex,
                entry_flip_point,
                entry_spot_price,
                entry_regime,
                notes
            FROM positions
            WHERE status = 'OPEN'
            ORDER BY opened_at DESC
        """

        df = pd.read_sql_query(query, conn.raw_connection)
        conn.close()

        if not df.empty:
            df['opened_at'] = pd.to_datetime(df['opened_at'])

        return df

    def check_position_conditions(self, position: Dict, current_gex: Dict) -> Dict:
        """Check if current conditions differ from entry conditions"""

        # Extract entry conditions
        entry_net_gex = position.get('entry_net_gex', 0)
        entry_flip = position.get('entry_flip_point', 0)
        entry_spot = position.get('entry_spot_price', 0)
        entry_regime = position.get('entry_regime', 'Unknown')

        # Extract current conditions
        current_net_gex = current_gex.get('net_gex', 0)
        current_flip = current_gex.get('flip_point', 0)
        current_spot = current_gex.get('spot_price', 0)
        current_regime = self._determine_regime(current_net_gex, current_spot, current_flip)

        # Calculate changes
        gex_change = current_net_gex - entry_net_gex
        gex_change_pct = (gex_change / abs(entry_net_gex) * 100) if entry_net_gex != 0 else 0

        flip_change = current_flip - entry_flip
        flip_change_pct = (flip_change / entry_flip * 100) if entry_flip != 0 else 0

        spot_change = current_spot - entry_spot
        spot_change_pct = (spot_change / entry_spot * 100) if entry_spot != 0 else 0

        # Detect condition changes
        alerts = []
        severity = "info"  # info, warning, critical

        # Alert 1: GEX regime flip
        entry_gex_sign = "negative" if entry_net_gex < 0 else "positive"
        current_gex_sign = "negative" if current_net_gex < 0 else "positive"

        if entry_gex_sign != current_gex_sign:
            alerts.append({
                'type': 'gex_regime_flip',
                'message': f"🚨 GEX Regime Flip: Entry was {entry_gex_sign} (${entry_net_gex/1e9:.2f}B), now {current_gex_sign} (${current_net_gex/1e9:.2f}B)",
                'severity': 'critical',
                'suggestion': "Position thesis may be invalidated. Consider closing or hedging."
            })
            severity = "critical"

        # Alert 2: Large GEX change (same sign but >50% change)
        elif abs(gex_change_pct) > 50:
            alerts.append({
                'type': 'gex_material_change',
                'message': f"⚠️ Large GEX Change: {gex_change_pct:+.1f}% from entry (${entry_net_gex/1e9:.2f}B → ${current_net_gex/1e9:.2f}B)",
                'severity': 'warning',
                'suggestion': "Dealer positioning shifted significantly. Monitor closely."
            })
            if severity != "critical":
                severity = "warning"

        # Alert 3: Flip point movement
        if abs(flip_change_pct) > 1.0:  # >1% move
            direction = "up" if flip_change > 0 else "down"
            alerts.append({
                'type': 'flip_movement',
                'message': f"📊 Flip Point Moved {direction.upper()}: {flip_change_pct:+.2f}% (${entry_flip:.2f} → ${current_flip:.2f})",
                'severity': 'warning' if abs(flip_change_pct) > 2 else 'info',
                'suggestion': f"Target zone shifted {direction}. Consider rolling strikes {direction}." if abs(flip_change_pct) > 2 else f"Flip moved slightly {direction}."
            })
            if severity == "info" and abs(flip_change_pct) > 2:
                severity = "warning"

        # Alert 4: Position relative to flip changed
        entry_above_flip = "Above Flip" in entry_regime
        current_above_flip = "Above Flip" in current_regime

        if entry_above_flip != current_above_flip:
            crossed = "above" if current_above_flip else "below"
            alerts.append({
                'type': 'flip_cross',
                'message': f"🎯 Price Crossed Flip: Now {crossed} flip (Entry: ${entry_spot:.2f}, Flip: ${current_flip:.2f}, Current: ${current_spot:.2f})",
                'severity': 'warning',
                'suggestion': f"Price crossed flip point. Dealer hedging dynamics changed."
            })
            if severity == "info":
                severity = "warning"

        # Alert 5: Large price move
        if abs(spot_change_pct) > 5.0:  # >5% price move
            alerts.append({
                'type': 'large_price_move',
                'message': f"📈 Large Price Move: {spot_change_pct:+.2f}% from entry (${entry_spot:.2f} → ${current_spot:.2f})",
                'severity': 'info',
                'suggestion': "Consider taking profits or adjusting stops." if spot_change_pct > 0 else "Monitor for reversal."
            })

        # Alert 6: Favorable conditions (if no critical alerts)
        if not alerts and abs(spot_change_pct) > 2.0 and severity == "info":
            alerts.append({
                'type': 'stable_conditions',
                'message': f"✅ Conditions Stable: Entry thesis intact. Price {spot_change_pct:+.2f}% from entry.",
                'severity': 'info',
                'suggestion': "Let position work. Conditions remain favorable."
            })

        return {
            'alerts': alerts,
            'severity': severity,
            'changes': {
                'gex_change': gex_change,
                'gex_change_pct': gex_change_pct,
                'flip_change': flip_change,
                'flip_change_pct': flip_change_pct,
                'spot_change': spot_change,
                'spot_change_pct': spot_change_pct,
            },
            'entry': {
                'net_gex': entry_net_gex,
                'flip_point': entry_flip,
                'spot_price': entry_spot,
                'regime': entry_regime
            },
            'current': {
                'net_gex': current_net_gex,
                'flip_point': current_flip,
                'spot_price': current_spot,
                'regime': current_regime
            }
        }

    def monitor_all_positions(self, api_client) -> List[Dict]:
        """Monitor all active positions and return alerts"""

        positions = self.get_active_positions_with_conditions()
        all_alerts = []

        if positions.empty:
            return all_alerts

        for _, position in positions.iterrows():
            symbol = position['symbol']

            # Skip if no entry conditions stored
            if pd.isna(position['entry_net_gex']) or position['entry_net_gex'] == 0:
                continue

            try:
                # Fetch current GEX data for this symbol
                current_gex = api_client.get_net_gamma(symbol)

                if current_gex and not current_gex.get('error'):
                    # Check conditions
                    analysis = self.check_position_conditions(position.to_dict(), current_gex)

                    if analysis['alerts']:
                        all_alerts.append({
                            'position_id': position['id'],
                            'symbol': symbol,
                            'strategy': position['strategy'],
                            'opened_at': position['opened_at'],
                            'analysis': analysis
                        })

            except Exception as e:
                # Skip this position if we can't fetch data
                continue

        return all_alerts


def display_position_monitoring(agent: PositionManagementAgent):
    """Display position monitoring dashboard"""

    st.subheader("🔍 Active Position Monitoring")
    st.markdown("**AI-powered monitoring of entry conditions vs current market**")

    # Get active positions
    positions = agent.get_active_positions_with_conditions()

    if positions.empty:
        st.info("""
        📊 **No active positions to monitor**

        When you open positions, this agent will:
        - Store entry conditions (GEX, flip point, regime)
        - Monitor how conditions change after entry
        - Alert when your thesis is invalidated
        - Suggest adjustments (roll, close, hedge)

        Open a position to see this in action!
        """)
        return

    # Display positions
    st.markdown(f"**Monitoring {len(positions)} active position(s)**")

    # Check if we should run monitoring
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info("💡 Click 'Refresh Symbol' in the sidebar to update position conditions")
    with col2:
        if st.button("🔍 Check All Now", use_container_width=True):
            with st.spinner("Checking position conditions..."):
                alerts = agent.monitor_all_positions(st.session_state.api_client)
                st.session_state.position_alerts = alerts
                st.rerun()

    # Display alerts if any
    if 'position_alerts' in st.session_state and st.session_state.position_alerts:
        alerts = st.session_state.position_alerts

        st.divider()
        st.subheader("⚠️ Position Alerts")

        for alert_data in alerts:
            symbol = alert_data['symbol']
            strategy = alert_data['strategy']
            analysis = alert_data['analysis']
            severity = analysis['severity']

            # Choose color based on severity
            if severity == "critical":
                st.error(f"**{symbol} - {strategy}**")
            elif severity == "warning":
                st.warning(f"**{symbol} - {strategy}**")
            else:
                st.info(f"**{symbol} - {strategy}**")

            # Display each alert
            for alert in analysis['alerts']:
                st.markdown(alert['message'])
                st.caption(f"💡 {alert['suggestion']}")

            # Show entry vs current comparison
            with st.expander(f"📊 View Entry vs Current Conditions - {symbol}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Entry Conditions**")
                    st.metric("Net GEX", f"${analysis['entry']['net_gex']/1e9:.2f}B")
                    st.metric("Flip Point", f"${analysis['entry']['flip_point']:.2f}")
                    st.metric("Spot Price", f"${analysis['entry']['spot_price']:.2f}")
                    st.caption(analysis['entry']['regime'])

                with col2:
                    st.markdown("**Current Conditions**")
                    st.metric(
                        "Net GEX",
                        f"${analysis['current']['net_gex']/1e9:.2f}B",
                        delta=f"{analysis['changes']['gex_change_pct']:+.1f}%"
                    )
                    st.metric(
                        "Flip Point",
                        f"${analysis['current']['flip_point']:.2f}",
                        delta=f"{analysis['changes']['flip_change_pct']:+.2f}%"
                    )
                    st.metric(
                        "Spot Price",
                        f"${analysis['current']['spot_price']:.2f}",
                        delta=f"{analysis['changes']['spot_change_pct']:+.2f}%"
                    )
                    st.caption(analysis['current']['regime'])

            st.divider()

    else:
        st.divider()
        st.markdown("**Active Positions**")

        # Display positions table
        display_positions = positions[['symbol', 'strategy', 'entry_price', 'opened_at']].copy()
        display_positions['opened_at'] = display_positions['opened_at'].dt.strftime('%Y-%m-%d %H:%M')
        display_positions.columns = ['Symbol', 'Strategy', 'Entry Price', 'Opened']

        st.dataframe(display_positions, use_container_width=True, hide_index=True)

        # Check for positions without entry conditions
        missing_conditions = positions[positions['entry_net_gex'].isna() | (positions['entry_net_gex'] == 0)]
        if not missing_conditions.empty:
            st.warning(f"⚠️ {len(missing_conditions)} position(s) missing entry conditions. Refresh symbols to capture current conditions.")


def display_position_monitoring_widget():
    """Compact widget for sidebar showing position alerts"""

    if 'position_alerts' not in st.session_state or not st.session_state.position_alerts:
        return

    alerts = st.session_state.position_alerts

    # Count by severity
    critical = sum(1 for a in alerts if a['analysis']['severity'] == 'critical')
    warning = sum(1 for a in alerts if a['analysis']['severity'] == 'warning')

    if critical > 0:
        st.error(f"🚨 {critical} Critical Position Alert(s)")
    elif warning > 0:
        st.warning(f"⚠️ {warning} Position Warning(s)")

    st.caption("Check Positions tab for details")
