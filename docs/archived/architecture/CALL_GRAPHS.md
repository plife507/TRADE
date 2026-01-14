# Backtest Simulator Call Graphs

> Generated: 2026-01-11
> Purpose: Document function call chains and execution flow

## Overview

This document traces call chains through the backtest simulator, from entry points to leaf functions.

---

## Primary Execution Flow

```
[CLI/Tools] -> [Runner] -> [Engine Factory] -> [Engine] -> [Bar Processor] -> [Exchange]
                                                  |
                                                  v
                                          [Rules/Evaluation]
```

---

## Phase 1: Entry Point Call Chains

### From runner.py (Main Entry Point)

```
run_backtest_with_gates(config)
├── config.load_play()
│   └── load_play() [play.py]
│
├── [GATE 1: Preflight]
│   └── run_preflight_gate() [runtime/preflight.py]
│       ├── validate data availability
│       └── compute_warmup_requirements()
│
├── [GATE 2: Indicator Requirements]
│   └── validate_indicator_requirements() [gates/indicator_requirements_gate.py]
│
├── [RUN BACKTEST]
│   ├── create_engine_from_play() [engine_factory.py]
│   │   ├── Build SystemConfig from Play
│   │   ├── Build RiskProfileConfig
│   │   ├── Compute tf_mapping
│   │   └── BacktestEngine() constructor
│   │
│   └── run_engine_with_play() [engine_factory.py]
│       ├── PlaySignalEvaluator(play)
│       ├── engine.run(play_strategy)
│       └── Return PlayBacktestResult
│
├── [WRITE ARTIFACTS]
│   ├── write_parquet() [artifacts/parquet_writer.py]
│   ├── compute_results_summary()
│   └── create_pipeline_signature()
│
└── [GATE 3: Artifact Validation]
    └── validate_artifacts() [artifacts/artifact_standards.py]
```

### From engine.py (BacktestEngine.run())

```
BacktestEngine.run(strategy)
├── prepare_multi_tf_frames() OR prepare_backtest_frame()
│   └── prepare_backtest_frame_impl() [engine_data_prep.py]
│       ├── validate_usdt_pair()
│       ├── load_data_impl()
│       └── apply_feature_spec_indicators() [indicators.py]
│
├── _build_feed_stores()
│   └── build_feed_stores_impl() [engine_feed_builder.py]
│       ├── FeedStore.from_dataframe()
│       └── MultiTFFeedStore()
│   └── _build_structures()
│       └── build_structures_into_feed() [engine_feed_builder.py]
│   └── _build_quote_feed()
│       └── build_quote_feed_impl() [engine_feed_builder.py]
│   └── _build_market_data()
│       └── build_market_data_arrays_impl() [engine_feed_builder.py]
│
├── _build_incremental_state()
│   └── MultiTFIncrementalState() [incremental/state.py]
│
├── StateRationalizer() [rationalization.py]
│
├── SimulatedExchange() [sim/exchange.py]
│
├── BarProcessor(engine, strategy, run_start_time)
│
├── [MAIN BAR LOOP]
│   for i in range(num_bars):
│       ├── processor.build_bar(i)
│       │
│       ├── [WARMUP PERIOD]
│       │   └── processor.process_warmup_bar()
│       │
│       └── [TRADING PERIOD]
│           └── processor.process_trading_bar()
│               ├── _update_incremental_state()
│               ├── _process_exchange_bar()
│               ├── _check_stop_conditions()
│               ├── _build_snapshot_view()
│               ├── _evaluate_with_1m_subloop()
│               │   └── strategy(snapshot, params)
│               └── _process_signal()
│
└── _build_result()
    ├── compute_backtest_metrics() [metrics.py]
    └── _write_artifacts() [engine_artifacts.py]
```

### From engine_factory.py

```
create_engine_from_play(play, window_start, window_end, ...)
├── Validate play.account exists
├── Get symbol from play.symbol_universe
├── Get FeatureRegistry from play
├── _feature_to_spec() - Convert Features to FeatureSpecs
├── Extract capital/account params (fail loud if missing)
├── Build RiskProfileConfig
├── _compute_warmup_by_tf() - Warmup from registry
├── _blocks_require_history() - Check for crossover operators
├── Build tf_mapping from registry TFs
├── Create SystemConfig
└── BacktestEngine(..., feature_registry=registry)

run_engine_with_play(engine, play)
├── PlaySignalEvaluator(play) [execution_validation.py]
├── Define play_strategy(snapshot, params)
│   ├── evaluator.evaluate(snapshot, has_position, position_side)
│   └── Convert SignalDecision to Signal
├── engine.run(play_strategy)
└── Return PlayBacktestResult
```

### From bar_processor.py

```
BarProcessor.__init__(engine, strategy, run_start_time)
├── Cache engine attributes:
│   └── _exec_feed, _htf_feed, _mtf_feed, _quote_feed
│   └── _exchange, _config, _risk_profile
│   └── _incremental_state, _rationalizer, _history_manager

build_bar(i)
└── CanonicalBar from FeedStore arrays (O(1))

process_warmup_bar(i, bar, prev_bar, sim_start_idx)
├── debug_milestone()
├── _update_incremental_state()
├── _exchange.set_bar_context()
├── _process_exchange_bar()
├── engine.risk_manager.sync_equity()
├── engine._update_htf_mtf_indices()
├── _extract_features()
└── engine._update_history()

process_trading_bar(i, bar, prev_bar, sim_start_idx, equity_curve, account_curve)
├── debug_milestone()
├── _update_incremental_state()
│   ├── Build BarData from FeedStore
│   ├── incremental_state.update_exec(bar_data)
│   └── rationalizer.rationalize() [Layer 2]
├── _exchange.set_bar_context()
├── _process_exchange_bar()
│   └── _exchange.process_bar(bar, prev_bar, quote_feed, ...)
├── engine.risk_manager.sync_equity()
├── engine._update_htf_mtf_indices()
├── _update_htf_incremental_state()
├── _check_stop_conditions()
│   └── check_all_stop_conditions() [engine_stops.py]
├── [IF TERMINAL STOP]
│   └── _handle_terminal_stop()
├── engine._accumulate_1m_quotes()
├── engine._freeze_rollups()
├── engine._build_snapshot_view()
├── _assert_no_lookahead()
├── engine._evaluate_with_1m_subloop()
│   └── [1m SUB-LOOP]
│       ├── engine._build_snapshot_view() per 1m bar
│       └── strategy(snapshot, params) per 1m bar
├── engine._process_signal()
│   └── _exchange.submit_order()
├── _record_equity_point()
└── engine._update_history()
```

---

## Phase 2: sim/ Call Chains

### SimulatedExchange.process_bar()
```
SimulatedExchange.process_bar(bar, prev_bar, quote_feed, ...)
├── _update_price_snapshot(bar, quote_feed)
│   └── PriceModel.compute_prices(bar)
├── [IF has_position]
│   ├── _check_liquidation()
│   │   └── LiquidationModel.check_liquidation(position, price_snapshot)
│   └── [IF liquidated]
│       └── _execute_liquidation()
├── _process_pending_orders(bar, quote_feed)
│   ├── For each pending stop order:
│   │   └── _check_stop_trigger(order, bar)
│   │       └── ExecutionModel.check_stop_trigger()
│   └── For each triggered order:
│       └── _execute_order(order, bar)
├── _check_tp_sl_1m(bar, quote_feed)
│   └── IntrabarPath.check_tp_sl_1m(position, 1m_bars)
├── _apply_funding(bar)
│   └── FundingModel.apply_funding(position, funding_event)
└── _record_step_result()
    └── StepResult(fills, position, ledger_state, ...)
```

### Order Execution Flow
```
submit_order(side, size_usdt, stop_loss, take_profit, timestamp)
├── _validate_order_params()
├── Constraints.validate(size_usdt, price)
├── Create Order object
├── OrderBook.add(order)
├── [IF market order]
│   └── _execute_market_order()
│       ├── ExecutionModel.fill_market_order()
│       │   ├── SlippageModel.compute_slippage()
│       │   └── ImpactModel.compute_impact()
│       ├── Ledger.apply_entry_fee()
│       └── Update position
└── Return order_id
```

---

## Phase 3: runtime/ + features/ Call Chains

### RuntimeSnapshotView Resolution
```
snapshot.get(path)
├── _tokenize_path(path)  # Cached via LRU
│   └── Returns (namespace, tokens)
├── _dispatch_by_namespace(namespace, tokens)
│   ├── "price" -> _resolve_price(tokens)
│   │   └── Returns mark_price, last_price, close, etc.
│   ├── "indicator" -> _resolve_indicator(tokens)
│   │   └── Returns indicator value at current index
│   ├── "structure" -> _resolve_structure(tokens)
│   │   └── Returns incremental or FeedStore structure value
│   └── "feature" -> _resolve_feature(tokens)
│       └── FeatureRegistry.get(feature_id).get_value(field)
└── Return resolved value
```

### FeedStore Access Pattern
```
FeedStore.get_indicator(key, index)
├── indicators[key][index]  # O(1) numpy array access
└── Return float value

FeedStore.from_dataframe(df, ...)
├── Extract OHLCV to numpy arrays
├── Build ts_close_ms_to_idx mapping
└── Initialize indicators dict (empty)

FeedStore.from_dataframe_with_features(df, features, ...)
├── from_dataframe(df)
├── For each feature in features:
│   └── indicators[key] = feature_array
└── Return FeedStore with indicators
```

---

## Phase 4: rules/ Call Chains

### DSL Parsing Flow
```
parse_play_actions(play_dict)
├── Get "actions" or "blocks" key
├── parse_blocks(actions_data)
│   └── For each block:
│       └── parse_block(block_dict)
│           ├── parse_case(case_dict)
│           │   ├── parse_expr(when_dict) -> Expr AST
│           │   │   ├── [all] -> AllExpr(children)
│           │   │   ├── [any] -> AnyExpr(children)
│           │   │   ├── [not] -> NotExpr(child)
│           │   │   ├── [holds_for] -> HoldsFor(bars, expr)
│           │   │   └── [lhs/op/rhs] -> Cond(lhs, op, rhs)
│           │   └── parse_intent(emit_list) -> Intent
│           └── Return Case(when, emit)
└── Return list[Block]
```

### Expression Evaluation Flow
```
ExprEvaluator.evaluate(expr, snapshot)
├── _dispatch_by_type(expr)
│   ├── Cond -> _eval_cond(cond, snapshot)
│   │   ├── _resolve_lhs(cond.lhs, snapshot)
│   │   ├── _resolve_rhs(cond.rhs, snapshot)
│   │   └── _apply_operator(op, lhs_value, rhs_value)
│   ├── AllExpr -> _eval_all(expr, snapshot)
│   │   └── all(evaluate(child) for child in children)
│   ├── AnyExpr -> _eval_any(expr, snapshot)
│   │   └── any(evaluate(child) for child in children)
│   ├── HoldsFor -> _eval_holds_for(expr, snapshot)
│   │   └── For offset in range(bars):
│   │       └── evaluate(shifted_expr, snapshot)
│   └── SetupRef -> _eval_setup_ref(expr, snapshot)
│       └── Cached evaluation of referenced setup
└── Return bool
```

### Crossover Evaluation
```
_eval_crossover(cond, snapshot)  # cross_above, cross_below
├── curr_lhs = _resolve_lhs(lhs, snapshot, offset=0)
├── prev_lhs = _resolve_lhs(lhs, snapshot, offset=1)
├── curr_rhs = _resolve_rhs(rhs, snapshot, offset=0)
├── [cross_above]: prev_lhs <= curr_rhs AND curr_lhs > curr_rhs
└── [cross_below]: prev_lhs >= curr_rhs AND curr_lhs < curr_rhs
```

---

## Critical Paths

### Order Execution Path
```
engine._process_signal(signal, bar, snapshot)
├── [FLAT signal] exchange.submit_close(reason, percent)
├── [Position check] Skip if position exists
├── [Pending orders check] Skip if orders exist
├── risk_policy.check() - Apply risk filtering
├── risk_manager.size_order() - Compute size_usdt
├── [Min size check] Skip if < min_trade_usdt
└── exchange.submit_order(side, size_usdt, stop_loss, take_profit, timestamp)
```

### Signal Generation Path (Play-based)
```
play_strategy(snapshot, params)
├── snapshot.has_position, snapshot.position_side
├── evaluator.evaluate(snapshot, has_position, position_side)
│   └── PlaySignalEvaluator.evaluate() [execution_validation.py]
│       ├── Iterate blocks/actions
│       ├── Evaluate DSL conditions
│       └── Return SignalDecision
└── Convert to Signal (LONG/SHORT/FLAT)
```

### Risk Check Path
```
risk_policy.check(signal, equity, available_balance, ...)
└── RiskPolicy implementations [risk_policy.py]
    ├── NoRiskPolicy: Always allow
    └── RulesBasedRiskPolicy: Apply rule checks
```

---

## Hotloop Analysis

### Hot Loop Location
`engine.py` lines ~980-1003: Main bar loop

### Per-Bar Operations (Trading Period)
1. `processor.build_bar(i)` - O(1) array access
2. `processor.process_trading_bar()`:
   - `_update_incremental_state()` - O(1) per structure
   - `_process_exchange_bar()` - O(1m bars in exec bar)
   - `_check_stop_conditions()` - O(1)
   - `_build_snapshot_view()` - O(1)
   - `_evaluate_with_1m_subloop()` - O(1m bars in exec bar)
   - `_process_signal()` - O(1)
   - `_record_equity_point()` - O(1)

### Key Performance Characteristics
- **FeedStore**: Precomputed numpy arrays, O(1) access
- **RuntimeSnapshotView**: Read-only view, no DataFrame operations
- **Incremental State**: O(1) per-bar update, not O(n) recomputation
- **1m Sub-loop**: Iterates 1m bars within exec bar (e.g., 15 iterations for 15m exec TF)

---

## Key Observations (Phase 1)

1. **Two execution paths**:
   - `run_backtest_with_gates()` for gated execution with artifacts
   - `run_backtest()` for simple system_id-based runs

2. **Engine factory isolation**: `create_engine_from_play()` translates Play config to SystemConfig, isolating Play semantics from engine

3. **Bar processor extraction**: Trading logic cleanly separated from orchestration in engine.run()

4. **1m evaluation loop**: Strategy evaluates at 1m granularity within each exec bar, enabling precise entry timing

5. **Layered state updates**:
   - Layer 1: Incremental structures (swing, zone, etc.)
   - Layer 2: Rationalization (transitions, derived state)
