"""
SPX Institutional Trader - Debug Logger
========================================

Comprehensive debugging and logging for the SPX institutional trader.
Logs all critical decision points, data fetches, calculations, and errors.

Usage:
    from spx_debug_logger import SPXDebugLogger, get_spx_debug_logger

    logger = get_spx_debug_logger()
    logger.log_data_fetch('GEX', gex_data, success=True)
    logger.log_regime_classification(regime_result)
    logger.log_position_sizing(sizing_details)
"""

import logging
import os
import json
import traceback
from datetime import datetime
from typing import Dict, Optional, Any, List
from zoneinfo import ZoneInfo

# Database imports
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("Warning: database_adapter not available for SPX debug logging")

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Configure file logging
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Set up file handler for detailed debug logs
file_handler = logging.FileHandler(
    os.path.join(LOG_DIR, f'spx_debug_{datetime.now().strftime("%Y%m%d")}.log'),
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
))

# Set up console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
))

# Create logger
logger = logging.getLogger('SPXDebugLogger')
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)


class SPXDebugLogger:
    """
    Comprehensive debug logger for SPX Institutional Trader.

    Logs to:
    1. Console (INFO level) - for real-time monitoring
    2. File (DEBUG level) - for detailed analysis
    3. Database (all levels) - for persistent storage and API access
    """

    def __init__(self, session_id: str = None):
        """Initialize the debug logger."""
        self.session_id = session_id or f"SPX-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.scan_cycle = 0
        self.logger = logger
        self._ensure_debug_table()

        self.log_info(f"SPX Debug Logger initialized - Session: {self.session_id}")

    def _ensure_debug_table(self):
        """
        Verify debug log table exists.
        NOTE: Table 'spx_debug_logs' is defined in db/config_and_database.py (single source of truth).
        """
        if not DB_AVAILABLE:
            return
        # Tables created by main schema - no action needed

    def _log_to_db(
        self,
        level: str,
        category: str,
        subcategory: str,
        message: str,
        data: Dict = None,
        duration_ms: int = None,
        success: bool = True,
        error_message: str = None,
        stack_trace: str = None
    ):
        """Log entry to database."""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO spx_debug_logs (
                    session_id, scan_cycle, log_level, category, subcategory,
                    message, data, duration_ms, success, error_message, stack_trace
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                self.session_id, self.scan_cycle, level, category, subcategory,
                message, json.dumps(data) if data else None, duration_ms,
                success, error_message, stack_trace
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Failed to log to DB: {e}")

    # ================================================================
    # BASIC LOGGING METHODS
    # ================================================================

    def log_debug(self, message: str, data: Dict = None):
        """Log debug level message."""
        self.logger.debug(f"[{self.session_id}] {message}")
        if data:
            self.logger.debug(f"  Data: {json.dumps(data, default=str)[:500]}")
        self._log_to_db('DEBUG', 'GENERAL', 'debug', message, data)

    def log_info(self, message: str, data: Dict = None):
        """Log info level message."""
        self.logger.info(f"[{self.session_id}] {message}")
        self._log_to_db('INFO', 'GENERAL', 'info', message, data)

    def log_warning(self, message: str, data: Dict = None):
        """Log warning level message."""
        self.logger.warning(f"[{self.session_id}] {message}")
        self._log_to_db('WARNING', 'GENERAL', 'warning', message, data)

    def log_error(self, message: str, error: Exception = None, data: Dict = None):
        """Log error level message with optional exception."""
        stack = traceback.format_exc() if error else None
        self.logger.error(f"[{self.session_id}] {message}")
        if error:
            self.logger.error(f"  Error: {error}")
        self._log_to_db('ERROR', 'GENERAL', 'error', message, data,
                       success=False, error_message=str(error), stack_trace=stack)

    # ================================================================
    # DATA FETCHING DEBUG
    # ================================================================

    def log_data_fetch_start(self, data_type: str, symbol: str = 'SPX'):
        """Log start of data fetch operation."""
        msg = f"FETCH START: {data_type} for {symbol}"
        self.logger.debug(f"[{self.session_id}] {msg}")
        self._log_to_db('DEBUG', 'DATA_FETCH', data_type, msg, {'symbol': symbol})
        return datetime.now()

    def log_data_fetch_result(
        self,
        data_type: str,
        data: Dict,
        start_time: datetime = None,
        success: bool = True,
        error: str = None
    ):
        """Log result of data fetch operation."""
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000) if start_time else None

        if success and data:
            # Log key data points
            key_values = {}
            if data_type == 'GEX':
                key_values = {
                    'net_gex': data.get('net_gex'),
                    'flip_point': data.get('flip_point'),
                    'call_wall': data.get('call_wall'),
                    'put_wall': data.get('put_wall'),
                    'spot_price': data.get('spot_price')
                }
            elif data_type == 'PRICE':
                key_values = {'price': data}
            elif data_type == 'VIX':
                key_values = {'vix': data}
            elif data_type == 'OPTIONS_CHAIN':
                key_values = {
                    'chain_count': len(data) if isinstance(data, list) else 'N/A',
                    'has_data': bool(data)
                }

            msg = f"FETCH SUCCESS: {data_type} in {duration_ms}ms"
            self.logger.info(f"[{self.session_id}] {msg} | {key_values}")
            self._log_to_db('INFO', 'DATA_FETCH', data_type, msg,
                           {'result': key_values, 'full_data_keys': list(data.keys()) if isinstance(data, dict) else None},
                           duration_ms=duration_ms)
        else:
            msg = f"FETCH FAILED: {data_type} - {error}"
            self.logger.error(f"[{self.session_id}] {msg}")
            self._log_to_db('ERROR', 'DATA_FETCH', data_type, msg,
                           success=False, error_message=error, duration_ms=duration_ms)

    # ================================================================
    # REGIME CLASSIFICATION DEBUG
    # ================================================================

    def log_regime_input(self, inputs: Dict):
        """Log inputs to regime classifier."""
        msg = "REGIME INPUT"
        self.logger.debug(f"[{self.session_id}] {msg}")

        # Log key inputs
        key_inputs = {
            'spot_price': inputs.get('spot_price'),
            'net_gex': inputs.get('net_gex'),
            'flip_point': inputs.get('flip_point'),
            'vix': inputs.get('vix'),
            'current_iv': inputs.get('current_iv'),
            'momentum_1h': inputs.get('momentum_1h'),
            'momentum_4h': inputs.get('momentum_4h'),
            'above_20ma': inputs.get('above_20ma'),
            'above_50ma': inputs.get('above_50ma')
        }

        self.logger.debug(f"  Inputs: {key_inputs}")
        self._log_to_db('DEBUG', 'REGIME', 'input', msg, key_inputs)

    def log_regime_classification(self, regime, reasoning_details: Dict = None):
        """Log regime classification result."""
        if regime is None:
            msg = "REGIME CLASSIFICATION: No regime (None returned)"
            self.logger.warning(f"[{self.session_id}] {msg}")
            self._log_to_db('WARNING', 'REGIME', 'classification', msg, success=False)
            return

        regime_data = {
            'volatility_regime': str(regime.volatility_regime.value) if hasattr(regime, 'volatility_regime') else 'N/A',
            'gamma_regime': str(regime.gamma_regime.value) if hasattr(regime, 'gamma_regime') else 'N/A',
            'trend_regime': str(regime.trend_regime.value) if hasattr(regime, 'trend_regime') else 'N/A',
            'recommended_action': str(regime.recommended_action.value) if hasattr(regime, 'recommended_action') else 'N/A',
            'confidence': getattr(regime, 'confidence', 0),
            'iv_rank': getattr(regime, 'iv_rank', 0),
            'net_gex': getattr(regime, 'net_gex', 0),
            'bars_in_regime': getattr(regime, 'bars_in_regime', 0),
            'reasoning': getattr(regime, 'reasoning', '')[:500]
        }

        msg = f"REGIME: Vol={regime_data['volatility_regime']}, Gamma={regime_data['gamma_regime']}, " \
              f"Trend={regime_data['trend_regime']} -> {regime_data['recommended_action']} ({regime_data['confidence']}%)"

        self.logger.info(f"[{self.session_id}] {msg}")
        self._log_to_db('INFO', 'REGIME', 'classification', msg, regime_data)

        # Log detailed reasoning
        if reasoning_details:
            self.logger.debug(f"[{self.session_id}] Regime reasoning: {reasoning_details}")
            self._log_to_db('DEBUG', 'REGIME', 'reasoning', 'Detailed reasoning', reasoning_details)

    def log_stay_flat_reason(self, reason: str, market_context: Dict):
        """Log detailed reason for STAY_FLAT decision."""
        msg = f"STAY_FLAT: {reason[:200]}"
        self.logger.info(f"[{self.session_id}] {msg}")
        self._log_to_db('INFO', 'REGIME', 'stay_flat', msg, {
            'reason': reason,
            'market_context': market_context
        })

    # ================================================================
    # POSITION SIZING DEBUG
    # ================================================================

    def log_vix_stress(
        self,
        current_vix: float,
        stress_level: str,
        stress_factor: float,
        impact: str = None
    ):
        """Log VIX stress level and its impact on trading."""
        msg = f"VIX STRESS: {current_vix:.1f} -> {stress_level.upper()} (factor: {stress_factor:.0%})"

        if stress_level in ['extreme', 'high']:
            self.logger.warning(f"[{self.session_id}] {msg}")
            log_level = 'WARNING'
        else:
            self.logger.info(f"[{self.session_id}] {msg}")
            log_level = 'INFO'

        self._log_to_db(log_level, 'VIX', 'stress', msg, {
            'current_vix': current_vix,
            'stress_level': stress_level,
            'stress_factor': stress_factor,
            'position_reduction_pct': (1 - stress_factor) * 100,
            'impact': impact or f"Position sizes reduced by {(1-stress_factor)*100:.0f}%"
        })

    def log_vix_fetch(
        self,
        vix_value: float,
        source: str,
        success: bool = True,
        error: str = None
    ):
        """Log VIX data fetch result."""
        if success:
            msg = f"VIX FETCH: {vix_value:.2f} from {source}"
            self.logger.debug(f"[{self.session_id}] {msg}")
            self._log_to_db('DEBUG', 'DATA_FETCH', 'VIX', msg, {
                'vix_value': vix_value,
                'source': source
            })
        else:
            msg = f"VIX FETCH FAILED: {error}"
            self.logger.error(f"[{self.session_id}] {msg}")
            self._log_to_db('ERROR', 'DATA_FETCH', 'VIX', msg,
                           success=False, error_message=error)

    def log_backtest_lookup(self, strategy_name: str, params: Dict):
        """Log backtest parameter lookup."""
        msg = f"BACKTEST LOOKUP: {strategy_name}"
        self.logger.debug(f"[{self.session_id}] {msg}")

        self._log_to_db('DEBUG', 'SIZING', 'backtest_lookup', msg, {
            'strategy_name': strategy_name,
            'win_rate': params.get('win_rate'),
            'expectancy': params.get('expectancy'),
            'avg_win': params.get('avg_win'),
            'avg_loss': params.get('avg_loss'),
            'is_proven': params.get('is_proven'),
            'total_trades': params.get('total_trades'),
            'source': params.get('source')
        })

    def log_kelly_calculation(
        self,
        strategy_name: str,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        raw_kelly: float,
        adjusted_kelly: float,
        adjustment_type: str
    ):
        """Log Kelly criterion calculation details."""
        risk_reward = avg_win / avg_loss if avg_loss > 0 else 0

        msg = f"KELLY: {strategy_name} - Raw={raw_kelly:.2%}, Adjusted={adjusted_kelly:.2%} ({adjustment_type})"
        self.logger.info(f"[{self.session_id}] {msg}")

        self._log_to_db('INFO', 'SIZING', 'kelly_calculation', msg, {
            'strategy_name': strategy_name,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'risk_reward_ratio': risk_reward,
            'raw_kelly': raw_kelly,
            'adjusted_kelly': adjusted_kelly,
            'adjustment_type': adjustment_type
        })

    def log_position_sizing_result(self, sizing_details: Dict, contracts: int):
        """Log final position sizing result."""
        msg = f"SIZING RESULT: {contracts} contracts"
        self.logger.info(f"[{self.session_id}] {msg}")

        # Log key sizing factors
        key_details = {
            'contracts': contracts,
            'kelly_pct': sizing_details.get('kelly_pct'),
            'available_capital': sizing_details.get('available_capital'),
            'max_position_value': sizing_details.get('max_position_value'),
            'confidence_factor': sizing_details.get('confidence_factor'),
            'vol_factor': sizing_details.get('vol_factor'),
            'backtest_factor': sizing_details.get('backtest_factor'),
            'final_position_value': sizing_details.get('adjusted_position_value'),
            'cost_per_contract': sizing_details.get('cost_per_contract'),
            'liquidity_capped': sizing_details.get('liquidity_constraint_applied'),
            'blocked': sizing_details.get('blocked', False),
            'error': sizing_details.get('error')
        }

        self.logger.debug(f"  Details: {key_details}")
        self._log_to_db('INFO', 'SIZING', 'result', msg, key_details)

    def log_strategy_blocked(self, strategy_name: str, reason: str):
        """Log when a strategy is blocked from trading."""
        msg = f"STRATEGY BLOCKED: {strategy_name} - {reason}"
        self.logger.warning(f"[{self.session_id}] {msg}")
        self._log_to_db('WARNING', 'SIZING', 'blocked', msg, {
            'strategy_name': strategy_name,
            'reason': reason
        })

    # ================================================================
    # TRADE EXECUTION DEBUG
    # ================================================================

    def log_trade_attempt(self, trade_details: Dict):
        """Log trade execution attempt."""
        msg = f"TRADE ATTEMPT: {trade_details.get('action')} {trade_details.get('option_type')} @ ${trade_details.get('strike')}"
        self.logger.info(f"[{self.session_id}] {msg}")
        self._log_to_db('INFO', 'TRADE', 'attempt', msg, trade_details)

    def log_risk_check(self, check_name: str, passed: bool, details: str):
        """Log risk check result."""
        status = "PASSED" if passed else "FAILED"
        msg = f"RISK CHECK {status}: {check_name} - {details}"
        level = 'INFO' if passed else 'WARNING'

        if passed:
            self.logger.debug(f"[{self.session_id}] {msg}")
        else:
            self.logger.warning(f"[{self.session_id}] {msg}")

        self._log_to_db(level, 'TRADE', 'risk_check', msg, {
            'check_name': check_name,
            'passed': passed,
            'details': details
        })

    def log_trade_execution(
        self,
        position_id: int,
        action: str,
        symbol: str,
        strike: float,
        option_type: str,
        contracts: int,
        entry_price: float,
        commission: float,
        slippage: float,
        total_cost: float
    ):
        """Log successful trade execution."""
        msg = f"TRADE EXECUTED: #{position_id} - {action} {contracts}x {symbol} ${strike} {option_type}"
        self.logger.info(f"[{self.session_id}] {msg}")

        self._log_to_db('INFO', 'TRADE', 'executed', msg, {
            'position_id': position_id,
            'action': action,
            'symbol': symbol,
            'strike': strike,
            'option_type': option_type,
            'contracts': contracts,
            'entry_price': entry_price,
            'commission': commission,
            'slippage': slippage,
            'total_cost': total_cost
        })

    def log_trade_rejected(self, reason: str, details: Dict = None):
        """Log rejected trade."""
        msg = f"TRADE REJECTED: {reason}"
        self.logger.warning(f"[{self.session_id}] {msg}")
        self._log_to_db('WARNING', 'TRADE', 'rejected', msg, details, success=False)

    # ================================================================
    # EXIT LOGIC DEBUG
    # ================================================================

    def log_position_update(
        self,
        position_id: int,
        current_price: float,
        unrealized_pnl: float,
        pnl_pct: float
    ):
        """Log position P&L update."""
        msg = f"POSITION UPDATE: #{position_id} - P&L: ${unrealized_pnl:+,.2f} ({pnl_pct:+.1f}%)"
        self.logger.debug(f"[{self.session_id}] {msg}")
        self._log_to_db('DEBUG', 'POSITION', 'update', msg, {
            'position_id': position_id,
            'current_price': current_price,
            'unrealized_pnl': unrealized_pnl,
            'pnl_pct': pnl_pct
        })

    def log_exit_check(
        self,
        position_id: int,
        check_name: str,
        triggered: bool,
        current_value: Any,
        threshold: Any
    ):
        """Log exit condition check."""
        status = "TRIGGERED" if triggered else "not triggered"
        msg = f"EXIT CHECK #{position_id}: {check_name} {status} (current: {current_value}, threshold: {threshold})"

        if triggered:
            self.logger.info(f"[{self.session_id}] {msg}")
        else:
            self.logger.debug(f"[{self.session_id}] {msg}")

        self._log_to_db('DEBUG' if not triggered else 'INFO', 'POSITION', 'exit_check', msg, {
            'position_id': position_id,
            'check_name': check_name,
            'triggered': triggered,
            'current_value': current_value,
            'threshold': threshold
        })

    def log_position_closed(
        self,
        position_id: int,
        exit_reason: str,
        gross_pnl: float,
        net_pnl: float,
        hold_duration_minutes: int
    ):
        """Log position close."""
        msg = f"POSITION CLOSED: #{position_id} - {exit_reason} - Net P&L: ${net_pnl:+,.2f}"
        self.logger.info(f"[{self.session_id}] {msg}")
        self._log_to_db('INFO', 'POSITION', 'closed', msg, {
            'position_id': position_id,
            'exit_reason': exit_reason,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'hold_duration_minutes': hold_duration_minutes
        })

    # ================================================================
    # SCAN CYCLE DEBUG
    # ================================================================

    def start_scan_cycle(self):
        """Mark start of a new scan cycle."""
        self.scan_cycle += 1
        msg = f"SCAN CYCLE {self.scan_cycle} START"
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"[{self.session_id}] {msg}")
        self.logger.info(f"{'='*60}")
        self._log_to_db('INFO', 'SCAN', 'start', msg, {'scan_cycle': self.scan_cycle})
        return self.scan_cycle

    def end_scan_cycle(self, result: str, duration_seconds: float = None):
        """Mark end of scan cycle."""
        msg = f"SCAN CYCLE {self.scan_cycle} END: {result}"
        if duration_seconds:
            msg += f" ({duration_seconds:.1f}s)"
        self.logger.info(f"[{self.session_id}] {msg}")
        self.logger.info(f"{'='*60}\n")
        self._log_to_db('INFO', 'SCAN', 'end', msg, {
            'scan_cycle': self.scan_cycle,
            'result': result,
            'duration_seconds': duration_seconds
        })

    # ================================================================
    # UTILITY METHODS
    # ================================================================

    def get_recent_logs(self, limit: int = 100, category: str = None) -> List[Dict]:
        """Get recent debug logs from database."""
        if not DB_AVAILABLE:
            return []

        try:
            conn = get_connection()
            c = conn.cursor()

            if category:
                c.execute("""
                    SELECT timestamp, log_level, category, subcategory, message, data, success
                    FROM spx_debug_logs
                    WHERE session_id = %s AND category = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (self.session_id, category, limit))
            else:
                c.execute("""
                    SELECT timestamp, log_level, category, subcategory, message, data, success
                    FROM spx_debug_logs
                    WHERE session_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (self.session_id, limit))

            rows = c.fetchall()
            conn.close()

            return [{
                'timestamp': row[0],
                'level': row[1],
                'category': row[2],
                'subcategory': row[3],
                'message': row[4],
                'data': row[5],
                'success': row[6]
            } for row in rows]

        except Exception as e:
            self.logger.error(f"Failed to get logs: {e}")
            return []

    def get_error_summary(self) -> Dict:
        """Get summary of errors in current session."""
        if not DB_AVAILABLE:
            return {'error': 'Database not available'}

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                SELECT category, COUNT(*) as count
                FROM spx_debug_logs
                WHERE session_id = %s AND success = FALSE
                GROUP BY category
            """, (self.session_id,))

            error_counts = {row[0]: row[1] for row in c.fetchall()}

            c.execute("""
                SELECT timestamp, category, message, error_message
                FROM spx_debug_logs
                WHERE session_id = %s AND success = FALSE
                ORDER BY timestamp DESC
                LIMIT 10
            """, (self.session_id,))

            recent_errors = [{
                'timestamp': row[0],
                'category': row[1],
                'message': row[2],
                'error': row[3]
            } for row in c.fetchall()]

            conn.close()

            return {
                'session_id': self.session_id,
                'error_counts_by_category': error_counts,
                'total_errors': sum(error_counts.values()),
                'recent_errors': recent_errors
            }

        except Exception as e:
            return {'error': str(e)}


# Singleton instance
_debug_logger_instance: Optional[SPXDebugLogger] = None

def get_spx_debug_logger() -> SPXDebugLogger:
    """Get or create the singleton debug logger instance."""
    global _debug_logger_instance
    if _debug_logger_instance is None:
        _debug_logger_instance = SPXDebugLogger()
    return _debug_logger_instance

def reset_debug_logger():
    """Reset the debug logger (for testing)."""
    global _debug_logger_instance
    _debug_logger_instance = None
