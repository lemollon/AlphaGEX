"""
COUNSELOR Learning Memory - Self-improving prediction system.

Tracks COUNSELOR predictions and outcomes to:
- Calculate accuracy by market regime
- Adjust confidence based on historical performance
- Identify patterns in successful/unsuccessful predictions
- Provide transparency ("In similar conditions, I've been 72% accurate")

This is a key differentiator - most trading AIs don't learn from their mistakes.
"""

import os
import json
import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)

# Central Time zone
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")


@dataclass
class Prediction:
    """A COUNSELOR prediction record."""
    prediction_id: str
    timestamp: str
    prediction_type: str  # direction, trade_quality, strike_selection
    prediction: str  # The actual prediction made
    confidence: float  # 0-1
    context_hash: str  # Hash of market context for similarity matching
    gex_regime: str
    vix_level: float
    day_of_week: int
    outcome: Optional[str] = None  # actual outcome once known
    outcome_timestamp: Optional[str] = None
    was_correct: Optional[bool] = None
    notes: Optional[str] = None


@dataclass
class RegimeAccuracy:
    """Accuracy tracking for a specific market regime."""
    regime: str
    total_predictions: int = 0
    correct_predictions: int = 0
    accuracy_pct: float = 0.0
    last_updated: str = ""

    def update(self, was_correct: bool):
        self.total_predictions += 1
        if was_correct:
            self.correct_predictions += 1
        self.accuracy_pct = (self.correct_predictions / self.total_predictions) * 100
        self.last_updated = datetime.now(CENTRAL_TZ).isoformat()


class CounselorLearningMemory:
    """
    Learning memory system for COUNSELOR predictions.

    Stores predictions and outcomes, tracks accuracy by regime,
    and adjusts confidence based on historical performance.
    """

    # Batch write threshold to reduce disk I/O
    BATCH_WRITE_THRESHOLD = 10

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize learning memory.

        Args:
            storage_path: Path to store predictions (defaults to in-memory)
        """
        self.storage_path = storage_path
        self.predictions: Dict[str, Prediction] = {}
        self.regime_accuracy: Dict[str, RegimeAccuracy] = {}
        self.prediction_type_accuracy: Dict[str, RegimeAccuracy] = {}
        self._pending_writes = 0  # Track pending writes for batching

        # Load existing data if available
        if storage_path and os.path.exists(storage_path):
            self._load_from_disk()

    def _generate_context_hash(self, context: Dict[str, Any]) -> str:
        """Generate a hash for context similarity matching."""
        # Normalize key values for hashing
        normalized = {
            "gex_regime": context.get("gex_regime", "unknown"),
            "vix_bucket": self._bucket_vix(context.get("vix", 15)),
            "day_type": self._classify_day(context.get("day_of_week", 0)),
            "flip_zone": self._in_flip_zone(context)
        }
        return hashlib.md5(json.dumps(normalized, sort_keys=True).encode()).hexdigest()[:12]

    def _bucket_vix(self, vix: float) -> str:
        """Bucket VIX into categories."""
        if vix < 12:
            return "very_low"
        elif vix < 16:
            return "low"
        elif vix < 20:
            return "normal"
        elif vix < 25:
            return "elevated"
        elif vix < 30:
            return "high"
        else:
            return "extreme"

    def _classify_day(self, day_of_week: int) -> str:
        """Classify day type for trading patterns."""
        if day_of_week == 0:
            return "monday"
        elif day_of_week == 1:
            return "tuesday"  # Best day for directional
        elif day_of_week in [2, 3]:
            return "midweek"
        elif day_of_week == 4:
            return "friday"  # OPEX risk
        else:
            return "weekend"

    def _in_flip_zone(self, context: Dict[str, Any]) -> bool:
        """Check if price is near gamma flip point."""
        price = context.get("spot_price", 0)
        flip = context.get("flip_point", 0)
        if price and flip:
            distance_pct = abs(price - flip) / price * 100
            return distance_pct < 0.5  # Within 0.5%
        return False

    def record_prediction(
        self,
        prediction_type: str,
        prediction: str,
        confidence: float,
        context: Dict[str, Any]
    ) -> str:
        """
        Record a new COUNSELOR prediction.

        Args:
            prediction_type: Type of prediction (direction, trade_quality, etc.)
            prediction: The actual prediction made
            confidence: Confidence level (0-1)
            context: Market context at time of prediction

        Returns:
            prediction_id for later outcome recording
        """
        now = datetime.now(CENTRAL_TZ)
        # Use UUID for uniqueness instead of short MD5 hash to prevent collisions
        prediction_id = f"pred_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:12]}"

        pred = Prediction(
            prediction_id=prediction_id,
            timestamp=now.isoformat(),
            prediction_type=prediction_type,
            prediction=prediction,
            confidence=confidence,
            context_hash=self._generate_context_hash(context),
            gex_regime=context.get("gex_regime", "unknown"),
            vix_level=context.get("vix", 15),
            day_of_week=now.weekday()
        )

        self.predictions[prediction_id] = pred
        self._pending_writes += 1

        # Batch writes to reduce disk I/O
        if self._pending_writes >= self.BATCH_WRITE_THRESHOLD:
            self._save_to_disk()
            self._pending_writes = 0

        logger.info(f"Recorded prediction {prediction_id}: {prediction_type} = {prediction} ({confidence*100:.0f}% confidence)")
        return prediction_id

    def record_outcome(
        self,
        prediction_id: str,
        outcome: str,
        was_correct: bool,
        notes: Optional[str] = None
    ) -> bool:
        """
        Record the actual outcome for a prediction.

        Args:
            prediction_id: ID of the prediction
            outcome: What actually happened
            was_correct: Whether the prediction was correct
            notes: Optional notes about the outcome

        Returns:
            True if recorded successfully
        """
        if prediction_id not in self.predictions:
            logger.warning(f"Prediction {prediction_id} not found")
            return False

        pred = self.predictions[prediction_id]
        pred.outcome = outcome
        pred.was_correct = was_correct
        pred.outcome_timestamp = datetime.now(CENTRAL_TZ).isoformat()
        pred.notes = notes

        # Update regime accuracy
        regime = pred.gex_regime
        if regime not in self.regime_accuracy:
            self.regime_accuracy[regime] = RegimeAccuracy(regime=regime)
        self.regime_accuracy[regime].update(was_correct)

        # Update prediction type accuracy
        ptype = pred.prediction_type
        if ptype not in self.prediction_type_accuracy:
            self.prediction_type_accuracy[ptype] = RegimeAccuracy(regime=ptype)
        self.prediction_type_accuracy[ptype].update(was_correct)

        self._save_to_disk()

        logger.info(f"Recorded outcome for {prediction_id}: {outcome} (correct: {was_correct})")
        return True

    def get_accuracy_for_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get historical accuracy for similar market conditions.

        This allows COUNSELOR to say: "In similar conditions, I've been X% accurate"

        Args:
            context: Current market context

        Returns:
            Accuracy information for similar conditions
        """
        regime = context.get("gex_regime", "unknown")
        vix_bucket = self._bucket_vix(context.get("vix", 15))

        # Get regime accuracy
        regime_acc = self.regime_accuracy.get(regime)
        regime_accuracy = regime_acc.accuracy_pct if regime_acc else None

        # Find predictions in similar conditions
        context_hash = self._generate_context_hash(context)
        similar_predictions = [
            p for p in self.predictions.values()
            if p.context_hash == context_hash and p.was_correct is not None
        ]

        similar_correct = sum(1 for p in similar_predictions if p.was_correct)
        similar_total = len(similar_predictions)
        similar_accuracy = (similar_correct / similar_total * 100) if similar_total > 0 else None

        return {
            "regime": regime,
            "regime_accuracy_pct": regime_accuracy,
            "regime_sample_size": regime_acc.total_predictions if regime_acc else 0,
            "similar_conditions_accuracy_pct": similar_accuracy,
            "similar_conditions_sample_size": similar_total,
            "vix_bucket": vix_bucket,
            "context_hash": context_hash,
            "confidence_adjustment": self._calculate_confidence_adjustment(regime_accuracy, similar_accuracy)
        }

    def _calculate_confidence_adjustment(
        self,
        regime_accuracy: Optional[float],
        similar_accuracy: Optional[float]
    ) -> float:
        """
        Calculate how much to adjust confidence based on historical accuracy.

        Returns a multiplier (e.g., 0.9 means reduce confidence by 10%)
        """
        if similar_accuracy is not None and similar_accuracy > 0:
            # Use similar conditions accuracy if available
            return min(1.2, max(0.5, similar_accuracy / 70))  # Normalize to ~70% as baseline
        elif regime_accuracy is not None and regime_accuracy > 0:
            # Fall back to regime accuracy
            return min(1.2, max(0.5, regime_accuracy / 70))
        else:
            # No data - use default
            return 1.0

    def get_accuracy_statement(self, context: Dict[str, Any]) -> str:
        """
        Generate a natural language accuracy statement for COUNSELOR to use.

        Example: "In similar market conditions, I've been 72% accurate."
        """
        acc = self.get_accuracy_for_context(context)

        if acc["similar_conditions_sample_size"] >= 5:
            return f"In similar market conditions (regime: {acc['regime']}, VIX: {acc['vix_bucket']}), I've been {acc['similar_conditions_accuracy_pct']:.0f}% accurate across {acc['similar_conditions_sample_size']} predictions."
        elif acc["regime_sample_size"] >= 10:
            return f"In {acc['regime']} GEX regimes, I've been {acc['regime_accuracy_pct']:.0f}% accurate across {acc['regime_sample_size']} predictions."
        else:
            return "I don't have enough historical data for this exact scenario to provide an accuracy estimate."

    def get_learning_insights(self) -> Dict[str, Any]:
        """Get overall learning insights and accuracy statistics."""
        total_predictions = len(self.predictions)
        with_outcomes = sum(1 for p in self.predictions.values() if p.was_correct is not None)
        correct = sum(1 for p in self.predictions.values() if p.was_correct is True)

        overall_accuracy = (correct / with_outcomes * 100) if with_outcomes > 0 else 0

        # Best and worst regimes
        regime_stats = [
            (r.regime, r.accuracy_pct, r.total_predictions)
            for r in self.regime_accuracy.values()
            if r.total_predictions >= 5
        ]
        regime_stats.sort(key=lambda x: x[1], reverse=True)

        return {
            "total_predictions": total_predictions,
            "predictions_with_outcomes": with_outcomes,
            "overall_accuracy_pct": round(overall_accuracy, 1),
            "best_regimes": regime_stats[:3] if regime_stats else [],
            "worst_regimes": regime_stats[-3:] if len(regime_stats) > 3 else [],
            "accuracy_by_regime": {
                r.regime: {"accuracy": r.accuracy_pct, "sample_size": r.total_predictions}
                for r in self.regime_accuracy.values()
            },
            "accuracy_by_type": {
                r.regime: {"accuracy": r.accuracy_pct, "sample_size": r.total_predictions}
                for r in self.prediction_type_accuracy.values()
            }
        }

    def flush(self) -> None:
        """Force write any pending predictions to disk."""
        if self._pending_writes > 0:
            self._save_to_disk()
            self._pending_writes = 0

    def _save_to_disk(self):
        """Save predictions to disk if storage path is set."""
        if not self.storage_path:
            return

        data = {
            "predictions": {k: asdict(v) for k, v in self.predictions.items()},
            "regime_accuracy": {k: asdict(v) for k, v in self.regime_accuracy.items()},
            "prediction_type_accuracy": {k: asdict(v) for k, v in self.prediction_type_accuracy.items()}
        }

        try:
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save learning memory: {e}")

    def _load_from_disk(self):
        """Load predictions from disk."""
        if not self.storage_path or not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            for k, v in data.get("predictions", {}).items():
                self.predictions[k] = Prediction(**v)

            for k, v in data.get("regime_accuracy", {}).items():
                self.regime_accuracy[k] = RegimeAccuracy(**v)

            for k, v in data.get("prediction_type_accuracy", {}).items():
                self.prediction_type_accuracy[k] = RegimeAccuracy(**v)

            logger.info(f"Loaded {len(self.predictions)} predictions from disk")
        except Exception as e:
            logger.warning(f"Failed to load learning memory: {e}")


# Global instance (can be overridden with custom storage path)
_learning_memory: Optional[CounselorLearningMemory] = None


def get_learning_memory(storage_path: Optional[str] = None) -> CounselorLearningMemory:
    """Get the global learning memory instance."""
    global _learning_memory
    if _learning_memory is None:
        _learning_memory = CounselorLearningMemory(storage_path=storage_path)
    return _learning_memory


# Convenience functions
def record_prediction(prediction_type: str, prediction: str, confidence: float, context: Dict[str, Any]) -> str:
    """Record a prediction to the global memory."""
    return get_learning_memory().record_prediction(prediction_type, prediction, confidence, context)


def record_outcome(prediction_id: str, outcome: str, was_correct: bool, notes: Optional[str] = None) -> bool:
    """Record an outcome to the global memory."""
    return get_learning_memory().record_outcome(prediction_id, outcome, was_correct, notes)


def get_accuracy_statement(context: Dict[str, Any]) -> str:
    """Get an accuracy statement for the current context."""
    return get_learning_memory().get_accuracy_statement(context)


logger.info("COUNSELOR Learning Memory module loaded - self-improvement enabled")
