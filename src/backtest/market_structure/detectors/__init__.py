"""
Structure detectors.

Each detector computes a specific type of market structure
(swing highs/lows, trend classification, etc.).
"""

from .swing_detector import SwingDetector, SwingState, detect_swing_pivots
from .trend_classifier import TrendClassifier, classify_single_swing_update

__all__ = [
    "SwingDetector",
    "SwingState",
    "detect_swing_pivots",
    "TrendClassifier",
    "classify_single_swing_update",
]
