"""
VALOR Margin Manager — Zone-based margin protection system.

Layers on TOP of the existing margin tracker (trading/shared/margin_engine.py
and trading/shared/margin_config.py). Does NOT replace or duplicate any existing
margin calculation — calls existing functions for utilization data and uses
existing close_position() for liquidation.

Zone System (per-instrument, isolated $100K each):
  GREEN   0-50%   Normal trading
  YELLOW  50-70%  Reduce new position sizing 50%, warn
  ORANGE  70-80%  Block new entries, close 1 worst position/cycle
  RED     80-90%  Block new entries, close 2 worst positions/cycle
  CRITICAL 90%+   Flatten all positions, 30-min cooldown

Combined portfolio thresholds (more conservative):
  GREEN   0-40%
  YELLOW  40-55%
  ORANGE  55-70%
  RED     70-80%
  CRITICAL 80%+
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from .models import FUTURES_TICKERS, get_ticker_point_value, CENTRAL_TZ

logger = logging.getLogger(__name__)


# =============================================================================
# CME MARGIN REQUIREMENTS (single source of truth for VALOR)
# =============================================================================
# These are the SIMULATED exchange margin rates. Update here when CME changes.
# Also kept in sync with trading/shared/margin_config.py FUTURES_MARGIN_SPECS.

VALOR_MARGIN_REQUIREMENTS: Dict[str, Dict[str, float]] = {
    "MES": {"initial": 2300.0, "maintenance": 2100.0},
    "MNQ": {"initial": 3300.0, "maintenance": 3000.0},
    "RTY": {"initial": 950.0, "maintenance": 860.0},
    "CL":  {"initial": 575.0, "maintenance": 520.0},
    "NG":  {"initial": 575.0, "maintenance": 520.0},
    "MGC": {"initial": 1870.0, "maintenance": 1700.0},
}


def get_margin_requirement(ticker: str) -> Dict[str, float]:
    """Get margin requirements for a VALOR instrument."""
    return VALOR_MARGIN_REQUIREMENTS.get(ticker, {"initial": 2300.0, "maintenance": 2100.0})


# =============================================================================
# ZONE DEFINITIONS
# =============================================================================

class MarginZone(Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    CRITICAL = "CRITICAL"


# Per-instrument zone thresholds (maintenance margin / equity)
INSTRUMENT_ZONE_THRESHOLDS = {
    MarginZone.GREEN: (0.0, 0.50),
    MarginZone.YELLOW: (0.50, 0.70),
    MarginZone.ORANGE: (0.70, 0.80),
    MarginZone.RED: (0.80, 0.90),
    MarginZone.CRITICAL: (0.90, float('inf')),
}

# Combined portfolio thresholds (more conservative)
COMBINED_ZONE_THRESHOLDS = {
    MarginZone.GREEN: (0.0, 0.40),
    MarginZone.YELLOW: (0.40, 0.55),
    MarginZone.ORANGE: (0.55, 0.70),
    MarginZone.RED: (0.70, 0.80),
    MarginZone.CRITICAL: (0.80, float('inf')),
}

ZONE_EMOJI = {
    MarginZone.GREEN: "🟢",
    MarginZone.YELLOW: "⚠️",
    MarginZone.ORANGE: "🟠",
    MarginZone.RED: "🔴",
    MarginZone.CRITICAL: "⚫",
}


def get_zone(utilization: float, thresholds: Dict = None) -> MarginZone:
    """Determine margin zone from utilization percentage (0.0 to 1.0+)."""
    if thresholds is None:
        thresholds = INSTRUMENT_ZONE_THRESHOLDS
    for zone, (low, high) in thresholds.items():
        if low <= utilization < high:
            return zone
    return MarginZone.CRITICAL


# =============================================================================
# MARGIN MANAGER
# =============================================================================

class ValorMarginManager:
    """
    Margin protection system for VALOR multi-instrument futures bot.

    Uses isolated margin per instrument (each has its own $100K allocation).
    Hooks into existing position open/close functions — does NOT create new
    execution paths.
    """

    def __init__(self):
        # Per-instrument zone tracking
        self._previous_zones: Dict[str, MarginZone] = {}
        self._previous_combined_zone: MarginZone = MarginZone.GREEN

        # Cooldown state (per-instrument)
        self._cooldown_until: Dict[str, Optional[datetime]] = {}
        self._liquidation_count_today: Dict[str, int] = {}
        self._last_liquidation_time: Dict[str, Optional[datetime]] = {}
        self._liquidation_date: Optional[str] = None  # For daily reset
        self._re_entry_reduced: Dict[str, bool] = {}  # First re-entry after liquidation = 50% size

        # Margin event log (in-memory ring buffer, latest 200 events)
        self._margin_events: List[Dict[str, Any]] = []
        self._max_events = 200

        # Initialize state for all configured tickers
        for ticker in VALOR_MARGIN_REQUIREMENTS:
            self._previous_zones[ticker] = MarginZone.GREEN
            self._cooldown_until[ticker] = None
            self._liquidation_count_today[ticker] = 0
            self._last_liquidation_time[ticker] = None
            self._re_entry_reduced[ticker] = False

        margin_summary = ', '.join(
            f'{k}=${v["initial"]}' for k, v in VALOR_MARGIN_REQUIREMENTS.items()
        )
        logger.info(
            f"ValorMarginManager initialized: {len(VALOR_MARGIN_REQUIREMENTS)} instruments, "
            f"margins={margin_summary}"
        )

    # =========================================================================
    # CORE: Calculate margin state for one instrument
    # =========================================================================

    def get_instrument_margin_state(
        self,
        ticker: str,
        open_positions: list,
        equity: float,
    ) -> Dict[str, Any]:
        """
        Calculate full margin state for a single instrument.

        Args:
            ticker: Instrument symbol (MES, MNQ, etc.)
            open_positions: List of FuturesPosition objects for this ticker
            equity: Per-instrument equity (starting_capital + realized_pnl)

        Returns:
            Dict with margin_used, utilization, zone, free_margin, etc.
        """
        req = get_margin_requirement(ticker)
        maint_margin = req["maintenance"]
        init_margin = req["initial"]

        total_contracts = sum(getattr(p, 'contracts', 1) for p in open_positions)
        total_maintenance_margin = total_contracts * maint_margin
        total_initial_margin = total_contracts * init_margin

        utilization = (total_maintenance_margin / equity) if equity > 0 else 1.0
        free_margin = max(0.0, equity - total_maintenance_margin)
        zone = get_zone(utilization)

        return {
            "ticker": ticker,
            "equity": equity,
            "contracts": total_contracts,
            "positions": len(open_positions),
            "maintenance_margin_used": total_maintenance_margin,
            "initial_margin_used": total_initial_margin,
            "utilization": utilization,
            "utilization_pct": round(utilization * 100, 1),
            "free_margin": free_margin,
            "zone": zone,
            "zone_name": zone.value,
            "initial_per_contract": init_margin,
            "maintenance_per_contract": maint_margin,
            "max_new_contracts": int(free_margin / init_margin) if init_margin > 0 else 0,
            "liquidation_count_today": self._liquidation_count_today.get(ticker, 0),
            "cooldown_until": self._cooldown_until.get(ticker),
            "in_cooldown": self._is_in_cooldown(ticker),
        }

    def get_combined_margin_state(
        self,
        per_instrument_states: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate combined portfolio margin state across all instruments.

        Args:
            per_instrument_states: Dict of ticker -> instrument margin state

        Returns:
            Dict with combined utilization, zone, per-instrument breakdown
        """
        total_equity = sum(s["equity"] for s in per_instrument_states.values())
        total_maintenance = sum(s["maintenance_margin_used"] for s in per_instrument_states.values())
        total_contracts = sum(s["contracts"] for s in per_instrument_states.values())

        utilization = (total_maintenance / total_equity) if total_equity > 0 else 1.0
        zone = get_zone(utilization, COMBINED_ZONE_THRESHOLDS)

        return {
            "total_equity": total_equity,
            "total_maintenance_margin": total_maintenance,
            "total_contracts": total_contracts,
            "utilization": utilization,
            "utilization_pct": round(utilization * 100, 1),
            "zone": zone,
            "zone_name": zone.value,
            "instruments": per_instrument_states,
        }

    # =========================================================================
    # PRE-TRADE MARGIN GATE
    # =========================================================================

    def can_open_position(
        self,
        ticker: str,
        num_contracts: int,
        open_positions: list,
        equity: float,
    ) -> Tuple[bool, str, int]:
        """
        Check if there's enough margin to open a new position.

        Returns:
            (allowed, reason, adjusted_contracts)
            - adjusted_contracts may be less than requested (YELLOW zone reduction)
        """
        state = self.get_instrument_margin_state(ticker, open_positions, equity)
        zone = state["zone"]
        utilization = state["utilization"]
        free_margin = state["free_margin"]
        req = get_margin_requirement(ticker)

        # Check cooldown
        if self._is_in_cooldown(ticker):
            remaining = self._cooldown_remaining_minutes(ticker)
            return False, f"[MARGIN][{ticker}] Re-entry BLOCKED — still in cooldown ({remaining:.0f} min remaining)", 0

        # Check if instrument is paused for the day (3rd margin event)
        if self._liquidation_count_today.get(ticker, 0) >= 3:
            return False, f"[MARGIN][{ticker}] Re-entry BLOCKED — 3rd margin liquidation today, instrument paused until midnight", 0

        # Must be in GREEN zone to re-enter after a margin-forced liquidation
        if self._re_entry_reduced.get(ticker, False) and zone != MarginZone.GREEN:
            return False, f"[MARGIN][{ticker}] Re-entry BLOCKED — must be in GREEN zone (current: {zone.value}, {state['utilization_pct']}%)", 0

        # ORANGE or above: block ALL new entries
        if zone in (MarginZone.ORANGE, MarginZone.RED, MarginZone.CRITICAL):
            return False, f"[MARGIN][{ticker}] {zone.value} zone ({state['utilization_pct']}%): new entries blocked", 0

        initial_margin_needed = num_contracts * req["initial"]
        new_maintenance = state["maintenance_margin_used"] + (num_contracts * req["maintenance"])
        new_utilization = (new_maintenance / equity) if equity > 0 else 1.0

        # Check: enough free margin for initial margin?
        if initial_margin_needed > free_margin:
            return False, (
                f"[MARGIN][{ticker}] Insufficient free margin: "
                f"need ${initial_margin_needed:,.0f}, have ${free_margin:,.0f}"
            ), 0

        adjusted_contracts = num_contracts

        # YELLOW zone: reduce by 50%
        if zone == MarginZone.YELLOW:
            adjusted_contracts = max(1, num_contracts // 2)
            new_maintenance_adj = state["maintenance_margin_used"] + (adjusted_contracts * req["maintenance"])
            new_util_adj = (new_maintenance_adj / equity) if equity > 0 else 1.0
            if new_util_adj >= 0.70:
                return False, f"[MARGIN][{ticker}] YELLOW zone: even reduced position would push to ORANGE. Blocked.", 0
            return True, (
                f"[MARGIN][{ticker}] YELLOW zone ({state['utilization_pct']}%): "
                f"reduced from {num_contracts} to {adjusted_contracts} contracts"
            ), adjusted_contracts

        # GREEN zone: check that opening won't push past 50%
        if zone == MarginZone.GREEN and new_utilization >= 0.50:
            # Calculate max contracts to stay below 50%
            max_maint_for_green = equity * 0.49 - state["maintenance_margin_used"]
            max_contracts_green = int(max_maint_for_green / req["maintenance"]) if req["maintenance"] > 0 else 0
            if max_contracts_green < 1:
                return False, f"[MARGIN][{ticker}] Cannot open even 1 contract without entering YELLOW zone", 0
            adjusted_contracts = min(num_contracts, max_contracts_green)
            return True, (
                f"[MARGIN][{ticker}] Reduced to {adjusted_contracts} contracts to stay in GREEN zone"
            ), adjusted_contracts

        # Post-liquidation re-entry: first trade is 50% size
        if self._re_entry_reduced.get(ticker, False):
            adjusted_contracts = max(1, adjusted_contracts // 2)
            self._re_entry_reduced[ticker] = False  # Clear after first re-entry
            return True, (
                f"[MARGIN][{ticker}] Re-entry allowed — GREEN zone ({state['utilization_pct']}%), "
                f"cooldown expired, reduced size (50%) → {adjusted_contracts} contracts"
            ), adjusted_contracts

        return True, f"[MARGIN][{ticker}] GREEN zone ({state['utilization_pct']}%): full size approved", adjusted_contracts

    # =========================================================================
    # LIQUIDATION ENGINE
    # =========================================================================

    def get_positions_to_liquidate(
        self,
        ticker: str,
        open_positions: list,
        equity: float,
        current_prices: Dict[str, float],
    ) -> List[Any]:
        """
        Determine which positions to close based on margin zone.

        Returns list of positions to close (ordered by priority).
        ORANGE: 1 position, RED: 2, CRITICAL: all.
        """
        state = self.get_instrument_margin_state(ticker, open_positions, equity)
        zone = state["zone"]

        if zone in (MarginZone.GREEN, MarginZone.YELLOW):
            return []

        if not open_positions:
            return []

        # Score all positions by return_on_margin (worst first)
        scored = self._score_positions(ticker, open_positions, current_prices)

        if zone == MarginZone.CRITICAL:
            # Flatten ALL positions
            return [p for p, _ in scored]

        if zone == MarginZone.RED:
            # Close up to 2 worst positions
            count = min(2, len(scored))
            return [p for p, _ in scored[:count]]

        if zone == MarginZone.ORANGE:
            # Close 1 worst position
            return [scored[0][0]] if scored else []

        return []

    def _score_positions(
        self,
        ticker: str,
        positions: list,
        current_prices: Dict[str, float],
    ) -> List[Tuple[Any, float]]:
        """
        Score positions by return_on_margin (lowest/worst first).

        Returns list of (position, return_on_margin) sorted worst-first.
        """
        req = get_margin_requirement(ticker)
        maint = req["maintenance"]
        point_value = get_ticker_point_value(ticker)

        scored = []
        for pos in positions:
            price = current_prices.get(ticker, getattr(pos, 'entry_price', 0))
            entry = getattr(pos, 'entry_price', 0)
            contracts = getattr(pos, 'contracts', 1)
            direction_val = getattr(pos, 'direction', None)
            if direction_val is not None and hasattr(direction_val, 'value'):
                direction_str = direction_val.value.lower()
            else:
                direction_str = str(direction_val).lower() if direction_val else "long"
            direction = 1 if direction_str in ("long", "buy") else -1

            unrealized_pnl = (price - entry) * point_value * direction * contracts
            margin_consumed = contracts * maint

            if margin_consumed > 0:
                return_on_margin = unrealized_pnl / margin_consumed
            else:
                return_on_margin = 0.0

            scored.append((pos, return_on_margin))

        # Sort: worst return_on_margin first (most negative)
        # Tiebreaker: more margin consumed first (frees more capital)
        scored.sort(key=lambda x: (x[1], -(getattr(x[0], 'contracts', 1) * maint)))

        return scored

    def execute_liquidations(
        self,
        ticker: str,
        positions_to_close: list,
        close_position_fn,
        current_prices: Dict[str, float],
        zone: MarginZone,
    ) -> int:
        """
        Execute margin-forced liquidations using the existing close function.

        Args:
            ticker: Instrument being liquidated
            positions_to_close: Ordered list of positions to close
            close_position_fn: Reference to ValorTrader._close_position()
            current_prices: Dict of ticker -> current price
            zone: Current margin zone (for logging)

        Returns:
            Number of positions successfully closed
        """
        closed_count = 0
        price = current_prices.get(ticker, 0)

        if not price:
            logger.error(f"[MARGIN][{ticker}] Cannot liquidate — no current price available")
            return 0

        for pos in positions_to_close:
            try:
                from .models import PositionStatus
                reason = f"MARGIN_{zone.value}_LIQUIDATION"
                success = close_position_fn(
                    pos, price, PositionStatus.STOPPED, reason
                )
                if success:
                    closed_count += 1
                    pos_id = getattr(pos, 'position_id', 'unknown')[:12]
                    contracts = getattr(pos, 'contracts', 0)
                    entry = getattr(pos, 'entry_price', 0)
                    direction = getattr(pos, 'direction', None)
                    dir_str = direction.value if hasattr(direction, 'value') else str(direction)

                    point_value = get_ticker_point_value(ticker)
                    dir_mult = 1 if str(dir_str).lower() in ("long", "buy") else -1
                    unrealized = (price - entry) * point_value * dir_mult * contracts

                    logger.warning(
                        f"[MARGIN][{ticker}] {ZONE_EMOJI.get(zone, '')} Forced liquidation — "
                        f"Closed {dir_str} {contracts}ct @ ${price:,.2f} "
                        f"(P&L: ${unrealized:+,.2f}) [{pos_id}]"
                    )

                    self._log_margin_event(
                        ticker, "forced_liquidation",
                        f"Closed {dir_str} {contracts}ct @ ${price:,.2f} (P&L: ${unrealized:+,.2f})",
                        zone,
                    )
            except Exception as e:
                logger.error(f"[MARGIN][{ticker}] Liquidation failed for position: {e}")

        if closed_count > 0:
            self._record_liquidation(ticker)

        return closed_count

    # =========================================================================
    # COOLDOWN / RE-ENTRY LOGIC
    # =========================================================================

    def _record_liquidation(self, ticker: str) -> None:
        """Record a margin-forced liquidation event for cooldown tracking."""
        now = datetime.now(CENTRAL_TZ)

        # Daily reset check
        today_str = now.strftime('%Y-%m-%d')
        if self._liquidation_date != today_str:
            self._liquidation_date = today_str
            for tk in VALOR_MARGIN_REQUIREMENTS:
                self._liquidation_count_today[tk] = 0

        self._liquidation_count_today[ticker] = self._liquidation_count_today.get(ticker, 0) + 1
        self._last_liquidation_time[ticker] = now
        count = self._liquidation_count_today[ticker]

        # Set cooldown based on count
        if count >= 3:
            # 3rd time: paused until midnight
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            self._cooldown_until[ticker] = tomorrow
            logger.critical(
                f"[MARGIN][{ticker}] ⚫ 3rd margin liquidation today — "
                f"instrument PAUSED until midnight CT"
            )
        elif count >= 2:
            # 2nd time: 2 hour cooldown
            self._cooldown_until[ticker] = now + timedelta(hours=2)
            logger.warning(
                f"[MARGIN][{ticker}] 🔴 2nd margin liquidation today — "
                f"2-hour cooldown until {self._cooldown_until[ticker].strftime('%H:%M')} CT"
            )
        else:
            # 1st time: 30 minute cooldown
            self._cooldown_until[ticker] = now + timedelta(minutes=30)
            logger.warning(
                f"[MARGIN][{ticker}] 🟠 Margin liquidation — "
                f"30-min cooldown until {self._cooldown_until[ticker].strftime('%H:%M')} CT"
            )

        # Mark that next re-entry should be reduced size
        self._re_entry_reduced[ticker] = True

    def _is_in_cooldown(self, ticker: str) -> bool:
        """Check if instrument is in margin cooldown."""
        cooldown = self._cooldown_until.get(ticker)
        if cooldown is None:
            return False
        now = datetime.now(CENTRAL_TZ)
        if now >= cooldown:
            self._cooldown_until[ticker] = None
            return False
        return True

    def _cooldown_remaining_minutes(self, ticker: str) -> float:
        """Get remaining cooldown time in minutes."""
        cooldown = self._cooldown_until.get(ticker)
        if cooldown is None:
            return 0.0
        now = datetime.now(CENTRAL_TZ)
        if now >= cooldown:
            return 0.0
        return (cooldown - now).total_seconds() / 60

    # =========================================================================
    # ZONE MONITORING (called every scan cycle)
    # =========================================================================

    def monitor_and_log(
        self,
        per_instrument_states: Dict[str, Dict[str, Any]],
        combined_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Log margin status for all instruments. Detect zone changes.

        Called once per scan cycle from run_scan().

        Returns:
            Dict with zone_changes and any instruments needing liquidation.
        """
        zone_changes = {}
        needs_liquidation = []

        # Per-instrument logging
        for ticker, state in per_instrument_states.items():
            zone = state["zone"]
            prev_zone = self._previous_zones.get(ticker, MarginZone.GREEN)
            emoji = ZONE_EMOJI.get(zone, "")

            # Log margin status every cycle
            logger.info(
                f"[MARGIN][{ticker}] Equity: ${state['equity']:,.0f} | "
                f"Margin Used: ${state['maintenance_margin_used']:,.0f} ({state['contracts']} contracts) | "
                f"Utilization: {state['utilization_pct']}% | "
                f"Zone: {emoji} {zone.value} | "
                f"Free: ${state['free_margin']:,.0f}"
            )

            # Detect zone change
            if zone != prev_zone:
                direction = "→"
                if zone.value > prev_zone.value:
                    # Getting worse
                    logger.warning(
                        f"[MARGIN][{ticker}] {emoji} ZONE CHANGE: "
                        f"{prev_zone.value} → {zone.value} "
                        f"(utilization: {state['utilization_pct']}%)"
                    )
                else:
                    # Getting better
                    logger.info(
                        f"[MARGIN][{ticker}] ✅ ZONE CHANGE: "
                        f"{prev_zone.value} → {zone.value} "
                        f"(utilization: {state['utilization_pct']}%) — pressure relieved"
                    )

                zone_changes[ticker] = {
                    "from": prev_zone.value,
                    "to": zone.value,
                    "utilization_pct": state["utilization_pct"],
                }
                self._log_margin_event(
                    ticker, "zone_change",
                    f"{prev_zone.value} → {zone.value} ({state['utilization_pct']}%)",
                    zone,
                )
                self._previous_zones[ticker] = zone

            # Flag instruments needing liquidation
            if zone in (MarginZone.ORANGE, MarginZone.RED, MarginZone.CRITICAL):
                needs_liquidation.append(ticker)

        # Combined portfolio logging
        cz = combined_state["zone"]
        prev_cz = self._previous_combined_zone
        logger.info(
            f"[MARGIN][COMBINED] Equity: ${combined_state['total_equity']:,.0f} | "
            f"Margin Used: ${combined_state['total_maintenance_margin']:,.0f} | "
            f"Utilization: {combined_state['utilization_pct']}% | "
            f"Zone: {ZONE_EMOJI.get(cz, '')} {cz.value}"
        )

        if cz != prev_cz:
            zone_changes["COMBINED"] = {
                "from": prev_cz.value,
                "to": cz.value,
                "utilization_pct": combined_state["utilization_pct"],
            }
            self._log_margin_event(
                "COMBINED", "zone_change",
                f"{prev_cz.value} → {cz.value} ({combined_state['utilization_pct']}%)",
                cz,
            )
            self._previous_combined_zone = cz

        # Combined zone override: if combined is ORANGE+ but individual instruments are GREEN
        if cz in (MarginZone.ORANGE, MarginZone.RED, MarginZone.CRITICAL):
            # Find worst-performing instrument across all
            # (handled by caller using combined_state info)
            pass

        return {
            "zone_changes": zone_changes,
            "needs_liquidation": needs_liquidation,
            "combined_zone": cz.value,
        }

    # =========================================================================
    # COMBINED PORTFOLIO LIQUIDATION TARGET
    # =========================================================================

    def get_combined_liquidation_target(
        self,
        all_positions_by_ticker: Dict[str, list],
        per_instrument_states: Dict[str, Dict[str, Any]],
        combined_state: Dict[str, Any],
        current_prices: Dict[str, float],
    ) -> Optional[Tuple[str, list]]:
        """
        When combined margin triggers action, find the worst position across
        ALL instruments to liquidate.

        Returns:
            (ticker, [position]) or None if no action needed
        """
        cz = combined_state["zone"]
        if cz in (MarginZone.GREEN, MarginZone.YELLOW):
            return None

        # Score ALL positions across ALL instruments
        all_scored = []
        for ticker, positions in all_positions_by_ticker.items():
            scored = self._score_positions(ticker, positions, current_prices)
            for pos, rom in scored:
                all_scored.append((ticker, pos, rom))

        if not all_scored:
            return None

        # Sort by return_on_margin (worst first)
        all_scored.sort(key=lambda x: x[2])

        # Return the worst position's ticker and the position
        worst_ticker, worst_pos, worst_rom = all_scored[0]
        logger.warning(
            f"[MARGIN][COMBINED] {ZONE_EMOJI.get(cz, '')} Combined {cz.value} zone — "
            f"targeting {worst_ticker} position (return_on_margin: {worst_rom:.3f})"
        )

        return worst_ticker, [worst_pos]

    # =========================================================================
    # MARGIN EVENT LOG
    # =========================================================================

    def _log_margin_event(
        self,
        ticker: str,
        event_type: str,
        description: str,
        zone: MarginZone,
    ) -> None:
        """Log a margin event to the in-memory ring buffer."""
        event = {
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "ticker": ticker,
            "event": event_type,
            "description": description,
            "zone": zone.value,
        }
        self._margin_events.append(event)
        if len(self._margin_events) > self._max_events:
            self._margin_events = self._margin_events[-self._max_events:]

    def get_margin_events(self, limit: int = 50, ticker: Optional[str] = None) -> List[Dict]:
        """Get recent margin events, optionally filtered by ticker."""
        events = self._margin_events
        if ticker:
            events = [e for e in events if e["ticker"] == ticker]
        return list(reversed(events[-limit:]))

    # =========================================================================
    # SERIALIZATION (for API responses)
    # =========================================================================

    def get_status_dict(self) -> Dict[str, Any]:
        """Get full margin manager status for API."""
        now = datetime.now(CENTRAL_TZ)
        cooldowns = {}
        for ticker in VALOR_MARGIN_REQUIREMENTS:
            cd = self._cooldown_until.get(ticker)
            cooldowns[ticker] = {
                "in_cooldown": self._is_in_cooldown(ticker),
                "cooldown_until": cd.isoformat() if cd and now < cd else None,
                "remaining_minutes": self._cooldown_remaining_minutes(ticker),
                "liquidation_count_today": self._liquidation_count_today.get(ticker, 0),
                "re_entry_reduced": self._re_entry_reduced.get(ticker, False),
            }

        return {
            "margin_requirements": VALOR_MARGIN_REQUIREMENTS,
            "cooldowns": cooldowns,
            "recent_events": self.get_margin_events(limit=20),
            "previous_zones": {k: v.value for k, v in self._previous_zones.items()},
            "combined_zone": self._previous_combined_zone.value,
        }
