"""
Logging system for the trading bot.

Provides:
- Human-readable console output with colors
- Daily text log files (bot_*.log, trades_*.log, errors_*.log)
- Structured JSONL event stream for agent/tool tracing (events_*.jsonl)
- Centralized redaction of sensitive fields
- Integration with log_context for distributed tracing correlation

Usage:
    from src.utils.logger import get_logger
    
    logger = get_logger()
    logger.info("Hello world")
    
    # Structured event logging (for tools/agents)
    logger.event("tool.call.start", tool_name="market_buy", symbol="SOLUSDT")
    logger.event("tool.call.end", tool_name="market_buy", success=True, elapsed_ms=150.5)
"""

from __future__ import annotations

import json
import logging
import os
import copy
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# =============================================================================
# Configuration (can be overridden via environment variables)
# =============================================================================

# Whether to write JSONL event logs (default: true)
LOG_JSON_ENABLED = os.environ.get("LOG_JSON", "true").lower() in ("true", "1", "yes")

# Whether to include function arguments in logs (default: true)
LOG_INCLUDE_ARGS = os.environ.get("LOG_INCLUDE_ARGS", "true").lower() in ("true", "1", "yes")

# Whether to include agent text (prompts/responses) - default: false for safety
LOG_INCLUDE_AGENT_TEXT = os.environ.get("LOG_INCLUDE_AGENT_TEXT", "false").lower() in ("true", "1", "yes")


# =============================================================================
# Redaction utilities (centralized for all logging)
# =============================================================================

# Keys that should always be redacted (case-insensitive substring match)
REDACT_KEY_PATTERNS = [
    "api_key", "apikey", "secret", "token", "password",
    "private_key", "privatekey", "auth", "credential",
]

# Keys that contain agent text (only logged if LOG_INCLUDE_AGENT_TEXT is true)
# These are specifically for AI/LLM prompts and responses, not general messages
AGENT_TEXT_KEYS = ["prompt", "response", "completion", "llm_response", "agent_response"]


def redact_value(value: Any, key: str = "", max_length: int = 500) -> Any:
    """
    Redact sensitive values for safe logging.
    
    Args:
        value: The value to potentially redact
        key: The key/field name (used for pattern matching)
        max_length: Maximum length for string/repr values
    
    Returns:
        Redacted/sanitized value safe for logging
    """
    # Check if key matches redaction patterns
    key_lower = key.lower() if key else ""
    
    for pattern in REDACT_KEY_PATTERNS:
        if pattern in key_lower:
            return "***REDACTED***"
    
    # Check if key is agent text (and we're not logging agent text)
    if not LOG_INCLUDE_AGENT_TEXT:
        for agent_key in AGENT_TEXT_KEYS:
            if agent_key in key_lower:
                return "***AGENT_TEXT_REDACTED***"
    
    # Handle different types
    if value is None or isinstance(value, (bool, int, float)):
        return value
    
    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length - 3] + "..."
        return value
    
    if isinstance(value, (list, tuple)):
        # Limit list length and recursively redact
        items = list(value)[:50]
        return [redact_value(v, key, max_length) for v in items]
    
    if isinstance(value, dict):
        return redact_dict(value, max_length)
    
    # For other types, convert to string repr
    rep = repr(value)
    if len(rep) > max_length:
        return rep[:max_length - 3] + "..."
    return rep


def redact_dict(d: dict[str, Any], max_length: int = 500) -> dict[str, Any]:
    """
    Recursively redact a dictionary for safe logging.
    
    Args:
        d: Dictionary to redact
        max_length: Maximum length for string values
    
    Returns:
        Redacted dictionary safe for logging
    """
    result = {}
    for k, v in d.items():
        key_str = str(k)
        result[key_str] = redact_value(v, key_str, max_length)
    return result


# =============================================================================
# ANSI color codes for terminal output
# =============================================================================

class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BOLD + Colors.RED,
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format without mutating the original LogRecord.
        
        IMPORTANT:
        A single LogRecord instance is shared across handlers. Mutating it in the
        console formatter leaks ANSI codes into file logs.
        """
        record_copy = copy.copy(record)
        color = self.LEVEL_COLORS.get(record.levelno, Colors.WHITE)
        record_copy.levelname = f"{color}{record.levelname}{Colors.RESET}"
        record_copy.msg = f"{color}{record.getMessage()}{Colors.RESET}"
        record_copy.args = ()
        return super().format(record_copy)


class TradingLogger:
    """
    Central logging system for the trading bot.
    
    Features:
    - Console output with colors
    - File output with rotation
    - Separate log files for trades, errors, and general logs
    - Structured JSONL event stream for agent/tool tracing
    - Centralized redaction of sensitive data
    - Integration with log_context for distributed tracing correlation
    """
    
    _instance: TradingLogger | None = None
    _initialized: bool = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, log_dir: str = "logs", log_level: str = "INFO"):
        if TradingLogger._initialized:
            return
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Process-level identifiers for JSONL
        self._hostname = socket.gethostname()
        self._pid = os.getpid()
        
        # Create loggers
        self.main_logger = self._create_logger("trade", log_level)
        self.trade_logger = self._create_logger("trade.orders", log_level, "trades")
        self.error_logger = self._create_logger("trade.errors", "ERROR", "errors")
        
        # Create JSONL event file handle (if enabled)
        self._jsonl_file = None
        if LOG_JSON_ENABLED:
            self._setup_jsonl_handler()
        
        TradingLogger._initialized = True
    
    def _setup_jsonl_handler(self):
        """Setup the JSONL event stream file."""
        date_str = datetime.now().strftime('%Y%m%d')
        jsonl_filename = f"events_{date_str}_{self._hostname}_{self._pid}.jsonl"
        jsonl_path = self.log_dir / jsonl_filename
        
        try:
            # G6.3.2: Use LF line endings for Windows compatibility
            self._jsonl_file = open(jsonl_path, 'a', encoding='utf-8', newline='\n')
        except Exception as e:
            # Fall back to logging the error, but don't crash
            print(f"Warning: Could not open JSONL log file: {e}")
            self._jsonl_file = None
    
    def _create_logger(self, name: str, level: str, file_prefix: str | None = None) -> logging.Logger:
        """Create a configured logger instance."""
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper()))
        logger.handlers.clear()
        
        # Use brackets on Windows to avoid PowerShell parsing issues
        # PowerShell interprets | and :: in various ways, causing false error messages
        # Using brackets [INFO] is safer and more readable on Windows
        import sys
        if sys.platform == "win32":
            # Windows: Use brackets to avoid PowerShell parsing
            console_separator = " ["
            console_separator_end = "] "
        else:
            # Unix: Use pipe for traditional log format
            console_separator = " | "
            console_separator_end = ""
        
        # Console handler with colors
        console_handler = logging.StreamHandler()
        if sys.platform == "win32":
            # Windows format: 23:13:50 [INFO] message
            format_str = f"%(asctime)s{console_separator}%(levelname)s{console_separator_end}%(message)s"
        else:
            # Unix format: 23:13:50 | INFO | message
            format_str = f"%(asctime)s{console_separator}%(levelname)s{console_separator}%(message)s"
        console_handler.setFormatter(ColoredFormatter(format_str, datefmt="%H:%M:%S"))
        logger.addHandler(console_handler)
        
        # File handler (plain text, no colors)
        if file_prefix:
            log_file = self.log_dir / f"{file_prefix}_{datetime.now().strftime('%Y%m%d')}.log"
        else:
            log_file = self.log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(file_handler)
        
        return logger
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message."""
        self.main_logger.info(msg, *args, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message."""
        self.main_logger.debug(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message."""
        self.main_logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error message."""
        self.main_logger.error(msg, *args, **kwargs)
        self.error_logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """Log critical message."""
        self.main_logger.critical(msg, *args, **kwargs)
        self.error_logger.critical(msg, *args, **kwargs)
    
    def trade(self, action: str, symbol: str, side: str, size: float, 
              price: float | None = None, pnl: float | None = None, **kwargs):
        """
        Log a trade action with structured format.
        
        Args:
            action: ORDER_PLACED, ORDER_FILLED, ORDER_CANCELLED, POSITION_OPENED, POSITION_CLOSED
            symbol: Trading symbol (e.g., BTCUSDT)
            side: BUY or SELL
            size: Position size in USD
            price: Execution price (optional)
            pnl: Realized PnL (optional, for closes)
            **kwargs: Additional fields
        """
        parts = [
            f"[{action}]",
            f"symbol={symbol}",
            f"side={side}",
            f"size=${size:.2f}",
        ]
        
        if price:
            parts.append(f"price={price:.4f}")
        if pnl is not None:
            color = Colors.GREEN if pnl >= 0 else Colors.RED
            parts.append(f"pnl={color}${pnl:.2f}{Colors.RESET}")
        
        for key, value in kwargs.items():
            parts.append(f"{key}={value}")
        
        msg = " | ".join(parts)
        self.trade_logger.info(msg)
        self.main_logger.info(msg)
    
    def risk(self, action: str, reason: str, **kwargs):
        """
        Log risk management actions.
        
        Args:
            action: ALLOWED, BLOCKED, WARNING
            reason: Reason for the action
            **kwargs: Additional context
        """
        parts = [f"[RISK:{action}]", reason]
        for key, value in kwargs.items():
            parts.append(f"{key}={value}")
        
        msg = " | ".join(parts)
        
        if action == "BLOCKED":
            self.main_logger.warning(msg)
        else:
            self.main_logger.info(msg)
    
    def panic(self, msg: str):
        """Log panic/emergency actions."""
        formatted = f"{Colors.BOLD}{Colors.RED}🚨 PANIC: {msg}{Colors.RESET}"
        self.main_logger.critical(formatted)
        self.error_logger.critical(f"PANIC: {msg}")
        
        # Also emit as structured event
        self.event("panic.triggered", level="CRITICAL", message=msg)
    
    # =========================================================================
    # Structured Event Logging (for agents/tools/distributed tracing)
    # =========================================================================
    
    def event(
        self,
        event_name: str,
        level: str = "INFO",
        component: str | None = None,
        **fields: Any,
    ) -> None:
        """
        Log a structured event to the JSONL event stream.
        
        This is the primary method for agent/tool-call logging. Events are
        written as single-line JSON objects to the events_*.jsonl file.
        
        Args:
            event_name: Event identifier (e.g., "tool.call.start", "order.execute.end")
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            component: Component name (e.g., "tool_registry", "order_executor")
            **fields: Additional event fields (will be redacted for safety)
        
        Example:
            logger.event(
                "tool.call.start",
                tool_name="market_buy",
                symbol="SOLUSDT",
                usd_amount=100,
            )
        """
        # Get context from log_context module (if available)
        context_fields = self._get_context_fields()
        
        # Build the event record
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "event": event_name,
            "hostname": self._hostname,
            "pid": self._pid,
        }
        
        if component:
            record["component"] = component
        
        # Add context fields (run_id, trace_id, agent_id, tool_call_id, etc.)
        record.update(context_fields)
        
        # Add and redact user-provided fields
        if fields and LOG_INCLUDE_ARGS:
            redacted_fields = redact_dict(fields)
            record.update(redacted_fields)
        
        # Write to JSONL file
        self._write_jsonl(record)
        
        # Also log to main logger at appropriate level (human-readable summary)
        log_level = getattr(logging, level.upper(), logging.INFO)
        summary = self._format_event_summary(event_name, fields)
        self.main_logger.log(log_level, summary)
    
    def _get_context_fields(self) -> dict[str, Any]:
        """Get context fields from log_context module."""
        try:
            from .log_context import get_log_context
            ctx = get_log_context()
            return ctx.to_log_fields()
        except ImportError:
            # log_context not available, return minimal context
            return {
                "hostname": self._hostname,
                "pid": self._pid,
            }
        except Exception:
            return {}
    
    def _format_event_summary(self, event_name: str, fields: dict[str, Any]) -> str:
        """Format an event as a human-readable log line."""
        parts = [f"[{event_name}]"]
        
        # Include key fields in the summary
        summary_keys = ["tool_name", "symbol", "success", "error", "elapsed_ms", "message"]
        for key in summary_keys:
            if key in fields:
                value = fields[key]
                if key == "elapsed_ms" and isinstance(value, (int, float)):
                    parts.append(f"{key}={value:.1f}")
                elif key == "success":
                    parts.append(f"{key}={'✓' if value else '✗'}")
                else:
                    parts.append(f"{key}={value}")
        
        return " | ".join(parts)
    
    def _write_jsonl(self, record: dict[str, Any]) -> None:
        """Write a record to the JSONL file."""
        if not self._jsonl_file:
            return
        
        try:
            line = json.dumps(record, default=str, ensure_ascii=False)
            self._jsonl_file.write(line + "\n")
            self._jsonl_file.flush()
        except Exception as e:
            # Don't crash on logging errors, but warn
            self.main_logger.warning(f"Failed to write JSONL event: {e}")
    
    def close(self) -> None:
        """Close the logger and flush all handlers."""
        if self._jsonl_file:
            try:
                self._jsonl_file.close()
            except Exception:
                pass
            self._jsonl_file = None
    
    def __del__(self):
        """Cleanup on destruction."""
        self.close()


# Global logger instance
_logger: TradingLogger | None = None


def get_logger(log_dir: str = "logs", log_level: str = "INFO") -> TradingLogger:
    """Get or create the global logger instance."""
    global _logger
    if _logger is None:
        _logger = TradingLogger(log_dir, log_level)
        _configure_third_party_loggers()
    return _logger


def setup_logger(log_dir: str = "logs", log_level: str = "INFO") -> TradingLogger:
    """Initialize the logger with custom settings."""
    global _logger
    TradingLogger._initialized = False
    _logger = None  # Force recreation with new format
    TradingLogger._instance = None
    _logger = TradingLogger(log_dir, log_level)
    _configure_third_party_loggers()
    return _logger


def _configure_third_party_loggers():
    """
    Configure third-party library loggers to reduce noise.
    
    pybit and websocket-client can be very verbose with connection
    errors and reconnection attempts. We suppress their console output
    while still logging to file for debugging.
    """
    # Suppress pybit's verbose WebSocket logging
    pybit_logger = logging.getLogger("pybit")
    pybit_logger.setLevel(logging.WARNING)
    
    # Suppress websocket-client library noise
    ws_logger = logging.getLogger("websocket")
    ws_logger.setLevel(logging.ERROR)
    
    # Suppress urllib3 connection pool warnings
    urllib3_logger = logging.getLogger("urllib3")
    urllib3_logger.setLevel(logging.WARNING)
    
    # Create a file-only handler for pybit if we want to capture its output
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    pybit_file = log_dir / f"pybit_{datetime.now().strftime('%Y%m%d')}.log"
    pybit_file_handler = logging.FileHandler(pybit_file, encoding='utf-8')
    pybit_file_handler.setLevel(logging.DEBUG)
    pybit_file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    pybit_logger.addHandler(pybit_file_handler)


class WebSocketErrorFilter(logging.Filter):
    """
    Filter to suppress repetitive WebSocket error messages in console.
    
    Allows first occurrence through, then suppresses repeats for a cooldown period.
    """
    
    def __init__(self, cooldown_seconds: float = 60.0):
        super().__init__()
        self._seen_messages = {}
        self._cooldown = cooldown_seconds
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Patterns to suppress after first occurrence
        suppress_patterns = [
            "Too many connection attempts",
            "connection failed",
            "pybit will no longer try to reconnect",
            "WebSocket connection closed",
            "Reconnecting",
        ]
        
        msg = record.getMessage()
        
        for pattern in suppress_patterns:
            if pattern.lower() in msg.lower():
                now = datetime.now().timestamp()
                last_seen = self._seen_messages.get(pattern, 0)
                
                if now - last_seen < self._cooldown:
                    # Suppress this message
                    return False
                else:
                    # Allow and record timestamp
                    self._seen_messages[pattern] = now
                    return True
        
        return True

