# tests/trading/agape_shared/test_regime_classifier.py
from trading.agape_shared.regime_classifier import classify_regime, Regime


def _snap(combined_signal=None, combined_confidence=None, crypto_gex_regime=None):
    return {
        "combined_signal": combined_signal,
        "combined_confidence": combined_confidence,
        "crypto_gex_regime": crypto_gex_regime,
    }


def test_long_high_confidence_is_trend():
    assert classify_regime(_snap("LONG", "HIGH")) == Regime.TREND


def test_short_medium_confidence_is_trend():
    assert classify_regime(_snap("SHORT", "MEDIUM")) == Regime.TREND


def test_long_low_confidence_is_chop():
    # Low-confidence directional reads behave like chop in practice
    assert classify_regime(_snap("LONG", "LOW")) == Regime.CHOP


def test_range_bound_is_chop():
    assert classify_regime(_snap("RANGE_BOUND", "HIGH")) == Regime.CHOP


def test_missing_signal_uses_gex_tiebreaker():
    assert classify_regime(_snap(None, None, "NEGATIVE")) == Regime.TREND
    assert classify_regime(_snap(None, None, "POSITIVE")) == Regime.CHOP


def test_completely_missing_is_unknown():
    assert classify_regime(_snap()) == Regime.UNKNOWN


def test_wait_signal_is_unknown():
    # WAIT shouldn't open a trade in production but if it ever does, treat as unknown
    assert classify_regime(_snap("WAIT", "HIGH")) == Regime.UNKNOWN


def test_accepts_object_with_attributes():
    class Snap:
        combined_signal = "LONG"
        combined_confidence = "HIGH"
        crypto_gex_regime = "NEUTRAL"
    assert classify_regime(Snap()) == Regime.TREND


def test_method_attribute_does_not_classify_as_trend():
    """Methods named like signal fields shouldn't leak through as truthy strings."""
    class Snap:
        def combined_signal(self):  # noqa: D401 — intentional method, not property
            return "LONG"
        combined_confidence = "HIGH"
        crypto_gex_regime = None
    # The method is callable; classifier should ignore it and fall back to UNKNOWN.
    assert classify_regime(Snap()) == Regime.UNKNOWN
