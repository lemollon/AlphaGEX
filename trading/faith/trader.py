"""
FAITH - Main Trader (Orchestrator)
===================================

Paper-trading 2DTE Iron Condor bot. Clone of FORTRESS with:
- 2DTE targeting (more premium than 0DTE, still day-traded)
- Paper-only execution (real Tradier data, no order placement)
- $5,000 simulated starting capital
- Max 1 trade per day
- 30% profit target, 100% stop loss, 3:45 PM ET EOD cutoff
- PDT compliance (max 3 day trades per rolling 5 business days)
- Symmetric wing enforcement

The asymmetric wings bug in FORTRESS's calculate_strikes() also exists
in the parent codebase. FAITH enforces symmetry; FORTRESS should be
fixed separately (not modified by this PR).
"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from .models import (
    FaithConfig, IronCondorPosition, PositionStatus,
    DailySummary, PaperAccount, CENTRAL_TZ, EASTERN_TZ
)
from .db import FaithDatabase
from .signals import FaithSignalGenerator
from .executor import FaithExecutor

logger = logging.getLogger(__name__)


class FaithTrader:
    """
    FAITH paper-trading Iron Condor bot.

    Lifecycle per scan cycle:
    1. Check if market is in trading window
    2. Check open positions - monitor for profit target / stop loss / EOD close
    3. If no open position and haven't traded today: check PDT, generate signal, trade
    4. Log all decisions to database
    """

    def __init__(self, config: Optional[FaithConfig] = None):
        """Initialize FAITH trader with database, signal generator, and executor."""
        # Load config from DB or use provided/default
        if config:
            self.config = config
        else:
            self.config = FaithConfig()

        dte_mode = self.config.dte_mode
        bot_name = f"FAITH_{dte_mode}" if dte_mode != "2DTE" else "FAITH"
        self.db = FaithDatabase(bot_name=bot_name, dte_mode=dte_mode)

        # If no config provided, load from DB (after DB is initialized)
        if not config:
            self.config = self.db.load_config()
            # Restore dte_mode since DB config doesn't store it
            self.config.dte_mode = dte_mode

        # Ensure paper account exists
        self.db.initialize_paper_account(self.config.starting_capital)

        # Initialize components
        self.signal_generator = FaithSignalGenerator(self.config)
        self.executor = FaithExecutor(self.config, self.db)

        # State
        self.is_active = True
        self.last_scan_time = None
        self.last_scan_result = None
        self._cycle_lock = threading.RLock()
        self._mtm_failure_counts = {}  # {position_id: consecutive_failure_count}

        # Circuit breaker: force-close after this many consecutive MTM failures
        self.MAX_CONSECUTIVE_MTM_FAILURES = 10

        logger.info(
            f"FAITH initialized: capital=${self.config.starting_capital}, "
            f"DTE={self.config.min_dte}, mode={dte_mode}, PT={self.config.profit_target_pct}%, "
            f"SL={self.config.stop_loss_pct}%, EOD={self.config.eod_cutoff_et} ET"
        )

        # Recover orphaned positions on startup
        self._recover_orphaned_positions()

    def _recover_orphaned_positions(self):
        """
        On startup, check for orphaned open positions.

        If market is open: log and resume monitoring (run_cycle will handle them).
        If market is closed: force-close with reason 'server_restart_recovery'.
        """
        try:
            open_positions = self.db.get_open_positions()
            if not open_positions:
                return

            now = datetime.now(CENTRAL_TZ)
            in_window, _ = self._is_in_trading_window(now)

            for position in open_positions:
                if in_window:
                    logger.info(
                        f"FAITH: Recovered orphaned position {position.position_id} — "
                        f"market open, resuming monitoring"
                    )
                    self.db.log("RECOVERY", f"Orphaned position {position.position_id} found on restart — resuming monitoring")
                else:
                    logger.warning(
                        f"FAITH: Recovered orphaned position {position.position_id} — "
                        f"market closed, force-closing at entry credit"
                    )
                    close_price = position.total_credit
                    self.executor.close_paper_position(
                        position, close_price, "server_restart_recovery"
                    )
                    self.db.log("RECOVERY", f"Orphaned position {position.position_id} force-closed on restart (market closed)")
        except Exception as e:
            logger.error(f"FAITH: Position recovery failed: {e}")

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """
        Execute one complete trading cycle.

        This is the main entry point called by the scheduler every 5 minutes.

        Steps:
        1. Check trading window
        2. Manage open positions (profit target, stop loss, EOD close)
        3. If no open positions and haven't traded today: evaluate and trade
        4. Update heartbeat

        Args:
            close_only: If True, only manage existing positions (don't open new ones)

        Returns:
            Dict with cycle results and status
        """
        with self._cycle_lock:
            return self._run_cycle_inner(close_only)

    def _run_cycle_inner(self, close_only: bool = False) -> Dict[str, Any]:
        """Inner cycle logic, protected by _cycle_lock."""
        now = datetime.now(CENTRAL_TZ)
        self.last_scan_time = now
        result = {
            'timestamp': now.isoformat(),
            'action': 'scan',
            'traded': False,
            'positions_managed': 0,
            'details': {},
        }

        try:
            # Step 1: ALWAYS manage existing positions (even if bot is disabled)
            # This ensures stop-loss, profit target, and EOD safety fire regardless
            open_positions = self.db.get_open_positions()
            if open_positions:
                managed, manage_pnl = self._manage_positions(now)
                result['positions_managed'] = managed
                if managed > 0:
                    result['details']['managed_pnl'] = manage_pnl

            # Step 2: Check if bot is active (only blocks NEW trades, not monitoring)
            if not self.is_active:
                result['action'] = 'inactive'
                note = 'Bot disabled'
                if open_positions:
                    note += f' — monitoring {len(open_positions)} existing position(s) only'
                result['details']['reason'] = note
                self.db.update_heartbeat('inactive', 'disabled_monitoring' if open_positions else 'disabled')
                self.last_scan_result = result
                return result

            # Step 3: Check trading window
            in_window, window_msg = self._is_in_trading_window(now)
            if not in_window:
                result['action'] = 'outside_window'
                result['details']['reason'] = window_msg
                self.db.update_heartbeat('idle', window_msg)
                self.last_scan_result = result
                return result

            # Step 4: Manage positions again if not done above (bot active, in window)
            if not open_positions:
                managed, manage_pnl = self._manage_positions(now)
                result['positions_managed'] = managed
                if managed > 0:
                    result['details']['managed_pnl'] = manage_pnl

            # Step 5: If close_only, stop here
            if close_only:
                result['action'] = 'close_only'
                self.db.update_heartbeat('active', 'close_only')
                self.last_scan_result = result
                return result

            # Step 6: Check if we can open a new trade
            open_positions = self.db.get_open_positions()
            if open_positions:
                result['action'] = 'monitoring'
                result['details']['reason'] = f'{len(open_positions)} position(s) open'
                self.db.update_heartbeat('active', 'monitoring')
                self.last_scan_result = result
                return result

            # Step 6: Already traded today?
            today_str = now.strftime('%Y-%m-%d')
            if self.db.has_traded_today(today_str):
                result['action'] = 'max_trades'
                result['details']['reason'] = 'Already traded today (max 1/day)'
                self.db.update_heartbeat('active', 'max_trades_reached')
                self.last_scan_result = result
                return result

            # Step 7: PDT check
            can_trade, pdt_count, pdt_msg = self.can_trade_today()
            if not can_trade:
                result['action'] = 'pdt_blocked'
                result['details']['reason'] = pdt_msg
                result['details']['pdt_count'] = pdt_count
                self.db.log("SKIP", f"PDT blocked: {pdt_msg}", {'pdt_count': pdt_count})
                self.db.update_heartbeat('active', 'pdt_blocked')
                self.last_scan_result = result
                return result

            # Step 8: Check buying power
            account = self.db.get_paper_account()
            if account.buying_power < 200:
                result['action'] = 'insufficient_bp'
                result['details']['reason'] = f'Buying power ${account.buying_power:.2f} < $200 minimum'
                self.db.log("SKIP", f"Insufficient BP: ${account.buying_power:.2f}")
                self.db.update_heartbeat('active', 'insufficient_bp')
                self.last_scan_result = result
                return result

            # Step 9: Generate signal
            signal = self.signal_generator.generate_signal()
            if not signal or not signal.is_valid:
                skip_reason = signal.reasoning if signal else "No signal generated"
                result['action'] = 'no_signal'
                result['details']['reason'] = skip_reason

                # Log the signal even if skipped
                if signal:
                    self.db.log_signal(
                        spot_price=signal.spot_price, vix=signal.vix,
                        expected_move=signal.expected_move,
                        call_wall=signal.call_wall, put_wall=signal.put_wall,
                        gex_regime=signal.gex_regime,
                        put_short=signal.put_short, put_long=signal.put_long,
                        call_short=signal.call_short, call_long=signal.call_long,
                        total_credit=signal.total_credit,
                        confidence=signal.confidence,
                        was_executed=False,
                        skip_reason=skip_reason,
                        reasoning=signal.reasoning,
                        wings_adjusted=signal.wings_adjusted,
                    )

                self.db.log("SKIP", f"No valid signal: {skip_reason}")
                self.db.update_heartbeat('active', 'no_signal')
                self.last_scan_result = result
                return result

            # Step 10: Size the trade
            spread_width = signal.put_short - signal.put_long
            collateral_per_contract = self.executor.calculate_collateral(
                spread_width, signal.total_credit
            )
            max_contracts = self.executor.calculate_max_contracts(
                account.buying_power, collateral_per_contract
            )

            if max_contracts < 1:
                result['action'] = 'insufficient_bp'
                result['details']['reason'] = (
                    f"Can't afford 1 contract. BP=${account.buying_power:.2f}, "
                    f"Collateral=${collateral_per_contract:.2f}"
                )
                self.db.log("SKIP", result['details']['reason'])
                self.db.update_heartbeat('active', 'insufficient_bp')
                self.last_scan_result = result
                return result

            # Step 11: Atomic guard — re-check no open position right before opening
            if self.db.get_open_positions():
                result['action'] = 'skipped'
                result['details']['reason'] = 'Position already exists (race condition guard)'
                self.db.log("SKIP", "Position already open — aborting duplicate open")
                self.last_scan_result = result
                return result

            # Step 12: Execute paper trade
            position = self.executor.open_paper_position(signal, max_contracts)
            if not position:
                result['action'] = 'execution_failed'
                result['details']['reason'] = 'Paper execution failed'
                self.db.log("ERROR", "Paper execution failed")
                self.last_scan_result = result
                return result

            # Log the executed signal
            self.db.log_signal(
                spot_price=signal.spot_price, vix=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall, put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                put_short=signal.put_short, put_long=signal.put_long,
                call_short=signal.call_short, call_long=signal.call_long,
                total_credit=signal.total_credit,
                confidence=signal.confidence,
                was_executed=True,
                reasoning=signal.reasoning,
                wings_adjusted=signal.wings_adjusted,
            )

            result['action'] = 'traded'
            result['traded'] = True
            result['details'] = {
                'position_id': position.position_id,
                'strikes': f"{signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C",
                'contracts': max_contracts,
                'credit': signal.total_credit,
                'collateral': collateral_per_contract * max_contracts,
                'expiration': signal.expiration,
                'wings_adjusted': signal.wings_adjusted,
                'pdt_count': pdt_count + 1,
            }

            self.db.update_heartbeat('active', 'traded')
            self.last_scan_result = result
            return result

        except Exception as e:
            logger.error(f"FAITH: Run cycle failed: {e}")
            import traceback
            traceback.print_exc()
            result['action'] = 'error'
            result['details']['error'] = str(e)
            self.db.log("ERROR", f"Run cycle error: {e}")
            self.last_scan_result = result
            return result

    def _manage_positions(self, now: datetime) -> Tuple[int, float]:
        """
        Manage open positions: check profit target, stop loss, and EOD cutoff.

        Returns:
            Tuple of (positions_managed, total_pnl)
        """
        positions = self.db.get_open_positions()
        if not positions:
            return 0, 0

        managed = 0
        total_pnl = 0

        for position in positions:
            close_price = self.signal_generator.get_ic_mark_to_market(
                put_short=position.put_short_strike,
                put_long=position.put_long_strike,
                call_short=position.call_short_strike,
                call_long=position.call_long_strike,
                expiration=position.expiration,
            )

            if close_price is None:
                # Track consecutive MTM failures per position
                pid = position.position_id
                self._mtm_failure_counts[pid] = self._mtm_failure_counts.get(pid, 0) + 1
                fail_count = self._mtm_failure_counts[pid]

                logger.warning(
                    f"FAITH: Could not get MTM for {pid} "
                    f"({fail_count}/{self.MAX_CONSECUTIVE_MTM_FAILURES} consecutive failures)"
                )

                # Circuit breaker: force-close after N consecutive failures
                if fail_count >= self.MAX_CONSECUTIVE_MTM_FAILURES:
                    logger.error(
                        f"FAITH: MTM circuit breaker triggered for {pid} — "
                        f"{fail_count} consecutive failures, force-closing at entry credit"
                    )
                    close_price = position.total_credit
                    success, pnl = self.executor.close_paper_position(
                        position, close_price, "data_feed_failure"
                    )
                    if success:
                        managed += 1
                        total_pnl += pnl
                        self._mtm_failure_counts.pop(pid, None)
                    continue

                # If we can't get MTM, still check EOD cutoff
                if self._is_past_eod_cutoff(now):
                    close_price = position.total_credit
                    success, pnl = self.executor.close_paper_position(
                        position, close_price, "eod_safety_no_data"
                    )
                    if success:
                        managed += 1
                        total_pnl += pnl
                        self._mtm_failure_counts.pop(pid, None)
                continue

            # Reset MTM failure counter on successful quote
            self._mtm_failure_counts.pop(position.position_id, None)

            entry_credit = position.total_credit

            # Check 1: 30% profit target
            profit_target_price = entry_credit * (1 - self.config.profit_target_pct / 100)
            if close_price <= profit_target_price:
                success, pnl = self.executor.close_paper_position(
                    position, close_price, "profit_target"
                )
                if success:
                    managed += 1
                    total_pnl += pnl
                    logger.info(
                        f"FAITH: Profit target hit for {position.position_id}: "
                        f"${close_price:.4f} <= ${profit_target_price:.4f}"
                    )
                continue

            # Check 2: Stop loss (IC doubles in price = 100% loss of credit)
            stop_loss_price = entry_credit * (1 + self.config.stop_loss_pct / 100)
            if close_price >= stop_loss_price:
                success, pnl = self.executor.close_paper_position(
                    position, close_price, "stop_loss"
                )
                if success:
                    managed += 1
                    total_pnl += pnl
                    logger.info(
                        f"FAITH: Stop loss hit for {position.position_id}: "
                        f"${close_price:.4f} >= ${stop_loss_price:.4f}"
                    )
                continue

            # Check 3: EOD safety close at 3:45 PM ET
            if self._is_past_eod_cutoff(now):
                success, pnl = self.executor.close_paper_position(
                    position, close_price, "eod_safety"
                )
                if success:
                    managed += 1
                    total_pnl += pnl
                    logger.info(
                        f"FAITH: EOD safety close for {position.position_id} "
                        f"@ ${close_price:.4f}"
                    )
                continue

        return managed, total_pnl

    def _is_in_trading_window(self, now: datetime) -> Tuple[bool, str]:
        """Check if current time is within trading window."""
        # Convert entry_start and entry_end from CT to compare
        hour = now.hour
        minute = now.minute
        current_minutes = hour * 60 + minute

        start_parts = self.config.entry_start.split(':')
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])

        # For managing positions, extend until EOD cutoff (in ET, convert to CT)
        # 3:45 PM ET = 2:45 PM CT
        eod_ct_minutes = 14 * 60 + 45  # 2:45 PM CT

        if current_minutes < start_minutes:
            return False, f"Before market open ({self.config.entry_start} CT)"
        if current_minutes > eod_ct_minutes:
            return False, f"Past EOD cutoff (2:45 PM CT)"

        return True, "In trading window"

    def _is_past_eod_cutoff(self, now: datetime) -> bool:
        """Check if past the EOD cutoff time (3:45 PM ET = 2:45 PM CT)."""
        now_et = now.astimezone(EASTERN_TZ)
        cutoff_parts = self.config.eod_cutoff_et.split(':')
        cutoff_hour = int(cutoff_parts[0])
        cutoff_minute = int(cutoff_parts[1])

        if now_et.hour > cutoff_hour:
            return True
        if now_et.hour == cutoff_hour and now_et.minute >= cutoff_minute:
            return True
        return False

    def can_trade_today(self) -> Tuple[bool, int, str]:
        """
        Pre-trade PDT + frequency check.

        Returns:
            Tuple of (can_trade, pdt_count, reason_message)
        """
        now = datetime.now(CENTRAL_TZ)
        today_str = now.strftime('%Y-%m-%d')

        # Check 1: Already traded today?
        if self.db.has_traded_today(today_str):
            return False, -1, "Already traded today (max 1/day)"

        # Check 2: PDT limit (3 day trades per rolling 5 business days)
        count = self.db.get_day_trade_count_rolling_5_days()
        if count >= self.config.pdt_max_day_trades:
            return False, count, f"PDT limit reached: {count}/{self.config.pdt_max_day_trades} day trades in rolling 5 days"

        return True, count, f"OK: {count}/{self.config.pdt_max_day_trades} day trades used"

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive bot status for API."""
        now = datetime.now(CENTRAL_TZ)
        account = self.db.get_paper_account()
        open_positions = self.db.get_open_positions()
        can_trade, pdt_count, pdt_msg = self.can_trade_today()
        today_str = now.strftime('%Y-%m-%d')
        trades_today = self.db.get_trades_today_count(today_str)

        # Get DB-based execution count from heartbeat (survives restarts)
        heartbeat = self.db.get_heartbeat_info()
        execution_count = heartbeat.get('scan_count', 0) if heartbeat else 0

        status_data = {
            'bot_name': 'FAITH',
            'display_name': 'FAITH',
            'strategy': f'{self.config.dte_mode} Paper Iron Condor',
            'dte_mode': self.config.dte_mode,
            'is_active': self.is_active,
            'is_paper': True,
            'mode': 'PAPER',
            'ticker': self.config.ticker,
            'dte': self.config.min_dte,
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'last_scan_result': self.last_scan_result,
            'open_positions': len(open_positions),
            'trades_today': trades_today,
            'max_trades_per_day': self.config.max_trades_per_day,
            'profit_target_pct': self.config.profit_target_pct,
            'stop_loss_pct': self.config.stop_loss_pct,
            'eod_cutoff': self.config.eod_cutoff_et,
            'sd_multiplier': self.config.sd_multiplier,
            'spread_width': self.config.spread_width,
            'vix_skip': self.config.vix_skip,
            'paper_account': account.to_dict(),
            'pdt': {
                'day_trades_rolling_5': pdt_count if pdt_count >= 0 else 0,
                'day_trades_remaining': max(0, self.config.pdt_max_day_trades - (pdt_count if pdt_count >= 0 else 0)),
                'trades_today': trades_today,
                'can_trade': can_trade,
                'reason': pdt_msg,
                'next_reset': self.db.get_next_pdt_reset_date(),
            },
            'scheduler': {
                'job_id': 'faith_trading',
                'interval_minutes': 5,
                'execution_count': execution_count,
                'last_heartbeat': heartbeat.get('last_heartbeat') if heartbeat else None,
                'heartbeat_status': heartbeat.get('status') if heartbeat else 'UNKNOWN',
            },
        }

        return status_data

    def get_position_monitor(self) -> Optional[Dict[str, Any]]:
        """
        Get live position monitoring data.

        Returns real-time data about the open position including
        progress toward profit target and stop loss.
        """
        positions = self.db.get_open_positions()
        if not positions:
            return None

        position = positions[0]  # FAITH only has 1 position at a time

        # Get current cost to close from Tradier
        current_cost = self.signal_generator.get_ic_mark_to_market(
            put_short=position.put_short_strike,
            put_long=position.put_long_strike,
            call_short=position.call_short_strike,
            call_long=position.call_long_strike,
            expiration=position.expiration,
        )

        entry_credit = position.total_credit
        profit_target_price = entry_credit * (1 - self.config.profit_target_pct / 100)
        stop_loss_price = entry_credit * (1 + self.config.stop_loss_pct / 100)

        pnl_per_contract = 0
        pnl_pct = 0
        if current_cost is not None:
            pnl_per_contract = (entry_credit - current_cost) * 100
            pnl_pct = ((entry_credit - current_cost) / entry_credit * 100) if entry_credit > 0 else 0

        put_width = position.put_short_strike - position.put_long_strike
        call_width = position.call_long_strike - position.call_short_strike

        return {
            'position_id': position.position_id,
            'ticker': position.ticker,
            'expiration': position.expiration,
            'put_short_strike': position.put_short_strike,
            'put_long_strike': position.put_long_strike,
            'call_short_strike': position.call_short_strike,
            'call_long_strike': position.call_long_strike,
            'put_width': put_width,
            'call_width': call_width,
            'wings_symmetric': abs(put_width - call_width) < 0.01,
            'wings_adjusted': position.wings_adjusted,
            'contracts': position.contracts,
            'entry_credit': entry_credit,
            'current_cost_to_close': current_cost,
            'profit_target_price': round(profit_target_price, 4),
            'stop_loss_price': round(stop_loss_price, 4),
            'pnl_per_contract': round(pnl_per_contract, 2) if current_cost else None,
            'pnl_total': round(pnl_per_contract * position.contracts, 2) if current_cost else None,
            'pnl_pct': round(pnl_pct, 1) if current_cost else None,
            'profit_target_pct': self.config.profit_target_pct,
            'stop_loss_pct': self.config.stop_loss_pct,
            'eod_cutoff': self.config.eod_cutoff_et,
            'open_time': position.open_time.isoformat() if position.open_time else None,
            'collateral_required': position.collateral_required,
        }

    def toggle(self, active: bool) -> Dict[str, Any]:
        """Enable or disable the bot."""
        self.is_active = active
        status = "enabled" if active else "disabled"
        self.db.log("CONFIG", f"FAITH bot {status}")
        logger.info(f"FAITH: Bot {status}")
        return {'is_active': self.is_active, 'message': f'FAITH bot {status}'}
