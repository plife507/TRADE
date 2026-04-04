"""
Logging utilities for the trading bot.

Provides:
- get_module_logger(): Create child loggers under the ``trade.*`` hierarchy
- suppress_for_validation(): Silence trade.* loggers in validation workers
- redact_value() / redact_dict(): Centralized sensitive-field redaction

The actual logging pipeline (console + JSONL) is configured by
``src.utils.logging_config.configure_logging()``.  All ``trade.*``
loggers propagate to the root logger where structlog's
ProcessorFormatter handles rendering.

Usage:
    from src.utils.logger import get_module_logger

    logger = get_module_logger(__name__)
    logger.info("Hello world")
"""

import logging
import os
from typing import Any


# =============================================================================
# Configuration (can be overridden via environment variables)
# =============================================================================

# Whether to include agent text (prompts/responses) - default: false for safety
LOG_INCLUDE_AGENT_TEXT = os.environ.get(
    "LOG_INCLUDE_AGENT_TEXT", "false"
).lower() in ("true", "1", "yes")


# =============================================================================
# Redaction utilities (centralized for all logging)
# =============================================================================

# Keys that should always be redacted (case-insensitive substring match)
REDACT_KEY_PATTERNS = [
    "api_key", "apikey", "secret", "token", "password",
    "private_key", "privatekey", "auth", "credential",
    "bearer", "jwt", "x-api-key", "x-api-secret",
    "passphrase", "signature",
]

# Keys that contain agent text (only logged if LOG_INCLUDE_AGENT_TEXT is true)
# These are specifically for AI/LLM prompts and responses, not general messages
AGENT_TEXT_KEYS = [
    "prompt", "response", "completion", "llm_response", "agent_response",
]


def redact_value(value: Any, key: str = "", max_length: int = 500) -> Any:
    """Redact sensitive values for safe logging.

    Args:
        value: The value to potentially redact.
        key: The key/field name (used for pattern matching).
        max_length: Maximum length for string/repr values.

    Returns:
        Redacted/sanitized value safe for logging.
    """
    key_lower = key.lower() if key else ""

    for pattern in REDACT_KEY_PATTERNS:
        if pattern in key_lower:
            return "***REDACTED***"

    if not LOG_INCLUDE_AGENT_TEXT:
        for agent_key in AGENT_TEXT_KEYS:
            if agent_key in key_lower:
                return "***AGENT_TEXT_REDACTED***"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length - 3] + "..."
        return value

    if isinstance(value, (list, tuple)):
        items = list(value)[:50]
        return [redact_value(v, key, max_length) for v in items]

    if isinstance(value, dict):
        return redact_dict(value, max_length)

    rep = repr(value)
    if len(rep) > max_length:
        return rep[:max_length - 3] + "..."
    return rep


def redact_dict(d: dict[str, Any], max_length: int = 500) -> dict[str, Any]:
    """Recursively redact a dictionary for safe logging.

    Args:
        d: Dictionary to redact.
        max_length: Maximum length for string values.

    Returns:
        Redacted dictionary safe for logging.
    """
    result = {}
    for k, v in d.items():
        key_str = str(k)
        result[key_str] = redact_value(v, key_str, max_length)
    return result


# =============================================================================
# Logger factory
# =============================================================================

def get_module_logger(module_name: str) -> logging.Logger:
    """Get a logger that's a child of the ``trade`` hierarchy.

    Replaces bare ``logging.getLogger(__name__)`` calls which create orphan
    loggers with no handlers.  By parenting under ``trade.*`` every module
    logger inherits the root ``trade`` handler configuration.

    Example::

        logger = get_module_logger(__name__)
        # src.backtest.runner  ->  trade.backtest.runner
    """
    suffix = module_name
    for prefix in ("src.", "src\\"):
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix):]
            break
    return logging.getLogger(f"trade.{suffix}")


def suppress_for_validation() -> None:
    """Set the ``trade.*`` logger tree to WARNING for clean validation output.

    Unlike ``logging.disable(logging.INFO)`` this is scoped to our loggers
    only and does not affect third-party libraries.  It also doesn't need
    to be re-enabled -- subsequent calls will recreate the root logger with
    the correct level.
    """
    trade_root = logging.getLogger("trade")
    trade_root.setLevel(logging.WARNING)
    for name in ("trade.backtest", "trade.engine", "trade.data", "trade.indicators"):
        logging.getLogger(name).setLevel(logging.WARNING)
