# Architecture Review: Backtest Runtime Module

**Review Date**: 2026-01-02
**Reviewer**: Claude Opus 4.5
**Scope**: `src/backtest/runtime/`

---

## Executive Summary

The runtime module implements the core data access layer for the backtest engine hot loop. It provides:

1. **View-Based Snapshots** (`RuntimeSnapshotView`) - O(1) access to precomputed arrays
2. **Multi-TF Feed Stores** (`FeedStore`, `MultiTFFeedStore`) - Immutable array storage
3. **MTF Caching** (`TimeframeCache`) - Data-driven close detection and forward-fill
4. **State Tracking** (Stage 7) - Record-only signal/action/gate state machines
5. **Preflight Validation** - Data coverage and quality checks before backtest

**Overall Assessment**: The module is well-designed with strong performance guarantees. The separation between materialized types (`RuntimeSnapshot`) and view-based types (`RuntimeSnapshotView`) creates some redundancy but provides a clear migration path. State tracking is cleanly isolated with pure transition functions.

---

## File-by-File Analysis

### 1. `snapshot_view.py` (RuntimeSnapshotView)

**Purpose**: Strategy-facing view over cached feed data. Zero per-bar allocation for OHLCV/features.

**Key Functions**:
- `__init__()` - O(1) setup; stores references to feeds, builds resolver dispatch table
- `get_feature(indicator_key, tf_role, offset)` - Unified feature lookup API
- `get(path)` - Canonical path resolver for DSL (`indicator.*`, `price.*`, `structure.*`)
- `_resolve_*_path()` - Namespace-specific path resolution
- OHLCV property accessors (`open`, `high`, `low`, `close`, `volume`)
- Previous bar accessors (`prev_close()`, `bars_exec_low()`)
- HTF/MTF accessors (`htf_indicator()`, `mtf_indicator()`)
- Rollup accessors (`rollup_min_1m`, `rollup_max_1m`, etc.)

**Dependencies**:
- `FeedStore`, `MultiTFFeedStore` from `feed_store.py`
- `ExchangeState`, `HistoryConfig` from `types.py`
- `numpy` for array operations

**O(1) Guarantees**:
- Uses `__slots__` to prevent dict overhead
- Path tokenization cached at module level (`_PATH_CACHE`)
- All data access via array indexing
- Resolver dispatch table built once in `__init__`

**Issues Found**:
1. **Missing import**: Line 925 uses `math.isnan()` but `math` is not imported
2. **Redundant `TFContext`**: Defined both here (lines 46-131) and conceptually overlaps with `RuntimeSnapshot.features_*`
3. **Staleness check incomplete**: `htf_is_stale` and `mtf_is_stale` only compare timestamps; no validation that indices are in bounds

**Structural Concerns**:
- `RuntimeSnapshotView` and `RuntimeSnapshot` (from `types.py`) have overlapping responsibilities. The codebase should consolidate on one.
- The `TFContext` class could be extracted to its own file for clarity
- `to_dict()` creates dict allocations in serialization path - should be marked debug-only

---

### 2. `snapshot_builder.py` (SnapshotBuilder)

**Purpose**: Constructs materialized `RuntimeSnapshot` from pre-computed inputs.

**Key Functions**:
- `build()` - Full snapshot construction with validation
- `build_with_defaults()` - Handles warmup with not-ready placeholders
- `build_exchange_state_from_exchange()` - Efficient ExchangeState construction from SimulatedExchange

**Dependencies**:
- `RuntimeSnapshot`, `Bar`, `FeatureSnapshot`, `ExchangeState` from `types.py`

**Issues Found**:
1. **Legacy naming**: Uses `bar_ltf`, `features_ltf` parameters (backward compat) alongside newer `bar_exec`, `features_exec` - confusing
2. **Unused in hot loop**: Docstrings say "SnapshotBuilder is NOT used" (per `snapshot_view.py` comments) - suggests dead code

**Structural Concerns**:
- This file builds `RuntimeSnapshot` but the engine uses `RuntimeSnapshotView` - creates two parallel paths
- Consider deprecating this in favor of direct `RuntimeSnapshotView` construction

---

### 3. `feed_store.py` (FeedStore, MultiTFFeedStore)

**Purpose**: Immutable store of precomputed numpy arrays for one timeframe.

**Key Functions**:
- `from_dataframe()` - Build from DataFrame (explicit indicator columns only)
- `from_dataframe_with_features()` - Build from DataFrame + FeatureArrays
- `get_ts_close_datetime(idx)` - O(1) timestamp lookup
- `get_idx_at_ts_close(ts)` - O(1) reverse lookup via precomputed map
- `get_last_closed_idx_at_or_before(ts)` - O(log n) via binary search
- `get_structure_field()` / `get_zone_field()` - Market structure access
- `has_structure()` / `has_zone()` - Structure existence checks

**Dependencies**:
- `FeatureArrays` from `features/feature_frame_builder.py`
- `IndicatorMetadata` from `indicator_metadata.py`
- `StructureStore` from `market_structure/builder.py`
- `numpy`, `pandas`, `bisect`

**O(1) Guarantees**:
- All OHLCV access via numpy array indexing
- `ts_close_ms_to_idx` precomputed dict for O(1) timestamp lookup
- `_sorted_close_ms` built once in `__post_init__` for O(log n) range queries

**Issues Found**:
1. **Float32/64 inconsistency**: OHLCV always `float64`, indicators use `prefer_float32` flag - could cause precision drift
2. **Lazy import**: `tf_duration` imported inside method (line 388) - minor performance cost on first call
3. **Mutable default warning**: `structures` and `structure_key_map` use `field(default_factory=dict)` - correct but worth noting

**Structural Concerns**:
- `MultiTFFeedStore` is a thin wrapper - could be a simple dict with type hints instead
- Structure storage via `StructureStore` adds complexity; could be unified with indicators

---

### 4. `cache.py` (TimeframeCache)

**Purpose**: Caches FeatureSnapshots for HTF and MTF with data-driven close detection.

**Key Functions**:
- `set_close_ts_maps()` - Populate close timestamp lookup sets
- `is_htf_close()` / `is_mtf_close()` - Check if current bar is a TF close
- `update_htf()` / `update_mtf()` - Update cached snapshots
- `refresh_step()` - Combined HTF+MTF refresh with factory callbacks

**Dependencies**:
- `FeatureSnapshot`, `Bar` from `types.py`

**Issues Found**:
1. **Set membership cost**: `is_htf_close()` is O(1) average but O(n) worst case for hash collisions
2. **No cache invalidation**: Once set, close_ts_maps are never updated - assumes static data

**Structural Concerns**:
- Uses `FeatureSnapshot` (materialized) rather than `TFContext` (view-based) - creates allocation pressure
- Could be simplified to just track indices into FeedStore rather than full snapshots
- `refresh_step()` takes factory callables - inversion of control is good, but adds indirection

---

### 5. `timeframe.py`

**Purpose**: Timeframe duration calculation and validation utilities.

**Key Functions**:
- `tf_duration(tf)` - Get timedelta for timeframe string
- `tf_minutes(tf)` - Get duration in minutes
- `validate_tf_mapping()` - Ensure HTF >= MTF >= LTF hierarchy
- `ceil_to_tf_close(dt, tf)` - Align datetime to TF boundary

**Dependencies**:
- `TF_MINUTES` from `data/historical_data_store.py` (canonical source)

**Issues Found**:
- None significant

**Structural Concerns**:
- Docstring mentions "close detection is data-driven, not modulo-based" - but `ceil_to_tf_close` uses modulo calculation. This is acceptable for alignment vs detection but could confuse readers.

---

### 6. `types.py` (Bar, FeatureSnapshot, ExchangeState, RuntimeSnapshot, HistoryConfig)

**Purpose**: Core runtime types - immutable dataclasses for point-in-time state.

**Key Types**:
- `Bar` (frozen) - OHLCV with explicit ts_open/ts_close
- `FeatureSnapshot` (frozen) - Indicator values at TF close
- `ExchangeState` (frozen) - Margin, position, equity snapshot
- `RuntimeSnapshot` (frozen) - Complete point-in-time state
- `HistoryConfig` (frozen) - Bounded history window configuration

**Dependencies**:
- Standard library only (datetime, typing, dataclasses)

**Issues Found**:
1. **Memory overhead**: `RuntimeSnapshot` stores tuples of `Bar` and `FeatureSnapshot` for history - could be indices instead
2. **Redundant with view**: `RuntimeSnapshot` vs `RuntimeSnapshotView` duplication

**Structural Concerns**:
- `FeatureSnapshot.bar` embeds a full `Bar` - could be reference to avoid duplication
- `RuntimeSnapshot` has many backward-compat aliases (`bar_ltf`, `ltf_tf`) - adds maintenance burden
- `create_not_ready_feature_snapshot()` factory creates Bar dependency - could use None instead

---

### 7. `data_health.py` (DataHealthCheck)

**Purpose**: Validates data coverage and quality before backtest runs.

**Key Functions**:
- `check_coverage()` - Verify data exists for required range
- `detect_gaps()` - Find missing candles within window
- `check_sanity()` - OHLC consistency, no NaN, positive volume
- `run()` - Full health check returning DataHealthReport

**Key Types**:
- `GapRange` - Range of missing data
- `CoverageInfo` - Coverage info per series/TF
- `SanityIssue` - Data quality issue record
- `DataHealthReport` - Complete health report

**Dependencies**:
- `tf_duration` from `timeframe.py`

**Issues Found**:
1. **NaN check pattern**: `val != val` is a clever NaN check but less readable than `math.isnan(val)`
2. **Funding tolerance hardcoded**: 8-hour tolerance for funding is correct but should be a constant

**Structural Concerns**:
- Well-structured with clear separation of concerns
- Report serialization via `to_dict()` is clean

---

### 8. `quote_state.py` (QuoteState)

**Purpose**: Immutable quote state from closed 1m bars - ticker proxy for simulator.

**Key Functions**:
- `QuoteState.__post_init__()` - Validates positive prices, high >= low, valid mark_source
- `quote_to_packet_dict()` - Convert to dict for snapshot injection
- `QUOTE_KEYS` - Standard packet key namespace

**Dependencies**:
- None (standalone dataclass)

**Issues Found**:
- None significant

**Structural Concerns**:
- Clean, focused design
- `mark_source` enum validation is inline; could be a proper Enum type

---

### 9. `rollup_bucket.py` (ExecRollupBucket)

**Purpose**: Accumulates 1m bar data between exec TF closes.

**Key Functions**:
- `accumulate(quote)` - O(1) min/max/count updates
- `freeze()` - O(1) dict construction for packet injection
- `reset()` - O(1) field resets for next interval
- `create_empty_rollup_dict()` - Factory for initial state

**Dependencies**:
- `QuoteState` from `quote_state.py`

**O(1) Guarantees**:
- All operations are field updates or dict construction
- No loops in accumulate/freeze/reset

**Issues Found**:
- None significant

**Structural Concerns**:
- Zone interaction fields are commented out as placeholders - proper for phased development
- `open_price_1m` uses close as proxy on first bar (line 113) - documented but slightly misleading name

---

### 10. `windowing.py` (LoadWindow, DataWindow)

**Purpose**: Compute required data windows for backtest runs including warmup and buffers.

**Key Functions**:
- `compute_warmup_bars()` - Now just returns lookback (delegated to FeatureSpec)
- `compute_warmup_span()` - Total warmup as timedelta
- `compute_safety_buffer_span()` - Extra closes for cache reliability
- `compute_tail_buffer_span()` - Extra bars at end for funding
- `compute_load_window()` - Full window computation
- `compute_data_window()` - Simplified API for Preflight-computed warmup

**Dependencies**:
- `tf_duration`, `tf_minutes` from `timeframe.py`

**Issues Found**:
1. **Two window types**: `LoadWindow` and `DataWindow` have overlapping purposes - confusing
2. **Unused variable**: Line 119 assigns to `config` but never uses it

**Structural Concerns**:
- Could consolidate `LoadWindow` and `DataWindow` into one type
- Default constants (10 HTF safety closes, etc.) are reasonable but not exposed for override

---

### 11. `indicator_metadata.py` (IndicatorMetadata)

**Purpose**: Lightweight provenance tracking for indicator computation.

**Key Functions**:
- `canonicalize_params()` - Deterministic parameter normalization
- `compute_feature_spec_id()` - Stable 12-char hash from type+params+input
- `find_first_valid_idx()` - Find first non-NaN index in array
- `validate_metadata_coverage()` - Check indicator/metadata key parity
- `validate_feature_spec_ids()` - Full consistency validation
- `export_metadata_*()` - JSONL/JSON/CSV export functions

**Key Types**:
- `IndicatorMetadata` (frozen) - Full provenance record
- `MetadataValidationResult` - Validation check results

**Dependencies**:
- `FeedStore` from `feed_store.py` (TYPE_CHECKING only)
- `hashlib`, `json`, `csv`, `numpy`, `pathlib`

**Issues Found**:
1. **Version detection fragile**: `get_pandas_ta_version()` checks both `version` and `__version__` attributes - defensive but indicates unstable API

**Structural Concerns**:
- Well-designed with clear separation
- Export functions are comprehensive (JSONL, JSON, CSV)
- Hash payload explicitly excludes tf/symbol for portability - good decision

---

### 12. `preflight.py` (PreflightReport, run_preflight_gate)

**Purpose**: Data validation gate that MUST pass before backtest runs.

**Key Functions**:
- `parse_tf_to_minutes()` - TF string parsing
- `calculate_warmup_start()` - Compute effective start with warmup
- `validate_tf_data()` - Single (symbol, tf) validation
- `_validate_exec_to_1m_mapping()` - Verify 1m bars exist for exec TF closes
- `_run_auto_sync()` - Auto-fix via data tools (tool discipline enforced)
- `run_preflight_gate()` - Main entry point with warmup computation

**Key Types**:
- `PreflightStatus` (Enum) - PASSED/FAILED/WARNING
- `GapInfo`, `TFPreflightResult`, `PreflightReport` - Validation results
- `ToolCallRecord`, `AutoSyncConfig`, `AutoSyncResult` - Auto-fix tracking

**Dependencies**:
- `pandas`, `numpy`
- `compute_warmup_requirements` from `execution_validation.py`
- Data tools for auto-sync (lazy import)

**Issues Found**:
1. **Long function**: `run_preflight_gate()` is 320+ lines - should be decomposed
2. **Lazy tool import**: `_get_default_tools()` imports at call time - acceptable for circular import avoidance
3. **Datetime timezone handling**: Multiple places normalize to naive - potential for timezone bugs

**Structural Concerns**:
- Very comprehensive but complex
- Good use of dataclasses for result types
- Error classification (`error_code`) is helpful for smoke test assertions
- 1m coverage check is mandatory - enforced correctly

---

## State Tracking Files (Stage 7)

### 13. `state_types.py` (SignalStateValue, ActionStateValue, GateCode, GateResult)

**Purpose**: Core enums and data structures for state tracking.

**Key Types**:
- `SignalStateValue` (IntEnum) - NONE/CANDIDATE/CONFIRMING/CONFIRMED/EXPIRED/CONSUMED
- `ActionStateValue` (IntEnum) - IDLE/ACTIONABLE/SIZING/SUBMITTED/FILLED/REJECTED/CANCELED
- `GateCode` (IntEnum) - G_PASS and failure codes (G_WARMUP_REMAINING, etc.)
- `GateResult` (frozen dataclass) - Immutable gate evaluation result

**Design Notes**:
- IntEnum values explicit for array storage
- `GateResult.pass_()` and `GateResult.fail_()` factory methods
- `GATE_CODE_DESCRIPTIONS` dict for human-readable messages

**Issues Found**:
- None significant

**Structural Concerns**:
- Type aliases at bottom (`SignalState = SignalStateValue`) are confusing - comment says "will be replaced"

---

### 14. `signal_state.py` (SignalState, transition_signal_state)

**Purpose**: Signal lifecycle state machine.

**Key Functions**:
- `transition_signal_state()` - Pure transition function (no side effects)
- `reset_signal_state()` - Factory for fresh NONE state
- `SignalState` dataclass with lifecycle helpers

**State Flow**:
```
NONE -> CANDIDATE -> CONFIRMING -> CONFIRMED -> CONSUMED
                               |-> EXPIRED
```

**Issues Found**:
- None significant

**Structural Concerns**:
- One-bar confirmation (v1) means CANDIDATE is often skipped
- `SIGNAL_TRANSITIONS` dict defines valid transitions - good for validation
- `can_transition_to()` method not used in transition function - could be integrated

---

### 15. `action_state.py` (ActionState, transition_action_state)

**Purpose**: Order/action lifecycle state machine.

**Key Functions**:
- `transition_action_state()` - Pure transition function
- `reset_action_state()` - Factory for fresh IDLE state
- `ActionState` dataclass with lifecycle helpers

**State Flow**:
```
IDLE -> ACTIONABLE -> SIZING -> SUBMITTED -> FILLED/REJECTED/CANCELED
```

**Issues Found**:
- None significant

**Structural Concerns**:
- Mirrors `signal_state.py` structure - consistent design
- `reject_reason` captured on rejection - good for debugging

---

### 16. `gate_state.py` (GateContext, evaluate_gates)

**Purpose**: Gate evaluation for pre-trade conditions.

**Key Functions**:
- `evaluate_gates()` - Evaluate all gates, return first failure
- `evaluate_warmup_gate()` - Warmup-only convenience function
- `evaluate_margin_gate()` - Margin-only convenience function

**Gate Categories**:
1. Warmup (G_WARMUP_REMAINING, G_HISTORY_NOT_READY)
2. Cache (G_CACHE_NOT_READY)
3. Risk (G_RISK_BLOCK, G_MAX_DRAWDOWN, G_INSUFFICIENT_MARGIN)
4. Position (G_POSITION_LIMIT, G_EXPOSURE_LIMIT)
5. Cooldown (G_COOLDOWN_ACTIVE)

**Issues Found**:
1. **History gate logic**: `ctx.history_bars < ctx.warmup_bars` - should this be separate from warmup?

**Structural Concerns**:
- Fail-fast with all failures collected is a good pattern
- `GateContext` is a simple dataclass - could use TypedDict for fewer allocations

---

### 17. `block_state.py` (BlockState, create_block_state)

**Purpose**: Unified per-bar state container combining signal, action, and gate states.

**Key Functions**:
- `create_block_state()` - Factory function
- `reset_block_state()` - Fresh state factory
- `BlockState.summary()` - Human-readable debug string

**Key Properties**:
- `is_actionable` - Signal confirmed + gates passed + action idle
- `is_blocked` - Gates did not pass
- `block_reason` / `block_code` - Why blocked
- `signal_detected/confirmed/consumed` - Signal state queries
- `action_filled/rejected` - Action state queries

**Issues Found**:
- None significant

**Structural Concerns**:
- Clean aggregation of sub-states
- Properties provide convenient query interface

---

### 18. `state_tracker.py` (StateTracker, StateTrackerConfig)

**Purpose**: Engine integration layer for unified state tracking.

**Key Functions**:
- `on_bar_start(bar_idx)` - Reset per-bar accumulators
- `on_signal_evaluated(direction)` - Record raw signal
- `on_warmup_check()`, `on_history_check()`, `on_risk_check()` - Gate inputs
- `on_sizing_computed()`, `on_order_submitted/filled/rejected()` - Action tracking
- `on_bar_end()` - Transition state machines, record BlockState
- `summary_stats()` - Aggregated statistics from block history

**Dependencies**:
- All state modules (signal_state, action_state, gate_state, block_state)
- State type primitives

**Issues Found**:
1. **Block history unbounded**: `block_history: List[BlockState] = []` grows indefinitely - memory concern for long runs
2. **Linear search**: `get_block_at(bar_idx)` is O(n) - should use dict for O(1)

**Structural Concerns**:
- Good separation: config, tracker, and state machines are distinct
- `create_state_tracker()` factory function provides clean initialization
- Record-only mode is clearly documented

---

### 19. `__init__.py`

**Purpose**: Module exports and documentation.

**Issues Found**:
- None significant

**Structural Concerns**:
- Comprehensive `__all__` list
- Good module docstring describing performance contract
- Stage 7 state tracking exports cleanly integrated

---

## Cross-Cutting Concerns

### O(1) Hot-Loop Guarantees

**Met**:
- `RuntimeSnapshotView` - Array access, path cache, `__slots__`
- `FeedStore` - Precomputed arrays, O(1) ts lookup
- `ExecRollupBucket` - Simple field updates
- `TFContext` - Array indexing

**Potential Violations**:
- `TimeframeCache` stores `FeatureSnapshot` objects (allocation)
- `StateTracker.block_history` list append (amortized O(1) but memory)
- `FeedStore.get_last_closed_idx_at_or_before()` is O(log n) - acceptable

### MTF Handling

**Strengths**:
- Data-driven close detection via `close_ts_set` - no modulo arithmetic
- Forward-fill semantics correctly implemented
- Staleness tracking via `htf_is_stale` / `mtf_is_stale`

**Weaknesses**:
- Two cache paths: `TimeframeCache` (FeatureSnapshot) vs `RuntimeSnapshotView` (FeedStore indices)
- No explicit documentation of which path the engine uses

### Snapshot Architecture

**Dual Implementation Issue**:
- `RuntimeSnapshot` (types.py) - Materialized frozen dataclass
- `RuntimeSnapshotView` (snapshot_view.py) - View over FeedStore arrays

The module appears to be migrating from `RuntimeSnapshot` to `RuntimeSnapshotView`. Comments in `snapshot_view.py` explicitly state "SnapshotBuilder is NOT used" and "RuntimeSnapshot (materialized dataclass) is NOT supported".

**Recommendation**: Complete the migration and deprecate `RuntimeSnapshot` and `SnapshotBuilder`.

### State Tracking Design

**Strengths**:
- Pure transition functions with no side effects
- Clear state machine definitions with valid transition maps
- Record-only mode does not affect trade outcomes
- Factory functions and reset helpers

**Weaknesses**:
- `StateTracker.block_history` unbounded growth
- Linear search in `get_block_at()`
- Some redundancy between state enums and state classes

---

## Summary of Issues

### Priority 1 (Bugs)
1. `snapshot_view.py` line 925: `math.isnan()` used but `math` not imported

### Priority 2 (Performance)
1. `state_tracker.py`: `block_history` list grows unbounded
2. `state_tracker.py`: `get_block_at()` is O(n) linear search

### Priority 3 (Code Quality)
1. Dual snapshot implementations (`RuntimeSnapshot` vs `RuntimeSnapshotView`)
2. `snapshot_builder.py` appears to be dead code
3. `windowing.py`: Two window types (`LoadWindow`, `DataWindow`) overlap
4. Timezone handling inconsistencies in `preflight.py`
5. `preflight.py`: `run_preflight_gate()` function too long (320+ lines)

### Priority 4 (Documentation)
1. `TFContext` defined in `snapshot_view.py` - should document relationship to `FeatureSnapshot`
2. Migration status from materialized to view-based snapshots not documented

---

## Recommendations

1. **Complete snapshot migration**: Deprecate `RuntimeSnapshot`, `SnapshotBuilder`, and `TimeframeCache` in favor of view-based architecture

2. **Fix state tracker scaling**:
   - Cap `block_history` length or use ring buffer
   - Use dict for `bar_idx -> BlockState` lookup

3. **Add missing import**: Add `import math` to `snapshot_view.py`

4. **Consolidate window types**: Merge `LoadWindow` and `DataWindow`

5. **Decompose preflight**: Split `run_preflight_gate()` into smaller functions

6. **Document MTF path**: Clarify which cache path (TimeframeCache vs direct index) is canonical

---

*End of Review*
