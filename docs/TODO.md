# TRADE TODO

Single source of truth for all open work, bugs, and task progress.

---

## Completed Work (archived)

| Item | Status | Date | Reference |
|------|--------|------|-----------|
| Liquidation Parity (Bybit) | DONE | 2026-02 | Liquidation parity review complete |
| Fast Parallel Validation | DONE | 2026-02 | Phases 1-7 complete |
| Health Audit Fixes | DONE | 2026-02-18 | near_pct fixed, legacy cleanup done |
| Backtest Safety Gaps 3-6 | DONE | 2026-02 | GAP-3/4/5/6 all FIXED |
| Full Codebase Review | DONE | 2026-02-17 | `docs/architecture/` (10 files, 253 KB, 120 findings) |
| Codebase Review Gate 1: DSL Critical | DONE | 2026-02-17 | 5 CRIT fixes (setup cache, operators, else_emit, auto-conversion, risk policy) |
| Codebase Review Gate 2: Sim Parity | DONE | 2026-02-17 | 3 HIGH fixes (liquidation fee, bankruptcy price, close reasons) |
| Codebase Review Gate 3: Warmup | DONE | 2026-02-17 | 2 items resolved (ENG-001, BT-007). 2 deferred (see below) |
| Codebase Review Gate 4: Live Safety | DONE | 2026-02-17 | 12 fixes (close ordering, WS reconnect, stale data, pre-live gates) |
| Codebase Review Gate 5: DSL & Engine MED | DONE | 2026-02-17 | 17 fixes + pyright 0 + validate standard 12/12 |
| Codebase Review Gate 6: Sim & Backtest MED | DONE | 2026-02-17 | 13 fixes + validate standard 12/12. 2 future features deferred |
| Codebase Review Gate 7: Data/CLI/Forge MED | DONE | 2026-02-17 | 18 fixes. 1 deferred (DATA-011) |
| Codebase Review Gate 8: LOW Cleanup | DONE | 2026-02-17 | 12 fixed, 18 evaluated OK, 8 not-a-bug. 1 deferred (DATA-017) |
| CLI & Tools Module Splitting (P4.5) | DONE | 2026-02-19 | Phases 1-5 complete. 5 gates passed. Net -113 lines deduplication |

Full gate details with per-item descriptions: `memory/completed_work.md`

---

## Deferred Items

Items evaluated during codebase review, confirmed low-risk, deferred to appropriate milestones.

### Pre-Deployment (must fix before live trading)

- [ ] **GAP-2** No REST API fallback for warmup data. `_load_tf_bars()` tries buffer -> DuckDB -> fails. Needed for cold-start live scenarios.
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but does not force pybit reconnect. `GlobalRiskView._check_ws_health()` blocks trading after 30s unhealthy. Adding active reconnect risky without integration testing.
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering is a defensible tradeoff. Reversing to close-first needs integration test to confirm exchange rejects TP-after-close on reduce-only positions.
- [ ] **GATE**: `python trade_cli.py validate pre-live --play X` passes

### Optimization (before sustained live sessions)

- [ ] **ENG-BUG-015** `np.append` O(n) on 500-element arrays, ~3-10 MB/hour GC pressure. Correct behavior, optimize before sustained live sessions.

### Future Features (no correctness impact)

- [ ] **IND-006** Validation that warmup estimates match actual `is_ready()` thresholds. Not a bug (indicators output NaN until ready, which propagates safely).
- [ ] **SIM-MED-3** `ExchangeMetrics` class (217 lines) fully implemented but zero callers. Needs result schema wiring to surface metrics.
- [ ] **SIM-MED-4** `Constraints` class (193 lines) fully implemented but not wired. Needs per-symbol constraint config from exchange instrument info.

---

## Known Issues (non-blocking)

### pandas_ta `'H'` Deprecation Warning

**Status**: Cosmetic warning, no impact on correctness. Will become error in future pandas release.

**Root cause**: `pandas_ta.vwap()` calls `anchor.upper()` internally, passing uppercase `'H'` to `index.to_period()`. Pandas deprecated uppercase `'H'` in favor of lowercase `'h'`.

**Affected**: Only VWAP with hourly anchors (e.g., `anchor: "4h"`). Daily/weekly unaffected. Our `IncrementalVWAP` (live mode) unaffected.

**Fix options** (when pandas removes `'H'`):
1. Upgrade `pandas_ta` if they fix the `.upper()` call upstream.
2. If no upstream fix: monkey-patch or fork `pandas_ta.vwap()` to use lowercase anchor.

---

## Open Feature Work

### P1: Live Engine Rubric

- [ ] Define live parity rubric: backtest results as gold standard for live comparison
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### P2: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

### P4: CLI Redesign (Gates 4, 5, 8 open)

See `docs/CLI_REDESIGN.md` for full details.

- [ ] **Gate 4**: Unified `_place_order()` flow (type selector, side, symbol, amount, preview, confirm)
- [ ] **Gate 5**: Data menu top-level rewrite (delegate to sub-menu files already created)
- [ ] **Gate 8**: Final manual validation (offline menu, connect flow, quick-picks, cross-links)

### P4.5: CLI & Tools Module Splitting (deferred items only)

Phases 1-5 DONE (see Completed Work table). Remaining low-priority items:

- `order_tools.py` (1,069 lines) — could split batch/conditional orders but not urgent
- `src/cli/validate.py` (1,802 lines) — self-contained validation orchestration, split only if it grows further
- `src/cli/utils.py` (927 lines) — cohesive utility collection, leave as-is

### P5: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0) -- existing indicators + structures, zero new deps
- [ ] Phase 2: Bybit exchange sentiment (Tier 1) -- funding rate, OI, L/S ratio, liquidations, OBI
- [ ] Phase 3: External data (Tier 2) -- Fear & Greed Index, DeFiLlama stablecoin supply
- [ ] Phase 4: Historical sentiment for backtesting
- [ ] Phase 5: Statistical regime detection -- HMM-based (optional, requires hmmlearn)
- [ ] Future: Agent-based play selector that consumes sentiment tracker output

---

## Accepted Behavior

| ID | File | Note |
|----|------|------|
| GAP-BD2 | `trade_cli.py` | `os._exit(0)` is correct -- pybit WS threads are non-daemon, `sys.exit()` would hang |

## Platform Issues

- **DuckDB file locking on Windows** -- all scripts run sequentially, `run_full_suite.py` has retry logic (5 attempts, 3-15s backoff)

---

## Validation Commands

```bash
# Unified tiers (parallel staged execution, with timeouts + incremental reporting)
python trade_cli.py validate quick              # Pre-commit (~2min)
python trade_cli.py validate standard           # Pre-merge (~4min)
python trade_cli.py validate full               # Pre-release (~6min)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)

# Options
python trade_cli.py validate full --workers 4         # Control parallelism
python trade_cli.py validate full --timeout 60        # Per-play timeout (default 120s)
python trade_cli.py validate full --gate-timeout 300  # Per-gate timeout (default 600s)

# Backtest / verification
python trade_cli.py backtest run --play X --sync      # Single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/verify_trade_math.py --play X          # Math verification
```
