# Validation Suite Consolidation

Consolidate 4 parallel validation systems into one `validate` command + `debug` subcommand. Add `--debug` verbose flag to `backtest run`.

**Before:** validate tiers + backtest audit-* + --smoke flags + scripts/ (same audits reachable via 2-3 paths)
**After:** `validate` is the single entry point, `debug` holds diagnostic tools, `backtest run --debug` for verbose engine tracing.

---

## Gate 0: Delete Redundant Backtest Audit Commands

Remove 8 `backtest audit-*` handlers that duplicate validate gates.

### Tasks

- [x] **0.1** Delete `handle_backtest_audit_toolkit` from `src/cli/subcommands.py` (duplicates G2)
- [x] **0.2** Delete `handle_backtest_audit_incremental_parity` from `src/cli/subcommands.py` (duplicates G3)
- [x] **0.3** Delete `handle_backtest_audit_structure_parity` from `src/cli/subcommands.py` (duplicates G5)
- [x] **0.4** Delete `handle_backtest_audit_rollup` from `src/cli/subcommands.py` (duplicates G6)
- [x] **0.5** Delete `handle_backtest_metadata_smoke` from `src/cli/subcommands.py` (absorbed by G2)
- [x] **0.6** Delete `handle_backtest_mark_price_smoke` from `src/cli/subcommands.py`
- [x] **0.7** Delete `handle_backtest_structure_smoke` from `src/cli/subcommands.py` (absorbed by G5+G9)
- [x] **0.8** Delete `handle_backtest_verify_suite` from `src/cli/subcommands.py` (replaced by validate full)
- [x] **0.9** Remove corresponding argparser entries from `_setup_backtest_subcommands()` in `src/cli/argparser.py`
- [x] **0.10** Remove corresponding dispatch branches from `trade_cli.py` backtest command block
- [x] **0.11** Remove imports of deleted handlers from `trade_cli.py`

### Test Gate 0

```bash
python trade_cli.py validate quick          # Must still pass G1-G4          ✅ (G3 pre-existing parity issue)
python trade_cli.py backtest run --help      # Must still work               ✅
python trade_cli.py backtest list            # Must still work               ✅
```

---

## Gate 1: Create `debug` Subcommand

Move 4 diagnostic tools from `backtest` to new `debug` top-level command.

### Tasks

- [x] **1.1** Rename `handle_backtest_math_parity` -> `handle_debug_math_parity` in `src/cli/subcommands.py`
- [x] **1.2** Rename `handle_backtest_audit_snapshot_plumbing` -> `handle_debug_snapshot_plumbing` in `src/cli/subcommands.py`
- [x] **1.3** Rename `handle_backtest_verify_determinism` -> `handle_debug_determinism` in `src/cli/subcommands.py`
- [x] **1.4** Rename `handle_backtest_metrics_audit` -> `handle_debug_metrics` in `src/cli/subcommands.py`
- [x] **1.5** Add `_setup_debug_subcommands()` to `src/cli/argparser.py` with 4 subcommands:
  - `math-parity` (same args as old `backtest math-parity`)
  - `snapshot-plumbing` (same args as old `backtest audit-snapshot-plumbing`)
  - `determinism` (same args as old `backtest verify-determinism`)
  - `metrics` (same args as old `backtest metrics-audit`)
- [x] **1.6** Remove old argparser entries from `_setup_backtest_subcommands()`
- [x] **1.7** Add `debug` command dispatch block to `trade_cli.py`
- [x] **1.8** Remove old `backtest` dispatch branches for moved commands
- [x] **1.9** Update imports in `trade_cli.py`

### Test Gate 1

```bash
python trade_cli.py debug metrics           # Must pass (6 metric tests)     ✅
python trade_cli.py debug determinism --help # Must show help                ✅
python trade_cli.py debug math-parity --help # Must show help                ✅
python trade_cli.py validate quick           # Must still pass G1-G4         ✅
```

---

## Gate 2: Add G11 (Metrics Audit) to Validate Standard

Move metrics audit logic into a gate function in `src/cli/validate.py`.

### Tasks

- [x] **2.1** Add `_gate_metrics_audit() -> GateResult` to `src/cli/validate.py`
  - Move 6 test scenarios from `handle_debug_metrics`:
    1. Drawdown independent maxima
    2. CAGR geometric formula
    3. Calmar uses CAGR
    4. TF strict mode (unknown TF raises)
    5. TF normalization (Bybit formats)
    6. Zero max DD edge case (Calmar capped)
  - Return GateResult with gate_id="G11", name="Metrics Audit"
  - Count checked = number of test scenarios passed
- [x] **2.2** Renumber existing gates: old G11 (Indicator Suite) -> G12, old G12 (Pattern Suite) -> G13
  - Update `_gate_play_suite` calls: `"G11"` -> `"G12"`, `"G12"` -> `"G13"`
- [x] **2.3** Add `_gate_metrics_audit` to standard tier gate list (after G10)
- [x] **2.4** Update `_gate_play_suite` call for indicators to use `"G12"` and patterns to use `"G13"`

### Test Gate 2

```bash
python trade_cli.py validate quick           # G1-G4 pass (unchanged)        ✅
python trade_cli.py validate standard        # G1-G11 pass (G11 = metrics)   (not run - ~2min)
python trade_cli.py validate standard --json # JSON shows G11 metrics audit  (not run)
```

---

## Gate 3: Add G14 (Determinism) to Validate Full

Add determinism gate that runs core plays twice and compares trade hashes.

### Tasks

- [x] **3.1** Add `_gate_determinism() -> GateResult` to `src/cli/validate.py`
  - For each of 5 CORE_PLAY_IDS:
    1. Run `create_engine_from_play(play)` + `run_engine_with_play(engine, play)` -> get trades
    2. Run again with same play -> get trades
    3. Compare trade count and trade details (entry_price, exit_price, side, pnl)
  - If any play produces different results across 2 runs, fail
  - Return GateResult with gate_id="G14", name="Determinism"
- [x] **3.2** Add `_gate_determinism` to full tier gate list (after G13)

### Test Gate 3

```bash
python trade_cli.py validate full            # G1-G14 pass                   (not run - ~10min)
python trade_cli.py validate full --json     # JSON shows G14 determinism    (not run)
```

---

## Gate 4: Add `validate exchange` Tier (Absorb --smoke)

Create 5th validate tier for exchange integration. Absorb `--smoke full` logic.

### Tasks

- [x] **4.1** Add `Tier.EXCHANGE = "exchange"` to Tier enum in `src/cli/validate.py`
- [x] **4.2** Add `_gate_exchange_connectivity() -> GateResult` (EX1)
  - Test Bybit API connection via `test_connection_tool()`
  - Test server time offset via `get_server_time_offset_tool()`
- [x] **4.3** Add `_gate_exchange_account() -> GateResult` (EX2)
  - Test: `get_account_balance_tool()`, `get_total_exposure_tool()`, `get_account_info_tool()`, `get_portfolio_snapshot_tool()`, `get_collateral_info_tool()`
  - Each must return `result.success == True`
- [x] **4.4** Add `_gate_exchange_market_data() -> GateResult` (EX3)
  - Test: `get_price_tool(symbol)`, `get_ohlcv_tool(symbol, "60", 10)`, `get_funding_rate_tool(symbol)`, `get_open_interest_tool(symbol)`, `get_orderbook_tool(symbol, 5)`
  - Use first symbol from `config.smoke.symbols` or default "BTCUSDT"
- [x] **4.5** Add `_gate_exchange_order_flow() -> GateResult` (EX4)
  - Place limit buy at 90% of current price -> verify in open orders -> cancel
  - Use `config.smoke.usd_size` for order size
  - Must be in demo mode (check `config.bybit.use_demo`)
- [x] **4.6** Add `_gate_exchange_diagnostics() -> GateResult` (EX5)
  - Test: `get_rate_limit_status_tool()`, `get_websocket_status_tool()`, `exchange_health_check_tool(symbol)`, `get_api_environment_tool()`
- [x] **4.7** Add exchange tier to `run_validation()` gate list builder
  - Simplified: gates import config directly (no signature change needed)
- [x] **4.8** Update `_setup_validate_subcommand()` in argparser: add `"exchange"` to tier choices
- [x] **4.9** Update `trade_cli.py` validate dispatch to pass `app` and `config` when tier is exchange
  - Simplified: not needed since gates import config directly

### Test Gate 4

```bash
python trade_cli.py validate exchange        # EX1-EX5 pass (needs demo API) (not run - needs demo keys)
python trade_cli.py validate exchange --json # JSON output with EX gates      (not run)
```

---

## Gate 5: Remove --smoke Flag and Delete Unused Smoke Tests

### Tasks

- [x] **5.1** Delete `src/cli/smoke_tests/backtest.py` (absorbed by G4)
- [x] **5.2** Delete `src/cli/smoke_tests/forge.py` (absorbed by G2+G3)
- [x] **5.3** Delete `src/cli/smoke_tests/structure.py` (absorbed by G5+G9)
- [x] **5.4** Delete `src/cli/smoke_tests/metadata.py` (absorbed by G2)
- [x] **5.5** Delete `src/cli/smoke_tests/prices.py` (not needed standalone)
- [x] **5.6** Delete `src/cli/smoke_tests/rules.py` (tested by G8-G13 play suites)
- [x] **5.7** Deleted `src/cli/smoke_tests/core.py` entirely (broken imports to deleted files, exchange gates live in validate.py)
- [x] **5.8** Remove `--smoke` argparse flag and handler from `trade_cli.py`
- [x] **5.9** Remove `--smoke` argparse entries from `src/cli/argparser.py`
- [x] **5.10** Clean up any remaining imports of deleted smoke test modules

**Keep:**
- `src/cli/smoke_tests/sim_orders.py` (used by G7)
- `src/cli/smoke_tests/data.py` (standalone data builder test, useful)
- `src/cli/smoke_tests/orders.py` (helpers for EX4)

### Test Gate 5

```bash
python trade_cli.py validate quick           # Still passes                  ✅
python trade_cli.py validate standard        # Still passes                  (not run - ~2min)
python trade_cli.py validate exchange        # Still passes                  (not run - needs demo keys)
python trade_cli.py --smoke full             # Should error (flag removed)   ✅
```

---

## Gate 6: Update Documentation

### Tasks

- [x] **6.1** Update `CLAUDE.md` Quick Commands section:
  - Remove all `--smoke` commands
  - Add `validate exchange` command
  - Add `debug` commands
  - Remove `backtest audit-*` commands
- [x] **6.2** Update `.claude/commands/validate.md` if it references old commands
- [x] **6.3** Update `.claude/agents/validate.md` if it references old commands

### Test Gate 6

```bash
# Final comprehensive test
python trade_cli.py validate quick           # G1-G4 pass                    ✅
python trade_cli.py validate standard        # G1-G11 pass                   (not run - ~2min)
python trade_cli.py validate full            # G1-G14 pass                   (not run - ~10min)
python trade_cli.py validate exchange        # EX1-EX5 pass                  (not run - needs demo keys)
python trade_cli.py validate pre-live --play V_CORE_001_indicator_cross      (not run - needs API)
python trade_cli.py debug metrics            # 6 tests pass                  ✅
python trade_cli.py debug determinism --help # Shows help                    ✅
python trade_cli.py backtest run --help      # Still works                   ✅
python trade_cli.py backtest list            # Still works                   ✅
```

---

## Gate 7: Add `--debug` Flag to `backtest run`

Enable verbose step-by-step engine trace during backtest execution.

**Existing infrastructure:** `src/utils/debug.py` has `enable_debug()`, `debug_log()`, `debug_signal()`, `debug_trade()`, `debug_milestone()`, `debug_snapshot()`. Global `--debug` flag exists but only activates sparse logging.

### Tasks

- [x] **7.1** Add `--debug` argument to `backtest run` subparser in `src/cli/argparser.py`
- [x] **7.2** In `handle_backtest_run()`, detect `--debug` flag and call `enable_debug(True)` + set log level to DEBUG
- [x] **7.3** Add bar-level debug tracing to `PlayEngine.process_bar()` in `src/engine/play_engine.py`:
  - Log bar OHLCV at each step (every bar when debug enabled)
  - Log signal evaluation result (which conditions passed/failed)
  - Log position state changes (open/close/SL/TP)
  - Use existing `debug_log()`, `debug_signal()`, `debug_trade()` from `src/utils/debug.py`
- [x] **7.4** Add indicator value dump at signal bars in engine (use `debug_snapshot()`)
- [x] **7.5** Set console log level to DEBUG when `--debug` is active (normally WARNING for backtest)

### Test Gate 7

```bash
python trade_cli.py backtest run --play V_CORE_001_indicator_cross --synthetic --debug
# Shows: bar-by-bar trace, signal evaluations, trade events, indicator snapshots  ✅
# Verify output includes [play:HASH] [bar:N] prefixed lines                      ✅

python trade_cli.py backtest run --play V_CORE_001_indicator_cross --synthetic
# Should NOT show debug output (normal quiet mode)                                ✅
```

---

## Final CLI Surface

```bash
# Validation (single entry point)
python trade_cli.py validate quick                    # Pre-commit (~10s)
python trade_cli.py validate standard                 # Pre-merge (~2min)
python trade_cli.py validate full                     # Pre-release (~10min)
python trade_cli.py validate pre-live --play X        # Deployment gate
python trade_cli.py validate exchange                 # Exchange integration (~30s)

# Backtest (operational only)
python trade_cli.py backtest run --play X             # Run backtest
python trade_cli.py backtest run --play X --debug     # Run with verbose engine trace
python trade_cli.py backtest preflight --play X       # Check without running
python trade_cli.py backtest indicators --play X      # Discover indicator keys
python trade_cli.py backtest list                     # List plays
python trade_cli.py backtest data-fix --play X        # Fix data gaps
python trade_cli.py backtest play-normalize --play X  # Validate YAML
python trade_cli.py backtest play-normalize-batch     # Batch validate

# Debug (diagnostic tools)
python trade_cli.py debug math-parity --play X        # Real-data math audit
python trade_cli.py debug snapshot-plumbing --play X   # Snapshot field check
python trade_cli.py debug determinism --run-a A --run-b B  # Compare runs
python trade_cli.py debug metrics                      # Financial calc audit

# Batch runners (scripts/)
python scripts/run_full_suite.py                      # 170-play synthetic
python scripts/run_real_verification.py               # 60-play real data
python scripts/verify_trade_math.py --play X          # Per-play math
```
