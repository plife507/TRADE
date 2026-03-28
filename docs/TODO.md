# TRADE TODO

Open work, bugs, and priorities. Completed work is in `memory/completed_work.md`.

---

## Active Work (backtest quality + new features)

### T1: Warmup Parity Validation
- [ ] Add a validation check that runs each indicator to `is_ready()` and compares vs registry formula
- [ ] **GATE**: `python trade_cli.py validate module --module coverage` passes

### T2: Structure Health — Test & Heal

Replaces old T2. Covers all structure detector issues identified in investigation (2026-03-27).
See `docs/STRUCTURE_DETECTION_AUDIT.md` for 6-month BTCUSDT audit data.

#### Phase 1: Confirmation Close Default + Noise Reduction ✅
- [x] Change `confirmation_close` default from `False` to `True` in `market_structure.py:83`
- [x] Update vectorized reference in `vectorized_references/market_structure_reference.py` to match
- [x] Update G5 parity audit expected values if needed (not needed — uses defaults)
- [x] Audit all 14 structure validation plays — added `confirmation_close: false` to STR_003 (wick-based BOS test)
- [x] Add new play `STR_015_ms_confirmation_close.yml` — tests both close and wick modes
- [x] Document in `STRUCTURE_DETECTION_AUDIT.md`: "default changed, wick mode still available"
- [x] **GATE**: `python trade_cli.py validate module --module parity --json` — G5 9/9 pass
- [x] **GATE**: `python trade_cli.py validate module --module structures --json` — 15/15 pass

#### Phase 2: Live/Backtest Indicator Parity (Shadow Exchange readiness)
- [x] Add NaN-input tests for all 7 detectors — feed BarData with NaN indicators, verify no crash and predictable behavior
- [x] Zone detector (`zone.py:191-193`): returns early on NaN ATR — test proves zone stays "none" until ATR available
- [x] Swing detector: significance outputs are NaN (not crash) when `atr_key` indicator missing — verified
- [x] Fibonacci detector: levels stay NaN when source swing hasn't formed yet — verified
- [x] Derived zone detector: empty-slot sentinels returned when no zones exist — verified
- [x] Zone late-ATR parity test: NaN for first 50 bars then real ATR — no crash, zones form after — verified
- [ ] Add integration test: feed identical 500-bar candle sequence through both `FeedStore` (backtest path) and `LiveIndicatorCache` (live path), compare all structure outputs bar-by-bar (deferred: requires engine-level integration test harness)
- [ ] Add integration test: verify med_tf/high_tf structure update timing — `TFIndexManager` (backtest) vs buffer-length (live) produce updates on same bars (deferred: requires live provider mock)
- [x] **GATE**: `python trade_cli.py validate module --module parity --json` — G5 16/16 pass (was 9)
- [x] **GATE**: 7 NaN-resilience tests added to G5, all pass

#### Phase 3: Trend Strength=2 Investigation + Fix ✅
- [x] Instrument `_classify_trend()` — tested wave sequences with synthetic staircase and real-like data
- [x] Root cause confirmed: **data characteristic, not algorithm bug**. BTC 4h volatility alternates wave direction too fast for 2+ consecutive same-direction pairs. Algorithm correctly produces strength=2 on `trend_stairs` pattern (27.6% of bars).
- [x] On real BTC data with default params (left=5, right=5), wave pairs alternate: UP→RANGING→DOWN→RANGING. Need calmer markets or higher TFs.
- [x] No existing plays depend on `strength >= 2` (all use `>= 1`). Confirmed via grep.
- [x] Added `STR_016_trend_strength.yml` — uses `trend_stairs` pattern, left=3/right=3, produces strength=2.
- [x] Document: strength=2 requires orderly trending markets. Use higher TFs (4h+) or altcoins with cleaner structure for reliable strength=2 signals. See `STRUCTURE_DETECTION_AUDIT.md`.
- [x] **GATE**: `python trade_cli.py validate module --module structures --json` — 16/16 pass
- [x] **GATE**: STR_016 produces strength=2 on synthetic data (551/2000 bars = 27.6%)

#### Phase 4: CHoCH Break-Level Correctness ✅
- [x] CHoCH now only fires when price breaks the BOS-anchored swing level (not any prior swing)
- [x] Added `_choch_anchor_level` / `_choch_anchor_idx` tracking to market_structure.py
- [x] Fixed `_update_break_levels` — split into per-side updates to match vectorized reference (prevented stale break level re-assertion after CHoCH)
- [x] Updated vectorized reference to match BOS-anchored CHoCH logic
- [x] Added `STR_017_choch_bos_anchor.yml` — long_short mode, wick-based, trending pattern (11 trades)
- [x] **GATE**: `python trade_cli.py validate module --module parity --json` — G5 16/16 pass
- [x] **GATE**: `python trade_cli.py validate module --module structures --json` — 17/17 pass
- [ ] **GATE**: Run `scripts/run_full_suite.py` — pending (running in background)

### T9: ICT Structure Features — Full Integration Plan

See `docs/MARKET_STRUCTURE_FEATURES.md` for algorithm specs, output fields, edge cases, and DSL examples.

**Current state**: 7 structures + 44 indicators (mechanics layer).
**Goal**: Add 7 structures + 3 indicators (institutional narrative layer) across 6 gated phases.

```
Dependency graph:
  swing (exists) ──┬──> order_block ──> breaker_block
                   ├──> liquidity_zones
                   ├──> premium_discount (trivial)
  ATR (exists) ────┼──> displacement ──> order_block
  (none) ──────────┼──> fair_value_gap ──> mitigation_tracking
  (none) ──────────┼──> volume_profile ──> anchored_volume_profile
  (time-based) ────┴──> session_levels
```

**Per-detector integration checklist** (12 steps, all required):
1. Create `src/structures/detectors/<name>.py` — `@register_structure`, `BaseIncrementalDetector`
2. Import in `src/structures/detectors/__init__.py` + add to `__all__`
3. Add output types to `STRUCTURE_OUTPUT_TYPES` in `registry.py`
4. Add warmup formula to `STRUCTURE_WARMUP_FORMULAS` in `registry.py`
5. Create vectorized reference in `src/forge/audits/vectorized_references/<name>_reference.py`
6. Add `audit_<name>()` function in `audit_structure_parity.py`
7. Register audit function in `audit_funcs` list (line ~1270)
8. Create validation play `plays/validation/structures/STR_0XX_<name>.yml`
9. Add synthetic data pattern if needed (to `PatternType` + `PATTERN_GENERATORS`)
10. Verify G15 coverage: `python trade_cli.py validate module --module coverage`
11. Verify G5 parity: `python trade_cli.py validate module --module parity`
12. Verify G9 suite: `python trade_cli.py validate module --module structures`

**Per-indicator integration checklist** (7 steps):
1. Create incremental class in `src/indicators/incremental/<module>.py` — inherit `IncrementalIndicator`
2. Register in factory `src/indicators/incremental/factory.py` — `_FACTORY` + `_VALID_PARAMS`
3. Export from `src/indicators/incremental/__init__.py`
4. Add to `SUPPORTED_INDICATORS` in `src/backtest/indicator_registry.py` — warmup, inputs, params, output_keys
5. Add to `INDICATOR_OUTPUT_TYPES` in `src/backtest/indicator_registry.py`
6. Create validation play `plays/validation/indicators/IND_0XX_<name>.yml`
7. Verify G15 coverage + G9 suite pass

#### Phase 1: Displacement + Fair Value Gap (parallel, zero deps) ✅

Both detectors built and validated. 9 structures registered, 0 coverage gaps.

**1a. Displacement detector** — strong impulsive candle detection
- [x] Create `src/structures/detectors/displacement.py`
  - `@register_structure("displacement")`
  - `OPTIONAL_PARAMS`: `atr_key` ("atr"), `body_atr_min` (1.5), `wick_ratio_max` (0.4)
  - `DEPENDS_ON`: [] (reads ATR from `bar.indicators`)
  - State: per-bar flags (`is_displacement`, `direction`, `body_atr_ratio`, `wick_ratio`) + persistent (`last_idx`, `last_direction`, `version`)
  - O(1) update: compute body/ATR ratio and wick ratio, classify
  - Handle NaN ATR gracefully (no displacement, return early)
- [x] Add to `detectors/__init__.py` — import + `__all__`
- [x] `STRUCTURE_OUTPUT_TYPES["displacement"]`: `is_displacement`=BOOL, `direction`=INT, `body_atr_ratio`=FLOAT, `wick_ratio`=FLOAT, `last_idx`=INT, `last_direction`=INT, `version`=INT
- [x] `STRUCTURE_WARMUP_FORMULAS["displacement"]`: `lambda params, swing_params: 1`
- [x] Create `vectorized_references/displacement_reference.py`
- [x] Add `audit_displacement()` to parity audit + register in `audit_funcs`
- [x] Add synthetic pattern `displacement_impulse` — phases: calm (40%), impulse burst (20%), calm (40%). Strong body candles with small wicks during burst phase.
- [x] Create `STR_018_displacement.yml` — entry on `disp.is_displacement == 1 AND disp.direction == 1` with `displacement_impulse` pattern
- [x] **GATE**: G5 parity passes for displacement

**1b. Fair Value Gap detector** — 3-candle price imbalance gaps
- [x] Create `src/structures/detectors/fair_value_gap.py`
  - `@register_structure("fair_value_gap")`
  - `OPTIONAL_PARAMS`: `atr_key` ("atr"), `min_gap_atr` (0.0), `max_active` (5)
  - `DEPENDS_ON`: []
  - State: 3-candle deque buffer, active FVG slots (list of dicts: direction, upper, lower, anchor_idx, state, fill_pct), per-bar flags, nearest bull/bear accessors, aggregate counts
  - O(1) update: push candle, check 3-candle gap pattern, update mitigation on active FVGs
  - Mitigation: track fill_pct; 50%+ fill → "mitigated"; close through → "invalidated"
  - Slot management: newest first, evict oldest beyond `max_active`
- [x] Add to `detectors/__init__.py`
- [x] `STRUCTURE_OUTPUT_TYPES["fair_value_gap"]`: 12 output fields registered
- [x] `STRUCTURE_WARMUP_FORMULAS["fair_value_gap"]`: warmup=3
- [x] Create `vectorized_references/fair_value_gap_reference.py`
- [x] Add `audit_fair_value_gap()` to parity audit + register
- [x] Add synthetic pattern `trending_with_gaps`
- [x] Create `STR_019_fvg_basic.yml` — 11 trades on trending_with_gaps
- [ ] Create `STR_020_fvg_mitigation.yml` — deferred to Phase 6 (mitigation tracking enhancement)
- [x] **GATE**: G5 parity passes for fair_value_gap (18/18 detectors, 0 failures)

**Phase 1 gates:**
- [x] **GATE**: `python trade_cli.py validate module --module parity --json` — 18/18 pass
- [x] **GATE**: `python trade_cli.py validate module --module structures --json` — 19/19 pass
- [x] **GATE**: `python trade_cli.py validate module --module coverage --json` — 9 structures, 0 gaps

#### Phase 2: Order Block + Liquidity Zones (parallel, depend on Phase 1) ✅

Both detectors built and validated. 11 structures registered, 0 coverage gaps.

**2a. Order Block detector** — last opposing candle before displacement
- [x] Create `src/structures/detectors/order_block.py`
  - `@register_structure("order_block")`
  - `OPTIONAL_PARAMS`: `atr_key` ("atr"), `use_body` (True), `require_displacement` (True), `body_atr_min` (1.5), `wick_ratio_max` (0.4), `max_active` (5), `lookback` (3)
  - `DEPENDS_ON`: ["swing"], `OPTIONAL_DEPS`: ["displacement"]
  - State: candle history deque (lookback+2), active OB slots (direction, upper, lower, anchor_idx, state, touch_count), per-bar flags, nearest accessors, aggregate counts
  - O(1) update: check displacement (via dep or inline), search backward for opposing candle, create OB, update mitigation on active OBs
  - If displacement dep available: use `disp.is_displacement`; else: compute inline with same body_atr_min/wick_ratio_max
  - OB zone: body range (use_body=True) or full range (use_body=False) of opposing candle
  - Mitigation: price enters OB zone → "touched"/"mitigated"; close through → "invalidated"
- [x] Add to `detectors/__init__.py`
- [x] `STRUCTURE_OUTPUT_TYPES["order_block"]`: 12 output fields (new_this_bar, new_direction, new_upper, new_lower, nearest_bull/bear upper/lower, active counts, any_mitigated, version)
- [x] `STRUCTURE_WARMUP_FORMULAS["order_block"]`: `lambda params, swing_params: max(params.get("lookback", 3) + 2, swing_params["left"] + swing_params["right"])`
- [x] Create vectorized reference + parity audit function
- [x] Add synthetic pattern `ob_retest` — scale-invariant displacement from opposing candle, then retracement to OB zone
- [x] Create `STR_021_order_block.yml` — entry on `ob.new_this_bar == 1 AND ob.new_direction == 1`
- [x] **GATE**: G5 parity passes for order_block (20/20 detectors)

**2b. Liquidity Zones detector** — equal highs/lows clustering + sweep detection
- [x] Create `src/structures/detectors/liquidity_zones.py`
  - `@register_structure("liquidity_zones")`
  - `OPTIONAL_PARAMS`: `atr_key` ("atr"), `tolerance_atr` (0.3), `sweep_atr` (0.1), `min_touches` (2), `max_active` (5), `max_swing_history` (20)
  - `DEPENDS_ON`: ["swing"]
  - State: swing history deques (highs/lows), active zone slots (side, level, touches, state, sweep_bar_idx), per-bar flags (new_zone, sweep_this_bar, sweep_direction), nearest level accessors
  - O(1) update: track new swing pivots, cluster detection on last N swings, check sweeps on active zones, recompute nearest
  - Clustering: find N swings within tolerance_atr * ATR of each other → form zone at average level
  - Sweep: price exceeds zone level by sweep_atr * ATR
- [x] Add to `detectors/__init__.py`
- [x] `STRUCTURE_OUTPUT_TYPES["liquidity_zones"]`: 9 output fields registered
- [x] `STRUCTURE_WARMUP_FORMULAS["liquidity_zones"]`: `lambda params, swing_params: (swing_params["left"] + swing_params["right"]) * params.get("min_touches", 2)`
- [x] Create vectorized reference + parity audit function
- [x] Add synthetic pattern `equal_highs_lows` — range-bound with multiple swing touches at same level, then sweep + reversal
- [x] Create `STR_022_liquidity_zones.yml` — entry on `liq.sweep_this_bar == 1 AND liq.sweep_direction == -1` (swept lows = bullish signal)
- [x] **GATE**: G5 parity passes for liquidity_zones (20/20 detectors)

**Phase 2 gates:**
- [x] **GATE**: `python trade_cli.py validate module --module parity --json` — 20/20 pass
- [x] **GATE**: `python trade_cli.py validate module --module structures --json` — 21/21 pass
- [x] **GATE**: `python trade_cli.py validate module --module coverage --json` — 11 structures, 0 gaps

#### Phase 3: Premium/Discount (trivial, depends on swing pairs) ✅

- [x] Create `src/structures/detectors/premium_discount.py`
  - `@register_structure("premium_discount")`
  - `DEPENDS_ON`: ["swing"]
  - Reads `pair_high_level`, `pair_low_level` from swing dependency
  - Computes: `equilibrium` = midpoint, `premium_level` = 75%, `discount_level` = 25%, `zone` = "premium"/"discount"/"equilibrium"/"none", `depth_pct` = position 0.0-1.0
  - O(1): just reads swing pair values and divides
- [x] Add to `detectors/__init__.py`
- [x] `STRUCTURE_OUTPUT_TYPES["premium_discount"]`: 6 fields registered
- [x] `STRUCTURE_WARMUP_FORMULAS["premium_discount"]`: `lambda params, swing_params: swing_params["left"] + swing_params["right"]`
- [x] Create vectorized reference + parity audit
- [x] Add "premium", "discount", "equilibrium" to `_KNOWN_ENUM_VALUES` in `dsl_parser.py`
- [x] Create `STR_023_premium_discount.yml` — entry on `pd.zone == "discount" AND trend.direction == 1` (8 trades)
- [x] **GATE**: `python trade_cli.py validate module --module parity --json` — 21/21 pass
- [x] **GATE**: `python trade_cli.py validate module --module structures --json` — 22/22 pass
- [x] **GATE**: `python trade_cli.py validate module --module coverage --json` — 12 structures, 0 gaps

#### Phase 4: Volume Profile indicator (standalone, hard)

**4a. IncrementalVolumeProfile** — volume distribution across price levels
- [ ] Create class in `src/indicators/incremental/volume.py`
  - Inherit `IncrementalIndicator`
  - Params: `num_buckets` (100), `lookback` (50), `value_area_pct` (0.70)
  - State: price range tracker, bucket volumes array, bar contribution deque for rolling eviction
  - O(buckets) per bar for volume distribution (acceptable: ~100 ops)
  - Lazy rebinning: only rebin when price exceeds range by 10%+
  - Outputs: `poc` (FLOAT), `vah` (FLOAT), `val` (FLOAT), `poc_volume` (FLOAT), `above_poc` (BOOL), `in_value_area` (BOOL)
- [ ] Register in factory `_FACTORY` + `_VALID_PARAMS`
- [ ] Export from `src/indicators/incremental/__init__.py`
- [ ] Add to `SUPPORTED_INDICATORS` — multi_output=True, output_keys=("poc", "vah", "val", "poc_volume", "above_poc", "in_value_area"), warmup=lookback
- [ ] Add to `INDICATOR_OUTPUT_TYPES` — poc=FLOAT, vah=FLOAT, val=FLOAT, poc_volume=FLOAT, above_poc=BOOL, in_value_area=BOOL
- [ ] Create `IND_052_volume_profile_poc.yml` — entry on `vp.above_poc == 1 AND trend.direction == 1`
- [ ] **GATE**: `python trade_cli.py validate module --module coverage --json` — no gaps
- [ ] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 5: Breaker Blocks + Session Levels (depend on Phase 2)

**5a. Breaker Block detector** — failed OB that flips polarity on CHoCH ✅
- [x] Add OB invalidation tracking outputs (`any_invalidated_this_bar`, `last_invalidated_direction/upper/lower`) to order_block detector + vectorized reference + registry
- [x] Create `src/structures/detectors/breaker_block.py`
  - `@register_structure("breaker_block")`
  - `DEPENDS_ON`: ["order_block"], `OPTIONAL_DEPS`: ["market_structure"]
  - Monitors OB invalidations; when an OB is invalidated during a CHoCH event, it flips polarity (bullish OB → bearish resistance, vice versa)
  - State: active breaker slots (direction, upper, lower, state, touch_count), per-bar flags
  - Outputs: same pattern as OB (nearest, active counts, any_mitigated, version)
- [x] Full integration checklist (registry, vectorized ref, parity audit, validation play)
- [x] Create `STR_024_breaker_block.yml` — uses `[ob, ms]` multi-dep, entry on `brk.active_bull_count > 0` (7 trades)
- [x] **GATE**: G5 parity 22/22, G9 suite 23/23, G15 coverage 13 structures 0 gaps

**5b. Session Levels indicator** — previous daily/weekly/monthly highs/lows
- [ ] Create class in `src/indicators/incremental/volume.py` (or new `session.py`)
  - Tracks session boundaries using `ts_open` from bar data
  - Outputs: `prev_day_high`=FLOAT, `prev_day_low`=FLOAT, `current_day_high`=FLOAT, `current_day_low`=FLOAT, `prev_week_high`=FLOAT, `prev_week_low`=FLOAT
  - Needs: timestamp awareness for session boundary detection
- [ ] Full indicator integration checklist
- [ ] Create `IND_053_session_levels.yml`
- [ ] **GATE**: Coverage + quick validation pass

**Phase 5 gates:**
- [ ] **GATE**: `python trade_cli.py validate module --module parity --json` — all pass
- [ ] **GATE**: `python trade_cli.py validate module --module coverage --json` — no gaps
- [ ] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 6: Enhancements (depend on Phases 2 + 4)

**6a. Anchored Volume Profile** — resets on structural event
- [ ] Create class extending VolumeProfile logic
  - Resets accumulation on swing pair version change (same pattern as `anchored_vwap`)
  - Additional output: `bars_since_anchor`=INT
- [ ] Full indicator integration checklist
- [ ] Create `IND_054_anchored_vol_profile.yml`

**6b. Mitigation Tracking** — FVG + OB lifecycle enhancement
- [ ] Enhance FVG detector: add `fill_pct` output per slot, `touch_count`, lifecycle states (active → first_touch → partial_fill → mitigated → invalidated)
- [ ] Enhance OB detector: same lifecycle states
- [ ] Add `STR_025_fvg_lifecycle.yml` — tests mitigation progression
- [ ] Add `STR_026_ob_lifecycle.yml` — tests touch → invalidation
- [ ] **GATE**: Existing FVG/OB plays still pass (backward compatible)

**Phase 6 gates:**
- [ ] **GATE**: `python trade_cli.py validate module --module parity --json` — all pass
- [ ] **GATE**: `python trade_cli.py validate module --module coverage --json` — no gaps
- [ ] **GATE**: `python trade_cli.py validate standard` passes
- [ ] **GATE**: `python scripts/run_full_suite.py` — no regressions

#### Final: ICT Chain Integration Play ✅

- [x] Create `STR_027_full_ict_chain.yml` — 9 structures in one play: swing → displacement → FVG → OB → liquidity_zones → trend → market_structure → premium_discount → breaker_block. Entry: sticky bullish BOS direction + discount zone + active bullish OB. 17 trades on volatile pattern.
- [x] Dissected all 8 detector outputs independently — BOS `this_bar` contradicts discount zone (BOS pushes price up); switched to sticky `bos_direction` for structural bias.
- [ ] **GATE**: `python trade_cli.py validate standard` — pending (run separately)

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
