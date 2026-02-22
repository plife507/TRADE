# TRADE TODO

Single source of truth for all open work, bugs, and task progress.

---

## Completed Work

| Item | Date | Summary |
|------|------|---------|
| Liquidation Parity (Bybit) | 2026-02 | Full parity review |
| Fast Parallel Validation | 2026-02 | Phases 1-7 |
| Health Audit Fixes | 2026-02-18 | near_pct fixed, legacy cleanup |
| Backtest Safety Gaps 3-6 | 2026-02 | GAP-3/4/5/6 all fixed |
| Full Codebase Review | 2026-02-17 | 10 files, 253 KB, 120 findings |
| Codebase Review Gates 1-8 | 2026-02-17 | 80+ fixes across DSL, sim, warmup, live safety, data, CLI |
| CLI & Tools Module Splitting (P4.5) | 2026-02-19 | 5 gates, -113 lines dedup |
| Debug & Logging Redesign (P6) | 2026-02-19 | 8 phases: plumbing, verbosity, trace, metrics, journal |
| Live Dashboard Redesign (P7) | 2026-02-19 | Modular package, Rich rendering, tiered refresh, signal proximity |
| Dead Code Audit + Cleanup (P9) | 2026-02-20 | 44 findings, 471 lines deleted. See `docs/DEAD_CODE_AUDIT.md` |
| Structure Detection Audit | 2026-02-20 | Swing/trend/MS on real BTC data. See `docs/STRUCTURE_DETECTION_AUDIT.md` |
| Codebase Review Pass 3 | 2026-02-21 | 51 findings, 49 confirmed by agent verification |
| P10 Phase 1: Critical Live Blockers | 2026-02-21 | 5 fixes (C1, C4, C6, H1, H17) |
| P10 Phase 2: High Live Safety | 2026-02-21 | 10 fixes (C2, C3, H2-H4, H6-H10) |
| P10 Phase 3: Exchange Integration | 2026-02-21 | 4 fixes (H11, H14, M6, M14) |
| P10 Phase 4: Backtest/Engine | 2026-02-21 | 7 fixes + H22 deferred + M16 not-a-bug |
| P10 Phase 5: Data/CLI/Artifacts | 2026-02-21 | 8 fixes (H12, H13, H15, H19, M1, M2, M11, M15) |
| P10 Phase 6: Low Priority | 2026-02-21 | 11 fixes (C5, H5, H16, H18, H20, M3, M9, M10, M12, M17, M19) |
| Codebase Review Pass 4 | 2026-02-21 | 6-agent team, 319 files, 89 findings. See `docs/CODEBASE_REVIEW_2026_02_21.md` |

Full details: `docs/architecture/CODEBASE_REVIEW_ONGOING.md`

---

## Deferred Items

Confirmed issues, low-risk, deferred to appropriate milestones.

### Pre-Deployment (fix before live trading)

- [ ] **GAP-2** No REST API fallback for warmup data. `_load_tf_bars()` tries buffer -> DuckDB -> fails. Needed for cold-start live.
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but doesn't force pybit reconnect. Adding active reconnect risky without integration testing.
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering — defensible tradeoff, needs integration test to reverse.
- [ ] **H22** `backtest_runner.py` — Sim accepts `funding_events` kwarg but no funding event generation pipeline exists yet.

### Optimization (before sustained live sessions)

- [ ] **ENG-BUG-015** `np.append` O(n) on 500-element arrays, ~3-10 MB/hour GC pressure

### Future Features (no correctness impact)

- [ ] **IND-006** Validate warmup estimates match actual `is_ready()` thresholds
- [ ] **SIM-MED-3** `ExchangeMetrics` class (217 lines) — needs result schema wiring
- [ ] **SIM-MED-4** `Constraints` class (193 lines) — needs per-symbol constraint config

---

## Known Issues (non-blocking)

### pandas_ta `'H'` Deprecation Warning

Cosmetic warning, no impact. `pandas_ta.vwap()` passes uppercase `'H'` to `index.to_period()`. Only affects VWAP with hourly anchors. Our `IncrementalVWAP` (live) is unaffected.

---

## Open Feature Work

### P8: Structure Detection Fixes

See `docs/STRUCTURE_DETECTION_AUDIT.md` for full audit.

#### Phase 1: Fix Config Defaults
- [ ] Change `confirmation_close` default to `True` in `market_structure.py`
- [ ] Add recommended defaults to play templates: `min_atr_move: 0.5` or `strict_alternation: true`
- [ ] Document trend/MS timing mismatch in `docs/PLAY_DSL_REFERENCE.md`
- [ ] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 2: Trend Detector Review
- [ ] Investigate why `strength=2` never fires on real BTC data (4h/12h/D, 6 months)
- [ ] Consider reducing consecutive-pair requirement or increasing wave history size
- [ ] **GATE**: Trend reaches `strength=2` at least once on 6-month BTC 4h data

#### Phase 3: Trend/MS Synchronization (Design Decision)
- [ ] Decide approach: accept mismatch / make MS depend on trend / add pending CHoCH / speed up trend / slow down MS
- [ ] Implement chosen approach
- [ ] **GATE**: `python trade_cli.py validate standard` passes

#### Phase 4: CHoCH Correctness
- [ ] Track which swing produced the last BOS
- [ ] CHoCH only valid when breaking the BOS-producing swing level
- [ ] **GATE**: `python trade_cli.py validate quick` passes

### P11: Codebase Review 2026-02-21 Fixes

Full review: `docs/CODEBASE_REVIEW_2026_02_21.md` — 89 findings (5 critical, 19 high, 32 medium, 33 low).

#### Phase 1: Live Safety (immediate)
- [x] **C1**: Already handled — `exchange_orders_manage.close_position()` hardcodes `reduce_only=True` at line 197
- [x] **C2-C4**: Add proper locking in live adapter indicator cache access (`src/engine/adapters/live.py:941,1494,1608`)
- [x] **C5**: Remove duplicate log line in `_load_tf_bars` (`src/engine/adapters/live.py:894`)
- [x] **H-S2**: Unify daily PnL tracking — `GlobalRiskView` now delegates to `DailyLossTracker`
- [x] **M-S6**: Wire `reference_price` on Signal so price deviation guard actually functions
- [x] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 2: Correctness Bugs
- [x] **C5**: (moved from Phase 1) Remove duplicate log line in `_load_tf_bars`
- [x] **H-B1**: Fix `get_structure` prefix stripping — `.removeprefix("high_tf_")` in `snapshot_view.py:1189`
- [x] **H-C2**: Fix gate timeout default — argparser 300 → 600 in `cli/argparser.py:276`
- [x] **H-C3**: Fix timeframe validation for "D" — case-insensitive matching in `utils/timeframes.py`
- [x] **H-E6**: Fix DailyLossTracker error message — use absolute values for clarity
- [x] **H-E7**: Add `ws.ensure_symbol_tracked` to both `limit_buy/sell_with_tpsl` in `exchange_orders_limit.py`
- [x] **H-I1**: Fix MFI first-bar buffer/sum desync — don't append placeholder to buffers
- [x] **GATE**: `python trade_cli.py validate standard` passes (G5 derived_zone parity is pre-existing)

#### Phase 3: Architecture & Quality
- [x] **H-E4**: Add `_validate_trading_operation()` + `ws.ensure_symbol_tracked()` to partial close path
- [x] **H-X1**: Remove duplicate `short_hash()` in `run_logger.py` — imports from `utils/debug.py`
- [x] **H-X3**: Standardize `Path.home()` over `os.path.expanduser` (4 files + unused `os` imports removed)
- [x] **M-I7**: Not applicable — MarketStructure uses scalar fields, not growing lists
- [x] **M-B3**: Use `deque(maxlen=...)` for `state_tracker.py` block_history — O(1) eviction
- [x] **M-C3**: Not applicable — all file accesses in flagged files are reads; writes already have `newline='\n'`
- [ ] **M-C4**: Replace ~48 bare `assert isinstance(...)` with explicit checks in `cli/menus/*.py` (deferred — large mechanical change)
- [x] **GATE**: `python trade_cli.py validate standard` passes (G5 derived_zone parity is pre-existing)

#### Phase 4: Performance & Polish
- [x] **M-I1**: Use `MonotonicDeque` for O(1) min/max in 5 indicators (WilliamsR, Stochastic, StochRSI, Midprice, Fisher)
- [x] **H-I2**: Add periodic sum recomputation for SMA/BBands floating-point drift
- [x] **M-I3**: Move debug import to module level in `structures/state.py`
- [x] **L-I1**: Replace factory if/elif chain with dict lookup in `indicators/incremental/factory.py`
- [x] **L-B3**: Remove dead `compute_warmup_bars` passthrough in `backtest/runtime/windowing.py`
- [x] **M-B5**: Fix `sync_forward` naive `datetime.now()` → `datetime.now(timezone.utc)` in `data/historical_sync.py`
- [ ] **GATE**: `python scripts/run_full_suite.py` — 170/170 pass

### P1: Live Engine Rubric

- [ ] Define live parity rubric: backtest results as gold standard
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### P2: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

### P4: CLI Redesign (Gates 4, 5, 8 open)

See `docs/CLI_REDESIGN.md` for full details.

- [ ] **Gate 4**: Unified `_place_order()` flow
- [ ] **Gate 5**: Data menu top-level rewrite
- [ ] **Gate 8**: Final manual validation

### P5: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0)
- [ ] Phase 2: Bybit exchange sentiment (Tier 1)
- [ ] Phase 3: External data (Tier 2)
- [ ] Phase 4: Historical sentiment for backtesting
- [ ] Phase 5: Statistical regime detection (HMM-based)

---

## Accepted Behavior

| ID | File | Note |
|----|------|------|
| GAP-BD2 | `trade_cli.py` | `os._exit(0)` correct — pybit WS threads are non-daemon |

## Platform Issues

- **DuckDB file locking on Windows** — sequential scripts, `run_full_suite.py` has retry logic

---

## Validation Commands

```bash
# Tiers
python trade_cli.py validate quick              # Pre-commit (~2min)
python trade_cli.py validate standard           # Pre-merge (~6.5min)
python trade_cli.py validate full               # Pre-release (~10min)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)

# Options
python trade_cli.py validate full --workers 4         # Control parallelism
python trade_cli.py validate full --timeout 60        # Per-play timeout (default 120s)
python trade_cli.py validate full --gate-timeout 600  # Per-gate timeout (default 600s)

# Backtest / verification
python trade_cli.py backtest run --play X --sync      # Single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/verify_trade_math.py --play X          # Math verification
```
