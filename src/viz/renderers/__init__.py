"""
Renderer Registry for visualization.

Provides fail-loud rendering for indicators and structures.
If a type is not supported, an explicit error is raised.
"""

from .indicators import IndicatorRenderer, UnsupportedIndicatorError
from .structures import StructureRenderer, UnsupportedStructureError

__all__ = [
    "IndicatorRenderer",
    "UnsupportedIndicatorError",
    "StructureRenderer",
    "UnsupportedStructureError",
]
