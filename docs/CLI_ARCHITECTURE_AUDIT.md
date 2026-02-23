# TRADE CLI Architecture Audit

**Date**: 2026-02-22
**Scope**: Complete enumeration of CLI subcommand groups, handlers, wiring patterns, and menu structure.

---

## Executive Summary

The TRADE CLI has a **dual-layer architecture**:

1. **Non-interactive mode** (subcommands): Via `argparse` → handlers in `src/cli/subcommands/` → tool functions in `src/tools/`
2. **Interactive mode** (menus): Via `trade_cli.py` main menu → menu functions in `src/cli/menus/` → tool functions in `src/tools/`

Both layers converge on the same tool functions (`src/tools/`), making them the canonical business logic layer.

---

## Part 1: Argparse Architecture (Non-Interactive Mode)

### Main Entry Point: `trade_cli.py`

**File**: `/mnt/c/CODE/AI/TRADE/trade_cli.py`

- **Class**: `TradeCLI` — pure shell, no business logic
  - `connect_to_exchange()` — interactive connection flow (DEMO/LIVE selection + confirmation)
  - `main_menu()` — dispatches to menu handlers
  - `panic_menu()` — emergency close all positions
  - Various menu delegates: `account_menu()`, `positions_menu()`, etc.

- **Top-level main() function** (lines 709–854):
  - Parses args via `setup_argparse()` (from `src.cli.argparser`)
  - Routes to non-interactive handlers based on `args.command`:
    - `backtest`, `debug`, `play`, `validate`, `account`, `position`, `panic`
  - Falls through to interactive mode if no command specified
  - Forces exit via `os._exit(0)` to kill lingering pybit WebSocket threads

---

### Argparse Setup: `src/cli/argparser.py`

**Responsibility**: Define all subcommand groups and their arguments.

#### Subcommand Groups Registered

| Group | Handler Module | Tier | Commands |
|-------|---|---|---|
| **backtest** | `subcommands.backtest` | Operational | 7 sub-subcommands |
| **play** | `subcommands.play` | Operational | 7 sub-subcommands |
| **validate** | `src.cli.validate` | Operational | 1 command (with 7 tiers) |
| **debug** | `subcommands.debug` | Diagnostic | 4 sub-subcommands |
| **account** | `subcommands.trading` | Operational | 2 sub-subcommands |
| **position** | `subcommands.trading` | Operational | 2 sub-subcommands |
| **panic** | `subcommands.trading` | Operational | 1 command |

#### Global Flags (Mutually Exclusive)

```
-q, --quiet       → WARNING only, minimal output (validation workers)
-v, --verbose     → INFO + signal evaluation traces
--debug           → DEBUG + hash tracing (sets TRADE_DEBUG=1)
```

---

### Backtest Subcommands

**Route**: `backtest <subcommand> [options]`
**Handler Module**: `src/cli/subcommands/backtest.py`

| Subcommand | Handler | Arguments | Purpose |
|---|---|---|---|
| **run** | `handle_backtest_run()` | `--play` (required), `--start`, `--end`, `--smoke`, `--sync`, `--validate`, `--synthetic` | Execute single Play backtest |
| **preflight** | `handle_backtest_preflight()` | `--play`, `--start`, `--end`, `--sync` | Validate config/data without running |
| **indicators** | `handle_backtest_indicators()` | `--play` OR `--audit-math-from-snapshots`, `--compute`, `--start`, `--end` | Discover/audit indicator keys |
| **data-fix** | `handle_backtest_data_fix()` | `--play`, `--start`, `--sync-to-now`, `--heal` | Fix/heal data gaps |
| **list** | `handle_backtest_list()` | `--dir` | List available Plays |
| **play-normalize** | `handle_backtest_normalize()` | `--play`, `--write` | Validate + normalize YAML (build-time) |
| **play-normalize-batch** | `handle_backtest_normalize_batch()` | `--dir` (required), `--write` | Batch normalize Play directory |

**Handler Pattern** (example from `handle_backtest_run()`):
```python
def handle_backtest_run(args) -> int:
    """Handle `backtest run` subcommand."""
    # 1. Parse CLI args
    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else None

    # 2. Call tool function
    result = backtest_run_play_tool(
        play_id=args.play,
        env=args.data_env,
        start=start,
        end=end,
        # ... more args
    )

    # 3. Format output
    if args.json_output:
        return _json_result(result)
    return _print_result(result)
```

---

### Play Subcommands

**Route**: `play <subcommand> [options]`
**Handler Module**: `src/cli/subcommands/play.py`

| Subcommand | Handler | Arguments | Purpose |
|---|---|---|---|
| **run** | `handle_play_run()` | `--play`, `--mode` (backtest\|demo\|live\|shadow), `--start`, `--end`, `--confirm` | Run Play in specified mode |
| **status** | `handle_play_status()` | `--play` (optional) | Check running instances |
| **stop** | `handle_play_stop()` | `--play`, `--force`, `--all`, `--close-positions` | Stop running instance |
| **watch** | `handle_play_watch()` | `--play` (optional), `--interval` | Live dashboard |
| **logs** | `handle_play_logs()` | `--play` (required), `--follow`, `--lines` | Stream logs |
| **pause** | `handle_play_pause()` | `--play` (required) | Pause signal evaluation |
| **resume** | `handle_play_resume()` | `--play` (required) | Resume paused instance |

**Note**: These are "future" placeholders except `run`. Most are not implemented yet.

---

### Debug Subcommands

**Route**: `debug <subcommand> [options]`
**Handler Module**: `src/cli/subcommands/debug.py`

| Subcommand | Handler | Arguments | Purpose |
|---|---|---|---|
| **math-parity** | `handle_debug_math_parity()` | `--play`, `--start`, `--end`, `--output-dir`, `--contract-sample-bars` | Validate indicator math (contract + in-memory) |
| **snapshot-plumbing** | `handle_debug_snapshot_plumbing()` | `--play`, `--start`, `--end`, `--max-samples`, `--tolerance` | Snapshot field correctness audit |
| **determinism** | `handle_debug_determinism()` | `--run-a`, `--run-b` OR `--re-run`, `--sync` | Compare run hashes for determinism |
| **metrics** | `handle_debug_metrics()` | (no args) | Financial metrics audit |

---

### Validate Subcommand

**Route**: `validate <tier> [options]`
**Handler Module**: `src.cli.validate.run_validation()`

| Tier | Duration | Purpose |
|---|---|---|
| **quick** | ~7s | Pre-commit gate (smoke tests) |
| **standard** | ~20s | Pre-merge gate |
| **full** | ~50s | Pre-release gate (all 170 plays) |
| **real** | ~2min | Real-data verification (60 plays) |
| **module** | varies | Single module validation (requires `--module`) |
| **pre-live** | varies | Deployment gate (requires `--play`) |
| **exchange** | ~30s | Exchange integration tests |

**Options**: `--play`, `--module`, `--workers`, `--timeout`, `--gate-timeout`, `--json`

---

### Account Subcommands

**Route**: `account <subcommand>`
**Handler Module**: `src/cli/subcommands/trading.py`

| Subcommand | Handler | Purpose |
|---|---|---|
| **balance** | `handle_account_balance()` | Show account balance (equity, available, wallet) |
| **exposure** | `handle_account_exposure()` | Show total exposure (USD) |

**Tool Functions Called**:
- `get_account_balance_tool()` from `src.tools.account_tools`
- `get_total_exposure_tool()` from `src.tools.account_tools`

---

### Position Subcommands

**Route**: `position <subcommand>`
**Handler Module**: `src/cli/subcommands/trading.py`

| Subcommand | Handler | Arguments | Purpose |
|---|---|---|---|
| **list** | `handle_position_list()` | none | List open positions |
| **close** | `handle_position_close()` | `symbol` (required) | Close a specific position |

**Tool Functions Called**:
- `list_open_positions_tool()` from `src.tools.position_tools`
- `close_position_tool()` from `src.tools.position_tools`

---

### Panic Subcommand

**Route**: `panic`
**Handler Module**: `src/cli/subcommands/trading.py`

| Subcommand | Handler | Arguments | Purpose |
|---|---|---|---|
| **panic** | `handle_panic()` | `--confirm` (required) | Emergency: close all + cancel all |

**Tool Function Called**:
- `panic_close_all_tool()` from `src.tools`

---

## Part 2: Handler Dispatch Pattern

All 23 handlers follow the same pattern:

### Standard Pattern (3 Layers)

```
User Input (args)
    ↓
Handler in src/cli/subcommands/
    ├─ Parse args (datetimes, paths, etc.)
    ├─ Call tool function from src/tools/
    └─ Format result (--json or human-readable)
        ↓
Tool Function (src/tools/)
    └─ Business logic (no CLI concerns)
        ↓
Result (ToolResult object)
    ├─ status: success | fail
    ├─ message: human-readable message
    ├─ data: structured output (dict)
    └─ error: error details (if fail)
```

### Helper Functions (`src/cli/subcommands/_helpers.py`)

```python
_json_result(result: ToolResult) -> int
  └─ Prints {"status", "message", "data"} JSON envelope

_print_result(result: ToolResult) -> int
  └─ Prints "OK" or "FAIL" status line

_parse_datetime(dt_str: str) -> datetime
  └─ Flexible datetime parser (4 formats supported)

_print_preflight_diagnostics(diag: dict)
  └─ Pretty-prints preflight report (diagnostics table)
```

---

## Part 3: Interactive Menu Architecture

### Menu Entry Point: `TradeCLI.main_menu()`

**File**: `trade_cli.py`, lines 376–555

Two states:
1. **Disconnected** — 7 menu items (data, backtest, forge, validate, connect, health, exit)
2. **Connected** — 11 items (DEMO) or 12 items (LIVE) with trading menus added

Each menu choice delegates to a handler function.

---

### Menu Handlers (`src/cli/menus/`)

**Structure**: Each menu file exports a single function named `{menu_name}_menu(cli: TradeCLI)`.

| Menu Module | Function | Purpose | Submenus |
|---|---|---|---|
| **account_menu.py** | `account_menu(cli)` | Account info | Balance, Portfolio, History, Transactions |
| **positions_menu.py** | `positions_menu(cli)` | Position mgmt | List, Close, TP/SL, Margin, Trailing stops |
| **orders_menu.py** | `orders_menu(cli)` | Order placement | Place (Market/Limit/Stop), Manage (List/Amend/Cancel) |
| **market_data_menu.py** | `market_data_menu(cli)` | Market data | Ticker, OHLCV, Funding, Orderbook, Instruments |
| **data_menu.py** | `data_menu(cli)` | Data builder | Build, Sync, Browse, Maintenance, Settings |
| **backtest_menu.py** | `backtest_menu(cli)` | Backtest engine | Run, List, Analytics, Audits |
| **forge_menu.py** | `forge_menu(cli)` | Play development | Validate, Batch validate, Audits, Stress tests |
| **plays_menu.py** | `plays_menu(cli)` | Play lifecycle | Run, Monitor, Stop (future) |

---

### Menu Pattern

Each menu function:

```python
def {menu_name}_menu(cli: "TradeCLI"):
    """Menu handler."""
    while True:
        clear_screen()
        print_header()

        # Build menu table
        menu = CLIStyles.create_menu_table()
        menu.add_row("1", "Option A", "Description")
        menu.add_row("2", "Option B", "Description")
        # ...

        console.print(menu)
        choice = get_choice(range(1, N))

        if choice is BACK:
            break
        elif choice == 1:
            _submenu_or_action()
        elif choice == 2:
            _another_action()
        # ...
```

---

### Data Menu State Management

**File**: `src/cli/menus/data_menu.py`

Unique feature: local `data_env` variable persists within the menu session (LIVE or DEMO).

```python
while True:
    clear_screen()

    # data_env can be toggled with "8" option
    data_env: DataEnv = "live"  # or "demo"

    # All actions within this menu use data_env
    # e.g., sync_to_now_tool(symbols=..., env=data_env)
```

**Note**: This is menu-local state. Not shared across menu sessions.

---

### Orders Menu Status

**File**: `src/cli/menus/orders_menu.py`

**Current status**: 2-group flat structure:
1. **Place** — Unified order form (type → side → symbol → amount → conditional fields)
2. **Manage** — List, amend, cancel, cancel-all

**Key observation**: P4 gate says "old sub-menu functions already deleted" → suggests past restructuring.

All order functions are implemented and wired to tool functions.

---

### Forge Menu Status

**File**: `src/cli/menus/forge_menu.py`

**Current status**: 8 items covering validation + audits + stress tests:

```
--- Validation ---
1. Validate Play (single)
2. Validate Batch (directory)
3. Validate All

--- Audits ---
4. Toolkit Audit (indicator registry)
5. Rollup Audit (price rollup parity)

--- Stress Tests ---
6. Stress Test Suite (full pipeline)
7. Run Play (Synthetic, no DB)

--- Navigation ---
8. Go to Backtest Engine
0. Back
```

All menu items are implemented and call tool functions from `src/tools/`.

---

### Backtest Menu Status

**File**: `src/cli/menus/backtest_menu.py`

Delegates to 4 submenus:
1. **backtest_play_menu.py** — Run, list, indicators
2. **backtest_analytics_menu.py** — PnL, drawdown, etc.
3. **backtest_audits_menu.py** — Determinism, math parity, etc.
4. **data_maintenance_menu.py** — Data ops (sync, heal, delete)

Plus additional submenus for data queries and sync operations.

---

## Part 4: Tool Layer Architecture

### Tool Organization (`src/tools/`)

Tool functions are organized by domain:

| Module | Purpose | Tool Count |
|---|---|---|
| **account_tools.py** | Account balance, exposure | 2 |
| **position_tools.py** | Position listing, closing | 2 |
| **order_tools.py** | Order placement (market/limit/stop) | 8+ |
| **market_data_tools.py** | Ticker, OHLCV, funding rates | 4+ |
| **data_tools.py** | Data sync, build history | 3+ |
| **backtest_play_tools.py** | Backtest run, preflight, indicators | 3+ |
| **backtest_play_data_tools.py** | Data fix, sync, heal | 3+ |
| **backtest_play_normalize_tools.py** | YAML validation, normalization | 2 |
| **diagnostics_tools.py** | Connection, health checks | 5 |
| **forge_stress_test_tools.py** | Validation, audits | 2+ |
| **shared.py** | ToolResult class, common patterns | – |

### ToolResult Envelope

All tool functions return `ToolResult`:

```python
class ToolResult:
    success: bool
    message: str           # OK message if success
    error: str            # Error details if not success
    data: dict | None     # Structured output (varies by tool)
```

**JSON Output Pattern**:
```json
{
  "status": "pass" | "fail",
  "message": "...",
  "data": { /* tool-specific */ }
}
```

---

## Part 5: Subcommand Registration Wiring

### Import Flow

```
trade_cli.py (main())
  ↓
setup_argparse() [src/cli/argparser.py]
  ├─ _setup_backtest_subcommands(subparsers)
  ├─ _setup_play_subcommands(subparsers)
  ├─ _setup_validate_subcommand(subparsers)
  ├─ _setup_debug_subcommands(subparsers)
  ├─ _setup_account_subcommands(subparsers)
  ├─ _setup_position_subcommands(subparsers)
  └─ _setup_panic_subcommand(subparsers)

  → Returns argparse.Namespace with:
     args.command = "backtest" | "play" | "validate" | "debug" | "account" | "position" | "panic"
     args.{subcommand}_command = sub-subcommand name
     args.{option_name} = option value
```

### Handler Imports

Handlers are imported at the top of `trade_cli.py` (lines 85–106):

```python
from src.cli.subcommands import (
    handle_backtest_run,
    handle_backtest_preflight,
    # ... 20 more handles
)
```

Re-exported from `src/cli/subcommands/__init__.py` (clean namespace).

### Dispatch Logic in main()

```python
if args.command == "backtest":
    if args.backtest_command == "run":
        sys.exit(handle_backtest_run(args))
    elif args.backtest_command == "preflight":
        sys.exit(handle_backtest_preflight(args))
    # ... etc

if args.command == "validate":
    from src.cli.validate import run_validation, Tier
    tier = Tier(args.tier)
    sys.exit(run_validation(tier=tier, ...))
```

---

## Part 6: How to Add a New Subcommand

### Example: Add `backtest foo` subcommand

#### Step 1: Define Arguments in `src/cli/argparser.py`

```python
def _setup_backtest_subcommands(subparsers) -> None:
    backtest_subparsers = # ... (already exists)

    # Add new subcommand
    foo_parser = backtest_subparsers.add_parser("foo", help="Do foo")
    foo_parser.add_argument("--play", required=True, help="Play ID")
    foo_parser.add_argument("--option", default="value", help="Optional arg")
```

#### Step 2: Create Handler in `src/cli/subcommands/backtest.py`

```python
def handle_backtest_foo(args) -> int:
    """Handle `backtest foo` subcommand."""
    from src.tools.backtest_play_tools import foo_tool

    result = foo_tool(
        play_id=args.play,
        option=args.option,
    )

    if args.json_output:
        return _json_result(result)
    return _print_result(result)
```

#### Step 3: Create Tool Function in `src/tools/backtest_play_tools.py`

```python
def foo_tool(play_id: str, option: str) -> ToolResult:
    """Foo operation on a Play."""
    # Business logic here (no CLI concerns)
    # Return ToolResult(success=..., message=..., data=...)
```

#### Step 4: Export Handler in `src/cli/subcommands/__init__.py`

```python
from src.cli.subcommands.backtest import (
    # ... existing
    handle_backtest_foo,  # NEW
)

__all__ = [
    # ... existing
    "handle_backtest_foo",  # NEW
]
```

#### Step 5: Import Handler in `trade_cli.py`

```python
from src.cli.subcommands import (
    # ... existing
    handle_backtest_foo,  # NEW
)
```

#### Step 6: Dispatch in `main()`

```python
if args.command == "backtest":
    if args.backtest_command == "foo":
        sys.exit(handle_backtest_foo(args))  # NEW
    elif args.backtest_command == "run":
        # ... existing
```

---

## Part 7: Key Patterns and Conventions

### Naming Conventions

| Entity | Pattern | Example |
|---|---|---|
| Subcommand | `{domain}` (lowercase, dash-separated) | `backtest`, `play`, `debug` |
| Sub-subcommand | `{action}` (lowercase, dash-separated) | `run`, `preflight`, `math-parity` |
| Handler function | `handle_{domain}_{action}()` | `handle_backtest_run()`, `handle_debug_math_parity()` |
| Tool function | `{action}_tool()` (verb-based) | `backtest_run_play_tool()`, `get_account_balance_tool()` |
| Menu function | `{domain}_menu()` | `data_menu()`, `account_menu()` |
| Menu action | `_{action}()` (private) | `_validate_single_play()`, `_place_order()` |

### JSON Output

**Every** handler that might be called with `--json` should use `_json_result()`:

```python
if getattr(args, "json_output", False):
    return _json_result(result)
```

**Expected output**:
```json
{
  "status": "pass" | "fail",
  "message": "OK message" | "Error message",
  "data": { /* tool-specific structure */ }
}
```

### Error Handling

- Handlers: Catch exceptions, convert to `ToolResult(success=False, error=msg)`
- CLI layer: Print error and return non-zero exit code
- Never let exceptions escape to main() unless unrecoverable

### Verbosity Control

**In handlers**:
```python
if not getattr(args, "json_output", False):
    console.print(Panel(f"Running {args.play}..."))
```

**In tool functions**: Use `src.utils.debug` module:
```python
from src.utils.debug import verbose_log, debug_log

verbose_log(play_hash, "Signal fired", direction="long")  # INFO gated on -v
debug_log(play_hash, "Position updated", qty=10)  # DEBUG gated on --debug
```

---

## Part 8: Status Summary

### Fully Implemented Subcommands

✅ `backtest run`, `backtest preflight`, `backtest indicators`, `backtest list`, `backtest data-fix`, `backtest play-normalize`, `backtest play-normalize-batch`

✅ `debug math-parity`, `debug snapshot-plumbing`, `debug determinism`, `debug metrics`

✅ `account balance`, `account exposure`

✅ `position list`, `position close`

✅ `panic`

✅ `validate` (all tiers)

### Partially Implemented (Placeholder)

🔶 `play run` — Basic implementation exists

🔶 `play status`, `play stop`, `play watch`, `play logs`, `play pause`, `play resume` — Registered but mostly stub implementations

---

## Part 9: Recent Changes (P4/P13 Era)

From TODO.md and commit history:

- **P4 Gate 4**: Orders menu refactor — "old sub-menu functions already deleted"
- **P4 Gate 5**: Data menu refactor (state management for LIVE/DEMO env)
- **P13**: CLI autonomy audit and redesign — cross-reference in `docs/CLI_REDESIGN.md`

These indicate the CLI underwent structural cleanup, with legacy code paths removed.

---

## Part 10: Cross-Reference to Related Docs

- **`docs/TODO.md`** — Current project status, P13 CLI redesign gates
- **`docs/CLI_REDESIGN.md`** — CLI autonomy architecture (P13 G1-G3, G6, G7, G9)
- **`docs/PLAY_DSL_REFERENCE.md`** — Play YAML structure (used by validate, forge)
- **`docs/VALIDATION_BEST_PRACTICES.md`** — How validation tiers work

---

## Conclusion

The TRADE CLI architecture is clean and scalable:

1. **Argparse layer** provides CLI argument parsing
2. **Handler layer** (one per subcommand) is thin → parses args → calls tools → formats output
3. **Tool layer** contains all business logic → no CLI concerns
4. **Menu layer** provides interactive alternative to subcommands → calls same tool functions

**Key principle**: CLI is a shell, tools are the core. Multiple interfaces (subcommands, menus) can front the same tools.

New features are added by:
1. Defining args in argparser
2. Writing a handler (parse → tool → format)
3. Creating tool function (pure business logic)
4. Wiring imports and dispatch

This document serves as the reference for CLI architecture. For P13 and beyond, extend it with autonomy features, multi-agent coordination, and dynamic capability discovery.
