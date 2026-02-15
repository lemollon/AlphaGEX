"""
Margin Monitor Service - Background polling, alerts, and storage.

Polls margin status for each active bot, calculates metrics, stores snapshots,
and triggers alerts at configurable thresholds.

Runs as a background service within the trading scheduler.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from trading.margin.margin_config import (
    MarketType,
    BotMarginConfig,
    get_bot_margin_config,
    BOT_INSTRUMENT_MAP,
)
from trading.margin.margin_engine import (
    MarginEngine,
    AccountMarginMetrics,
    PositionMarginMetrics,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class AlertLevel:
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    DANGER = "DANGER"
    CRITICAL = "CRITICAL"


class MarginAlert:
    """A margin-related alert."""

    def __init__(
        self,
        level: str,
        bot_name: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.level = level
        self.bot_name = bot_name
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now(CENTRAL_TZ)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "bot_name": self.bot_name,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_discord_message(self) -> str:
        """Format alert for Discord webhook."""
        emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.DANGER: "🔶",
            AlertLevel.CRITICAL: "🔴",
        }.get(self.level, "❓")

        return (
            f"{emoji} **MARGIN {self.level}** - {self.bot_name}\n"
            f"{self.message}\n"
            f"__{self.timestamp.strftime('%Y-%m-%d %H:%M:%S CT')}__"
        )


class MarginMonitor:
    """Background service that monitors margin health across all bots.

    Features:
    - Polls margin status at configurable intervals
    - Stores snapshots in database for historical analysis
    - Triggers alerts at configurable thresholds
    - Provides pre-trade margin checking
    - Generates daily margin reports

    Usage:
        monitor = MarginMonitor()
        monitor.start()  # Begins background polling

        # Manual check for a specific bot
        metrics = monitor.get_bot_margin_metrics("AGAPE_BTC_PERP")

        # Pre-trade check
        result = monitor.check_margin_for_trade("AGAPE_BTC_PERP", proposed_trade)
    """

    def __init__(
        self,
        poll_interval_seconds: int = 30,
        enabled: bool = True,
    ):
        self.poll_interval = poll_interval_seconds
        self.enabled = enabled
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Cache of latest metrics per bot
        self._latest_metrics: Dict[str, AccountMarginMetrics] = {}
        self._last_poll_time: Dict[str, datetime] = {}

        # Alert history (last 100 alerts)
        self._alert_history: List[MarginAlert] = []
        self._max_alert_history = 100

        # Track time spent in danger zone for auto-risk-reduction
        self._danger_zone_start: Dict[str, Optional[datetime]] = {}

        # Discord webhook URL for alerts
        self._discord_webhook_url = os.getenv("DISCORD_MARGIN_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")

        # Daily report tracking
        self._daily_peak_usage: Dict[str, float] = {}
        self._daily_min_liq_distance: Dict[str, float] = {}
        self._daily_zone_time: Dict[str, Dict[str, float]] = {}  # bot -> {zone: seconds}

    def start(self):
        """Start the background monitoring thread."""
        if self._running:
            logger.warning("MarginMonitor already running")
            return

        if not self.enabled:
            logger.info("MarginMonitor disabled, not starting")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="MarginMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"MarginMonitor started (polling every {self.poll_interval}s)")

    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            logger.info("MarginMonitor stopped")

    def _monitor_loop(self):
        """Main monitoring loop - polls all bots at configured interval."""
        while self._running:
            try:
                self._poll_all_bots()
            except Exception as e:
                logger.exception(f"MarginMonitor poll error: {e}")

            time.sleep(self.poll_interval)

    def _poll_all_bots(self):
        """Poll margin status for all configured bots."""
        for bot_name in BOT_INSTRUMENT_MAP:
            try:
                metrics = self._poll_bot(bot_name)
                if metrics:
                    with self._lock:
                        self._latest_metrics[bot_name] = metrics
                        self._last_poll_time[bot_name] = datetime.now(CENTRAL_TZ)

                    # Check alerts
                    self._check_alerts(metrics)

                    # Check auto-risk-reduction
                    self._check_auto_risk_reduction(metrics)

                    # Store snapshot
                    self._store_snapshot(metrics)

                    # Track daily stats
                    self._track_daily_stats(metrics)

            except Exception as e:
                logger.debug(f"Could not poll margin for {bot_name}: {e}")

    def _poll_bot(self, bot_name: str) -> Optional[AccountMarginMetrics]:
        """Poll margin metrics for a single bot.

        Retrieves account equity and open positions from the database,
        then calculates all margin metrics.
        """
        try:
            config = get_bot_margin_config(bot_name)
            if not config:
                return None

            engine = MarginEngine(config)

            # Get account equity and positions from database
            equity, positions = self._get_bot_state(bot_name, config)
            if equity is None:
                return None

            return engine.calculate_account_metrics(equity, positions)

        except Exception as e:
            logger.debug(f"Error polling {bot_name}: {e}")
            return None

    def _get_bot_state(
        self, bot_name: str, config: BotMarginConfig
    ) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        """Get account equity and open positions for a bot from the database.

        This connects to the actual database to get real position data.
        Returns (equity, positions) or (None, []) if unavailable.
        """
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()
        except Exception as e:
            logger.debug(f"Database not available for margin check: {e}")
            return None, []

        try:
            equity = None
            positions = []
            market_type = config.market_config.market_type

            if market_type == MarketType.CRYPTO_PERPETUAL:
                equity, positions = self._get_perp_state(cursor, bot_name, config)
            elif market_type == MarketType.CRYPTO_FUTURES:
                equity, positions = self._get_crypto_futures_state(cursor, bot_name, config)
            elif market_type == MarketType.STOCK_FUTURES:
                equity, positions = self._get_stock_futures_state(cursor, bot_name, config)
            elif market_type == MarketType.OPTIONS:
                equity, positions = self._get_options_state(cursor, bot_name, config)
            elif market_type == MarketType.CRYPTO_SPOT:
                equity, positions = self._get_spot_state(cursor, bot_name, config)

            cursor.close()
            conn.close()
            return equity, positions

        except Exception as e:
            logger.debug(f"Error getting bot state for {bot_name}: {e}")
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
            return None, []

    def _get_perp_state(
        self, cursor, bot_name: str, config: BotMarginConfig
    ) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        """Get state for crypto perpetual bots (AGAPE_*_PERP)."""
        table_prefix = bot_name.lower()  # e.g., agape_btc_perp

        # Get starting capital from config
        cursor.execute("""
            SELECT value FROM autonomous_config
            WHERE key = %s
        """, (f"{table_prefix}_starting_capital",))
        row = cursor.fetchone()
        starting_capital = float(row[0]) if row else 25000.0

        # Get total realized P&L
        positions_table = f"{table_prefix}_positions"
        try:
            cursor.execute(f"""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM {positions_table}
                WHERE status = 'closed' AND realized_pnl IS NOT NULL
            """)
            total_pnl = float(cursor.fetchone()[0])
        except Exception:
            total_pnl = 0.0

        equity = starting_capital + total_pnl

        # Get open positions
        positions = []
        try:
            cursor.execute(f"""
                SELECT position_id, side, quantity, entry_price, unrealized_pnl
                FROM {positions_table}
                WHERE status = 'open'
            """)
            for row in cursor.fetchall():
                positions.append({
                    "position_id": row[0],
                    "symbol": config.market_config.market_type.value,
                    "side": row[1] if isinstance(row[1], str) else row[1].value if hasattr(row[1], 'value') else str(row[1]),
                    "quantity": float(row[2]),
                    "entry_price": float(row[3]),
                    "current_price": float(row[3]),  # Updated below with real price
                    "unrealized_pnl": float(row[4]) if row[4] else 0.0,
                })
        except Exception as e:
            logger.debug(f"Could not query {positions_table}: {e}")

        # Add unrealized P&L to equity
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        equity += total_unrealized

        return equity, positions

    def _get_crypto_futures_state(
        self, cursor, bot_name: str, config: BotMarginConfig
    ) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        """Get state for CME crypto futures bots (AGAPE_BTC)."""
        table_prefix = bot_name.lower()

        cursor.execute("""
            SELECT value FROM autonomous_config
            WHERE key = %s
        """, (f"{table_prefix}_starting_capital",))
        row = cursor.fetchone()
        starting_capital = float(row[0]) if row else 5000.0

        positions_table = f"{table_prefix}_positions"
        try:
            cursor.execute(f"""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM {positions_table}
                WHERE status = 'closed' AND realized_pnl IS NOT NULL
            """)
            total_pnl = float(cursor.fetchone()[0])
        except Exception:
            total_pnl = 0.0

        equity = starting_capital + total_pnl

        positions = []
        try:
            cursor.execute(f"""
                SELECT position_id, side, quantity, entry_price, unrealized_pnl
                FROM {positions_table}
                WHERE status = 'open'
            """)
            for row in cursor.fetchall():
                side_val = row[1]
                if hasattr(side_val, 'value'):
                    side_val = side_val.value
                positions.append({
                    "position_id": row[0],
                    "symbol": BOT_INSTRUMENT_MAP.get(bot_name, ""),
                    "side": str(side_val),
                    "quantity": float(row[2]),
                    "entry_price": float(row[3]),
                    "current_price": float(row[3]),
                    "unrealized_pnl": float(row[4]) if row[4] else 0.0,
                })
        except Exception as e:
            logger.debug(f"Could not query {positions_table}: {e}")

        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        equity += total_unrealized

        return equity, positions

    def _get_stock_futures_state(
        self, cursor, bot_name: str, config: BotMarginConfig
    ) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        """Get state for stock index futures bots.

        These bots may not have dedicated tables yet (PHOENIX, HERMES).
        Falls back to autonomous_open_positions for legacy bots.
        """
        table_prefix = bot_name.lower()

        cursor.execute("""
            SELECT value FROM autonomous_config
            WHERE key = %s
        """, (f"{table_prefix}_starting_capital",))
        row = cursor.fetchone()
        starting_capital = float(row[0]) if row else 50000.0

        # Try bot-specific table first, fall back to autonomous
        positions = []
        total_pnl = 0.0

        for table in [f"{table_prefix}_positions", "autonomous_open_positions"]:
            try:
                cursor.execute(f"""
                    SELECT position_id, side, quantity, entry_price
                    FROM {table}
                    WHERE status = 'open'
                    LIMIT 100
                """)
                for row in cursor.fetchall():
                    side_val = row[1]
                    if hasattr(side_val, 'value'):
                        side_val = side_val.value
                    positions.append({
                        "position_id": row[0],
                        "symbol": BOT_INSTRUMENT_MAP.get(bot_name, ""),
                        "side": str(side_val) if side_val else "long",
                        "quantity": float(row[2]) if row[2] else 1,
                        "entry_price": float(row[3]) if row[3] else 0,
                        "current_price": float(row[3]) if row[3] else 0,
                    })
                break  # Found the table
            except Exception:
                continue

        equity = starting_capital + total_pnl
        return equity, positions

    def _get_options_state(
        self, cursor, bot_name: str, config: BotMarginConfig
    ) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        """Get state for options bots (ANCHOR, FORTRESS, etc.).

        Options positions use max_loss as margin requirement (defined risk).
        """
        table_prefix = bot_name.lower()

        cursor.execute("""
            SELECT value FROM autonomous_config
            WHERE key = %s
        """, (f"{table_prefix}_starting_capital",))
        row = cursor.fetchone()
        starting_capital = float(row[0]) if row else 200000.0

        positions_table = f"{table_prefix}_positions"
        try:
            cursor.execute(f"""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM {positions_table}
                WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
            """)
            total_pnl = float(cursor.fetchone()[0])
        except Exception:
            total_pnl = 0.0

        equity = starting_capital + total_pnl

        positions = []
        try:
            cursor.execute(f"""
                SELECT position_id, contracts, total_credit, max_loss,
                       underlying_at_entry, spread_width
                FROM {positions_table}
                WHERE status = 'open'
            """)
            for row in cursor.fetchall():
                # For options, "margin" = max_loss of the spread
                contracts = int(row[1]) if row[1] else 1
                total_credit = float(row[2]) if row[2] else 0
                max_loss = float(row[3]) if row[3] else 0
                underlying = float(row[4]) if row[4] else 0
                spread_width = float(row[5]) if row[5] else 10.0

                positions.append({
                    "position_id": row[0],
                    "symbol": BOT_INSTRUMENT_MAP.get(bot_name, "SPX"),
                    "side": "long",  # IC = neutral
                    "quantity": contracts,
                    "entry_price": underlying,
                    "current_price": underlying,
                    "max_loss": max_loss,
                    "total_credit": total_credit,
                    "spread_width": spread_width,
                })
        except Exception as e:
            logger.debug(f"Could not query {positions_table}: {e}")

        return equity, positions

    def _get_spot_state(
        self, cursor, bot_name: str, config: BotMarginConfig
    ) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        """Get state for crypto spot bots (AGAPE_SPOT).

        Spot trading has no margin/leverage - included for completeness.
        """
        try:
            cursor.execute("""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM agape_spot_positions
                WHERE status = 'closed' AND realized_pnl IS NOT NULL
            """)
            total_pnl = float(cursor.fetchone()[0])
        except Exception:
            total_pnl = 0.0

        equity = 5000.0 + total_pnl  # Default starting capital

        positions = []
        try:
            cursor.execute("""
                SELECT position_id, ticker, quantity, entry_price, unrealized_pnl
                FROM agape_spot_positions
                WHERE status = 'open'
            """)
            for row in cursor.fetchall():
                positions.append({
                    "position_id": row[0],
                    "symbol": row[1],
                    "side": "long",
                    "quantity": float(row[2]),
                    "entry_price": float(row[3]),
                    "current_price": float(row[3]),
                    "unrealized_pnl": float(row[4]) if row[4] else 0.0,
                })
        except Exception as e:
            logger.debug(f"Could not query agape_spot_positions: {e}")

        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        equity += total_unrealized

        return equity, positions

    # =========================================================================
    # ALERT SYSTEM
    # =========================================================================

    def _check_alerts(self, metrics: AccountMarginMetrics):
        """Check margin metrics against thresholds and generate alerts."""
        bot = metrics.bot_name
        usage = metrics.margin_usage_pct

        # Margin usage alerts
        if usage >= metrics.critical_threshold:
            self._fire_alert(AlertLevel.CRITICAL, bot,
                f"Margin usage at {usage:.1f}% (critical threshold: {metrics.critical_threshold}%)",
                {"margin_usage_pct": usage, "equity": metrics.account_equity}
            )
        elif usage >= metrics.danger_threshold:
            self._fire_alert(AlertLevel.DANGER, bot,
                f"Margin usage at {usage:.1f}% (danger threshold: {metrics.danger_threshold}%)",
                {"margin_usage_pct": usage, "equity": metrics.account_equity}
            )
        elif usage >= metrics.warning_threshold:
            self._fire_alert(AlertLevel.WARNING, bot,
                f"Margin usage at {usage:.1f}% (warning threshold: {metrics.warning_threshold}%)",
                {"margin_usage_pct": usage, "equity": metrics.account_equity}
            )

        # Liquidation proximity alerts
        for pos in metrics.positions:
            if pos.distance_to_liq_pct is not None:
                if pos.distance_to_liq_pct < 3.0:
                    self._fire_alert(AlertLevel.CRITICAL, bot,
                        f"Position {pos.position_id} ({pos.symbol}) "
                        f"only {pos.distance_to_liq_pct:.2f}% from liquidation!",
                        {
                            "position_id": pos.position_id,
                            "symbol": pos.symbol,
                            "distance_to_liq_pct": pos.distance_to_liq_pct,
                            "liquidation_price": pos.liquidation_price,
                            "current_price": pos.current_price,
                        }
                    )
                elif pos.distance_to_liq_pct < 5.0:
                    self._fire_alert(AlertLevel.DANGER, bot,
                        f"Position {pos.position_id} ({pos.symbol}) "
                        f"{pos.distance_to_liq_pct:.2f}% from liquidation",
                        {
                            "position_id": pos.position_id,
                            "distance_to_liq_pct": pos.distance_to_liq_pct,
                        }
                    )

        # Track danger zone time for auto-risk-reduction
        if usage >= 85.0:
            if bot not in self._danger_zone_start or self._danger_zone_start[bot] is None:
                self._danger_zone_start[bot] = datetime.now(CENTRAL_TZ)
        else:
            self._danger_zone_start[bot] = None

    def _check_auto_risk_reduction(self, metrics: AccountMarginMetrics):
        """Check if auto-risk-reduction should be triggered.

        Auto-risk-reduction is OFF by default and must be explicitly enabled
        per-bot via the margin_bot_config table.

        Rules:
        1. If margin_usage > auto_reduce_margin_pct for > auto_reduce_duration_seconds,
           reduce the largest position by auto_reduce_position_pct (default 25%)
        2. If any position's distance_to_liquidation < auto_close_liq_distance_pct,
           close 50% of that position immediately.

        All auto-actions are logged and sent to Discord.
        """
        bot = metrics.bot_name
        config = get_bot_margin_config(bot)
        if not config or not config.auto_reduce_enabled:
            return

        now = datetime.now(CENTRAL_TZ)

        # Rule 1: Sustained high margin usage -> reduce largest position
        if metrics.margin_usage_pct >= config.auto_reduce_margin_pct:
            danger_start = self._danger_zone_start.get(bot)
            if danger_start:
                duration = (now - danger_start).total_seconds()
                if duration >= config.auto_reduce_duration_seconds:
                    # Find the largest position by margin required
                    if metrics.positions:
                        largest = max(metrics.positions, key=lambda p: p.initial_margin_required)
                        reduce_pct = config.auto_reduce_position_pct
                        self._fire_alert(AlertLevel.CRITICAL, bot,
                            f"AUTO-RISK-REDUCTION: Reducing {largest.position_id} by {reduce_pct}% "
                            f"(margin at {metrics.margin_usage_pct:.1f}% for {duration:.0f}s)",
                            {
                                "action": "auto_reduce",
                                "position_id": largest.position_id,
                                "reduce_pct": reduce_pct,
                                "duration_seconds": duration,
                            }
                        )
                        # Log the action (actual execution is delegated to the bot)
                        self._store_auto_action(bot, "REDUCE_POSITION", {
                            "position_id": largest.position_id,
                            "reduce_pct": reduce_pct,
                            "margin_usage_pct": metrics.margin_usage_pct,
                        })
                        # Reset the timer
                        self._danger_zone_start[bot] = now

        # Rule 2: Position too close to liquidation -> emergency close
        for pos in metrics.positions:
            if pos.distance_to_liq_pct is not None and pos.distance_to_liq_pct < config.auto_close_liq_distance_pct:
                self._fire_alert(AlertLevel.CRITICAL, bot,
                    f"AUTO-CLOSE TRIGGERED: {pos.position_id} is {pos.distance_to_liq_pct:.2f}% "
                    f"from liquidation (threshold: {config.auto_close_liq_distance_pct}%)",
                    {
                        "action": "auto_close",
                        "position_id": pos.position_id,
                        "distance_to_liq_pct": pos.distance_to_liq_pct,
                        "liquidation_price": pos.liquidation_price,
                    }
                )
                self._store_auto_action(bot, "EMERGENCY_CLOSE", {
                    "position_id": pos.position_id,
                    "close_pct": 50,
                    "distance_to_liq_pct": pos.distance_to_liq_pct,
                })

    def _store_auto_action(self, bot_name: str, action: str, details: Dict[str, Any]):
        """Store auto-risk-reduction action in the database for audit trail."""
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO margin_alerts (
                    bot_name, alert_level, message, details, created_at
                ) VALUES (%s, %s, %s, %s, %s)
            """, (
                bot_name,
                "AUTO_ACTION",
                f"Auto-risk-reduction: {action}",
                json.dumps(details),
                datetime.now(CENTRAL_TZ),
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.warning(f"Could not store auto-action: {e}")

    def generate_daily_report_discord(self) -> Optional[str]:
        """Generate formatted daily margin report for Discord.

        Call at market close to send a summary of the day's margin usage.

        Returns:
            Formatted Discord message or None
        """
        report = self.get_daily_report()
        if not report or not report.get("bots"):
            return None

        lines = [
            "**DAILY MARGIN REPORT**",
            f"Date: {report['date']}",
            "```",
            f"{'Bot':<18} {'Peak%':>6} {'MinLiq%':>8} {'Green':>6} {'Red':>6}",
            "-" * 50,
        ]

        for bot_name, data in report["bots"].items():
            peak = data.get("peak_margin_usage_pct", 0)
            min_liq = data.get("min_liquidation_distance_pct")
            green_s = data.get("time_in_green_seconds", 0)
            red_s = data.get("time_in_red_seconds", 0)

            if peak == 0 and green_s == 0:
                continue  # Skip inactive bots

            green_min = green_s / 60
            red_min = red_s / 60
            min_liq_str = f"{min_liq:.1f}%" if min_liq else "N/A"

            lines.append(
                f"{bot_name:<18} {peak:>5.1f}% {min_liq_str:>8} {green_min:>5.0f}m {red_min:>5.0f}m"
            )

        lines.append("```")

        message = "\n".join(lines)

        # Send to Discord if webhook configured
        if self._discord_webhook_url:
            try:
                import requests
                requests.post(
                    self._discord_webhook_url,
                    json={"content": message},
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"Failed to send daily report to Discord: {e}")

        return message

    def _fire_alert(
        self,
        level: str,
        bot_name: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Create and dispatch a margin alert."""
        alert = MarginAlert(level, bot_name, message, details)

        with self._lock:
            self._alert_history.append(alert)
            if len(self._alert_history) > self._max_alert_history:
                self._alert_history = self._alert_history[-self._max_alert_history:]

        logger.warning(f"MARGIN {level} [{bot_name}]: {message}")

        # Send to Discord (non-blocking)
        if self._discord_webhook_url and level in (AlertLevel.DANGER, AlertLevel.CRITICAL):
            self._send_discord_alert(alert)

        # Store in database
        self._store_alert(alert)

    def _send_discord_alert(self, alert: MarginAlert):
        """Send alert to Discord webhook (non-blocking)."""
        try:
            import requests
            threading.Thread(
                target=self._do_discord_send,
                args=(alert,),
                daemon=True,
            ).start()
        except ImportError:
            logger.debug("requests library not available for Discord alerts")

    def _do_discord_send(self, alert: MarginAlert):
        """Actually send the Discord webhook (runs in separate thread)."""
        try:
            import requests
            payload = {
                "content": alert.to_discord_message(),
            }
            requests.post(self._discord_webhook_url, json=payload, timeout=10)
        except Exception as e:
            logger.debug(f"Failed to send Discord alert: {e}")

    def _store_alert(self, alert: MarginAlert):
        """Store alert in the database."""
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO margin_alerts (
                    bot_name, alert_level, message, details, created_at
                ) VALUES (%s, %s, %s, %s, %s)
            """, (
                alert.bot_name,
                alert.level,
                alert.message,
                json.dumps(alert.details),
                alert.timestamp,
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not store margin alert: {e}")

    # =========================================================================
    # SNAPSHOT STORAGE
    # =========================================================================

    def _store_snapshot(self, metrics: AccountMarginMetrics):
        """Store margin snapshot in database for historical analysis."""
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Store account-level snapshot
            cursor.execute("""
                INSERT INTO margin_snapshots (
                    bot_name, timestamp, account_equity, margin_used,
                    margin_available, margin_usage_pct, margin_ratio,
                    effective_leverage, total_notional, total_unrealized_pnl,
                    position_count, health_status, market_type,
                    total_funding_cost_daily
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                metrics.bot_name,
                metrics.timestamp,
                metrics.account_equity,
                metrics.total_margin_used,
                metrics.available_margin,
                metrics.margin_usage_pct,
                metrics.margin_ratio,
                metrics.effective_leverage,
                metrics.total_notional_value,
                metrics.total_unrealized_pnl,
                metrics.position_count,
                metrics.health_status,
                metrics.market_type,
                metrics.total_funding_cost_daily,
            ))

            # Store per-position details
            for pos in metrics.positions:
                cursor.execute("""
                    INSERT INTO margin_position_details (
                        bot_name, position_id, symbol, side,
                        entry_price, current_price, quantity,
                        notional_value, margin_required,
                        liquidation_price, distance_to_liq_pct,
                        unrealized_pnl, funding_rate,
                        funding_cost_daily, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    pos.bot_name,
                    pos.position_id,
                    pos.symbol,
                    pos.side,
                    pos.entry_price,
                    pos.current_price,
                    pos.quantity,
                    pos.notional_value,
                    pos.initial_margin_required,
                    pos.liquidation_price,
                    pos.distance_to_liq_pct,
                    pos.unrealized_pnl,
                    pos.funding_rate,
                    pos.funding_cost_projection_daily,
                    pos.timestamp,
                ))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            logger.debug(f"Could not store margin snapshot: {e}")

    # =========================================================================
    # DAILY STATS TRACKING
    # =========================================================================

    def _track_daily_stats(self, metrics: AccountMarginMetrics):
        """Track daily peak usage and min liquidation distance."""
        bot = metrics.bot_name
        usage = metrics.margin_usage_pct

        # Peak usage
        current_peak = self._daily_peak_usage.get(bot, 0.0)
        if usage > current_peak:
            self._daily_peak_usage[bot] = usage

        # Min liquidation distance
        for pos in metrics.positions:
            if pos.distance_to_liq_pct is not None:
                current_min = self._daily_min_liq_distance.get(bot, float('inf'))
                if pos.distance_to_liq_pct < current_min:
                    self._daily_min_liq_distance[bot] = pos.distance_to_liq_pct

        # Zone time tracking
        if bot not in self._daily_zone_time:
            self._daily_zone_time[bot] = {
                "green": 0, "yellow": 0, "orange": 0, "red": 0
            }
        zone = metrics.health_status.lower()
        zone_map = {"healthy": "green", "warning": "yellow", "danger": "orange", "critical": "red"}
        zone_key = zone_map.get(zone, "green")
        self._daily_zone_time[bot][zone_key] += self.poll_interval

    def reset_daily_stats(self):
        """Reset daily tracking. Call at end of trading day."""
        self._daily_peak_usage.clear()
        self._daily_min_liq_distance.clear()
        self._daily_zone_time.clear()

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def get_bot_margin_metrics(self, bot_name: str) -> Optional[AccountMarginMetrics]:
        """Get the latest cached margin metrics for a bot."""
        with self._lock:
            return self._latest_metrics.get(bot_name)

    def get_all_bot_metrics(self) -> Dict[str, AccountMarginMetrics]:
        """Get latest metrics for all monitored bots."""
        with self._lock:
            return dict(self._latest_metrics)

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get aggregate portfolio margin overview across all bots."""
        with self._lock:
            metrics_list = list(self._latest_metrics.values())

        if not metrics_list:
            return {
                "total_equity": 0,
                "total_margin_used": 0,
                "total_available": 0,
                "total_notional": 0,
                "total_unrealized_pnl": 0,
                "bot_count": 0,
                "worst_health": "HEALTHY",
                "bots": [],
            }

        total_equity = sum(m.account_equity for m in metrics_list)
        total_margin = sum(m.total_margin_used for m in metrics_list)
        total_available = sum(m.available_margin for m in metrics_list)
        total_notional = sum(m.total_notional_value for m in metrics_list)
        total_unrealized = sum(m.total_unrealized_pnl for m in metrics_list)

        # Worst health status
        health_order = {"HEALTHY": 0, "WARNING": 1, "DANGER": 2, "CRITICAL": 3}
        worst = max(metrics_list, key=lambda m: health_order.get(m.health_status, 0))

        bots = []
        for m in metrics_list:
            bots.append({
                "bot_name": m.bot_name,
                "market_type": m.market_type,
                "equity": round(m.account_equity, 2),
                "margin_used_pct": round(m.margin_usage_pct, 1),
                "health_status": m.health_status,
                "position_count": m.position_count,
                "unrealized_pnl": round(m.total_unrealized_pnl, 2),
            })

        return {
            "total_equity": round(total_equity, 2),
            "total_margin_used": round(total_margin, 2),
            "total_available": round(total_available, 2),
            "total_notional": round(total_notional, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "overall_margin_usage_pct": round(
                (total_margin / total_equity * 100) if total_equity > 0 else 0, 1
            ),
            "bot_count": len(metrics_list),
            "worst_health": worst.health_status,
            "bots": bots,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
        }

    def get_alert_history(
        self, bot_name: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent margin alerts."""
        with self._lock:
            alerts = self._alert_history.copy()

        if bot_name:
            alerts = [a for a in alerts if a.bot_name == bot_name]

        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        return [a.to_dict() for a in alerts[:limit]]

    def get_daily_report(self) -> Dict[str, Any]:
        """Generate daily margin report data."""
        report = {
            "date": datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d"),
            "bots": {},
        }

        for bot_name in BOT_INSTRUMENT_MAP:
            peak = self._daily_peak_usage.get(bot_name, 0.0)
            min_liq = self._daily_min_liq_distance.get(bot_name, None)
            zones = self._daily_zone_time.get(bot_name, {})
            latest = self._latest_metrics.get(bot_name)

            report["bots"][bot_name] = {
                "peak_margin_usage_pct": round(peak, 1),
                "min_liquidation_distance_pct": round(min_liq, 2) if min_liq and min_liq != float('inf') else None,
                "time_in_green_seconds": zones.get("green", 0),
                "time_in_yellow_seconds": zones.get("yellow", 0),
                "time_in_orange_seconds": zones.get("orange", 0),
                "time_in_red_seconds": zones.get("red", 0),
                "current_equity": round(latest.account_equity, 2) if latest else None,
                "current_usage_pct": round(latest.margin_usage_pct, 1) if latest else None,
                "total_funding_cost_daily": (
                    round(latest.total_funding_cost_daily, 4)
                    if latest and latest.total_funding_cost_daily else None
                ),
            }

        return report

    def check_margin_for_trade(
        self,
        bot_name: str,
        proposed_trade: Dict[str, Any],
        account_equity: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Public interface for pre-trade margin checks.

        Args:
            bot_name: The bot requesting the trade
            proposed_trade: Dict with symbol, side, quantity, entry_price
            account_equity: Override equity (if None, uses latest cached)

        Returns:
            PreTradeCheckResult as dict, or None if margin data unavailable
        """
        config = get_bot_margin_config(bot_name)
        if not config:
            logger.warning(f"No margin config for bot: {bot_name}")
            return None

        engine = MarginEngine(config)

        # Get equity and positions
        if account_equity is None:
            cached = self.get_bot_margin_metrics(bot_name)
            if cached:
                account_equity = cached.account_equity
            else:
                # Try to fetch from database
                equity, _ = self._get_bot_state(bot_name, config)
                if equity is None:
                    logger.warning(f"Cannot determine equity for {bot_name}")
                    return None
                account_equity = equity

        # Get current positions
        _, positions = self._get_bot_state(bot_name, config)

        result = engine.check_pre_trade(account_equity, positions, proposed_trade)
        return result.to_dict()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_monitor_instance: Optional[MarginMonitor] = None
_monitor_lock = threading.Lock()


def get_margin_monitor(
    poll_interval: int = 30,
    enabled: bool = True,
) -> MarginMonitor:
    """Get or create the singleton MarginMonitor instance."""
    global _monitor_instance
    with _monitor_lock:
        if _monitor_instance is None:
            _monitor_instance = MarginMonitor(
                poll_interval_seconds=poll_interval,
                enabled=enabled,
            )
        return _monitor_instance
