# TRADE CLI Reference

Headless subcommand interface for agents, scripts, and automation.
No interactive mode — all access via `python trade_cli.py <command> [subcommand] [args]`.

## Architecture

```
trade_cli.py (337 lines)          Entry point: argparse + dispatch
  src/cli/argparser.py (652)      Argument definitions for 11 command groups
  src/cli/subcommands/ (2978)     63 handler functions (args -> tool -> format)
    _helpers.py                   _json_result, _print_result, _parse_datetime
  src/cli/utils.py (6)            console singleton only
  src/cli/validate.py (1864)      Validation suite engine
  src/cli/validate_timestamps.py  G17 timestamp gate (503 checks)
  src/cli/dashboard/ (~2500)      Rich TUI for live play monitoring
  src/cli/smoke_tests/ (~1860)    Smoke test infrastructure
```

**Data flow**: `argparse -> handler(args) -> tool_fn() -> ToolResult -> format -> exit code`

Every handler follows this contract:
1. Extract args from `argparse.Namespace`
2. Call a tool function from `src/tools/`
3. Format output (JSON via `_json_result()` or Rich via `_print_result()`)
4. Return exit code (0 = success, 1 = failure)

## JSON Output Contract

All `--json` output uses a standard envelope:

```json
{
  "status": "pass" | "fail",
  "message": "Human-readable summary",
  "data": { /* command-specific payload */ }
}
```

This is the contract for the planned Node.js interface.

## Global Flags

```bash
-q, --quiet       # WARNING only — CI, validation workers, scripted runs
-v, --verbose     # INFO + signal/structure traces — debug why signals don't fire
--debug           # DEBUG + full hash tracing — development, determinism checks
```

## Command Reference

### backtest — Play-based backtesting (offline)

```bash
backtest run --play X [--synthetic] [--json]           # Run backtest (golden path)
backtest run --play X --synthetic --synthetic-seed 42   # Reproducible synthetic run
backtest run --play X --start 2025-01-01 --end 2025-06-30 --sync  # Real data with auto-sync
backtest preflight --play X [--json]                    # Check data/config without running
backtest indicators --play X [--json]                   # List resolved indicators
backtest data-fix --play X [--sync] [--heal] [--json]   # Fix data gaps
backtest list [--json]                                   # List available plays
backtest play-normalize --play X [--write] [--json]      # Normalize play YAML
backtest play-normalize-batch --dir plays/ [--write]     # Batch normalize
```

### play — Unified play engine (all modes)

```bash
play run --play X --mode backtest [--json]              # Backtest via play engine
play run --play X --mode live --confirm [--json]        # Live trading (REAL MONEY)
play run --play X --mode shadow [--json]                # Signal logging, no execution
play status [--play X] [--json]                         # Check running instances
play stop [--play X] [--force] [--all]                  # Stop running instance
play watch --play X [--interval 2.0] [--json]           # Watch live snapshots
play logs --play X [-f] [-n 50]                         # Tail play logs
play pause --play X                                     # Pause signal processing
play resume --play X                                    # Resume signal processing
```

### validate — Validation suite

```bash
validate quick                                          # Pre-commit (~2min)
validate standard                                       # Pre-merge (~4min)
validate full                                           # Pre-release (~6min)
validate real                                           # Real-data verification (~2min)
validate module --module X [--json]                     # Single module
validate pre-live --play X                              # Deployment gate
validate exchange                                       # Exchange integration (~30s)
```

Available modules: `core`, `risk`, `audits`, `operators`, `structures`, `complexity`,
`indicators`, `patterns`, `parity`, `sim`, `metrics`, `determinism`, `coverage`, `lint`,
`timestamps`, `real-accumulation`, `real-markup`, `real-distribution`, `real-markdown`

### debug — Diagnostic tools

```bash
debug math-parity --play X --start D --end D [--json]   # Indicator math audit
debug snapshot-plumbing --play X --start D --end D       # Snapshot field check
debug determinism --run-a A --run-b B [--json]           # Compare run hashes
debug metrics [--json]                                    # Financial calc audit
```

### account — Account information (needs API)

```bash
account balance [--json]                                 # Account balance
account exposure [--json]                                # Total exposure
account info [--json]                                    # Account config
account history [--days N] [--symbol X] [--json]         # Order history
account pnl [--days N] [--symbol X] [--json]             # Closed P&L
account transactions [--days N] [--json]                  # Transaction log
account collateral [--currency X] [--json]                # Collateral info
```

### position — Position management (needs API)

```bash
position list [--json]                                   # List open positions
position close SYMBOL                                    # Close a position
position detail --symbol X [--json]                      # Detailed position info
position set-tp --symbol X --price P [--json]            # Set take profit
position set-sl --symbol X --price P [--json]            # Set stop loss
position set-tpsl --symbol X [--tp P] [--sl P] [--json] # Set both TP and SL
position trailing --symbol X --distance D [--json]       # Trailing stop
position partial-close --symbol X --percent N [--json]   # Partial close
position margin --symbol X --mode cross|isolated [--json] # Switch margin mode
position risk-limit --symbol X --id N [--json]           # Set risk limit
```

### order — Order management (needs API)

```bash
order buy --symbol X --amount N --type market [--json]   # Place buy order
order sell --symbol X --amount N --type limit --price P   # Place sell order
order list [--symbol X] [--json]                          # List open orders
order amend --symbol X --order-id ID [--qty N] [--price P] # Amend order
order cancel --symbol X --order-id ID [--json]            # Cancel order
order cancel-all [--symbol X] [--json]                    # Cancel all orders
order leverage --symbol X --leverage N [--json]           # Set leverage
order batch --file orders.json [--json]                   # Batch orders
```

Order types: `market`, `limit`, `stop`, `stop-limit`
Time-in-force: `GTC`, `IOC`, `FOK`, `PostOnly`

### data — Historical data management (DuckDB)

```bash
data sync --symbols BTCUSDT,ETHUSDT [--period 30d] [--json]  # Sync data
data info [--json]                                             # Database stats
data symbols [--json]                                          # List cached symbols
data status --symbol X [--json]                                # Symbol status
data summary [--json]                                          # Symbol summary
data query --symbol X [--tf 1m] [--period 7d] [--json]        # Query OHLCV
data heal [--symbol X] [--json]                                # Check/repair integrity
data vacuum [--json]                                           # Vacuum database
data delete --symbol X --confirm [--json]                      # Delete symbol data
```

### market — Live market data (needs API)

```bash
market price --symbol X [--json]                         # Current price
market ohlcv --symbol X [--tf 15] [--limit 100] [--json] # OHLCV candles
market funding --symbol X [--json]                       # Funding rate
market oi --symbol X [--json]                            # Open interest
market orderbook --symbol X [--depth 25] [--json]        # Orderbook
market instruments [--symbol X] [--json]                  # Instrument info
```

### health — System diagnostics

```bash
health check [--symbol BTCUSDT] [--json]                 # Exchange health check
health connection [--json]                                # API connectivity
health rate-limit [--json]                                # Rate limit status
health ws [--json]                                        # WebSocket status
health environment [--json]                               # API environment config
```

### panic — Emergency (needs API)

```bash
panic --confirm                                          # Cancel all orders, close all positions
```

## Adding a New Subcommand

```python
# 1. Define args in src/cli/argparser.py (_setup_domain_subcommands)
# 2. Create handler in src/cli/subcommands/domain.py
def handle_domain_action(args) -> int:
    from src.tools.domain_tools import action_tool
    result = action_tool(param=args.required_arg)
    if getattr(args, "json_output", False):
        return _json_result(result)
    return _print_result(result)

# 3. Create tool in src/tools/domain_tools.py (returns ToolResult)
# 4. Export handler in src/cli/subcommands/__init__.py
# 5. Import + dispatch in trade_cli.py main()
```

**5 files to touch, all mechanical.** Handler is a thin parsing/formatting layer — business logic lives in the tool function.

## ToolResult Envelope

All tool functions return:

```python
@dataclass
class ToolResult:
    success: bool          # True if operation succeeded
    message: str           # "OK: ..." if success
    error: str             # Error details if not success
    data: dict | None      # Structured output (varies by tool)
```

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `trade_cli.py` | 337 | Entry point: argparse + if-elif dispatch |
| `src/cli/argparser.py` | 652 | Argument definitions for 11 groups |
| `src/cli/subcommands/` | 2,978 | 63 handler functions across 8 files |
| `src/cli/utils.py` | 6 | `console = Console()` singleton |
| `src/cli/validate.py` | 1,864 | Validation suite engine |
| `src/cli/dashboard/` | ~2,500 | Rich TUI for live play monitoring |
| `src/tools/` | — | Business logic (ToolResult contract) |

## Common Mistakes

- Put business logic in handler -> Put in tool function
- Throw exceptions from tools -> Return `ToolResult(success=False, error=msg)`
- Add per-bar logging without gating -> Gate on `is_verbose_enabled()`
- Use `datetime.now()` -> Use `utc_now()` from datetime_utils
- Use `logging.getLogger()` -> Use `get_module_logger()` from utils.logger
