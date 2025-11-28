"""
Psychology Trap Detection - Push Notification System

This module provides real-time push notifications for critical psychology trap patterns.
Notifies users immediately when high-impact patterns are detected.

Critical Patterns:
- GAMMA_SQUEEZE_CASCADE - VIX spike + short gamma = explosive move
- FLIP_POINT_CRITICAL - Price at zero gamma level = breakout imminent
- CAPITULATION_CASCADE - Broken support + volume surge = danger zone

Notification Delivery:
- Server-Sent Events (SSE) for real-time browser notifications
- WebSocket fallback for older browsers
- Email alerts (optional, future enhancement)
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict
from database_adapter import get_connection


class NotificationManager:
    """Manages push notifications for psychology trap detection"""

    def __init__(self):
        self.subscribers: Set[asyncio.Queue] = set()
        self.notification_history: List[Dict] = []
        self.last_check_time: Optional[datetime] = None

        # Critical patterns that trigger immediate notifications
        self.critical_patterns = {
            'GAMMA_SQUEEZE_CASCADE',
            'FLIP_POINT_CRITICAL',
            'CAPITULATION_CASCADE'
        }

        # High-priority patterns (notifications with lower urgency)
        self.high_priority_patterns = {
            'LIBERATION_TRADE',
            'FALSE_FLOOR',
            'EXPLOSIVE_CONTINUATION',
            'POST_OPEX_REGIME_FLIP'
        }

    async def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to notification stream

        Returns:
            asyncio.Queue for receiving notifications
        """
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """
        Unsubscribe from notification stream

        Args:
            queue: The queue to remove
        """
        self.subscribers.discard(queue)

    async def broadcast(self, notification: Dict):
        """
        Broadcast notification to all subscribers

        Args:
            notification: Notification data to send
        """
        # Add to history
        self.notification_history.append({
            **notification,
            'broadcast_time': datetime.now().isoformat()
        })

        # Keep only last 100 notifications
        if len(self.notification_history) > 100:
            self.notification_history = self.notification_history[-100:]

        # Send to all subscribers
        dead_queues = set()
        for queue in self.subscribers:
            try:
                await queue.put(notification)
            except Exception:
                dead_queues.add(queue)

        # Clean up dead subscribers
        self.subscribers -= dead_queues

    def check_for_new_signals(self) -> List[Dict]:
        """
        Check database for new critical signals since last check

        Returns:
            List of new critical signals that should trigger notifications
        """
        conn = get_connection()
        c = conn.cursor()

        # Get new signals since last check
        if self.last_check_time:
            c.execute('''
                SELECT
                    id, timestamp, spy_price, primary_regime_type,
                    confidence_score, trade_direction, risk_level,
                    description, psychology_trap,
                    vix_current, vix_spike_detected,
                    volatility_regime, at_flip_point
                FROM regime_signals
                WHERE timestamp > ?
                AND primary_regime_type IN (?, ?, ?, ?, ?, ?, ?)
                ORDER BY timestamp DESC
            ''', (
                self.last_check_time.isoformat(),
                'GAMMA_SQUEEZE_CASCADE',
                'FLIP_POINT_CRITICAL',
                'CAPITULATION_CASCADE',
                'LIBERATION_TRADE',
                'FALSE_FLOOR',
                'EXPLOSIVE_CONTINUATION',
                'POST_OPEX_REGIME_FLIP'
            ))
        else:
            # First check - only get signals from last hour
            one_hour_ago = (datetime.now().replace(microsecond=0) -
                           timedelta(hours=1)).isoformat()
            c.execute('''
                SELECT
                    id, timestamp, spy_price, primary_regime_type,
                    confidence_score, trade_direction, risk_level,
                    description, psychology_trap,
                    vix_current, vix_spike_detected,
                    volatility_regime, at_flip_point
                FROM regime_signals
                WHERE timestamp > ?
                AND primary_regime_type IN (?, ?, ?, ?, ?, ?, ?)
                ORDER BY timestamp DESC
            ''', (
                one_hour_ago,
                'GAMMA_SQUEEZE_CASCADE',
                'FLIP_POINT_CRITICAL',
                'CAPITULATION_CASCADE',
                'LIBERATION_TRADE',
                'FALSE_FLOOR',
                'EXPLOSIVE_CONTINUATION',
                'POST_OPEX_REGIME_FLIP'
            ))

        # Fetch rows and convert to dict (database-agnostic)
        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        signals = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            signals.append({
                'id': row_dict['id'],
                'timestamp': row_dict['timestamp'],
                'price': row_dict['spy_price'],
                'pattern': row_dict['primary_regime_type'],
                'confidence': row_dict['confidence_score'],
                'direction': row_dict['trade_direction'],
                'risk_level': row_dict['risk_level'],
                'description': row_dict['description'],
                'psychology_trap': row_dict['psychology_trap'],
                'vix': row_dict['vix_current'],
                'vix_spike': bool(row_dict['vix_spike_detected']) if row_dict['vix_spike_detected'] is not None else False,
                'volatility_regime': row_dict['volatility_regime'],
                'at_flip_point': bool(row_dict['at_flip_point']) if row_dict['at_flip_point'] is not None else False
            })

        conn.close()
        self.last_check_time = datetime.now()

        return signals

    def create_notification(self, signal: Dict) -> Dict:
        """
        Create notification object from signal data

        Args:
            signal: Signal data from database

        Returns:
            Formatted notification ready for broadcast
        """
        pattern = signal['pattern']
        is_critical = pattern in self.critical_patterns

        # Determine urgency level
        if is_critical:
            urgency = 'critical'
        elif pattern in self.high_priority_patterns:
            urgency = 'high'
        else:
            urgency = 'medium'

        # Create notification title
        if pattern == 'GAMMA_SQUEEZE_CASCADE':
            title = '⚡ GAMMA SQUEEZE CASCADE DETECTED'
            action = f"VIX spike + short gamma = explosive {signal['direction']} move incoming!"
        elif pattern == 'FLIP_POINT_CRITICAL':
            title = '🎯 FLIP POINT CRITICAL - EXPLOSIVE BREAKOUT'
            action = 'Price at zero gamma level - explosive move imminent!'
        elif pattern == 'CAPITULATION_CASCADE':
            title = '⚠️ CAPITULATION CASCADE - DANGER ZONE'
            action = 'Support broken + volume surge - further downside likely!'
        elif pattern == 'LIBERATION_TRADE':
            title = '🚀 LIBERATION TRADE SETUP'
            action = f"Resistance expires soon - {signal['direction']} breakout likely!"
        elif pattern == 'FALSE_FLOOR':
            title = '⚠️ FALSE FLOOR DETECTED'
            action = 'Support is temporary - breakdown risk when gamma expires!'
        elif pattern == 'EXPLOSIVE_CONTINUATION':
            title = '💥 EXPLOSIVE CONTINUATION'
            action = f"Wall broken with volume - {signal['direction']} momentum confirmed!"
        elif pattern == 'POST_OPEX_REGIME_FLIP':
            title = '🔄 POST-OPEX REGIME FLIP'
            action = 'Gamma structure changing - regime shift incoming!'
        else:
            title = f'📊 {pattern.replace("_", " ").title()}'
            action = signal['description']

        return {
            'id': signal['id'],
            'timestamp': signal['timestamp'],
            'urgency': urgency,
            'title': title,
            'action': action,
            'pattern': pattern,
            'price': signal['price'],
            'confidence': signal['confidence'],
            'direction': signal['direction'],
            'risk_level': signal['risk_level'],
            'description': signal['description'],
            'psychology_trap': signal['psychology_trap'],
            'vix': signal.get('vix'),
            'vix_spike': signal.get('vix_spike', False),
            'at_flip_point': signal.get('at_flip_point', False),
            'volatility_regime': signal.get('volatility_regime')
        }

    async def monitor_and_notify(self, interval_seconds: int = 60):
        """
        Continuously monitor for new signals and send notifications

        Args:
            interval_seconds: How often to check for new signals (default 60s)
        """
        while True:
            try:
                # Check for new signals
                new_signals = self.check_for_new_signals()

                # Create and broadcast notifications
                for signal in new_signals:
                    notification = self.create_notification(signal)
                    await self.broadcast(notification)

                # Wait before next check
                await asyncio.sleep(interval_seconds)

            except Exception as e:
                print(f"Error in notification monitor: {e}")
                await asyncio.sleep(interval_seconds)

    def get_notification_history(self, limit: int = 50) -> List[Dict]:
        """
        Get recent notification history

        Args:
            limit: Maximum number of notifications to return

        Returns:
            List of recent notifications
        """
        return self.notification_history[-limit:]

    def get_notification_stats(self) -> Dict:
        """
        Get statistics about notifications

        Returns:
            Dict with notification stats
        """
        if not self.notification_history:
            return {
                'total_notifications': 0,
                'critical_count': 0,
                'high_priority_count': 0,
                'by_pattern': {},
                'active_subscribers': len(self.subscribers)
            }

        by_pattern = defaultdict(int)
        critical_count = 0
        high_priority_count = 0

        for notif in self.notification_history:
            by_pattern[notif['pattern']] += 1
            if notif['urgency'] == 'critical':
                critical_count += 1
            elif notif['urgency'] == 'high':
                high_priority_count += 1

        return {
            'total_notifications': len(self.notification_history),
            'critical_count': critical_count,
            'high_priority_count': high_priority_count,
            'by_pattern': dict(by_pattern),
            'active_subscribers': len(self.subscribers),
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None
        }


# Singleton instance
notification_manager = NotificationManager()
