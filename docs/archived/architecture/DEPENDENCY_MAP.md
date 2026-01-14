# Backtest Simulator Dependency Map

> Generated: 2026-01-11
> Purpose: Document all file imports and dependencies in the backtest simulator

## Overview

This document maps all imports and dependencies between modules in `src/backtest/`.

---

## Phase 1: Entry Points

### engine.py
**Location**: `src/backtest/engine.py`
**Lines**: ~1618
**Role**: Main orchestrator for deterministic backtesting

**External Imports**:
- `collections.abc.Callable`
- `json`
- `numpy as np`
- `pandas as pd`
- `datetime.datetime, timedelta`
- `pathlib.Path`
- `typing.Any, TYPE_CHECKING`
- `uuid`

**Internal Imports (backtest/)**:
- `.engine_data_prep`: PreparedFrame, MultiTFPreparedFrames, prepare_backtest_frame_impl, prepare_multi_tf_frames_impl, load_data_impl, load_1m_data_impl, load_funding_data_impl, load_open_interest_data_impl, timeframe_to_timedelta, get_tf_features_at_close_impl
- `.engine_feed_builder`: build_feed_stores_impl, build_quote_feed_impl, get_quote_at_exec_close, build_structures_into_feed, build_market_data_arrays_impl
- `.runtime.funding_scheduler`: get_funding_events_in_window
- `.engine_snapshot`: build_snapshot_view_impl, update_htf_mtf_indices_impl, refresh_tf_caches_impl
- `.engine_history`: HistoryManager, parse_history_config_impl
- `.engine_stops`: StopCheckResult, check_all_stop_conditions, handle_terminal_stop
- `.engine_artifacts`: calculate_drawdowns_impl, write_artifacts_impl
- `.bar_processor`: BarProcessor, BarProcessingResult
- `.engine_factory`: run_backtest, create_engine_from_play, run_engine_with_play
- `.types`: Trade, EquityPoint, AccountCurvePoint, BacktestMetrics, BacktestResult, BacktestRunConfigEcho, StrategyInstanceSummary, WindowConfig, StopReason
- `.runtime.types`: Bar (as CanonicalBar), FeatureSnapshot, RuntimeSnapshot, HistoryConfig, DEFAULT_HISTORY_CONFIG, create_not_ready_feature_snapshot
- `.runtime.timeframe`: tf_duration, tf_minutes, validate_tf_mapping, ceil_to_tf_close
- `.runtime.cache`: TimeframeCache
- `.runtime.feed_store`: FeedStore, MultiTFFeedStore
- `.runtime.snapshot_view`: RuntimeSnapshotView
- `.runtime.rollup_bucket`: ExecRollupBucket, create_empty_rollup_dict
- `.runtime.state_tracker`: StateTracker, create_state_tracker
- `.runtime.quote_state`: QuoteState
- `.system_config`: SystemConfig, load_system_config, RiskProfileConfig, validate_usdt_pair, validate_margin_mode_isolated, validate_quote_ccy_and_instrument_type
- `.indicators`: apply_feature_spec_indicators, get_warmup_from_specs, get_max_warmup_from_specs_by_role, get_required_indicator_columns_from_specs, find_first_valid_bar
- `.sim`: SimulatedExchange, ExecutionConfig, StepResult
- `.simulated_risk_manager`: SimulatedRiskManager
- `.risk_policy`: RiskPolicy, create_risk_policy, RiskDecision
- `.metrics`: compute_backtest_metrics
- `.incremental.base`: BarData
- `.incremental.state`: MultiTFIncrementalState
- `.incremental.registry`: list_structure_types
- `.rationalization`: StateRationalizer, RationalizedState

**Internal Imports (other src/)**:
- `..core.risk_manager`: Signal
- `..data.historical_data_store`: get_historical_store, TF_MINUTES
- `..utils.logger`: get_logger
- `..utils.debug`: debug_log, debug_milestone, debug_signal, debug_trade, debug_run_complete, is_debug_enabled

**TYPE_CHECKING imports**:
- `.feature_registry`: FeatureRegistry
- `.play`: Play

**Public API**:
- `BacktestEngine` class: Main engine with run(), prepare_backtest_frame(), etc.
- Re-exports from engine_factory: run_backtest, create_engine_from_play, run_engine_with_play

**Depends On**: 17 internal modules, 4 external packages
**Used By**: runner.py, engine_factory.py, tools/backtest_tools.py

---

### runner.py
**Location**: `src/backtest/runner.py`
**Lines**: ~944
**Role**: Backtest Runner with Gate Enforcement

**External Imports**:
- `collections.abc.Callable`
- `dataclasses.dataclass, field`
- `datetime.datetime, timezone`
- `typing.Any`
- `pathlib.Path`
- `json`
- `time`
- `pandas as pd`

**Internal Imports (backtest/)**:
- `.play`: Play, load_play
- `.runtime.preflight`: PreflightStatus, PreflightReport, run_preflight_gate, DataLoader
- `.artifacts.artifact_standards`: ArtifactPathConfig, ArtifactValidationResult, validate_artifacts, validate_artifact_path_config, ResultsSummary, compute_results_summary, STANDARD_FILES, RunManifest
- `.artifacts.hashes`: compute_trades_hash, compute_equity_hash, compute_run_hash, InputHashComponents
- `.artifacts.parquet_writer`: write_parquet
- `.gates.indicator_requirements_gate`: validate_indicator_requirements, extract_available_keys_from_feature_frames, IndicatorGateStatus, IndicatorRequirementsResult
- `.execution_validation`: validate_play_full, compute_warmup_requirements, compute_play_hash, PlaySignalEvaluator, SignalDecision
- `.logging`: RunLogger, set_run_logger
- `.artifacts.pipeline_signature`: PIPELINE_VERSION, PipelineSignature, PIPELINE_SIGNATURE_FILE, create_pipeline_signature
- `.engine`: create_engine_from_play, run_engine_with_play (dynamic import)
- `.snapshot_artifacts`: emit_snapshot_artifacts (dynamic import)

**Internal Imports (other src/)**:
- `..data.historical_data_store`: get_historical_store (dynamic import)

**Public API**:
- `GateFailure` exception
- `PlayBacktestResult` class
- `RunnerConfig` dataclass
- `RunnerResult` dataclass
- `run_backtest_with_gates()` function
- `run_smoke_test()` function
- `main()` CLI entrypoint

**Depends On**: 10 internal backtest modules, 1 external data module
**Used By**: CLI (trade_cli.py), tools/backtest_tools.py

---

### engine_factory.py
**Location**: `src/backtest/engine_factory.py`
**Lines**: ~503
**Role**: Factory functions for BacktestEngine creation

**External Imports**:
- `collections.abc.Callable`
- `dataclasses.dataclass`
- `datetime.datetime`
- `pathlib.Path`
- `typing.Any, TYPE_CHECKING`

**Internal Imports (backtest/)** - dynamic:
- `.engine`: BacktestEngine (dynamic)
- `.system_config`: load_system_config, SystemConfig, RiskProfileConfig, StrategyInstanceConfig, StrategyInstanceInputs (dynamic)
- `.features.feature_spec`: FeatureSpec, InputSource as FSInputSource (dynamic)
- `.feature_registry`: FeatureType (dynamic)
- `.runtime.timeframe`: tf_minutes (dynamic)
- `.rules.dsl_nodes`: Expr, Cond, AllExpr, AnyExpr, NotExpr, HoldsFor, OccurredWithin, CountTrue (dynamic)
- `.execution_validation`: PlaySignalEvaluator, SignalDecision, compute_play_hash (dynamic)

**Internal Imports (other src/)** - dynamic:
- `..core.risk_manager`: Signal (dynamic)

**TYPE_CHECKING imports**:
- `.engine`: BacktestEngine
- `.types`: BacktestResult
- `.play`: Play
- `.feature_registry`: FeatureRegistry
- `.runtime.types`: RuntimeSnapshot
- `.runtime.snapshot_view`: RuntimeSnapshotView
- `..core.risk_manager`: Signal

**Public API**:
- `run_backtest()`: Convenience function for system_id-based runs
- `create_engine_from_play()`: Factory for Play-native engine creation
- `run_engine_with_play()`: Run engine with Play signal evaluation
- `PlayBacktestResult` dataclass
- `_get_play_result_class()`: Helper for import avoidance

**Depends On**: 7 internal modules (mostly dynamic imports)
**Used By**: engine.py (re-exports), runner.py

---

### bar_processor.py
**Location**: `src/backtest/bar_processor.py`
**Lines**: ~654
**Role**: Per-bar processing logic extracted from engine.run()

**External Imports**:
- `collections.abc.Callable`
- `datetime.datetime`
- `typing.TYPE_CHECKING, Any`
- `numpy as np`

**Internal Imports (backtest/)**:
- `.types`: Trade, EquityPoint, AccountCurvePoint, StopReason
- `.runtime.types`: Bar (as CanonicalBar), FeatureSnapshot
- `.runtime.feed_store`: FeedStore
- `.runtime.quote_state`: QuoteState
- `.sim`: StepResult
- `.engine_stops`: StopCheckResult, check_all_stop_conditions, handle_terminal_stop
- `.runtime.funding_scheduler`: get_funding_events_in_window
- `.incremental.base`: BarData

**Internal Imports (other src/)**:
- `..core.risk_manager`: Signal
- `..data.historical_data_store`: TF_MINUTES
- `..utils.debug`: debug_milestone

**TYPE_CHECKING imports**:
- `.engine`: BacktestEngine
- `.runtime.snapshot_view`: RuntimeSnapshotView

**Public API**:
- `BarProcessingResult` class
- `BarProcessor` class with:
  - `build_bar()`: O(1) bar construction
  - `process_warmup_bar()`: Warmup period (no trading)
  - `process_trading_bar()`: Full trading logic

**Depends On**: 9 internal modules
**Used By**: engine.py

---

## Phase 2: sim/ Directory

The `sim/` directory contains the SimulatedExchange and all modular components for deterministic backtesting.

### Directory Structure

```
sim/
├── __init__.py          # Public API exports
├── exchange.py          # Main orchestrator (~1067 lines)
├── types.py             # All shared types (~873 lines)
├── ledger.py            # USDT accounting (~367 lines)
├── bar_compat.py        # Bar timestamp compatibility
├── pricing/
│   ├── __init__.py
│   ├── price_model.py   # Mark/last/mid price derivation
│   ├── spread_model.py  # Bid/ask spread simulation
│   └── intrabar_path.py # Deterministic TP/SL checking
├── execution/
│   ├── __init__.py
│   ├── execution_model.py # Market/limit/stop execution
│   ├── slippage_model.py  # Slippage estimation
│   ├── impact_model.py    # Market impact
│   └── liquidity_model.py # Partial fill caps
├── funding/
│   ├── __init__.py
│   └── funding_model.py   # Funding rate application
├── liquidation/
│   ├── __init__.py
│   └── liquidation_model.py # Mark-based liquidation
├── constraints/
│   ├── __init__.py
│   └── constraints.py     # Tick/lot/min_notional validation
├── metrics/
│   ├── __init__.py
│   └── metrics.py         # Exchange-side metrics
└── adapters/
    ├── __init__.py
    ├── ohlcv_adapter.py   # OHLCV data conversion
    └── funding_adapter.py # Funding data conversion
```

### sim/__init__.py
**Location**: `src/backtest/sim/__init__.py`
**Role**: Public API exports for simulated exchange

**Exports**:
- `SimulatedExchange` (from exchange.py)
- Enums: `OrderType`, `OrderSide`, `OrderStatus`, `FillReason`, `StopReason`, `TimeInForce`, `TriggerDirection`
- Core types: `Bar`, `Order`, `OrderId`, `OrderBook`, `Fill`, `Position`, `FundingEvent`, `LiquidationEvent`, `PriceSnapshot`
- Results: `FillResult`, `FundingResult`, `LiquidationResult`, `LedgerState`, `LedgerUpdate`, `StepResult`, `SimulatorExchangeState`
- Config: `ExecutionConfig`
- Adapters: `adapt_ohlcv_row`, `adapt_funding_rows`

---

### sim/exchange.py
**Location**: `src/backtest/sim/exchange.py`
**Lines**: ~1067
**Role**: Thin orchestrator that routes to modular components

**External Imports**:
- `dataclasses.dataclass`
- `datetime.datetime`
- `typing.TYPE_CHECKING`

**Internal Imports (sim/)**:
- `.types`: Bar, Order, OrderBook, OrderId, OrderSide, OrderType, OrderStatus, TimeInForce, TriggerDirection, Position, Fill, FillReason, FundingEvent, StepResult, SimulatorExchangeState, StopReason, ExecutionConfig, FundingResult
- `.bar_compat`: get_bar_ts_open, get_bar_timestamp
- `.ledger`: Ledger, LedgerConfig
- `.pricing`: PriceModel, PriceModelConfig, SpreadModel, SpreadConfig, IntrabarPath
- `.pricing.intrabar_path`: check_tp_sl_1m
- `.execution`: ExecutionModel, ExecutionModelConfig, SlippageConfig
- `.funding`: FundingModel
- `.liquidation`: LiquidationModel

**Internal Imports (backtest/)**:
- `..types`: Trade
- `..system_config`: validate_usdt_pair, RiskProfileConfig (TYPE_CHECKING)
- `..runtime.feed_store`: FeedStore (TYPE_CHECKING)

**Public API**:
- `SimulatedExchange` class with:
  - Properties: cash_balance_usdt, unrealized_pnl_usdt, equity_usdt, used_margin_usdt, free_margin_usdt, available_balance_usdt, maintenance_margin, leverage, total_fees_paid, is_liquidatable
  - Order methods: submit_order(), submit_limit_order(), submit_stop_order(), cancel_order_by_id(), cancel_all_orders(), amend_order(), get_open_orders(), submit_close()
  - Bar processing: process_bar()
  - State: force_close_position(), get_state()

**Depends On**: 7 sim/ modules, 3 backtest/ modules
**Used By**: engine.py, bar_processor.py

---

### sim/types.py
**Location**: `src/backtest/sim/types.py`
**Lines**: ~873
**Role**: All shared types, enums, events, and snapshots

**External Imports**:
- `dataclasses.dataclass, field`
- `datetime.datetime`
- `enum.Enum`
- `typing.Any`

**Internal Imports**:
- `..types`: StopReason (re-export)
- `..runtime.types`: Bar (re-export)

**Defines**:
- Enums: `OrderType`, `OrderSide`, `OrderStatus`, `FillReason`, `TimeInForce`, `TriggerDirection`
- Core dataclasses: `Order`, `Position`, `Fill`
- Event dataclasses: `FundingEvent`, `LiquidationEvent`
- Snapshot dataclasses: `PriceSnapshot`, `PricePoint`
- Result dataclasses: `Rejection`, `FillResult`, `FundingResult`, `LiquidationResult`, `LedgerState`, `LedgerUpdate`, `StepResult`, `SimulatorExchangeState`
- Config: `ExecutionConfig`
- Container: `OrderBook` class

**Depends On**: backtest/types.py, backtest/runtime/types.py
**Used By**: All sim/ modules, engine.py, bar_processor.py

---

### sim/ledger.py
**Location**: `src/backtest/sim/ledger.py`
**Lines**: ~367
**Role**: USDT accounting with Bybit-aligned margin model

**External Imports**:
- `dataclasses.dataclass`
- `typing.TYPE_CHECKING`

**Internal Imports**:
- `.types`: Fill, Position, FundingResult, PriceSnapshot, LedgerState, LedgerUpdate, OrderSide

**Public API**:
- `LedgerConfig` dataclass
- `Ledger` class with:
  - Properties: state, is_liquidatable
  - Methods: check_invariants(), update_for_mark_price(), apply_entry_fee(), apply_exit(), apply_partial_exit(), apply_funding(), apply_liquidation_fee(), compute_required_for_entry(), can_afford_entry()

**Invariants Enforced**:
1. equity = cash_balance + unrealized_pnl
2. free_margin = equity - used_margin
3. available_balance = max(0, free_margin)

**Depends On**: sim/types.py only
**Used By**: sim/exchange.py

---

### sim/pricing/ Submodule
**Role**: Price derivation and intrabar path simulation

| Module | Exports | Purpose |
|--------|---------|---------|
| `price_model.py` | `PriceModel`, `PriceModelConfig` | Mark/last/mid price from OHLC |
| `spread_model.py` | `SpreadModel`, `SpreadConfig` | Bid/ask spread simulation |
| `intrabar_path.py` | `IntrabarPath`, `IntrabarPathConfig`, `check_tp_sl_1m()` | Deterministic TP/SL checking |

**Dependencies**: Only sim/types.py

---

### sim/execution/ Submodule
**Role**: Order execution with slippage, impact, and liquidity

| Module | Exports | Purpose |
|--------|---------|---------|
| `execution_model.py` | `ExecutionModel`, `ExecutionModelConfig` | Market/limit/stop execution |
| `slippage_model.py` | `SlippageModel`, `SlippageConfig` | Slippage estimation |
| `impact_model.py` | `ImpactModel`, `ImpactConfig` | Market impact modeling |
| `liquidity_model.py` | `LiquidityModel`, `LiquidityConfig` | Partial fill caps |

**Dependencies**: sim/types.py, slippage/impact/liquidity models

---

### sim/funding/ Submodule
**Role**: Funding rate application

| Module | Exports | Purpose |
|--------|---------|---------|
| `funding_model.py` | `FundingModel`, `FundingModelConfig` | Apply funding to positions |

**Dependencies**: sim/types.py only

---

### sim/liquidation/ Submodule
**Role**: Margin-based liquidation

| Module | Exports | Purpose |
|--------|---------|---------|
| `liquidation_model.py` | `LiquidationModel`, `LiquidationModelConfig` | Check/trigger liquidation |

**Dependencies**: sim/types.py only

---

### sim/constraints/ Submodule
**Role**: Exchange constraint validation

| Module | Exports | Purpose |
|--------|---------|---------|
| `constraints.py` | `Constraints`, `ConstraintConfig`, `ValidationResult` | Tick/lot/min_notional |

**Dependencies**: sim/types.py only

---

### sim/adapters/ Submodule
**Role**: Data format conversion

| Module | Exports | Purpose |
|--------|---------|---------|
| `ohlcv_adapter.py` | `adapt_ohlcv_row`, `adapt_ohlcv_dataframe`, `build_bar_close_ts_map` | OHLCV conversion |
| `funding_adapter.py` | `adapt_funding_rows`, `adapt_funding_dataframe` | Funding data conversion |

**Dependencies**: sim/types.py, pandas

---

### sim/ Import Statistics

| Module | Internal Imports | External Imports | Lines |
|--------|-----------------|------------------|-------|
| exchange.py | 10 modules | 3 packages | ~1067 |
| types.py | 2 modules | 4 packages | ~873 |
| ledger.py | 1 module | 2 packages | ~367 |
| pricing/* | 1-2 modules | 2 packages | ~200 each |
| execution/* | 2-3 modules | 2 packages | ~150 each |
| funding/* | 1 module | 2 packages | ~100 |
| liquidation/* | 1 module | 2 packages | ~100 |

### Key Observations (Phase 2)

1. **Clean separation**: sim/ is well-modularized with clear responsibility boundaries
2. **Types as foundation**: sim/types.py is the single source of truth for all exchange types
3. **Minimal external deps**: Most modules only depend on sim/types.py and stdlib
4. **Ledger invariants**: Financial accounting has explicit invariant enforcement
5. **Adapter pattern**: Clean separation between exchange logic and data format conversion
6. **Re-exports**: Bar and StopReason are re-exported from backtest/runtime and backtest/types respectively

---

## Phase 3: runtime/ + features/

The `runtime/` directory provides the core execution runtime for backtesting.
The `features/` directory handles indicator specification and computation.

### runtime/ Directory Structure

```
runtime/
├── __init__.py          # Public API exports (extensive)
├── types.py             # Bar, RuntimeSnapshot, ExchangeState (~510 lines)
├── feed_store.py        # FeedStore, MultiTFFeedStore (~560 lines)
├── snapshot_view.py     # RuntimeSnapshotView (~1750 lines)
├── timeframe.py         # tf_duration, tf_minutes, validate_tf_mapping
├── windowing.py         # Load window computation
├── data_health.py       # Data health checks
├── cache.py             # Multi-TF feature caching
├── quote_state.py       # 1m price feed (QuoteState)
├── rollup_bucket.py     # 1m aggregates (ExecRollupBucket)
├── indicator_metadata.py # Provenance tracking
├── preflight.py         # Preflight gate validation
├── state_types.py       # State tracking enums (SignalStateValue, etc.)
├── signal_state.py      # Signal state machine
├── action_state.py      # Action state machine
├── gate_state.py        # Gate evaluation
├── block_state.py       # Block state tracking
├── state_tracker.py     # StateTracker (record-only)
└── funding_scheduler.py # Funding event scheduling
```

---

### runtime/types.py
**Location**: `src/backtest/runtime/types.py`
**Lines**: ~510
**Role**: Core runtime types (Bar, RuntimeSnapshot, ExchangeState)

**External Imports**:
- `dataclasses.dataclass, field`
- `datetime.datetime`
- `typing.Any`

**Internal Imports**: None (foundation module)

**Defines**:
- `HistoryConfig`: Config for snapshot history depth
- `Bar`: Canonical OHLCV bar with ts_open/ts_close
- `FeatureSnapshot`: Indicator snapshot per timeframe
- `ExchangeState`: Immutable exchange state snapshot
- `RuntimeSnapshot`: Complete point-in-time state for strategy
- `create_not_ready_feature_snapshot()`: Factory for warmup state

**Depends On**: Nothing (foundation)
**Used By**: Nearly all backtest modules

---

### runtime/feed_store.py
**Location**: `src/backtest/runtime/feed_store.py`
**Lines**: ~560
**Role**: Precomputed arrays for O(1) hot loop access

**External Imports**:
- `bisect`
- `numpy as np`
- `pandas as pd`
- `dataclasses.dataclass, field`
- `datetime.datetime`
- `typing.TYPE_CHECKING`

**TYPE_CHECKING Imports**:
- `features.feature_frame_builder.FeatureArrays`
- `runtime.indicator_metadata.IndicatorMetadata`
- `market_structure.builder.StructureStore`

**Public API**:
- `FeedStore` class with:
  - OHLCV arrays: ts_open, ts_close, open, high, low, close, volume
  - indicators dict: name -> numpy array
  - indicator_metadata dict: name -> IndicatorMetadata
  - structures dict: block_id -> StructureStore
  - Factory methods: from_dataframe(), from_dataframe_with_features()
  - Accessors: get_structure_field(), get_zone_field()
- `MultiTFFeedStore`: Container for HTF/MTF/Exec FeedStores

**Performance Contract**:
- O(1) array access for all OHLCV and indicators
- ts_close_ms_to_idx: O(1) timestamp to index mapping
- Binary search for last closed bar lookup

**Depends On**: runtime/timeframe.py
**Used By**: engine.py, bar_processor.py, snapshot_view.py

---

### runtime/snapshot_view.py
**Location**: `src/backtest/runtime/snapshot_view.py`
**Lines**: ~1750
**Role**: Array-backed snapshot for hot-loop performance

**External Imports**:
- `math`
- `collections.abc.Callable`
- `dataclasses.dataclass, field`
- `datetime.datetime`
- `functools.lru_cache`
- `typing.Any, TYPE_CHECKING`
- `numpy as np`

**Internal Imports**:
- `.feed_store`: FeedStore, MultiTFFeedStore
- `.types`: ExchangeState, HistoryConfig, DEFAULT_HISTORY_CONFIG

**TYPE_CHECKING Imports**:
- `incremental.state.MultiTFIncrementalState`
- `feature_registry.FeatureRegistry`
- `rationalization.RationalizedState`

**Public API**:
- `TFContext` class: Context for single timeframe
- `RuntimeSnapshotView` class with:
  - Price accessors: mark_price, last_price, close, open, high, low
  - Indicator accessors: indicator(), indicator_strict(), prev_indicator()
  - Feature lookup: get_feature(), has_feature(), get_feature_value()
  - Structure lookup: get_structure(), list_structure_paths()
  - Canonical path resolver: get(), get_with_offset(), has_path()

**Namespace Resolvers**:
- `price.*` -> mark price and bar prices
- `indicator.*` -> indicator values by TF role
- `structure.*` -> incremental or FeedStore structures
- `feature.*` -> Feature Registry-based lookup

**Depends On**: runtime/feed_store.py, runtime/types.py
**Used By**: engine.py, bar_processor.py, rules/evaluation/

---

### features/ Directory Structure

```
features/
├── __init__.py            # Public API exports
├── feature_spec.py        # FeatureSpec, FeatureSpecSet (~530 lines)
└── feature_frame_builder.py # FeatureFrameBuilder, IndicatorCompute
```

---

### features/feature_spec.py
**Location**: `src/backtest/features/feature_spec.py`
**Lines**: ~530
**Role**: Declarative indicator specification

**External Imports**:
- `dataclasses.dataclass, field`
- `enum.Enum`
- `typing.Any`

**Internal Imports**: None in file, but delegates to indicator_registry.py

**Public API**:
- `InputSource` enum: OPEN, HIGH, LOW, CLOSE, VOLUME, HLC3, OHLC4, INDICATOR
- `FeatureSpec` dataclass:
  - indicator_type, output_key, params, input_source
  - is_multi_output, output_keys_list, warmup_bars
- `FeatureSpecSet`: Collection with dependency ordering
- Factory functions: ema_spec(), sma_spec(), rsi_spec(), atr_spec(), macd_spec(), bbands_spec(), stoch_spec(), stochrsi_spec()

**Validation**:
- Validates against IndicatorRegistry
- Validates multi-output mappings
- Validates indicator dependencies

**Depends On**: indicator_registry.py (via imports)
**Used By**: engine.py, engine_factory.py, features/feature_frame_builder.py

---

### runtime/ Import Statistics

| Module | Internal Imports | External Imports | Lines |
|--------|-----------------|------------------|-------|
| types.py | 0 modules | 3 packages | ~510 |
| feed_store.py | 1 module | 5 packages | ~560 |
| snapshot_view.py | 2 modules | 6 packages | ~1750 |
| feature_spec.py | 0 modules | 3 packages | ~530 |

### Key Observations (Phase 3)

1. **Foundation types**: runtime/types.py has NO internal dependencies - true foundation
2. **Massive snapshot_view**: At ~1750 lines, snapshot_view.py handles many responsibilities (accessor, resolver, structure lookup)
3. **Namespace dispatch**: snapshot_view uses dispatch table pattern for scalability
4. **LRU caching**: Path tokenization cached to avoid string split in hot loop
5. **TYPE_CHECKING isolation**: Heavy use of TYPE_CHECKING imports to avoid circular dependencies
6. **Clean feature spec**: feature_spec.py is self-contained, delegates to registry

---

## Phase 4: rules/

The `rules/` directory contains the DSL compilation and evaluation system for Play actions.

### rules/ Directory Structure

```
rules/
├── __init__.py          # Public API exports
├── types.py             # ReasonCode, ValueType, EvalResult, RefValue
├── compile.py           # CompiledRef, compile_ref (~409 lines)
├── eval.py              # evaluate_condition, OPERATORS
├── registry.py          # OPERATOR_REGISTRY, OperatorSpec
├── dsl_parser.py        # YAML → AST parsing (~774 lines)
├── dsl_eval.py          # Re-export shim for backward compatibility
├── dsl_nodes.py         # Re-export shim for backward compatibility
├── dsl_warmup.py        # Warmup calculation from expressions
├── strategy_blocks.py   # Block, Case, Intent dataclasses
├── dsl_nodes/           # DSL AST node types
│   ├── constants.py     # Operator sets, limits, ceilings
│   ├── base.py          # FeatureRef, ScalarValue, ArithmeticExpr
│   ├── boolean.py       # AllExpr, AnyExpr, NotExpr, SetupRef
│   ├── condition.py     # Cond class
│   ├── windows.py       # HoldsFor, OccurredWithin, CountTrue
│   ├── types.py         # Expr type alias
│   └── utils.py         # Utility functions
└── evaluation/          # Expression evaluator
    ├── core.py          # ExprEvaluator class
    ├── boolean_ops.py   # _eval_all, _eval_any, _eval_not
    ├── condition_ops.py # _eval_cond, _eval_crossover
    ├── window_ops.py    # holds_for, occurred_within, count_true
    ├── shift_ops.py     # _shift_expr, _shift_arithmetic
    ├── resolve.py       # _resolve_ref, _resolve_lhs
    └── setups.py        # _eval_setup_ref with caching
```

---

### rules/__init__.py
**Location**: `src/backtest/rules/__init__.py`
**Role**: Public API for rule compilation and evaluation

**Exports**:
- Types: `ReasonCode`, `ValueType`, `EvalResult`, `RefValue`
- Compilation: `CompiledRef`, `compile_ref`, `validate_ref_path`, `RefNamespace`
- Evaluation: `evaluate_condition`, `OPERATORS`
- Registry: `OperatorSpec`, `OpCategory`, `OPERATOR_REGISTRY`, `SUPPORTED_OPERATORS`

---

### rules/compile.py
**Location**: `src/backtest/rules/compile.py`
**Lines**: ~409
**Role**: Pre-compile references at normalization time for O(1) hot-loop resolution

**External Imports**:
- `dataclasses.dataclass`
- `enum.Enum, auto`
- `typing.Any`

**Internal Imports**:
- `.types`: RefValue, ReasonCode, ValueType

**Public API**:
- `RefNamespace` enum: PRICE, INDICATOR, STRUCTURE, LITERAL
- `CompiledRef` class: Pre-compiled reference with resolve()
- `compile_ref()`: Factory function
- `validate_ref_path()`: Path validation at compile time
- `compile_condition()`: Compile condition dict to CompiledRefs

**Key Design**:
- Paths parsed at normalization, not in hot loop
- O(1) resolution via snapshot.get()
- Fail-fast with actionable error messages

---

### rules/dsl_parser.py
**Location**: `src/backtest/rules/dsl_parser.py`
**Lines**: ~774
**Role**: Parse YAML into AST node types

**Internal Imports**:
- `.dsl_nodes`: Expr, Cond, AllExpr, AnyExpr, NotExpr, HoldsFor, etc.
- `.strategy_blocks`: Block, Case, Intent

**Public API**:
- `parse_expr()`: Parse expression dict/list to AST
- `parse_cond()`: Parse condition dict
- `parse_block()`: Parse block dict
- `parse_blocks()`: Parse list of blocks
- `parse_play_actions()`: High-level Play parsing

**Supports**:
- Boolean: all, any, not
- Window: holds_for, occurred_within, count_true
- Duration: holds_for_duration, occurred_within_duration, count_true_duration
- Arithmetic: [operand, op, operand] syntax
- Verbose and shorthand formats

---

### rules/dsl_nodes/__init__.py
**Role**: Re-exports all DSL node types

**Exports**:
- Constants: ARITHMETIC_OPERATORS, COMPARISON_OPERATORS, VALID_OPERATORS, etc.
- Value nodes: FeatureRef, ScalarValue, RangeValue, ListValue, ArithmeticExpr
- Condition: Cond
- Boolean: AllExpr, AnyExpr, NotExpr, SetupRef
- Window: HoldsFor, OccurredWithin, CountTrue + duration variants
- Type alias: Expr
- Utilities: get_max_offset, validate_expr_types, etc.

---

### rules/evaluation/__init__.py
**Role**: Re-exports evaluator

**Exports**:
- `ExprEvaluator`: Main evaluator class
- `evaluate_expression()`: Convenience function

**Submodules**:
- core.py: ExprEvaluator dispatch
- boolean_ops.py: AND/OR/NOT evaluation
- condition_ops.py: Comparison and crossover
- window_ops.py: Window operator evaluation
- shift_ops.py: Historical lookback shifting
- resolve.py: Value resolution
- setups.py: Setup reference caching

---

### rules/ Import Statistics

| Module | Internal Imports | External Imports | Lines |
|--------|-----------------|------------------|-------|
| compile.py | 1 module | 3 packages | ~409 |
| dsl_parser.py | 2 modules | 1 package | ~774 |
| dsl_nodes/__init__.py | 7 submodules | 0 packages | ~170 |
| evaluation/__init__.py | 1 submodule | 0 packages | ~28 |

### Key Observations (Phase 4)

1. **Clean modular structure**: Well-organized into dsl_nodes/ and evaluation/ subpackages
2. **Compile-time validation**: Paths validated at normalization, not hot loop
3. **Re-export shims**: dsl_eval.py and dsl_nodes.py provide backward compatibility
4. **Minimal external deps**: rules/ modules have very few external dependencies
5. **Frozen DSL**: v3.0.0 is frozen (2026-01-08) - operators, windows, syntax all stable
6. **Lazy imports**: compile.py lazily loads structure fields to avoid circular deps

---

## Phase 5: Supporting Modules

### incremental/ Directory
**Purpose**: O(1) per-bar market structure detection

**Directory Structure**:
```
incremental/
├── __init__.py          # Public API exports
├── primitives.py        # MonotonicDeque, RingBuffer
├── base.py              # BarData, BaseIncrementalDetector
├── registry.py          # STRUCTURE_REGISTRY, register_structure()
├── state.py             # TFIncrementalState, MultiTFIncrementalState
└── detectors/
    ├── swing.py         # IncrementalSwingDetector
    ├── fibonacci.py     # IncrementalFibonacci
    ├── trend.py         # IncrementalTrendDetector
    ├── zone.py          # IncrementalZoneDetector
    ├── derived_zone.py  # K-slot derived zones
    └── rolling_window.py # IncrementalRollingWindow
```

**Key Exports**:
- Primitives: `MonotonicDeque`, `RingBuffer`
- Base: `BarData`, `BaseIncrementalDetector`
- Registry: `STRUCTURE_REGISTRY`, `register_structure`, `list_structure_types`
- Detectors: `IncrementalSwingDetector`, `IncrementalFibonacci`, etc.
- State: `TFIncrementalState`, `MultiTFIncrementalState`

**Depends On**: minimal (mostly stdlib)
**Used By**: engine.py, bar_processor.py, snapshot_view.py

---

### play/ Directory
**Purpose**: Declarative strategy specification with Feature Registry

**Directory Structure**:
```
play/
├── __init__.py          # Re-exports
├── config_models.py     # FeeModel, AccountConfig, ExitMode
├── risk_model.py        # RiskModel, SizingRule, StopLossRule
└── play.py              # Play dataclass, load_play()
```

**Key Exports**:
- Config: `FeeModel`, `AccountConfig`, `ExitMode`
- Risk: `RiskModel`, `SizingRule`, `StopLossRule`, `TakeProfitRule`
- Play: `Play`, `load_play()`, `list_plays()`, `PositionPolicy`

**Depends On**: pathlib, YAML, dataclasses
**Used By**: engine_factory.py, runner.py, tools/backtest_tools.py

---

### artifacts/ Directory
**Purpose**: Lossless run recording for debugging and reproducibility

**Directory Structure**:
```
artifacts/
├── __init__.py          # Public API exports
├── manifest_writer.py   # run_manifest.json writer
├── eventlog_writer.py   # events.jsonl streamer
├── equity_writer.py     # equity_curve.csv export
├── parquet_writer.py    # Parquet format utilities
├── artifact_standards.py # STANDARD_FILES, validation
├── hashes.py            # Hash computation for determinism
├── determinism.py       # Determinism enforcement
└── pipeline_signature.py # Pipeline version tracking
```

**Key Exports**:
- Writers: `ManifestWriter`, `EventLogWriter`, `EquityWriter`
- Parquet: `write_parquet`, `read_parquet`
- Standards: `validate_artifacts`, `ArtifactPathConfig`, `STANDARD_FILES`
- Hashes: `compute_trades_hash`, `compute_equity_hash`, `compute_run_hash`

**Isolation Rule**: Only wired from tools/entrypoints, NOT from engine/sim/runtime

**Depends On**: json, pathlib, pyarrow
**Used By**: runner.py (only)

---

### gates/ Directory
**Purpose**: Production enforcement validators (read-only)

**Directory Structure**:
```
gates/
├── __init__.py                    # Public API exports
├── production_first_import_gate.py # Gate A: Production-first validation
├── indicator_requirements_gate.py  # Gate: Indicator validation
├── play_generator.py               # Generate synthetic Plays
└── batch_verification.py           # Run batch tests
```

**Key Exports**:
- Gate A: `run_production_first_gate`, `GateViolation`, `GateResult`
- Generator: `GeneratorConfig`, `GeneratedPlay`, `generate_plays`
- Batch: `PlayRunResult`, `BatchSummary`, `run_batch_verification`

**Depends On**: pathlib, yaml
**Used By**: runner.py, CLI

---

### types.py
**Location**: `src/backtest/types.py`
**Purpose**: Core type definitions for backtesting

**Defines**:
- `StopReason` enum: LIQUIDATED, EQUITY_FLOOR_HIT, STRATEGY_STARVED
- `Trade` dataclass: Complete trade record with MAE/MFE
- `EquityPoint` dataclass: Equity curve point
- `AccountCurvePoint` dataclass: Full margin state per bar
- `BacktestMetrics` dataclass: 62-field metrics
- `BacktestResult` dataclass: Complete backtest output

**Re-exports**: `Bar` from runtime/types.py

**Depends On**: runtime/types.py
**Used By**: Nearly all backtest modules

---

### indicator_registry.py
**Location**: `src/backtest/indicator_registry.py`
**Purpose**: Single source of truth for 43 supported indicators

**Defines**:
- `SUPPORTED_INDICATORS`: Dict of indicator metadata
- `IndicatorRegistry` class: Validation, warmup, multi-output expansion
- Warmup formulas per indicator type

**Key API**:
- `get_registry()`: Get singleton registry
- `is_supported(indicator_type)`: Check if indicator is supported
- `get_warmup_bars(indicator_type, params)`: Compute warmup
- `get_expanded_keys(indicator_type, output_key)`: Multi-output expansion

**Depends On**: rules/types.py
**Used By**: features/, engine_factory.py, play/

---

### feature_registry.py
**Location**: `src/backtest/feature_registry.py`
**Purpose**: Unified registry for all features (indicators + structures)

**Defines**:
- `FeatureType` enum: INDICATOR, STRUCTURE
- `InputSource` enum: CLOSE, OPEN, HIGH, LOW, VOLUME, etc.
- `Feature` dataclass: Single feature declaration
- `FeatureRegistry` class: Central registry for Play features

**Key API**:
- `get(feature_id)`: Get feature by ID
- `get_or_none(feature_id)`: Safe lookup
- `has(feature_id)`: Check existence
- `get_output_type(feature_id, field)`: Get output type for type checking

**Depends On**: indicator_registry.py, rules/types.py
**Used By**: snapshot_view.py, engine_factory.py, execution_validation.py

---

### Supporting Module Import Statistics

| Module | Internal Imports | External Imports | Files |
|--------|-----------------|------------------|-------|
| incremental/ | 2-3 modules | 3 packages | 12 files |
| play/ | 0 modules | 3 packages | 4 files |
| artifacts/ | 0 modules | 5 packages | 9 files |
| gates/ | 2-3 modules | 2 packages | 5 files |
| types.py | 1 module | 3 packages | 1 file |
| indicator_registry.py | 1 module | 3 packages | 1 file |
| feature_registry.py | 2 modules | 3 packages | 1 file |

### Key Observations (Phase 5)

1. **Clean isolation**: artifacts/ is isolated from engine/sim/runtime (correct separation)
2. **Registry pattern**: indicator_registry and feature_registry provide single source of truth
3. **Incremental state**: O(1) per-bar primitives enable live-compatible computation
4. **Play abstraction**: play/ provides clean declarative strategy specification
5. **Gates are read-only**: Validators scan and report, never modify
6. **Type re-exports**: types.py re-exports Bar from runtime for convenience

---

## Dependency Matrix

### Module Dependency Graph (Simplified)

```
                                 ┌─────────────────────────────────────┐
                                 │         EXTERNAL PACKAGES           │
                                 │  (numpy, pandas, pyarrow, yaml)    │
                                 └───────────────┬─────────────────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    │                            │                            │
                    ▼                            ▼                            ▼
          ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
          │  runtime/types  │         │    sim/types    │         │  rules/types    │
          │   (FOUNDATION)  │         │   (FOUNDATION)  │         │  (FOUNDATION)   │
          └────────┬────────┘         └────────┬────────┘         └────────┬────────┘
                   │                           │                           │
                   ├──────────────────────────┐│                           │
                   │                          ││                           │
                   ▼                          ▼▼                           ▼
          ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
          │ runtime/feed_   │         │  sim/exchange   │         │ rules/dsl_nodes │
          │     store       │         │  sim/ledger     │         │ rules/evaluation│
          └────────┬────────┘         └────────┬────────┘         └────────┬────────┘
                   │                           │                           │
                   ├───────────────────────────┼───────────────────────────┤
                   │                           │                           │
                   ▼                           ▼                           ▼
          ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
          │ runtime/snapshot│         │   incremental/  │         │  rules/compile  │
          │     _view       │         │      state      │         │  dsl_parser     │
          └────────┬────────┘         └────────┬────────┘         └────────┬────────┘
                   │                           │                           │
                   └───────────────────────────┼───────────────────────────┘
                                               │
                                               ▼
                              ┌────────────────────────────────────┐
                              │         ENGINE LAYER               │
                              │  bar_processor.py, engine.py       │
                              │  engine_factory.py, runner.py      │
                              └────────────────┬───────────────────┘
                                               │
                                               ▼
                              ┌────────────────────────────────────┐
                              │         ARTIFACTS LAYER            │
                              │    artifacts/, gates/ (isolated)   │
                              └────────────────────────────────────┘
```

### Afferent/Efferent Coupling Table

| Module | Afferent (Used By) | Efferent (Uses) | Instability |
|--------|-------------------|-----------------|-------------|
| runtime/types.py | 25+ | 0 | 0.00 (stable) |
| sim/types.py | 20+ | 2 | 0.09 (stable) |
| runtime/feed_store.py | 15+ | 2 | 0.12 (stable) |
| runtime/snapshot_view.py | 10+ | 5 | 0.33 (moderate) |
| sim/exchange.py | 5+ | 10 | 0.67 (moderate) |
| engine.py | 3 | 17 | 0.85 (unstable) |
| bar_processor.py | 1 | 9 | 0.90 (unstable) |
| runner.py | 1 | 10 | 0.91 (unstable) |

*Instability = Efferent / (Afferent + Efferent)*
*Lower = more stable (many depend on it), Higher = more unstable (depends on many)*

### Cross-Module Dependencies Summary

| From Module | To Module | Type |
|-------------|-----------|------|
| engine.py | runtime/* | Heavy |
| engine.py | sim/* | Heavy |
| engine.py | rules/* | Moderate |
| engine.py | core/risk_manager | Cross-domain |
| engine.py | data/historical_store | Cross-domain |
| bar_processor.py | runtime/* | Heavy |
| bar_processor.py | sim/* | Moderate |
| runner.py | artifacts/* | Moderate |
| runner.py | gates/* | Light |
| snapshot_view.py | feature_registry | Moderate |
| sim/exchange.py | sim/* internal | Heavy |
| dsl_parser.py | dsl_nodes/* | Heavy |

### Circular Dependency Locations

| Modules | Resolution |
|---------|------------|
| engine.py ↔ engine_factory.py | Dynamic imports in factory |
| compile.py ↔ market_structure | Lazy import in compile.py |
| feature_spec.py → indicator_registry | Deferred import in __post_init__ |

### Foundation Modules (0 Internal Dependencies)

These modules form the stable foundation layer:

1. `runtime/types.py` - Bar, RuntimeSnapshot, ExchangeState
2. `rules/dsl_nodes/constants.py` - Operator sets, limits
3. `incremental/primitives.py` - MonotonicDeque, RingBuffer

---

## Import Statistics (Phase 1)

| Module | Internal Imports | External Imports | Lines |
|--------|-----------------|------------------|-------|
| engine.py | 17 modules | 4 packages | ~1618 |
| runner.py | 10 modules | 5 packages | ~944 |
| engine_factory.py | 7 modules | 3 packages | ~503 |
| bar_processor.py | 9 modules | 2 packages | ~654 |

### Key Observations (Phase 1)

1. **engine.py is the hub**: It imports from 17 internal modules, making it the central dependency aggregator
2. **Circular dependency risk**: engine.py ↔ engine_factory.py (factory is imported by engine, factory imports engine)
3. **Heavy runtime/ dependency**: All 4 entry points depend on runtime/ submodule
4. **Cross-domain imports**: All entry points import from core.risk_manager and data.historical_data_store
5. **Dynamic imports**: engine_factory.py uses many dynamic imports to avoid circular dependencies
