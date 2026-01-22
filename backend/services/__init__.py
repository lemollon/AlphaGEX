"""
Backend Services Module

Contains background workers and job queue functionality.

Services:
- job_queue: PostgreSQL-backed job queue for async task processing
- backtest_worker: Background worker for processing backtest jobs
- bot_metrics_service: Unified metrics service for all trading bots (single source of truth)
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

from backend.services.bot_metrics_service import (
    BotName,
    BotCapitalConfig,
    BotMetricsSummary,
    BotMetricsService,
    get_metrics_service,
)

__all__ = [
    # Job Queue
    'JobType',
    'JobStatus',
    'enqueue_job',
    'enqueue_backtest_job',
    'enqueue_spx_backtest_job',
    'enqueue_ml_training_job',
    'get_job_status',
    'get_pending_jobs',
    'get_recent_jobs',
    # Bot Metrics Service
    'BotName',
    'BotCapitalConfig',
    'BotMetricsSummary',
    'BotMetricsService',
    'get_metrics_service',
]
