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

### Full Codebase Audit (2026-02-17)

94 issues found across 6 subsystems. P0s all fixed. P1/P2 second pass completed 2026-02-17.

#### P0 Critical — Engine Core

| # | Status | File | Issue |
|---|--------|------|-------|
| BUG-E1 | **FIXED** | `engine/play_engine.py:232` | `_snapshot_view` never assigned — ATR trailing stops silently broken for all backtests |
| BUG-E2 | **FIXED** | `engine/play_engine.py:824` | `_update_high_tf_med_tf_indices()` never passes `exec_idx` to `update_indices()` — exec TF index stuck at 0 |
| BUG-E3 | **FIXED** | `engine/play_engine.py:373` | Misleading comment says `exchange.step()` handles TP/SL — it's a no-op in backtest; fills happen in runner before engine |

#### P0 Critical — Sim/Exchange

| # | Status | File | Issue |
|---|--------|------|-------|
| BUG-S1 | **FIXED** | `sim/liquidation/liquidation_model.py:151-198` | Liquidation price formula ignores MM at mark price — missing `(1 ± MMR)` denominator |
| BUG-S2 | **FIXED** | `simulated_risk_manager.py:36-75` | Same liquidation formula error in simplified version |

#### P0 Critical — Security / Live Safety (must fix before live)

| # | Status | File | Issue |
|---|--------|------|-------|
| BUG-SEC1 | **FIXED** | `core/exchange_orders_stop.py:288` | TP/SL calculated from pre-fill price, not actual fill price — SL at wrong distance in volatile markets |
| BUG-SEC2 | **FIXED** | `core/exchange_orders_stop.py:356-385` | Position left unprotected if SL order + emergency close_position both fail |
| BUG-SEC3 | **FIXED** | `core/order_executor.py:753-757` | Price deviation guard fails open — allows orders when price check errors |
| BUG-SEC4 | **FIXED** | `core/exchange_orders_market.py` etc. | No validation of negative/zero `usd_amount` in order functions |
| BUG-SEC5 | **FIXED** | `core/safety.py:118-122` | `DailyLossTracker.seed_from_exchange` failure silently resets to $0 — bot can exceed daily loss limit on restart |
| BUG-SEC6 | **FIXED** | `core/safety.py:174` | `PanicState.trigger_time` uses naive `datetime.now()` instead of `datetime.now(timezone.utc)` |
| BUG-SEC7 | **FIXED** | `core/exchange_orders_manage.py:289-416` | Batch order functions bypass ALL risk controls (RiskManager, SafetyChecks, panic check, price deviation) |

#### P0 Critical — Runtime/Rules

| # | Status | File | Issue |
|---|--------|------|-------|
| BUG-R1 | **FIXED** | `rules/evaluation/shift_ops.py:128-132` | `SetupRef` not shifted inside window operators — evaluates at current-bar values instead of historical |

#### Validation Fix

| # | Status | File | Issue |
|---|--------|------|-------|
| BUG-V1 | **FIXED** | `cli/smoke_tests/data.py:21,454` | Stale import `sync_to_now_and_sync_data_tool` → `sync_forward_tool` — broke `validate standard` |

#### P1 High — Second Pass (2026-02-17)

| # | Status | File | Issue |
|---|--------|------|-------|
| BUG-P1-1 | **FIXED** | `engine/play_engine.py:1586` | Expired limit orders dropped from tracking when cancel fails — phantom orders on exchange |
| BUG-P1-2 | **FIXED** | `sim/exchange.py:944` | Limit fill position uses `order.size_usdt` not actual fill notional (`qty × fill_price`) |
| BUG-P1-3 | **FIXED** | `core/safety.py:248` | `panic_close_all` timestamp uses local time instead of UTC |
| BUG-P1-4 | **FIXED** | `core/safety.py:193` | Panic callback catches only 3 exception types — any other kills remaining callbacks |
| BUG-P1-5 | **FIXED** | `core/exchange_manager.py:270` | `get_price` returns 0.0 on missing ticker — downstream division by zero / free orders |
| BUG-P1-6 | **FIXED** | `core/exchange_orders_manage.py:109` | `cancel_all_orders` partial success (1/N symbols) reports as success |
| BUG-P1-7 | **FIXED** | `core/exchange_orders_stop.py:416` | Orphan TP orders placed after SL failure + emergency close |
| BUG-P1-8 | **FIXED** | `core/safety.py:316` | `panic_close_all` position verification uses `p.size > 0` — misses short positions |

#### P2 Medium — Second Pass (2026-02-17)

| # | Status | File | Issue |
|---|--------|------|-------|
| BUG-P2-1 | **FIXED** | `engine/play_engine.py:648` | `_total_trades` inflated for unfilled limit order submissions |
| BUG-P2-2 | **FIXED** | `simulated_risk_manager.py:294` | Cap 1 formula missing `× leverage` — inconsistent with SizingModel |
| BUG-P2-3 | **FIXED** | `engine/play_engine.py` | `max_drawdown_pct` declared but never enforced — now halts engine at threshold |
| BUG-P2-4 | **FIXED** | `sim/exchange.py:1189` | Partial close doesn't pro-rate `funding_pnl_cumulative` — double-counts on final close |
| BUG-P2-5 | **FIXED** | `core/exchange_orders_market.py:34` | `avgPrice = "0"` treated as valid fill price |
| BUG-P2-6 | **FIXED** | `core/safety.py:52` | `record_loss` silently ignores positive amounts — now uses `abs()` |
| BUG-P2-7 | **FIXED** | `engine/signal/subloop.py:149` | `TF_MINUTES` missing `1d`/`1w` aliases, silent fallback to 15m — now raises ValueError |
| BUG-P2-8 | **FIXED** | `core/exchange_orders_manage.py:326` | Batch orders silently skip `qty<=0` — now logs warning + returns failed result |
| BUG-P2-9 | **FIXED** | `core/exchange_orders_market.py:38` | `_extract_fill_price` fallback to quote price without logging |

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

## Session Handoff — 2026-02-17

**Completed this session:**

1. **Full codebase audit** — 94 issues found across 6 subsystems
2. **P0 critical bug fixes (15 bugs)** — engine core, sim/exchange, security/live safety, runtime/rules, validation
3. **P1 high bug fixes (8 bugs)** — limit order tracking, fill notional, panic timestamps/callbacks, price validation, cancel semantics, orphan TPs, position verification
4. **P2 medium bug fixes (9 bugs)** — trade counting, sizing formula parity, max drawdown enforcement, funding pro-rating, avgPrice validation, record_loss semantics, TF aliases, batch logging, fill price logging

**State of the codebase:**
- pyright: 0 errors
- `validate quick`: 4/4 gates passing
- Max drawdown enforcement now active (visible in validation logs)

**Next session priorities:**
- GAP-1 (CRITICAL): Wire `get_warmup_from_specs()` into `LiveDataProvider`
- GAP-2 (HIGH): REST API fallback for warmup data
- P0 remaining: live parity rubric, demo 24h validation, sub-loop activation
- Run `validate standard` and `run_full_suite.py` to confirm no regressions from sim formula changes

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
