"""
JUBILEE Tracing and Observability

Provides:
- Request tracing with correlation IDs
- Box spread operation metrics
- Performance monitoring
- Error tracking with context
- Rate calculation auditing

Follows the same pattern as ai/counselor_tracing.py for consistency.
"""

import time
import uuid
import logging
import threading
from typing import Any, Dict, Optional, Callable, TypeVar, List
from functools import wraps
from datetime import datetime, timezone
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class JubileeSpan:
    """A single trace span representing a JUBILEE operation."""
    span_id: str
    trace_id: str
    parent_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> Optional[float]:
        """Get duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def add_event(self, name: str, attributes: Optional[Dict] = None) -> None:
        """Add an event to this span."""
        self.events.append({
            'name': name,
            'timestamp': time.time(),
            'attributes': attributes or {}
        })

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on this span."""
        self.attributes[key] = value

    def set_error(self, error: str) -> None:
        """Mark span as errored."""
        self.error = error
        self.status = "error"

    def finish(self, status: str = "ok") -> None:
        """Finish the span."""
        self.end_time = time.time()
        if not self.error:
            self.status = status

    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            'span_id': self.span_id,
            'trace_id': self.trace_id,
            'parent_id': self.parent_id,
            'operation_name': self.operation_name,
            'start_time': datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            'end_time': datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            'duration_ms': self.duration_ms,
            'status': self.status,
            'attributes': self.attributes,
            'events': self.events,
            'error': self.error
        }


class JubileeTracer:
    """
    Tracer for JUBILEE box spread operations.

    Usage:
        tracer = JubileeTracer()

        # Context manager for tracing
        with tracer.trace("jubilee.quote.fetch") as span:
            span.set_attribute("ticker", "SPX")
            quotes = fetch_box_quotes(...)
            span.set_attribute("quote_count", len(quotes))

        # Decorator for functions
        @tracer.traced("jubilee.rate.calculate")
        def calculate_implied_rate(credit, theoretical, dte):
            return (theoretical - credit) / credit * (365 / dte)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern for global tracer."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the tracer (only once due to singleton)."""
        if self._initialized:
            return

        self._service_name = "jubilee"
        self._active_traces: Dict[str, JubileeSpan] = {}
        self._completed_traces: List[JubileeSpan] = []
        self._trace_lock = threading.RLock()
        self._max_completed = 500

        # Thread-local storage for current trace context
        self._local = threading.local()

        # Metrics
        self._metrics = {
            'total_spans': 0,
            'error_spans': 0,
            'operation_counts': {},
            'operation_durations': {},
            # JUBILEE-specific metrics
            'quotes_fetched': 0,
            'rates_calculated': 0,
            'positions_opened': 0,
            'positions_closed': 0,
            'total_borrowed': 0.0,
            'avg_implied_rate': 0.0,
            'rate_calculations': [],
        }

        self._initialized = True
        logger.info("JubileeTracer initialized")

    @property
    def current_trace_id(self) -> Optional[str]:
        """Get current trace ID from context."""
        return getattr(self._local, 'trace_id', None)

    @property
    def current_span_id(self) -> Optional[str]:
        """Get current span ID from context."""
        return getattr(self._local, 'span_id', None)

    def _generate_id(self) -> str:
        """Generate a unique ID."""
        return uuid.uuid4().hex[:16]

    @contextmanager
    def trace(
        self,
        operation_name: str,
        attributes: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ):
        """
        Context manager for tracing an operation.

        Args:
            operation_name: Name of the operation (e.g., "jubilee.quote.fetch")
            attributes: Initial attributes
            trace_id: Optional trace ID (generates new if not provided)

        Yields:
            JubileeSpan object
        """
        # Get or create trace ID
        parent_span_id = self.current_span_id
        if trace_id is None:
            trace_id = self.current_trace_id or self._generate_id()

        # Create span
        span = JubileeSpan(
            span_id=self._generate_id(),
            trace_id=trace_id,
            parent_id=parent_span_id,
            operation_name=operation_name,
            start_time=time.time(),
            attributes=attributes or {}
        )

        # Set context
        old_trace_id = getattr(self._local, 'trace_id', None)
        old_span_id = getattr(self._local, 'span_id', None)
        self._local.trace_id = trace_id
        self._local.span_id = span.span_id

        # Track active span
        with self._trace_lock:
            self._active_traces[span.span_id] = span
            self._metrics['total_spans'] += 1

            # Update operation counts
            if operation_name not in self._metrics['operation_counts']:
                self._metrics['operation_counts'][operation_name] = 0
            self._metrics['operation_counts'][operation_name] += 1

        try:
            yield span
            span.finish("ok")
        except Exception as e:
            span.set_error(str(e))
            span.finish("error")
            with self._trace_lock:
                self._metrics['error_spans'] += 1
            raise
        finally:
            # Restore context
            self._local.trace_id = old_trace_id
            self._local.span_id = old_span_id

            # Move to completed
            with self._trace_lock:
                if span.span_id in self._active_traces:
                    del self._active_traces[span.span_id]
                self._completed_traces.append(span)

                # Track durations
                if operation_name not in self._metrics['operation_durations']:
                    self._metrics['operation_durations'][operation_name] = []
                if span.duration_ms is not None:
                    self._metrics['operation_durations'][operation_name].append(span.duration_ms)

                # Trim completed traces
                if len(self._completed_traces) > self._max_completed:
                    self._completed_traces = self._completed_traces[-self._max_completed:]

            # Log span
            if span.status == "error":
                logger.warning(
                    f"JUBILEE span error: {operation_name} - {span.error}",
                    extra={'span': span.to_dict()}
                )
            else:
                logger.debug(
                    f"JUBILEE span: {operation_name} ({span.duration_ms:.2f}ms)",
                    extra={'span': span.to_dict()}
                )

    def traced(self, operation_name: Optional[str] = None) -> Callable:
        """
        Decorator for tracing functions.

        Args:
            operation_name: Optional operation name (defaults to function name)

        Returns:
            Decorated function with tracing
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            op_name = operation_name or f"jubilee.{func.__name__}"

            @wraps(func)
            def wrapper(*args, **kwargs) -> T:
                with self.trace(op_name) as span:
                    # Add function context
                    span.set_attribute('function', func.__name__)
                    span.set_attribute('args_count', len(args))
                    span.set_attribute('kwargs_keys', list(kwargs.keys()))

                    result = func(*args, **kwargs)

                    # Add result info
                    if result is not None:
                        span.set_attribute('result_type', type(result).__name__)

                    return result

            return wrapper
        return decorator

    # ==========================================================================
    # JUBILEE-Specific Tracing Methods
    # ==========================================================================

    def trace_quote_fetch(
        self,
        ticker: str,
        expiration: str,
        lower_strike: float,
        upper_strike: float
    ):
        """Trace a box spread quote fetch operation."""
        return self.trace(
            "jubilee.quote.fetch",
            attributes={
                'ticker': ticker,
                'expiration': expiration,
                'lower_strike': lower_strike,
                'upper_strike': upper_strike,
            }
        )

    def trace_rate_calculation(
        self,
        credit: float,
        theoretical: float,
        dte: int,
        calculated_rate: float
    ) -> None:
        """Record a rate calculation for auditing."""
        with self._trace_lock:
            self._metrics['rates_calculated'] += 1
            self._metrics['rate_calculations'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'credit': credit,
                'theoretical': theoretical,
                'dte': dte,
                'calculated_rate': calculated_rate,
            })

            # Keep only last 100 calculations
            if len(self._metrics['rate_calculations']) > 100:
                self._metrics['rate_calculations'] = self._metrics['rate_calculations'][-100:]

            # Update average rate
            rates = [r['calculated_rate'] for r in self._metrics['rate_calculations']]
            self._metrics['avg_implied_rate'] = sum(rates) / len(rates) if rates else 0.0

    def trace_position_opened(self, position_id: str, borrowed_amount: float) -> None:
        """Record a position being opened."""
        with self._trace_lock:
            self._metrics['positions_opened'] += 1
            self._metrics['total_borrowed'] += borrowed_amount

        logger.info(f"JUBILEE position opened: {position_id}, borrowed: ${borrowed_amount:,.2f}")

    def trace_position_closed(self, position_id: str, pnl: float) -> None:
        """Record a position being closed."""
        with self._trace_lock:
            self._metrics['positions_closed'] += 1

        logger.info(f"JUBILEE position closed: {position_id}, P&L: ${pnl:,.2f}")

    # ==========================================================================
    # Metrics and Reporting
    # ==========================================================================

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        with self._trace_lock:
            # Calculate duration stats
            duration_stats = {}
            for op_name, durations in self._metrics['operation_durations'].items():
                if durations:
                    sorted_durations = sorted(durations)
                    p95_idx = int(len(sorted_durations) * 0.95)
                    duration_stats[op_name] = {
                        'count': len(durations),
                        'min_ms': min(durations),
                        'max_ms': max(durations),
                        'avg_ms': sum(durations) / len(durations),
                        'p95_ms': sorted_durations[p95_idx] if p95_idx < len(sorted_durations) else sorted_durations[-1],
                    }

            error_rate = 0.0
            if self._metrics['total_spans'] > 0:
                error_rate = (self._metrics['error_spans'] / self._metrics['total_spans']) * 100

            return {
                'service': self._service_name,
                'total_spans': self._metrics['total_spans'],
                'error_spans': self._metrics['error_spans'],
                'error_rate_pct': round(error_rate, 2),
                'active_spans': len(self._active_traces),
                'operation_counts': dict(self._metrics['operation_counts']),
                'duration_stats': duration_stats,
                # JUBILEE-specific
                'quotes_fetched': self._metrics['quotes_fetched'],
                'rates_calculated': self._metrics['rates_calculated'],
                'positions_opened': self._metrics['positions_opened'],
                'positions_closed': self._metrics['positions_closed'],
                'total_borrowed': self._metrics['total_borrowed'],
                'avg_implied_rate': round(self._metrics['avg_implied_rate'], 4),
            }

    def get_recent_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent completed traces."""
        with self._trace_lock:
            return [span.to_dict() for span in self._completed_traces[-limit:]]

    def get_rate_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get rate calculation audit trail."""
        with self._trace_lock:
            return self._metrics['rate_calculations'][-limit:]

    def reset_metrics(self) -> None:
        """Reset metrics (for testing)."""
        with self._trace_lock:
            self._metrics = {
                'total_spans': 0,
                'error_spans': 0,
                'operation_counts': {},
                'operation_durations': {},
                'quotes_fetched': 0,
                'rates_calculated': 0,
                'positions_opened': 0,
                'positions_closed': 0,
                'total_borrowed': 0.0,
                'avg_implied_rate': 0.0,
                'rate_calculations': [],
            }
            self._completed_traces = []
            self._active_traces = {}


# Global tracer instance
_tracer: Optional[JubileeTracer] = None


def get_tracer() -> JubileeTracer:
    """Get the global JUBILEE tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = JubileeTracer()
    return _tracer


# Convenience decorators
def trace_quote(func: Callable) -> Callable:
    """Decorator for quote fetching functions."""
    return get_tracer().traced(f"jubilee.quote.{func.__name__}")(func)


def trace_rate(func: Callable) -> Callable:
    """Decorator for rate calculation functions."""
    return get_tracer().traced(f"jubilee.rate.{func.__name__}")(func)


def trace_position(func: Callable) -> Callable:
    """Decorator for position management functions."""
    return get_tracer().traced(f"jubilee.position.{func.__name__}")(func)


def trace_signal(func: Callable) -> Callable:
    """Decorator for signal generation functions."""
    return get_tracer().traced(f"jubilee.signal.{func.__name__}")(func)
