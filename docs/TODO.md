# TRADE TODO

Single source of truth for all open work and known bugs.
Completed work archived in Claude Code memory: `completed_work.md`.

---

## P0: Liquidation Parity (Bybit) -- DONE

See `docs/LIQUIDATION_PARITY_REVIEW.md` for full gap analysis. All phases complete.

## P0: Fast Parallel Validation

Validation is the #1 development bottleneck. Current: `quick` ~10s, `standard` ~2min, `full` ~10min, real-data ~30min+. Target: `quick` ~7s, `standard` ~20s, `full` ~50s, `real` ~2min.

**Architecture**: Sync DuckDB once (single writer), then run all plays in parallel (read-only). Synthetic plays never touch DuckDB. Module-based CLI enables Claude Code agents to run validation in parallel.

**Files modified**: `src/cli/validate.py`, `src/cli/argparser.py`, `trade_cli.py`, `.claude/commands/validate.md`, `.claude/agents/validate.md`

### Phase 1: Parallel play execution in `_gate_play_suite`
- [x] Add `_run_single_play_synthetic(play_id) -> tuple[str, int, str | None]` module-level function
- [x] Rewrite `_gate_play_suite()` to use `ProcessPoolExecutor(max_workers=cpu_count()-1)` with `as_completed()`
- [x] Add `--workers N` CLI argument to `argparser.py`
- [x] Pass `max_workers` through `run_validation()` to `_gate_play_suite()`
- [x] **GATE**: `python trade_cli.py validate quick` passes (5/5 gates, all pass)

### Phase 2: Staged concurrent gate execution
- [x] Add `_run_staged_gates(schedule, fail_fast) -> list[GateResult]`
- [x] Single gate in stage: run directly. Multiple: `ThreadPoolExecutor`
- [x] Build schedule lists for quick/standard/full tiers
- [x] Replace `_run_gates()` with `_run_staged_gates()` for quick/standard/full
- [x] **GATE**: `python trade_cli.py validate quick` passes with staged execution

### Phase 3: `validate module` subcommand
- [x] Add `MODULE_DEFINITIONS` dict mapping module name to gate function(s)
- [x] Add `run_module_validation(module_name, max_workers, json_output) -> int`
- [x] Add `"module"` to tier choices + `--module` argument in `argparser.py`
- [x] Wire module dispatch in `trade_cli.py`
- [x] **GATE**: `python trade_cli.py validate module --module core --json` passes
- [x] **GATE**: `python trade_cli.py validate module --module metrics --json` passes

### Phase 4: Real-data parallel validation with sync-once
- [x] Add `REAL_DATA_SYNC_MANIFEST` dict with symbol/TF/date entries
- [x] Add `_sync_real_data_manifest()` function (serial sync)
- [x] Add `_run_single_play_real(play_id, start, end)` worker
- [x] Add `_extract_dates_from_play(play_path)` (regex on description)
- [x] Add `"real"` tier + real-data module definitions
- [x] Wire `validate real`: sync phase (serial) -> run phase (parallel)
- [ ] **GATE**: `python trade_cli.py validate real` passes -- 61/61 plays (needs data sync)

### Phase 5: `/validate` skill + agent rewrite
- [x] Rewrite `.claude/commands/validate.md` with staged orchestration protocol
- [x] Update `.claude/agents/validate.md` with module commands, real-data tier

### Phase 6: Final validation + cleanup
- [x] `python trade_cli.py validate quick` -- 5/5 gates pass
- [x] `python trade_cli.py validate standard` -- 9/11 gates pass (2 pre-existing zero-trade plays: STR_001, STR_009, STR_010, CL_006)
- [x] pyright -- 0 errors
- [x] Update TODO.md + CLAUDE.md validation commands sections
- [x] Rewrite `.claude/commands/validate.md` + `.claude/agents/validate.md`

**Note**: STR_001/009/010 and CL_006 zero-trade failures are pre-existing (confirmed via serial run). Not caused by parallelization.

## P1: Live Engine Rubric

- [ ] Define live parity rubric: backtest results as gold standard for live comparison
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

## P2: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

## P4: CLI Redesign (Gates 4, 5, 8 open)

See `docs/CLI_REDESIGN.md` for full details.

- [ ] **Gate 4**: Unified `_place_order()` flow (type selector, side, symbol, amount, preview, confirm)
- [ ] **Gate 5**: Data menu top-level rewrite (delegate to sub-menu files already created)
- [ ] **Gate 8**: Final manual validation (offline menu, connect flow, quick-picks, cross-links)

## P5: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0) -- existing indicators + structures, zero new deps
- [ ] Phase 2: Bybit exchange sentiment (Tier 1) -- funding rate, OI, L/S ratio, liquidations, OBI
- [ ] Phase 3: External data (Tier 2) -- Fear & Greed Index, DeFiLlama stablecoin supply
- [ ] Phase 4: Historical sentiment for backtesting
- [ ] Phase 5: Statistical regime detection -- HMM-based (optional, requires hmmlearn)
- [ ] Future: Agent-based play selector that consumes sentiment tracker output

---

## Open Bugs & Architecture Gaps

### Backtest Safety Gaps (from CODEBASE_REVIEW.md, 2026-02-17)

| # | Severity | Issue | File(s) | Status |
|---|----------|-------|---------|--------|
| GAP-3 | **CRITICAL** | Max drawdown stop not propagated: `run_engine_with_play()` drops stop fields when converting `BacktestResult` → `PlayBacktestResult` | `engine_factory.py` | **FIXED** — reads stop fields from `backtest_result.metadata` |
| GAP-4 | **CRITICAL** | Liquidation not treated as terminal stop -- backtest returns success after liquidation events | `sim/exchange.py`, `backtest_runner.py` | **FIXED** — `_check_liquidation` returns `LiquidationResult`, runner breaks on liquidation |
| GAP-5 | **HIGH** | `run_backtest_with_gates()` marks success based on gates/artifacts, ignores terminal risk events | `backtest/runner.py` | **FIXED** — Phase 9b risk gate raises `GateFailure` on terminal `StopReason` |
| GAP-6 | **HIGH** | No validation plays exercise terminal risk events (max drawdown, liquidation) | `validate.py` | **FIXED** — G4b gate runs 4 risk plays (`V_RISK_001`-`004`) asserting correct stop classifications |

### Live/Demo Gaps

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| GAP-1 | **CRITICAL** | `LiveDataProvider._warmup_bars` hardcoded to 100 regardless of Play needs | Wire `get_warmup_from_specs()` into `LiveDataProvider.__init__()` |
| GAP-2 | HIGH | No REST API fallback for warmup data -- `_load_tf_bars()` tries buffer -> DuckDB -> gives up | Add REST `get_klines()` fallback |

### Accepted Behavior

| # | File | Note |
|---|------|------|
| GAP-BD2 | `trade_cli.py` | `os._exit(0)` is correct -- pybit WS threads are non-daemon, `sys.exit()` would hang |

### Platform

- **DuckDB file locking on Windows** -- all scripts run sequentially, `run_full_suite.py` has retry logic

---

## Validation Commands

```bash
# Unified tiers (parallel play execution + staged gates)
python trade_cli.py validate quick              # Pre-commit (~7s)
python trade_cli.py validate standard           # Pre-merge (~20s)
python trade_cli.py validate full               # Pre-release (~50s)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)

# Single module (for parallel agent execution)
python trade_cli.py validate module --module core --json
python trade_cli.py validate module --module indicators --json
python trade_cli.py validate module --module metrics --json

# Options
python trade_cli.py validate full --workers 4        # Control parallelism
python trade_cli.py validate standard --no-fail-fast  # Run all gates
python trade_cli.py validate quick --json             # JSON output for CI

# Backtest / verification
python trade_cli.py backtest run --play X --sync      # Single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/run_real_verification.py               # 60-play real verification
python scripts/verify_trade_math.py --play X          # Math verification
```
