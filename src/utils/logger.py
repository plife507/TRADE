"""
Logging system for the trading bot.
Provides structured, human-readable logs with file and console output.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# ANSI color codes for terminal output
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
    
    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, Colors.WHITE)
        record.levelname = f"{color}{record.levelname}{Colors.RESET}"
        record.msg = f"{color}{record.msg}{Colors.RESET}"
        return super().format(record)


class TradingLogger:
    """
    Central logging system for the trading bot.
    
    Features:
    - Console output with colors
    - File output with rotation
    - Separate log files for trades, errors, and general logs
    - Structured logging for easy parsing
    """
    
    _instance: Optional['TradingLogger'] = None
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
        
        # Create loggers
        self.main_logger = self._create_logger("trade", log_level)
        self.trade_logger = self._create_logger("trade.orders", log_level, "trades")
        self.error_logger = self._create_logger("trade.errors", "ERROR", "errors")
        
        TradingLogger._initialized = True
    
    def _create_logger(self, name: str, level: str, file_prefix: str = None) -> logging.Logger:
        """Create a configured logger instance."""
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper()))
        logger.handlers.clear()
        
        # Console handler with colors
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColoredFormatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S"
        ))
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
              price: float = None, pnl: float = None, **kwargs):
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


# Global logger instance
_logger: Optional[TradingLogger] = None


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

