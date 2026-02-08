"""
API Authentication Middleware for AlphaGEX

Provides:
1. API Key authentication for external services
2. Optional JWT token authentication
3. Rate limiting integration points
4. Request logging for security auditing

Usage:
    from backend.api.auth_middleware import require_api_key, require_auth

    @router.post("/api/fortress/trade")
    async def execute_trade(request: Request, auth: dict = Depends(require_api_key)):
        ...
"""

import os
import hmac
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import lru_cache

from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class AuthConfig:
    """Authentication configuration loaded from environment"""

    # API Key Settings
    API_KEY_HEADER = "X-API-Key"
    API_KEY_ENV_VAR = "ALPHAGEX_API_KEY"
    ADMIN_KEY_ENV_VAR = "ALPHAGEX_ADMIN_KEY"

    # JWT Settings (optional)
    JWT_SECRET_ENV_VAR = "ALPHAGEX_JWT_SECRET"
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_HOURS = 24

    # Rate limiting settings (per IP/key)
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_REQUESTS = 100  # requests per window
    RATE_LIMIT_WINDOW_SECONDS = 60  # 1 minute window

    # Paths that don't require authentication
    PUBLIC_PATHS = [
        "/health",
        "/api/health",
        "/api/system-health",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]

    # Paths that require admin-level access
    ADMIN_PATHS = [
        "/api/fortress/force-trade",
        "/api/solomon/force-trade",
        "/api/admin/",
        "/api/config/",
    ]

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        """Get the configured API key"""
        return os.getenv(cls.API_KEY_ENV_VAR)

    @classmethod
    def get_admin_key(cls) -> Optional[str]:
        """Get the configured admin API key"""
        return os.getenv(cls.ADMIN_KEY_ENV_VAR)

    @classmethod
    def get_jwt_secret(cls) -> Optional[str]:
        """Get the JWT secret for token signing"""
        return os.getenv(cls.JWT_SECRET_ENV_VAR)

    @classmethod
    def is_auth_enabled(cls) -> bool:
        """Check if authentication is enabled (API key configured)"""
        return cls.get_api_key() is not None


# =============================================================================
# Security Schemes
# =============================================================================

api_key_header = APIKeyHeader(name=AuthConfig.API_KEY_HEADER, auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


# =============================================================================
# Authentication Models
# =============================================================================

class AuthInfo(BaseModel):
    """Information about the authenticated request"""
    authenticated: bool = False
    auth_type: str = "none"  # "api_key", "jwt", "admin", "none"
    key_id: Optional[str] = None  # Hashed/truncated key identifier
    permissions: List[str] = []
    request_id: Optional[str] = None


class RateLimitInfo(BaseModel):
    """Rate limit status"""
    allowed: bool = True
    remaining: int = 0
    reset_at: Optional[datetime] = None
    limit: int = AuthConfig.RATE_LIMIT_REQUESTS


# =============================================================================
# Rate Limiting (In-memory, per-process)
# =============================================================================

_rate_limit_store: Dict[str, Dict[str, Any]] = {}


def _get_rate_limit_key(request: Request, api_key: Optional[str] = None) -> str:
    """Generate a rate limit key based on IP and API key"""
    client_ip = request.client.host if request.client else "unknown"

    if api_key:
        # Use hashed API key as identifier
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return f"key:{key_hash}"
    else:
        return f"ip:{client_ip}"


def check_rate_limit(request: Request, api_key: Optional[str] = None) -> RateLimitInfo:
    """Check if request is within rate limits"""
    if not AuthConfig.RATE_LIMIT_ENABLED:
        return RateLimitInfo(allowed=True, remaining=AuthConfig.RATE_LIMIT_REQUESTS)

    key = _get_rate_limit_key(request, api_key)
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=AuthConfig.RATE_LIMIT_WINDOW_SECONDS)

    if key not in _rate_limit_store:
        _rate_limit_store[key] = {
            "requests": [],
            "window_start": now
        }

    # Clean old requests outside window
    store = _rate_limit_store[key]
    store["requests"] = [ts for ts in store["requests"] if ts > window_start]

    # Check limit
    request_count = len(store["requests"])
    remaining = AuthConfig.RATE_LIMIT_REQUESTS - request_count

    if request_count >= AuthConfig.RATE_LIMIT_REQUESTS:
        reset_at = min(store["requests"]) + timedelta(seconds=AuthConfig.RATE_LIMIT_WINDOW_SECONDS)
        return RateLimitInfo(
            allowed=False,
            remaining=0,
            reset_at=reset_at,
            limit=AuthConfig.RATE_LIMIT_REQUESTS
        )

    # Record this request
    store["requests"].append(now)

    return RateLimitInfo(
        allowed=True,
        remaining=remaining - 1,
        limit=AuthConfig.RATE_LIMIT_REQUESTS
    )


# =============================================================================
# Authentication Functions
# =============================================================================

def _hash_key_for_logging(key: str) -> str:
    """Create a safe identifier for logging (first 4 chars + hash)"""
    if len(key) < 4:
        return "****"
    prefix = key[:4]
    hash_suffix = hashlib.sha256(key.encode()).hexdigest()[:8]
    return f"{prefix}...{hash_suffix}"


def verify_api_key(provided_key: str, expected_key: str) -> bool:
    """Securely compare API keys using constant-time comparison"""
    if not provided_key or not expected_key:
        return False
    return hmac.compare_digest(provided_key, expected_key)


async def get_api_key_auth(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> AuthInfo:
    """
    Validate API key from header.

    Returns AuthInfo with authentication status.
    Does NOT raise exceptions - allows optional auth.
    """
    auth_info = AuthInfo(request_id=secrets.token_hex(8))

    # Check if path is public
    path = request.url.path
    if any(path.startswith(public) for public in AuthConfig.PUBLIC_PATHS):
        auth_info.authenticated = True
        auth_info.auth_type = "public"
        return auth_info

    # No key provided
    if not api_key:
        return auth_info

    # Check against admin key first
    admin_key = AuthConfig.get_admin_key()
    if admin_key and verify_api_key(api_key, admin_key):
        auth_info.authenticated = True
        auth_info.auth_type = "admin"
        auth_info.key_id = _hash_key_for_logging(api_key)
        auth_info.permissions = ["read", "write", "admin"]
        logger.info(f"Admin auth successful: {auth_info.key_id}")
        return auth_info

    # Check against regular API key
    expected_key = AuthConfig.get_api_key()
    if expected_key and verify_api_key(api_key, expected_key):
        auth_info.authenticated = True
        auth_info.auth_type = "api_key"
        auth_info.key_id = _hash_key_for_logging(api_key)
        auth_info.permissions = ["read", "write"]
        return auth_info

    # Invalid key
    logger.warning(f"Invalid API key attempt: {_hash_key_for_logging(api_key)}")
    return auth_info


# =============================================================================
# Dependency Functions (for route protection)
# =============================================================================

async def require_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> AuthInfo:
    """
    Require valid API key authentication.

    Raises HTTPException if authentication fails.
    Use as dependency: Depends(require_api_key)
    """
    # Skip auth check if not configured
    if not AuthConfig.is_auth_enabled():
        return AuthInfo(
            authenticated=True,
            auth_type="disabled",
            permissions=["read", "write"]
        )

    auth_info = await get_api_key_auth(request, api_key)

    # Check rate limit
    rate_limit = check_rate_limit(request, api_key)
    if not rate_limit.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": rate_limit.limit,
                "reset_at": rate_limit.reset_at.isoformat() if rate_limit.reset_at else None
            }
        )

    if not auth_info.authenticated:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Invalid or missing API key",
                "header": AuthConfig.API_KEY_HEADER
            }
        )

    return auth_info


async def require_admin(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> AuthInfo:
    """
    Require admin-level authentication.

    Raises HTTPException if not authenticated or not admin.
    Use as dependency: Depends(require_admin)
    """
    auth_info = await require_api_key(request, api_key)

    if auth_info.auth_type != "admin":
        logger.warning(f"Admin access denied: {auth_info.key_id} (type: {auth_info.auth_type})")
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )

    return auth_info


async def optional_auth(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> AuthInfo:
    """
    Optional authentication - doesn't fail if no key provided.

    Use for endpoints that have different behavior for authenticated users.
    """
    return await get_api_key_auth(request, api_key)


# =============================================================================
# Middleware for Global Auth (optional)
# =============================================================================

class AuthMiddleware:
    """
    Global authentication middleware.

    Add to FastAPI app:
        app.add_middleware(AuthMiddleware)

    Note: For more granular control, use the Depends() functions above.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Extract path
            path = scope.get("path", "")

            # Skip auth for public paths
            if any(path.startswith(public) for public in AuthConfig.PUBLIC_PATHS):
                await self.app(scope, receive, send)
                return

            # For non-public paths, let the route handlers manage auth
            # This middleware just logs the request
            headers = dict(scope.get("headers", []))
            api_key = headers.get(AuthConfig.API_KEY_HEADER.lower().encode())

            if api_key:
                logger.debug(f"API request with key to {path}")
            else:
                logger.debug(f"Unauthenticated request to {path}")

        await self.app(scope, receive, send)


# =============================================================================
# Utility Functions
# =============================================================================

def generate_api_key(prefix: str = "agx") -> str:
    """
    Generate a secure API key.

    Format: prefix_base64(32 random bytes)
    Example: agx_a1b2c3d4e5f6g7h8...
    """
    random_bytes = secrets.token_bytes(32)
    key_part = secrets.token_urlsafe(32)
    return f"{prefix}_{key_part}"


def log_auth_event(
    event_type: str,
    auth_info: AuthInfo,
    request: Request,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an authentication event for security auditing.

    Events: "login", "logout", "access_denied", "rate_limited", "admin_action"
    """
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path

    log_data = {
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "client_ip": client_ip,
        "path": path,
        "auth_type": auth_info.auth_type,
        "key_id": auth_info.key_id,
        "request_id": auth_info.request_id,
    }

    if details:
        log_data.update(details)

    if event_type in ["access_denied", "rate_limited"]:
        logger.warning(f"Security event: {log_data}")
    else:
        logger.info(f"Auth event: {log_data}")


# =============================================================================
# Database integration (optional - for API key storage)
# =============================================================================

def get_api_keys_from_db() -> List[Dict[str, Any]]:
    """
    Retrieve API keys from database (if configured).

    Returns list of key configs with permissions.
    """
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT key_hash, key_prefix, permissions, created_at, expires_at
            FROM api_keys
            WHERE is_active = true
              AND (expires_at IS NULL OR expires_at > NOW())
        """)

        keys = []
        for row in cursor.fetchall():
            keys.append({
                "key_hash": row[0],
                "key_prefix": row[1],
                "permissions": row[2] or ["read"],
                "created_at": row[3],
                "expires_at": row[4]
            })

        conn.close()
        return keys

    except Exception as e:
        logger.debug(f"Could not load API keys from DB: {e}")
        return []


def create_api_keys_table_sql() -> str:
    """Return SQL to create API keys table."""
    return """
        CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            key_hash VARCHAR(64) UNIQUE NOT NULL,
            key_prefix VARCHAR(10) NOT NULL,
            description VARCHAR(255),
            permissions TEXT[] DEFAULT ARRAY['read'],
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP,
            last_used_at TIMESTAMP,
            created_by VARCHAR(100)
        );

        CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
        CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active) WHERE is_active = true;
    """
