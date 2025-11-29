"""
Intraday GEX Tracking
Monitor dealer repositioning throughout the trading day

This module provides logic-only intraday tracking functionality.
UI rendering has been removed - use the backend API for tracking views.
"""

from typing import Dict, List, Optional
from datetime import datetime, time
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class IntradayTracker:
    """Track GEX metrics throughout the day using in-memory storage"""

    def __init__(self):
        # In-memory storage for intraday snapshots
        self._snapshots: Dict[str, List[Dict]] = {}

    def _safe_float(self, value, default=0.0) -> float:
        """Safely convert value to float, handling corrupted/invalid data"""
        try:
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
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
        if symbol not in self._snapshots:
            self._snapshots[symbol] = []

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
        existing_times = [s['time_str'] for s in self._snapshots[symbol]]
        if snapshot['time_str'] not in existing_times:
            self._snapshots[symbol].append(snapshot)

            # Keep only today's data (clear at midnight)
            today = datetime.now().date()
            self._snapshots[symbol] = [
                s for s in self._snapshots[symbol]
                if s['timestamp'].date() == today
            ]

    def get_snapshots(self, symbol: str) -> List[Dict]:
        """Get all snapshots for a symbol"""
        return self._snapshots.get(symbol, [])

    def get_snapshot_count(self, symbol: str) -> int:
        """Get number of snapshots for a symbol"""
        return len(self.get_snapshots(symbol))

    def _validate_snapshots(self, snapshots: List[Dict]) -> List[Dict]:
        """Remove corrupted snapshots"""
        valid_snapshots = []
        for snapshot in snapshots:
            try:
                self._safe_float(snapshot.get('spot_price', 0))
                self._safe_float(snapshot.get('net_gex', 0))
                self._safe_float(snapshot.get('flip_point', 0))
                valid_snapshots.append(snapshot)
            except (ValueError, TypeError):
                continue
        return valid_snapshots

    def calculate_changes(self, symbol: str) -> Optional[Dict]:
        """
        Calculate intraday changes

        Returns:
            Dictionary with change metrics or None if insufficient data
        """
        snapshots = self.get_snapshots(symbol)
        snapshots = self._validate_snapshots(snapshots)

        if len(snapshots) < 2:
            return None

        first = snapshots[0]
        latest = snapshots[-1]

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
            self._snapshots[symbol] = []
        else:
            self._snapshots = {}

    def get_snapshots_dataframe(self, symbol: str) -> pd.DataFrame:
        """Get snapshots as a DataFrame for charting"""
        snapshots = self.get_snapshots(symbol)
        if not snapshots:
            return pd.DataFrame()
        return pd.DataFrame(snapshots)


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


def get_intraday_summary(symbol: str, tracker: IntradayTracker) -> str:
    """
    Get quick text summary of intraday changes

    Args:
        symbol: Ticker symbol
        tracker: IntradayTracker instance

    Returns:
        Summary string
    """
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


def get_intraday_insights(changes: Dict) -> List[str]:
    """
    Generate trading insights from intraday changes

    Args:
        changes: Dictionary from calculate_changes()

    Returns:
        List of insight strings
    """
    if not changes:
        return []

    insights = []

    # Net GEX regime shift
    if abs(changes['net_gex_change']) > 1e9:  # >$1B change
        direction = "more negative" if changes['net_gex_change'] < 0 else "more positive"
        insights.append(f"GEX Regime Shift: Net GEX became {direction} by ${abs(changes['net_gex_change'])/1e9:.2f}B")

        if changes['net_gex_change'] < 0:
            insights.append("Dealers getting SHORT gamma - More volatility expected")
        else:
            insights.append("Dealers getting LONG gamma - Volatility suppression")

    # Flip point movement
    if changes['flip_change_pct'] > 1.0:
        insights.append(f"Flip Rising: Flip point moved up {changes['flip_change_pct']:.1f}% - Bullish dealer repositioning")
    elif changes['flip_change_pct'] < -1.0:
        insights.append(f"Flip Falling: Flip point moved down {abs(changes['flip_change_pct']):.1f}% - Bearish dealer repositioning")

    # Price vs Flip divergence
    if changes['price_change_pct'] > 0 and changes['flip_change_pct'] < 0:
        insights.append("Divergence: Price up but flip down - Potential reversal signal")
    elif changes['price_change_pct'] < 0 and changes['flip_change_pct'] > 0:
        insights.append("Divergence: Price down but flip up - Potential bounce")

    # IV changes
    if changes['iv_change'] > 5:
        insights.append(f"IV Spiking: IV increased {changes['iv_change']:.1f}% - Fear/uncertainty rising")
    elif changes['iv_change'] < -5:
        insights.append(f"IV Crushing: IV decreased {abs(changes['iv_change']):.1f}% - Premium selling opportunity")

    # PCR changes
    if changes['pcr_change'] > 0.2:
        insights.append(f"Put Buying: PCR increased {changes['pcr_change']:+.2f} - Bearish positioning")
    elif changes['pcr_change'] < -0.2:
        insights.append(f"Call Buying: PCR decreased {changes['pcr_change']:+.2f} - Bullish positioning")

    return insights


# Module-level tracker instance
_tracker: Optional[IntradayTracker] = None


def get_tracker() -> IntradayTracker:
    """Get or create the intraday tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = IntradayTracker()
    return _tracker
