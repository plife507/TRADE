# TRADE TODO

Open work, bugs, and priorities. Completed work is in `memory/completed_work.md`.

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

## P1: Shadow Exchange Order Fidelity (SimExchange vs Bybit Parity)

See `docs/SHADOW_ORDER_FIDELITY_REVIEW.md` for full analysis.
14 features correct today. 4 HIGH gaps, 3 MEDIUM gaps identified.

### Phase 1: Price Fidelity (H1 + H2)
- [ ] `PriceModel.set_external_prices(mark, last, index)` — shadow mode feeds real WS prices
- [ ] Add `TriggerSource` enum (`LAST_PRICE`, `MARK_PRICE`, `INDEX_PRICE`) to `types.py`
- [ ] Add `tp_trigger_by`, `sl_trigger_by` to `Position` and `Order` (default `LAST_PRICE`)
- [ ] `check_tp_sl()` / `check_tp_sl_1m()` compare against configured price source
- [ ] `OrderBook.check_triggers()` respects `trigger_by` on stop orders
- [ ] Add `tp_trigger_by`, `sl_trigger_by` to Play DSL risk_model
- [ ] **GATE**: `python trade_cli.py validate quick` passes

### Phase 2: Exit Fidelity (H3 + H4)
- [ ] New `TpSlLevel` dataclass: `price`, `size_pct`, `order_type`, `trigger_by`, `limit_price`, `triggered`
- [ ] Replace single `Position.take_profit`/`stop_loss` with `list[TpSlLevel]` (backward compat via computed properties)
- [ ] Wire `_check_tp_sl_exits()` to iterate levels, call `_partial_close_position()` for partials
- [ ] Add `modify_position_stops()` public API to `SimulatedExchange`
- [ ] DSL: split-TP syntax (`take_profit: [{level: 1.5, size_pct: 50}, ...]`)
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: Existing 170 synthetic plays still pass

### Phase 3: Safety & Polish (M1 + M2 + M3)
- [ ] `closeOnTrigger`: cancel competing orders to free margin when SL fires
- [ ] Partial fills: `PARTIALLY_FILLED` status, `LiquidityModel` depth estimation, IOC/FOK differentiation
- [ ] Trailing stop: absolute `activePrice` + fixed `trail_distance` alongside existing pct/ATR modes
- [ ] **GATE**: `python trade_cli.py validate standard` passes

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
