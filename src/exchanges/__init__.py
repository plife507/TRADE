"""
Exchange client modules.

Provides API clients for supported cryptocurrency exchanges.
Currently supports Bybit via the official pybit library.
"""

from .bybit_client import BybitClient, BybitAPIError

# Re-export pybit exceptions for convenience
from pybit.exceptions import (
    FailedRequestError,
    InvalidRequestError,
    InvalidChannelTypeError,
    TopicMismatchError,
    UnauthorizedExceptionError,
)

__all__ = [
    # Main client
    "BybitClient",
    # Custom exception
    "BybitAPIError",
    # pybit exceptions
    "FailedRequestError",
    "InvalidRequestError", 
    "InvalidChannelTypeError",
    "TopicMismatchError",
    "UnauthorizedExceptionError",
]
