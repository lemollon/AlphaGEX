"""
KRONOS Infrastructure Module

Provides enterprise-grade infrastructure for KRONOS backtesting:
1. Redis/PostgreSQL job storage (persistent across restarts)
2. Database connection pooling (better performance)
3. ORAT data caching (faster backtests)
4. WebSocket manager for live updates

Usage:
    from backend.services.kronos_infrastructure import (
        job_store, connection_pool, orat_cache, ws_manager
    )
"""

import os
import sys
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum
import threading

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger(__name__)

# =============================================================================
# 1. JOB STORAGE - Redis with PostgreSQL fallback
# =============================================================================

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class KronosJob:
    """Job data structure for KRONOS backtests"""
    job_id: str
    status: str = "pending"
    progress: int = 0
    progress_message: str = ""
    config: Dict[str, Any] = None
    result: Dict[str, Any] = None
    error: Optional[str] = None
    created_at: str = None
    completed_at: Optional[str] = None
    original_query: Optional[str] = None  # For NLP backtests
    parsing_method: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'job_id': self.job_id,
            'status': self.status,
            'progress': self.progress,
            'progress_message': self.progress_message,
            'config': self.config,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at,
            'completed_at': self.completed_at,
            'original_query': self.original_query,
            'parsing_method': self.parsing_method,
        }


class JobStore:
    """
    Persistent job storage with Redis primary and PostgreSQL fallback.

    Jobs survive server restarts unlike in-memory storage.
    """

    def __init__(self):
        self._redis = None
        self._redis_available = False
        self._pg_available = False
        self._memory_fallback: Dict[str, KronosJob] = {}
        self._lock = threading.Lock()
        self._job_ttl = 86400 * 7  # 7 days

        self._init_storage()

    def _init_storage(self):
        """Initialize storage backends"""
        # Try Redis first
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                self._redis_available = True
                logger.info("Job storage: Using Redis")
            except Exception as e:
                logger.warning(f"Redis not available: {e}")
                self._redis = None

        # Check PostgreSQL availability
        try:
            from database_adapter import is_database_available
            self._pg_available = is_database_available()
            if self._pg_available:
                self._ensure_job_table()
                logger.info("Job storage: PostgreSQL available as fallback")
        except Exception as e:
            logger.warning(f"PostgreSQL not available: {e}")

        if not self._redis_available and not self._pg_available:
            logger.warning("Job storage: Using in-memory fallback (jobs will be lost on restart)")

    def _ensure_job_table(self):
        """Create job table if it doesn't exist"""
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kronos_jobs (
                    job_id VARCHAR(100) PRIMARY KEY,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    progress_message TEXT,
                    config JSONB,
                    result JSONB,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP,
                    original_query TEXT,
                    parsing_method VARCHAR(50)
                );
                CREATE INDEX IF NOT EXISTS idx_kronos_jobs_status ON kronos_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_kronos_jobs_created ON kronos_jobs(created_at);
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to create kronos_jobs table: {e}")

    def _redis_key(self, job_id: str) -> str:
        return f"kronos:job:{job_id}"

    def create(self, job: KronosJob) -> bool:
        """Create a new job"""
        job.created_at = job.created_at or datetime.now().isoformat()

        if self._redis_available:
            try:
                key = self._redis_key(job.job_id)
                self._redis.setex(key, self._job_ttl, json.dumps(job.to_dict()))
                # Also add to active jobs set
                self._redis.sadd("kronos:active_jobs", job.job_id)
                return True
            except Exception as e:
                logger.error(f"Redis create failed: {e}")

        if self._pg_available:
            try:
                from database_adapter import get_connection
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO kronos_jobs (job_id, status, progress, progress_message, config, created_at, original_query, parsing_method)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        progress = EXCLUDED.progress,
                        progress_message = EXCLUDED.progress_message,
                        config = EXCLUDED.config
                """, (
                    job.job_id, job.status, job.progress, job.progress_message,
                    json.dumps(job.config) if job.config else None,
                    job.created_at, job.original_query, job.parsing_method
                ))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logger.error(f"PostgreSQL create failed: {e}")

        # Memory fallback
        with self._lock:
            self._memory_fallback[job.job_id] = job
        return True

    def get(self, job_id: str) -> Optional[KronosJob]:
        """Get a job by ID"""
        if self._redis_available:
            try:
                data = self._redis.get(self._redis_key(job_id))
                if data:
                    d = json.loads(data)
                    return KronosJob(**d)
            except Exception as e:
                logger.error(f"Redis get failed: {e}")

        if self._pg_available:
            try:
                from database_adapter import get_connection
                import psycopg2.extras
                conn = get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("SELECT * FROM kronos_jobs WHERE job_id = %s", (job_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return KronosJob(
                        job_id=row['job_id'],
                        status=row['status'],
                        progress=row['progress'] or 0,
                        progress_message=row['progress_message'] or '',
                        config=row['config'],
                        result=row['result'],
                        error=row['error'],
                        created_at=row['created_at'].isoformat() if row['created_at'] else None,
                        completed_at=row['completed_at'].isoformat() if row['completed_at'] else None,
                        original_query=row.get('original_query'),
                        parsing_method=row.get('parsing_method'),
                    )
            except Exception as e:
                logger.error(f"PostgreSQL get failed: {e}")

        # Memory fallback
        with self._lock:
            return self._memory_fallback.get(job_id)

    def update(self, job_id: str, **updates) -> bool:
        """Update job fields"""
        if self._redis_available:
            try:
                job = self.get(job_id)
                if job:
                    for key, value in updates.items():
                        if hasattr(job, key):
                            setattr(job, key, value)
                    self._redis.setex(self._redis_key(job_id), self._job_ttl, json.dumps(job.to_dict()))
                    return True
            except Exception as e:
                logger.error(f"Redis update failed: {e}")

        if self._pg_available:
            try:
                from database_adapter import get_connection
                conn = get_connection()
                cursor = conn.cursor()

                # Build dynamic update
                set_clauses = []
                values = []
                for key, value in updates.items():
                    if key in ('config', 'result'):
                        set_clauses.append(f"{key} = %s")
                        values.append(json.dumps(value) if value else None)
                    else:
                        set_clauses.append(f"{key} = %s")
                        values.append(value)

                values.append(job_id)
                cursor.execute(
                    f"UPDATE kronos_jobs SET {', '.join(set_clauses)} WHERE job_id = %s",
                    values
                )
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logger.error(f"PostgreSQL update failed: {e}")

        # Memory fallback
        with self._lock:
            job = self._memory_fallback.get(job_id)
            if job:
                for key, value in updates.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                return True
        return False

    def get_active_jobs(self) -> List[Dict[str, Any]]:
        """Get all running/pending jobs"""
        jobs = []

        if self._redis_available:
            try:
                job_ids = self._redis.smembers("kronos:active_jobs")
                for job_id in job_ids:
                    job = self.get(job_id)
                    if job and job.status in ('pending', 'running'):
                        jobs.append(job.to_dict())
                    elif job and job.status in ('completed', 'failed'):
                        # Remove from active set
                        self._redis.srem("kronos:active_jobs", job_id)
                return jobs
            except Exception as e:
                logger.error(f"Redis get_active failed: {e}")

        if self._pg_available:
            try:
                from database_adapter import get_connection
                import psycopg2.extras
                conn = get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute("""
                    SELECT job_id, status, progress, progress_message, created_at
                    FROM kronos_jobs
                    WHERE status IN ('pending', 'running')
                    ORDER BY created_at DESC
                """)
                for row in cursor.fetchall():
                    jobs.append({
                        'job_id': row['job_id'],
                        'status': row['status'],
                        'progress': row['progress'] or 0,
                        'progress_message': row['progress_message'],
                    })
                conn.close()
                return jobs
            except Exception as e:
                logger.error(f"PostgreSQL get_active failed: {e}")

        # Memory fallback
        with self._lock:
            for job in self._memory_fallback.values():
                if job.status in ('pending', 'running'):
                    jobs.append(job.to_dict())
        return jobs

    def contains(self, job_id: str) -> bool:
        """Check if job exists"""
        return self.get(job_id) is not None

    def get_storage_type(self) -> str:
        """Return current storage type"""
        if self._redis_available:
            return "redis"
        if self._pg_available:
            return "postgresql"
        return "memory"


# =============================================================================
# 2. CONNECTION POOLING
# =============================================================================

class ConnectionPool:
    """
    Database connection pool for better performance.

    Reuses connections instead of creating new ones for each request.
    """

    def __init__(self, min_connections: int = 2, max_connections: int = 10):
        self._pool = None
        self._min_connections = min_connections
        self._max_connections = max_connections
        self._initialized = False
        self._lock = threading.Lock()

    def _init_pool(self):
        """Initialize the connection pool"""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            database_url = os.getenv('DATABASE_URL') or os.getenv('ORAT_DATABASE_URL')
            if not database_url:
                logger.warning("No DATABASE_URL, connection pooling disabled")
                return

            try:
                from urllib.parse import urlparse
                from psycopg2 import pool

                result = urlparse(database_url)
                self._pool = pool.ThreadedConnectionPool(
                    self._min_connections,
                    self._max_connections,
                    host=result.hostname,
                    port=result.port or 5432,
                    user=result.username,
                    password=result.password,
                    database=result.path[1:],
                    connect_timeout=30,
                    options='-c statement_timeout=300000',
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5
                )
                self._initialized = True
                logger.info(f"Connection pool initialized: {self._min_connections}-{self._max_connections} connections")
            except Exception as e:
                logger.error(f"Failed to initialize connection pool: {e}")

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager)"""
        self._init_pool()

        if not self._pool:
            # Fallback to direct connection
            from database_adapter import get_connection
            conn = get_connection()
            try:
                yield conn
            finally:
                conn.close()
            return

        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        finally:
            if conn:
                self._pool.putconn(conn)

    def close_all(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.closeall()
            self._initialized = False
            logger.info("Connection pool closed")

    @property
    def is_available(self) -> bool:
        """Check if pool is available"""
        self._init_pool()
        return self._pool is not None


# =============================================================================
# 3. ORAT DATA CACHING
# =============================================================================

class ORATCache:
    """
    Cache for ORAT options data to speed up backtests.

    Caches frequently accessed date ranges in memory or Redis.
    """

    def __init__(self, max_memory_mb: int = 500):
        self._memory_cache: Dict[str, Any] = {}
        self._cache_stats = {'hits': 0, 'misses': 0}
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._current_memory = 0
        self._redis = None
        self._redis_available = False
        self._lock = threading.Lock()
        self._cache_ttl = 3600  # 1 hour

        self._init_redis()

    def _init_redis(self):
        """Initialize Redis for distributed caching"""
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url, decode_responses=False)
                self._redis.ping()
                self._redis_available = True
                logger.info("ORAT Cache: Redis enabled for distributed caching")
            except Exception as e:
                logger.warning(f"ORAT Cache: Redis not available: {e}")

    def _cache_key(self, ticker: str, trade_date: str, dte: Optional[int] = None) -> str:
        """Generate cache key"""
        if dte is not None:
            return f"orat:{ticker}:{trade_date}:{dte}"
        return f"orat:{ticker}:{trade_date}"

    def get_options_data(self, ticker: str, trade_date: str, dte: Optional[int] = None) -> Optional[List[Dict]]:
        """Get cached options data"""
        key = self._cache_key(ticker, trade_date, dte)

        # Check memory cache first
        with self._lock:
            if key in self._memory_cache:
                self._cache_stats['hits'] += 1
                return self._memory_cache[key]['data']

        # Check Redis cache
        if self._redis_available:
            try:
                import pickle
                data = self._redis.get(f"orat_cache:{key}")
                if data:
                    self._cache_stats['hits'] += 1
                    result = pickle.loads(data)
                    # Store in memory for faster access
                    self._store_in_memory(key, result)
                    return result
            except Exception as e:
                logger.debug(f"Redis cache get failed: {e}")

        self._cache_stats['misses'] += 1
        return None

    def set_options_data(self, ticker: str, trade_date: str, data: List[Dict], dte: Optional[int] = None):
        """Cache options data"""
        key = self._cache_key(ticker, trade_date, dte)

        # Store in memory
        self._store_in_memory(key, data)

        # Store in Redis for distributed access
        if self._redis_available:
            try:
                import pickle
                self._redis.setex(
                    f"orat_cache:{key}",
                    self._cache_ttl,
                    pickle.dumps(data)
                )
            except Exception as e:
                logger.debug(f"Redis cache set failed: {e}")

    def _store_in_memory(self, key: str, data: List[Dict]):
        """Store in memory cache with size management"""
        import sys
        data_size = sys.getsizeof(data)

        with self._lock:
            # Evict old entries if necessary
            while self._current_memory + data_size > self._max_memory_bytes and self._memory_cache:
                oldest_key = next(iter(self._memory_cache))
                old_size = self._memory_cache[oldest_key].get('size', 0)
                del self._memory_cache[oldest_key]
                self._current_memory -= old_size

            self._memory_cache[key] = {
                'data': data,
                'size': data_size,
                'timestamp': datetime.now()
            }
            self._current_memory += data_size

    def preload_date_range(self, ticker: str, start_date: str, end_date: str):
        """
        Preload ORAT data for a date range.

        Call this before running a backtest to warm up the cache.
        """
        try:
            from database_adapter import get_connection
            import psycopg2.extras

            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get all trading days in range
            cursor.execute("""
                SELECT DISTINCT trade_date FROM orat_options_eod
                WHERE ticker = %s AND trade_date BETWEEN %s AND %s
                ORDER BY trade_date
            """, (ticker, start_date, end_date))

            dates = [row['trade_date'].strftime('%Y-%m-%d') for row in cursor.fetchall()]

            # Load data for each date
            loaded = 0
            for date in dates:
                if not self.get_options_data(ticker, date):
                    cursor.execute("""
                        SELECT * FROM orat_options_eod
                        WHERE ticker = %s AND trade_date = %s
                    """, (ticker, date))
                    data = [dict(row) for row in cursor.fetchall()]
                    if data:
                        # Convert dates to strings for JSON serialization
                        for row in data:
                            for key, value in row.items():
                                if hasattr(value, 'isoformat'):
                                    row[key] = value.isoformat()
                        self.set_options_data(ticker, date, data)
                        loaded += 1

            conn.close()
            logger.info(f"ORAT Cache: Preloaded {loaded} days for {ticker}")
            return loaded

        except Exception as e:
            logger.error(f"ORAT preload failed: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        hit_rate = 0
        total = self._cache_stats['hits'] + self._cache_stats['misses']
        if total > 0:
            hit_rate = self._cache_stats['hits'] / total * 100

        return {
            'hits': self._cache_stats['hits'],
            'misses': self._cache_stats['misses'],
            'hit_rate_pct': round(hit_rate, 2),
            'memory_entries': len(self._memory_cache),
            'memory_used_mb': round(self._current_memory / 1024 / 1024, 2),
            'redis_available': self._redis_available,
        }

    def clear(self):
        """Clear all caches"""
        with self._lock:
            self._memory_cache.clear()
            self._current_memory = 0
            self._cache_stats = {'hits': 0, 'misses': 0}

        if self._redis_available:
            try:
                # Delete all ORAT cache keys
                keys = self._redis.keys("orat_cache:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception as e:
                logger.error(f"Redis cache clear failed: {e}")

        logger.info("ORAT Cache cleared")


# =============================================================================
# 4. WEBSOCKET MANAGER FOR LIVE KRONOS UPDATES
# =============================================================================

class KronosWebSocketManager:
    """
    WebSocket manager for real-time KRONOS updates.

    Allows multiple clients to subscribe to job progress updates.
    """

    def __init__(self):
        self._connections: Dict[str, set] = {}  # job_id -> set of websockets
        self._all_connections: set = set()
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
        self._sync_lock = threading.Lock()

    async def connect(self, websocket, job_id: Optional[str] = None):
        """Register a new WebSocket connection"""
        async with self._lock:
            self._all_connections.add(websocket)
            if job_id:
                if job_id not in self._connections:
                    self._connections[job_id] = set()
                self._connections[job_id].add(websocket)

        logger.debug(f"WebSocket connected: {job_id or 'general'}")

    async def disconnect(self, websocket):
        """Unregister a WebSocket connection"""
        async with self._lock:
            self._all_connections.discard(websocket)
            for job_connections in self._connections.values():
                job_connections.discard(websocket)

        logger.debug("WebSocket disconnected")

    async def broadcast_job_update(self, job_id: str, data: Dict[str, Any]):
        """Broadcast job update to all subscribed clients"""
        message = json.dumps({
            'type': 'job_update',
            'job_id': job_id,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })

        async with self._lock:
            # Send to job-specific subscribers
            if job_id in self._connections:
                dead_connections = set()
                for websocket in self._connections[job_id]:
                    try:
                        await websocket.send_text(message)
                    except Exception:
                        dead_connections.add(websocket)

                # Clean up dead connections
                for ws in dead_connections:
                    self._connections[job_id].discard(ws)
                    self._all_connections.discard(ws)

    async def broadcast_gex_update(self, data: Dict[str, Any]):
        """Broadcast GEX data update to all connected clients"""
        message = json.dumps({
            'type': 'gex_update',
            'data': data,
            'timestamp': datetime.now().isoformat()
        })

        async with self._lock:
            dead_connections = set()
            for websocket in self._all_connections:
                try:
                    await websocket.send_text(message)
                except Exception:
                    dead_connections.add(websocket)

            # Clean up
            for ws in dead_connections:
                self._all_connections.discard(ws)

    def sync_broadcast_job_update(self, job_id: str, data: Dict[str, Any]):
        """Synchronous wrapper for broadcasting job updates (for use in non-async code)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.broadcast_job_update(job_id, data))
            else:
                loop.run_until_complete(self.broadcast_job_update(job_id, data))
        except RuntimeError:
            # No event loop, skip WebSocket broadcast
            pass

    @property
    def connection_count(self) -> int:
        """Get number of active connections"""
        return len(self._all_connections)


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================

# Initialize singletons
job_store = JobStore()
connection_pool = ConnectionPool()
orat_cache = ORATCache()
ws_manager = KronosWebSocketManager()


def get_infrastructure_status() -> Dict[str, Any]:
    """Get status of all infrastructure components"""
    return {
        'job_store': {
            'type': job_store.get_storage_type(),
            'active_jobs': len(job_store.get_active_jobs()),
        },
        'connection_pool': {
            'available': connection_pool.is_available,
        },
        'orat_cache': orat_cache.get_stats(),
        'websocket': {
            'connections': ws_manager.connection_count,
        }
    }


# =============================================================================
# INTEGRATION WITH EXISTING KRONOS ROUTES
# =============================================================================

def migrate_to_persistent_storage(legacy_jobs: Dict[str, Dict]):
    """
    Migrate in-memory jobs to persistent storage.

    Call this on startup to preserve any jobs from the old in-memory system.
    """
    migrated = 0
    for job_id, job_data in legacy_jobs.items():
        if not job_store.contains(job_id):
            job = KronosJob(
                job_id=job_id,
                status=job_data.get('status', 'pending'),
                progress=job_data.get('progress', 0),
                progress_message=job_data.get('progress_message', ''),
                config=job_data.get('config'),
                result=job_data.get('result'),
                error=job_data.get('error'),
                created_at=job_data.get('created_at'),
                completed_at=job_data.get('completed_at'),
            )
            job_store.create(job)
            migrated += 1

    if migrated > 0:
        logger.info(f"Migrated {migrated} jobs to persistent storage")

    return migrated
