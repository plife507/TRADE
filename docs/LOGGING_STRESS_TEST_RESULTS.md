# P18.5: Logging Module Stress Test Results

## Status: PASS (14/14)

Script: `scripts/test_logging_module.py`

## Test Matrix

| # | Test | Status | Notes |
|---|------|--------|-------|
| 01 | Contextvars cross-thread | PASS | play_hash, symbol, mode survive QueueHandler thread boundary |
| 02 | File rotation | PASS | 5 files created (100KB maxBytes, backupCount=7) |
| 03 | Concurrent thread logging | PASS | 200/200 msgs, 0 invalid JSON lines |
| 04 | suppress_for_validation | PASS | INFO suppressed, WARNING flows through |
| 05 | Verbosity flags | PASS | All 3 levels (quiet/verbose/debug) gate correctly via JSONL |
| 06 | Redaction in JSONL | PASS | Both stdlib + native paths redacted (after QueueHandler fix) |
| 07 | Shutdown drain | PASS | 500/500 messages drained on shutdown |
| 08 | bind/clear lifecycle | PASS | Context present when bound, absent after clear |
| 09 | Debug gating overhead | PASS | 100k no-op calls in 0.008s (limit 0.5s) |
| 10 | RunLogger finalize | PASS | Handler removed, index.jsonl written, per-run log created |
| 11 | JSONL validity | PASS | All 9 edge-case messages (unicode, long, special chars) valid JSON |
| 12 | Console vs file format | PASS | Console=human-readable, file=JSON |
| 13 | Idempotency | PASS | configure_logging() twice: 2 handlers both times |
| 14 | Empty context | PASS | No spurious engine fields when no context bound |

## Bug Found & Fixed: structlog native logger + QueueHandler incompatibility

### Root Cause

When using `structlog.get_logger()` (native structlog bound logger), Python's stdlib `QueueHandler.prepare()` calls `self.format(record)` which converts `record.msg` from a dict to a string. On the QueueListener thread, `ProcessorFormatter` then fails with `AttributeError: 'str' object has no attribute 'copy'`. This only affects the file (JSONL) path; console output works because its ProcessorFormatter runs on the calling thread before queueing.

### Fix Applied

**`_StructlogQueueHandler`** (in `src/utils/logging_config.py`): Overrides `prepare()` to skip the `self.format()` call, preserving dict-typed `record.msg` across the queue boundary. Both structlog-native and stdlib loggers now correctly write to JSONL.

### Lint Guard Added

**Gate G16: Logging Lint** (in `src/cli/validate.py`): Scans all 324 files in `src/` for `structlog.get_logger()` or `structlog.getLogger()` calls, enforcing the project convention of using `get_module_logger()`. Runs in Stage 0 of `validate quick` alongside YAML parse.

```bash
# Run standalone
python trade_cli.py validate module --module lint --json

# Runs automatically in every validate tier
python trade_cli.py validate quick  # Now shows 6 gates (was 5)
```

## Run Log

- **2026-02-24 Run 1**: 12/14 pass. Tests 05 and 06 failed.
  - Test 05 root cause: handler attached to wrong logger name (`trade.test.verbosity` vs `trade.utils.debug`)
  - Test 06 root cause: `structlog.get_logger()` + QueueHandler.prepare() destroys dict msg
- **2026-02-24 Run 2**: 14/14 pass after test fixes (JSONL-based checks)
- **2026-02-24 Run 3**: 14/14 pass after production fix (`_StructlogQueueHandler`) + lint guard (G16)
  - Test 06 now exercises BOTH stdlib and native paths
  - `validate quick` passes with 6 gates (G1 + G16 in Stage 0)
