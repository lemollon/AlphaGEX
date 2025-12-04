"""
Simple Job Queue for Background Tasks

Uses PostgreSQL as the job store - no external dependencies like Redis.
Perfect for Render deployment where we want to keep things simple.

Usage:
    # Enqueue a job
    job_id = enqueue_backtest_job(config)

    # Check status
    status = get_job_status(job_id)

    # Worker processes jobs
    process_pending_jobs()
"""

import os
import sys
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database_adapter import get_connection
import psycopg2.extras

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    BACKTEST = "backtest"
    ML_TRAINING = "ml_training"
    SPX_BACKTEST = "spx_backtest"


def ensure_job_table():
    """Create job queue table if it doesn't exist"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS background_jobs (
                job_id VARCHAR(64) PRIMARY KEY,
                job_type VARCHAR(32) NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'pending',
                config JSONB,
                result JSONB,
                error TEXT,
                progress INTEGER DEFAULT 0,
                progress_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                worker_id VARCHAR(64)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON background_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_created ON background_jobs(created_at);
        ''')
        conn.commit()
        conn.close()
        logger.info("Job queue table ready")
    except Exception as e:
        logger.error(f"Error creating job table: {e}")


def enqueue_job(job_type: JobType, config: Dict[str, Any]) -> str:
    """
    Add a job to the queue.

    Returns:
        job_id: Unique identifier to track the job
    """
    ensure_job_table()

    job_id = f"{job_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO background_jobs (job_id, job_type, status, config)
            VALUES (%s, %s, %s, %s)
        ''', (job_id, job_type.value, JobStatus.PENDING.value, json.dumps(config)))
        conn.commit()
        conn.close()

        logger.info(f"Enqueued job {job_id}")
        return job_id

    except Exception as e:
        logger.error(f"Error enqueueing job: {e}")
        raise


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get current status of a job"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT job_id, job_type, status, progress, progress_message,
                   config, result, error, created_at, started_at, completed_at
            FROM background_jobs
            WHERE job_id = %s
        ''', (job_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "job_id": row['job_id'],
            "job_type": row['job_type'],
            "status": row['status'],
            "progress": row['progress'] or 0,
            "progress_message": row['progress_message'],
            "config": row['config'],
            "result": row['result'],
            "error": row['error'],
            "created_at": row['created_at'].isoformat() if row['created_at'] else None,
            "started_at": row['started_at'].isoformat() if row['started_at'] else None,
            "completed_at": row['completed_at'].isoformat() if row['completed_at'] else None,
            "duration_seconds": (row['completed_at'] - row['started_at']).total_seconds()
                if row['completed_at'] and row['started_at'] else None
        }

    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        return None


def update_job_progress(job_id: str, progress: int, message: str = None):
    """Update job progress (0-100)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE background_jobs
            SET progress = %s, progress_message = %s
            WHERE job_id = %s
        ''', (progress, message, job_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating progress: {e}")


def start_job(job_id: str, worker_id: str):
    """Mark job as running"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE background_jobs
            SET status = %s, started_at = NOW(), worker_id = %s
            WHERE job_id = %s AND status = %s
        ''', (JobStatus.RUNNING.value, worker_id, job_id, JobStatus.PENDING.value))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    except Exception as e:
        logger.error(f"Error starting job: {e}")
        return False


def complete_job(job_id: str, result: Dict[str, Any]):
    """Mark job as completed with results"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE background_jobs
            SET status = %s, result = %s, completed_at = NOW(), progress = 100
            WHERE job_id = %s
        ''', (JobStatus.COMPLETED.value, json.dumps(result), job_id))
        conn.commit()
        conn.close()
        logger.info(f"Job {job_id} completed")
    except Exception as e:
        logger.error(f"Error completing job: {e}")


def fail_job(job_id: str, error: str):
    """Mark job as failed with error"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE background_jobs
            SET status = %s, error = %s, completed_at = NOW()
            WHERE job_id = %s
        ''', (JobStatus.FAILED.value, error, job_id))
        conn.commit()
        conn.close()
        logger.error(f"Job {job_id} failed: {error}")
    except Exception as e:
        logger.error(f"Error failing job: {e}")


def get_pending_jobs(job_type: Optional[JobType] = None, limit: int = 10) -> list:
    """Get pending jobs to process"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if job_type:
            cursor.execute('''
                SELECT job_id, job_type, config
                FROM background_jobs
                WHERE status = %s AND job_type = %s
                ORDER BY created_at ASC
                LIMIT %s
            ''', (JobStatus.PENDING.value, job_type.value, limit))
        else:
            cursor.execute('''
                SELECT job_id, job_type, config
                FROM background_jobs
                WHERE status = %s
                ORDER BY created_at ASC
                LIMIT %s
            ''', (JobStatus.PENDING.value, limit))

        jobs = cursor.fetchall()
        conn.close()
        return [dict(j) for j in jobs]

    except Exception as e:
        logger.error(f"Error getting pending jobs: {e}")
        return []


def get_recent_jobs(limit: int = 20) -> list:
    """Get recent jobs for dashboard display"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT job_id, job_type, status, progress, progress_message,
                   created_at, started_at, completed_at, error
            FROM background_jobs
            ORDER BY created_at DESC
            LIMIT %s
        ''', (limit,))
        jobs = cursor.fetchall()
        conn.close()

        return [{
            "job_id": j['job_id'],
            "job_type": j['job_type'],
            "status": j['status'],
            "progress": j['progress'] or 0,
            "progress_message": j['progress_message'],
            "created_at": j['created_at'].isoformat() if j['created_at'] else None,
            "started_at": j['started_at'].isoformat() if j['started_at'] else None,
            "completed_at": j['completed_at'].isoformat() if j['completed_at'] else None,
            "error": j['error']
        } for j in jobs]

    except Exception as e:
        logger.error(f"Error getting recent jobs: {e}")
        return []


def cleanup_old_jobs(days: int = 7):
    """Remove jobs older than X days"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM background_jobs
            WHERE created_at < NOW() - INTERVAL '%s days'
        ''', (days,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info(f"Cleaned up {deleted} old jobs")
        return deleted
    except Exception as e:
        logger.error(f"Error cleaning up jobs: {e}")
        return 0


# Convenience functions for specific job types
def enqueue_backtest_job(config: Dict[str, Any]) -> str:
    """Enqueue a pattern backtest job"""
    return enqueue_job(JobType.BACKTEST, config)


def enqueue_spx_backtest_job(config: Dict[str, Any]) -> str:
    """Enqueue an SPX wheel backtest job"""
    return enqueue_job(JobType.SPX_BACKTEST, config)


def enqueue_ml_training_job(config: Dict[str, Any]) -> str:
    """Enqueue an ML training job"""
    return enqueue_job(JobType.ML_TRAINING, config)
