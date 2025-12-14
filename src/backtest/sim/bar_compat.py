"""
Bar utility functions.

Provides helper functions for working with the canonical Bar type.
"""

from datetime import datetime

from ..runtime.types import Bar as CanonicalBar

# Type alias for Bar (CanonicalBar is the only Bar type)
AnyBar = CanonicalBar


def get_bar_ts_open(bar: CanonicalBar) -> datetime:
    """
    Get the bar open timestamp.
    
    Use this for fill timestamps (fills occur at bar open).
    """
    return bar.ts_open


def get_bar_ts_close(bar: CanonicalBar) -> datetime:
    """
    Get the bar close timestamp.
    
    Use this for step time / MTM updates.
    """
    return bar.ts_close


def get_bar_timestamp(bar: CanonicalBar) -> datetime:
    """
    Get the step timestamp (ts_close).
    
    This is the "step time" - when strategy evaluates.
    """
    return bar.ts_close

