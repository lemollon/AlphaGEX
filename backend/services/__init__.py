"""
Backend Services Module

Contains background workers and job queue functionality.

Services:
- job_queue: PostgreSQL-backed job queue for async task processing
- backtest_worker: Background worker for processing backtest jobs
"""

from backend.services.job_queue import (
    JobType,
    JobStatus,
    enqueue_job,
    enqueue_backtest_job,
    enqueue_spx_backtest_job,
    enqueue_ml_training_job,
    get_job_status,
    get_pending_jobs,
    get_recent_jobs,
)

__all__ = [
    'JobType',
    'JobStatus',
    'enqueue_job',
    'enqueue_backtest_job',
    'enqueue_spx_backtest_job',
    'enqueue_ml_training_job',
    'get_job_status',
    'get_pending_jobs',
    'get_recent_jobs',
]
