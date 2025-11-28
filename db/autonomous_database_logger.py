"""
Autonomous Trader Database Logger
Comprehensive logging of ALL decisions, reasoning, and outcomes

Every scan cycle logs:
- Market context
- Psychology trap analysis
- Strike selection reasoning
- Position sizing calculations
- AI thought process
- Trade decisions
- Outcomes
"""

from database_adapter import get_connection
from datetime import datetime
from typing import Dict, Optional
import uuid
import psycopg2.extras
import logging

# Configure logger
logger = logging.getLogger('autonomous_database_logger')


class AutonomousDatabaseLogger:
    """Comprehensive database logging for autonomous trader"""

    def __init__(self):
        self.session_id = str(uuid.uuid4())[:8]  # Unique session ID
        self.scan_cycle = 0
        self._last_error_time = None
        self._error_count = 0

    def _handle_db_error(self, error: Exception, operation: str) -> None:
        """Handle database errors without crashing the trader"""
        self._error_count += 1
        self._last_error_time = datetime.now()
        logger.error(f"Database logging error in {operation}: {error}")

    def log_scan_start(self, symbol: str, spot_price: float, market_context: Dict) -> Optional[int]:
        """Log the start of a new scan cycle"""
        self.scan_cycle += 1

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol, spot_price, net_gex, flip_point,
                    call_wall, put_wall, vix_level, scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'SCAN_START',
                symbol,
                spot_price,
                market_context.get('net_gex'),
                market_context.get('flip_point'),
                market_context.get('call_wall'),
                market_context.get('put_wall'),
                market_context.get('vix'),
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_scan_start')
            return None

    def log_psychology_analysis(self, regime: Dict, symbol: str, spot_price: float) -> Optional[int]:
        """Log complete psychology trap analysis"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol, spot_price,
                    pattern_detected, confidence_score, trade_direction, risk_level,
                    liberation_setup, liberation_strike, liberation_expiry,
                    false_floor_detected, false_floor_strike,
                    forward_magnet_above, forward_magnet_below, polr,
                    rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d,
                    rsi_aligned_overbought, rsi_aligned_oversold, rsi_coiling,
                    full_reasoning, scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'PSYCHOLOGY_ANALYSIS',
                symbol,
                spot_price,
                regime.get('primary_regime_type'),
                regime.get('confidence_score'),
                regime.get('trade_direction'),
                regime.get('risk_level'),
                regime.get('liberation_setup_detected', False),
                regime.get('liberation_target_strike'),
                regime.get('liberation_expiry_date'),
                regime.get('false_floor_detected', False),
                regime.get('false_floor_strike'),
                regime.get('monthly_magnet_above'),
                regime.get('monthly_magnet_below'),
                regime.get('path_of_least_resistance'),
                regime.get('rsi_5m'),
                regime.get('rsi_15m'),
                regime.get('rsi_1h'),
                regime.get('rsi_4h'),
                regime.get('rsi_1d'),
                regime.get('rsi_aligned_overbought', False),
                regime.get('rsi_aligned_oversold', False),
                regime.get('rsi_coiling', False),
                f"PATTERN: {regime.get('primary_regime_type')}\n"
                f"DESCRIPTION: {regime.get('description', 'N/A')}\n"
                f"PSYCHOLOGY TRAP: {regime.get('psychology_trap', 'N/A')}\n"
                f"DETAILED: {regime.get('detailed_explanation', 'N/A')}",
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_psychology_analysis')
            return None

    def log_strike_selection(self, symbol: str, strike_analysis: Dict, spot_price: float) -> Optional[int]:
        """Log detailed strike selection reasoning"""
        try:
            conn = get_connection()
            c = conn.cursor()

            # Format alternative strikes analysis
            alternatives_text = "\n".join([
                f"${strike}: {reason}"
                for strike, reason in strike_analysis.get('alternative_analysis', {}).items()
            ])

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol, spot_price,
                    strike_chosen, strike_selection_reason,
                    alternative_strikes, why_not_alternatives,
                    ai_thought_process, ai_confidence, ai_warnings,
                    langchain_chain_used, scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'STRIKE_SELECTION',
                symbol,
                spot_price,
                strike_analysis.get('recommended_strike'),
                strike_analysis.get('reasoning'),
                ', '.join([str(k) for k in strike_analysis.get('alternative_analysis', {}).keys()]),
                alternatives_text,
                strike_analysis.get('ai_thought_process', 'N/A'),
                strike_analysis.get('confidence', 'MEDIUM'),
                '\n'.join(strike_analysis.get('warnings', [])),
                strike_analysis.get('langchain_chain', 'unknown'),
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_strike_selection')
            return None

    def log_position_sizing(self, symbol: str, sizing_analysis: Dict, contracts: int) -> Optional[int]:
        """Log position sizing calculations and rationale"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol,
                    kelly_pct, contracts, sizing_rationale,
                    ai_thought_process, ai_warnings,
                    langchain_chain_used, scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'POSITION_SIZING',
                symbol,
                sizing_analysis.get('kelly_pct'),
                contracts,
                sizing_analysis.get('sizing_rationale'),
                sizing_analysis.get('ai_thought_process', 'N/A'),
                '\n'.join(sizing_analysis.get('risk_warnings', [])),
                sizing_analysis.get('langchain_chain', 'unknown'),
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_position_sizing')
            return None

    def log_trade_decision(self, symbol: str, action: str, strategy: str,
                          reasoning: str, confidence: float, position_id: Optional[int] = None) -> Optional[int]:
        """Log final trade decision"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol, action_taken, strategy_name,
                    reasoning_summary, confidence_score,
                    position_id, scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'TRADE_DECISION',
                symbol,
                action,
                strategy,
                reasoning,
                confidence,
                position_id,
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_trade_decision')
            return None

    def log_ai_evaluation(self, symbol: str, evaluation: Dict) -> Optional[int]:
        """Log AI's comprehensive trade evaluation"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol,
                    ai_thought_process, ai_confidence, ai_warnings,
                    langchain_chain_used, reasoning_summary,
                    scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'AI_EVALUATION',
                symbol,
                evaluation.get('ai_thought_process', 'N/A'),
                evaluation.get('confidence', 'MEDIUM'),
                '\n'.join(evaluation.get('warnings', [])),
                evaluation.get('langchain_chain', 'unknown'),
                f"Should Trade: {evaluation.get('should_trade', False)}\n"
                f"Reasoning: {evaluation.get('reasoning', 'N/A')}\n"
                f"Expected Outcome: {evaluation.get('expected_outcome', 'N/A')}",
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_ai_evaluation')
            return None

    def log_skip_reason(self, symbol: str, reason: str) -> Optional[int]:
        """Log why a trade was skipped"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol, action_taken, reasoning_summary,
                    scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'TRADE_SKIPPED',
                symbol,
                'SKIP',
                reason,
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_skip_reason')
            return None

    def log_error(self, symbol: str, error_type: str, error_message: str) -> Optional[int]:
        """Log errors encountered during trading"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO autonomous_trader_logs (
                    log_type, symbol, action_taken, reasoning_summary,
                    scan_cycle, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                'ERROR',
                symbol,
                error_type,
                error_message,
                self.scan_cycle,
                self.session_id
            ))

            result = c.fetchone()
            log_id = result[0] if result else None
            conn.commit()
            conn.close()

            return log_id

        except Exception as e:
            self._handle_db_error(e, 'log_error')
            return None

    def get_session_logs(self, limit: int = 100) -> list:
        """Get logs for current session"""
        try:
            conn = get_connection()
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            c.execute("""
                SELECT * FROM autonomous_trader_logs
                WHERE session_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (self.session_id, limit))

            logs = [dict(row) for row in c.fetchall()]
            conn.close()

            return logs

        except Exception as e:
            self._handle_db_error(e, 'get_session_logs')
            return []

    def get_recent_logs(self, log_type: Optional[str] = None, limit: int = 50) -> list:
        """Get recent logs, optionally filtered by type"""
        try:
            conn = get_connection()
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if log_type:
                c.execute("""
                    SELECT * FROM autonomous_trader_logs
                    WHERE log_type = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (log_type, limit))
            else:
                c.execute("""
                    SELECT * FROM autonomous_trader_logs
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (limit,))

            logs = [dict(row) for row in c.fetchall()]
            conn.close()

            return logs

        except Exception as e:
            self._handle_db_error(e, 'get_recent_logs')
            return []

    def get_logs_by_pattern(self, pattern: str, limit: int = 50) -> list:
        """Get logs for specific pattern detection"""
        try:
            conn = get_connection()
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            c.execute("""
                SELECT * FROM autonomous_trader_logs
                WHERE pattern_detected = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (pattern, limit))

            logs = [dict(row) for row in c.fetchall()]
            conn.close()

            return logs

        except Exception as e:
            self._handle_db_error(e, 'get_logs_by_pattern')
            return []


# Singleton instance per trader
_logger_instances = {}

def get_database_logger(trader_id: str = 'default') -> AutonomousDatabaseLogger:
    """Get database logger instance"""
    if trader_id not in _logger_instances:
        _logger_instances[trader_id] = AutonomousDatabaseLogger()
    return _logger_instances[trader_id]
