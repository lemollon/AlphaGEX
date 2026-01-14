#!/usr/bin/env python3
"""
Background Backtest Worker Service

This runs as a separate Render service (Background Worker) to process
long-running backtest jobs without HTTP timeouts.

Render Configuration:
    Service Type: Background Worker
    Start Command: python backend/services/backtest_worker.py
    Instance Type: Starter (or higher for better performance)

Usage:
    # Direct execution
    python backend/services/backtest_worker.py

    # Or as module
    python -m backend.services.backtest_worker
"""

import os
import sys
import time
import signal
import logging
import uuid
from datetime import datetime

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("backtest_worker")

from backend.services.job_queue import (
    JobType, JobStatus,
    get_pending_jobs, start_job, complete_job, fail_job,
    update_job_progress, cleanup_old_jobs
)


# Worker configuration
WORKER_ID = f"worker_{uuid.uuid4().hex[:8]}"
POLL_INTERVAL = 5  # seconds between polling for jobs
BATCH_SIZE = 10    # ML scoring batch size
MAX_TRADES_PER_BATCH = 50  # Process trades in batches to update progress


# Graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    global shutdown_requested
    logger.info(f"Received signal {signum}, requesting shutdown...")
    shutdown_requested = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def process_backtest_job(job_id: str, config: dict) -> dict:
    """
    Process a pattern backtest job.

    This runs the autonomous_backtest_engine with progress updates.
    """
    logger.info(f"Processing backtest job {job_id}")
    update_job_progress(job_id, 5, "Initializing backtester...")

    try:
        from backtest.autonomous_backtest_engine import get_backtester

        lookback_days = config.get('lookback_days', 90)
        strategies = config.get('strategies')

        update_job_progress(job_id, 10, f"Running backtests ({lookback_days} day lookback)...")

        backtester = get_backtester()

        # Run backtest
        results = backtester.backtest_all_patterns_and_save(
            lookback_days=lookback_days,
            save_to_db=True
        )

        update_job_progress(job_id, 90, "Analyzing results...")

        # Count patterns with actual data
        patterns_with_data = sum(1 for r in results if r.get('total_signals', 0) > 0)

        update_job_progress(job_id, 100, "Complete!")

        return {
            "success": True,
            "message": f"Backtest complete - {patterns_with_data} patterns with signals",
            "total_patterns": len(results),
            "patterns_with_signals": patterns_with_data,
            "lookback_days": lookback_days,
            "timestamp": datetime.now().isoformat(),
            "results_summary": [
                {
                    "pattern": r['pattern'],
                    "signals": r['total_signals'],
                    "win_rate": round(r['win_rate'], 2) if r.get('win_rate') else 0,
                    "expectancy": round(r['expectancy'], 4) if r.get('expectancy') else 0
                }
                for r in sorted(results, key=lambda x: x.get('expectancy', 0), reverse=True)[:10]
            ]
        }

    except Exception as e:
        logger.error(f"Backtest job error: {e}", exc_info=True)
        raise


def process_spx_backtest_job(job_id: str, config: dict) -> dict:
    """
    Process an SPX wheel backtest job with ML scoring.

    This is the heavy job that was crashing browsers.
    Now runs in background with batched ML scoring.
    """
    logger.info(f"Processing SPX backtest job {job_id}")
    update_job_progress(job_id, 2, "Loading SPX backtester...")

    try:
        from backtest.spx_premium_backtest import SPXPremiumBacktester

        start_date = config.get('start_date', '2024-01-01')
        end_date = config.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        initial_capital = config.get('initial_capital', 100000)
        put_delta = config.get('put_delta', 0.20)
        dte_target = config.get('dte_target', 45)
        max_margin_pct = config.get('max_margin_pct', 0.50)
        use_ml_scoring = config.get('use_ml_scoring', True)
        ml_min_score = config.get('ml_min_score', 0.40)

        update_job_progress(job_id, 5, f"Creating backtest ({start_date} to {end_date})...")

        # Create backtester
        backtester = SPXPremiumBacktester(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            put_delta=put_delta,
            dte_target=dte_target,
            max_margin_pct=max_margin_pct
        )

        update_job_progress(job_id, 10, "Running backtest simulation...")

        # Run backtest
        results = backtester.run(save_to_db=True)

        if not results:
            raise Exception("Backtest failed to return results")

        update_job_progress(job_id, 60, "Processing results...")

        summary = results.get('summary', {})
        data_quality = results.get('data_quality', {})
        trades = results.get('all_trades', results.get('trades', []))

        # Map field names
        if 'winning_trades' not in summary and 'expired_otm' in summary:
            summary['winning_trades'] = summary.get('expired_otm', 0)
        if 'losing_trades' not in summary and 'cash_settled_itm' in summary:
            summary['losing_trades'] = summary.get('cash_settled_itm', 0)

        # Calculate Sharpe if needed
        if 'sharpe_ratio' not in summary:
            daily_snapshots = results.get('daily_snapshots', [])
            if len(daily_snapshots) > 1:
                import numpy as np
                equities = [
                    s.get('total_equity', s.get('equity', 0)) if isinstance(s, dict)
                    else getattr(s, 'total_equity', 0)
                    for s in daily_snapshots
                ]
                if len(equities) > 1:
                    returns = np.diff(equities) / np.array(equities[:-1])
                    returns = returns[~np.isnan(returns)]
                    if len(returns) > 0 and np.std(returns) > 0:
                        summary['sharpe_ratio'] = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
                    else:
                        summary['sharpe_ratio'] = 0
                else:
                    summary['sharpe_ratio'] = 0
            else:
                summary['sharpe_ratio'] = 0

        # ML Scoring (batched to prevent hangs)
        ml_results = None
        if use_ml_scoring and trades:
            update_job_progress(job_id, 70, f"ML scoring {len(trades)} trades (batched)...")
            ml_results = score_trades_with_ml_batched(
                trades, ml_min_score, job_id
            )

        update_job_progress(job_id, 85, "Recording trades for ML training...")

        # Auto-process for ML training (batched)
        ml_training_result = None
        if trades:
            ml_training_result = auto_process_trades_batched(job_id, trades)

        update_job_progress(job_id, 95, "Finalizing results...")

        backtest_id = f"spx_wheel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return {
            "success": True,
            "backtest_id": backtest_id,
            "summary": {
                "start_date": start_date,
                "end_date": end_date,
                "initial_capital": initial_capital,
                "final_equity": summary.get('final_equity', initial_capital),
                "total_return_pct": round(summary.get('total_return_pct', 0), 2),
                "total_trades": summary.get('total_trades', 0),
                "winning_trades": summary.get('winning_trades', 0),
                "losing_trades": summary.get('losing_trades', 0),
                "win_rate": round(summary.get('win_rate', 0), 1),
                "max_drawdown_pct": round(summary.get('max_drawdown', 0), 2),
                "sharpe_ratio": round(summary.get('sharpe_ratio', 0), 2)
            },
            "data_quality": {
                "real_data_pct": round(data_quality.get('real_data_pct', 0), 1),
                "real_data_points": data_quality.get('real_data_points', 0),
                "estimated_data_points": data_quality.get('estimated_data_points', 0),
                "quality_verdict": "HIGH" if data_quality.get('real_data_pct', 0) >= 80
                    else "MEDIUM" if data_quality.get('real_data_pct', 0) >= 50 else "LOW"
            },
            "ml_analysis": ml_results if ml_results else {"enabled": False},
            "ml_training": ml_training_result,
            "trades_count": len(trades),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"SPX backtest job error: {e}", exc_info=True)
        raise


def score_trades_with_ml_batched(trades: list, ml_min_score: float, job_id: str) -> dict:
    """
    Score trades with ML in batches to prevent timeouts.

    Processes BATCH_SIZE trades at a time with progress updates.
    """
    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer, SPXWheelFeatures

        trainer = get_spx_wheel_ml_trainer()
        if not trainer or trainer.model is None:
            return {
                "enabled": True,
                "model_trained": False,
                "message": "ML model not trained yet"
            }

        ml_approved = 0
        ml_rejected = 0
        ml_approved_pnl = 0.0
        ml_rejected_pnl = 0.0
        real_data_count = 0
        estimated_count = 0

        total = len(trades)
        processed = 0

        # Process in batches
        for i in range(0, total, BATCH_SIZE):
            batch = trades[i:i + BATCH_SIZE]

            for trade in batch:
                strike = trade.get('strike', 0)
                underlying = trade.get('entry_underlying_price', 0)
                pnl = trade.get('total_pnl', 0) or trade.get('pnl', 0) or 0
                trade_date = trade.get('trade_date', '')
                premium = trade.get('premium', trade.get('entry_price', 0)) or 0
                dte = trade.get('dte', 45)

                if not underlying or not strike:
                    continue

                # Use fallback features (real data fetch would be too slow in batch)
                features = SPXWheelFeatures(
                    trade_date=trade_date,
                    strike=float(strike),
                    underlying_price=float(underlying),
                    dte=dte,
                    delta=trade.get('delta', 0.20),
                    premium=float(premium),
                    iv=trade.get('implied_volatility', 0.15),
                    iv_rank=50,
                    vix=18,
                    vix_percentile=50,
                    vix_term_structure=0,
                    put_wall_distance_pct=(underlying - strike) / underlying * 100 if underlying else 5,
                    call_wall_distance_pct=5,
                    net_gex=0,
                    spx_20d_return=0,
                    spx_5d_return=0,
                    spx_distance_from_high=0,
                    premium_to_strike_pct=float(premium) / float(strike) * 100 if strike else 0,
                    annualized_return=(float(premium) / float(strike) * 100 * 365 / dte) if strike and dte else 0
                )

                try:
                    prediction = trainer.predict(features)
                    ml_score = prediction.get('win_probability', 0.5)

                    if ml_score >= ml_min_score:
                        ml_approved += 1
                        ml_approved_pnl += float(pnl)
                    else:
                        ml_rejected += 1
                        ml_rejected_pnl += float(pnl)
                except Exception:
                    estimated_count += 1

            processed += len(batch)

            # Update progress (70-85% range for ML scoring)
            progress = 70 + int((processed / total) * 15)
            update_job_progress(job_id, progress, f"ML scored {processed}/{total} trades...")

            # Allow for graceful shutdown between batches
            if shutdown_requested:
                break

        return {
            "enabled": True,
            "model_trained": True,
            "ml_threshold": ml_min_score,
            "trades_analyzed": processed,
            "ml_approved": ml_approved,
            "ml_rejected": ml_rejected,
            "ml_approved_pnl": round(ml_approved_pnl, 2),
            "ml_rejected_pnl": round(ml_rejected_pnl, 2),
            "ml_value_add": round(ml_approved_pnl - ml_rejected_pnl, 2) if ml_rejected_pnl < 0 else 0,
            "recommendation": "ML filtering would improve results" if ml_rejected_pnl < 0 else "Current trades are good"
        }

    except Exception as e:
        logger.error(f"ML scoring error: {e}")
        return {"enabled": True, "error": str(e)}


def auto_process_trades_batched(job_id: str, trades: list) -> dict:
    """
    Process trades for ML training in batches.

    This prevents the unbounded loop that was causing timeouts.
    """
    try:
        from trading.spx_wheel_ml import (
            get_spx_wheel_ml_trainer,
            get_outcome_tracker,
            SPXWheelFeatures
        )

        tracker = get_outcome_tracker()
        trainer = get_spx_wheel_ml_trainer()

        recorded = 0
        total = len(trades)

        # Process in batches
        for i in range(0, total, MAX_TRADES_PER_BATCH):
            batch = trades[i:i + MAX_TRADES_PER_BATCH]

            for trade in batch:
                trade_id = f"{job_id}_{trade.get('trade_date', 'unknown')}_{trade.get('strike', 0)}"

                strike = trade.get('strike', 0)
                underlying = trade.get('entry_underlying_price', trade.get('underlying_price', 0))
                pnl = trade.get('total_pnl', trade.get('pnl', 0)) or 0
                trade_date = trade.get('trade_date', '')

                if not strike or not underlying or not trade_date:
                    continue

                premium = trade.get('premium', trade.get('entry_price', 0)) or 0
                dte = trade.get('dte', 45)

                features = SPXWheelFeatures(
                    trade_date=trade_date,
                    strike=float(strike),
                    underlying_price=float(underlying),
                    dte=dte,
                    delta=trade.get('delta', 0.20),
                    premium=float(premium),
                    iv=trade.get('implied_volatility', 0.15),
                    iv_rank=50,
                    vix=18,
                    vix_percentile=50,
                    vix_term_structure=0,
                    put_wall_distance_pct=(float(underlying) - float(strike)) / float(underlying) * 100 if underlying else 5,
                    call_wall_distance_pct=5,
                    net_gex=0,
                    spx_20d_return=0,
                    spx_5d_return=0,
                    spx_distance_from_high=0,
                    premium_to_strike_pct=float(premium) / float(strike) * 100 if strike else 0,
                    annualized_return=(float(premium) / float(strike) * 100 * 365 / dte) if strike and dte else 0
                )

                outcome = 'WIN' if float(pnl) > 0 else 'LOSS'

                tracker.record_trade_entry(trade_id, features)
                tracker.record_trade_outcome(
                    trade_id=trade_id,
                    outcome=outcome,
                    pnl=float(pnl),
                    settlement_price=trade.get('settlement_price', underlying),
                    max_drawdown=trade.get('max_drawdown', 0)
                )

                recorded += 1

            # Update progress
            progress = 85 + int((i / total) * 10)
            update_job_progress(job_id, progress, f"Recorded {recorded}/{total} trades for ML...")

            if shutdown_requested:
                break

        # Check if we can auto-train
        all_outcomes = tracker.get_all_outcomes()
        can_train = len(all_outcomes) >= 30
        trained = False

        if can_train and not trainer.model:
            update_job_progress(job_id, 95, "Auto-training ML model...")
            result = trainer.train(all_outcomes)
            trained = 'error' not in result

        return {
            "trades_recorded": recorded,
            "total_training_samples": len(all_outcomes),
            "can_train": can_train,
            "auto_trained": trained,
            "message": f"Recorded {recorded} trades. {'Auto-trained ML model!' if trained else f'Need {30 - len(all_outcomes)} more for training' if not can_train else 'Model already trained'}"
        }

    except Exception as e:
        logger.error(f"Auto-process error: {e}")
        return {"error": str(e), "trades_recorded": 0}


def process_job(job: dict):
    """Process a single job based on its type"""
    job_id = job['job_id']
    job_type = job['job_type']
    config = job.get('config', {}) or {}

    logger.info(f"Starting job {job_id} (type: {job_type})")

    # Claim the job
    if not start_job(job_id, WORKER_ID):
        logger.warning(f"Could not claim job {job_id} - may be taken by another worker")
        return

    try:
        if job_type == JobType.BACKTEST.value:
            result = process_backtest_job(job_id, config)
        elif job_type == JobType.SPX_BACKTEST.value:
            result = process_spx_backtest_job(job_id, config)
        elif job_type == JobType.ML_TRAINING.value:
            result = process_ml_training_job(job_id, config)
        else:
            raise ValueError(f"Unknown job type: {job_type}")

        complete_job(job_id, result)
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        fail_job(job_id, str(e))
        logger.error(f"Job {job_id} failed: {e}")


def process_ml_training_job(job_id: str, config: dict) -> dict:
    """Process an ML training job"""
    update_job_progress(job_id, 10, "Loading training data...")

    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer, get_outcome_tracker

        tracker = get_outcome_tracker()
        trainer = get_spx_wheel_ml_trainer()

        all_outcomes = tracker.get_all_outcomes()

        if len(all_outcomes) < 30:
            return {
                "success": False,
                "message": f"Need at least 30 training samples, have {len(all_outcomes)}"
            }

        update_job_progress(job_id, 50, f"Training on {len(all_outcomes)} samples...")

        result = trainer.train(all_outcomes)

        return {
            "success": 'error' not in result,
            "samples": len(all_outcomes),
            "metrics": result.get('metrics', {}),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"ML training error: {e}")
        raise


def run_worker():
    """Main worker loop"""
    logger.info(f"Starting backtest worker {WORKER_ID}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s, Batch size: {BATCH_SIZE}")

    # Cleanup old jobs on startup
    cleanup_old_jobs(days=7)

    while not shutdown_requested:
        try:
            # Get pending jobs
            jobs = get_pending_jobs(limit=1)

            if jobs:
                for job in jobs:
                    if shutdown_requested:
                        break
                    process_job(job)
            else:
                # No jobs, wait before polling again
                time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            time.sleep(POLL_INTERVAL)

    # Graceful shutdown sequence
    logger.info("=" * 60)
    logger.info("GRACEFUL SHUTDOWN SEQUENCE")
    logger.info("=" * 60)

    # Close database connection pool
    try:
        from database_adapter import close_pool
        logger.info("[SHUTDOWN] Closing database connection pool...")
        close_pool()
        logger.info("[SHUTDOWN] Database pool closed")
    except Exception as e:
        logger.error(f"[SHUTDOWN] Database pool close failed: {e}")

    logger.info("=" * 60)
    logger.info(f"Worker {WORKER_ID} shutdown complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_worker()
