"""
Feature specification and computation pipeline.

Internal module for backtest engine dependencies.
Canonical API: src/indicators/__init__.py
"""

from .feature_spec import (
    InputSource,
    FeatureSpec,
    FeatureSpecSet,
    is_multi_output,
    get_output_names,
)
from .feature_frame_builder import (
    FeatureFrameBuilder,
    FeatureArrays,
    IndicatorCompute,
    get_compute,
)

__all__ = [
    # Core types
    "InputSource",
    "FeatureSpec",
    "FeatureSpecSet",
    "is_multi_output",
    "get_output_names",
    # Builder and compute adapter
    "FeatureFrameBuilder",
    "FeatureArrays",
    "IndicatorCompute",
    "get_compute",
]
