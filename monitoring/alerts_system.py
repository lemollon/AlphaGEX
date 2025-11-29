"""
Real-Time Alerts System
Monitor key levels and market conditions

This module provides alert logic without any UI dependencies.
Alerts are stored in-memory and can be persisted to database.
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """Individual alert definition"""
    alert_type: str  # 'flip_proximity', 'wall_break', 'gex_regime', 'iv_spike'
    symbol: str
    condition: str
    threshold: float
    current_value: Optional[float] = None
    triggered: bool = False
    trigger_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

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
                return True, f"{self.symbol}: Price ${spot:.2f} is within {distance_pct:.2f}% of flip point ${flip:.2f}"

        elif self.alert_type == 'wall_break':
            spot = current_data.get('spot_price', 0)
            call_wall = current_data.get('call_wall', 0)
            put_wall = current_data.get('put_wall', 0)

            if self.condition == 'call_wall' and call_wall and spot >= call_wall:
                return True, f"{self.symbol}: CALL WALL BROKEN - Price ${spot:.2f} above ${call_wall:.2f}"
            if self.condition == 'put_wall' and put_wall and spot <= put_wall:
                return True, f"{self.symbol}: PUT WALL BROKEN - Price ${spot:.2f} below ${put_wall:.2f}"

        elif self.alert_type == 'gex_regime':
            net_gex = current_data.get('net_gex', 0)

            if self.condition == 'flip_negative' and net_gex < 0:
                return True, f"{self.symbol}: GEX REGIME CHANGE - Net GEX turned NEGATIVE (${net_gex/1e9:.2f}B)"
            elif self.condition == 'flip_positive' and net_gex > 0:
                return True, f"{self.symbol}: GEX REGIME CHANGE - Net GEX turned POSITIVE (${net_gex/1e9:.2f}B)"

        elif self.alert_type == 'iv_spike':
            iv = current_data.get('iv', 0)

            if iv > self.threshold:
                return True, f"{self.symbol}: IV SPIKE - Implied Vol at {iv:.1f}% (threshold: {self.threshold:.1f}%)"

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
            'trigger_time': self.trigger_time.isoformat() if self.trigger_time else None,
            'created_at': self.created_at.isoformat()
        }


class AlertManager:
    """
    Manage and monitor alerts

    Uses in-memory storage. For persistence, use save_to_db/load_from_db.
    """

    def __init__(self):
        self.active_alerts: List[Alert] = []
        self.triggered_alerts: List[Dict] = []
        self.alert_history: List[Dict] = []
        self.last_check: Optional[datetime] = None

    def add_alert(self, alert: Alert) -> None:
        """Add new alert to monitoring"""
        self.active_alerts.append(alert)
        logger.info(f"Alert added: {alert.alert_type} for {alert.symbol}")

    def remove_alert(self, index: int) -> bool:
        """Remove alert by index"""
        if 0 <= index < len(self.active_alerts):
            removed = self.active_alerts.pop(index)
            logger.info(f"Alert removed: {removed.alert_type} for {removed.symbol}")
            return True
        return False

    def check_alerts(self, market_data: Dict) -> List[str]:
        """
        Check all active alerts against current data

        Args:
            market_data: Dict with 'symbol', 'spot_price', 'flip_point', 'call_wall', 'put_wall', 'net_gex', 'iv'

        Returns:
            List of triggered alert messages
        """
        triggered_messages = []
        self.last_check = datetime.now()

        for alert in self.active_alerts:
            if alert.symbol == market_data.get('symbol', ''):
                triggered, message = alert.check(market_data)

                if triggered and not alert.triggered:
                    # New trigger
                    alert.triggered = True
                    alert.trigger_time = datetime.now()
                    triggered_messages.append(message)

                    # Log the trigger
                    logger.warning(f"ALERT TRIGGERED: {message}")

                    # Add to triggered list
                    self.triggered_alerts.append(alert.to_dict())

                    # Add to history
                    self.alert_history.append({
                        'time': datetime.now(),
                        'message': message,
                        'alert': alert.to_dict()
                    })

        # Remove triggered alerts from active list
        self.active_alerts = [a for a in self.active_alerts if not a.triggered]

        return triggered_messages

    def get_active_count(self) -> int:
        """Get count of active alerts"""
        return len(self.active_alerts)

    def get_triggered_count(self, hours: int = 24) -> int:
        """Get count of triggered alerts in last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [a for a in self.alert_history if a['time'] > cutoff]
        return len(recent)

    def get_status(self) -> Dict:
        """Get alert system status"""
        return {
            'active_count': self.get_active_count(),
            'triggered_24h': self.get_triggered_count(24),
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'active_alerts': [a.to_dict() for a in self.active_alerts],
            'recent_triggers': self.triggered_alerts[-10:]  # Last 10
        }

    def print_status(self) -> None:
        """Print alert status to console"""
        status = self.get_status()
        print(f"\n{'='*50}")
        print("ALERT SYSTEM STATUS")
        print(f"{'='*50}")
        print(f"Active Alerts: {status['active_count']}")
        print(f"Triggered (24h): {status['triggered_24h']}")
        print(f"Last Check: {status['last_check'] or 'Never'}")

        if self.active_alerts:
            print(f"\nActive Alerts:")
            for i, alert in enumerate(self.active_alerts):
                print(f"  {i+1}. {alert.symbol} - {alert.alert_type} ({alert.condition})")

        if self.triggered_alerts:
            print(f"\nRecent Triggers:")
            for trigger in self.triggered_alerts[-5:]:
                print(f"  - {trigger.get('symbol')}: {trigger.get('type')}")


def create_alert_presets(symbol: str) -> List[Alert]:
    """
    Create preset alerts for common scenarios

    Args:
        symbol: Ticker symbol

    Returns:
        List of preset Alert objects
    """
    return [
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


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create global alert manager"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
