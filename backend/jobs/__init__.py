"""
Background Jobs Package

Provides async job execution for long-running tasks.
"""

from .background_jobs import JobManager, JobStatus, JobResult, get_job_manager, job_manager

__all__ = ['JobManager', 'JobStatus', 'JobResult', 'get_job_manager', 'job_manager']
