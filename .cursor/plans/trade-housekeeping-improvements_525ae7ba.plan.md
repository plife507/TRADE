---
name: trade-housekeeping-improvements
overview: Refine the TRADE bot codebase with targeted housekeeping and best-practice changes across logging, data storage, CLI UX, and tests without altering core behavior.
todos:
  - id: logging-cleanup
    content: Fix ColoredFormatter and third-party logger configuration
    status: pending
  - id: data-quiet-mode
    content: Add verbose/quiet mode to HistoricalDataStore and gate prints
    status: pending
  - id: historical-split
    content: Split historical_data_store.py into focused data modules with stable API
    status: pending
  - id: cli-cleanup
    content: Trim trade_cli imports and unify env banners in CLI menus
    status: pending
  - id: tests-extensions
    content: Extend tests for logging, ToolRegistry env mismatch, and quiet mode
    status: pending
  - id: docs-deps-update
    content: Refresh docs/requirements to match refactors and optional TA-Lib usage
    status: pending
---

# TRADE Housekeeping & Best-Practices Plan

## Scope

Tighten logging, data, and CLI layers to align with project rules (safety, modularity, no hardcoding) while keeping all public behavior and APIs stable.

## Steps

### 1. Logging cleanup in `src/utils/logger.py`

- Update `ColoredFormatter` to avoid mutating `record.levelname`/`record.msg` so ANSI color codes stay console-only and do not leak into file logs.
- Ensure file handlers always receive uncolored messages by using separate formatter logic or formatting only within the console handler.
- Either wire up `WebSocketErrorFilter` to the appropriate loggers/handlers (e.g., `pybit` and WebSocket-related loggers) or remove it if you decide the behavior is not needed.
- Guard `_configure_third_party_loggers()` so it does not re-attach duplicate handlers on repeated logger setup (e.g., via an idempotent flag or checking existing handlers).

### 2. Refactor `src/data/historical_data_store.py` into focused modules

- Identify and group responsibilities in `historical_data_store.py`: (a) DB schema/connection & table naming, (b) sync/gap-filling/period parsing, (c) query/status APIs, (d) CLI-style UX helpers (spinners/emoji/prints).
- Create new focused modules under `src/data/` (for example `historical_store_core.py`, `historical_sync.py`, `historical_queries.py`, `historical_ui.py`) and move the corresponding code blocks while keeping imports and types intact.
- Keep `HistoricalDataStore` as the main public entry point; if you move the class, re-export it from `historical_data_store.py` so external imports remain `from src.data.historical_data_store import HistoricalDataStore`.
- Run the existing data-related tests and smoke tests to ensure there are no behavioral regressions after the split.

### 3. Quiet/non-interactive mode for data operations

- Introduce a `verbose: bool = True` (or similar) flag on `HistoricalDataStore` (and/or its key sync methods) to control whether spinners and `print_activity` emit to stdout.
- Route UX-oriented output (`ActivitySpinner`, `print_activity`) through this flag, and consider using the central logger for progress messages instead of raw `print` when `verbose` is False.
- Update CLI data menu calls in `src/cli/menus/data_menu.py` to explicitly use `verbose=True` so the interactive experience is unchanged, while orchestrators/tests can opt into `verbose=False`.

### 4. CLI shell & menu cleanup

- In `trade_cli.py`, trim imports from `src.tools` down to only the tools directly used in that file (connection test, health check, panic, smoke tests) and rely on `src/cli/menus/*` to import their own tools.
- Consolidate duplicated environment status banners across `src/cli/menus/orders_menu.py` and `src/cli/menus/positions_menu.py` into a shared helper (e.g., `print_trading_env_banner(config)` in `src/cli/utils.py` or `src/cli/styles.py`) and update both menus to call it.
- Remove any unused imports in menus (e.g., `print_result` where only `print_data_result` is used) and ensure menu functions consistently use the shared CLI utility functions from `src/cli/utils.py`.

### 5. Tests and behavior guards

- Add a small logging test (e.g., in `tests/`) that logs a message via `get_logger()` and asserts that file logs do not contain ANSI escape sequences after the formatter changes.
- Extend existing `ToolRegistry` tests (e.g., `tests/test_data_tools_builder.py` or `tests/test_trading_env.py`) to cover `trading_env` mismatch behavior: calling a trading tool with `trading_env="demo"` when the process is configured for live should return a `ToolResult` error, not raise.
- Add or update tests around `HistoricalDataStore` (or its public interface) to verify that enabling `verbose=False` suppresses stdout while keeping behavior and return values intact.

### 6. Documentation & dependency touch-ups

- Update relevant documentation references, if needed, to reflect any new data modules while keeping `HistoricalDataStore` as the main public entry point (e.g., adjust internal architecture diagrams in `docs/architecture/DATA_ARCHITECTURE.md` if they point to a monolithic file).
- If you decide `TA-Lib` is truly optional for infra-only use, consider documenting it as an optional dependency (or moving it into a separate requirements file) and note this in `README.md` without changing any current import behavior.

## Execution order

1) Implement and test logging fixes (formatter + third-party logger configuration) since they are low-risk and improve observability.
2) Add the quiet/verbose mode for data operations and adjust CLI usage so non-interactive consumers can opt out of prints.
3) Refactor `historical_data_store.py` into smaller modules, keeping imports stable and running data-related tests/smoke tests afterwards.
4) Clean up `trade_cli.py` imports and consolidate environment banners in CLI menus.
5) Add/extend tests and, finally, update docs/requirements to reflect the refactors and defaults.