"""
Custom exceptions for AlphaGEX API.

This module defines domain-specific exceptions for quantitative trading operations.
These exceptions provide better error context and enable proper error handling.
"""

from typing import Any, Dict, Optional


class AlphaGEXError(Exception):
    """Base exception for all AlphaGEX errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "ALPHAGEX_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API response."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details
        }


# =============================================================================
# NUMERICAL/CALCULATION ERRORS
# =============================================================================

class NumericalPrecisionError(AlphaGEXError):
    """
    Raised when numerical calculation precision is compromised.

    Use this for:
    - Overflow/underflow in calculations
    - Values outside expected bounds
    - Precision loss in critical calculations
    """

    def __init__(
        self,
        message: str,
        value: Any = None,
        expected_range: Optional[tuple] = None,
        calculation_context: Optional[str] = None
    ):
        details = {
            "value": str(value) if value is not None else None,
            "expected_range": expected_range,
            "calculation_context": calculation_context
        }
        super().__init__(
            message=message,
            error_code="NUMERICAL_PRECISION_ERROR",
            details=details
        )
        self.value = value
        self.expected_range = expected_range
        self.calculation_context = calculation_context


class GEXCalculationError(AlphaGEXError):
    """
    Raised when GEX calculation fails or produces invalid results.

    Use this for:
    - Invalid input data for GEX calculation
    - GEX values outside plausible range
    - Missing required data for calculation
    """

    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        spot_price: Optional[float] = None,
        calculation_stage: Optional[str] = None
    ):
        details = {
            "symbol": symbol,
            "spot_price": spot_price,
            "calculation_stage": calculation_stage
        }
        super().__init__(
            message=message,
            error_code="GEX_CALCULATION_ERROR",
            details=details
        )


class GreeksCalculationError(AlphaGEXError):
    """Raised when Greeks calculation fails."""

    def __init__(
        self,
        message: str,
        greek: Optional[str] = None,
        strike: Optional[float] = None,
        spot_price: Optional[float] = None
    ):
        details = {
            "greek": greek,
            "strike": strike,
            "spot_price": spot_price
        }
        super().__init__(
            message=message,
            error_code="GREEKS_CALCULATION_ERROR",
            details=details
        )


# =============================================================================
# DATA VALIDATION ERRORS
# =============================================================================

class DataValidationError(AlphaGEXError):
    """
    Raised when input data fails validation.

    Use this for:
    - Invalid symbol format
    - Out-of-range values
    - Missing required fields
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        constraint: Optional[str] = None
    ):
        details = {
            "field": field,
            "value": str(value) if value is not None else None,
            "constraint": constraint
        }
        super().__init__(
            message=message,
            error_code="DATA_VALIDATION_ERROR",
            details=details
        )
        self.field = field
        self.value = value
        self.constraint = constraint


class InvalidOptionDataError(DataValidationError):
    """Raised when option contract data is invalid."""

    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        strike: Optional[float] = None,
        option_type: Optional[str] = None
    ):
        super().__init__(
            message=message,
            field="option_data",
            value=f"{symbol} {strike} {option_type}",
            constraint="Valid option contract"
        )
        self.symbol = symbol
        self.strike = strike
        self.option_type = option_type


class InvalidSymbolError(DataValidationError):
    """Raised when a trading symbol is invalid."""

    def __init__(self, symbol: str, reason: Optional[str] = None):
        message = f"Invalid symbol: {symbol}"
        if reason:
            message += f" - {reason}"
        super().__init__(
            message=message,
            field="symbol",
            value=symbol,
            constraint="Valid trading symbol"
        )


# =============================================================================
# DATA SOURCE ERRORS
# =============================================================================

class DataSourceError(AlphaGEXError):
    """
    Raised when a data source fails or returns invalid data.

    Use this for:
    - API connection failures
    - Rate limiting
    - Invalid response format
    """

    def __init__(
        self,
        message: str,
        source: str,
        status_code: Optional[int] = None,
        retryable: bool = True
    ):
        details = {
            "source": source,
            "status_code": status_code,
            "retryable": retryable
        }
        super().__init__(
            message=message,
            error_code="DATA_SOURCE_ERROR",
            details=details
        )
        self.source = source
        self.status_code = status_code
        self.retryable = retryable


class TradingVolatilityAPIError(DataSourceError):
    """Raised when TradingVolatility API fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(
            message=message,
            source="TradingVolatilityAPI",
            status_code=status_code,
            retryable=status_code in (429, 500, 502, 503, 504) if status_code else True
        )


class TradierAPIError(DataSourceError):
    """Raised when Tradier API fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(
            message=message,
            source="TradierAPI",
            status_code=status_code,
            retryable=status_code in (429, 500, 502, 503, 504) if status_code else True
        )


class PolygonAPIError(DataSourceError):
    """Raised when Polygon API fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(
            message=message,
            source="PolygonAPI",
            status_code=status_code,
            retryable=status_code in (429, 500, 502, 503, 504) if status_code else True
        )


# =============================================================================
# DATABASE ERRORS
# =============================================================================

class DatabaseError(AlphaGEXError):
    """
    Raised for database-related errors.

    Use this for:
    - Connection failures
    - Query errors
    - Transaction failures
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        retryable: bool = True
    ):
        # Never include sensitive info like connection strings
        details = {
            "operation": operation,
            "table": table,
            "retryable": retryable
        }
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details=details
        )
        self.operation = operation
        self.table = table
        self.retryable = retryable


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""

    def __init__(self, message: str = "Database connection failed"):
        # Never expose connection details
        super().__init__(
            message=message,
            operation="connect",
            retryable=True
        )


class DatabaseQueryError(DatabaseError):
    """Raised when a database query fails."""

    def __init__(self, message: str, table: Optional[str] = None):
        super().__init__(
            message=message,
            operation="query",
            table=table,
            retryable=False
        )


# =============================================================================
# TRADING ERRORS
# =============================================================================

class TradingError(AlphaGEXError):
    """Base class for trading-related errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "TRADING_ERROR",
        symbol: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        full_details = details or {}
        if symbol:
            full_details["symbol"] = symbol
        super().__init__(
            message=message,
            error_code=error_code,
            details=full_details
        )
        self.symbol = symbol


class RiskLimitExceededError(TradingError):
    """Raised when a trade would exceed risk limits."""

    def __init__(
        self,
        message: str,
        limit_type: str,
        current_value: float,
        limit_value: float,
        symbol: Optional[str] = None
    ):
        details = {
            "limit_type": limit_type,
            "current_value": current_value,
            "limit_value": limit_value
        }
        super().__init__(
            message=message,
            error_code="RISK_LIMIT_EXCEEDED",
            symbol=symbol,
            details=details
        )


class PositionNotFoundError(TradingError):
    """Raised when a position is not found."""

    def __init__(self, position_id: int, symbol: Optional[str] = None):
        super().__init__(
            message=f"Position not found: {position_id}",
            error_code="POSITION_NOT_FOUND",
            symbol=symbol,
            details={"position_id": position_id}
        )


class InsufficientCapitalError(TradingError):
    """Raised when there is insufficient capital for a trade."""

    def __init__(
        self,
        required: float,
        available: float,
        symbol: Optional[str] = None
    ):
        super().__init__(
            message=f"Insufficient capital: required ${required:.2f}, available ${available:.2f}",
            error_code="INSUFFICIENT_CAPITAL",
            symbol=symbol,
            details={"required": required, "available": available}
        )


# =============================================================================
# CONFIGURATION ERRORS
# =============================================================================

class ConfigurationError(AlphaGEXError):
    """Raised for configuration-related errors."""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        expected_type: Optional[str] = None
    ):
        details = {
            "config_key": config_key,
            "expected_type": expected_type
        }
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details
        )


class MissingConfigError(ConfigurationError):
    """Raised when required configuration is missing."""

    def __init__(self, config_key: str):
        super().__init__(
            message=f"Missing required configuration: {config_key}",
            config_key=config_key
        )


# =============================================================================
# SERVICE ERRORS
# =============================================================================

class ServiceUnavailableError(AlphaGEXError):
    """Raised when a required service is unavailable."""

    def __init__(
        self,
        service_name: str,
        reason: Optional[str] = None
    ):
        message = f"Service unavailable: {service_name}"
        if reason:
            message += f" - {reason}"
        super().__init__(
            message=message,
            error_code="SERVICE_UNAVAILABLE",
            details={"service": service_name, "reason": reason}
        )


class RateLimitError(AlphaGEXError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        service: str,
        retry_after: Optional[int] = None
    ):
        message = f"Rate limit exceeded for {service}"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            details={"service": service, "retry_after": retry_after}
        )
