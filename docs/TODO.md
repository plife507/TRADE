# TRADE TODO

Open work, bugs, and priorities. Completed work is in `memory/completed_work.md`.

---

## P0: Codebase Audit Cleanup (2026-04-04)

Full audit by 6 parallel agents across 349 files / ~127k lines. Findings below.

### Phase 1: Delete Dead Code (~9,200 lines)
- [x] Delete `src/utils/cli_display.py` (2,525 lines — zero imports, old display layer)
- [x] Delete `src/cli/smoke_tests/data.py` (590 lines — exported but never called)
- [x] Delete `src/cli/smoke_tests/orders.py` (603 lines — exported but never called, only sim_orders.py used)
- [x] Clean up `src/cli/smoke_tests/__init__.py` — remove dead exports
- [x] Delete `src/forge/audits/audit_fibonacci.py` (468 lines — superseded by audit_structure_parity.py)
- [x] Delete `src/forge/audits/audit_rolling_window.py` (401 lines — superseded by audit_structure_parity.py)
- [x] Delete `src/backtest/artifacts/equity_writer.py` (123 lines — runner uses write_parquet)
- [x] Delete `src/backtest/artifacts/manifest_writer.py` (150 lines — runner uses RunManifest.write_json)
- [x] Delete `src/backtest/artifacts/eventlog_writer.py` (284 lines — engine uses BacktestJournal)
- [x] Delete dead functions: `PlayEngine.restore_state()`, `_get_risk_policy()`, `_check_risk_policy()`
- [x] Delete `LiveDataProvider._load_bars_from_db()` (superseded by _for_tf version)
- [x] Delete `BacktestResult.metrics` compat shim (ALL FORWARD violation — consumers use metadata)
- [x] Delete `InstanceMode.SHADOW` enum value (never instantiated)
- [x] Delete `SimulatedExchange.cancel_pending_order()` (superseded by cancel_order_by_id)
- [x] Delete dead hash functions: `compute_input_hash_full()`, `verify_short_hash_derivation()`, `compute_artifact_file_hash()`
- [x] Delete `ManifestVerificationResult` class (defined but never instantiated)
- [x] Delete `build_features_from_play()`, `PlayFeatures`, `IndicatorCompute.list_custom_overrides()` (broken/dead)
- [x] Delete `market_close()` in exchange_orders_market.py (redundant with close_position)
- [x] Delete `set_position_mode()` in exchange_positions.py (redundant with switch_to_* methods)
- [x] Delete `_cleanup_completed_order()`, `wait_for_fill()` in order_executor.py
- [x] Delete `reset_application()`, `reset_global_risk_view()` (test utilities, no tests)
- [x] Delete 7 unused bybit_account methods: `upgrade_to_unified_account`, `get_mmp_state`, `set_mmp`, `reset_mmp`, `get_borrow_quota`, `repay_liability`, `batch_set_collateral_coin`
- [x] Delete `subscribe_orderbook()`, `subscribe_trades()` in bybit_websocket.py
- [x] Delete `ShadowEngineStats.duration_seconds` property (never accessed, hardcoded date)
- [x] Delete `docs/transcript.md` (empty file)
- [x] **GATE**: `python trade_cli.py validate quick` passes

### Phase 2: Fix ALL FORWARD Violations
- [x] Remove `BacktestConfig.from_dict()` account_fallback compat shim
- [x] Remove `DeployConfig.from_dict()` account_fallback compat shim
- [x] Clean up backward compat comment in `engine/factory.py:123` (fallback logic kept — legitimate default path)
- [x] Fix stale docstring in `sim/exchange.py` claiming "~200 LOC target" (1494 lines)
- [x] **GATE**: `python trade_cli.py validate quick` passes

### Phase 3: Fix Naming Issues
- [x] Rename `resolved_idea_path` → `resolved_play_path` in ResultsSummary + runner.py
- [x] Rename `portfolio_manager.PortfolioSnapshot` → `UTAPortfolioSnapshot` (collision with position_manager)
- [x] Unify duplicate `InputSource` enum (feature_registry.py vs feature_spec.py)
- [x] Delete stale `StructureType` enum (only had SWING/TREND, registry is canonical)
- [x] **GATE**: `python trade_cli.py validate quick` passes

### Phase 4: Fix Documentation (global count update)
- [x] Global find-replace: 44 indicators → 47, 7 structures → 13
- [x] Global find-replace: 170 synthetic plays → 229, 34 patterns → 38
- [x] Global find-replace: 84 indicator plays → 88, 14 structure plays → 26, 60 real-data → 61
- [x] Fix README.md — rewrite stale YAML example, fix counts, remove dead links
- [x] Fix ARCHITECTURE.md — M4 status, M5 status, remove demo refs, fix src/play/ path
- [x] Fix UTA_PORTFOLIO_SPEC.md — change "NOT STARTED" to "COMPLETE"
- [x] Fix MARKET_STRUCTURE_FEATURES.md — change from "plan" to "reference" (all ICT implemented)
- [x] Fix AGENT_READINESS_EVALUATION.md — update counts for M8/M9
- [x] Fix SYNTHETIC_DATA_REFERENCE.md — fix YAML key, add 4 ICT patterns, update count
- [x] Fix CLAUDE.md — coverage section updated to "13 types"
- [x] Fix P1 Phase 2 gate — updated to "229 synthetic plays"
- [x] Delete `docs/transcript.md` (empty file)
- [x] **GATE**: No doc references stale counts

### Phase 5: Register Missing Tools (28 unregistered)
- [x] Add specs for 15 trading/position/account tools (TPSL, margin, risk limits, collateral, exposure)
- [x] Add specs for 5 market data tools (ticker, orderbook, OI, instruments, market tests)
- [x] Add specs for 3 batch order tools
- [x] Add specs for 4 forge tools (stress test, synthetic data, parity) — new `forge_specs.py`
- [x] Add spec for `backtest_play_normalize_batch_tool`
- [x] **GATE**: 124/124 exported tools now have specs (was 96/124)

### Phase 6: Minor Cleanup
- [x] Fix `asyncio.get_event_loop()` → `asyncio.get_running_loop()` in shadow/daemon.py
- [x] Remove `from __future__ import annotations` from 18 files (unnecessary on 3.12+)
- [ ] Derive factory `_VALID_PARAMS` from registry (eliminate duplication) — deferred, low priority
- [ ] Fix shadow stubs: wire MAE/MFE from sim position, atr_pct from indicator cache — deferred, needs M6
- [x] Fix backtest-specialist agent "34 total" → "38 total" synthetic patterns header

---

## EX4: Safe Live Exchange Smoke Test

Order lifecycle validation against real Bybit API without risking money.
Limit orders placed 50% from market → never fill → full lifecycle test.

### Phase 1: Core Implementation
- [x] Create `src/cli/smoke_tests/exchange_orders.py` — order lifecycle + position lifecycle smoke tests
- [x] Update `src/cli/smoke_tests/__init__.py` — export new function
- [x] Add `_gate_exchange_order_lifecycle()` (EX4) to `src/cli/validate.py`
- [x] Wire EX4 into exchange tier gate list (between EX3 and EX5)
- [x] Add `"exchange-orders"` to module definitions
- [x] Add `--confirm` flag to validate subcommand in `src/cli/argparser.py`
- [x] Add PL5 gate for pre-live position test (gated on `--confirm`)
- [x] Sub-account isolation: `_get_smoke_manager()` uses dedicated `smoke_test` sub if available
- [ ] **GATE**: `python trade_cli.py validate exchange` — EX1-EX5 pass (EX4 may SKIP on low balance)
- [ ] Fund smoke sub-account and run full EX4 lifecycle test

---

## P0: UTA Critical Bug Fixes (2026-04-04)

Audit found 3 money-losing bugs, 6 safety gaps, 0 integration tests.

### Phase 1: Critical Bugs (blocks all live use)
- [x] Fix PlayDeployer cleanup — use funded `settle_coin` not `spec.settle_coin`
- [x] Add `--confirm` gate to `fund`, `withdraw`, `stop`, `rebalance` portfolio operations
- [x] Add `threading.RLock` to PlayDeployer `_deployments` dict
- [x] **GATE**: `python trade_cli.py validate module --module core` passes

### Phase 2: Multi-coin & Recovery (blocks multi-coin deployment)
- [x] Fix rebalance — use `SubAccountInfo.funded_coin` instead of hardcoded "USDT"
- [x] Handle PENDING transfer — optimistic accounting with sync_from_exchange reconciliation
- [x] Add "username already exists" recovery via `_find_existing_sub()`
- [x] Add max 20 sub-account pre-check before create
- [x] **GATE**: pyright clean on all modified files

### Phase 3: Production Hardening
- [x] Validate settle coin in deploy pre-flight (must be in LINEAR_SETTLE_COINS)
- [x] Improve recall_all with 1s wait + position close verification + WARNING on remaining
- [x] Log WARNING (not silent pass) on chmod failure for state file
- [x] PENDING transfers now persist optimistically (funds trackable after crash)
- [ ] Use InstrumentRegistry for settle coin inference instead of regex in get_positions — deferred

---

## Active Work

### T1: Warmup Parity Validation
- [ ] Add a validation check that runs each indicator to `is_ready()` and compares vs registry formula
- [ ] **GATE**: `python trade_cli.py validate module --module coverage` passes

### T2: Structure Health — Deferred Integration Tests
- [ ] Feed identical 500-bar candle sequence through both `FeedStore` (backtest) and `LiveIndicatorCache` (live), compare all structure outputs bar-by-bar
- [ ] Verify med_tf/high_tf structure update timing — `TFIndexManager` (backtest) vs buffer-length (live) produce updates on same bars

### T9: ICT Features — Remaining Items
- [ ] `STR_020_fvg_mitigation.yml` — FVG mitigation tracking validation play
- [ ] Full 5-state FVG/OB lifecycle (active -> first_touch -> partial_fill -> mitigated -> invalidated) + FVG touch_count

---

## P1: SimExchange Fidelity (SimExchange vs Bybit Parity)

Sim fidelity is the foundation — every backtest and shadow run depends on it.
Code investigation completed 2026-04-04. Items marked [x] already exist in code.

### Phase 1: Trigger Source Wiring (DSL → Order → Position)

The infrastructure exists (TriggerSource enum, fields on Order/Position, resolution
logic in IntrabarPath/check_tp_sl_1m). What's missing is the **config→runtime pipe**.

**Already implemented:**
- [x] `PriceModel.set_external_prices(mark, last, index)` — `pricing/price_model.py:63`
- [x] `TriggerSource` enum (LAST_PRICE, MARK_PRICE, INDEX_PRICE) — `sim/types.py:88`
- [x] `tp_trigger_by`, `sl_trigger_by` fields on `Order` — `sim/types.py:168-169`
- [x] `tp_trigger_by`, `sl_trigger_by` fields on `Position` — `sim/types.py:263-264`
- [x] `IntrabarPath.check_tp_sl()` respects trigger source — `pricing/intrabar_path.py:132`
- [x] `check_tp_sl_1m()` respects trigger source — `pricing/intrabar_path.py:265`
- [x] `OrderBook.check_triggers()` respects `trigger_by` — `sim/types.py:825`

**To implement:**

1. **Play DSL: parse `tp_trigger_by` / `sl_trigger_by` from risk section**
   - File: `src/backtest/play/play.py` — `_parse_risk_from_section()` ~line 1034
   - Add `tp_trigger_by` and `sl_trigger_by` string fields to `Play` dataclass (~line 433, beside `tp_order_type`)
   - Parse from `risk:` / `risk_model:` YAML section (same pattern as `tp_order_type`)
   - Validate values: must be `"LastPrice"`, `"MarkPrice"`, or `"IndexPrice"` (match `TriggerSource` enum)
   - Default: `"LastPrice"` (Bybit default, preserves existing behavior)
   - Serialize in `to_dict()` (~line 603, same pattern as `tp_order_type`)

2. **Engine: thread trigger source from Play → Order**
   - File: `src/engine/interfaces.py` — add `tp_trigger_by` and `sl_trigger_by` str fields to engine `Order` (~line 57)
   - File: `src/engine/play_engine.py` — `execute_signal()` ~line 632: set `order.tp_trigger_by = self.play.tp_trigger_by`
   - File: `src/engine/adapters/backtest.py` — `submit_order()` ~line 306: pass trigger source through to `SimulatedExchange.submit_order()`

3. **SimExchange: accept and propagate trigger source**
   - File: `src/backtest/sim/exchange.py` — `submit_order()` ~line 259: add `tp_trigger_by`/`sl_trigger_by` params, pass to `Order` constructor
   - File: `src/backtest/sim/exchange.py` — `submit_limit_order()` ~line 313: same treatment
   - File: `src/backtest/sim/exchange.py` — `_handle_entry_fill()` ~line 1035: copy `order.tp_trigger_by`/`sl_trigger_by` to Position (currently only copies `tp_order_type`/`sl_order_type`)

- [x] Step 1: Play DSL — parse and validate `tp_trigger_by` / `sl_trigger_by`
- [x] Step 2: Engine Order + PlayEngine — thread trigger source to order
- [x] Step 3: BacktestExchangeAdapter — pass trigger source to SimExchange
- [x] Step 4: SimExchange `submit_order`/`submit_limit_order` — accept trigger source params
- [x] Step 5: `_handle_entry_fill` — copy trigger source from Order → Position
- [x] **GATE**: `python3 trade_cli.py validate quick` passes
- [x] **GATE**: `V_RISK_010_trigger_source_mark.yml` runs with MarkPrice, pipeline roundtrips verified

### Phase 2: Split TP/SL (Multi-Level Exits)

Currently TP/SL are single `float | None` on Position. Bybit supports up to 5 TP/SL
levels with independent sizes. `_partial_close_position()` already works (exchange.py:1213).

**Already implemented:**
- [x] `_partial_close_position(exit_price, exit_time, reason, percent)` — `exchange.py:1213`
- [x] Partial close pro-rates: entry_fee, funding_pnl, position size — `exchange.py:1290-1294`
- [x] `OrderBook.amend_order()` can modify TP/SL on pending orders — `types.py:929`

**To implement:**

1. **`TpSlLevel` dataclass** in `sim/types.py`
   - Fields: `price: float`, `size_pct: float` (1-100), `trigger_by: TriggerSource`, `triggered: bool = False`
   - Sum of all level `size_pct` must equal 100
   - Single-level backward compat: `[TpSlLevel(price=X, size_pct=100)]` is equivalent to current `float`

2. **Replace Position.take_profit / stop_loss with level lists**
   - `Position.tp_levels: list[TpSlLevel]` and `Position.sl_levels: list[TpSlLevel]`
   - Add computed properties `Position.take_profit -> float | None` and `Position.stop_loss -> float | None` that return the first untriggered level's price (preserves all existing consumers)
   - Update `Position.to_dict()` to serialize levels

3. **RiskModel: multi-level take_profit**
   - File: `src/backtest/play/risk_model.py` — extend `TakeProfitRule` or create `TakeProfitLevel` list
   - Support both single value (current) and list of `{type, value, size_pct}` entries
   - `RiskModel.from_dict()` handles both forms

4. **DSL: split-TP YAML syntax**
   - File: `src/backtest/play/play.py` — parse list form in risk_model section
   - Single: `take_profit_pct: 3.0` (existing, unchanged)
   - Multi: `take_profit: [{pct: 2.0, size_pct: 50}, {pct: 4.0, size_pct: 50}]`
   - Validation: size_pct values must sum to 100

5. **Signal generation: compute multi-level TP prices**
   - File: `src/engine/execution_validation.py` — `_compute_sl_tp()` must produce a list of TP levels
   - Pass levels through `signal.metadata["tp_levels"]`

6. **Exchange: iterate TP levels in `_check_tp_sl_exits()`**
   - File: `src/backtest/sim/exchange.py` — `_check_tp_sl_exits()` ~line 621
   - Check each untriggered TP level; if hit, call `_partial_close_position(percent=level.size_pct)`
   - Mark level as `triggered = True`
   - Last level (or SL) does full `_close_position()`

7. **`modify_position_stops()` public API**
   - File: `src/backtest/sim/exchange.py` — new method
   - Accepts new TP/SL levels for the open position
   - Used by strategies that want to adjust stops mid-trade (beyond trailing/BE)

- [x] Step 1: `TpSlLevel` dataclass in `sim/types.py`
- [x] Step 2: Position — `tp_levels`/`sl_levels` lists + `next_tp_level()`, `sync_tp_sl_from_levels()`
- [x] Step 3: RiskModel — `TakeProfitLevel` + `take_profit_levels` on RiskModel
- [x] Step 4: Play DSL — parse `take_profit_levels: [{pct: X, size_pct: Y}, ...]`
- [x] Step 5: Signal generation — `_compute_sl_tp()` returns tp_levels, `_compute_tp_level_prices()` added
- [x] Step 6: `_handle_entry_fill` — builds TpSlLevel list from Order, adjusts for fill price gap
- [x] Step 7: `_check_tp_sl_exits()` — iterates levels, partial close per level, SL priority
- [x] Step 8: `modify_position_stops()` API on SimulatedExchange
- [x] **GATE**: `python3 trade_cli.py validate quick` passes
- [x] **GATE**: 229 synthetic plays — same results as before (pre-existing timeouts/bugs unchanged)
- [x] **GATE**: `V_RISK_011_split_tp_3_level.yml` — 567 trades, 1612 TP partial/full closes (multi-level working)

### Phase 3: Order Lifecycle Safety

Three independent fixes. No dependencies between them.

**Already implemented:**
- [x] `OrderBook.cancel_all(symbol)` — `sim/types.py:805`
- [x] `LiquidityModel` with `get_max_fillable()` — `execution/liquidity_model.py:46`
- [x] `LiquidityModel.would_be_partial_fill()` — `execution/liquidity_model.py:82`
- [x] Trailing stop: ATR + pct modes, activation threshold — `exchange.py:1351`
- [x] Break-even stop: one-time activation with offset — `exchange.py:1433`
- [x] IOC/FOK/PostOnly order semantics — `execution/execution_model.py:366-398`

**To implement:**

1. **closeOnTrigger: cancel competing orders on TP/SL fill**
   - File: `src/backtest/sim/exchange.py` — `_close_position()` ~line 1209
   - After `self.position = None` (line 1210), add `self._order_book.cancel_all(self.symbol)`
   - This cancels ghost TP orders after SL fill (and vice versa)
   - Same fix needed in `_partial_close_position()` — but only cancel if position fully closed
   - Also cancel pending orders on liquidation (in `_check_liquidation()`)

2. **Partial fills: fill-and-remainder instead of reject**
   - File: `src/backtest/sim/execution/execution_model.py` — where liquidity check rejects
   - Currently: if `fillable_usdt < order.size_usdt` → reject entire order
   - New behavior: fill `fillable_usdt`, remainder stays in order book as new order
   - Add `PARTIALLY_FILLED` to `OrderStatus` enum in `sim/types.py:47`
   - LiquidityModel already computes `get_unfilled_amount()` — use it
   - Wire `LiquidityConfig` from Play DSL or RiskProfileConfig (currently hardcoded disabled)

3. **Trailing stop: fixed distance mode (Bybit `trail_distance`)**
   - Currently: ATR-based (`atr_multiplier × ATR`) and percent-based (`trail_pct`)
   - Missing: fixed absolute distance in price units (Bybit: `trailingStop` parameter)
   - File: `src/backtest/play/risk_model.py` — add `trail_distance: float | None` to `TrailingConfig`
   - File: `src/backtest/sim/exchange.py` — `update_trailing_stop()` ~line 1351: add fixed distance branch
   - DSL: `trailing: {distance: 50.0, activation_pct: 1.0}` (50 USD fixed trail)

- [ ] Step 1: `_close_position()` — cancel all pending orders after position close
- [ ] Step 2: `_check_liquidation()` — cancel all pending orders after liquidation
- [ ] Step 3: Add `PARTIALLY_FILLED` to `OrderStatus` enum
- [ ] Step 4: Execution model — fill-and-remainder instead of reject when liquidity constrained
- [ ] Step 5: Wire `LiquidityConfig` from DSL/RiskProfileConfig (enable via `liquidity: {mode: volume_fraction}`)
- [ ] Step 6: `TrailingConfig` — add `trail_distance` field for fixed absolute trailing
- [ ] Step 7: `update_trailing_stop()` — add fixed distance branch
- [ ] Step 8: Play DSL — parse `trailing: {distance: X}` syntax
- [ ] **GATE**: `python3 trade_cli.py validate quick` passes
- [ ] **GATE**: `python3 trade_cli.py validate standard` passes

### Phase 4: DSL + Validation Restructure

After P1 Phases 1-3 are complete, restructure the DSL parser and validation system.
290 validation plays (82% of all plays) — many from previous DSL versions.

- [ ] Audit all 290 validation plays against current DSL spec — identify stale/broken
- [ ] Delete plays that test removed DSL features or use deprecated syntax
- [ ] Consolidate overlapping plays (88 indicator plays, 34 pattern plays)
- [ ] Rewrite remaining plays to use current `risk_model:` / `risk:` syntax cleanly
- [ ] Add new validation plays for Phase 1-3 features (trigger source, split TP, closeOnTrigger)
- [ ] Update validation gate counts in CLAUDE.md and docs
- [ ] **GATE**: `python3 trade_cli.py validate full` passes
- [ ] **GATE**: Total play count reduced by ≥30% with same or better coverage

---

## P2: Deprecate Demo Mode — COMPLETE (2026-04-03)

Demo mode fully removed. Pipeline is now: **backtest -> shadow -> live**.
Both shadow and live use the live Bybit API (`api.bybit.com`).
All `TradingMode`, `TRADING_MODE`, `BYBIT_USE_DEMO`, `BYBIT_DEMO_*` removed.

---

## M4: Shadow Exchange — Remaining Phases

Phases 1-4 complete (ShadowEngine, FeedHub, Orchestrator, PerformanceDB, Daemon).
See `docs/SHADOW_EXCHANGE_DESIGN.md` for full architecture.

### Phase 5: ShadowGraduator — Promotion Pipeline
- [ ] `ShadowGraduator`: computes graduation scores daily
- [ ] `config/shadow_graduation.yml`: default graduation thresholds
- [ ] CLI: `shadow graduation check --instance X`, `shadow graduation report --instance X`
- [ ] Manual promotion: `shadow graduation promote --instance X --confirm`
- [ ] **GATE**: Graduation scoring produces correct pass/fail for test scenarios

### Phase 6: M6 Integration Hooks
- [ ] Market context capture: record regime + metrics alongside every trade and snapshot
- [ ] `export_training_data(symbol, days)` -> DataFrame for M6 consumption
- [ ] Performance-by-regime analytics: per-play breakdown across 4 regime types
- [ ] **GATE**: Training data export covers 90 days, all required columns present

---

## M7: TradingView Parity Verification

See `docs/TV_PARITY_DESIGN.md` for full architecture.

### Phase 1: Infrastructure + Rolling Window + Swing
- [ ] Install tradingview-mcp, create `.mcp.json`, verify `tv` CLI works
- [ ] `bridge.py`, `ohlcv_alignment.py`, `comparison.py`, `runner.py`, `report.py`
- [ ] `rolling_window.pine`, `swing.pine`
- [ ] **GATE**: rolling_window + swing pass 95%+ match rate

### Phase 2-4: Remaining detectors
- [ ] trend, market_structure, zone, fibonacci, derived_zone, displacement, premium_discount
- [ ] FVG, order_block, liquidity_zones, breaker_block
- [ ] **GATE**: 13/13 detectors pass 95%+

---

## M8: UTA Portfolio Management — COMPLETE (2026-04-04)

Full UTA control. One manager, no fallbacks. Sub-account isolation per play.
See `docs/UTA_PORTFOLIO_SPEC.md` for spec. See `docs/UTA_PORTFOLIO_DESIGN.md` for API reference.

- [x] Phase 0: InstrumentRegistry (675 instruments, USDT+USDC+inverse)
- [x] Phase 1: SubAccountManager (programmatic sub lifecycle)
- [x] Phase 2: Exchange layer — all hardcoded USDT removed, LINEAR_SETTLE_COINS
- [x] Phase 3: PortfolioManager (parallel snapshot, pre-flight, recall-all)
- [x] Phase 4: 22 registered tools, all ToolResult, web-UI ready
- [x] Phase 5: PlayDeployer (sub-account → fund → LiveRunner pipeline)
- [x] Full E2E: pre-flight → create sub → fund → start runner → health → stop → cleanup
- [x] 6 code review cycles, pyright clean, orchestration audit passed

---

## M9: Shadow Unification + Play DSL Split — COMPLETE (2026-04-04)

One shadow path (daemon). Play DSL: `account` (shared) + `backtest` (sim) + `deploy` (live/shadow).

- [x] Phase 1: Factory shadow killed (ShadowExchange, ShadowRunner — 656 lines deleted)
- [x] Phase 2: BacktestConfig + DeployConfig models added to Play
- [x] Phase 3: Consumers wired (_build_config_from_play, ShadowEngine, PlayDeployer)
- [x] Phase 4: Dead fields removed (max_notional_usdt, max_margin_usdt), consumers migrated
- [x] Phase 5: Docs updated, critical ShadowEngine self-assignment bug fixed by audit
- [ ] Future: Remove `starting_equity_usdt`/`slippage_bps` from AccountConfig entirely (30+ refs in forge/validation)
- [ ] Future: Document `backtest:` and `deploy:` sections in `docs/PLAY_DSL_REFERENCE.md`

---

## Pre-Deployment (fix before live trading)

### T3: Live Blockers
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but doesn't force pybit reconnect
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering — needs integration test
- [ ] **H22** Sim accepts `funding_events` kwarg but no funding event generation pipeline exists yet

### T4: Live Engine Rubric
- [ ] Define live parity rubric: backtest results as gold standard
- [ ] Shadow mode 24h validation
- [ ] Verify sub-loop activation in live mode

### T5: Live Trading Integration
- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Shadow trading integration

### T6: Manual Verification (requires exchange connection)
- [ ] `shadow run --play AT_001` runs and Ctrl+C stops
- [ ] `play watch --json`, `play stop --all` work correctly
- [ ] Start -> stop -> cooldown -> restart timing works (15s)

---

## Accepted Behavior

| ID | Note |
|----|------|
| GAP-BD2 | `os._exit(0)` correct — pybit WS threads are non-daemon |

## Platform Issues

- **DuckDB file locking on Windows** — sequential scripts, `run_full_suite.py` has retry logic
- **Windows `os.replace` over open files** — `PermissionError` if another process is mid-read of instance JSON

## Known Issues (non-blocking)

- **pandas_ta `'H'` Deprecation Warning** — cosmetic, `pandas_ta.vwap()` passes `'H'` to `index.to_period()`. Our `IncrementalVWAP` is unaffected.
- **2 pre-existing pyright errors** — pandas Series type inference in `engine_feed_builder.py:367`

---
