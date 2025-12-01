"""
Structured logging configuration for AlphaGEX.

This module provides JSON-formatted structured logging for quantitative operations,
enabling proper observability and calculation accuracy tracking.
"""

import logging
import json
import sys
import uuid
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Callable
from functools import wraps
from contextlib import contextmanager


# =============================================================================
# STRUCTURED JSON FORMATTER
# =============================================================================

class QuantFormatter(logging.Formatter):
    """
    JSON formatter for quantitative logging.

    Outputs structured logs with:
    - Timestamp in ISO format
    - Log level
    - Logger name (module)
    - Message
    - Extra context fields
    - Calculation metrics when applicable
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage()
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra context from the record
        if hasattr(record, 'context') and record.context:
            log_data["context"] = record.context

        # Add correlation ID if present
        if hasattr(record, 'correlation_id') and record.correlation_id:
            log_data["correlation_id"] = record.correlation_id

        # Add calculation metrics if present
        if hasattr(record, 'metrics') and record.metrics:
            log_data["metrics"] = record.metrics

        return json.dumps(log_data)


class HumanReadableFormatter(logging.Formatter):
    """
    Human-readable formatter for development/debugging.

    Format: [TIMESTAMP] LEVEL - MODULE:LINE - MESSAGE
    """

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        color = self.COLORS.get(record.levelname, '')

        base_msg = f"[{timestamp}] {color}{record.levelname:8}{self.RESET} - {record.module}:{record.lineno} - {record.getMessage()}"

        # Add context if present
        if hasattr(record, 'context') and record.context:
            base_msg += f" | context={record.context}"

        # Add metrics if present
        if hasattr(record, 'metrics') and record.metrics:
            base_msg += f" | metrics={record.metrics}"

        if record.exc_info:
            base_msg += "\n" + self.formatException(record.exc_info)

        return base_msg


# =============================================================================
# LOGGER SETUP
# =============================================================================

def setup_logger(
    name: str,
    level: int = logging.INFO,
    json_output: bool = True,
    include_console: bool = True
) -> logging.Logger:
    """
    Set up a structured logger for a module.

    Args:
        name: Logger name (usually __name__)
        level: Logging level
        json_output: If True, output JSON format; else human-readable
        include_console: If True, add console handler

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    if include_console:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        if json_output:
            handler.setFormatter(QuantFormatter())
        else:
            handler.setFormatter(HumanReadableFormatter())

        logger.addHandler(handler)

    return logger


# Global logger for the API
api_logger = setup_logger("alphagex.api", json_output=False)


# =============================================================================
# CONTEXTUAL LOGGING
# =============================================================================

class LogContext:
    """Thread-local storage for logging context."""

    _context: Dict[str, Any] = {}
    _correlation_id: Optional[str] = None

    @classmethod
    def set(cls, **kwargs):
        """Set context values."""
        cls._context.update(kwargs)

    @classmethod
    def get(cls) -> Dict[str, Any]:
        """Get current context."""
        return cls._context.copy()

    @classmethod
    def clear(cls):
        """Clear context."""
        cls._context = {}
        cls._correlation_id = None

    @classmethod
    def set_correlation_id(cls, correlation_id: str):
        """Set correlation ID for request tracing."""
        cls._correlation_id = correlation_id

    @classmethod
    def get_correlation_id(cls) -> Optional[str]:
        """Get current correlation ID."""
        return cls._correlation_id

    @classmethod
    def new_correlation_id(cls) -> str:
        """Generate and set a new correlation ID."""
        correlation_id = str(uuid.uuid4())[:8]
        cls._correlation_id = correlation_id
        return correlation_id


@contextmanager
def log_context(**kwargs):
    """
    Context manager for temporary logging context.

    Usage:
        with log_context(symbol='SPY', operation='gex_calculation'):
            logger.info("Starting calculation")
            # ... do work ...
            logger.info("Calculation complete")
    """
    previous = LogContext.get()
    LogContext.set(**kwargs)
    try:
        yield
    finally:
        LogContext._context = previous


# =============================================================================
# CALCULATION TRACKING DECORATOR
# =============================================================================

def track_calculation(
    calc_type: str,
    log_inputs: bool = True,
    log_output: bool = True,
    warn_threshold_ms: float = 1000.0
):
    """
    Decorator to track calculation timing and accuracy.

    Args:
        calc_type: Type of calculation (e.g., 'gex', 'greeks', 'position_size')
        log_inputs: Whether to log input parameters
        log_output: Whether to log output value
        warn_threshold_ms: Threshold in milliseconds to warn about slow calculations

    Usage:
        @track_calculation('gex_calculation')
        def calculate_gex(symbol: str, spot_price: float) -> float:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            start_time = time.time()
            correlation_id = LogContext.get_correlation_id() or LogContext.new_correlation_id()

            # Build input context
            input_context = {}
            if log_inputs:
                # Get function argument names
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())

                # Map positional args to names
                for i, arg in enumerate(args):
                    if i < len(param_names):
                        input_context[param_names[i]] = _sanitize_for_log(arg)

                # Add keyword args
                for key, value in kwargs.items():
                    input_context[key] = _sanitize_for_log(value)

            # Log start
            logger.info(
                f"Starting {calc_type}",
                extra={
                    'correlation_id': correlation_id,
                    'context': {
                        'calculation_type': calc_type,
                        'inputs': input_context if log_inputs else None
                    }
                }
            )

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                # Build metrics
                metrics = {
                    'duration_ms': round(duration_ms, 2),
                    'status': 'success'
                }

                # Log completion
                log_level = logging.WARNING if duration_ms > warn_threshold_ms else logging.INFO
                logger.log(
                    log_level,
                    f"Completed {calc_type} in {duration_ms:.2f}ms",
                    extra={
                        'correlation_id': correlation_id,
                        'metrics': metrics,
                        'context': {
                            'calculation_type': calc_type,
                            'output': _sanitize_for_log(result) if log_output else None
                        }
                    }
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                logger.error(
                    f"Failed {calc_type}: {str(e)}",
                    extra={
                        'correlation_id': correlation_id,
                        'metrics': {
                            'duration_ms': round(duration_ms, 2),
                            'status': 'error'
                        },
                        'context': {
                            'calculation_type': calc_type,
                            'error_type': type(e).__name__
                        }
                    },
                    exc_info=True
                )
                raise

        return wrapper
    return decorator


def _sanitize_for_log(value: Any, max_length: int = 100) -> Any:
    """
    Sanitize a value for logging (truncate strings, summarize large objects).
    """
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value[:max_length] + '...' if len(value) > max_length else value
    if isinstance(value, (list, tuple)):
        if len(value) <= 3:
            return [_sanitize_for_log(v) for v in value]
        return f"[{len(value)} items]"
    if isinstance(value, dict):
        if len(value) <= 5:
            return {k: _sanitize_for_log(v) for k, v in value.items()}
        return f"{{dict with {len(value)} keys}}"
    return str(type(value).__name__)


# =============================================================================
# TRADE LOGGING
# =============================================================================

def log_trade_entry(
    logger: logging.Logger,
    symbol: str,
    strike: float,
    option_type: str,
    contracts: int,
    entry_price: float,
    strategy: str,
    confidence: Optional[float] = None,
    reasoning: Optional[str] = None
):
    """Log a trade entry with full context."""
    logger.info(
        f"TRADE ENTRY: {symbol} {strike} {option_type} x{contracts} @ ${entry_price:.2f}",
        extra={
            'context': {
                'event_type': 'trade_entry',
                'symbol': symbol,
                'strike': strike,
                'option_type': option_type,
                'contracts': contracts,
                'entry_price': entry_price,
                'strategy': strategy,
                'confidence': confidence,
                'reasoning': reasoning[:200] if reasoning else None
            }
        }
    )


def log_trade_exit(
    logger: logging.Logger,
    symbol: str,
    strike: float,
    option_type: str,
    contracts: int,
    entry_price: float,
    exit_price: float,
    pnl: float,
    pnl_pct: float,
    exit_reason: str,
    hold_duration_minutes: Optional[int] = None
):
    """Log a trade exit with full context and P&L."""
    logger.info(
        f"TRADE EXIT: {symbol} {strike} {option_type} x{contracts} | P&L: ${pnl:.2f} ({pnl_pct:+.1f}%) - {exit_reason}",
        extra={
            'context': {
                'event_type': 'trade_exit',
                'symbol': symbol,
                'strike': strike,
                'option_type': option_type,
                'contracts': contracts,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'exit_reason': exit_reason,
                'hold_duration_minutes': hold_duration_minutes
            }
        }
    )


def log_risk_alert(
    logger: logging.Logger,
    alert_type: str,
    message: str,
    current_value: float,
    threshold: float,
    symbol: Optional[str] = None
):
    """Log a risk management alert."""
    logger.warning(
        f"RISK ALERT [{alert_type}]: {message}",
        extra={
            'context': {
                'event_type': 'risk_alert',
                'alert_type': alert_type,
                'symbol': symbol,
                'current_value': current_value,
                'threshold': threshold
            }
        }
    )


# =============================================================================
# METRIC TRACKING
# =============================================================================

class MetricsCollector:
    """
    Collects and aggregates metrics for quantitative operations.

    Usage:
        metrics = MetricsCollector()
        metrics.record('gex_calculation', duration_ms=45.2, symbol='SPY')
        metrics.record('api_call', duration_ms=120.5, source='tradier')

        summary = metrics.get_summary()
    """

    def __init__(self):
        self._metrics: Dict[str, list] = {}

    def record(self, metric_type: str, **values):
        """Record a metric with associated values."""
        if metric_type not in self._metrics:
            self._metrics[metric_type] = []

        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **values
        }
        self._metrics[metric_type].append(entry)

        # Keep only last 1000 entries per type
        if len(self._metrics[metric_type]) > 1000:
            self._metrics[metric_type] = self._metrics[metric_type][-1000:]

    def get_summary(self, metric_type: Optional[str] = None) -> Dict[str, Any]:
        """Get summary statistics for metrics."""
        if metric_type:
            entries = self._metrics.get(metric_type, [])
            return self._summarize_entries(metric_type, entries)

        return {
            mt: self._summarize_entries(mt, entries)
            for mt, entries in self._metrics.items()
        }

    def _summarize_entries(self, metric_type: str, entries: list) -> Dict[str, Any]:
        """Summarize a list of metric entries."""
        if not entries:
            return {'count': 0}

        # Extract duration_ms values if present
        durations = [e.get('duration_ms') for e in entries if 'duration_ms' in e]

        summary = {
            'count': len(entries),
            'last_recorded': entries[-1].get('timestamp') if entries else None
        }

        if durations:
            summary['duration_ms'] = {
                'min': min(durations),
                'max': max(durations),
                'avg': sum(durations) / len(durations),
                'p95': sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 10 else max(durations)
            }

        return summary

    def clear(self):
        """Clear all recorded metrics."""
        self._metrics = {}


# Global metrics collector
metrics_collector = MetricsCollector()
