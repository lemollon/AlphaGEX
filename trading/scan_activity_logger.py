"""
Scan Activity Logger - Comprehensive logging for EVERY bot scan

This module provides complete visibility into what each trading bot is doing
on every single scan. No more mystery - you'll see exactly:

1. WHEN the scan happened
2. WHAT market conditions were observed
3. WHAT signals were generated
4. WHY a trade was or wasn't taken
5. WHAT checks were performed and their results

Usage:
    from trading.scan_activity_logger import log_scan_activity, ScanOutcome

    # Log every scan - whether it trades or not
    log_scan_activity(
        bot_name="ARES",
        outcome=ScanOutcome.NO_TRADE,
        decision_summary="Oracle confidence too low (45%)",
        market_data={"underlying_price": 5980, "vix": 18.5},
        ...
    )
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Texas Central Time
CENTRAL_TZ = ZoneInfo("America/Chicago")


class ScanOutcome(Enum):
    """Possible outcomes of a scan"""
    TRADED = "TRADED"                    # Trade was executed
    NO_TRADE = "NO_TRADE"               # Scan complete, no trade (conditions not met)
    SKIP = "SKIP"                       # Skipped intentionally (already traded, etc.)
    ERROR = "ERROR"                     # Error occurred during scan
    MARKET_CLOSED = "MARKET_CLOSED"     # Market is closed
    BEFORE_WINDOW = "BEFORE_WINDOW"     # Before trading window
    AFTER_WINDOW = "AFTER_WINDOW"       # After trading window
    UNAVAILABLE = "UNAVAILABLE"         # Bot/service unavailable


@dataclass
class CheckResult:
    """Result of a single check performed during scan"""
    check_name: str
    passed: bool
    value: str = ""
    threshold: str = ""
    reason: str = ""


@dataclass
class ScanActivity:
    """Complete record of a scan"""
    # Identification
    bot_name: str
    scan_id: str
    scan_number: int

    # Timing
    timestamp: datetime
    date: str
    time_ct: str

    # Outcome
    outcome: ScanOutcome
    action_taken: str
    decision_summary: str
    full_reasoning: str = ""

    # Market conditions
    underlying_price: float = 0
    underlying_symbol: str = ""
    vix: float = 0
    expected_move: float = 0

    # GEX context
    gex_regime: str = ""
    net_gex: float = 0
    call_wall: float = 0
    put_wall: float = 0
    distance_to_call_wall_pct: float = 0
    distance_to_put_wall_pct: float = 0

    # Signals
    signal_source: str = ""
    signal_direction: str = ""
    signal_confidence: float = 0
    signal_win_probability: float = 0

    # Oracle
    oracle_advice: str = ""
    oracle_reasoning: str = ""

    # Checks
    checks_performed: List[CheckResult] = field(default_factory=list)
    all_checks_passed: bool = True

    # Trade details
    trade_executed: bool = False
    position_id: str = ""
    strike_selection: Dict = field(default_factory=dict)
    contracts: int = 0
    premium_collected: float = 0
    max_risk: float = 0

    # Error
    error_message: str = ""
    error_type: str = ""

    # Full context
    full_context: Dict = field(default_factory=dict)


# Counter for scan IDs
_scan_counters: Dict[str, int] = {}


def _generate_scan_id(bot_name: str) -> str:
    """Generate unique scan ID"""
    global _scan_counters
    if bot_name not in _scan_counters:
        _scan_counters[bot_name] = 0
    _scan_counters[bot_name] += 1

    now = datetime.now(CENTRAL_TZ)
    return f"{bot_name}-{now.strftime('%Y%m%d-%H%M%S')}-{_scan_counters[bot_name]:04d}"


def _get_scan_number_today(bot_name: str) -> int:
    """Get the scan number for today from database"""
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        today = datetime.now(CENTRAL_TZ).date()
        c.execute("""
            SELECT COALESCE(MAX(scan_number), 0) + 1
            FROM scan_activity
            WHERE bot_name = %s AND date = %s
        """, (bot_name, today))

        result = c.fetchone()
        conn.close()
        return result[0] if result else 1
    except Exception as e:
        logger.debug(f"Could not get scan number: {e}")
        return _scan_counters.get(bot_name, 0) + 1


def log_scan_activity(
    bot_name: str,
    outcome: ScanOutcome,
    decision_summary: str,
    action_taken: str = "",
    full_reasoning: str = "",
    # Market data
    market_data: Optional[Dict] = None,
    # GEX data
    gex_data: Optional[Dict] = None,
    # Signal data
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    # Oracle data
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    # Risk/Reward
    risk_reward_ratio: float = 0,
    # Checks
    checks: Optional[List[CheckResult]] = None,
    # Trade data
    trade_executed: bool = False,
    position_id: str = "",
    strike_selection: Optional[Dict] = None,
    contracts: int = 0,
    premium_collected: float = 0,
    max_risk: float = 0,
    # Error
    error_message: str = "",
    error_type: str = "",
    # Claude AI explanations
    what_would_trigger: str = "",
    market_insight: str = "",
    # Additional context
    full_context: Optional[Dict] = None,
    # Generate AI explanation
    generate_ai_explanation: bool = True
) -> Optional[str]:
    """
    Log a scan activity to the database.

    This should be called on EVERY scan, regardless of outcome.

    Args:
        bot_name: Name of the bot (ARES, ATHENA)
        outcome: What happened (TRADED, NO_TRADE, ERROR, etc.)
        decision_summary: One-line human-readable summary
        action_taken: What action was taken (if any)
        full_reasoning: Detailed reasoning for the decision
        market_data: Current market conditions
        gex_data: GEX context if available
        signal_source: Where the signal came from (ML, Oracle, etc.)
        signal_direction: BULLISH, BEARISH, NEUTRAL
        signal_confidence: 0-1 confidence score
        signal_win_probability: 0-1 win probability
        oracle_advice: What Oracle recommended
        oracle_reasoning: Why Oracle made that recommendation
        checks: List of checks performed
        trade_executed: Whether a trade was executed
        position_id: Position ID if traded
        strike_selection: Strike details if traded
        contracts: Number of contracts traded
        premium_collected: Premium collected
        max_risk: Maximum risk
        error_message: Error message if error occurred
        error_type: Type of error
        full_context: Additional context as JSON

    Returns:
        scan_id if logged successfully, None otherwise
    """
    try:
        from database_adapter import get_connection

        now = datetime.now(CENTRAL_TZ)
        scan_id = _generate_scan_id(bot_name)
        scan_number = _get_scan_number_today(bot_name)

        # Extract market data
        underlying_price = 0
        underlying_symbol = ""
        vix = 0
        expected_move = 0

        if market_data:
            underlying_price = market_data.get('underlying_price', 0) or market_data.get('spot_price', 0)
            underlying_symbol = market_data.get('symbol', '') or market_data.get('ticker', '')
            vix = market_data.get('vix', 0)
            expected_move = market_data.get('expected_move', 0)

        # Extract GEX data
        gex_regime = ""
        net_gex = 0
        call_wall = 0
        put_wall = 0
        distance_to_call_wall_pct = 0
        distance_to_put_wall_pct = 0

        if gex_data:
            gex_regime = gex_data.get('regime', '') or gex_data.get('gex_regime', '')
            net_gex = gex_data.get('net_gex', 0)
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)

            # Calculate distances if we have spot price
            spot = underlying_price or gex_data.get('spot_price', 0)
            if spot and call_wall:
                distance_to_call_wall_pct = ((call_wall - spot) / spot) * 100
            if spot and put_wall:
                distance_to_put_wall_pct = ((spot - put_wall) / spot) * 100

        # Convert checks to JSON
        checks_json = []
        all_checks_passed = True
        if checks:
            for check in checks:
                if isinstance(check, CheckResult):
                    checks_json.append(asdict(check))
                    if not check.passed:
                        all_checks_passed = False
                elif isinstance(check, dict):
                    checks_json.append(check)
                    if not check.get('passed', True):
                        all_checks_passed = False

        # Build full context
        context = full_context or {}
        context['market_data'] = market_data
        context['gex_data'] = gex_data

        conn = get_connection()
        c = conn.cursor()

        # Ensure table exists with all columns
        c.execute("""
            CREATE TABLE IF NOT EXISTS scan_activity (
                id SERIAL PRIMARY KEY,
                bot_name VARCHAR(50) NOT NULL,
                scan_id VARCHAR(100) NOT NULL UNIQUE,
                scan_number INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                date DATE NOT NULL,
                time_ct VARCHAR(20) NOT NULL,
                outcome VARCHAR(50) NOT NULL,
                action_taken VARCHAR(100),
                decision_summary TEXT NOT NULL,
                full_reasoning TEXT,
                underlying_price DECIMAL(15, 4),
                underlying_symbol VARCHAR(10),
                vix DECIMAL(10, 4),
                expected_move DECIMAL(10, 4),
                gex_regime VARCHAR(50),
                net_gex DECIMAL(20, 2),
                call_wall DECIMAL(15, 4),
                put_wall DECIMAL(15, 4),
                distance_to_call_wall_pct DECIMAL(10, 4),
                distance_to_put_wall_pct DECIMAL(10, 4),
                signal_source VARCHAR(50),
                signal_direction VARCHAR(20),
                signal_confidence DECIMAL(5, 4),
                signal_win_probability DECIMAL(5, 4),
                oracle_advice VARCHAR(50),
                oracle_reasoning TEXT,
                risk_reward_ratio DECIMAL(10, 4),
                checks_performed JSONB,
                all_checks_passed BOOLEAN DEFAULT TRUE,
                trade_executed BOOLEAN DEFAULT FALSE,
                position_id VARCHAR(100),
                strike_selection JSONB,
                contracts INTEGER,
                premium_collected DECIMAL(15, 4),
                max_risk DECIMAL(15, 4),
                error_message TEXT,
                error_type VARCHAR(100),
                what_would_trigger TEXT,
                market_insight TEXT,
                full_context JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add new columns if they don't exist (for existing tables)
        try:
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS risk_reward_ratio DECIMAL(10, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS what_would_trigger TEXT")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS market_insight TEXT")
        except Exception:
            pass  # Columns may already exist

        # Generate Claude AI explanation if enabled and market data available
        ai_what_trigger = what_would_trigger
        ai_market_insight = market_insight

        if generate_ai_explanation and market_data and not ai_what_trigger:
            try:
                from trading.scan_explainer import generate_scan_explanation, ScanContext, MarketContext, SignalContext, CheckDetail, DecisionType

                # Build context for Claude
                check_details = []
                if checks:
                    for check in checks:
                        if isinstance(check, CheckResult):
                            check_details.append(CheckDetail(
                                name=check.check_name,
                                passed=check.passed,
                                actual_value=check.value,
                                required_value=check.threshold,
                                explanation=check.reason
                            ))

                scan_ctx = ScanContext(
                    bot_name=bot_name,
                    scan_number=scan_number,
                    decision_type=DecisionType(outcome.value),
                    market=MarketContext(
                        underlying_symbol=underlying_symbol or "SPY",
                        underlying_price=underlying_price,
                        vix=vix,
                        expected_move=expected_move,
                        net_gex=net_gex,
                        gex_regime=gex_regime,
                        call_wall=call_wall,
                        put_wall=put_wall,
                        distance_to_call_wall_pct=distance_to_call_wall_pct,
                        distance_to_put_wall_pct=distance_to_put_wall_pct
                    ),
                    signal=SignalContext(
                        source=signal_source or "None",
                        direction=signal_direction or "NONE",
                        confidence=signal_confidence,
                        win_probability=signal_win_probability,
                        advice=oracle_advice,
                        reasoning=oracle_reasoning
                    ) if signal_source else None,
                    checks=check_details if check_details else None,
                    error_message=error_message
                )

                explanation = generate_scan_explanation(scan_ctx)
                ai_what_trigger = explanation.get('what_would_trigger', '')
                ai_market_insight = explanation.get('market_insight', '')

                # Use Claude's full explanation if we don't have one
                if not full_reasoning and explanation.get('full_explanation'):
                    full_reasoning = explanation.get('full_explanation', '')

            except Exception as e:
                logger.debug(f"Could not generate Claude explanation: {e}")

        # Insert scan activity
        c.execute("""
            INSERT INTO scan_activity (
                bot_name, scan_id, scan_number,
                timestamp, date, time_ct,
                outcome, action_taken, decision_summary, full_reasoning,
                underlying_price, underlying_symbol, vix, expected_move,
                gex_regime, net_gex, call_wall, put_wall,
                distance_to_call_wall_pct, distance_to_put_wall_pct,
                signal_source, signal_direction, signal_confidence, signal_win_probability,
                oracle_advice, oracle_reasoning,
                risk_reward_ratio,
                checks_performed, all_checks_passed,
                trade_executed, position_id, strike_selection, contracts,
                premium_collected, max_risk,
                error_message, error_type,
                what_would_trigger, market_insight,
                full_context
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s
            )
        """, (
            bot_name, scan_id, scan_number,
            now, now.date(), now.strftime('%I:%M:%S %p'),
            outcome.value, action_taken, decision_summary, full_reasoning,
            underlying_price, underlying_symbol, vix, expected_move,
            gex_regime, net_gex, call_wall, put_wall,
            distance_to_call_wall_pct, distance_to_put_wall_pct,
            signal_source, signal_direction, signal_confidence, signal_win_probability,
            oracle_advice, oracle_reasoning,
            risk_reward_ratio,
            json.dumps(checks_json) if checks_json else None, all_checks_passed,
            trade_executed, position_id, json.dumps(strike_selection) if strike_selection else None, contracts,
            premium_collected, max_risk,
            error_message, error_type,
            ai_what_trigger, ai_market_insight,
            json.dumps(context)
        ))

        conn.commit()
        conn.close()

        logger.info(f"[{bot_name}] Scan #{scan_number} logged: {outcome.value} - {decision_summary}")
        return scan_id

    except Exception as e:
        logger.error(f"Failed to log scan activity: {e}")
        return None


def get_recent_scans(
    bot_name: Optional[str] = None,
    limit: int = 50,
    date: Optional[str] = None,
    outcome: Optional[str] = None
) -> List[Dict]:
    """
    Get recent scan activity.

    Args:
        bot_name: Filter by bot name (optional)
        limit: Maximum records to return
        date: Filter by date (YYYY-MM-DD)
        outcome: Filter by outcome (TRADED, NO_TRADE, etc.)

    Returns:
        List of scan activity records
    """
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Build query
        query = """
            SELECT
                id, bot_name, scan_id, scan_number,
                timestamp, date, time_ct,
                outcome, action_taken, decision_summary, full_reasoning,
                underlying_price, underlying_symbol, vix, expected_move,
                gex_regime, net_gex, call_wall, put_wall,
                distance_to_call_wall_pct, distance_to_put_wall_pct,
                signal_source, signal_direction, signal_confidence, signal_win_probability,
                oracle_advice, oracle_reasoning,
                risk_reward_ratio,
                checks_performed, all_checks_passed,
                trade_executed, position_id, strike_selection, contracts,
                premium_collected, max_risk,
                error_message, error_type,
                what_would_trigger, market_insight
            FROM scan_activity
            WHERE 1=1
        """
        params = []

        if bot_name:
            query += " AND bot_name = %s"
            params.append(bot_name)

        if date:
            query += " AND date = %s"
            params.append(date)

        if outcome:
            query += " AND outcome = %s"
            params.append(outcome)

        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        c.execute(query, params)

        columns = [
            'id', 'bot_name', 'scan_id', 'scan_number',
            'timestamp', 'date', 'time_ct',
            'outcome', 'action_taken', 'decision_summary', 'full_reasoning',
            'underlying_price', 'underlying_symbol', 'vix', 'expected_move',
            'gex_regime', 'net_gex', 'call_wall', 'put_wall',
            'distance_to_call_wall_pct', 'distance_to_put_wall_pct',
            'signal_source', 'signal_direction', 'signal_confidence', 'signal_win_probability',
            'oracle_advice', 'oracle_reasoning',
            'risk_reward_ratio',
            'checks_performed', 'all_checks_passed',
            'trade_executed', 'position_id', 'strike_selection', 'contracts',
            'premium_collected', 'max_risk',
            'error_message', 'error_type',
            'what_would_trigger', 'market_insight'
        ]

        results = []
        for row in c.fetchall():
            record = dict(zip(columns, row))
            # Convert timestamp to ISO string
            if record.get('timestamp'):
                record['timestamp'] = record['timestamp'].isoformat()
            if record.get('date'):
                record['date'] = str(record['date'])
            # Convert Decimal to float for JSON
            for key in ['underlying_price', 'vix', 'expected_move', 'net_gex',
                        'call_wall', 'put_wall', 'distance_to_call_wall_pct',
                        'distance_to_put_wall_pct', 'signal_confidence',
                        'signal_win_probability', 'premium_collected', 'max_risk']:
                if record.get(key) is not None:
                    record[key] = float(record[key])
            results.append(record)

        conn.close()
        return results

    except Exception as e:
        logger.error(f"Failed to get recent scans: {e}")
        return []


def get_scan_summary(bot_name: Optional[str] = None, days: int = 7) -> Dict:
    """
    Get summary statistics for scan activity.

    Args:
        bot_name: Filter by bot name (optional)
        days: Number of days to include

    Returns:
        Summary statistics
    """
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        bot_filter = "AND bot_name = %s" if bot_name else ""
        params = [days]
        if bot_name:
            params.append(bot_name)

        c.execute(f"""
            SELECT
                COUNT(*) as total_scans,
                COUNT(CASE WHEN trade_executed THEN 1 END) as trades_executed,
                COUNT(CASE WHEN outcome = 'NO_TRADE' THEN 1 END) as no_trade_scans,
                COUNT(CASE WHEN outcome = 'ERROR' THEN 1 END) as error_scans,
                COUNT(CASE WHEN outcome = 'MARKET_CLOSED' THEN 1 END) as market_closed_scans,
                AVG(signal_confidence) as avg_confidence,
                AVG(vix) as avg_vix,
                MAX(timestamp) as last_scan
            FROM scan_activity
            WHERE timestamp >= NOW() - INTERVAL '%s days'
            {bot_filter}
        """, params)

        row = c.fetchone()
        conn.close()

        if row:
            return {
                'total_scans': row[0] or 0,
                'trades_executed': row[1] or 0,
                'no_trade_scans': row[2] or 0,
                'error_scans': row[3] or 0,
                'market_closed_scans': row[4] or 0,
                'avg_confidence': round(float(row[5] or 0), 3),
                'avg_vix': round(float(row[6] or 0), 2),
                'last_scan': row[7].isoformat() if row[7] else None
            }
        return {}

    except Exception as e:
        logger.error(f"Failed to get scan summary: {e}")
        return {}


# Convenience functions for specific bots with AI explanations
def log_ares_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    checks: Optional[List[CheckResult]] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    trade_executed: bool = False,
    error_message: str = "",
    generate_ai_explanation: bool = True,
    **kwargs
) -> Optional[str]:
    """
    Log ARES scan activity with optional Claude AI explanation.

    If generate_ai_explanation is True, uses Claude to create a detailed
    human-readable explanation of WHY this decision was made.
    """
    full_reasoning = kwargs.get('full_reasoning', '')

    # Generate AI explanation if requested and we have enough context
    if generate_ai_explanation and market_data:
        try:
            from trading.scan_explainer import explain_ares_decision

            # Convert checks to dict format
            checks_list = []
            if checks:
                for check in checks:
                    if isinstance(check, CheckResult):
                        checks_list.append({
                            'check_name': check.check_name,
                            'passed': check.passed,
                            'value': check.value,
                            'threshold': check.threshold,
                            'reason': check.reason
                        })
                    elif isinstance(check, dict):
                        checks_list.append(check)

            # Get scan number
            scan_number = _get_scan_number_today("ARES")

            # Get values from market/gex data
            underlying_price = market_data.get('underlying_price', 0) or market_data.get('spot_price', 0)
            vix = market_data.get('vix', 0)
            expected_move = market_data.get('expected_move', 0)

            net_gex = gex_data.get('net_gex', 0) if gex_data else 0
            call_wall = gex_data.get('call_wall', 0) if gex_data else 0
            put_wall = gex_data.get('put_wall', 0) if gex_data else 0

            # Build trade details if traded
            trade_details = None
            if trade_executed:
                trade_details = {
                    'strategy': 'Iron Condor',
                    'contracts': kwargs.get('contracts', 0),
                    'premium_collected': kwargs.get('premium_collected', 0),
                    'max_risk': kwargs.get('max_risk', 0)
                }

            # Generate explanation
            explanation = explain_ares_decision(
                scan_number=scan_number,
                outcome=outcome.value,
                underlying_price=underlying_price,
                vix=vix,
                checks=checks_list,
                signal_source=signal_source or None,
                signal_direction=signal_direction or None,
                signal_confidence=signal_confidence or None,
                signal_win_prob=signal_win_probability or None,
                oracle_advice=oracle_advice or None,
                oracle_reasoning=oracle_reasoning or None,
                expected_move=expected_move or None,
                net_gex=net_gex or None,
                call_wall=call_wall or None,
                put_wall=put_wall or None,
                trade_details=trade_details,
                error_message=error_message or None
            )

            # Use AI-generated summary and reasoning
            decision_summary = explanation.get('summary', decision_summary)
            full_reasoning = explanation.get('full_explanation', full_reasoning)

            logger.info(f"[ARES] AI explanation generated: {decision_summary}")

        except Exception as e:
            logger.warning(f"Failed to generate AI explanation for ARES: {e}")
            # Fall back to provided summary

    return log_scan_activity(
        bot_name="ARES",
        outcome=outcome,
        decision_summary=decision_summary,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        checks=checks,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        trade_executed=trade_executed,
        error_message=error_message,
        **kwargs
    )


def log_athena_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    checks: Optional[List[CheckResult]] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    risk_reward_ratio: float = 0,
    generate_ai_explanation: bool = True,
    **kwargs
) -> Optional[str]:
    """
    Log ATHENA scan activity with optional Claude AI explanation.

    If generate_ai_explanation is True, uses Claude to create a detailed
    human-readable explanation of WHY this decision was made.
    """
    full_reasoning = kwargs.get('full_reasoning', '')

    # Generate AI explanation if requested and we have enough context
    if generate_ai_explanation and market_data:
        try:
            from trading.scan_explainer import explain_athena_decision

            # Convert checks to dict format
            checks_list = []
            if checks:
                for check in checks:
                    if isinstance(check, CheckResult):
                        checks_list.append({
                            'check_name': check.check_name,
                            'passed': check.passed,
                            'value': check.value,
                            'threshold': check.threshold,
                            'reason': check.reason
                        })
                    elif isinstance(check, dict):
                        checks_list.append(check)

            # Get scan number
            scan_number = _get_scan_number_today("ATHENA")

            # Get values from market/gex data
            underlying_price = market_data.get('underlying_price', 0) or market_data.get('spot_price', 0)
            vix = market_data.get('vix', 0)

            net_gex = gex_data.get('net_gex', 0) if gex_data else 0
            gex_regime = gex_data.get('regime', '') if gex_data else ''
            call_wall = gex_data.get('call_wall', 0) if gex_data else 0
            put_wall = gex_data.get('put_wall', 0) if gex_data else 0

            # Build trade details if traded
            trade_details = None
            if trade_executed:
                trade_details = {
                    'strategy': kwargs.get('strategy', 'Directional Spread'),
                    'contracts': kwargs.get('contracts', 0),
                    'premium_collected': kwargs.get('premium_collected', 0),
                    'max_risk': kwargs.get('max_risk', 0)
                }

            # Generate explanation
            explanation = explain_athena_decision(
                scan_number=scan_number,
                outcome=outcome.value,
                underlying_price=underlying_price,
                vix=vix,
                checks=checks_list,
                signal_source=signal_source or None,
                signal_direction=signal_direction or None,
                signal_confidence=signal_confidence or None,
                signal_win_prob=signal_win_probability or None,
                net_gex=net_gex or None,
                gex_regime=gex_regime or None,
                call_wall=call_wall or None,
                put_wall=put_wall or None,
                risk_reward_ratio=risk_reward_ratio or None,
                trade_details=trade_details,
                error_message=error_message or None
            )

            # Use AI-generated summary and reasoning
            decision_summary = explanation.get('summary', decision_summary)
            full_reasoning = explanation.get('full_explanation', full_reasoning)

            logger.info(f"[ATHENA] AI explanation generated: {decision_summary}")

        except Exception as e:
            logger.warning(f"Failed to generate AI explanation for ATHENA: {e}")
            # Fall back to provided summary

    return log_scan_activity(
        bot_name="ATHENA",
        outcome=outcome,
        decision_summary=decision_summary,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        checks=checks,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        trade_executed=trade_executed,
        error_message=error_message,
        **kwargs
    )
