# CLI-First Backtest Data & Indicators Phases

> **Objective**: Refactor backtest workflow so debugging and validation never depends on ad-hoc `test_*.py` files. Instead, use a CLI wrapper command with `--smoke` mode as the golden path.

## Hard Rules (Non-negotiable)

- No new standalone `test_*.py` scripts for backtest validation
- Indicators must remain **explicit-only** (IdeaCard → FeatureSpec → indicator_vendor)
- Backtest data queries must validate: **env**, **symbol uppercase**, **timeframe string**, **coverage including warmup**, and handle **UTC-naive DuckDB timestamps**

---

## Phase A — Data Correctness (must pass before indicator debugging)

### A1. CLI Preflight Diagnostics
- [x] Add CLI "preflight" for backtest runs that prints:
  - env (`live|demo`)
  - resolved DB file path
  - resolved OHLCV table name
  - symbol normalization (uppercase)
  - tf string (canonical: 1m/5m/15m/1h/4h/1d)
  - requested start/end vs effective start/end (effective includes warmup span)

### A2. Timeframe & Symbol Validation
- [x] Enforce timeframe string validity (`1h`, not `60`)
- [x] Enforce uppercase symbol matching
- [x] Reject Bybit API intervals (`60/240/D`) with fix-it message

### A3. Timezone Handling
- [x] If user passes tz-aware bounds, strip tz to match DuckDB UTC-naive storage
- [x] Log the normalization explicitly

### A4. Data Fix CLI Shortcut
- [x] Add CLI shortcut to call existing data tools to fix gaps/coverage
- [x] No new DB "custom tools" - dispatch to existing: `sync_range_tool`, `fill_gaps_tool`, `heal_data_tool`, `sync_full_from_launch_tool`

### Gate A Acceptance
A smoke run can fail with "no data found" but must always explain:
- Which env/table/range caused it
- How to fix via existing data tools

---

## Phase B — Indicator System (explicit-only, strict, debuggable)

### B1. IdeaCard-Only Indicator Path
- [x] Confirm IdeaCard → FeatureSpec → indicator_vendor pipeline is the only computation path for CLI runs
- [x] Use `load_idea_card()` + `validate_idea_card_full()` 
- [x] Use `adapt_idea_card_to_system_config()` to feed engine with `feature_specs_by_role`

### B2. Indicator Key Printing
- [x] Add/standardize logging for `snapshot.available_indicators` (+ htf/mtf variants)
- [x] Print on run start AND on strict failure
- [x] Show exec/htf/mtf keys separately

### B3. Strict Failure Improvements
- [x] Missing key: print available keys and exact mismatch guidance
- [x] NaN: distinguish "warmup too small" vs "insufficient DB coverage before window_start"
- [x] Print actionable "what to do next" for each failure type

### B4. Multi-Output Naming Validation
- [x] Validate multi-output naming rules (MACD/BBANDS/STOCH/STOCHRSI)
- [x] Ensure CLI prints the expanded keys used (e.g., `macd_macd`, `macd_signal`)
- [x] Fail loud if vendor returns unexpected keys

### Gate B Acceptance
If a strategy requests an indicator incorrectly, CLI output must let you fix it without opening code:
- Shows declared keys + available keys
- Shows which role (exec vs htf vs mtf) the key belongs to

---

## Phase C — CLI Wrapper + Smoke as the Only Debug Path

### C1. Argparse Subcommands
- [x] Implement `trade_cli.py backtest run --idea-card ...` subcommand
- [x] Implement `trade_cli.py backtest preflight --idea-card ...` subcommand
- [x] Implement `trade_cli.py backtest data-fix ...` subcommand
- [x] Support options: `--env`, `--symbol`, `--tf-exec`, `--start`, `--end`
- [x] Support options: `--smoke`, `--strict`, `--artifacts-dir`, `--no-artifacts`

### C2. Smoke Mode Implementation
- [x] `--smoke` runs fast but does NOT skip pipeline stages
- [x] Uses data load → indicator compute → first-non-NaN gate → simulation loop
- [x] If `--start/--end` not provided, anchor to DB latest timestamp (printed explicitly)

### C3. Strict Mode
- [x] `--strict` default on for `--smoke`
- [x] Uses `indicator_strict()` access patterns
- [x] Fails loud with actionable diagnostics

### C4. Test Refactoring
- [x] Update `src/cli/smoke_tests.py:run_backtest_smoke` to call new IdeaCard-based wrapper
- [x] Refactor backtest/data/indicator tests to call shared wrapper function
- [x] Tests may assert on `ToolResult.data` fields but must not re-implement pipeline logic

### Gate C Acceptance
One canonical command reproduces 100% of smoke/debug issues and is the only supported workflow.

---

## Acceptance Criteria (Done Definition)

- [x] Data issues are diagnosable from CLI output: env/table/window/warmup/tz rules are visible
- [x] Indicator issues are diagnosable from CLI output: available keys printed, strict failures explain naming vs warmup vs coverage
- [x] No backtest validation depends on custom `test_*.py` scripts; the CLI wrapper + smoke is the single golden path

---

## Files to Create/Modify

### New Files
- `src/tools/backtest_cli_wrapper.py` — Shared wrapper for IdeaCard backtest runs

### Modified Files
- `trade_cli.py` — Add argparse subcommands for `backtest run/preflight/data-fix`
- `src/cli/smoke_tests.py` — Refactor `run_backtest_smoke` to use wrapper
- `src/backtest/runtime/snapshot_view.py` — Improve strict error messages
- `src/backtest/features/feature_frame_builder.py` — Add key validation
- `tests/test_*.py` — Refactor to call shared wrapper

---

## Known Issues to Fix

- `src/backtest/engine.py` references `max_lookback` in `PreparedFrame` but it's not defined in the code path. Must derive from declared FeatureSpecs.

