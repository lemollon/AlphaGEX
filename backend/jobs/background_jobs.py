"""
Background Job System for AlphaGEX

Handles long-running tasks like backtests that would otherwise timeout.
Jobs run in background threads and persist status to database.

Usage:
    from backend.jobs.background_jobs import JobManager, job_manager

    # Start a backtest job
    job_id = job_manager.start_job('backtest', params={'symbol': 'SPX', 'days': 365})

    # Check status
    status = job_manager.get_job_status(job_id)
"""

import threading
import uuid
import traceback
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass, asdict
import json

from database_adapter import get_connection

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobResult:
    job_id: str
    job_type: str
    status: JobStatus
    progress: int  # 0-100
    message: str
    result: Optional[Dict] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self):
        d = asdict(self)
        d['status'] = self.status.value
        if self.started_at:
            d['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            d['completed_at'] = self.completed_at.isoformat()
        return d


class JobManager:
    """
    Manages background jobs with database persistence.
    Jobs continue running even if user closes browser.
    """

    def __init__(self):
        self._jobs: Dict[str, JobResult] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._ensure_table()
        self._load_running_jobs()

    def _ensure_table(self):
        """Create background_jobs table if not exists"""
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS background_jobs (
                    job_id VARCHAR(64) PRIMARY KEY,
                    job_type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    progress INT DEFAULT 0,
                    message TEXT,
                    params JSONB,
                    result JSONB,
                    error TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index for status queries
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_background_jobs_status
                ON background_jobs(status)
            """)

            conn.commit()
            conn.close()
            logger.info("Background jobs table ready")
        except Exception as e:
            logger.error(f"Error creating background_jobs table: {e}")

    def _load_running_jobs(self):
        """Load any jobs that were running when app restarted"""
        try:
            conn = get_connection()
            c = conn.cursor()

            # Mark any 'running' jobs as failed (they died with the app)
            c.execute("""
                UPDATE background_jobs
                SET status = 'failed',
                    error = 'Job interrupted by application restart',
                    completed_at = CURRENT_TIMESTAMP
                WHERE status = 'running'
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {e}")

    def start_job(self, job_type: str, params: Dict[str, Any],
                  runner: Optional[Callable] = None) -> str:
        """
        Start a new background job.

        Args:
            job_type: Type of job (e.g., 'spx_backtest', 'spy_backtest')
            params: Job parameters
            runner: Optional custom runner function

        Returns:
            job_id: Unique job identifier
        """
        job_id = str(uuid.uuid4())[:8]

        job = JobResult(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.PENDING,
            progress=0,
            message="Job queued",
            started_at=datetime.now()
        )

        self._jobs[job_id] = job
        self._save_job_to_db(job, params)

        # Start background thread
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, job_type, params, runner),
            daemon=True  # Don't block app shutdown
        )
        self._threads[job_id] = thread
        thread.start()

        logger.info(f"Started background job {job_id} ({job_type})")
        return job_id

    def _save_job_to_db(self, job: JobResult, params: Dict = None):
        """Save job status to database"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO background_jobs
                (job_id, job_type, status, progress, message, params, result, error, started_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    progress = EXCLUDED.progress,
                    message = EXCLUDED.message,
                    result = EXCLUDED.result,
                    error = EXCLUDED.error,
                    completed_at = EXCLUDED.completed_at
            """, (
                job.job_id,
                job.job_type,
                job.status.value,
                job.progress,
                job.message,
                json.dumps(params) if params else None,
                json.dumps(job.result) if job.result else None,
                job.error,
                job.started_at,
                job.completed_at
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving job to DB: {e}")

    def update_progress(self, job_id: str, progress: int, message: str = None):
        """Update job progress (call from within job runner)"""
        if job_id in self._jobs:
            self._jobs[job_id].progress = progress
            if message:
                self._jobs[job_id].message = message
            self._save_job_to_db(self._jobs[job_id])

    def _run_job(self, job_id: str, job_type: str, params: Dict,
                 custom_runner: Optional[Callable] = None):
        """Execute job in background thread"""
        job = self._jobs[job_id]
        job.status = JobStatus.RUNNING
        job.message = "Job starting..."
        self._save_job_to_db(job, params)

        try:
            # Get appropriate runner
            if custom_runner:
                runner = custom_runner
            else:
                runner = self._get_runner_for_type(job_type)

            if not runner:
                raise ValueError(f"No runner found for job type: {job_type}")

            # Run the job
            result = runner(job_id, params, self.update_progress)

            # Mark complete
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.message = "Job completed successfully"
            job.result = result
            job.completed_at = datetime.now()

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}\n{traceback.format_exc()}")
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.message = f"Job failed: {str(e)}"
            job.completed_at = datetime.now()

        self._save_job_to_db(job, params)
        logger.info(f"Job {job_id} finished with status: {job.status.value}")

    def _get_runner_for_type(self, job_type: str) -> Optional[Callable]:
        """Get the runner function for a job type"""
        runners = {
            'spx_backtest': self._run_spx_backtest,
            'spy_backtest': self._run_spy_backtest,
            'full_backtest': self._run_full_backtest,
            'ml_training': self._run_ml_training,
        }
        return runners.get(job_type)

    def _run_spx_backtest(self, job_id: str, params: Dict,
                          update_progress: Callable) -> Dict:
        """Run SPX wheel backtest"""
        from trading.spx_wheel_system import SPXWheelOptimizer

        update_progress(job_id, 5, "Initializing SPX backtester...")

        days = params.get('days', 365)
        optimizer = SPXWheelOptimizer()

        update_progress(job_id, 10, f"Loading {days} days of data...")

        # Run backtest with progress updates
        results = optimizer.backtest(
            start_date=None,  # Will use days param
            end_date=None,
            params=params,
            progress_callback=lambda p, m: update_progress(job_id, 10 + int(p * 0.85), m)
        )

        update_progress(job_id, 95, "Generating report...")

        return results

    def _run_spy_backtest(self, job_id: str, params: Dict,
                          update_progress: Callable) -> Dict:
        """Run SPY trader backtest"""
        update_progress(job_id, 5, "Initializing SPY backtester...")

        # Import backtester
        try:
            from core.unified_backtester import UnifiedBacktester
            backtester = UnifiedBacktester()
        except ImportError:
            from core.autonomous_paper_trader import AutonomousPaperTrader
            backtester = AutonomousPaperTrader(symbol='SPY')

        days = params.get('days', 90)
        update_progress(job_id, 10, f"Running {days}-day backtest...")

        # Run backtest
        results = backtester.run_backtest(
            days=days,
            progress_callback=lambda p, m: update_progress(job_id, 10 + int(p * 0.85), m)
        ) if hasattr(backtester, 'run_backtest') else {'error': 'Backtest not implemented'}

        update_progress(job_id, 95, "Generating report...")

        return results

    def _run_full_backtest(self, job_id: str, params: Dict,
                           update_progress: Callable) -> Dict:
        """Run full multi-symbol backtest"""
        update_progress(job_id, 5, "Starting full backtest...")

        symbols = params.get('symbols', ['SPY', 'SPX'])
        results = {}

        for i, symbol in enumerate(symbols):
            progress_base = 5 + (i * 90 // len(symbols))
            update_progress(job_id, progress_base, f"Backtesting {symbol}...")

            if symbol == 'SPX':
                results[symbol] = self._run_spx_backtest(
                    job_id, params,
                    lambda jid, p, m: update_progress(
                        job_id,
                        progress_base + int(p * 0.9 / len(symbols)),
                        f"{symbol}: {m}"
                    )
                )
            else:
                results[symbol] = self._run_spy_backtest(
                    job_id, {**params, 'symbol': symbol},
                    lambda jid, p, m: update_progress(
                        job_id,
                        progress_base + int(p * 0.9 / len(symbols)),
                        f"{symbol}: {m}"
                    )
                )

        return results

    def _run_ml_training(self, job_id: str, params: Dict,
                         update_progress: Callable) -> Dict:
        """Run ML model training"""
        update_progress(job_id, 5, "Loading training data...")

        from ai.autonomous_ml_pattern_learner import get_pattern_learner
        learner = get_pattern_learner()

        update_progress(job_id, 20, "Training model...")

        lookback_days = params.get('lookback_days', 180)
        result = learner.train_pattern_classifier(lookback_days=lookback_days)

        update_progress(job_id, 90, "Saving model...")

        if result.get('trained'):
            learner.save_model()

        return result

    def get_job_status(self, job_id: str) -> Optional[JobResult]:
        """Get current status of a job"""
        # Check in-memory first
        if job_id in self._jobs:
            return self._jobs[job_id]

        # Load from database
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT job_id, job_type, status, progress, message,
                       result, error, started_at, completed_at
                FROM background_jobs WHERE job_id = %s
            """, (job_id,))

            row = c.fetchone()
            conn.close()

            if row:
                return JobResult(
                    job_id=row[0],
                    job_type=row[1],
                    status=JobStatus(row[2]),
                    progress=row[3] or 0,
                    message=row[4] or "",
                    result=row[5],
                    error=row[6],
                    started_at=row[7],
                    completed_at=row[8]
                )
        except Exception as e:
            logger.error(f"Error loading job {job_id}: {e}")

        return None

    def list_jobs(self, status: Optional[str] = None, limit: int = 20) -> list:
        """List recent jobs, optionally filtered by status"""
        try:
            conn = get_connection()
            c = conn.cursor()

            if status:
                c.execute("""
                    SELECT job_id, job_type, status, progress, message,
                           started_at, completed_at
                    FROM background_jobs
                    WHERE status = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (status, limit))
            else:
                c.execute("""
                    SELECT job_id, job_type, status, progress, message,
                           started_at, completed_at
                    FROM background_jobs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))

            rows = c.fetchall()
            conn.close()

            return [{
                'job_id': r[0],
                'job_type': r[1],
                'status': r[2],
                'progress': r[3],
                'message': r[4],
                'started_at': r[5].isoformat() if r[5] else None,
                'completed_at': r[6].isoformat() if r[6] else None
            } for r in rows]

        except Exception as e:
            logger.error(f"Error listing jobs: {e}")
            return []

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job (best effort)"""
        if job_id in self._jobs:
            self._jobs[job_id].status = JobStatus.CANCELLED
            self._jobs[job_id].message = "Job cancelled by user"
            self._jobs[job_id].completed_at = datetime.now()
            self._save_job_to_db(self._jobs[job_id])
            return True
        return False


# Singleton instance
job_manager = JobManager()


def get_job_manager() -> JobManager:
    """Get the singleton job manager"""
    return job_manager
