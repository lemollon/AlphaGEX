"""
AlphaGEX Centralized Logging Infrastructure
============================================

Production-grade logging with:
- Structured JSON logging for production
- Human-readable format for development
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Contextual logging with trade/session IDs
- File rotation and retention policies
- Performance metrics logging
- Audit trail for trade decisions

Usage:
    from utils.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("Processing trade", extra={"symbol": "SPY", "action": "BUY"})
"""

import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from functools import wraps
import time
import traceback


# ===== CONFIGURATION =====

class LogConfig:
    """Logging configuration"""

    # Log level from environment or default
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Environment detection
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    IS_PRODUCTION = ENVIRONMENT == 'production'

    # Log directory
    LOG_DIR = Path(os.getenv('LOG_DIR', 'logs'))

    # File rotation settings
    MAX_BYTES = 10 * 1024 * 1024  # 10MB per file
    BACKUP_COUNT = 5  # Keep 5 backup files

    # Log file names
    APP_LOG_FILE = 'alphagex.log'
    ERROR_LOG_FILE = 'alphagex_errors.log'
    TRADE_LOG_FILE = 'trades.log'
    AUDIT_LOG_FILE = 'audit.log'

    # Performance threshold (log slow operations)
    SLOW_OPERATION_THRESHOLD_MS = 1000  # 1 second


# ===== FORMATTERS =====

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info)
            }

        # Add extra fields (e.g., symbol, trade_id, session_id)
        extra_fields = {
            k: v for k, v in record.__dict__.items()
            if k not in logging.LogRecord(
                '', 0, '', 0, '', (), None
            ).__dict__ and not k.startswith('_')
        }
        if extra_fields:
            log_data["context"] = extra_fields

        return json.dumps(log_data)


class ReadableFormatter(logging.Formatter):
    """Human-readable formatter for development"""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'
    }

    def format(self, record: logging.LogRecord) -> str:
        # Color for terminal
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']

        # Base format
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        base = f"{timestamp} | {color}{record.levelname:8}{reset} | {record.name} | {record.getMessage()}"

        # Add context if present
        extra_fields = {
            k: v for k, v in record.__dict__.items()
            if k not in logging.LogRecord(
                '', 0, '', 0, '', (), None
            ).__dict__ and not k.startswith('_')
            and k not in ('message', 'args')
        }
        if extra_fields:
            context_str = ' | '.join(f"{k}={v}" for k, v in extra_fields.items())
            base += f" | {context_str}"

        # Add exception if present
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"

        return base


# ===== LOGGER SETUP =====

def setup_logging():
    """Initialize logging infrastructure"""

    # Create log directory
    LogConfig.LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LogConfig.LOG_LEVEL))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Select formatter based on environment
    if LogConfig.IS_PRODUCTION:
        formatter = JSONFormatter()
    else:
        formatter = ReadableFormatter()

    # Console handler (always)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LogConfig.LOG_LEVEL))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler - main app log (rotating)
    app_log_path = LogConfig.LOG_DIR / LogConfig.APP_LOG_FILE
    app_file_handler = logging.handlers.RotatingFileHandler(
        app_log_path,
        maxBytes=LogConfig.MAX_BYTES,
        backupCount=LogConfig.BACKUP_COUNT
    )
    app_file_handler.setLevel(logging.DEBUG)  # Capture all in file
    app_file_handler.setFormatter(JSONFormatter())  # Always JSON in files
    root_logger.addHandler(app_file_handler)

    # Error file handler (errors and above only)
    error_log_path = LogConfig.LOG_DIR / LogConfig.ERROR_LOG_FILE
    error_file_handler = logging.handlers.RotatingFileHandler(
        error_log_path,
        maxBytes=LogConfig.MAX_BYTES,
        backupCount=LogConfig.BACKUP_COUNT
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_file_handler)

    return root_logger


# ===== SPECIALIZED LOGGERS =====

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def get_trade_logger() -> logging.Logger:
    """
    Get logger for trade operations.
    Logs to separate file for audit trail.
    """
    logger = logging.getLogger('alphagex.trades')

    # Only add handler if not already configured
    if not any(isinstance(h, logging.handlers.RotatingFileHandler)
               and LogConfig.TRADE_LOG_FILE in str(getattr(h, 'baseFilename', ''))
               for h in logger.handlers):

        trade_log_path = LogConfig.LOG_DIR / LogConfig.TRADE_LOG_FILE
        handler = logging.handlers.RotatingFileHandler(
            trade_log_path,
            maxBytes=LogConfig.MAX_BYTES,
            backupCount=10  # Keep more backups for trades
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    return logger


def get_audit_logger() -> logging.Logger:
    """
    Get logger for audit trail (decisions, state changes).
    Critical for compliance and debugging production issues.
    """
    logger = logging.getLogger('alphagex.audit')

    if not any(isinstance(h, logging.handlers.RotatingFileHandler)
               and LogConfig.AUDIT_LOG_FILE in str(getattr(h, 'baseFilename', ''))
               for h in logger.handlers):

        audit_log_path = LogConfig.LOG_DIR / LogConfig.AUDIT_LOG_FILE
        handler = logging.handlers.RotatingFileHandler(
            audit_log_path,
            maxBytes=LogConfig.MAX_BYTES,
            backupCount=20  # Keep many backups for audit
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    return logger


# ===== CONTEXT MANAGERS AND DECORATORS =====

class LogContext:
    """
    Context manager for adding contextual information to logs.

    Usage:
        with LogContext(trade_id="T123", symbol="SPY"):
            logger.info("Processing trade")  # Will include trade_id and symbol
    """

    _context: Dict[str, Any] = {}

    def __init__(self, **kwargs):
        self.new_context = kwargs
        self.old_context = {}

    def __enter__(self):
        self.old_context = LogContext._context.copy()
        LogContext._context.update(self.new_context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        LogContext._context = self.old_context
        return False

    @classmethod
    def get_context(cls) -> Dict[str, Any]:
        return cls._context.copy()


def log_execution_time(logger: Optional[logging.Logger] = None, level: int = logging.DEBUG):
    """
    Decorator to log function execution time.

    Usage:
        @log_execution_time()
        def slow_function():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)

            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.time() - start) * 1000

                log_level = level
                if elapsed_ms > LogConfig.SLOW_OPERATION_THRESHOLD_MS:
                    log_level = logging.WARNING

                logger.log(
                    log_level,
                    f"{func.__name__} completed",
                    extra={
                        "function": func.__name__,
                        "execution_time_ms": round(elapsed_ms, 2),
                        "slow": elapsed_ms > LogConfig.SLOW_OPERATION_THRESHOLD_MS
                    }
                )
                return result
            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                logger.error(
                    f"{func.__name__} failed: {str(e)}",
                    extra={
                        "function": func.__name__,
                        "execution_time_ms": round(elapsed_ms, 2),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise
        return wrapper
    return decorator


def log_trade_decision(
    action: str,
    symbol: str,
    reason: str,
    confidence: Optional[float] = None,
    **kwargs
):
    """
    Log a trade decision for audit trail.

    Args:
        action: Trade action (BUY, SELL, HOLD, etc.)
        symbol: Trading symbol
        reason: Why this decision was made
        confidence: Confidence score (0-1)
        **kwargs: Additional context (price, quantity, etc.)
    """
    trade_logger = get_trade_logger()
    audit_logger = get_audit_logger()

    log_data = {
        "action": action,
        "symbol": symbol,
        "reason": reason,
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs
    }

    trade_logger.info(
        f"TRADE_DECISION: {action} {symbol}",
        extra=log_data
    )

    audit_logger.info(
        f"Decision: {action} {symbol} - {reason}",
        extra=log_data
    )


def log_error_with_context(
    logger: logging.Logger,
    message: str,
    error: Exception,
    **context
):
    """
    Log an error with full context and traceback.

    Args:
        logger: Logger instance
        message: Error message
        error: The exception
        **context: Additional context
    """
    logger.error(
        message,
        extra={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            **context
        },
        exc_info=True
    )


def log_api_call(
    logger: logging.Logger,
    api_name: str,
    endpoint: str,
    response_time_ms: float,
    status: str,
    **kwargs
):
    """
    Log an API call for monitoring.

    Args:
        logger: Logger instance
        api_name: Name of the API (e.g., "TradingVolatility", "Polygon")
        endpoint: API endpoint called
        response_time_ms: Response time in milliseconds
        status: Status (success, error, timeout, etc.)
        **kwargs: Additional context
    """
    level = logging.INFO if status == "success" else logging.WARNING

    logger.log(
        level,
        f"API_CALL: {api_name} {endpoint}",
        extra={
            "api_name": api_name,
            "endpoint": endpoint,
            "response_time_ms": round(response_time_ms, 2),
            "status": status,
            **kwargs
        }
    )


def log_data_quality_issue(
    logger: logging.Logger,
    issue_type: str,
    description: str,
    severity: str = "warning",
    **context
):
    """
    Log data quality issues for monitoring.

    Args:
        logger: Logger instance
        issue_type: Type of issue (missing_data, stale_data, invalid_value, etc.)
        description: Description of the issue
        severity: Severity level (info, warning, error, critical)
        **context: Additional context
    """
    level_map = {
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL
    }
    level = level_map.get(severity, logging.WARNING)

    logger.log(
        level,
        f"DATA_QUALITY: {issue_type} - {description}",
        extra={
            "issue_type": issue_type,
            "description": description,
            "severity": severity,
            **context
        }
    )


# ===== INITIALIZATION =====

# Setup logging on module import
_root_logger = setup_logging()
_init_logger = get_logger(__name__)
_init_logger.info(
    "Logging infrastructure initialized",
    extra={
        "log_level": LogConfig.LOG_LEVEL,
        "environment": LogConfig.ENVIRONMENT,
        "log_dir": str(LogConfig.LOG_DIR)
    }
)


# ===== EXPORTS =====
__all__ = [
    'LogConfig',
    'get_logger',
    'get_trade_logger',
    'get_audit_logger',
    'LogContext',
    'log_execution_time',
    'log_trade_decision',
    'log_error_with_context',
    'log_api_call',
    'log_data_quality_issue',
    'setup_logging',
]
