"""
HERACLES - Main Trader
======================

MES Futures Scalping Bot using GEX signals.
Named after the legendary Greek hero known for strength and perseverance.

Orchestrates:
- Signal generation from GEX data
- Position management with trailing stops
- Tastytrade order execution
- Win probability tracking (Bayesian → ML)
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

from .models import (
    FuturesPosition, FuturesSignal, TradeDirection, GammaRegime,
    PositionStatus, SignalSource, HERACLESConfig, TradingMode,
    BayesianWinTracker, MES_POINT_VALUE, CENTRAL_TZ
)
from .db import HERACLESDatabase
from .signals import HERACLESSignalGenerator, get_gex_data_for_heracles
from .executor import TastytradeExecutor

logger = logging.getLogger(__name__)


class HERACLESTrader:
    """
    HERACLES - MES Futures Scalping Bot

    Strategy:
    - POSITIVE GAMMA: Mean reversion - fade moves toward flip point
    - NEGATIVE GAMMA: Momentum - trade breakouts away from flip point

    Risk Management:
    - Initial stop: 3 points ($15 per contract)
    - Breakeven activation: +2 points ($10 profit)
    - Trailing stop: 1 point ($5 trail distance)

    Position Sizing:
    - Fixed Fractional with ATR Adjustment
    - Risk 1% per trade by default
    """

    def __init__(self, config: Optional[HERACLESConfig] = None):
        """Initialize HERACLES trader"""
        self.db = HERACLESDatabase()

        # Load config from DB or use provided/defaults
        self.config = config or self.db.get_config()

        # Initialize components
        self.win_tracker = self.db.get_win_tracker()
        self.signal_generator = HERACLESSignalGenerator(self.config, self.win_tracker)
        self.executor = TastytradeExecutor(self.config)

        # State
        self.last_scan_time: Optional[datetime] = None
        self.daily_trades: int = 0
        self.daily_pnl: float = 0.0

        logger.info(
            f"HERACLES initialized: mode={self.config.mode.value}, "
            f"symbol={self.config.symbol}, capital=${self.config.capital:,.2f}"
        )

    # ========================================================================
    # Main Trading Loop
    # ========================================================================

    def run_scan(self) -> Dict[str, Any]:
        """
        Run a single trading scan.

        This is called periodically (every minute) by the scheduler.
        """
        scan_result = {
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "status": "completed",
            "positions_checked": 0,
            "signals_generated": 0,
            "trades_executed": 0,
            "positions_closed": 0,
            "errors": []
        }

        try:
            # Check market hours
            if not self.executor.is_market_open():
                scan_result["status"] = "market_closed"
                return scan_result

            # Get current market data
            quote = self.executor.get_mes_quote()
            if not quote:
                scan_result["status"] = "no_quote"
                scan_result["errors"].append("Could not get MES quote")
                return scan_result

            current_price = quote.get("last", 0)
            if current_price <= 0:
                scan_result["status"] = "invalid_price"
                return scan_result

            # Get GEX data
            gex_data = get_gex_data_for_heracles("SPY")

            # Get account balance
            balance = self.executor.get_account_balance()
            account_balance = balance.get("net_liquidating_value", self.config.capital) if balance else self.config.capital

            # Get VIX (from GEX data or default)
            vix = gex_data.get("vix", 15.0)

            # Calculate ATR (simplified - would use real ATR in production)
            atr = self._estimate_atr(current_price)

            # 1. Manage existing positions (check stops, trailing)
            positions = self.db.get_open_positions()
            scan_result["positions_checked"] = len(positions)

            for position in positions:
                closed = self._manage_position(position, current_price)
                if closed:
                    scan_result["positions_closed"] += 1

            # 2. Check for new signals (if room for more positions)
            open_count = len([p for p in self.db.get_open_positions()])

            if open_count < self.config.max_open_positions:
                # Determine if overnight session
                is_overnight = self._is_overnight_session()

                # Generate signal
                signal = self.signal_generator.generate_signal(
                    current_price=current_price,
                    gex_data=gex_data,
                    vix=vix,
                    atr=atr,
                    account_balance=account_balance,
                    is_overnight=is_overnight
                )

                if signal:
                    scan_result["signals_generated"] += 1

                    if signal.is_valid:
                        # Execute the signal
                        success = self._execute_signal(signal, account_balance)
                        if success:
                            scan_result["trades_executed"] += 1

                            # Log signal
                            self.db.save_signal(signal, was_executed=True)
                        else:
                            self.db.save_signal(signal, was_executed=False, skip_reason="Execution failed")
                    else:
                        self.db.save_signal(signal, was_executed=False, skip_reason="Invalid signal")

            # 3. Save equity snapshot
            self._save_equity_snapshot(account_balance, positions)

            self.last_scan_time = datetime.now(CENTRAL_TZ)

        except Exception as e:
            logger.error(f"Error in HERACLES scan: {e}")
            scan_result["status"] = "error"
            scan_result["errors"].append(str(e))

        return scan_result

    # ========================================================================
    # Position Management
    # ========================================================================

    def _manage_position(self, position: FuturesPosition, current_price: float) -> bool:
        """
        Manage an open position - check stops and trailing.

        Returns True if position was closed.
        """
        try:
            # Check if stopped out
            if self._check_stop_hit(position, current_price):
                return self._close_position(
                    position,
                    current_price,
                    PositionStatus.STOPPED,
                    "Stop loss triggered"
                )

            # Check for breakeven activation
            if not position.trailing_active:
                if position.should_move_to_breakeven(
                    current_price,
                    self.config.breakeven_activation_points
                ):
                    # Move stop to breakeven
                    new_stop = position.entry_price
                    position.current_stop = new_stop
                    position.trailing_active = True
                    self.db.update_stop(position.position_id, new_stop, trailing_active=True)
                    logger.info(f"Position {position.position_id}: Stop moved to breakeven at {new_stop:.2f}")

            # Check for trailing stop update
            if position.trailing_active:
                new_stop = position.should_trail_stop(
                    current_price,
                    self.config.trailing_stop_points
                )
                if new_stop:
                    position.current_stop = new_stop
                    self.db.update_stop(position.position_id, new_stop, trailing_active=True)
                    logger.info(f"Position {position.position_id}: Trailing stop updated to {new_stop:.2f}")

            # Update high water mark and MAE
            pnl = position.calculate_pnl(current_price)
            if pnl > position.high_water_mark:
                position.high_water_mark = pnl
            if pnl < 0 and abs(pnl) > position.max_adverse_excursion:
                position.max_adverse_excursion = abs(pnl)

            return False

        except Exception as e:
            logger.error(f"Error managing position {position.position_id}: {e}")
            return False

    def _check_stop_hit(self, position: FuturesPosition, current_price: float) -> bool:
        """Check if position's stop has been hit"""
        if position.direction == TradeDirection.LONG:
            return current_price <= position.current_stop
        else:
            return current_price >= position.current_stop

    def _close_position(
        self,
        position: FuturesPosition,
        close_price: float,
        status: PositionStatus,
        reason: str
    ) -> bool:
        """Close a position"""
        try:
            # Execute close order
            success, message, fill_price = self.executor.close_position_order(position, reason)

            if success:
                # Use fill price if available, otherwise use provided close_price
                actual_close_price = fill_price if fill_price > 0 else close_price

                # Update database
                closed, realized_pnl = self.db.close_position(
                    position.position_id,
                    actual_close_price,
                    reason,
                    status
                )

                if closed:
                    # Update win tracker
                    won = realized_pnl > 0
                    self.win_tracker.update(won, position.gamma_regime)
                    self.db.save_win_tracker(self.win_tracker)

                    # Update daily stats
                    self.daily_pnl += realized_pnl
                    self.daily_trades += 1

                    # Log
                    self.db.log(
                        level="INFO",
                        action="CLOSE_POSITION",
                        message=f"Closed {position.direction.value} at {actual_close_price:.2f}",
                        details={
                            "position_id": position.position_id,
                            "realized_pnl": realized_pnl,
                            "reason": reason,
                            "status": status.value
                        }
                    )

                    logger.info(
                        f"Position {position.position_id} closed: "
                        f"P&L=${realized_pnl:.2f}, reason={reason}"
                    )
                    return True

            logger.error(f"Failed to close position {position.position_id}: {message}")
            return False

        except Exception as e:
            logger.error(f"Error closing position {position.position_id}: {e}")
            return False

    # ========================================================================
    # Signal Execution
    # ========================================================================

    def _execute_signal(self, signal: FuturesSignal, account_balance: float) -> bool:
        """Execute a trading signal"""
        try:
            # Validate order parameters
            valid, validation_msg = self.executor.validate_order_params(signal, account_balance)
            if not valid:
                logger.warning(f"Order validation failed: {validation_msg}")
                return False

            # Generate position ID
            position_id = f"HERACLES-{uuid.uuid4().hex[:8]}"

            # Execute order
            success, message, order_id = self.executor.execute_signal(signal, position_id)

            if not success:
                logger.error(f"Order execution failed: {message}")
                return False

            # Create position object
            position = FuturesPosition(
                position_id=position_id,
                symbol=self.config.symbol,
                direction=signal.direction,
                contracts=signal.contracts,
                entry_price=signal.entry_price,
                entry_value=signal.entry_price * signal.contracts * MES_POINT_VALUE,
                initial_stop=signal.stop_price,
                current_stop=signal.stop_price,
                breakeven_price=signal.entry_price,
                trailing_active=False,
                gamma_regime=signal.gamma_regime,
                gex_value=signal.gex_value,
                flip_point=signal.flip_point,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                vix_at_entry=signal.vix,
                atr_at_entry=signal.atr,
                signal_source=signal.source,
                signal_confidence=signal.confidence,
                win_probability=signal.win_probability,
                trade_reasoning=signal.reasoning,
                order_id=order_id or "",
                status=PositionStatus.OPEN,
                open_time=datetime.now(CENTRAL_TZ)
            )

            # Save to database
            self.db.save_position(position)

            # Log
            self.db.log(
                level="INFO",
                action="OPEN_POSITION",
                message=f"Opened {signal.direction.value} {signal.contracts} contracts at {signal.entry_price:.2f}",
                details={
                    "position_id": position_id,
                    "signal_source": signal.source.value,
                    "gamma_regime": signal.gamma_regime.value,
                    "win_probability": signal.win_probability,
                    "stop_price": signal.stop_price,
                    "reasoning": signal.reasoning
                }
            )

            logger.info(
                f"Opened position {position_id}: {signal.direction.value} "
                f"{signal.contracts} @ {signal.entry_price:.2f}, "
                f"stop={signal.stop_price:.2f}, win_prob={signal.win_probability:.2%}"
            )

            return True

        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return False

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def _is_overnight_session(self) -> bool:
        """Check if current time is overnight session (5 PM - 8 AM CT)"""
        now = datetime.now(CENTRAL_TZ)
        hour = now.hour

        # Overnight: 5 PM (17:00) to 8 AM (08:00)
        return hour >= 17 or hour < 8

    def _estimate_atr(self, current_price: float, period: int = 14) -> float:
        """
        Estimate ATR for position sizing.

        In production, this would use real historical data.
        For now, estimate based on typical MES volatility.
        """
        # MES typically moves ~0.3-0.5% per day
        # ATR is roughly 15-25 points on average
        # Scale with VIX if available

        # Base ATR estimate (0.3% of price)
        base_atr = current_price * 0.003

        # Typical range for MES
        return max(10.0, min(30.0, base_atr))

    def _save_equity_snapshot(
        self,
        account_balance: float,
        positions: List[FuturesPosition]
    ) -> None:
        """Save equity snapshot for equity curve"""
        try:
            # Get current quote for unrealized P&L
            quote = self.executor.get_mes_quote()
            current_price = quote.get("last", 0) if quote else 0

            unrealized_pnl = 0.0
            for position in positions:
                if position.is_open and current_price > 0:
                    unrealized_pnl += position.calculate_pnl(current_price)

            # Get today's stats
            summary = self.db.get_daily_summary()

            self.db.save_equity_snapshot(
                account_balance=account_balance,
                unrealized_pnl=unrealized_pnl,
                realized_pnl_today=summary.realized_pnl,
                open_positions=len([p for p in positions if p.is_open]),
                trades_today=summary.positions_closed,
                wins_today=0,  # Would track separately
                losses_today=0
            )

        except Exception as e:
            logger.warning(f"Error saving equity snapshot: {e}")

    # ========================================================================
    # Status & Reporting
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        positions = self.db.get_open_positions()
        config = self.config
        stats = self.db.get_performance_stats()
        summary = self.db.get_daily_summary()

        return {
            "bot_name": "HERACLES",
            "status": "active" if self.executor.is_market_open() else "market_closed",
            "mode": config.mode.value,
            "symbol": config.symbol,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "config": {
                "capital": config.capital,
                "risk_per_trade_pct": config.risk_per_trade_pct,
                "max_contracts": config.max_contracts,
                "max_open_positions": config.max_open_positions,
                "initial_stop_points": config.initial_stop_points,
                "breakeven_activation_points": config.breakeven_activation_points,
                "trailing_stop_points": config.trailing_stop_points,
            },
            "positions": {
                "open_count": len(positions),
                "positions": [p.to_dict() for p in positions]
            },
            "performance": stats,
            "today": summary.to_dict(),
            "win_tracker": self.win_tracker.to_dict(),
            "last_scan": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "market_open": self.executor.is_market_open()
        }

    def get_equity_curve(self, days: int = 30) -> List[Dict]:
        """Get equity curve data"""
        return self.db.get_equity_curve(days)

    def get_intraday_equity(self) -> List[Dict]:
        """Get today's equity curve"""
        return self.db.get_intraday_equity()

    def get_closed_trades(self, limit: int = 50) -> List[Dict]:
        """Get recent closed trades"""
        return self.db.get_closed_trades(limit=limit)

    def get_recent_signals(self, limit: int = 50) -> List[Dict]:
        """Get recent signals"""
        return self.db.get_recent_signals(limit)

    def get_logs(self, limit: int = 100) -> List[Dict]:
        """Get recent logs"""
        return self.db.get_logs(limit)


# ============================================================================
# Singleton instance for scheduler
# ============================================================================

_trader_instance: Optional[HERACLESTrader] = None


def get_heracles_trader() -> HERACLESTrader:
    """Get or create HERACLES trader instance"""
    global _trader_instance
    if _trader_instance is None:
        _trader_instance = HERACLESTrader()
    return _trader_instance


def run_heracles_scan() -> Dict[str, Any]:
    """
    Entry point for scheduler.

    Called periodically to run HERACLES trading logic.
    """
    trader = get_heracles_trader()
    return trader.run_scan()
