# Codebase Review (trade_cli + src)

Date: 2026-02-17
Scope: `trade_cli.py` and all Python files under `src/`
Reviewer: Cursor AI code review pass

## Review Method

This review combined:

- Static checks: `pyright`
- Project validation: `python trade_cli.py validate quick`
- Targeted source inspection of CLI, backtest feed/data plumbing, and safety-sensitive execution paths
- Pattern scan for broad exception handling and risky runtime behavior

## Validation Snapshot

- `python trade_cli.py validate quick` -> PASS (all 4 gates)
- `pyright` -> PASS (0 errors) — original 9 errors fixed in 32-bug audit (2026-02-17)

## Findings (Ordered by Severity)

### Medium

#### 1) ~~Optional DataFrame type narrowing is incomplete in feed builder~~ RESOLVED

- **Status**: Fixed in 32-bug audit (2026-02-17). pyright now reports 0 errors.
- File: `src/backtest/engine_feed_builder.py`
- Original issue: pyright flagged 9 errors on `iterrows`/subscript/member access on possible `None`.
- Resolution: Type narrowing fixed; pyright passes clean.

#### 2) ~~Timestamp comparison path may mix naive and aware datetimes~~ RESOLVED

- **Status**: Fixed (2026-02-17). `_to_naive_datetime()` helper normalizes all timestamps to UTC-naive before `<=` comparisons.
- File: `src/backtest/engine_feed_builder.py`
- Original issue: Ad-hoc `to_pydatetime()` conversions could mix tz-naive and tz-aware datetimes in funding/OI alignment loops.
- Resolution: Single `_to_naive_datetime()` normalizer strips tzinfo after UTC conversion. Applied to both funding and OI loops.

### Low

#### 3) Forced process exit bypasses normal interpreter shutdown — ACCEPTED

- **Status**: By design. pybit WebSocket threads are non-daemon; `sys.exit()` would hang. No clean fix without changing pybit's thread model.
- File: `trade_cli.py:863`
- `os._exit(0)` runs after `cli.shutdown()` which already calls `app.stop()` → `_stop_websocket()` with timeout. Revisit only if thread model changes.

## Observations (Non-blocking)

- `except Exception as e` is common across runtime and exchange-facing modules. This is expected in boundary layers but should be paired with consistent structured logging and explicit fallback behavior.
- No bare `except:` blocks were found in the reviewed tree scan.

## Remediation Status

All three findings resolved or accepted:

1. ~~Fix type narrowing in feed builder~~ — RESOLVED (32-bug audit)
2. ~~Add explicit timezone normalization~~ — RESOLVED (`_to_naive_datetime()`)
3. ~~Re-evaluate CLI shutdown~~ — ACCEPTED (by design, no fix needed)

## Suggested Verification Commands

After remediation:

- `pyright`
- `python trade_cli.py validate quick`
- `python trade_cli.py backtest run --play <PLAY_ID> --sync`
- `python trade_cli.py debug snapshot-plumbing --play <PLAY_ID>`

## Residual Risk

This document captures a comprehensive static and targeted manual review pass. A literal human-only line-by-line audit of every file under `src/` should be done in subsystem batches (`core/engine`, `backtest`, `cli/tools`, `forge/indicators/structures`) if you want maximal assurance before major releases.
