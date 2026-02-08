"""
COUNSELOR Tracing and Observability - Enhanced telemetry for COUNSELOR operations.

Provides:
- Request tracing with correlation IDs
- Command execution metrics
- Performance monitoring
- Error tracking with context
- Async operation tracing
"""

import time
import uuid
import logging
import asyncio
from typing import Any, Dict, Optional, Callable, TypeVar
from functools import wraps
from datetime import datetime, timezone
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field
import threading

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class TraceSpan:
    """A single trace span representing an operation."""
    span_id: str
    trace_id: str
    parent_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: list = field(default_factory=list)
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


class GEXISTracer:
    """
    Tracer for COUNSELOR operations with correlation ID support.

    Usage:
        tracer = GEXISTracer()

        # Context manager for tracing
        with tracer.trace("counselor.command.status") as span:
            span.set_attribute("command", "/status")
            result = execute_status_command()
            span.set_attribute("result_size", len(result))

        # Decorator for functions
        @tracer.traced("counselor.fetch_market_data")
        def fetch_market_data(symbol: str):
            return api.get_data(symbol)
    """

    def __init__(self, service_name: str = "counselor"):
        """
        Initialize the tracer.

        Args:
            service_name: Name of the service for traces
        """
        self._service_name = service_name
        self._active_traces: Dict[str, TraceSpan] = {}
        self._completed_traces: list = []
        self._lock = threading.RLock()
        self._max_completed = 1000

        # Thread-local storage for current trace context
        self._local = threading.local()

        # Metrics
        self._metrics = {
            'total_spans': 0,
            'error_spans': 0,
            'operation_counts': {},
            'operation_durations': {}
        }

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
            operation_name: Name of the operation
            attributes: Initial attributes
            trace_id: Optional trace ID (generates new if not provided)

        Yields:
            TraceSpan object
        """
        # Get or create trace ID
        parent_span_id = self.current_span_id
        if trace_id is None:
            trace_id = self.current_trace_id or self._generate_id()

        # Create span
        span = TraceSpan(
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
        with self._lock:
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
            with self._lock:
                self._metrics['error_spans'] += 1
            raise
        finally:
            # Restore context
            self._local.trace_id = old_trace_id
            self._local.span_id = old_span_id

            # Move to completed
            with self._lock:
                if span.span_id in self._active_traces:
                    del self._active_traces[span.span_id]
                self._completed_traces.append(span)

                # Track duration
                if span.duration_ms:
                    if operation_name not in self._metrics['operation_durations']:
                        self._metrics['operation_durations'][operation_name] = []
                    self._metrics['operation_durations'][operation_name].append(span.duration_ms)
                    # Keep only last 100 durations per operation
                    if len(self._metrics['operation_durations'][operation_name]) > 100:
                        self._metrics['operation_durations'][operation_name] = \
                            self._metrics['operation_durations'][operation_name][-100:]

                # Trim completed traces
                if len(self._completed_traces) > self._max_completed:
                    self._completed_traces = self._completed_traces[-self._max_completed:]

            # Log span
            self._log_span(span)

    @asynccontextmanager
    async def trace_async(
        self,
        operation_name: str,
        attributes: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ):
        """
        Async context manager for tracing an operation.

        Args:
            operation_name: Name of the operation
            attributes: Initial attributes
            trace_id: Optional trace ID

        Yields:
            TraceSpan object
        """
        # Reuse sync implementation - it's thread-safe
        with self.trace(operation_name, attributes, trace_id) as span:
            yield span

    def traced(
        self,
        operation_name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Decorator for tracing a function.

        Args:
            operation_name: Name of the operation (defaults to function name)
            attributes: Initial attributes

        Usage:
            @tracer.traced("counselor.command.status")
            def execute_status_command():
                ...
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            op_name = operation_name or f"{self._service_name}.{func.__name__}"

            @wraps(func)
            def wrapper(*args, **kwargs) -> T:
                with self.trace(op_name, attributes) as span:
                    # Add function args as attributes (sanitized)
                    if args:
                        span.set_attribute("args_count", len(args))
                    if kwargs:
                        span.set_attribute("kwargs_keys", list(kwargs.keys()))

                    result = func(*args, **kwargs)

                    # Add result info
                    if result is not None:
                        span.set_attribute("result_type", type(result).__name__)

                    return result

            return wrapper
        return decorator

    def traced_async(
        self,
        operation_name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Decorator for tracing an async function.

        Args:
            operation_name: Name of the operation (defaults to function name)
            attributes: Initial attributes

        Usage:
            @tracer.traced_async("counselor.command.status")
            async def execute_status_command():
                ...
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            op_name = operation_name or f"{self._service_name}.{func.__name__}"

            @wraps(func)
            async def wrapper(*args, **kwargs) -> T:
                async with self.trace_async(op_name, attributes) as span:
                    if args:
                        span.set_attribute("args_count", len(args))
                    if kwargs:
                        span.set_attribute("kwargs_keys", list(kwargs.keys()))

                    result = await func(*args, **kwargs)

                    if result is not None:
                        span.set_attribute("result_type", type(result).__name__)

                    return result

            return wrapper
        return decorator

    def _log_span(self, span: TraceSpan) -> None:
        """Log a completed span."""
        log_level = logging.ERROR if span.error else logging.DEBUG

        log_data = {
            'trace_id': span.trace_id,
            'span_id': span.span_id,
            'operation': span.operation_name,
            'duration_ms': round(span.duration_ms, 2) if span.duration_ms else None,
            'status': span.status
        }

        if span.error:
            log_data['error'] = span.error

        if span.attributes:
            log_data['attributes'] = span.attributes

        logger.log(log_level, f"Trace: {span.operation_name}", extra={'context': log_data})

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get tracer metrics summary.

        Returns:
            Dictionary with metrics
        """
        with self._lock:
            # Calculate duration stats
            duration_stats = {}
            for op, durations in self._metrics['operation_durations'].items():
                if durations:
                    sorted_durations = sorted(durations)
                    duration_stats[op] = {
                        'count': len(durations),
                        'min_ms': round(min(durations), 2),
                        'max_ms': round(max(durations), 2),
                        'avg_ms': round(sum(durations) / len(durations), 2),
                        'p95_ms': round(sorted_durations[int(len(sorted_durations) * 0.95)], 2)
                            if len(sorted_durations) >= 20 else round(max(durations), 2)
                    }

            return {
                'total_spans': self._metrics['total_spans'],
                'error_spans': self._metrics['error_spans'],
                'error_rate_pct': round(
                    self._metrics['error_spans'] / self._metrics['total_spans'] * 100, 2
                ) if self._metrics['total_spans'] > 0 else 0,
                'active_spans': len(self._active_traces),
                'operation_counts': dict(self._metrics['operation_counts']),
                'duration_stats': duration_stats
            }

    def get_recent_traces(self, limit: int = 50) -> list:
        """
        Get recent completed traces.

        Args:
            limit: Maximum number of traces to return

        Returns:
            List of trace dictionaries
        """
        with self._lock:
            return [span.to_dict() for span in self._completed_traces[-limit:]]

    def get_active_spans(self) -> list:
        """
        Get currently active spans.

        Returns:
            List of active span dictionaries
        """
        with self._lock:
            return [span.to_dict() for span in self._active_traces.values()]


# Global tracer instance
gexis_tracer = GEXISTracer()


# =============================================================================
# CONVENIENCE DECORATORS
# =============================================================================

def trace_command(command_name: str):
    """Decorator for tracing COUNSELOR commands."""
    return gexis_tracer.traced(f"counselor.command.{command_name}")


def trace_command_async(command_name: str):
    """Async decorator for tracing COUNSELOR commands."""
    return gexis_tracer.traced_async(f"counselor.command.{command_name}")


def trace_tool(tool_name: str):
    """Decorator for tracing COUNSELOR tools."""
    return gexis_tracer.traced(f"counselor.tool.{tool_name}")


def trace_api_call(api_name: str):
    """Decorator for tracing external API calls."""
    return gexis_tracer.traced(f"counselor.api.{api_name}")


# =============================================================================
# REQUEST CONTEXT
# =============================================================================

class RequestContext:
    """
    Context for a COUNSELOR request, providing correlation ID and trace context.

    Usage:
        with RequestContext() as ctx:
            logger.info(f"Processing request {ctx.request_id}")
            # All operations within will share the same trace_id
    """

    def __init__(self, request_id: Optional[str] = None):
        """
        Initialize request context.

        Args:
            request_id: Optional request ID (generates new if not provided)
        """
        self.request_id = request_id or uuid.uuid4().hex[:8]
        self.trace_id = uuid.uuid4().hex[:16]
        self.start_time = time.time()
        self._span = None

    def __enter__(self):
        """Enter the request context."""
        self._span = gexis_tracer.trace(
            "counselor.request",
            attributes={'request_id': self.request_id},
            trace_id=self.trace_id
        )
        self._span.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the request context."""
        if self._span:
            self._span.__exit__(exc_type, exc_val, exc_tb)

    @property
    def duration_ms(self) -> float:
        """Get request duration in milliseconds."""
        return (time.time() - self.start_time) * 1000

    def add_attribute(self, key: str, value: Any) -> None:
        """Add an attribute to the request span."""
        if self._span and hasattr(self._span, 'gen'):
            # Get the actual span from the generator
            pass  # Attributes set via trace context
