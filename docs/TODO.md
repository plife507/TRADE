# TRADE TODO

Open work, bugs, and priorities. Completed work is in `memory/completed_work.md`.

---

## Active Work (backtest quality + new features)

### T1: Warmup Parity Validation
- [ ] Add a validation check that runs each indicator to `is_ready()` and compares vs registry formula
- [ ] **GATE**: `python trade_cli.py validate module --module coverage` passes

### T2: Structure Detection (known limitations)

Current detectors work but have documented limitations. See `docs/STRUCTURE_DETECTION_AUDIT.md`.

- [ ] `confirmation_close` default should be `True` — simple fix
- [ ] Trend detector `strength=2` never fires on real BTC data — needs investigation
- [ ] Trend/MS timing mismatch — document as architectural trade-off, not bug
- [ ] CHoCH should only break the BOS-producing swing level, not any prior swing

### T9: New Market Structure Features

See `docs/MARKET_STRUCTURE_FEATURES.md` for full specs.

#### Phase 1: Tier 1 — Core ICT Chain
- [ ] Displacement detector (`src/structures/detectors/displacement.py`)
- [ ] Fair Value Gap detector (`src/structures/detectors/fair_value_gap.py`)
- [ ] Order Block detector (`src/structures/detectors/order_block.py`)
- [ ] Liquidity Zones detector (`src/structures/detectors/liquidity_zones.py`)
- [ ] Registry entries (output types + warmup formulas) for all 4
- [ ] Validation plays for all 4
- [ ] Synthetic data patterns if needed (displacement_impulse, trending_with_gaps, etc.)
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: `python trade_cli.py validate module --module coverage` — no gaps

#### Phase 2: Tier 2 — M6 Intelligence
- [ ] Volume Profile / POC indicator
- [ ] Anchored Volume Profile indicator
- [ ] Premium/Discount zone detector
- [ ] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 3: Tier 3 — Refinements
- [ ] Breaker Blocks detector
- [ ] Session Highs/Lows indicator
- [ ] Mitigation tracking enhancement to FVG + OB
- [ ] **GATE**: `python trade_cli.py validate standard` passes

---

## P1: Shadow Exchange Order Fidelity (SimExchange vs Bybit Parity)

See `docs/SHADOW_ORDER_FIDELITY_REVIEW.md` for full analysis, code references, and Bybit API cross-reference.

**Context:** Shadow Exchange (M4) = SimulatedExchange + real WS feed. No live Bybit order API. The sim IS the exchange.

**14 features correct today:** Market/limit/stop fills, GTC/IOC/FOK/PostOnly, maker/taker fees, OCO, liquidation on mark, bankruptcy settlement, funding, reduce-only, break-even stop, order amendment, 1m granular TP/SL.

**4 HIGH gaps, 3 MEDIUM gaps identified.**

### Phase 1: Price Fidelity (H1 + H2)
- [ ] `PriceModel.set_external_prices(mark, last, index)` — shadow mode feeds real WS prices
- [ ] Add `TriggerSource` enum (`LAST_PRICE`, `MARK_PRICE`, `INDEX_PRICE`) to `types.py`
- [ ] Add `tp_trigger_by`, `sl_trigger_by` to `Position` and `Order` (default `LAST_PRICE`)
- [ ] `check_tp_sl()` / `check_tp_sl_1m()` compare against configured price source
- [ ] `OrderBook.check_triggers()` respects `trigger_by` on stop orders
- [ ] Add `tp_trigger_by`, `sl_trigger_by` to Play DSL risk_model
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: Validation plays for mark vs last trigger divergence

### Phase 2: Exit Fidelity (H3 + H4)
- [ ] New `TpSlLevel` dataclass: `price`, `size_pct`, `order_type`, `trigger_by`, `limit_price`, `triggered`
- [ ] Replace single `Position.take_profit`/`stop_loss` with `list[TpSlLevel]` (backward compat via computed properties)
- [ ] Wire `_check_tp_sl_exits()` to iterate levels, call `_partial_close_position()` for partials
- [ ] Add `modify_position_stops()` public API to `SimulatedExchange`
- [ ] DSL: split-TP syntax (`take_profit: [{level: 1.5, size_pct: 50}, ...]`)
- [ ] Engine adapter: modify-stops hook for strategy-driven TP/SL changes
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: Validation plays for split-TP (3-level exit, SL after partial TP, modify SL post-entry)
- [ ] **GATE**: Existing 170 synthetic plays still pass

### Phase 3: Safety & Polish (M1 + M2 + M3)
- [ ] `closeOnTrigger`: cancel competing orders to free margin when SL fires
- [ ] Partial fills: `PARTIALLY_FILLED` status, `LiquidityModel` depth estimation, IOC/FOK differentiation
- [ ] Trailing stop: absolute `activePrice` + fixed `trail_distance` alongside existing pct/ATR modes
- [ ] **GATE**: `python trade_cli.py validate standard` passes

---

## P0: Codebase Review Remediation (Safety-Critical Fixes)

### Phase 1: DuckDB Lock Eviction (P0 — prevents DB corruption) ✅
- [x] Skip age-based eviction when PID is alive (line 506-513 in `historical_data_store.py`)
- [x] Add mtime heartbeat refresh during long write operations
- [x] **GATE**: `python3 trade_cli.py validate quick` passes

### Phase 2: LiveRunner Queue Backpressure (P0 — prevents stale signal execution) ✅
- [x] Soft queue depth warning (threshold=5, logs when exceeded)
- [x] Add queue age tracking (monotonic timestamp when item enqueued)
- [x] Add circuit breaker: halt trading + trigger panic if queue age > 2× exec timeframe
- [x] Log queue depth + age metrics on each consumption
- [x] **GATE**: `python3 trade_cli.py validate quick` passes

### Phase 3: Risk Controls for Demo Mode (P1 — prevents unguarded demo runs) ✅
- [x] Extend PL4 pre-live validation gate to demo mode in `cli/subcommands/play.py`
- [x] Add max_drawdown_pct value validation (reject >= 100% as effectively disabled)
- [x] **GATE**: `python3 trade_cli.py validate quick` passes

### Phase 4: Dangerous Exception Handlers (P1 — stops silent failures in live path) ✅
- [x] `engine/adapters/live.py` — warm-up bar load: narrow to infrastructure errors, log at ERROR
- [x] `engine/adapters/live.py` — structure init: removed silent catches (now fails loud)
- [x] `engine/adapters/live.py` — added insufficient-warmup ERROR log when all tiers fail
- [x] `core/safety.py` — panic verification: narrowed to network errors, escalate on final failure
- [x] `data/historical_data_store.py` — DB close: log at ERROR with context
- [x] `engine/runners/live_runner.py` — drawdown check: added traceback in error log
- [x] `core/exchange_positions.py` — set_tp_sl: split network vs API error types in log
- [x] **GATE**: `python3 trade_cli.py validate quick` passes

### Phase 5: Artifact Atomicity (P2 — prevents corruption cascade)
- [x] Add `atomic_write_text()` and `atomic_write_bytes()` helpers in `utils/helpers.py`
- [x] Apply to `ResultsSummary.write_json()` (result.json)
- [x] Apply to `RunManifest.write_json()` (run_manifest.json)
- [x] Apply to `ManifestWriter.write()` (run_manifest.json)
- [x] Apply to `PipelineSignature.write_json()` (pipeline_signature.json)
- [x] Apply to `write_parquet()` (trades.parquet, equity.parquet) via temp + rename
- [x] Add `fcntl.flock()` file locking to `index.jsonl` appender
- [x] **GATE**: `python3 trade_cli.py validate quick` passes
- [x] **GATE**: `python3 scripts/run_full_suite.py` — 154/171 pass (17 pre-existing: 14 timeouts on WSL2, 1 VWAP deprecation, 1 numeric overflow, 1 cosmetic)

---

## Pre-Deployment (fix before live trading)

### T3: Live Blockers
- [x] **GAP-2** REST API fallback for warmup data — `_load_bars_from_rest_api()` in `live.py` (3-tier: buffer → DuckDB → REST)
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but doesn't force pybit reconnect. Passive detection + runner-level reconnect works, but no active force-reconnect.
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering — needs integration test.
- [ ] **H22** Sim accepts `funding_events` kwarg but no funding event generation pipeline exists yet.

### T4: Live Engine Rubric
- [ ] Define live parity rubric: backtest results as gold standard
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### T5: Live Trading Integration
- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration

### T6: Manual Verification (requires exchange connection)
- [ ] Run demo play 10+ minutes — NO "Signal execution blocked" warnings
- [ ] `play run --play AT_001 --mode demo --headless` prints JSON, Ctrl+C stops
- [ ] `play watch --json`, `play stop --all` work correctly
- [ ] Start → stop → cooldown → restart timing works (15s)

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

---

## Commands

### Validation

```bash
python trade_cli.py validate quick              # Pre-commit (~2min, 7 gates)
python trade_cli.py validate standard           # Pre-merge (~7min, 13 gates)
python trade_cli.py validate full               # Pre-release (~10min, 15 gates)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)
```

### Backtest

```bash
python trade_cli.py backtest run --play X --sync       # Single backtest (sync data first)
python trade_cli.py backtest run --play X --synthetic   # Single backtest (synthetic data)
python scripts/run_full_suite.py                        # 170-play synthetic suite
python scripts/run_real_verification.py                 # 60-play real verification
python scripts/verify_trade_math.py --play X            # Math verification for a play
```

### Debugging & Logging

```bash
# Verbosity flags (apply to ANY command)
python trade_cli.py -q ...                     # Quiet: WARNING only (CI, scripts)
python trade_cli.py -v ...                     # Verbose: signal traces, structure events
python trade_cli.py --debug ...                # Debug: full hash tracing, all internals

# Examples
python trade_cli.py -v backtest run --play X --synthetic   # See WHY signals fire
python trade_cli.py --debug backtest run --play X --sync   # Full hash trace per bar

# Debug subcommands (diagnostic tools)
python trade_cli.py debug math-parity --play X             # Real-data math audit
python trade_cli.py debug snapshot-plumbing --play X       # Snapshot field check
python trade_cli.py debug determinism --run-a A --run-b B  # Compare two runs
python trade_cli.py debug metrics                          # Financial calc audit

# All debug subcommands support --json for structured output
python trade_cli.py debug math-parity --play X --json
```

### Log Files

```bash
# Structured JSONL log (all runs)
tail -f logs/trade.jsonl                       # Live stream
cat logs/trade.jsonl | jq '.event'             # Events only

# Backtest event journal (per-run)
cat artifacts/<input_hash>/events.jsonl        # Fill and close events per trade
```
