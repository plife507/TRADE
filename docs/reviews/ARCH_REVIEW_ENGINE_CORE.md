# Architecture Review: Backtest Engine Core

**Date**: 2026-01-02
**Reviewer**: Claude Opus 4.5
**Scope**: Core backtest engine files in `src/backtest/`

---

## Executive Summary

The backtest engine is a well-structured, modular system for deterministic backtesting of trading strategies. The codebase demonstrates good separation of concerns through functional decomposition into specialized modules. However, there are notable concerns around complexity in the main engine class, tight coupling to the IdeaCard abstraction, and some code duplication across the data preparation paths.

**Overall Assessment**: Production-ready for its intended scope (USDT perpetuals, isolated margin), with opportunities for further simplification and decoupling.

---

## File-by-File Analysis

---

### 1. `engine.py` (Main Orchestrator)

**Purpose**: Central orchestrator that coordinates data loading, feed construction, bar-by-bar simulation, strategy evaluation, and result generation.

**Key Functions**:

| Function | Description | LOC |
|----------|-------------|-----|
| `__init__` | Engine initialization with config validation, tf_mapping setup, state initialization | ~140 |
| `run()` | Main simulation loop - loads data, builds feeds, iterates bars, evaluates strategy | ~500 |
| `prepare_backtest_frame()` | Delegates single-TF data prep to engine_data_prep | ~15 |
| `prepare_multi_tf_frames()` | Delegates multi-TF data prep to engine_data_prep | ~50 |
| `_build_feed_stores()` | Builds FeedStores for O(1) array access | ~30 |
| `_build_snapshot_view()` | Creates RuntimeSnapshotView for strategy evaluation | ~25 |
| `_process_signal()` | Handles strategy signals through risk sizing | ~70 |
| `_update_history()` | Updates rolling history windows | ~20 |
| `_accumulate_1m_quotes()` | Accumulates 1m quotes for rollup values | ~25 |

**Dependencies**:
- engine_data_prep (PreparedFrame, MultiTFPreparedFrames)
- engine_feed_builder (build_feed_stores_impl, build_quote_feed_impl)
- engine_snapshot (build_snapshot_view_impl, update_htf_mtf_indices_impl)
- engine_history (HistoryManager)
- engine_stops (check_all_stop_conditions, handle_terminal_stop)
- engine_artifacts (calculate_drawdowns_impl, write_artifacts_impl)
- engine_factory (run_backtest, create_engine_from_idea_card, run_engine_with_idea_card)
- runtime.* (FeedStore, RuntimeSnapshotView, TimeframeCache, etc.)
- sim (SimulatedExchange, ExecutionConfig)
- system_config (SystemConfig, RiskProfileConfig)
- indicators module
- types module

**Issues Found**:

1. **God Class Tendency** (Severity: Medium)
   - `BacktestEngine` has 30+ instance variables and 20+ methods
   - The `run()` method is ~500 lines with deeply nested logic
   - While delegation exists, the class still orchestrates too much state

2. **Mixed Abstraction Levels** (Severity: Medium)
   - `run()` mixes high-level orchestration (loop control) with low-level details (feature extraction from arrays)
   - Lines 842-855: Manual feature dict construction inside hot loop

3. **Redundant Validation** (Severity: Low)
   - Symbol/margin mode validated in `__init__`, again in `prepare_backtest_frame_impl`, and again in config loading
   - Defense-in-depth is good, but suggests unclear ownership of validation

4. **Magic Numbers** (Severity: Low)
   - Line 324: `if sim_bars < 10:` - why 10?
   - Line 553: `exec_tf_minutes = TF_MINUTES.get(self.config.tf.lower(), 15)` - silent default

5. **Conditional Complexity** (Severity: Medium)
   - `run()` has many `if self._multi_tf_mode` branches creating two parallel code paths
   - Consider strategy pattern for single-TF vs multi-TF execution

6. **Lookahead Guard Location** (Severity: Low)
   - Lines 965-978: Assertions in hot loop add overhead
   - Could be validated once at initialization or made debug-only

**Structural Concerns**:

1. **Tight Coupling to IdeaCard** - Engine now requires IdeaCard-style config (`feature_specs_by_role`, `warmup_bars_by_role`), but maintains backward-compat surface for YAML SystemConfig. This dual path adds complexity.

2. **State Tracker Integration** - `_state_tracker` is optionally wired throughout `run()` with many conditional calls. Consider observer pattern or AOP-style hooks.

---

### 2. `engine_data_prep.py` (Data Loading & Preparation)

**Purpose**: Handles all data loading, indicator computation, and warmup calculation for single-TF and multi-TF modes.

**Key Functions**:

| Function | Description |
|----------|-------------|
| `timeframe_to_timedelta()` | Converts TF string to timedelta |
| `prepare_backtest_frame_impl()` | Single-TF data preparation with warmup, indicators, first_valid_bar |
| `prepare_multi_tf_frames_impl()` | Multi-TF data preparation with close_ts maps |
| `load_data_impl()` | Thin wrapper around prepare_backtest_frame_impl |
| `get_tf_features_at_close_impl()` | Extracts features from TF DataFrame at timestamp |
| `load_1m_data_impl()` | Loads 1m quote data for rollup bucket |

**Dependencies**:
- runtime.types (FeatureSnapshot, Bar)
- runtime.timeframe (tf_duration, ceil_to_tf_close)
- runtime.windowing (compute_data_window)
- runtime.cache (build_close_ts_map_from_df)
- system_config (validate_* functions)
- indicators module
- data.historical_data_store

**Issues Found**:

1. **Code Duplication** (Severity: Medium)
   - `prepare_backtest_frame_impl()` and `prepare_multi_tf_frames_impl()` share ~70% of logic:
     - Warmup retrieval from config
     - Mode lock validations
     - Data loading pattern
     - Indicator application
     - First valid bar finding
     - Delay bars application
   - Consider extracting common logic into shared helper

2. **Complex Warmup Logic** (Severity: Medium)
   - Lines 166-178: Warmup retrieval with error message is duplicated
   - Warmup source is unclear - Preflight computes it, but config carries it, and engine validates it exists

3. **Long Functions** (Severity: Medium)
   - `prepare_backtest_frame_impl()` is ~230 lines
   - `prepare_multi_tf_frames_impl()` is ~260 lines
   - Both could be broken into smaller focused functions

4. **Silent Fallback in get_tf_features_at_close_impl** (Severity: Low)
   - Lines 486-490: Falls back from role-specific specs to 'exec' specs silently
   - This could mask configuration errors

5. **Undefined Variable Reference** (Severity: High - Bug)
   - Line 319: References `warmup_multiplier` which is not defined in scope
   - This would cause NameError if reached

**Structural Concerns**:

1. **PreparedFrame vs MultiTFPreparedFrames** - Two similar dataclasses with overlapping fields. Consider unifying with multi-TF as the general case.

2. **Role Mapping Complexity** - Lines 478-484: Manual loop to map TF back to role feels fragile. Consider maintaining explicit role->TF->DataFrame mapping.

---

### 3. `engine_feed_builder.py` (FeedStore Construction)

**Purpose**: Builds FeedStore instances from prepared DataFrames for O(1) array access in hot loop.

**Key Functions**:

| Function | Description |
|----------|-------------|
| `build_feed_stores_impl()` | Builds FeedStores for exec/htf/mtf from prepared frames |
| `build_structures_into_feed()` | Builds market structure blocks into exec FeedStore |
| `build_quote_feed_impl()` | Builds 1m quote FeedStore |
| `get_quote_at_exec_close()` | Gets QuoteState at exec close timestamp |

**Dependencies**:
- runtime.feed_store (FeedStore, MultiTFFeedStore)
- runtime.quote_state (QuoteState)
- indicators module
- market_structure (StructureBuilder) - imported locally

**Issues Found**:

1. **Unused Class** (Severity: Low)
   - `FeedStoreBuilderResult` class defined but never used - function returns tuple directly

2. **Conditional Same-Reference Assignment** (Severity: Low)
   - Lines 123, 135: `htf_feed = exec_feed` when TFs match
   - Later code checks `htf_feed is not exec_feed` which works but is subtle
   - Consider explicit None instead of same-reference for clarity

3. **Local Import for Circular Avoidance** (Severity: Low)
   - Line 207: `from .market_structure import StructureBuilder`
   - Indicates potential circular dependency or module organization issue

4. **Magic Values** (Severity: Low)
   - Line 343: `mark_source="approx_from_ohlcv_1m"` hardcoded
   - Should come from config for traceability

**Structural Concerns**:

1. **Structure Building Side Effects** - `build_structures_into_feed()` modifies exec_feed in-place rather than returning new data. This can make debugging harder.

---

### 4. `engine_history.py` (History Management)

**Purpose**: Manages rolling history windows for strategy evaluation (bars_exec, features_exec/htf/mtf).

**Key Functions**:

| Function | Description |
|----------|-------------|
| `parse_history_config_impl()` | Parses HistoryConfig from SystemConfig params |
| `HistoryManager.__init__()` | Initializes manager with config and empty windows |
| `HistoryManager.update()` | Updates rolling windows, trims to configured size |
| `HistoryManager.is_ready()` | Checks if all windows are at required depth |
| `HistoryManager.get_tuples()` | Returns immutable history tuples for snapshot |
| `HistoryManager.reset()` | Clears all history windows |

**Dependencies**:
- runtime.types (Bar, FeatureSnapshot, HistoryConfig, DEFAULT_HISTORY_CONFIG)

**Issues Found**:

1. **List Slice Reassignment** (Severity: Low)
   - Lines 132, 138, 144, 150: `self._history_X = self._history_X[-count:]`
   - Creates new list on each trim. Consider using deque with maxlen for O(1) trimming

2. **Inconsistent Ready Check** (Severity: Low)
   - `is_ready()` returns True if config doesn't require history
   - But `get_tuples()` returns empty tuples regardless
   - Semantics could be clearer

**Structural Concerns**:

1. **Tight Coupling to FeatureSnapshot** - History stores full FeatureSnapshot objects which may be heavier than needed for some use cases.

---

### 5. `engine_snapshot.py` (Snapshot Building)

**Purpose**: Constructs RuntimeSnapshotView for strategy evaluation, handles HTF/MTF index updates.

**Key Functions**:

| Function | Description |
|----------|-------------|
| `update_htf_mtf_indices_impl()` | Updates forward-fill indices using FeedStore ts_close mapping |
| `refresh_tf_caches_impl()` | Refreshes TF caches with factory functions |
| `build_snapshot_view_impl()` | Builds RuntimeSnapshotView with all context |

**Dependencies**:
- runtime.types (FeatureSnapshot, HistoryConfig)
- runtime.feed_store (FeedStore, MultiTFFeedStore)
- runtime.snapshot_view (RuntimeSnapshotView)
- runtime.cache (TimeframeCache)
- sim (StepResult)

**Issues Found**:

1. **Unused refresh_tf_caches_impl** (Severity: Low)
   - This function exists but `_refresh_tf_caches` in engine.py is never called
   - Dead code or incomplete refactor?

2. **Mark Price Fallback Logic** (Severity: Medium)
   - Lines 152-157: Falls back to close price if step_result is None or mark_price is None
   - This fallback path is undocumented and could hide issues

**Structural Concerns**:

1. **Module is Thin** - Only ~175 lines. Consider merging with engine.py or splitting responsibilities differently.

---

### 6. `engine_stops.py` (Stop Condition Handling)

**Purpose**: Checks and handles stop conditions (liquidation, equity floor, starvation) with proper precedence.

**Key Functions**:

| Function | Description |
|----------|-------------|
| `StopCheckResult` | Dataclass for stop check results |
| `check_liquidation()` | Checks if exchange is liquidatable |
| `check_equity_floor()` | Checks if equity hit floor threshold |
| `check_strategy_starvation()` | Checks if strategy can't meet entry gate |
| `check_all_stop_conditions()` | Orchestrates all checks with precedence |
| `handle_terminal_stop()` | Handles terminal stop: cancels orders, closes position |

**Dependencies**:
- types (StopReason)

**Issues Found**:

1. **Side Effects in Check Function** (Severity: Medium)
   - `check_strategy_starvation()` calls `exchange.set_starvation()` and `exchange.cancel_pending_order()`
   - Check functions should be read-only; side effects should be handled separately
   - Makes testing harder

2. **Inconsistent Return Pattern** (Severity: Low)
   - `check_*` functions return `Optional[StopCheckResult]`
   - `check_all_stop_conditions()` always returns `StopCheckResult`
   - Consider consistent pattern

**Structural Concerns**:

1. **Logging in Stop Check** - Lines 137-139 log info inside check function. Logging should be caller's responsibility.

---

### 7. `engine_artifacts.py` (Artifact Writing)

**Purpose**: Calculates drawdowns and writes run artifacts (Parquet files, JSON result).

**Key Functions**:

| Function | Description |
|----------|-------------|
| `calculate_drawdowns_impl()` | In-place drawdown calculation on equity curve |
| `write_artifacts_impl()` | Writes trades.parquet, equity.parquet, account_curve.parquet, returns.json, result.json |

**Dependencies**:
- artifacts.parquet_writer (write_parquet)
- metrics (compute_time_based_returns)

**Issues Found**:

1. **In-Place Mutation** (Severity: Low)
   - `calculate_drawdowns_impl()` modifies EquityPoint objects in place
   - Could cause issues if equity_curve is used elsewhere

2. **Empty DataFrame Handling** (Severity: Low)
   - Lines 103-111: Empty DataFrame columns hardcoded, must stay in sync with actual columns

3. **Hash Computation Coupling** (Severity: Low)
   - Lines 167-168: Reads file back to compute hash after writing
   - Could compute hash from DataFrame bytes directly

**Structural Concerns**:

1. **Phase Comments in Production Code** - Lines like "Phase 3.2: Parquet-only format" should be in commit messages, not permanent comments.

---

### 8. `engine_factory.py` (Engine Factory Functions)

**Purpose**: Factory functions for creating and running BacktestEngine from IdeaCard.

**Key Functions**:

| Function | Description |
|----------|-------------|
| `run_backtest()` | Convenience function to run backtest from system_id (deprecated path) |
| `create_engine_from_idea_card()` | Creates BacktestEngine from IdeaCard |
| `run_engine_with_idea_card()` | Runs engine with IdeaCard signal evaluation |
| `_verify_all_conditions_compiled()` | Verifies all IdeaCard conditions have compiled refs |
| `_get_idea_card_result_class()` | Returns IdeaCardBacktestResult class |

**Dependencies**:
- engine (BacktestEngine) - imported locally
- system_config (SystemConfig, RiskProfileConfig, etc.) - imported locally
- execution_validation (IdeaCardSignalEvaluator, etc.) - imported locally
- idea_card_yaml_builder (compile_idea_card) - imported locally
- core.risk_manager (Signal)

**Issues Found**:

1. **Long Function** (Severity: Medium)
   - `create_engine_from_idea_card()` is ~200 lines
   - Mixes validation, config extraction, transformation, and engine creation
   - Should be broken into:
     - `_validate_idea_card()`
     - `_build_risk_profile_from_idea_card()`
     - `_build_system_config_from_idea_card()`
     - `create_engine_from_idea_card()`

2. **Magic Defaults** (Severity: Medium)
   - Line 129: `slippage_bps = 5.0` default
   - Line 137: `risk_per_trade_pct = 1.0` default
   - Line 146: `maintenance_margin_rate = 0.005` default
   - These should be constants with clear names

3. **Inconsistent Error Messages** (Severity: Low)
   - Some errors include fix suggestions, others don't
   - Standardize error message format

4. **Duplicate Dataclass** (Severity: Low)
   - `IdeaCardBacktestResult` defined at module level (line 404)
   - `_get_idea_card_result_class()` returns it
   - Unnecessary indirection

5. **Local Imports Everywhere** (Severity: Medium)
   - Many imports inside functions to avoid circular dependencies
   - Indicates module organization issues

**Structural Concerns**:

1. **run_backtest Deprecation** - Function exists but uses deprecated `load_system_config`. Should be removed or clearly marked.

2. **Signal Conversion Logic** - `run_engine_with_idea_card()` converts IdeaCard signals to core.Signal. This translation layer adds complexity.

---

### 9. `types.py` (Type Definitions)

**Purpose**: Core type definitions for backtesting (Trade, EquityPoint, BacktestMetrics, BacktestResult, etc.).

**Key Types**:

| Type | Description |
|------|-------------|
| `StopReason` | Enum for stop classifications |
| `Trade` | Executed trade record with PnL, MAE/MFE |
| `EquityPoint` | Single equity curve point |
| `AccountCurvePoint` | Full margin state per bar |
| `WindowConfig` | Resolved window configuration |
| `BacktestMetrics` | 62-field metrics dataclass |
| `StrategyInstanceSummary` | Strategy instance summary for result |
| `BacktestRunConfigEcho` | Config snapshot for reproducibility |
| `BacktestResult` | Complete backtest output |
| `TimeBasedReturns` | Daily/weekly/monthly return analytics |

**Dependencies**:
- runtime.types (Bar - re-exported)

**Issues Found**:

1. **BacktestMetrics is Very Large** (Severity: Medium)
   - 62 fields in a single dataclass
   - Could be organized into nested dataclasses:
     - `EquityMetrics`
     - `DrawdownMetrics`
     - `TradeMetrics`
     - `RiskMetrics`
     - `TailRiskMetrics`
     - `LeverageMetrics`

2. **Default Values for Required Fields** (Severity: Medium)
   - `BacktestResult.start_ts`, `end_ts` etc. have no defaults but others do
   - Inconsistent required vs optional semantics

3. **Duplicate to_dict() Logic** (Severity: Low)
   - Every dataclass has manual `to_dict()` method
   - Consider using `dataclasses.asdict()` with custom encoder

4. **Property Aliases** (Severity: Low)
   - Lines 563-569: `start_time` and `end_time` property aliases for backward compat
   - Document or remove

**Structural Concerns**:

1. **Re-export Pattern** - `Bar` re-exported from `runtime.types`. Consider having one canonical location.

2. **Optional vs None** - Many fields use `Optional[X] = None` pattern. Consider distinguishing "not set" from "computed as None".

---

### 10. `system_config.py` (Configuration Management)

**Purpose**: Loads and validates YAML system configs, defines RiskProfileConfig, mode validation.

**Key Types/Functions**:

| Item | Description |
|------|-------------|
| `MarginMode`, `PositionMode`, `InstrumentType` | Mode enums with future placeholders |
| `validate_usdt_pair()` | Validates USDT-quoted perpetual symbol |
| `validate_margin_mode_isolated()` | Validates isolated margin mode |
| `validate_quote_ccy_and_instrument_type()` | Validates quote ccy and instrument type |
| `DataBuildConfig` | Dataset build configuration |
| `RiskProfileConfig` | Risk profile with margin/fee model |
| `StrategyInstanceConfig` | Single strategy instance config |
| `SystemConfig` | Complete system configuration |
| `load_system_config()` | Loads YAML config (deprecated) |

**Dependencies**:
- types (WindowConfig)
- window_presets (get_window_preset, has_preset)

**Issues Found**:

1. **Deprecated Function Still Central** (Severity: Medium)
   - `load_system_config()` is marked deprecated but still used
   - Deprecation warning is good but function should have clear removal timeline

2. **RiskProfileConfig Private Field** (Severity: Low)
   - `_initial_margin_rate` with property accessor
   - Uncommon pattern for dataclasses, works but surprising

3. **Validation Constants as Class Attributes** (Severity: Low)
   - Lines 285-288: `_VALID_*` constants in RiskProfileConfig
   - Better as module-level constants

4. **Long load_system_config Function** (Severity: Medium)
   - ~150 lines mixing parsing, validation, and object construction
   - Should be split into smaller functions

5. **Dual Extension Support** (Severity: Low)
   - Lines 824-830: Checks both .yml and .yaml
   - Consider standardizing on one

**Structural Concerns**:

1. **warmup_bars_by_role in SystemConfig** - This field is required by engine but not populated by YAML loading. Creates confusion about data flow.

2. **Mode Enums with Future Placeholders** - Commented-out enum values for future modes is unusual. Consider removing until implemented.

---

## Cross-Cutting Concerns

### 1. Dependency Management

**Circular Import Avoidance**:
- Multiple files use local imports (`from .engine import BacktestEngine` inside functions)
- Indicates module boundaries need rethinking

**Recommendation**: Create an explicit dependency graph and consider:
- Moving types to a shared `types.py` or `_types/` package
- Using dependency injection for complex dependencies
- Creating interface protocols for loose coupling

### 2. Error Handling

**Strengths**:
- Fail-loud philosophy is consistently applied
- Helpful error messages with fix suggestions
- Validation at multiple layers (defense in depth)

**Weaknesses**:
- No custom exception hierarchy - all `ValueError` or `RuntimeError`
- Error messages sometimes inconsistent in format
- No structured error codes for programmatic handling

**Recommendation**: Create exception hierarchy:
```
BacktestError
  ConfigurationError
    MissingWarmupError
    InvalidSymbolError
  DataError
    InsufficientDataError
    DataGapError
  ExecutionError
    LiquidationError
    StarvationError
```

### 3. State Management

**Concerns**:
- Engine holds 30+ instance variables
- State modified across many methods
- No clear state machine or lifecycle

**Recommendation**:
- Consider explicit phases: INIT -> DATA_LOADED -> FEEDS_BUILT -> RUNNING -> COMPLETE
- Make phase transitions explicit with methods like `engine.advance_to_running()`

### 4. Performance

**Hot Loop Optimization**:
- FeedStore provides O(1) array access (good)
- RuntimeSnapshotView avoids DataFrame operations (good)
- Assertions in hot loop (concern)
- Feature dict construction still happens in loop (concern)

**Recommendation**:
- Move assertions to debug mode or initialization
- Pre-allocate feature extraction or use views

### 5. Testing Implications

**Concerns**:
- Many functions have side effects (check_strategy_starvation)
- In-place mutation (calculate_drawdowns)
- Complex initialization (BacktestEngine needs full config)

**Recommendation**:
- Separate pure computation from side effects
- Create test fixtures for common configs
- Add builder pattern for test config construction

---

## Summary of Findings

### High Priority (Fix Soon)

1. **Bug: Undefined Variable** - `warmup_multiplier` in line 319 of engine_data_prep.py
2. **God Class** - BacktestEngine.run() is too long and complex
3. **Code Duplication** - Single-TF and Multi-TF data prep share 70% logic

### Medium Priority (Improve)

4. **Side Effects in Check Functions** - engine_stops.py checks should be read-only
5. **Long Functions** - create_engine_from_idea_card, prepare_*_impl functions
6. **BacktestMetrics Size** - 62 fields should be organized into nested structures
7. **Circular Import Workarounds** - Many local imports indicate architecture issue
8. **Dual Code Paths** - multi_tf_mode conditionals throughout run()

### Low Priority (Consider)

9. **Unused Code** - FeedStoreBuilderResult, refresh_tf_caches_impl
10. **In-place Mutations** - calculate_drawdowns, EquityPoint updates
11. **Magic Numbers** - Various hardcoded values without constants
12. **Property Aliases** - Backward compat properties add noise

---

## Recommendations

### Short-term (Next Sprint)

1. Fix the `warmup_multiplier` undefined variable bug
2. Extract `run()` loop body into smaller methods
3. Add constants for magic numbers

### Medium-term (Next Month)

1. Unify single-TF and multi-TF data preparation
2. Organize BacktestMetrics into nested dataclasses
3. Create explicit exception hierarchy
4. Remove deprecated code paths

### Long-term (Next Quarter)

1. Refactor BacktestEngine into smaller collaborating classes
2. Establish clear module boundaries to eliminate circular imports
3. Add explicit lifecycle state machine
4. Consider event-driven architecture for hooks (state tracking, logging)

---

## Appendix: Dependency Graph

```
engine.py
  |-- engine_data_prep.py
  |-- engine_feed_builder.py
  |-- engine_snapshot.py
  |-- engine_history.py
  |-- engine_stops.py
  |-- engine_artifacts.py
  |-- engine_factory.py (re-exports)
  |-- types.py
  |-- system_config.py
  |-- runtime/*
  |-- sim/*
  |-- indicators.py
  |-- metrics.py
```

```
engine_factory.py
  |-- engine.py (local import)
  |-- system_config.py (local import)
  |-- execution_validation.py (local import)
  |-- idea_card_yaml_builder.py (local import)
```

---

*End of Architecture Review*
