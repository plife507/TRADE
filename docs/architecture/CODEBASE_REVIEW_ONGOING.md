# Codebase Review Ongoing

Last updated: 2026-02-21 (post P10 Phases 2-5 fix)

This is a running senior-level audit log for active findings across the codebase.
Only issues verified in source are listed as confirmed.

## Resolved Findings

Fixed in commit `ed92caa` (P10 Phases 2-5, 2026-02-21) and `1a1dc51` (P10 Phase 1, 2026-02-21).

### Phase 1 (Critical Live Blockers — 5 fixes)
- **C1** RealtimeState missing callback methods — FIXED
- **C4** Anchored VWAP readiness deadlock — FIXED
- **C6** Non-idempotent order retries — FIXED
- **H1** ERROR→STOPPING state transition — FIXED
- **H17** Swallowed clock drift RuntimeError — FIXED

### Phase 2 (High Live Safety — 10 fixes)
- **C2** Per-stream stale detection — FIXED
- **C3** submit_close() result propagation — FIXED
- **H2** cancel_all_orders() return check — FIXED
- **H3** get_closed_pnl() exception propagation — FIXED
- **H4** Private WS startup when risk_needs_ws — FIXED
- **H6** RiskManager exchange_manager wiring — FIXED
- **H7** additional_exposure pre-trade gate — FIXED
- **H8** Fail-closed drawdown exception — FIXED
- **H9** Private state refresh on reconnect — FIXED
- **H10** Orders refresh on stale recovery — FIXED

### Phase 3 (Exchange Integration — 4 fixes)
- **H11** Batch cancel/amend double-unwrap — FIXED
- **H14** Transferable amount API — FIXED
- **M6** Structure value float() coercion — FIXED
- **M14** WS kline interval key normalization — FIXED

### Phase 4 (Backtest/Engine — 7 fixes)
- **H21** Exec warmup pointer — FIXED
- **H23** between operator list→RangeValue — FIXED
- **M4** Invalid feature source raise — FIXED
- **M7** Out-of-range lookback NaN — FIXED
- **M8** NaN ATR zone skip — FIXED
- **M13** Preflight status key — FIXED
- **M18** Determinism field presence check — FIXED

### Phase 5 (Data/CLI — 8 fixes)
- **H12** DuckDB write locking in historical_sync — FIXED
- **H13** Partial fetch metadata skip — FIXED
- **H15** get_open_orders() pagination — FIXED
- **H19** data_env passthrough in runner — FIXED
- **M1** Play resolution before pre-live gate — FIXED
- **M2** Play re-resolution verified — FIXED
- **M11** Indicator factory _VALID_PARAMS — FIXED
- **M15** get_positions() pagination — FIXED

### Not-a-bug
- **M16** long/short win_rate scale — consistent percentage-scale throughout pipeline

---

## Open Findings (Remaining)

### Deferred (confirmed, not yet fixed)

- **H22** `src/engine/runners/backtest_runner.py` + `src/backtest/sim/exchange.py`
  - Backtest runner does not pass `funding_events` into sim `process_bar()`.
  - Status: DEFERRED — sim accepts kwarg but no funding event generation pipeline exists.

- **C5** `src/data/historical_data_store.py`
  - File-lock stale eviction removes `.lock` files older than 5 minutes without PID validation.
  - Status: DEFERRED to pre-deployment (low practical risk).

- **H5** `src/core/application.py`
  - `_shutting_down` not reset after successful shutdown.
  - Status: DEFERRED (retry-only scenario).

- **H16** `src/core/exchange_instruments.py`
  - `round_price()`/`calculate_qty()` use `Decimal.quantize()` — doesn't enforce true multiples for non-power-of-10 steps.
  - Status: DEFERRED (rare pairs only).

- **H18** `src/backtest/runner.py`
  - Artifact identity hardcodes `"duckdb_live"` for all non-synthetic runs.
  - Status: DEFERRED.

- **H20** `src/backtest/runtime/timeframe.py`
  - `ceil_to_tf_close()` uses `datetime.timestamp()` on naive datetimes assuming UTC.
  - Status: DEFERRED.

- **M3** `src/tools/backtest_play_tools.py`
  - `strict` flag accepted but not wired to execution behavior.
  - Status: DEFERRED.

- **M9** `src/structures/detectors/derived_zone.py`
  - Zone hash uses stale `_source_version` during regeneration.
  - Status: DEFERRED.

- **M10** `src/structures/registry.py`
  - Missing fibonacci anchor metadata fields in STRUCTURE_OUTPUT_TYPES.
  - Status: DEFERRED.

- **M12** `src/cli/argparser.py`
  - Dead `_validate` path attached to parser, never reaches args namespace.
  - Status: DEFERRED.

- **M17** `src/backtest/artifacts/artifact_standards.py`
  - `verify_run_folder()`/`verify_hash_integrity()` not wired into artifact creation path.
  - Status: DEFERRED.

- **M19** `src/backtest/artifacts/determinism.py`
  - `verify_determinism_rerun()` doesn't propagate `data_env`/`plays_dir`.
  - Status: DEFERRED.

---

## Next Pass Queue

- Fix Phase 6 deferred items opportunistically or before specific milestones.
- P8 (Structure Detection) — 4 phases open, independent of P10.
- Live integration testing (P1/P2) requires demo mode validation.
