# CLI Quick Reference

Quick lookup for CLI architecture, handler patterns, and adding new subcommands.

## Handler Checklist (Adding a New Subcommand)

```python
# 1. Define args in src/cli/argparser.py
def _setup_domain_subcommands(subparsers) -> None:
    domain_subparsers = subparsers.add_parser("domain")
    # ... add_subparsers for sub-subcommands ...
    cmd_parser = domain_subparsers.add_parser("action")
    cmd_parser.add_argument("--required-arg", required=True)

# 2. Create handler in src/cli/subcommands/domain.py
def handle_domain_action(args) -> int:
    from src.tools.domain_tools import action_tool
    result = action_tool(param=args.required_arg, ...)
    if args.json_output:
        return _json_result(result)
    return _print_result(result)

# 3. Create tool in src/tools/domain_tools.py
def action_tool(param: str) -> ToolResult:
    try:
        # Business logic here
        return ToolResult(success=True, message="OK", data={...})
    except Exception as e:
        return ToolResult(success=False, error=str(e))

# 4. Export in src/cli/subcommands/__init__.py
from src.cli.subcommands.domain import handle_domain_action
__all__ = [..., "handle_domain_action"]

# 5. Import in trade_cli.py
from src.cli.subcommands import (..., handle_domain_action)

# 6. Dispatch in main()
if args.command == "domain":
    if args.domain_command == "action":
        sys.exit(handle_domain_action(args))
```

## All Subcommand Groups (7 total)

| Group | Sub-subcommands | Status |
|-------|---|---|
| **backtest** | run, preflight, indicators, data-fix, list, play-normalize, play-normalize-batch | ✅ Full |
| **play** | run ✅, status, stop, watch, logs, pause, resume (stubs) | 🔶 Partial |
| **validate** | quick, standard, full, real, module, pre-live, exchange (tiers) | ✅ Full |
| **debug** | math-parity, snapshot-plumbing, determinism, metrics | ✅ Full |
| **account** | balance, exposure | ✅ Full |
| **position** | list, close | ✅ Full |
| **panic** | (single command) | ✅ Full |

## Global Flags

```bash
-q, --quiet       # WARNING only (validation workers)
-v, --verbose     # INFO + signal traces (debugging)
--debug           # DEBUG + hash tracing (development)
```

## JSON Output Pattern

Every handler checking `--json` flag:

```python
if getattr(args, "json_output", False):
    return _json_result(result)
```

Expected output:
```json
{
  "status": "pass" | "fail",
  "message": "Human-readable message",
  "data": { /* tool-specific structure */ }
}
```

## Common Helper Functions (subcommands/_helpers.py)

```python
_json_result(result: ToolResult) -> int      # Print JSON, return exit code
_print_result(result: ToolResult) -> int     # Print OK/FAIL, return exit code
_parse_datetime(dt_str: str) -> datetime     # Parse YYYY-MM-DD or YYYY-MM-DD HH:MM
_print_preflight_diagnostics(diag: dict)    # Pretty-print diagnostics table
```

## ToolResult Envelope

All tool functions return:

```python
class ToolResult:
    success: bool          # True if operation succeeded
    message: str          # "OK message" if success
    error: str           # Error details if not success
    data: dict | None    # Structured output (varies by tool)
```

## Interactive Menus (8 total)

| Menu | Purpose | Submenus |
|---|---|---|
| **account_menu** | Account ops | Balance, Portfolio, History, Transactions |
| **positions_menu** | Position mgmt | List, Close, TP/SL, Margin, Trailing stops |
| **orders_menu** | Order placement | Place (Market/Limit/Stop), Manage (List/Amend/Cancel) |
| **market_data_menu** | Market data | Ticker, OHLCV, Funding, Orderbook, Instruments |
| **data_menu** | Data builder | Build, Sync, Browse, Maintenance (LIVE/DEMO state) |
| **backtest_menu** | Backtesting | Play, Analytics, Audits, Data maintenance |
| **forge_menu** | Play dev | Validate, Batch, Audits, Stress tests |
| **plays_menu** | Play lifecycle | Run, Monitor, Stop (future) |

## Menu Pattern

```python
def domain_menu(cli: "TradeCLI"):
    while True:
        clear_screen()
        print_header()

        menu = CLIStyles.create_menu_table()
        menu.add_row("1", "Option A", "Description")
        menu.add_row("2", "Option B", "Description")
        console.print(menu)

        choice = get_choice(range(1, N))

        if choice is BACK:
            break
        elif choice == 1:
            _action_a()
        elif choice == 2:
            _action_b()
```

## Data Menu State (Unique Pattern)

Data menu maintains local `data_env` variable (LIVE/DEMO) within session:

```python
def data_menu(cli: "TradeCLI"):
    data_env: DataEnv = DEFAULT_DATA_ENV  # Persists across menu iterations

    while True:
        # All actions in this menu use data_env
        # User can toggle with menu choice
```

## Key Files Reference

| File | Purpose |
|---|---|
| `trade_cli.py` | Main CLI entry, TradeCLI class, main() dispatcher |
| `src/cli/argparser.py` | Subcommand registration (_setup_* functions) |
| `src/cli/subcommands/` | Handler implementations (parse → tool → format) |
| `src/cli/subcommands/__init__.py` | Handler re-exports |
| `src/cli/subcommands/_helpers.py` | Shared helpers (_json_result, _print_result, etc.) |
| `src/cli/menus/` | Interactive menu handlers |
| `src/tools/` | Tool functions (business logic layer) |
| `docs/architecture/ARCHITECTURE.md` | System architecture & roadmap |

## Common Mistakes to Avoid

❌ **Don't**: Directly check JSON output in tool functions
✅ **Do**: Check in handler (before calling tool)

❌ **Don't**: Put business logic in handler
✅ **Do**: Put in tool function (handler is thin parsing/formatting layer)

❌ **Don't**: Throw exceptions from tool functions
✅ **Do**: Return `ToolResult(success=False, error=msg)`

❌ **Don't**: Add logging directly to handler
✅ **Do**: Use `src.utils.debug` (verbose_log, debug_log) in tools with gating

❌ **Don't**: Reuse handler code between subcommands
✅ **Do**: Extract shared logic to tool functions

## Testing a New Subcommand

```bash
# Test basic flow
python trade_cli.py domain action --required-arg value

# Test JSON output
python trade_cli.py domain action --required-arg value --json

# Test with verbosity
python trade_cli.py -v domain action --required-arg value
python trade_cli.py --debug domain action --required-arg value

# Test with quiet mode (validation)
python trade_cli.py -q domain action --required-arg value
```

## Related Documentation

- **`docs/architecture/ARCHITECTURE.md`** — System architecture & roadmap
- **`docs/TODO.md`** — Project status, current gates
- **`docs/VALIDATION_BEST_PRACTICES.md`** — Validation tier details
- **`docs/PLAY_DSL_REFERENCE.md`** — Play YAML structure
