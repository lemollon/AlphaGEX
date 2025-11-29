"""
Standard Deviation Level Tracking Component
Tracks how +/-1 and +/-7 std levels move compared to prior day

This module provides logic-only std tracking functionality.
UI rendering has been removed - use the backend API for tracking views.
"""

from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def calculate_std_level_changes(current_data: Dict, yesterday_data: Dict) -> Optional[Dict]:
    """
    Calculate standard deviation level changes compared to prior day

    Args:
        current_data: Today's data with std_1_pos, std_1_neg, std_7_pos, std_7_neg, spot_price
        yesterday_data: Yesterday's data with same fields

    Returns:
        Dictionary with change metrics or None if insufficient data
    """
    if not yesterday_data:
        return None

    # Extract current std levels
    current_std_1_pos = current_data.get('std_1_pos', 0)
    current_std_1_neg = current_data.get('std_1_neg', 0)
    current_std_7_pos = current_data.get('std_7_pos', 0)
    current_std_7_neg = current_data.get('std_7_neg', 0)
    current_spot = current_data.get('spot_price', 0)

    # Extract yesterday std levels
    yesterday_std_1_pos = yesterday_data.get('std_1_pos', 0)
    yesterday_std_1_neg = yesterday_data.get('std_1_neg', 0)
    yesterday_std_7_pos = yesterday_data.get('std_7_pos', 0)
    yesterday_std_7_neg = yesterday_data.get('std_7_neg', 0)
    yesterday_spot = yesterday_data.get('spot_price', 0)

    # Calculate changes
    std_1_pos_change = current_std_1_pos - yesterday_std_1_pos
    std_1_neg_change = current_std_1_neg - yesterday_std_1_neg
    std_7_pos_change = current_std_7_pos - yesterday_std_7_pos
    std_7_neg_change = current_std_7_neg - yesterday_std_7_neg

    # Calculate range widths
    current_1std_width = current_std_1_pos - current_std_1_neg
    yesterday_1std_width = yesterday_std_1_pos - yesterday_std_1_neg
    current_7std_width = current_std_7_pos - current_std_7_neg
    yesterday_7std_width = yesterday_std_7_pos - yesterday_std_7_neg

    width_1std_change = current_1std_width - yesterday_1std_width
    width_7std_change = current_7std_width - yesterday_7std_width

    return {
        # Current levels
        'current_std_1_pos': current_std_1_pos,
        'current_std_1_neg': current_std_1_neg,
        'current_std_7_pos': current_std_7_pos,
        'current_std_7_neg': current_std_7_neg,
        'current_spot': current_spot,

        # Yesterday levels
        'yesterday_std_1_pos': yesterday_std_1_pos,
        'yesterday_std_1_neg': yesterday_std_1_neg,
        'yesterday_std_7_pos': yesterday_std_7_pos,
        'yesterday_std_7_neg': yesterday_std_7_neg,
        'yesterday_spot': yesterday_spot,

        # Level changes
        'std_1_pos_change': std_1_pos_change,
        'std_1_neg_change': std_1_neg_change,
        'std_7_pos_change': std_7_pos_change,
        'std_7_neg_change': std_7_neg_change,

        # Width changes
        'current_1std_width': current_1std_width,
        'yesterday_1std_width': yesterday_1std_width,
        'current_7std_width': current_7std_width,
        'yesterday_7std_width': yesterday_7std_width,
        'width_1std_change': width_1std_change,
        'width_7std_change': width_7std_change
    }


def get_std_interpretation(changes: Dict) -> List[str]:
    """
    Generate trading interpretation from std level changes

    Args:
        changes: Dictionary from calculate_std_level_changes()

    Returns:
        List of interpretation strings
    """
    if not changes:
        return []

    interpretation = []

    width_1std_change = changes.get('width_1std_change', 0)
    width_7std_change = changes.get('width_7std_change', 0)
    std_1_pos_change = changes.get('std_1_pos_change', 0)
    std_1_neg_change = changes.get('std_1_neg_change', 0)
    std_7_pos_change = changes.get('std_7_pos_change', 0)
    std_7_neg_change = changes.get('std_7_neg_change', 0)

    # Range width changes
    if width_1std_change > 0:
        interpretation.append("Expanding 1σ range = Increasing short-term volatility, expect wider price swings")
    elif width_1std_change < 0:
        interpretation.append("Contracting 1σ range = Decreasing volatility, good for premium selling")

    if width_7std_change > 0:
        interpretation.append("Expanding 7σ range = Increasing longer-term volatility expectations")
    elif width_7std_change < 0:
        interpretation.append("Contracting 7σ range = Market settling down, volatility compression")

    # Level shift analysis
    if std_1_pos_change > 0 and std_1_neg_change > 0:
        interpretation.append("1σ shifted UP = Bullish bias, expected range moved higher")
    elif std_1_pos_change < 0 and std_1_neg_change < 0:
        interpretation.append("1σ shifted DOWN = Bearish bias, expected range moved lower")

    if std_7_pos_change > 0 and std_7_neg_change > 0:
        interpretation.append("7σ shifted UP = Long-term bullish outlook")
    elif std_7_pos_change < 0 and std_7_neg_change < 0:
        interpretation.append("7σ shifted DOWN = Long-term bearish outlook")

    return interpretation


def get_width_direction(width_change: float) -> str:
    """
    Get width direction label

    Args:
        width_change: Change in width

    Returns:
        Direction string
    """
    if width_change > 0:
        return "WIDENED"
    elif width_change < 0:
        return "NARROWED"
    else:
        return "UNCHANGED"
