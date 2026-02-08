"""
Bot Decision Logger - Comprehensive Unified Logging for All Bots

This module provides the central logging function that ALL bots use.
It captures FULL transparency on every decision including:
- Claude AI prompts/responses
- Execution timeline (order submitted → filled)
- Alternative analysis
- Session tracking
- Risk checks
- Error logging

Usage:
    from trading.bot_logger import log_bot_decision, BotDecision, ExecutionTimeline

    decision = BotDecision(
        bot_name="FORTRESS",
        decision_type="ENTRY",
        action="SELL",
        symbol="SPY",
        ...
    )
    decision_id = log_bot_decision(decision)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import json
import uuid
import time
from zoneinfo import ZoneInfo

from database_adapter import get_connection

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")


class BotName(Enum):
    """Bot identifiers"""
    LAZARUS = "LAZARUS"
    CORNERSTONE = "CORNERSTONE"
    FORTRESS = "FORTRESS"
    SHEPHERD = "SHEPHERD"
    PROPHET = "PROPHET"
    SOLOMON = "SOLOMON"    # Directional Spreads (Bull Call / Bear Call)
    GIDEON = "GIDEON"    # Aggressive Directional Spreads (relaxed GEX filters)
    ANCHOR = "ANCHOR"  # SPX Iron Condor ($10 spreads, weekly)
    SAMSON = "SAMSON"      # Aggressive SPX Iron Condor ($12 spreads)
    JUBILEE = "JUBILEE"  # Box Spread Synthetic Borrowing + IC Trading


class DecisionType(Enum):
    """Types of trading decisions"""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    SKIP = "SKIP"
    ADJUSTMENT = "ADJUSTMENT"
    ANALYSIS = "ANALYSIS"


class ExitTrigger(Enum):
    """What triggered an exit"""
    PROFIT_TARGET = "PROFIT_TARGET"
    STOP_LOSS = "STOP_LOSS"
    TIME_DECAY = "TIME_DECAY"
    MANUAL = "MANUAL"
    GEX_REGIME_CHANGE = "GEX_REGIME_CHANGE"
    EXPIRATION = "EXPIRATION"
    RISK_LIMIT = "RISK_LIMIT"


@dataclass
class ClaudeContext:
    """Claude AI interaction details for full transparency"""
    prompt: str = ""
    response: str = ""
    model: str = "claude-sonnet-4-5-latest"
    tokens_used: int = 0
    response_time_ms: int = 0
    chain_name: str = ""  # LangChain chain used
    confidence: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "prompt": self.prompt,
            "response": self.response,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "response_time_ms": self.response_time_ms,
            "chain_name": self.chain_name,
            "confidence": self.confidence,
            "warnings": self.warnings
        }


@dataclass
class MarketContext:
    """Market conditions at decision time"""
    spot_price: float = 0.0
    vix: float = 0.0
    net_gex: float = 0.0
    gex_regime: str = ""
    flip_point: float = 0.0
    call_wall: float = 0.0
    put_wall: float = 0.0
    trend: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Alternative:
    """An alternative that was considered but rejected"""
    strike: float = 0.0
    strategy: str = ""
    reason_rejected: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RiskCheck:
    """A risk check that was performed"""
    check_name: str = ""
    passed: bool = True
    current_value: float = 0.0
    limit_value: float = 0.0
    message: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ApiCall:
    """An API call made during decision process"""
    api_name: str = ""
    endpoint: str = ""
    time_ms: int = 0
    success: bool = True
    error: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExecutionTimeline:
    """Order execution timeline for tracking slippage"""
    order_submitted_at: Optional[datetime] = None
    order_filled_at: Optional[datetime] = None
    broker_order_id: str = ""
    expected_fill_price: float = 0.0
    actual_fill_price: float = 0.0
    broker_status: str = ""
    execution_notes: str = ""

    @property
    def slippage_pct(self) -> float:
        if self.expected_fill_price > 0 and self.actual_fill_price > 0:
            return ((self.actual_fill_price - self.expected_fill_price) / self.expected_fill_price) * 100
        return 0.0

    def to_dict(self) -> Dict:
        return {
            "order_submitted_at": self.order_submitted_at.isoformat() if self.order_submitted_at and hasattr(self.order_submitted_at, 'isoformat') else self.order_submitted_at,
            "order_filled_at": self.order_filled_at.isoformat() if self.order_filled_at and hasattr(self.order_filled_at, 'isoformat') else self.order_filled_at,
            "broker_order_id": self.broker_order_id,
            "expected_fill_price": self.expected_fill_price,
            "actual_fill_price": self.actual_fill_price,
            "slippage_pct": self.slippage_pct,
            "broker_status": self.broker_status,
            "execution_notes": self.execution_notes
        }


@dataclass
class BotDecision:
    """
    Comprehensive bot decision with ALL fields for full transparency.

    This is the main data structure that captures everything about a decision.
    """
    # IDENTIFICATION
    bot_name: str  # LAZARUS, CORNERSTONE, FORTRESS, SHEPHERD, PROPHET
    decision_type: str  # ENTRY, EXIT, SKIP, ADJUSTMENT
    action: str  # BUY, SELL, HOLD
    symbol: str = "SPY"
    strategy: str = ""

    # SIGNAL SOURCE & OVERRIDE TRACKING
    # Captures where the signal came from and if any override happened
    # Examples: "ML", "Prophet", "Prophet (override ML)", "ML+Prophet", "Manual"
    signal_source: str = ""
    # If True, trade was made despite one signal saying SKIP
    override_occurred: bool = False
    # Detailed override info: {"overridden_signal": "ML", "overridden_advice": "STAY_OUT",
    #                         "override_reason": "Prophet high confidence", "override_confidence": 0.85}
    override_details: Dict[str, Any] = field(default_factory=dict)

    # TRADE DETAILS
    strike: float = 0.0
    expiration: Optional[str] = None  # YYYY-MM-DD
    option_type: str = ""  # CALL, PUT
    contracts: int = 0

    # SESSION TRACKING
    session_id: str = ""  # e.g., "2024-12-12-AM"
    scan_cycle: int = 0
    decision_sequence: int = 0

    # MARKET CONTEXT
    market_context: MarketContext = field(default_factory=MarketContext)

    # CLAUDE AI (full transparency)
    claude_context: ClaudeContext = field(default_factory=ClaudeContext)

    # REASONING BREAKDOWN
    entry_reasoning: str = ""
    strike_reasoning: str = ""
    size_reasoning: str = ""
    exit_reasoning: str = ""

    # ALTERNATIVES
    alternatives_considered: List[Alternative] = field(default_factory=list)
    other_strategies_considered: List[str] = field(default_factory=list)

    # PSYCHOLOGY/PATTERNS
    psychology_pattern: str = ""
    liberation_setup: bool = False
    false_floor_detected: bool = False
    forward_magnets: Dict[str, float] = field(default_factory=dict)

    # POSITION SIZING
    kelly_pct: float = 0.0
    position_size_dollars: float = 0.0
    max_risk_dollars: float = 0.0

    # BACKTEST REFERENCE
    backtest_win_rate: float = 0.0
    backtest_expectancy: float = 0.0
    backtest_sharpe: float = 0.0

    # RISK CHECKS
    risk_checks: List[RiskCheck] = field(default_factory=list)
    passed_all_checks: bool = True
    blocked_reason: str = ""

    # EXECUTION TIMELINE
    execution: ExecutionTimeline = field(default_factory=ExecutionTimeline)

    # OUTCOME (filled later via update_outcome)
    actual_pnl: float = 0.0
    exit_triggered_by: str = ""
    exit_timestamp: Optional[datetime] = None
    exit_price: float = 0.0
    exit_slippage_pct: float = 0.0
    outcome_correct: bool = False
    outcome_notes: str = ""

    # DEBUGGING
    api_calls: List[ApiCall] = field(default_factory=list)
    errors_encountered: List[Dict] = field(default_factory=list)
    processing_time_ms: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON storage"""
        return {
            "bot_name": self.bot_name,
            "decision_type": self.decision_type,
            "action": self.action,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "strike": self.strike,
            "expiration": self.expiration,
            "option_type": self.option_type,
            "contracts": self.contracts,
            "session_id": self.session_id,
            "scan_cycle": self.scan_cycle,
            "decision_sequence": self.decision_sequence,
            "market_context": self.market_context.to_dict(),
            "claude_context": self.claude_context.to_dict(),
            "entry_reasoning": self.entry_reasoning,
            "strike_reasoning": self.strike_reasoning,
            "size_reasoning": self.size_reasoning,
            "exit_reasoning": self.exit_reasoning,
            "alternatives_considered": [a.to_dict() for a in self.alternatives_considered],
            "other_strategies_considered": self.other_strategies_considered,
            "psychology_pattern": self.psychology_pattern,
            "liberation_setup": self.liberation_setup,
            "false_floor_detected": self.false_floor_detected,
            "forward_magnets": self.forward_magnets,
            "kelly_pct": self.kelly_pct,
            "position_size_dollars": self.position_size_dollars,
            "max_risk_dollars": self.max_risk_dollars,
            "backtest_win_rate": self.backtest_win_rate,
            "backtest_expectancy": self.backtest_expectancy,
            "backtest_sharpe": self.backtest_sharpe,
            "risk_checks": [r.to_dict() for r in self.risk_checks],
            "passed_all_checks": self.passed_all_checks,
            "blocked_reason": self.blocked_reason,
            "execution": self.execution.to_dict(),
            "actual_pnl": self.actual_pnl,
            "exit_triggered_by": self.exit_triggered_by,
            "exit_timestamp": self.exit_timestamp.isoformat() if self.exit_timestamp and hasattr(self.exit_timestamp, 'isoformat') else self.exit_timestamp,
            "exit_price": self.exit_price,
            "exit_slippage_pct": self.exit_slippage_pct,
            "outcome_correct": self.outcome_correct,
            "outcome_notes": self.outcome_notes,
            "api_calls": [a.to_dict() for a in self.api_calls],
            "errors_encountered": self.errors_encountered,
            "processing_time_ms": self.processing_time_ms
        }


def generate_decision_id(bot_name: str) -> str:
    """Generate unique decision ID"""
    timestamp = datetime.now(CENTRAL_TZ).strftime("%Y%m%d%H%M%S")
    unique = str(uuid.uuid4())[:8]
    return f"{bot_name}-{timestamp}-{unique}"


def generate_session_id() -> str:
    """Generate session ID based on current date and time"""
    now = datetime.now(CENTRAL_TZ)
    period = "AM" if now.hour < 12 else "PM"
    return f"{now.strftime('%Y-%m-%d')}-{period}"


class SessionTracker:
    """
    Track scan_cycle and decision_sequence within a trading session.

    Usage:
        tracker = get_session_tracker("FORTRESS")
        tracker.new_cycle()  # Start a new scan cycle (scan_cycle += 1)
        scan = tracker.current_cycle
        seq = tracker.next_decision()  # Get next decision_sequence

    Each bot should have its own tracker instance.
    """

    _instances: Dict[str, 'SessionTracker'] = {}

    def __init__(self, bot_name: str):
        self.bot_name = bot_name
        self._session_id = generate_session_id()
        self._scan_cycle = 0
        self._decision_sequence = 0
        self._last_reset = datetime.now(CENTRAL_TZ)

    @property
    def session_id(self) -> str:
        # Check if we need to roll over to a new session (e.g., new day or AM/PM switch)
        new_session = generate_session_id()
        if new_session != self._session_id:
            self._session_id = new_session
            self._scan_cycle = 0
            self._decision_sequence = 0
            self._last_reset = datetime.now(CENTRAL_TZ)
        return self._session_id

    @property
    def current_cycle(self) -> int:
        return self._scan_cycle

    def new_cycle(self) -> int:
        """Start a new scan cycle. Returns the new cycle number."""
        # Ensure session is current
        _ = self.session_id
        self._scan_cycle += 1
        self._decision_sequence = 0
        return self._scan_cycle

    def next_decision(self) -> int:
        """Get the next decision sequence number for the current cycle."""
        # Ensure session is current
        _ = self.session_id
        if self._scan_cycle == 0:
            self._scan_cycle = 1  # Auto-start first cycle
        self._decision_sequence += 1
        return self._decision_sequence


def get_session_tracker(bot_name: str) -> SessionTracker:
    """Get or create a session tracker for a bot."""
    if bot_name not in SessionTracker._instances:
        SessionTracker._instances[bot_name] = SessionTracker(bot_name)
    return SessionTracker._instances[bot_name]


class DecisionTracker:
    """
    Track API calls, errors, and processing time for a single decision.

    Usage:
        tracker = DecisionTracker()
        tracker.start()  # Start timing

        # Track API calls
        with tracker.track_api("tradier", "quotes"):
            data = tradier.get_quotes(...)

        # Track errors
        try:
            risky_operation()
        except Exception as e:
            tracker.add_error(str(e), "risky_operation")

        # Get results
        decision.api_calls = tracker.api_calls
        decision.errors_encountered = tracker.errors
        decision.processing_time_ms = tracker.elapsed_ms
    """

    def __init__(self):
        self._start_time: Optional[float] = None
        self._api_calls: List[ApiCall] = []
        self._errors: List[Dict[str, Any]] = []

    def start(self):
        """Start timing the decision process"""
        self._start_time = time.time()

    @property
    def elapsed_ms(self) -> int:
        """Get elapsed time since start() in milliseconds"""
        if self._start_time is None:
            return 0
        return int((time.time() - self._start_time) * 1000)

    @property
    def api_calls(self) -> List[ApiCall]:
        return self._api_calls

    @property
    def errors(self) -> List[Dict[str, Any]]:
        return self._errors

    def track_api(self, api_name: str, endpoint: str):
        """Context manager to track an API call"""
        return _ApiCallTracker(self, api_name, endpoint)

    def add_api_call(self, api_name: str, endpoint: str, time_ms: int, success: bool = True, error: str = ""):
        """Manually add an API call record"""
        self._api_calls.append(ApiCall(
            api_name=api_name,
            endpoint=endpoint,
            time_ms=time_ms,
            success=success,
            error=error
        ))

    def add_error(self, error: str, context: str = "", retried: bool = False, resolved: bool = False):
        """Add an error record"""
        self._errors.append({
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "error": error,
            "context": context,
            "retried": retried,
            "resolved": resolved
        })


class _ApiCallTracker:
    """Context manager for tracking API call timing"""

    def __init__(self, parent: DecisionTracker, api_name: str, endpoint: str):
        self._parent = parent
        self._api_name = api_name
        self._endpoint = endpoint
        self._start: float = 0
        self._error: str = ""

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = int((time.time() - self._start) * 1000)
        success = exc_type is None
        error = str(exc_val) if exc_val else ""

        self._parent.add_api_call(
            self._api_name,
            self._endpoint,
            elapsed_ms,
            success,
            error
        )
        return False  # Don't suppress exceptions


def log_bot_decision(decision: BotDecision) -> Optional[str]:
    """
    Log a comprehensive bot decision to the bot_decision_logs table.

    This is THE central logging function that all bots should use.
    It captures EVERYTHING for full transparency.

    Args:
        decision: BotDecision object with all details

    Returns:
        decision_id if successful, None if failed

    Note: Includes numpy type conversion to prevent database errors.
    """
    # Helper to convert numpy types to Python native types
    def _convert_numpy(val):
        try:
            import numpy as np
            if isinstance(val, (np.integer, np.int64, np.int32)):
                return int(val)
            elif isinstance(val, (np.floating, np.float64, np.float32)):
                return float(val)
            elif isinstance(val, np.bool_):
                return bool(val)
            elif isinstance(val, np.ndarray):
                return val.tolist()
        except ImportError:
            pass
        return val

    def _convert_dict_numpy(d):
        if d is None:
            return None
        if isinstance(d, dict):
            return {k: _convert_dict_numpy(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [_convert_dict_numpy(item) for item in d]
        return _convert_numpy(d)

    decision_id = generate_decision_id(decision.bot_name)

    # Auto-generate session_id if not provided
    if not decision.session_id:
        decision.session_id = generate_session_id()

    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO bot_decision_logs (
                decision_id, bot_name, session_id, scan_cycle, decision_sequence,
                decision_type, action, symbol, strategy,
                signal_source, override_occurred, override_details,
                strike, expiration, option_type, contracts,
                spot_price, vix, net_gex, gex_regime, flip_point, call_wall, put_wall, trend,
                claude_prompt, claude_response, claude_model, claude_tokens_used, claude_response_time_ms,
                langchain_chain, ai_confidence, ai_warnings,
                entry_reasoning, strike_reasoning, size_reasoning, exit_reasoning,
                alternatives_considered, rejection_reasons, other_strategies_considered,
                psychology_pattern, liberation_setup, false_floor_detected, forward_magnets,
                kelly_pct, position_size_dollars, max_risk_dollars,
                backtest_win_rate, backtest_expectancy, backtest_sharpe,
                risk_checks_performed, passed_all_checks, blocked_reason,
                order_submitted_at, order_filled_at, broker_order_id,
                expected_fill_price, actual_fill_price, slippage_pct, broker_status, execution_notes,
                api_calls_made, errors_encountered, processing_time_ms,
                full_decision
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s
            )
            RETURNING decision_id
        """, (
            decision_id, decision.bot_name, decision.session_id, _convert_numpy(decision.scan_cycle), _convert_numpy(decision.decision_sequence),
            decision.decision_type, decision.action, decision.symbol, decision.strategy,
            decision.signal_source, decision.override_occurred, json.dumps(_convert_dict_numpy(decision.override_details)),
            _convert_numpy(decision.strike), decision.expiration, decision.option_type, _convert_numpy(decision.contracts),
            _convert_numpy(decision.market_context.spot_price), _convert_numpy(decision.market_context.vix), _convert_numpy(decision.market_context.net_gex),
            decision.market_context.gex_regime, _convert_numpy(decision.market_context.flip_point),
            _convert_numpy(decision.market_context.call_wall), _convert_numpy(decision.market_context.put_wall), decision.market_context.trend,
            decision.claude_context.prompt, decision.claude_context.response, decision.claude_context.model,
            _convert_numpy(decision.claude_context.tokens_used), _convert_numpy(decision.claude_context.response_time_ms),
            decision.claude_context.chain_name, decision.claude_context.confidence,
            json.dumps(_convert_dict_numpy(decision.claude_context.warnings)),
            decision.entry_reasoning, decision.strike_reasoning, decision.size_reasoning, decision.exit_reasoning,
            json.dumps(_convert_dict_numpy([a.to_dict() for a in decision.alternatives_considered])),
            json.dumps({}),  # rejection_reasons
            json.dumps(_convert_dict_numpy(decision.other_strategies_considered)),
            decision.psychology_pattern, decision.liberation_setup, decision.false_floor_detected,
            json.dumps(_convert_dict_numpy(decision.forward_magnets)),
            _convert_numpy(decision.kelly_pct), _convert_numpy(decision.position_size_dollars), _convert_numpy(decision.max_risk_dollars),
            _convert_numpy(decision.backtest_win_rate), _convert_numpy(decision.backtest_expectancy), _convert_numpy(decision.backtest_sharpe),
            json.dumps(_convert_dict_numpy([r.to_dict() for r in decision.risk_checks])),
            decision.passed_all_checks, decision.blocked_reason,
            decision.execution.order_submitted_at, decision.execution.order_filled_at,
            decision.execution.broker_order_id, _convert_numpy(decision.execution.expected_fill_price),
            _convert_numpy(decision.execution.actual_fill_price), _convert_numpy(decision.execution.slippage_pct),
            decision.execution.broker_status, decision.execution.execution_notes,
            json.dumps(_convert_dict_numpy([a.to_dict() for a in decision.api_calls])),
            json.dumps(_convert_dict_numpy(decision.errors_encountered)),
            _convert_numpy(decision.processing_time_ms),
            json.dumps(_convert_dict_numpy(decision.to_dict()))
        ))

        result = c.fetchone()
        conn.commit()
        conn.close()

        return result[0] if result else decision_id

    except Exception as e:
        print(f"Error logging bot decision: {e}")
        return None


def update_decision_outcome(
    decision_id: str,
    actual_pnl: float,
    exit_triggered_by: str,
    exit_price: float,
    exit_slippage_pct: float = 0.0,
    outcome_correct: bool = False,
    outcome_notes: str = ""
) -> bool:
    """
    Update a decision with its outcome after the trade closes.

    Args:
        decision_id: The decision to update
        actual_pnl: Realized P&L
        exit_triggered_by: What caused the exit (PROFIT_TARGET, STOP_LOSS, etc.)
        exit_price: Price at exit
        exit_slippage_pct: Slippage on exit
        outcome_correct: Was the decision correct?
        outcome_notes: Any notes about the outcome

    Returns:
        True if updated successfully
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            UPDATE bot_decision_logs
            SET actual_pnl = %s,
                exit_triggered_by = %s,
                exit_timestamp = NOW(),
                exit_price = %s,
                exit_slippage_pct = %s,
                outcome_correct = %s,
                outcome_notes = %s,
                updated_at = NOW()
            WHERE decision_id = %s
        """, (
            actual_pnl,
            exit_triggered_by,
            exit_price,
            exit_slippage_pct,
            outcome_correct,
            outcome_notes,
            decision_id
        ))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"Error updating decision outcome: {e}")
        return False


def update_execution_timeline(
    decision_id: str,
    order_submitted_at: datetime = None,
    order_filled_at: datetime = None,
    broker_order_id: str = "",
    actual_fill_price: float = 0.0,
    broker_status: str = "",
    execution_notes: str = ""
) -> bool:
    """
    Update execution timeline for a decision.

    Call this when order is submitted, then again when filled.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        updates = []
        params = []

        if order_submitted_at:
            updates.append("order_submitted_at = %s")
            params.append(order_submitted_at)

        if order_filled_at:
            updates.append("order_filled_at = %s")
            params.append(order_filled_at)

        if broker_order_id:
            updates.append("broker_order_id = %s")
            params.append(broker_order_id)

        if actual_fill_price > 0:
            updates.append("actual_fill_price = %s")
            params.append(actual_fill_price)
            # Calculate slippage
            c.execute("SELECT expected_fill_price FROM bot_decision_logs WHERE decision_id = %s", (decision_id,))
            row = c.fetchone()
            if row and row[0]:
                slippage = ((actual_fill_price - row[0]) / row[0]) * 100
                updates.append("slippage_pct = %s")
                params.append(slippage)

        if broker_status:
            updates.append("broker_status = %s")
            params.append(broker_status)

        if execution_notes:
            updates.append("execution_notes = %s")
            params.append(execution_notes)

        updates.append("updated_at = NOW()")
        params.append(decision_id)

        c.execute(f"""
            UPDATE bot_decision_logs
            SET {', '.join(updates)}
            WHERE decision_id = %s
        """, tuple(params))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"Error updating execution timeline: {e}")
        return False


def log_error(decision_id: str, error: str, retried: bool = False, resolved: bool = False) -> bool:
    """
    Add an error to an existing decision's error log.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get existing errors
        c.execute("SELECT errors_encountered FROM bot_decision_logs WHERE decision_id = %s", (decision_id,))
        row = c.fetchone()

        errors = json.loads(row[0]) if row and row[0] else []
        errors.append({
            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
            "error": error,
            "retried": retried,
            "resolved": resolved
        })

        c.execute("""
            UPDATE bot_decision_logs
            SET errors_encountered = %s, updated_at = NOW()
            WHERE decision_id = %s
        """, (json.dumps(errors), decision_id))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"Error logging error: {e}")
        return False


def get_recent_bot_decisions(
    bot_name: str = None,
    limit: int = 50,
    decision_type: str = None,
    session_id: str = None
) -> List[Dict]:
    """
    Get recent decisions for a bot.

    Args:
        bot_name: Filter by bot (None for all)
        limit: Number of records
        decision_type: Filter by type (ENTRY, EXIT, etc.)
        session_id: Filter by session

    Returns:
        List of decision dictionaries
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        conditions = []
        params = []

        if bot_name:
            conditions.append("bot_name = %s")
            params.append(bot_name)

        if decision_type:
            conditions.append("decision_type = %s")
            params.append(decision_type)

        if session_id:
            conditions.append("session_id = %s")
            params.append(session_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        c.execute(f"""
            SELECT
                decision_id, bot_name, session_id, scan_cycle, decision_sequence,
                timestamp, decision_type, action, symbol, strategy,
                strike, expiration, option_type, contracts,
                spot_price, vix, net_gex, gex_regime,
                claude_prompt, claude_response, claude_model, claude_tokens_used,
                entry_reasoning, strike_reasoning, size_reasoning,
                alternatives_considered, psychology_pattern,
                position_size_dollars, passed_all_checks, blocked_reason,
                order_submitted_at, order_filled_at, actual_fill_price, slippage_pct,
                actual_pnl, exit_triggered_by, outcome_notes,
                errors_encountered, processing_time_ms
            FROM bot_decision_logs
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT %s
        """, tuple(params))

        columns = [desc[0] for desc in c.description]
        decisions = []

        for row in c.fetchall():
            decisions.append(dict(zip(columns, row)))

        conn.close()
        return decisions

    except Exception as e:
        print(f"Error getting recent decisions: {e}")
        return []


def get_session_decisions(session_id: str) -> List[Dict]:
    """
    Get all decisions from a specific session, grouped together.
    """
    return get_recent_bot_decisions(session_id=session_id, limit=100)


# Convenience functions for each bot
def get_ares_logger():
    """Get a pre-configured logger for FORTRESS"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "FORTRESS" else None


def get_atlas_logger():
    """Get a pre-configured logger for CORNERSTONE"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "CORNERSTONE" else None


def get_phoenix_logger():
    """Get a pre-configured logger for LAZARUS"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "LAZARUS" else None


def get_hermes_logger():
    """Get a pre-configured logger for SHEPHERD"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "SHEPHERD" else None


def get_oracle_logger():
    """Get a pre-configured logger for PROPHET"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "PROPHET" else None


def get_solomon_logger():
    """Get a pre-configured logger for SOLOMON"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "SOLOMON" else None


def get_anchor_logger():
    """Get a pre-configured logger for ANCHOR"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "ANCHOR" else None


def get_icarus_logger():
    """Get a pre-configured logger for GIDEON"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "GIDEON" else None


def get_titan_logger():
    """Get a pre-configured logger for SAMSON"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "SAMSON" else None


def get_prometheus_logger():
    """Get a pre-configured logger for JUBILEE"""
    return lambda decision: log_bot_decision(decision) if decision.bot_name == "JUBILEE" else None
