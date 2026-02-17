# TRADE TODO

Single source of truth for all open work, known bugs, and session context.
All gates G0-G17 complete (2026-01-27 through 2026-02-15). P5 cleanup done (2026-02-16). Full history in Claude Code memory: `completed_work.md`.

---

## P0: Live Engine Rubric

28 demo/live bugs were fixed (2026-02-12). Remaining items:
- [ ] Define live parity rubric: backtest results as gold standard for live comparison
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### P0-R: Exchange Config Reconciliation

Play YAML config is for backtesting. In live/demo, the exchange is the source of truth. Replace scattered `_preflight_*` hacks with a single `_reconcile_config_with_exchange()` method in `LiveExchange.connect()` that patches **both** `Play.account` (frozen dataclass via `replace()`) **and** `PlayEngineConfig` (mutable, direct `setattr`).

| Field | Exchange Source | Currently Handled? |
|-------|---------------|-------------------|
| `starting_equity_usdt` | `get_balance()` → wallet total | Partial — patches Play.account but NOT PlayEngineConfig.initial_equity |
| `fee_model` (taker/maker bps) | `_actual_fee_rates` from `get_fee_rates()` | Partial — patches Play.account but NOT PlayEngineConfig.taker_fee_rate/maker_fee_rate |
| `max_leverage` | `get_risk_limits(symbol)` → tier 1 `maxLeverage` | NO — YAML value used uncapped; liq math may be wrong |
| `maintenance_margin_rate` | `get_risk_limits(symbol)` → tier 1 `maintenanceMarginRate` | NO — hardcoded default 0.5%; wrong for higher tiers |
| `min_trade_notional_usdt` | `_get_instrument_info(symbol)` → `lotSizeFilter.minNotionalValue` | NO — YAML default used; orders may fail at exchange |

**Implementation:** COMPLETE (2026-02-16)
- [x] Delete `_preflight_equity_check()` and `_preflight_fee_check()` (replaced)
- [x] Add `_reconcile_config_with_exchange()` — single method, queries all 5 values, patches Play.account + PlayEngineConfig
- [x] Call it in `connect()` after `ExchangeManager()` + `_bootstrap_balance_from_rest()`, before `_build_risk_config()`
- [x] Update GAP-3/5 entries

**Out of scope:** `max_notional_usdt` / `max_margin_usdt` (dead fields, user-set caps not exchange values), cross-margin branch (dead code), `slippage_bps` / `max_drawdown_pct` (model/strategy params)

### P0-D: Config Defaults — Hybrid Approach

**Design:** `AccountConfig.from_dict()` already fills missing Play fields from `DEFAULTS` at parse time. Engine code should trust Play values — no secondary fallbacks. For backtest/dev: defaults fill in for convenience with warnings. For pre-live: `validate pre-live` rejects Plays missing explicit values.

**Stage 1: Kill engine-level fallbacks (real bugs)** — COMPLETE
Engine code had secondary `or` fallbacks that contradicted defaults.yml and were unreachable since `AccountConfig.from_dict()` always populates fields. Replaced with fail-loud `ValueError` if None.
- [x] `src/backtest/engine_factory.py`: Removed `slippage_bps = 5.0` and `maintenance_margin_rate = 0.005` fallbacks — fail-loud if None
- [x] `src/engine/factory.py`: Removed `or 5.0`, `or 2.0`, `0.0006`, `0.0001` fallbacks — fail-loud if None
- [x] `src/engine/sizing/model.py`: Fixed `SizingConfig` defaults: `max_leverage=1.0`, `min_trade_usdt=10.0`

**Stage 2: Extend `SystemDefaults` to load ALL `defaults.yml` sections** — COMPLETE
- [x] Extended `RiskDefaults` with 4 fields, added `EngineDefaults`, `WindowingDefaults`, `ImpactDefaults`, `PositionPolicyDefaults`
- [x] Wired into `SystemDefaults` + `load_system_defaults()` with required-section validation

**Stage 3: Add warnings + pre-live gate** — COMPLETE
- [x] `AccountConfig.from_dict()`: logs warning listing each field filled from DEFAULTS
- [x] `validate pre-live` gate PL4: rejects Plays missing explicit account fields (equity, leverage, fees, slippage, drawdown)

**Stage 4: Wire remaining references** — COMPLETE
- [x] `src/risk/global_risk.py`: Wired `max_total_exposure_usd` in `RiskLimits.from_config()`

**NOT changing (intentional):** `src/config/config.py` RiskConfig conservative caps ($20 daily loss, $50 position) — LIVE SAFETY limits, deliberately stricter than backtest defaults.

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

## P5: Codebase Cleanup (COMPLETE 2026-02-16)

69 files changed, 7,817+ lines removed across 6 gates (C1-C6). All deferred items resolved. pyright 0. Full details in Claude Code memory: `completed_work.md`.

---

## Known Bugs & Architecture Gaps

### Live/Demo Gaps (from 2026-02-11 audit)

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| GAP-1 | **CRITICAL** | `LiveDataProvider._warmup_bars` hardcoded to 100 regardless of Play needs | Wire `get_warmup_from_specs()` into `LiveDataProvider.__init__()` |
| GAP-2 | HIGH | No REST API fallback for warmup data -- `_load_tf_bars()` tries buffer -> DuckDB -> gives up | Add REST `get_klines()` fallback |
| ~~GAP-3~~ | ~~MEDIUM~~ | ~~Play config not reconciled with exchange in live~~ | **RESOLVED 2026-02-16** — `_reconcile_config_with_exchange()` overrides equity, fees, leverage, MMR, min notional from exchange into both Play.account and PlayEngineConfig |
| ~~GAP-4~~ | ~~MEDIUM~~ | ~~`RiskConfig.max_leverage` defaulted to 3, ignoring Play~~ | **RESOLVED 2026-02-16** — `_build_risk_config()` wires `max_leverage` + `max_drawdown_pct` from Play |
| ~~GAP-5~~ | ~~LOW~~ | ~~`PlayEngineConfig` not updated with exchange values~~ | **RESOLVED 2026-02-16** — merged into GAP-3 fix; `_reconcile_config_with_exchange()` patches PlayEngineConfig directly |

### VWAP / Anchored VWAP (ALL RESOLVED 2026-02-16)

V-1 through V-8 resolved: crash recovery, swing selection, near_pct fix, batch skip, parity exclusion, session boundary test, docs. Details in Claude Code memory.

### Platform

- **DuckDB file locking on Windows** -- all scripts run sequentially, `run_full_suite.py` has retry logic (5 attempts, 3-15s backoff)

---

## Session Handoff — 2026-02-16

**Completed this session:**

1. **VWAP audit (V-1 through V-8)** — all 8 items resolved:
   - V-1: Added `reset()` + `to_dict()` crash recovery to 6 non-swing detectors (trend, zone, fibonacci, derived_zone, rolling_window, market_structure)
   - V-2/V-4: `anchor_structure` param for explicit swing selection + non-exec TF wiring
   - V-3: `near_pct` tolerance unified — verbose DSL path now divides by 100 like shorthand
   - V-5: Batch anchored_vwap replaced with NaN placeholders (engine overwrites every bar)
   - V-6: Parity audit excludes anchored_vwap with explanatory comment
   - V-7: New validation play `IND_044_vwap_session_boundary.yml`
   - V-8: `swing.high_version` / `swing.low_version` documented in DSL reference

2. **Exchange config reconciliation (P0-R)** — new `_reconcile_config_with_exchange()`:
   - Single method replaces scattered `_preflight_*` hacks
   - Patches 5 fields from exchange: equity, fees, leverage, MMR, min notional
   - Updates both `Play.account` (frozen dataclass) and `PlayEngineConfig` (mutable)
   - GAP-3, GAP-4, GAP-5 resolved

3. **P5 codebase cleanup finalized** — removed legacy aliases (`create_backtest_engine`, `PlayRunResult`), dead exports from `backtest/__init__.py`, condensed TODO sections

**State of the codebase:**
- pyright: 0 errors
- All 170/170 synthetic plays passing, 60/60 real-data plays passing
- Branch: `feature/unified-engine`, up to date with remote

**Next session priorities:**
- GAP-1 (CRITICAL): Wire `get_warmup_from_specs()` into `LiveDataProvider`
- GAP-2 (HIGH): REST API fallback for warmup data
- P0 remaining: live parity rubric, demo 24h validation, sub-loop activation

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
