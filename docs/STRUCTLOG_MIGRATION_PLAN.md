# structlog Migration Plan

> **Date**: 2026-02-24
> **Status**: Plan (not yet implemented)
> **Related**: `docs/STATE_MEMORY_REVIEW.md` (logging identified as biggest disk consumer)

---

## Context

The current logging system uses 5 parallel file streams (bot.log, trades.log, errors.log, pybit.log, events.jsonl), none with rotation. A single validation run produced a **200 MB log file**. The `logs/` directory contains **1,482 orphan JSONL files** (one per PID) and **243 MB** total. On a 30-day live run, logs would consume **~3 GB** of disk with no automatic cleanup.

The goal is to replace the custom `TradingLogger` + stdlib `FileHandler` architecture with **structlog** — an industry-standard structured logging library that provides typed context binding, processor pipelines, and native JSONL output, while wrapping stdlib so existing `logger.info()` calls continue to work unchanged.

---

## Current Architecture (What We Have)

### 5 Parallel File Streams

```
TradingLogger (singleton)
├── bot_{date}.log          ← FileHandler, no rotation, ~200 MB/day peak
├── trades_{date}.log       ← FileHandler, no rotation, trade events only
├── errors_{date}.log       ← FileHandler, no rotation, ERROR+ only
├── pybit_{date}.log        ← FileHandler, no rotation, exchange SDK noise
└── events_{date}_{host}_{PID}.jsonl  ← Raw file handle, one per process!
```

### Key Files

| File | Role | Lines |
|------|------|-------|
| `src/utils/logger.py` | TradingLogger, get_logger(), get_module_logger(), ColoredFormatter | 650 |
| `src/utils/debug.py` | verbose_log(), debug_log(), debug_trace(), hash-prefixed helpers | 401 |
| `src/backtest/logging/run_logger.py` | Per-run RunLogger, adds FileHandler per backtest | 322 |

### Usage Counts (Migration Scope)

| Pattern | Count | Files | Migration Impact |
|---------|-------|-------|-----------------|
| `logger.info/debug/warning/error()` | 598 | 48 | **None** — structlog wraps stdlib |
| `get_module_logger(__name__)` | 14 | 13 | **None** — returns stdlib Logger |
| `get_logger()` → TradingLogger | 43 | 29 | **Replace** with structlog calls |
| `verbose_log/debug_log` helpers | 30 | 7 | **Keep** — already gated, work fine |
| Import lines (logger + debug) | 55 | 44 | **Minimal** — update import paths |

### Problems

1. **No rotation** — `FileHandler` grows unbounded (200 MB/day peak)
2. **1,482 orphan files** — per-PID JSONL naming creates file explosion
3. **5 file handles per process** — unnecessary I/O multiplexing
4. **Dual writes** — `event()` writes to BOTH JSONL and main logger
5. **No queryability** — plain text logs, no structured fields to filter on
6. **Context via string formatting** — `f"[play:{hash}] message"` instead of typed fields

---

## Target Architecture (structlog)

### Single Rotating JSONL + Colored Console

```
structlog ProcessorFormatter
├── Console (human)  ← ConsoleRenderer(colors=True)
│     2026-02-24 14:30:45 [info] Signal generated  play_hash=8f2a symbol=BTCUSDT action=ENTRY_LONG
│
└── File (machine)   ← RotatingFileHandler → logs/trade.jsonl (100 MB × 7)
      {"ts":"2026-02-24T14:30:45Z","level":"info","event":"Signal generated","play_hash":"8f2a","symbol":"BTCUSDT","action":"ENTRY_LONG","channel":"engine"}
```

### How structlog Wraps stdlib (Zero Migration for 598 Calls)

```python
# structlog's ProcessorFormatter intercepts ALL stdlib log records.
# Existing code keeps working unchanged:

logger = logging.getLogger("trade.engine")  # stdlib Logger
logger.info("Signal generated")              # Goes through structlog pipeline

# structlog adds: timestamp, level, channel, any bound context
# Outputs to: console (colored) + JSONL file (rotating)
```

This is the key insight — **`foreign_pre_chain`** processes stdlib LogRecords through structlog's pipeline without changing the call sites. All 598 `logger.info()` calls, all 14 `get_module_logger()` calls, continue to work.

### What Changes

| Component | Before | After |
|-----------|--------|-------|
| `TradingLogger` class | Custom singleton, 5 file streams | **Deleted** — replaced by structlog config |
| `get_logger()` | Returns TradingLogger | Returns structlog BoundLogger |
| `get_module_logger()` | Returns stdlib Logger | **Unchanged** (still returns stdlib Logger) |
| `.trade()` method | Custom string formatting | `logger.info("trade", channel="trade", action=..., symbol=...)` |
| `.event()` method | Dual-write (JSONL + main) | Single write through pipeline |
| `.risk()` method | Custom string formatting | `logger.warning("risk_blocked", channel="risk", reason=...)` |
| `.panic()` method | Custom + JSONL | `logger.critical("panic", channel="safety", msg=...)` |
| File output | 5 unrotated files | 1 rotating JSONL (100 MB × 7 = 700 MB cap) |
| Console output | ColoredFormatter | structlog ConsoleRenderer (same visual result) |
| Redaction | `redact_dict()` function | structlog processor (same logic, pipeline position) |
| Per-run logs | RunLogger adds FileHandler | **Keep** — still useful for per-backtest artifacts |

---

## Configuration Design

### Core Setup (New: `src/utils/logging_config.py`)

```python
"""
structlog configuration for TRADE.

Call configure_logging() once at process startup (trade_cli.py, worker init).
All existing logging.getLogger() calls automatically route through structlog.
"""
import logging
import logging.config
import sys
from pathlib import Path

import structlog

# Shared processors (run on ALL log entries — structlog AND stdlib)
SHARED_PROCESSORS = [
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.contextvars.merge_contextvars,       # Thread-local context
]

def configure_logging(
    log_dir: str = "logs",
    log_level: str = "INFO",
    json_enabled: bool = True,
) -> None:
    """Configure structlog + stdlib integration."""

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    handlers = {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "console",
            "stream": "ext://sys.stderr",
        },
    }

    if json_enabled:
        handlers["file_json"] = {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_path / "trade.jsonl"),
            "maxBytes": 100_000_000,   # 100 MB
            "backupCount": 7,          # 700 MB total cap
            "formatter": "jsonl",
            "encoding": "utf-8",
        }

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
                ],
                "foreign_pre_chain": SHARED_PROCESSORS,
            },
            "jsonl": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    _redact_processor,
                    structlog.processors.JSONRenderer(),
                ],
                "foreign_pre_chain": SHARED_PROCESSORS,
            },
        },
        "handlers": handlers,
        "loggers": {
            "": {  # Root logger
                "handlers": list(handlers.keys()),
                "level": log_level,
            },
            "pybit": {"level": "WARNING"},
            "websocket": {"level": "ERROR"},
            "urllib3": {"level": "WARNING"},
        },
    })

    structlog.configure(
        processors=SHARED_PROCESSORS + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
```

### Redaction Processor (Migrated from Current `redact_value()`)

```python
from src.utils.logger import REDACT_KEY_PATTERNS  # Reuse existing patterns

def _redact_processor(logger, method_name, event_dict):
    """Structlog processor that redacts sensitive fields."""
    for key in list(event_dict.keys()):
        key_lower = key.lower()
        for pattern in REDACT_KEY_PATTERNS:
            if pattern in key_lower:
                event_dict[key] = "***REDACTED***"
                break
    return event_dict
```

### Bound Context Usage (New Pattern)

```python
import structlog

# At engine startup — bind context once
log = structlog.get_logger("trade.engine")
log = log.bind(play_hash="8f2a9c1d", symbol="BTCUSDT", mode="live")

# All subsequent calls carry context automatically
log.info("signal_generated", action="ENTRY_LONG", bar_idx=247)
# JSONL: {"ts":"...","level":"info","play_hash":"8f2a9c1d","symbol":"BTCUSDT",
#          "mode":"live","event":"signal_generated","action":"ENTRY_LONG","bar_idx":247}

# Add more context for a trade
trade_log = log.bind(trade_num=5, entry_price=42150.0)
trade_log.info("position_opened", side="LONG", size_usdt=500.0)
```

### contextvars for Thread-Local Context

```python
import structlog

# At live runner startup — set context for this async task
structlog.contextvars.clear_contextvars()
structlog.contextvars.bind_contextvars(
    play_hash="8f2a9c1d",
    symbol="BTCUSDT",
    instance_id="abc123",
)

# Any logger in this async context picks up the vars
log = structlog.get_logger()
log.info("candle_received")  # play_hash, symbol, instance_id auto-attached
```

---

## Migration Strategy (Incremental, 4 Phases)

### Phase 1: Install + Configure (No Code Changes to Consumers)

**Goal**: structlog processes ALL log output. Zero consumer changes.

```
Files to create:
  src/utils/logging_config.py          ← New structlog configuration

Files to modify:
  trade_cli.py                         ← Call configure_logging() at startup
  requirements.txt / pyproject.toml    ← Add structlog dependency
  src/cli/validate.py                  ← Call configure_logging() in workers

Files unchanged:
  All 48 files with logger.info() calls  ← Still use stdlib, routed through structlog
```

**Verification**:
- `python trade_cli.py backtest run --play AT_001_ema_cross_basic --sync`
  - Console output should be colored (structlog ConsoleRenderer)
  - `logs/trade.jsonl` should contain JSONL lines
  - Old `bot_{date}.log` should NOT be created

**GATE**: `python trade_cli.py validate quick` passes with new logging config.

### Phase 2: Replace TradingLogger (29 Files)

**Goal**: Delete TradingLogger class. Replace `get_logger()` calls with structlog.

```
Files to modify:
  src/utils/logger.py                  ← Gut TradingLogger, keep get_module_logger()
  29 files using get_logger()          ← Replace with structlog.get_logger()

Specific replacements:
  # Before:
  from src.utils.logger import get_logger
  logger = get_logger()
  logger.trade("ORDER_PLACED", symbol="BTCUSDT", side="BUY", size=500)

  # After:
  import structlog
  logger = structlog.get_logger("trade.orders")
  logger.info("order_placed", channel="trade", symbol="BTCUSDT", side="BUY", size=500)
```

**Key methods to replace**:
- `.trade()` → `logger.info("trade_event", channel="trade", action=..., ...)`
- `.risk()` → `logger.info/warning("risk_event", channel="risk", ...)`
- `.panic()` → `logger.critical("panic", channel="safety", ...)`
- `.event()` → `logger.info("event_name", channel="event", ...)` (no more dual write)

**GATE**: `python trade_cli.py validate quick` passes.

### Phase 3: Add Bound Context (Engine + LiveRunner)

**Goal**: Use structlog's context binding for play_hash, symbol, mode.

```
Files to modify:
  src/engine/play_engine.py            ← Bind play_hash, symbol at init
  src/engine/runners/live_runner.py    ← Bind instance_id, mode
  src/engine/runners/backtest_runner.py ← Bind run context
  src/engine/factory.py                ← Pass bound logger to engine
```

**Pattern**:
```python
# PlayEngine.__init__():
self._log = structlog.get_logger("trade.engine").bind(
    play_hash=self._play_hash[:8],
    symbol=self._symbol,
    mode=self._config.mode,
)

# Later, in process_bar():
self._log.info("signal_generated", action=signal.action, bar_idx=bar_idx)
# Automatically includes play_hash, symbol, mode in output
```

**GATE**: `python trade_cli.py validate standard` passes.

### Phase 4: Cleanup (Delete Old Infrastructure)

**Goal**: Remove dead code, delete accumulated log files.

```
Files to delete:
  (none — logger.py is kept but gutted)

Code to delete from src/utils/logger.py:
  - TradingLogger class (lines 173-508)
  - ColoredFormatter class (lines 146-170) — replaced by ConsoleRenderer
  - _configure_third_party_loggers() — replaced by dictConfig loggers section
  - WebSocketErrorFilter class (lines 611-648) — move to processor if still needed

Code to keep in src/utils/logger.py:
  - get_module_logger() (line 546) — still used by 14 files, returns stdlib Logger
  - suppress_for_validation() (line 562) — still useful for quiet mode
  - redact_value() / redact_dict() — reused by structlog processor
  - REDACT_KEY_PATTERNS — reused

Files to clean up:
  logs/*.log                           ← Delete old unrotated logs (243 MB)
  logs/events_*.jsonl                  ← Delete 1,482 orphan JSONL files
  logs/backtests/                      ← Keep (per-run logs still useful)
```

**GATE**: `python trade_cli.py validate standard` passes. `logs/` directory < 10 MB.

---

## ProcessPoolExecutor Integration

Backtest validation workers need their own logging setup:

```python
# In each worker function (e.g., validate.py worker):
def _run_validation_worker(play_id: str, context: dict) -> Result:
    # Each worker reconfigures logging independently
    from src.utils.logging_config import configure_logging
    configure_logging(log_level="WARNING")  # Quiet for workers

    # Optional: bind context
    import structlog
    structlog.contextvars.bind_contextvars(**context)

    # ... run backtest ...
```

`structlog.configure()` is process-local — workers don't interfere with the parent.

---

## What Stays Unchanged

| Component | Why |
|-----------|-----|
| `debug.py` (verbose_log, debug_log, etc.) | Already gated with `is_debug_enabled()`. Uses stdlib `logging.getLogger("trade")` which routes through structlog automatically. No changes needed. |
| `get_module_logger(__name__)` | Returns stdlib Logger. structlog's ProcessorFormatter intercepts the output. All 14 call sites work unchanged. |
| `run_logger.py` (RunLogger) | Per-backtest artifact logging. Adds a temporary FileHandler to write `engine_debug.log` into the artifact folder. This is orthogonal to structlog — keeps working. |
| `suppress_for_validation()` | Sets `trade.*` to WARNING. Still works with structlog stdlib integration. |

---

## Disk Impact

| Metric | Before | After |
|--------|--------|-------|
| Files per day | 5+ (bot.log, trades.log, errors.log, pybit.log, events.jsonl) | 1 (trade.jsonl) |
| Files per process | 1 JSONL (events_{pid}.jsonl) | 0 extra (shared trade.jsonl) |
| Max disk usage | Unbounded (~3 GB/month) | 700 MB cap (100 MB × 7 rotated) |
| File count after 30 days | ~1,500+ | ~8 (trade.jsonl + 7 rotated) |
| Queryability | grep on plain text | `grep '"channel":"trade"'` on JSONL, or `jq` |

---

## Dependencies

```
# New dependency:
structlog >= 24.1.0    # Stable, well-maintained, MIT license

# Already in stack (no new deps):
logging (stdlib)
json (stdlib)
logging.handlers (stdlib)
```

---

## Verification Plan

After each phase:

1. **`python trade_cli.py validate quick`** — ensures backtest engine still works
2. **Check `logs/trade.jsonl` exists** — JSONL output working
3. **Check console output is colored** — ConsoleRenderer working
4. **Check `bot_*.log` NOT created** — old FileHandler removed
5. **Check `events_*.jsonl` NOT created** — per-PID files eliminated
6. **`python trade_cli.py -v backtest run --play AT_001_ema_cross_basic --sync`** — verbose mode works
7. **`python trade_cli.py --debug backtest run --play AT_001_ema_cross_basic --sync`** — debug mode works

Final verification:
- **`python trade_cli.py validate standard`** — full validation suite
- **`du -sh logs/`** — should be < 10 MB after cleanup
- **`ls logs/`** — should show trade.jsonl + maybe 1-2 rotated files
