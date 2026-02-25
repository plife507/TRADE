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
| P10 Phases 1-6: Codebase Review | 2026-02-21 | 45 fixes across live safety, exchange, engine, data, CLI |
| P11 Phases 1-4: Review Fixes | 2026-02-21 | 27 fixes across live safety, correctness, architecture |
| P12: Lazy WS & Live WS Health | 2026-02-21 | Tri-state WS, stale monitor fix, timestamp/subscription cleanup (14 files) |
| Codebase Review Pass 4 | 2026-02-21 | 6-agent team, 319 files, 89 findings. See `docs/CODEBASE_REVIEW_2026_02_21.md` |
| Timestamp & WS Subscription Fix | 2026-02-21 | 7 files: tz-naive UTC convention, canonical `_datetime_to_epoch_ms`, kline sub default |
| P4+P13: Unified CLI (Phases 1-6) | 2026-02-22 | 64 handlers across 10 subcommand groups, 50+ tools wired to argparse |
| CLI Architecture Audit | 2026-02-22 | 103 tools inventoried. See `docs/CLI_ARCHITECTURE_AUDIT.md` |
| P14: Play Lifecycle — Headless Mode | 2026-02-22 | `--headless` flag, `play watch --json`, agent test prompt |
| P15: Cooldown & Race Fixes (Phases 1-4) | 2026-02-22 | Cross-process locking, atomic writes, 15s cooldown, two-phase reservation |
| Path Migration: ~/.trade → data/runtime/ | 2026-02-22 | 10 files migrated, centralized constants |
| Cross-Platform Newline Compliance | 2026-02-22 | 4 artifact writers fixed, 21/21 write ops verified |
| P16: Cross-Platform Audit (Phases 1-6) | 2026-02-22 | 72 fixes: 38 datetime.now()→UTC, 8 encoding, 6 manager.py bugs, cleanup |
| P17: Play Stop Kill + Duplicate Check | 2026-02-22 | PID-aware process kill, pre-launch symbol duplicate check |
| P18: structlog Migration (Phases 0-4) | 2026-02-24 | TradingLogger deleted, structlog+JSONL, contextvars binding, 243 MB recovered |
| P19: Post-structlog Logging Cleanup | 2026-02-25 | Traceback fix, context leak, dead code, structured fields, 408 f-string conversions |
| ENG-BUG-015: Live Cache Allocation | 2026-02-25 | Pre-allocated rolling buffers in LiveIndicatorCache (zero GC pressure) |

Full details: `docs/architecture/CODEBASE_REVIEW_ONGOING.md`

---

## Pre-Deployment (fix before live trading)

- [ ] **GAP-2** No REST API fallback for warmup data. `_load_tf_bars()` tries buffer → DuckDB → fails. Needed for cold-start live.
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but doesn't force pybit reconnect.
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering — needs integration test.
- [ ] **H22** Sim accepts `funding_events` kwarg but no funding event generation pipeline exists yet.

---

## P20: Timestamp & UTC-Naive Convention Audit

Full codebase audit of time/date handling. 5-agent parallel review covering:
Bybit/pybit docs, entry points, data layer, engine/indicators, live trading path.

### Phase 1: Fix UTC-Naive Convention Violations
- [x] Fix `PanicState.trigger_time` — stores tz-aware datetime, should be naive (`safety.py:211`)
- [x] Fix `TimeRange.start_datetime`/`end_datetime` — return tz-aware, should be naive (`time_range.py:338,343`)
- [x] Fix `IndicatorMetadata.computed_at_utc` — default factory creates tz-aware (`metadata.py:234`)
- [x] Fix `datetime_utils.datetime_to_epoch_ms()` — use `timegm()` like canonical `feed_store.py` function (`datetime_utils.py:178`)
- [x] **GATE**: `python trade_cli.py validate quick` passes

### Phase 2: Add `utc_now()` Helper + Bulk Migration
- [x] Add `utc_now()` to `src/utils/datetime_utils.py`
- [x] Replace 40+ `datetime.now(timezone.utc).replace(tzinfo=None)` with `utc_now()` across 16 files
- [x] **GATE**: `python trade_cli.py validate quick` passes (ALL 6 GATES PASSED, 75.2s)

### Phase 3: Verification Sweep Fixes
- [x] Fix `live_runner.py:744` — `datetime.now(timezone.utc) - naive_ts` would crash with `TypeError` during WS health check
- [x] Fix `feature_frame_builder.py:393` — passed tz-aware datetime to `IndicatorMetadata.computed_at_utc` (now naive)
- [x] **GATE**: `python trade_cli.py validate standard` passes (ALL 13 GATES PASSED, 411.4s)

### Phase 4: Design Gap Fixes
- [x] **G5** WS health check uses `time.time()` → `time.monotonic()` (immune to NTP backward jumps) (`global_risk.py`)
- [x] **G1** Order `created_time`/`updated_time` parsed from raw ms strings to UTC-naive datetimes (`exchange_orders_manage.py`)
- [x] **G2** Position `created_time`/`updated_time` added and parsed from Bybit response (`exchange_manager.py`, `exchange_positions.py`)
- [x] **GATE**: `python trade_cli.py validate quick` passes (ALL 6 GATES PASSED, 74.6s)

### Investigated Non-Issues
- **TickerData `time.time()`**: Correct for staleness detection (answers "when did I receive this?" not "when was it generated?"). Exchange `ts` field is in outer WS envelope, not applicable for health monitoring.
- **Clock skew offset**: `_time_offset_ms` is computed but not consumed in execution path. Available for future use if needed. Current staleness guards use `time.time()` which is correct for local health monitoring.

---

## Cleanup (automatable)

- [x] **M-C4**: Replace 39 bare `assert isinstance(...)` with explicit `TypeError` checks in 7 menu files
- [x] **datetime.utcnow()**: 2 occurrences fixed → `datetime.now(timezone.utc).replace(tzinfo=None)`

---

## Manual Verification (requires exchange connection)

### P4+P13: CLI
- [ ] `data info --json` returns valid JSON
- [ ] `health check --json` returns valid JSON
- [ ] App starts → offline menu → backtest works without connection
- [ ] "Connect to Exchange" (demo) → full menu appears
- [ ] Place market order via unified form
- [ ] `order buy --symbol BTCUSDT --amount 100 --type market --json` on demo
- [ ] `market price --symbol BTCUSDT --json` returns valid JSON
- [ ] Data sub-menus accessible, all operations reachable

### P12: Live WS
- [ ] Run demo play 10+ minutes — NO "Signal execution blocked" warnings
- [ ] `is_websocket_healthy()` returns `True` throughout
- [ ] Run play A → stop → play B → no stale symbols leak
- [ ] Health Check shows correct tri-state WS display

### P14: Headless Play
- [ ] `play run --play AT_001 --mode demo --headless` prints JSON, Ctrl+C stops cleanly
- [ ] While headless running, `play watch --json` shows instance
- [ ] `play stop --all` cleans up headless instance

### P15: Cooldown
- [ ] Start demo → stop → cooldown file → restart immediately (should fail) → wait 15s → succeeds
- [ ] Start headless → second start in different terminal (should fail)
- [ ] Fake instance file with dead PID → `play status` → cleaned up

---

## Future Features (no correctness impact)

- [x] **SIM-MED-3** Wired `ExchangeMetrics` into full result pipeline. SimulatedExchange records metrics → BacktestRunner extracts to metadata → PlayBacktestResult carries direct field → ResultsSummary writes to result.json. 16 metrics (slippage, fees, fills, funding, liquidation, volume).
- [x] **SIM-MED-4** Wired `Constraints` into SimulatedExchange. Min notional validation on all order submissions, tick size rounding on limit/trigger prices, lot size rounding on entry fills. Default config: tick=0.01, lot=0.001, min_notional=1 USDT. validate quick passed.

---

## Open Feature Work

### IND-006: Warmup Formula / `is_ready()` Mismatches (COMPLETE)

Fixed warmup formulas — ATR off-by-one, Supertrend off-by-one, Squeeze momentum SMA floor. All formulas now match `is_ready()` thresholds. validate quick passed.

#### Phase 1: Fix Registry Formulas
- [x] Fix Squeeze warmup formula to account for KC's internal EMA (`kc_length * 3 + 1`)
- [x] Fix ATR formula: `length` not `length + 1` (match `is_ready()`)
- [x] Fix Supertrend off-by-one
- [x] Fix Squeeze momentum SMA floor
- [x] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 2: Add Warmup Parity Validation
- [ ] Add a validation check that runs each indicator to `is_ready()` and compares vs registry formula
- [ ] **GATE**: `python trade_cli.py validate module --module coverage` passes

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

### P1: Live Engine Rubric

- [ ] Define live parity rubric: backtest results as gold standard
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### P2: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

---

## Accepted Behavior

| ID | File | Note |
|----|------|------|
| GAP-BD2 | `trade_cli.py` | `os._exit(0)` correct — pybit WS threads are non-daemon |

## Platform Issues

- **DuckDB file locking on Windows** — sequential scripts, `run_full_suite.py` has retry logic
- **Windows `os.replace` over open files** — `PermissionError` if another process is mid-read of instance JSON (`manager.py:416`)

## Known Issues (non-blocking)

- **pandas_ta `'H'` Deprecation Warning** — cosmetic, `pandas_ta.vwap()` passes `'H'` to `index.to_period()`. Our `IncrementalVWAP` is unaffected.

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
