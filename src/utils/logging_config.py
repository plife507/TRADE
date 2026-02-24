"""
structlog configuration for TRADE.

Call configure_logging() once at process startup (trade_cli.py, worker init).
All existing logging.getLogger() calls automatically route through structlog
via ProcessorFormatter's foreign_pre_chain.

Architecture:
    structlog ProcessorFormatter
    ├── Console (human)  ← ConsoleRenderer(colors=isatty())
    └── File (machine)   ← QueueHandler → RotatingFileHandler → logs/trade.jsonl
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import queue
import sys
from pathlib import Path

import structlog

from src.utils.logger import REDACT_KEY_PATTERNS

# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------

# Shared chain applied to ALL log entries (structlog-native AND stdlib foreign)
SHARED_PROCESSORS: list[structlog.types.Processor] = [
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.contextvars.merge_contextvars,
]


def _redact_processor(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Structlog processor that redacts sensitive fields in JSONL output."""
    for key in list(event_dict.keys()):
        key_lower = key.lower()
        for pattern in REDACT_KEY_PATTERNS:
            if pattern in key_lower:
                event_dict[key] = "***REDACTED***"
                break
    return event_dict


# ---------------------------------------------------------------------------
# QueueHandler / QueueListener for process-safe file logging
# ---------------------------------------------------------------------------

_log_queue: queue.Queue[logging.LogRecord] | None = None
_queue_listener: logging.handlers.QueueListener | None = None

# Key used to stash contextvars snapshot on the LogRecord so it survives
# the trip through the QueueHandler → QueueListener boundary.
_CTXVARS_ATTR = "_structlog_contextvars"


class _ContextVarsSnapshotFilter(logging.Filter):
    """Capture structlog contextvars on the calling thread before queueing.

    The QueueHandler sends LogRecords to a background QueueListener thread.
    ``merge_contextvars`` runs on *that* thread where the contextvars are
    empty.  This filter snapshots them on the *calling* thread and stashes
    them on the LogRecord so a matching processor can inject them later.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = structlog.contextvars.get_contextvars()
        if ctx:
            setattr(record, _CTXVARS_ATTR, ctx.copy())
        return True


def _inject_snapshot_context(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Structlog processor: inject stashed contextvars from the LogRecord.

    Paired with ``_ContextVarsSnapshotFilter`` — the filter stores the
    snapshot, this processor reads it back on the QueueListener thread.
    """
    record: logging.LogRecord | None = event_dict.get("_record")  # type: ignore[assignment]
    if record is not None:
        ctx = getattr(record, _CTXVARS_ATTR, None)
        if ctx:
            event_dict.update(ctx)
    return event_dict


class _StructlogQueueHandler(logging.handlers.QueueHandler):
    """QueueHandler that preserves structlog's dict-typed record.msg.

    The stdlib ``QueueHandler.prepare()`` calls ``self.format(record)``
    which converts ``record.msg`` from a dict to a string.  When the
    ``QueueListener`` thread later passes the record to a
    ``ProcessorFormatter``, it expects ``record.msg`` to still be a dict
    (calls ``.copy()``).  Skipping the format step here keeps the dict
    intact so both structlog-native and stdlib loggers work correctly.
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        # Only copy — do NOT call self.format() which destroys dict msg
        record.exc_info = None
        record.exc_text = None
        return record


def _make_queue_file_handler(
    log_path: Path,
) -> logging.handlers.QueueHandler:
    """Create a QueueHandler + QueueListener wrapping a RotatingFileHandler.

    This is process-safe: ProcessPoolExecutor workers can write to the
    QueueHandler without corrupting the shared log file. The QueueListener
    drains the queue on a background thread.

    A ``_ContextVarsSnapshotFilter`` is added to the QueueHandler so that
    structlog contextvars (play_hash, symbol, mode) survive the thread
    boundary and appear in JSONL output.
    """
    global _log_queue, _queue_listener

    log_path.parent.mkdir(parents=True, exist_ok=True)

    # The actual file handler (runs on the listener thread)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=100_000_000,   # 100 MB
        backupCount=7,          # 700 MB total cap
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    # Build the file handler's foreign_pre_chain — same as SHARED_PROCESSORS
    # but replaces merge_contextvars with _inject_snapshot_context (reads
    # the snapshot stashed by the filter on the calling thread).
    file_pre_chain: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_snapshot_context,
    ]

    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _redact_processor,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=file_pre_chain,
        )
    )

    # Queue plumbing — use _StructlogQueueHandler to preserve dict msg
    _log_queue = queue.Queue(-1)  # unbounded
    queue_handler = _StructlogQueueHandler(_log_queue)
    queue_handler.addFilter(_ContextVarsSnapshotFilter())

    _queue_listener = logging.handlers.QueueListener(
        _log_queue, file_handler, respect_handler_level=True
    )
    _queue_listener.start()

    return queue_handler


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_configured = False


def configure_logging(
    log_dir: str = "logs",
    log_level: str | None = None,
    json_file: bool = True,
) -> None:
    """Configure structlog + stdlib integration.

    Safe to call multiple times (idempotent after first call).

    Args:
        log_dir: Directory for log files.
        log_level: Override log level. Default resolves from env vars.
        json_file: Whether to write logs/trade.jsonl.
    """
    global _configured
    if _configured:
        return
    _configured = True

    # Resolve level: explicit > TRADE_LOG_LEVEL > LOG_LEVEL > INFO
    if log_level is None:
        log_level = os.environ.get(
            "TRADE_LOG_LEVEL",
            os.environ.get("LOG_LEVEL", "INFO"),
        ).upper()
    else:
        log_level = log_level.upper()

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # --- Console handler (always) ---
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
            ],
            foreign_pre_chain=SHARED_PROCESSORS,
        )
    )

    # --- File handler (optional, process-safe via QueueHandler) ---
    handlers: list[logging.Handler] = [console_handler]
    if json_file:
        queue_handler = _make_queue_file_handler(log_path / "trade.jsonl")
        queue_handler.setLevel(logging.DEBUG)
        handlers.append(queue_handler)

    # --- Configure stdlib root logger ---
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    # Remove any pre-existing handlers (from prior calls or third-party setup)
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    # Clear any stray handlers on trade.* loggers so structlog handles
    # output exclusively via root propagation.
    for name in ("trade", "trade.orders", "trade.errors"):
        logging.getLogger(name).handlers.clear()

    # --- Suppress noisy third-party loggers ---
    logging.getLogger("pybit").setLevel(logging.WARNING)
    logging.getLogger("websocket").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # --- Configure structlog ---
    structlog.configure(
        processors=[
            *SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def bind_engine_context(
    *,
    play_hash: str,
    symbol: str,
    mode: str,
) -> None:
    """Bind engine-level context fields to the current thread.

    All subsequent log calls on this thread will include these fields
    automatically in both console and JSONL output.  Call
    :func:`clear_engine_context` when the engine run finishes.

    Args:
        play_hash: Play configuration hash (16 hex chars).
        symbol: Trading symbol (e.g. ``BTCUSDT``).
        mode: Engine mode (``backtest``, ``demo``, ``live``).
    """
    structlog.contextvars.bind_contextvars(
        play_hash=play_hash,
        symbol=symbol,
        mode=mode,
    )


def clear_engine_context() -> None:
    """Remove engine-level context fields from the current thread."""
    structlog.contextvars.unbind_contextvars("play_hash", "symbol", "mode", "bar_idx")


def shutdown_logging() -> None:
    """Stop the queue listener (call at process exit)."""
    global _queue_listener, _configured
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None
    _configured = False
