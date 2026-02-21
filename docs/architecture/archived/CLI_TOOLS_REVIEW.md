# CLI and Tools Domain Review

**Scope**: `src/cli/`, `src/tools/`, `trade_cli.py`
**Reviewer**: claude-sonnet-4-6
**Date**: 2026-02-18
**Files reviewed**: 11 (see table below)
**Format**: `[CLI-XXX] Severity: HIGH/MED/LOW/INFO`

> **STATUS (2026-02-18):** All findings resolved. 1 HIGH accepted (CLI-008), 1 HIGH fixed (CLI-011), 5 MED fixed, 1 MED not-a-bug, 5 LOW OK/fixed.
> See `FINDINGS_SUMMARY.md` for current status of each finding.

---

## Module Overview

The CLI and tools layer forms the user-facing surface of the TRADE system. It has two major components:

1. **CLI layer** (`src/cli/`, `trade_cli.py`): Interactive menus (TradeCLI), non-interactive subcommand handlers (handle_* functions), validation orchestration (staged gate system), live dashboard (Rich TUI).

2. **Tools layer** (`src/tools/`): ~50 tool functions that wrap exchange and data operations. All return `ToolResult`. All live/trading tools validate trading environment before any exchange call.

The architecture is clean. Exit codes propagate correctly through all non-interactive paths. The `ToolResult` pattern is applied consistently. The pre-live validation gate auto-runs before live mode and cannot be skipped via CLI.

---

## Files Reviewed

| File | Lines | Purpose |
|------|-------|---------|
| `trade_cli.py` | ~872 | TradeCLI class, interactive menu, subprocess dispatch, os._exit(0) |
| `src/cli/validate.py` | ~1731 | 18 gate functions, staged execution, per-play/per-gate timeouts |
| `src/cli/subcommands.py` | ~1728 | All handle_* command handlers, exit code return contracts |
| `src/cli/live_dashboard.py` | ~1388 | Rich Live TUI, DashboardLogHandler, OrderTracker, data poller |
| `src/cli/utils.py` | ~928 | run_tool_action, run_long_action, safe_menu_action, shared console |
| `src/tools/shared.py` | ~235 | ToolResult, _get_exchange_manager singleton, trading env validation |
| `src/tools/backtest_play_tools.py` | ~1465 | backtest_run_play_tool golden path, artifact validation |
| `src/tools/order_tools.py` | ~1070 | Live order tools, batch tools, env validation at every entry |
| `src/tools/position_tools.py` | ~1166 | Position query/close tools, panic close |
| `src/tools/account_tools.py` | ~636 | Balance, exposure, portfolio snapshot tools |
| `src/tools/backtest_audit_tools.py` | ~485 | Determinism, metrics, snapshot plumbing audit wrappers |

---

## Architecture Diagram

```
trade_cli.py (TradeCLI)
    |
    |-- interactive mode:  main_menu() --> sub-menus --> validate_quick() / live handlers
    |-- non-interactive:   sys.exit(subcommands.handle_*())
    |-- terminal cleanup:  os._exit(0)  [interactive end only, after shutdown()]
    |
src/cli/subcommands.py
    |
    |-- handle_validate      --> src/cli/validate.py (run_validation, sys.exit code)
    |-- handle_backtest_run  --> backtest_run_play_tool (golden path)
    |-- handle_play_run      --> _run_play_backtest / _run_play_live / _run_play_shadow
    |-- handle_account_*     --> src/tools/account_tools.py
    |-- handle_position_*    --> src/tools/position_tools.py
    |-- handle_order_*       --> src/tools/order_tools.py
    |-- handle_panic         --> panic_close_all_tool (--confirm required)
    |-- handle_debug_*       --> src/tools/backtest_audit_tools.py
    |
src/cli/validate.py
    |
    |-- run_validation(Tier)
    |       |-- _run_staged_gates (ThreadPoolExecutor per stage, gate_timeout=300s)
    |       |       |-- G1: YAML parse  G2: Registry  G3: Incremental parity
    |       |       |-- G4: Core plays  G4b: Risk stops  G5: Structure parity
    |       |       |-- G6: Rollup      G7: Sim smoke   G8-G13: Suites (ProcessPoolExecutor)
    |       |       |-- G14: Determinism  G15: Coverage
    |       |-- _run_gates (sequential, single-gate stages)
    |       |-- checkpoint: .validate_report.json after each gate
    |
src/tools/backtest_play_tools.py
    |-- backtest_run_play_tool()
    |       |-- preflight gate (data coverage check)
    |       |-- RunnerConfig(skip_preflight=True, skip_artifact_validation=True)
    |       |-- run_backtest_with_gates() -> PlayBacktestResult
    |       |-- validate_artifacts_after=True (hard fail on artifact corruption)
    |
src/tools/order_tools.py + position_tools.py
    |-- Entry: if error := validate_trading_env_or_error(trading_env): return error
    |-- partial_close_position_tool: reduce_only=True explicitly passed
    |-- close_position_tool: delegates to exchange.close_position() implicitly
    |-- batch_*_tool: success = success_count > 0  [see CLI-027]
    |
src/cli/live_dashboard.py
    |-- DashboardLogHandler: deque(maxlen=N) + threading.Lock()  [bounded]
    |-- OrderTracker: deque(maxlen=N)                            [bounded]
    |-- _data_poller: daemon thread, except Exception: pass      [see CLI-033]
```

---

## File-by-File Findings

### trade_cli.py

#### [CLI-001] Severity: INFO -- os._exit(0) is Correct and Intentional

**Lines**: 865-867

```python
# pybit WebSocket threads are non-daemon and may keep Python alive
# after main() returns. Force exit to return to shell promptly.
os._exit(0)
```

`os._exit(0)` appears only at the end of the interactive mode path, after `cli.shutdown()` runs. Non-interactive subcommand paths hit `sys.exit(handle_*())` before reaching this line. The comment accurately explains the intent. This is correct behavior -- pybit WebSocket threads are non-daemon and would hold the process open without this call.

---

#### [CLI-002] Severity: LOW -- validate_quick() Discards run_validation() Return Code

**Line**: 556

```python
run_validation(tier=Tier.QUICK, fail_fast=True)
# return value discarded -- no PASS/FAIL banner shown to user
```

The interactive `validate_quick()` method ignores `run_validation()`'s return value (0=pass, 1=fail). The gate output prints correctly, but when the menu returns the user sees no summary banner. In the non-interactive path (`handle_validate`), `sys.exit(run_validation(...))` is used correctly.

**Fix**: Store return value and print `[green]PASS[/]` or `[red]FAIL[/]` before `Prompt.ask(...)`.

---

#### [CLI-003] Severity: LOW -- Ghost Branch in _main_menu_connected()

**Lines**: ~498

The `_main_menu_connected()` method contains a branch for a "connected" menu state that is never triggered from `main_menu()`. The interactive menu always calls `main_menu()` which does not distinguish connected vs. disconnected state at the method level. The ghost branch adds dead conditional logic with no reachable path.

**Fix**: Trace all callers of `_main_menu_connected()` and either wire the branch or remove it entirely (ALL FORWARD, NO LEGACY).

---

### src/cli/validate.py

#### [CLI-004] Severity: INFO -- REPORT_FILE is CWD-Relative

**Line**: 61

```python
REPORT_FILE = Path(".validate_report.json")
```

The checkpoint file resolves relative to the process's working directory. When invoked from outside the project root (e.g., a CI runner with a different cwd), the checkpoint file will land in the wrong directory and `--resume` will not find previous results.

**Impact**: Low in practice since all documented invocations use the project root. Consider resolving against `__file__.parent.parent` or a `PROJECT_ROOT` constant.

---

#### [CLI-005] Severity: LOW -- Coverage Gate Uses CWD-Relative Paths

**Lines**: 713-743

```python
ind_dir = Path("plays/validation/indicators")
str_dir = Path("plays/validation/structures")
```

Both paths in `_gate_coverage_check()` are CWD-relative. If validation is invoked from outside the project root, the directories will not be found, the `exists()` check returns False, and the gate will silently pass with no coverage checked (0 missing indicators, 0 missing structures reported as success).

**Fix**: Resolve against a canonical `PLAYS_DIR` constant or `Path(__file__).parent.parent.parent / "plays"`.

---

#### [CLI-006] Severity: MED -- Double-Timeout in _run_staged_gates()

**Lines**: 1379-1381

```python
for future in as_completed(futures, timeout=gate_timeout):
    try:
        result = future.result(timeout=gate_timeout)
```

Both `as_completed(timeout=gate_timeout)` and `future.result(timeout=gate_timeout)` use the same `gate_timeout` value. If `as_completed` yields without triggering the outer timeout (gate completes within `gate_timeout`), `future.result(timeout=gate_timeout)` starts a second independent countdown from zero. In theory a gate could consume up to `2 * gate_timeout` before the process detects it as hung.

In practice this is unlikely to matter because `as_completed` yields only when the future is already done, so `future.result(timeout=...)` returns immediately. But the pattern is misleading. The inner `future.result(timeout=gate_timeout)` catch should be `except Exception` to handle non-timeout errors, not `except FuturesTimeoutError`, since the timeout was already caught by `as_completed`.

**Fix**: Remove `timeout=gate_timeout` from `future.result()` since by the time `as_completed` yields the future, it is already done. Catch `Exception` there instead.

---

#### [CLI-007] Severity: MED -- Coverage Gate Silently Ignores YAML Parse Errors

**Lines**: 724-725 and 742-743

```python
            except Exception:
                pass  # in both ind_dir and str_dir scan loops
```

Both YAML scan loops in `_gate_coverage_check()` swallow all exceptions including `yaml.YAMLError`, `PermissionError`, and `UnicodeDecodeError`. A corrupt play file will silently contribute zero entries to `covered_indicators`, making the gate report a false gap for any indicator that only appears in the corrupt file.

**Fix**: At minimum log the error and append to `failures`: `failures.append(f"Parse error in {play_file}: {e}")`. The gate should not silently degrade.

---

#### [CLI-008] Severity: HIGH -- G4/G4b Run Sequential Plays with No Per-Play Timeout

**Lines**: 462-473 (G4), 495-508 (G4b)

```python
for i, pid in enumerate(CORE_PLAY_IDS, 1):
    console.print(f"       [dim]G4[/] {i}/{total} {pid}...", highlight=False)
    try:
        play = load_play(pid)
        engine = create_engine_from_play(play)
        result = run_engine_with_play(engine, play)  # no timeout
```

Gates G4 (Core Plays) and G4b (Risk Stops) run plays sequentially in the gate thread with no per-play timeout. A single hung play can block the entire gate thread indefinitely. This is inconsistent with G8-G13 which use `ProcessPoolExecutor` with `_collect_futures_with_timeout(play_timeout=PLAY_TIMEOUT_SEC)`.

The gate-level timeout (`GATE_TIMEOUT_SEC=300`) from `_run_staged_gates` does cover G4/G4b when they run in a concurrent stage, but this only works if G4 and G4b run concurrently with other gates in the same stage. A single-play hang in G4 running solo will block the stage for the full `gate_timeout` before the `as_completed` fires.

**Fix**: Submit each play as a `ProcessPoolExecutor` future and use `_collect_futures_with_timeout` with `play_timeout=PLAY_TIMEOUT_SEC`, matching the pattern used by G8-G13.

---

#### [CLI-009] Severity: LOW -- PL3 detail Field Shows play_id Instead of symbol

**Line**: 1157

```python
return GateResult(
    ...
    detail=f"Symbol: {play_id}",  # BUG: should be symbol
    ...
)
```

The `detail` field in `_gate_pre_live_no_conflicts()` says `Symbol: {play_id}` but `play_id` is the play identifier (e.g., `"my_btc_long"`), not the trading symbol (e.g., `"BTCUSDT"`). The `symbol` variable is set at line 1140 (`symbol = play.symbol_universe[0]`) but is not used in `detail`.

**Fix**: Change to `detail=f"Symbol: {symbol}"`.

---

#### [CLI-010] Severity: MED -- PL2 reads wrong key: "available_balance" vs "available"

**Line**: 1111

```python
available = float(result.data.get("available_balance", 0))
```

`get_account_balance_tool()` returns a dict with key `"available"`, not `"available_balance"`. The `.get("available_balance", 0)` always returns `0.0`. Gate PL2 (Account Balance) will always pass even when the account has zero available funds -- the insufficient balance check `available < required` evaluates as `0.0 < required`, which will fail correctly only if `required > 0`. But the reported `available` value in any failure message will always show `0.00` regardless of actual balance.

**Fix**: Change to `result.data.get("available", 0)`.

---

#### [CLI-011] Severity: HIGH -- PL3 Conflict Detection Never Fires

**Line**: 1144

```python
raw_data = result.data
positions: list[dict[str, Any]] = raw_data if isinstance(raw_data, list) else []
```

`list_open_positions_tool()` returns a dict with shape `{"positions": [...], "count": N}`. `isinstance(dict, list)` is always False. `positions` resolves to `[]` on every call. The symbol conflict check in the loop below never executes. Gate PL3 silently passes regardless of open positions.

**Fix**:
```python
raw_data = result.data or {}
positions = raw_data.get("positions", []) if isinstance(raw_data, dict) else []
```

---

### src/cli/subcommands.py

#### [CLI-012] Severity: MED -- handle_play_stop Silently Swallows Position Check Exception

**Line**: 1338

```python
        except Exception:
            pass  # If we can't check positions, proceed with stop
```

If the exchange is unreachable when `play stop` is called, the position check silently fails and the stop proceeds without any user warning. The user has no indication that the position check was skipped.

**Fix**: At minimum log a warning. Per CLAUDE.md live safety principles, fail-closed is preferred for operations that interact with live exchange state.

---

#### [CLI-013] Severity: LOW -- handle_play_logs() Uses split("\n") -- CRLF Risk on Windows

**Line**: ~1487

Log line splitting uses `split("\n")` which will leave `\r` at the end of each line on Windows when reading log files written with CRLF endings. Rich markup that contains trailing `\r` may render incorrectly.

**Fix**: Use `splitlines()` or strip before display.

---

#### [CLI-014] Severity: MED -- _run_play_backtest Does Not Forward CLI Args to Tool

**Lines**: 988-993

```python
result = backtest_run_play_tool(
    play_id=play.id,
    start=start,
    end=end,
    plays_dir=plays_dir,
)
```

`backtest_run_play_tool` accepts `sync`, `smoke`, `validate`, `strict`, and `emit_snapshots` parameters but `_run_play_backtest` does not forward any of them. CLI flags `--no-validate`, `--smoke`, `--strict`, `--emit-snapshots` are ignored when invoked via `play run --mode backtest`. The user expects CLI-specified flags to take effect.

**Fix**: Extract all relevant args from the `args` namespace and pass them explicitly:
```python
result = backtest_run_play_tool(
    play_id=play.id,
    start=start,
    end=end,
    plays_dir=plays_dir,
    sync=getattr(args, "sync", False),
    smoke=getattr(args, "smoke", False),
    validate=getattr(args, "validate", True),
    strict=getattr(args, "strict", False),
    emit_snapshots=getattr(args, "emit_snapshots", False),
)
```

---

#### [CLI-015] Severity: LOW -- play pause/resume Uses File Sentinel with No Engine Polling Confirmation

**Lines**: 1540-1596

`handle_play_pause()` creates a file sentinel at `~/.trade/instances/{instance_id}.pause` and returns immediately with a success message. There is no confirmation that the LiveRunner is actually polling for this file or that it has acknowledged the pause. The user sees "Paused" in the CLI before the engine has actually paused.

**Impact**: Low -- the sentinel mechanism is documented. But it creates a time-of-check/time-of-act gap for the user.

---

#### [CLI-032] Severity: MED -- Key Mismatch: "exposure_usd" vs "total_exposure_usdt"

**Lines**: `account_tools.py:76` (tool) and `subcommands.py:1641` (handler)

The tool returns:
```python
data={"exposure_usd": exposure}  # account_tools.py:76
```

The handler reads:
```python
total = data.get("total_exposure_usdt", "N/A")  # subcommands.py:1641
```

`total_exposure_usdt` is never set by the tool. `handle_account_exposure` always displays `"N/A"` as the exposure value, even when the tool succeeds.

**Fix**: Change handler to `data.get("exposure_usd", "N/A")` or change the tool to use the key `"total_exposure_usdt"` for consistency with other USDT-denominated keys.

---

### src/cli/live_dashboard.py

#### [CLI-016] Severity: LOW -- Brief Log-Loss Window During Handler Swap

During `_install_log_handler()`, there is a brief window between removing the old handler and installing the new `DashboardLogHandler` where log records emitted by concurrent threads are lost. This is a standard logging handler swap issue.

**Impact**: Very low -- the window is microseconds and validation runs are not concurrent with dashboard mode. Document as known limitation.

---

#### [CLI-017] Severity: INFO -- DashboardLogHandler is Correctly Bounded

```python
DashboardLogHandler: deque(maxlen=max_lines)  # bounded, no leak
OrderTracker: deque(maxlen=max_events)        # bounded, no leak
```

Both log and order event buffers use `deque` with `maxlen`, preventing unbounded memory growth during long-running dashboard sessions. Both daemon threads are correctly flagged as daemon so they do not block process exit. No memory leak risk.

---

#### [CLI-033] Severity: MED -- Data Poller Swallows All Exceptions Silently

**Live dashboard data polling thread**

Background `_data_poller` thread has bare `except Exception: pass` on both refresh calls. A silent exception (lost WebSocket connection, stale state) leaves the dashboard frozen with stale data and no indication to the user.

**Fix**: Log the exception at WARNING level via the dashboard log handler. Set a `_refresh_error_count` attribute that the dashboard rendering can display as a "DATA STALE" banner after N consecutive failures.

---

### src/tools/shared.py

#### [CLI-020] Severity: MED -- _get_exchange_manager() Singleton is Not Thread-Safe

**Lines**: 60-71

```python
def _get_exchange_manager() -> "ExchangeManager":
    if not hasattr(_get_exchange_manager, "_instance"):
        _get_exchange_manager._instance = ExchangeManager()
    return _get_exchange_manager._instance
```

The `hasattr` + `setattr` check-then-act is not atomic. Under concurrent tool calls (e.g., from an agent calling multiple tools simultaneously), two threads could both evaluate `hasattr` as False and each construct a separate `ExchangeManager` instance. The second write wins, but the first instance is orphaned -- it may hold open WebSocket connections or file handles.

**Fix**: Use `threading.Lock` or `threading.local` for safe singleton initialization:
```python
_exchange_manager_lock = threading.Lock()

def _get_exchange_manager():
    if not hasattr(_get_exchange_manager, "_instance"):
        with _exchange_manager_lock:
            if not hasattr(_get_exchange_manager, "_instance"):
                _get_exchange_manager._instance = ExchangeManager()
    return _get_exchange_manager._instance
```

---

#### [CLI-021] Severity: INFO -- ToolResult.to_dict() Delegates to asdict()

```python
def to_dict(self) -> dict[str, Any]:
    return asdict(self)
```

`dataclasses.asdict()` recursively converts dataclass fields but passes through non-dataclass types as-is. Any non-JSON-serializable value in `data` (e.g., `datetime`, `Decimal`) will cause `json.dumps()` downstream to raise `TypeError`. This is an existing limitation, not a new bug. Callers using `json.dumps(result.to_dict(), default=str)` are safe.

---

### src/tools/backtest_play_tools.py

#### [CLI-022] Severity: MED -- RunnerConfig Skips Preflight and Artifact Validation

**Lines**: 725-726

```python
runner_config = RunnerConfig(
    ...
    skip_preflight=True,   # CLI wrapper already validated
    skip_artifact_validation=True,  # Skip because preflight is skipped
    ...
)
```

Both `skip_preflight=True` and `skip_artifact_validation=True` are set unconditionally in `backtest_run_play_tool`. The comment says "CLI wrapper already validated", but the tool is also called directly by agents and by the validate gate suite. In those paths the CLI wrapper has not run preflight.

The implicit contract here (preflight already happened upstream) is not enforced by signature or assertion. An agent calling `backtest_run_play_tool` directly will silently skip the stricter runner-level warmup checks.

**Impact**: Medium. The tool does run its own lighter preflight before `RunnerConfig`. But the runner-level preflight (which checks high_tf/med_tf warmup separately) is always skipped.

---

#### [CLI-023] Severity: LOW -- Synthetic Mode Uses print() Instead of Logger

**Lines**: 591-614

```python
print(f"[Synthetic] Generating {bars} bars...")
print(f"[Synthetic] Generated {total_bars} 1m bars")
```

Synthetic data generation prints diagnostic output with `print()`. In non-interactive agent or CI contexts these go to stdout without timestamps or log level. All other diagnostic output in this file uses `logger`.

**Fix**: Replace `print()` calls with `logger.debug(...)`.

---

#### [CLI-025] Severity: LOW -- Hardcoded Stale Search Paths

**Lines**: 1256-1261

Play discovery uses hardcoded path segments `"_validation"` and `"_stress_test"` which are legacy path names (underscore prefix). The canonical paths are `"validation"` and `"stress_test"` (no underscore). This may cause play lookup to fail for validation plays stored in the canonical path structure.

**Fix**: Update to match the canonical `plays/validation/` and `plays/stress_test/` directory structure used elsewhere.

---

### src/tools/order_tools.py

#### [CLI-026] Severity: HIGH -- No market_close_tool with Enforced reduce_only=True

There is no dedicated `market_close_tool` function. Agents or CLI handlers that want to close a position via a market order must either use `close_position_tool` (which delegates `reduce_only` to the exchange layer implicitly) or `market_sell_tool` / `market_buy_tool`, neither of which has a `reduce_only` parameter.

This means an agent can open a new position when intending to close, if it calls `market_sell_tool` on a symbol with no existing long position.

Per CLAUDE.md: "All close/partial-close market orders must pass `reduce_only=True` to the exchange."

**Fix**: Add a `market_close_tool(symbol, side, qty, trading_env)` function that always passes `reduce_only=True`. Document that `market_buy_tool` and `market_sell_tool` are for opening positions only.

---

#### [CLI-027] Severity: MED -- Batch Tools Return success=True on Partial Failure

**Lines**: 928, 1003, 1056

```python
return ToolResult(
    success=success_count > 0,  # True even if 9/10 orders failed
    ...
)
```

All three batch tools (`batch_market_orders_tool`, `batch_limit_orders_tool`, `batch_cancel_orders_tool`) use `success = success_count > 0`. An agent or orchestrator that checks `result.success` to gate downstream logic will proceed after a 9/10 partial failure. The failed count is in `data["failed_count"]` but callers often don't inspect `data` on success.

**Fix**: Change to `success=failed_count == 0` -- all orders must succeed for `success=True`. The partial count is still available in `data` for informational use.

---

#### [CLI-028] Severity: LOW -- get_open_orders_tool() Filters Client-Side Only

**Lines**: 676-679

```python
if symbol:
    orders = [o for o in orders if o.get("symbol") == symbol]
```

Symbol filtering is done client-side after fetching all orders. For accounts with many open orders on multiple symbols, this is wasteful and may miss orders if the REST response is paginated and `symbol` is not passed to the API call.

**Fix**: Pass `symbol` to the exchange method so the API filters server-side, reducing response size and eliminating pagination risk.

---

### src/tools/position_tools.py

#### [CLI-029] Severity: LOW -- close_position_tool Does Not Enforce reduce_only at Tool Layer

**Lines**: 734-737

```python
result = exchange.close_position(
    symbol=symbol,
    cancel_conditional_orders=cancel_conditional_orders,
)
```

`reduce_only=True` is not explicitly passed at the tool layer. Enforcement depends entirely on the `ExchangeManager.close_position()` implementation. This is in contrast to `partial_close_position_tool` which explicitly passes `reduce_only=True`.

**Impact**: Low -- `ExchangeManager` currently enforces `reduce_only=True` for closes. But the tool-layer contract should be explicit per CLAUDE.md live safety principles.

**Fix**: Add `reduce_only=True` as an explicit kwarg to the `exchange.close_position()` call, matching the pattern in `partial_close_position_tool`.

---

#### [CLI-030] Severity: MED -- set_trailing_stop_by_percent_tool Does Not Forward trading_env

**Line**: ~672

`set_trailing_stop_by_percent_tool` accepts `trading_env` but does not forward it to the inner `set_trailing_stop_tool` call. The inner call uses no environment validation. The walrus guard on `trading_env` runs correctly at the outer layer, but the nested call operates without environment assertion.

**Fix**: Forward `trading_env` to the inner `set_trailing_stop_tool` call.

---

#### [CLI-031] Severity: LOW -- _position_to_dict() Uses Stale current_price for size_usdt

**Line**: ~53

`_position_to_dict()` computes `size_usdt` using `position.current_price` which may be stale if the WebSocket has not updated since the last tick. For positions with large size, the computed `size_usdt` can be significantly off from actual market value.

**Impact**: Display/reporting only. Does not affect order execution.

---

### src/tools/account_tools.py

#### [CLI-033a] Severity: MED -- get_portfolio_snapshot_tool Returns False Failure for Empty Accounts

**Lines**: 143-147

```python
if snapshot.total_equity <= 0 and snapshot.total_position_count == 0:
    return ToolResult(
        success=False,
        error="Global risk data not available - WebSocket may not be connected",
    )
```

A new or empty account with zero equity and zero positions will always return `success=False` with a misleading WebSocket error. This is a valid state for a funded-but-inactive account.

**Fix**: Check WebSocket connection status explicitly rather than inferring from zero equity. Return `success=True` with an appropriate message for genuinely empty portfolios.

---

## Cross-Module Dependencies

```
trade_cli.py
    --> src/cli/subcommands.py   (all handle_* functions)
    --> src/cli/validate.py      (run_validation, Tier)
    --> src/cli/live_dashboard.py (run_dashboard)
    --> src/cli/utils.py         (console, run_tool_action, BACK)

src/cli/subcommands.py
    --> src/tools/backtest_play_tools.py (backtest_run_play_tool)
    --> src/tools/order_tools.py         (market_buy_tool, batch_*, panic)
    --> src/tools/position_tools.py      (list_open_positions_tool, close_position_tool)
    --> src/tools/account_tools.py       (get_account_balance_tool, get_total_exposure_tool)
    --> src/tools/backtest_audit_tools.py (debug commands)
    --> src/tools/shared.py              (ToolResult)

src/tools/order_tools.py
    --> src/tools/shared.py          (validate_trading_env_or_error, ToolResult, _get_exchange_manager)
    --> src/tools/order_tools_common.py (validate_order_params, execute_simple_order)

src/tools/position_tools.py
    --> src/tools/shared.py          (ToolResult, _get_exchange_manager_for_env)
    --> src/core/exchange_manager.py (close_position, close_all_positions)

src/tools/account_tools.py
    --> src/tools/shared.py          (ToolResult, validate_trading_env_or_error)
    --> src/risk/                    (get_global_risk_view)

src/cli/validate.py
    --> src/tools/ (get_account_balance_tool, list_open_positions_tool)
    --> src/backtest/ (load_play, create_engine_from_play, run_engine_with_play)
    --> src/forge/ (audit modules)
```

**Notable coupling**: `_run_play_backtest` in `subcommands.py` passes `skip_preflight=True` implicitly via `backtest_run_play_tool` defaults. This is an implicit contract ("CLI wrapper already validated") not enforced by type or signature.

---

## Positive Findings

### Exit Code Propagation is Correct
All non-interactive subcommand paths use `sys.exit(handle_*())` and all `handle_*` functions return `int` (0 or 1). Exit code flows correctly from tool failure through handle function to process exit.

### Timeout Enforcement is Correct for Play Suites (G8-G13)
`PLAY_TIMEOUT_SEC=120` and `GATE_TIMEOUT_SEC=300` are enforced at two levels for play suite gates:
- Per-play: `future.result(timeout=play_timeout)` in `_collect_futures_with_timeout`
- Per-gate: `as_completed(timeout=gate_timeout)` in `_run_staged_gates`

### No Memory Leaks in Live Dashboard
Both `DashboardLogHandler` and `OrderTracker` use bounded `deque` with `maxlen`. Both background threads are daemon-flagged. No unbounded growth risk.

### Pre-Live Validation Gate Auto-Runs and Cannot Be Skipped
`handle_play_run` for `mode == "live"` auto-runs `run_validation(Tier.PRE_LIVE)` before any live engine start. No `--skip-validation` flag exists. Strong safety guarantee (noting BUG-level issues CLI-010/CLI-011 above which weaken individual gates).

### validate_trading_env_or_error() Walrus Guard Applied Consistently
All ~50 order, position, and account tools use the walrus guard pattern `if error := validate_trading_env_or_error(trading_env): return error` before any exchange call. No tool bypasses this.

### partial_close_position_tool Correctly Enforces reduce_only=True
The `reduce_only=True` is explicitly passed at the tool layer for partial closes, not delegated. This is the correct pattern (contrast with `close_position_tool` -- see CLI-029).

### panic_close_all_tool Requires --confirm at CLI Layer
`handle_panic` requires `--confirm` flag before executing `panic_close_all_tool`. Checked before any exchange call.

### ProcessPoolExecutor Windows Spawn Compatibility
Play suite gates use module-level `_run_gate_play()` worker function, not lambdas or closures, for Windows `spawn` compatibility. Correctly avoids `pickle` failures under Windows.

### backtest_run_play_tool Is a Hard-Fail Gate
`validate_artifacts_after=True` (default) causes the tool to return `success=False` on any artifact corruption after a run. Liquidation/drawdown hard-fail (GAP-3/4/5 fixed) propagates correctly through `run_result.success`.

---

## Summary Table

| ID | Severity | File | Line(s) | Description |
|----|----------|------|---------|-------------|
| CLI-008 | HIGH | validate.py | 462-508 | G4/G4b sequential plays with no per-play timeout |
| CLI-011 | HIGH | validate.py | 1144 | PL3 conflict detection never fires (dict vs list) |
| CLI-026 | HIGH | order_tools.py | -- | No market_close_tool with enforced reduce_only=True |
| CLI-006 | MED | validate.py | 1379-1381 | Double-timeout in _run_staged_gates |
| CLI-007 | MED | validate.py | 724-743 | Coverage gate silently swallows YAML parse errors |
| CLI-010 | MED | validate.py | 1111 | PL2 reads wrong key "available_balance" (always 0) |
| CLI-012 | MED | subcommands.py | 1338 | handle_play_stop silently swallows position check exception |
| CLI-014 | MED | subcommands.py | 988-993 | _run_play_backtest drops CLI args (sync, smoke, validate, strict) |
| CLI-020 | MED | shared.py | 69-70 | _get_exchange_manager singleton not thread-safe |
| CLI-022 | MED | backtest_play_tools.py | 725-726 | RunnerConfig always skips preflight and artifact validation |
| CLI-027 | MED | order_tools.py | 928, 1003, 1056 | Batch tools return success=True on partial failure |
| CLI-030 | MED | position_tools.py | ~672 | set_trailing_stop_by_percent_tool does not forward trading_env |
| CLI-032 | MED | account_tools.py/subcommands.py | 76 / 1641 | Key mismatch: "exposure_usd" vs "total_exposure_usdt" |
| CLI-033 | MED | live_dashboard.py | -- | Data poller swallows all exceptions silently |
| CLI-033a | MED | account_tools.py | 143-147 | get_portfolio_snapshot_tool false failure for empty accounts |
| CLI-002 | LOW | trade_cli.py | 556 | validate_quick() discards run_validation() return code |
| CLI-003 | LOW | trade_cli.py | ~498 | Ghost branch in _main_menu_connected() |
| CLI-005 | LOW | validate.py | 713-743 | Coverage gate uses CWD-relative paths |
| CLI-009 | LOW | validate.py | 1157 | PL3 detail field shows play_id instead of symbol |
| CLI-013 | LOW | subcommands.py | ~1487 | handle_play_logs split("\n") CRLF risk on Windows |
| CLI-015 | LOW | subcommands.py | 1540-1596 | play pause/resume sentinel with no engine acknowledgement |
| CLI-023 | LOW | backtest_play_tools.py | 591-614 | Synthetic mode uses print() instead of logger |
| CLI-025 | LOW | backtest_play_tools.py | 1256-1261 | Hardcoded legacy search paths "_validation", "_stress_test" |
| CLI-028 | LOW | order_tools.py | 676-679 | get_open_orders_tool client-side symbol filter only |
| CLI-029 | LOW | position_tools.py | 734-737 | close_position_tool no explicit reduce_only at tool layer |
| CLI-031 | LOW | position_tools.py | ~53 | _position_to_dict uses stale current_price for size_usdt |
| CLI-016 | LOW | live_dashboard.py | -- | Brief log-loss window during handler swap |
| CLI-004 | INFO | validate.py | 61 | REPORT_FILE is CWD-relative |
| CLI-001 | INFO | trade_cli.py | 867 | os._exit(0) is intentional and correctly placed |
| CLI-017 | INFO | live_dashboard.py | -- | DashboardLogHandler correctly bounded (positive) |
| CLI-021 | INFO | shared.py | 51-53 | ToolResult.to_dict() asdict() passes through non-JSON types |

---

## Priority Action List

1. **Fix CLI-011** (`validate.py:1144`): Fix PL3 to extract `positions` list from dict response -- gate is completely neutered.
2. **Fix CLI-010** (`validate.py:1111`): Change `available_balance` key to `available` in PL2.
3. **Fix CLI-026** (`order_tools.py`): Add `market_close_tool` with enforced `reduce_only=True`.
4. **Fix CLI-008** (`validate.py:462-508`): Give G4/G4b per-play timeouts via `ProcessPoolExecutor`.
5. **Fix CLI-032** (`subcommands.py:1641`): Change handler to read `exposure_usd` key.
6. **Fix CLI-027** (`order_tools.py:928, 1003, 1056`): Change batch tool success to `failed_count == 0`.
7. **Fix CLI-007** (`validate.py:724-743`): Log YAML parse errors in coverage gate instead of silently passing.

---

## Validation Reminder

```bash
python trade_cli.py validate quick
python trade_cli.py validate standard
```
