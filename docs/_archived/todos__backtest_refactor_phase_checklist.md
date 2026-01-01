# TODO Phases — RuntimeSnapshot + MTF Caching + Mark Unification

Phase checklists for the strict refactor implementation.
A phase is "done" only when ALL items are checked and acceptance criteria pass.

---

## Phase 0 — Prep / Cutover

### Module Layout

- [x] Create `src/backtest/runtime/__init__.py`
- [x] Create `src/backtest/runtime/types.py` (Bar, FeatureSnapshot, ExchangeState, RuntimeSnapshot)
- [x] Create `src/backtest/runtime/timeframe.py` (tf_duration, helpers)
- [x] Create `src/backtest/runtime/windowing.py` (LoadWindow computation)
- [x] Create `src/backtest/runtime/data_health.py` (DataHealthCheck)
- [x] Create `src/backtest/runtime/snapshot_builder.py` (SnapshotBuilder)
- [x] Create `src/backtest/runtime/cache.py` (TimeframeCache)
- [x] Create `src/backtest/artifacts/__init__.py`
- [x] Create `src/backtest/artifacts/manifest_writer.py`
- [x] Create `src/backtest/artifacts/eventlog_writer.py`
- [x] Create `src/backtest/artifacts/equity_writer.py`
- [x] Create tracking files (PHASE_NOTES.md, TODO_PHASES.md)

### Validation

- [x] Compile/import check passes
- [x] No forbidden imports (artifacts → core)
- [x] TF_MINUTES import works correctly
- [x] Test: `test_phase0_module_structure.py` passes (20 tests)

### Test Tiers + Integration Gates (Smoke-first)

- **Tier 1 (Unit/Smoke, default)**: synthetic bars/in-memory frames/mocked tool calls; fast + deterministic; required for each phase.
- **Tier 2 (Integration Smoke, opt-in/local)**: real LIVE DuckDB tables (`ohlcv_live`, `funding_rates_live`) via env/flag; validates tool-layer preflight + data access.

Integration checkpoints:
- **Integration Gate 1**: after Phase -1 Tier 1 passes, **before starting Phase 1** → run Phase -1 preflight on real DuckDB (small window).
- **Integration Gate 2**: after Phase 4, **before Phase 5 sign-off** → run tiny end-to-end replay determinism on real DuckDB (artifacts + hash). If symbol is new or incomplete, run full_from_launch bootstrap first (tools), then run end-to-end replay determinism tests. Must produce artifacts (run_manifest.json, events.jsonl) and verify replay hash consistency.

---

## Phase -1 — Preflight Data Window + Health Check + Heal Loop

### Context Window (Allowed Files)

- `src/backtest/runtime/windowing.py` ✅
- `src/backtest/runtime/data_health.py` ✅
- `src/tools/backtest_tools.py` ✅
- Allowed calls (no edits): ToolRegistry execution of existing data tools:
  - `get_symbol_timeframe_ranges_tool()`
  - `sync_range_tool()`
  - `fill_gaps_tool()`
  - `heal_data_tool(fix_issues=True, fill_gaps_after=True)`
  - `sync_to_now_and_fill_gaps_tool()`
- Disallowed: implementing any SQL-based "repair" logic inside backtest code (repairs must be via tools).

### Implementation

- [x] Wire DataHealthCheck in backtest_tools.py preflight (read-only validation)
- [x] Preflight uses ToolRegistry: ranges → sync_range(if needed) → fill_gaps → heal_data → recheck (bounded attempts)
  - Uses `fill_gaps_tool()`, `sync_range_tool()`, `sync_funding_tool()` from `data_tools.py`
- [x] **Data Tool Mode: FULL_FROM_LAUNCH bootstrap for new symbols**
  - Implemented `sync_full_from_launch_tool()` in `src/tools/data_tools.py`
  - Resolves `start_ts` automatically from Bybit instrument `launchTime` (category-aware) and `end_ts=now`
  - Works across project tf sets: L=[1m,5m,15m], M=[1h,4h], H=[1D]
  - **Syncs all required data types**: OHLCV (all timeframes), funding rates, and open interest from launchTime → now
  - Preserves existing explicit [start,end] range mode (additive, not replacement)
  - Includes safety cap option: `max_history_years` to prevent accidental massive pulls (default: 5 years)
  - Includes "dry-run/estimate" mode via `dry_run=True` parameter
  - **Chunking requirement**: Implemented `_sync_range_chunked()` helper that chunks by 90-day windows
- [x] Update Phase -1 preflight plan logic (tool-only rule must remain intact):
  - Preflight now detects when symbol has no data coverage and auto-bootstraps via `sync_full_from_launch_tool()`
  - ToolRegistry sequence: `check_existing → if missing: sync_full_from_launch → fill_gaps → heal_data → recheck` (bounded attempts)
  - Added `auto_bootstrap=True` parameter to `backtest_preflight_check_tool()`
  - Reiterate: "Disallowed: SQL repair logic inside backtest code; repairs and ingestion only via tools."
- [x] **Extremes/Bounds metadata artifact requirement**:
  - Added `data_extremes_{env}` table to DuckDB schema in `historical_data_store.py`
  - After `full_from_launch + heal` completes, tool writes/updates per (symbol, tf) for OHLCV, and per symbol for funding/OI:
    - OHLCV: `earliest_ts`, `latest_ts`, `row_count`, `gap_count_after_heal`, `source`, `resolved_launch_time`
    - Funding: `earliest_ts`, `latest_ts`, `record_count`, `gap_count_after_heal`, `source`
    - Open Interest: `earliest_ts`, `latest_ts`, `record_count`, `gap_count_after_heal`, `source`
  - Added `update_extremes()` and `get_extremes()` methods to HistoricalDataStore
  - Added `get_data_extremes_tool()` for querying extremes metadata
  - Plan note: simulation window builder and warmup logic can reference these extremes via `store.get_extremes(symbol)`
- [x] Add chunking helper if querying windows >365d via data.query tools (optional) - **IMPLEMENTED as `_sync_range_chunked()` in data_tools.py**
- [x] Add opt-in real DuckDB "integration smoke" runner (Phase -1 preflight only; small window)
  - Created `tests/test_integration_duckdb_preflight_gate.py` (7 tests, opt-in via `BACKTEST_INTEGRATION_TEST=1`)
- [x] Add integration test that calls actual preflight tool with healing enabled (end-to-end heal loop verification)
  - Added `TestIntegrationPreflightHealLoop` class with 2 tests
  - Fixed funding coverage check to use 8-hour tolerance (funding interval)
- [x] Hard-fail after MAX_HEAL_ATTEMPTS (3)
- [x] Block engine/exchange creation until preflight passes

### Acceptance Criteria

- [x] DataHealthCheck correctly reports coverage/gaps
- [x] Repairs (if needed) are performed ONLY via existing data tools (ToolRegistry), before any sim starts
- [x] Hard-fail after MAX_HEAL_ATTEMPTS
- [x] Test: `test_backtest_preflight_data_health_gate.py` passes (14 tests)
- [x] Integration Gate 1: opt-in integration smoke passes on real LIVE DuckDB (7 tests)
- [x] **FULL_FROM_LAUNCH bootstrap acceptance criteria**:
  - Running `sync_full_from_launch_tool(symbol="SOLUSDT")` populates DuckDB from `launchTime → now` for **all data types** (OHLCV all timeframes, funding rates, open interest), then fills gaps and heals
  - Subsequent runs are idempotent (DuckDB INSERT OR REPLACE; pagination makes monotonic progress; stops safely)
  - Preflight on a new symbol auto-bootstraps via tools (no engine start before coverage is valid) - via `auto_bootstrap=True`
  - Extremes metadata is produced and persisted to `data_extremes_{env}` table, reflects actual DB coverage per tf (and per data type: OHLCV, funding, OI)
  - [x] Integration Gate 2 passes on real LIVE DuckDB with artifacts + replay hash stability (verified)

---

## Phase 1 — Introduce ts_open/ts_close Everywhere

### Context Window (Allowed Files)

- `src/backtest/runtime/types.py` (canonical Bar finalized) ✅
- `src/backtest/runtime/timeframe.py` (tf_duration only) ✅
- `src/backtest/sim/adapters/ohlcv_adapter.py` ✅
- `src/backtest/engine.py` (ts_close step time wiring)
- `src/backtest/sim/exchange.py`
- `src/backtest/sim/execution/execution_model.py`
- `src/backtest/sim/pricing/intrabar_path.py`
- `src/backtest/sim/pricing/price_model.py`
- `src/backtest/sim/types.py` (deprecated Bar, keep sim-only types)

### Implementation

- [x] Update ohlcv_adapter to produce canonical runtime.types.Bar
  - Added `adapt_ohlcv_row_canonical()` and `adapt_ohlcv_dataframe_canonical()`
  - Added `build_bar_close_ts_map()` for data-driven close detection
  - Legacy functions remain for backward compatibility
- [x] Create bar_compat.py for legacy/canonical Bar compatibility
  - Added `get_bar_ts_open()`, `get_bar_ts_close()`, `AnyBar` type alias
- [x] Update execution_model to use Bar.ts_open for fill timestamps
  - Entry fills use `get_bar_ts_open(bar)` for timestamp
  - Exit fills use `get_bar_ts_open(bar)` for timestamp
- [x] Update intrabar_path to use canonical Bar fields
  - Path generation uses `get_bar_ts_open(bar)` for timing
  - Canonical-only (`AnyBar = CanonicalBar`)
- [x] Update price_model to import canonical Bar
  - Uses canonical-only `AnyBar` alias
  - Uses `get_bar_timestamp()` for PriceSnapshot
- [x] Update engine to use ts_close as step time
  - Engine now creates canonical Bar with ts_open/ts_close
  - Equity curve timestamps use ts_close (step time)
  - Signal submission uses ts_close (decision made at bar close)
- [x] Update SimulatedExchange.process_bar to consume canonical Bar
  - Uses `get_bar_ts_open()` for fill timestamps
  - Uses `get_bar_timestamp()` for step time / MTM updates
  - Canonical-only (`AnyBar = CanonicalBar`)
- [x] Remove Bar from sim/types.py (after full migration) - **COMPLETED**
  - ✅ All tests updated to use canonical `Bar` with `ts_open`/`ts_close`
  - ✅ `sim/types.py` now re-exports `Bar` from `runtime.types`
  - ✅ `bar_compat.py` simplified to canonical-only (`AnyBar = CanonicalBar`)
  - ✅ `ohlcv_adapter.py` functions now alias to canonical versions
  - ✅ All sim modules use canonical `Bar` type hints

### Acceptance Criteria

- [x] No code assumes DB timestamp == close (test: test_phase1_determinism.py)
- [x] ts_open/ts_close explicit everywhere (test: test_phase1_ts_open_ts_close.py)
- [x] Deterministic replay check passes (same hash across two runs)

---

## Phase 2 — Define RuntimeSnapshot Contract + Single Builder ✅

### Context Window (Allowed Files)

- `src/backtest/runtime/types.py` (finalize RuntimeSnapshot) ✅
- `src/backtest/runtime/snapshot_builder.py` ✅
- `src/backtest/engine.py` (snapshot construction) ✅
- `src/strategies/*` adapters ✅

### Implementation

- [x] Finalize RuntimeSnapshot contract in types.py
  - All required fields: ts_close, symbol, ltf_tf, mark_price, mark_price_source, bar_ltf, exchange_state, features_htf/mtf/ltf, tf_mapping
- [x] Engine uses SnapshotBuilder to construct snapshots
  - Added `_snapshot_builder` and `_tf_mapping` to engine
  - `_build_snapshot()` now returns RuntimeSnapshot via SnapshotBuilder.build_with_defaults()
  - Added `build_exchange_state_from_exchange()` helper
- [x] Strategy interface accepts RuntimeSnapshot only
  - Updated `BaseStrategy.generate_signal()` to accept `RuntimeSnapshot` only (MarketSnapshot removed)
  - Updated `ema_rsi_atr_strategy` to extract features from RuntimeSnapshot.features_ltf.features
  - Updated `StrategyFunction` type alias in registry to use RuntimeSnapshot only
  - Removed `AnySnapshot` Union type - RuntimeSnapshot is the only supported snapshot type
- [x] No MarketSnapshot usage in engine loop
  - Engine.run() now passes RuntimeSnapshot to strategy
  - Removed `_build_legacy_snapshot()` method (no longer needed)
  - Removed MarketSnapshot from `__init__.py` exports
  - Updated `SimulatedRiskManager` to use RuntimeSnapshot only

### Acceptance Criteria

- [x] Strategy input is RuntimeSnapshot only (test: test_phase2_runtime_snapshot_contract.py)
- [x] Snapshot building centralized in SnapshotBuilder (13 tests pass)

---

## Phase 3 — Implement TF Close Detection + Caching (MTF/HTF) ✅

### Context Window (Allowed Files)

- `src/backtest/runtime/cache.py` ✅
- `src/backtest/indicators.py` ✅
- `src/backtest/engine.py` (multi-TF loading, close-ts maps, readiness gate) ✅

### Implementation

- [x] Build close_ts maps when loading data
- [x] Implement data-driven close detection (no modulo)
- [x] Update TimeframeCache with close-ts sets
- [x] Precompute indicators per TF DataFrame (Option A)
- [x] Implement readiness gate (block trading until HTF/MTF ready)

### Acceptance Criteria

- [x] Between closes, cached snapshots don't change
- [x] At close timestamps, caches update exactly once
- [x] Coincident closes update deterministically (HTF then MTF)
- [x] Trading disabled until HTF/MTF caches ready

---

## Phase 4 — Mark Price Proxy Unification ✅

### Context Window (Allowed Files)

- `src/backtest/sim/exchange.py` (compute mark once, return in StepResult) ✅
- `src/backtest/sim/types.py` (StepResult type) ✅
- `src/backtest/runtime/snapshot_builder.py` (consume exchange mark) ✅
- `src/backtest/engine.py` (use StepResult.mark_price) ✅

### Implementation

- [x] SimulatedExchange computes mark_price exactly once per step
  - `process_bar()` now returns StepResult with mark_price from PriceModel
  - Mark price computed once: `mark_price = prices.mark_price`
- [x] StepResult includes ts_close, mark_price, mark_price_source
  - Added ts_close, mark_price, mark_price_source fields to StepResult
  - to_dict() includes all new fields
- [x] SnapshotBuilder consumes exchange-returned mark (no PriceModel call)
  - Engine passes step_result.mark_price to _build_snapshot()
  - SnapshotBuilder receives mark_price as parameter, never computes it
- [x] All MTM/liquidation/funding uses same mark_price
  - Ledger.update_for_mark_price() receives mark_price from process_bar
  - Single source of truth throughout step

### Acceptance Criteria

- [x] RuntimeSnapshot.mark_price == exchange mark price
- [x] SnapshotBuilder never calls PriceModel
- [x] 18 tests pass in test_backtest_mark_price_unification.py

---

## Phase 5 — Look-Ahead Bias Proof Tests

### Tests to Create

- [x] `test_backtest_mtf_cache_carry_forward.py` (covered in test_phase3_mtf_cache.py - TestCacheCarryForward)
- [x] `test_backtest_mtf_close_boundary_refresh.py` (covered in test_phase3_mtf_cache.py - TestTimeframeCacheCloseDetection)
- [x] `test_backtest_coincident_close_ordering.py` (covered in test_phase3_mtf_cache.py - TestCoincidentCloseOrdering)
- [x] `test_backtest_mark_price_unification.py` (18 tests, Phase 4)
- [x] `test_backtest_no_lookahead_mtf_htf.py` (created, 8 test classes)
- [x] `test_backtest_funding_window_semantics.py` (created, 6 test classes)
- [x] `test_backtest_preflight_data_health_gate.py` (14 tests, Phase -1)
- [x] `test_integration_duckdb_preflight_gate.py` (7 tests, opt-in; real DuckDB; Phase -1)
- [x] `test_integration_end_to_end_replay.py` (created, opt-in; real DuckDB; end-to-end determinism)
  - Supports: "If symbol is new or incomplete, run full_from_launch bootstrap first (tools)"
  - Tests artifact production and replay hash consistency
- [x] `test_exchange_indicator_separation.py` (regression, exists)

---

## Definition of Done

- [x] Phase -1 preflight gate enforced before any simulation
- [x] No run starts with unresolved gaps
- [x] Each run outputs run_manifest.json and events.jsonl (via backtest_tools.py)
- [x] Explicit ts_open/ts_close across runtime/sim/engine
- [x] RuntimeSnapshot is the only strategy input
- [x] HTF/MTF updates are data-driven via close-ts maps
- [x] Exchange-returned mark_price is snapshot source of truth (Phase 4)
- [x] Readiness gate prevents trading until caches ready
- [x] Integration Gate 1 completed (real DuckDB preflight; before Phase 1)
- [x] Integration Gate 2 test created (test_integration_end_to_end_replay.py)
  - [x] Full_from_launch bootstrap implemented and tested
  - [x] Replay hash determinism tests created
  - [x] Run with real LIVE DuckDB to verify (BACKTEST_INTEGRATION_TEST=1) - **PASSED (18 passed, 1 skipped)**
- [x] All Phase 5 tests created
  - [x] test_backtest_no_lookahead_mtf_htf.py
  - [x] test_backtest_funding_window_semantics.py
  - [x] test_integration_end_to_end_replay.py
  - [x] Artifact writers integrated into backtest_tools.py (run_manifest.json, events.jsonl)

---

## Post-Phase Cleanup (Technical Debt)

### Legacy Bar Removal

**Status**: ✅ COMPLETED

**Completed Tasks**:
- [x] Update tests to use `CanonicalBar` instead of `LegacyBar`
  - `test_phase1_determinism.py` - updated
  - `test_phase1_ts_open_ts_close.py` - updated
  - `test_simulated_exchange_accounting.py` - updated to use `Bar` with `ts_open`/`ts_close`
  - `test_stop_semantics.py` - updated to use `Bar` with `ts_open`/`ts_close`
  - `test_exchange_indicator_separation.py` - updated to use `Bar` with `ts_open`/`ts_close`
- [x] Remove `LegacyBar` from `sim/types.py` - now re-exports canonical `Bar` from `runtime.types`
- [x] Update deprecated functions in `ohlcv_adapter.py`:
  - `adapt_ohlcv_row()` - now alias to `adapt_ohlcv_row_canonical()`
  - `adapt_ohlcv_dataframe()` - now alias to `adapt_ohlcv_dataframe_canonical()`
- [x] Simplify `bar_compat.py`:
  - `AnyBar` now equals `CanonicalBar` only
  - `get_bar_ts_open()`, `get_bar_ts_close()` accept `CanonicalBar` only
  - `is_canonical_bar()` removed (always true)
- [x] Update sim modules to use `CanonicalBar` directly:
  - `price_model.py` - uses `Bar` (which is canonical)
  - `execution_model.py` - uses `Bar` type hints
  - `intrabar_path.py` - uses `Bar` type hints
  - `exchange.py` - uses `Bar` type hints
- [x] Update `src/backtest/types.py`:
  - `Candle` is now an alias to canonical `Bar`
  - Tests updated to use `make_bar()` helper with `ts_open`/`ts_close`

**Impact**: Code complexity reduced, technical debt removed, unified type system
