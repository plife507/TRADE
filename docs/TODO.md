# TRADE TODO

Single source of truth for all open work, known bugs, and session context.
All gates G0-G17 complete (2026-01-27 through 2026-02-15). Full history in Claude Code memory: `completed_work.md`.

---

## P0: Live Engine Rubric

28 demo/live bugs were fixed (2026-02-12). Remaining items:
- [ ] Define live parity rubric: backtest results as gold standard for live comparison
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

## P1: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

## P2: Unify `--fix-gaps` / `--fill-gaps` → `--sync` (COMPLETE 2026-02-15)

All 5 gates complete. `--sync`/`--no-sync` is the unified flag everywhere. `--heal` remains as separate doctor action. pyright 0 errors, grep clean.

## P3: CLI Redesign (Gates 4, 5, 8 open)

Gates 1-3, 6-7, 9 complete. See `docs/CLI_REDESIGN.md` for full details.

- [ ] **Gate 4**: Unified `_place_order()` flow (type selector, side, symbol, amount, preview, confirm)
- [ ] **Gate 5**: Data menu top-level rewrite (delegate to sub-menu files already created)
- [ ] **Gate 8**: Final manual validation (offline menu, connect flow, quick-picks, cross-links)

## P4: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0) -- existing indicators + structures, zero new deps
- [ ] Phase 2: Bybit exchange sentiment (Tier 1) -- funding rate, OI, L/S ratio, liquidations, OBI
- [ ] Phase 3: External data (Tier 2) -- Fear & Greed Index, DeFiLlama stablecoin supply
- [ ] Phase 4: Historical sentiment for backtesting
- [ ] Phase 5: Statistical regime detection -- HMM-based (optional, requires hmmlearn)
- [ ] Future: Agent-based play selector that consumes sentiment tracker output

---

## P5: Codebase Cleanup — Dead Code, Legacy, and Simplification (COMPLETE 2026-02-16)

Full codebase audit + execution. 5 parallel Opus agents, each gate grep-verified before deletion.
~2,500+ lines removed. pyright 0 errors. ALL FORWARD — no legacy wrappers.

### Gate C1: `src/engine/` — COMPLETE (19/19 items, ~307 lines)
All 19 dead functions/methods/properties deleted. Re-export cleaned from `timeframe/__init__.py`.

### Gate C2: `src/indicators/` — COMPLETE (11/11 items, ~870 lines)
Deleted `compute.py` (339-line duplicate), `provider.py` (257 lines), metadata export/validation functions (~220 lines), unused imports, `INCREMENTAL_INDICATORS` frozenset. Added `IncrementalAnchoredVWAP` to top-level exports. Facade re-exports kept (used by `src/forge/audits/`).

### Gate C3: `src/backtest/` — COMPLETE (10/15 items done, facade items deferred)
Deleted: `rationalization/` (6 files), `sim/adapters/` (3 files), `prices/engine.py` + `validation.py` + `backtest_source.py` + `demo_source.py`, `gates/` partial (kept `indicator_requirements_gate.py`), `rules/dsl_warmup.py`. Removed `StrategyInstanceSummary`, dead `system_config.py` functions, dead `artifacts/__init__.py` exports. Updated `market_structure/types.py` consumers to import from `structure_types.py`.

### Gate C4: `src/structures/` + `src/data/` — COMPLETE (8/10 items, ~620 lines)
Deleted `backend_protocol.py`, `sessions.py`. Cleaned 6 dead re-exports from `data/__init__.py`. Removed `create_detector_with_deps` + `STRUCTURE_WARMUP_FORMULAS` from `structures/__init__.py`. `realtime_models.py` merge deferred (low priority).

### Gate C5: `src/tools/` + `scripts/` — COMPLETE (11/12 items)
Deleted duplicate constants, 5 dead `shared.py` helpers, `backtest_audit_in_memory_parity_tool`, `scripts/add_validation_blocks.py`, `TIME_RANGE_PARAMS`, `ToolRegistry.execute_batch()`, 4 unreachable tools. `TradingEnvMismatchError` left as-is (low priority).

### Gate C6: Cross-Module — COMPLETE (partial, ~7 items)
Deleted `src/core/prices/` package. Cleaned dead exports from `core/__init__.py`, `risk/__init__.py`, `exchanges/__init__.py`. Deleted `config/defaults.yml` `window_bars_ceiling`. Deleted 8 feature-spec factory functions from `feature_spec.py`. Cleaned `indicators/__init__.py` and `backtest/features/__init__.py` dead re-exports.

**Audit corrections:** `notifications.py` and `journal.py` were NOT dead (used by `live_runner.py`). `FeatureSpecSet` was NOT dead (used by `feature_frame_builder.py`). Audit had incorrectly flagged these.

---

## Known Bugs & Architecture Gaps

### Live/Demo Gaps (from 2026-02-11 audit)

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| GAP-1 | **CRITICAL** | `LiveDataProvider._warmup_bars` hardcoded to 100 regardless of Play needs | Wire `get_warmup_from_specs()` into `LiveDataProvider.__init__()` |
| GAP-2 | HIGH | No REST API fallback for warmup data -- `_load_tf_bars()` tries buffer -> DuckDB -> gives up | Add REST `get_klines()` fallback |
| GAP-3 | MEDIUM | Play's `starting_equity_usdt` ignored in live -- real exchange balance used silently | Add preflight equity reconciliation warning |
| GAP-4 | MEDIUM | Leverage set per-order only, not during account init | Call `set_leverage()` in `LiveExchange.connect()` |
| GAP-5 | LOW | Play `taker_bps` vs actual Bybit VIP tier fees not compared | Add preflight fee reconciliation |

### VWAP / Anchored VWAP (from 2026-02-15 audit, line refs updated 2026-02-16)

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| V-1 | DESIGN | Non-swing detectors missing `reset()` / `to_dict()` for crash recovery | `trend.py`, `zone.py`, `fibonacci.py`, `derived_zone.py`, `rolling_window.py`, `market_structure.py` |
| V-2 | DESIGN | Multiple swing structures on exec TF: first wins, no way to select | `play_engine.py:1026` |
| V-3 | DESIGN | `near_pct` tolerance has two conversion paths (play.py /100, dsl_parser.py raw) -- fragile | `play.py:215`, `dsl_parser.py:578` |
| V-4 | EDGE | Anchored VWAP on non-exec TF cannot wire to non-exec swing structure | `play_engine.py:1026` |
| V-5 | EDGE | Batch pre-computation for anchored_vwap is wasted work (engine overwrites every bar) | `indicator_vendor.py:217-454` |
| V-6 | EDGE | Parity audits would false-fail for anchored_vwap (batch vs engine divergence) | `audit_incremental_parity.py` |
| V-7 | EDGE | No test coverage for VWAP session boundary resets | Validation plays |
| V-8 | EDGE | `swing.high_version` / `swing.low_version` accessible but undocumented in DSL reference | `PLAY_DSL_REFERENCE.md` |

### Platform

- **DuckDB file locking on Windows** -- all scripts run sequentially, `run_full_suite.py` has retry logic (5 attempts, 3-15s backoff)

---

## Validation Commands

```bash
python trade_cli.py validate quick              # Pre-commit (~10s)
python trade_cli.py validate standard           # Pre-merge (~2min)
python trade_cli.py validate full               # Pre-release (~10min)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange            # Exchange integration (~30s)

python trade_cli.py backtest run --play X --sync      # Single backtest (--sync default, shown for clarity)
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/run_real_verification.py               # 60-play real verification
python scripts/verify_trade_math.py --play X          # Math verification
```
