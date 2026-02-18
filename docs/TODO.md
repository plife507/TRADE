# TRADE TODO

Single source of truth for all open work, bugs, and task progress.

---

## Completed Work (archived)

| Item | Status | Reference |
|------|--------|-----------|
| Liquidation Parity (Bybit) | DONE | `docs/LIQUIDATION_PARITY_REVIEW.md` |
| Fast Parallel Validation | DONE | Phases 1-7 complete. 1 open gate: `validate real` 61/61 (needs data sync) |
| Health Audit Fixes | DONE | `docs/HEALTH_REPORT_2026_02_18.md` |
| Full Codebase Review | DONE | `docs/architecture/` (10 files, 253 KB, 120 findings) |
| Backtest Safety Gaps 3-6 | DONE | GAP-3/4/5/6 all FIXED |

---

## P0: Codebase Bug Fixes

**Source**: Deep line-by-line review of ~269 Python files (~80,500 lines).
**Full details**: `docs/architecture/FINDINGS_SUMMARY.md` (120 findings: 7 CRIT, 16 HIGH, 53 MED, 44 LOW)
**Per-domain reviews**: `docs/architecture/*_REVIEW.md` (8 files)

### Gate 1: DSL Critical Fixes

These 5 bugs break core Play functionality. Setup references fail, valid operators are rejected, exit detection is broken, and risk config silently misconfigures.

- [ ] **DSL-CRIT-1** `src/backtest/rules/evaluation/core.py:92` — `_setup_expr_cache` never populated in `ExprEvaluator`. All `setup:` references fail at runtime with `UNKNOWN_SETUP_REF`. Fix: wire setup cache population from compiled blocks.
- [ ] **DSL-CRIT-2** `src/backtest/rules/registry.py:52` — `near_pct`, `near_abs`, `between`, `in` missing from `OPERATOR_REGISTRY`. `validate_operator()` rejects valid plays. Fix: add all 4 operators to registry.
- [ ] **DSL-CRIT-3** `src/backtest/execution_validation.py:213` — `_play_has_exit_actions()` checks `else_clause` but `Block` uses `else_emit`. Exit detection in `else:` branches always fails. Fix: change attribute name.
- [ ] **DSL-CFG-001** `src/backtest/play/config_models.py:183` — `max_drawdown_pct` auto-converts `< 1.0` to percent for defaults but not user values. `0.25` silently becomes 0.25% instead of 25%. Fix: remove magic threshold or apply consistently.
- [ ] **BT-CRIT-1** `src/backtest/risk_policy.py:274` — `create_risk_policy()` silently defaults to `initial_equity=10000.0` when `risk_mode=rules` and `risk_profile=None`. ALL FORWARD violation. Fix: raise `ValueError`.
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: pyright 0 errors

### Gate 2: Sim Parity Fixes

3 bugs that make backtest sim diverge from Bybit. Liquidation understates equity, bankruptcy price is wrong, forced closes are mislabeled.

- [ ] **SIM-HIGH-1** `src/backtest/sim/exchange.py:702` — Liquidation fee double-counted. `apply_exit(fee=liquidation_fee)` + `apply_liquidation_fee()` deducts fee twice. Fix: remove duplicate call.
- [ ] **SIM-HIGH-2** `src/backtest/sim/liquidation/liquidation_model.py:94` — `calculate_bankruptcy_price()` missing taker fee term. Bybit formula: `EP * (1 - IMR + takerFeeRate)`. Fix: add fee term.
- [ ] **SIM-HIGH-3** `src/backtest/sim/exchange.py:1048` — `force_close` and `end_of_data` exits tagged as `FillReason.SIGNAL`. Fix: add entries to `_determine_fill_reason()`.
- [ ] **GATE**: `python trade_cli.py validate standard` passes
- [ ] **GATE**: `python scripts/verify_trade_math.py --play V_RISK_001` passes

### Gate 3: Warmup / GAP-1

Warmup hardcoded to 100 bars. Indicators requiring >100 bars (EMA-200) evaluate on insufficient data.

- [ ] **ENG-001** `src/engine/play_engine.py` — Engine has no internal warmup counter. Relies entirely on runner to skip bars. Fix: add warmup bar counter to engine.
- [ ] **BT-007** `src/backtest/runner.py` + `config/defaults.yml` — Warmup fallback to hardcoded 100 bars when preflight skipped. Fix: always compute from indicator requirements.
- [ ] **IND-006** `src/backtest/indicator_registry.py` — No validation that warmup estimates match actual `is_ready` thresholds. Fix: add estimate-vs-actual validation.
- [ ] **GAP-2** `src/engine/adapters/live.py` — No REST API fallback for warmup data. `_load_tf_bars()` tries buffer -> DuckDB -> gives up. Fix: add REST `get_klines()` fallback.
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: EMA-200 play warms up correctly (first signal after bar 200)

### Gate 4: Live Safety (pre-deployment blockers)

12 bugs that must be fixed before any live trading. Close ordering, WS reconnect, stale data, broken pre-live gates.

- [ ] **DATA-018** `src/core/exchange_orders_manage.py` — TP/SL cancelled BEFORE close market order. If close fails, position has no protection. Fix: close first, cancel conditionals after.
- [ ] **DATA-010** `src/data/realtime_bootstrap.py:559` — Dynamic symbol subscriptions lost after WS reconnect. Trades execute blind. Fix: persist and re-subscribe on reconnect.
- [ ] **ENG-009** `src/engine/runners/live_runner.py:995` — Stale queued candles processed after reconnect against stale indicator state. Fix: drain queue on reconnect, re-warm.
- [ ] **ENG-013** `src/engine/adapters/live.py:896` — Warmup candles have `ts_close=ts_open`. SubLoop gets zero-duration candles. Fix: compute proper `ts_close`.
- [ ] **ENG-006** `src/engine/runners/live_runner.py:176` — Position sync gate blocks trading 5 min without retry. Fix: add exponential backoff retry.
- [ ] **ENG-008** `src/engine/adapters/live.py:2287` — `reduce_only` only set on one close path. Other paths risk accidental reverse. Fix: audit all close paths, enforce `reduce_only=True`.
- [ ] **DATA-005** `src/core/safety.py:86` — `DailyLossTracker` seed failure permanently blocks trading. Fix: add retry with backoff.
- [ ] **DATA-007** `src/core/exchange_orders_market.py:48` — `reduce_only` defaults to `False`. Fix: add dedicated `market_close_tool` with enforced `reduce_only=True`.
- [ ] **CLI-011** `src/cli/validate.py:1144` — Pre-live conflict detection never fires. `isinstance(dict, list)` is always False. Fix: match tool return type.
- [ ] **CLI-010** `src/cli/validate.py:1111` — Pre-live balance gate reads wrong key `"available_balance"` vs `"available"`. Always sees 0.0. Fix: correct key.
- [ ] **IND-004** `src/indicators/incremental/stateful.py` — PSAR factory param names (`af_start`, `af_max`) silently ignored. Fix: validate param names, reject unknown.
- [ ] **DSL-006** `src/backtest/execution_validation.py:93` — `BUILTIN_FEATURES` includes OI/funding without preflight guarantee. Fix: add OI/funding checks to preflight.
- [ ] **GATE**: `python trade_cli.py validate pre-live --play X` passes with correct balance/conflict checks
- [ ] **GATE**: pyright 0 errors

### Gate 5: DSL & Engine MED Fixes

18 medium-severity bugs in DSL evaluation, engine adapters, and play parsing.

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | DSL-HIGH-1 | `strategy_blocks.py:256` | No conflict resolution when entry+exit fire on same bar |
| 2 | DSL-PLAY-001 | `play.py:698` | `tf: exec` in feature config not resolved to concrete TF |
| 3 | DSL-PLAY-002 | `play.py:349` | Unrecognized condition keys only warned, not rejected |
| 4 | DSL-RISK-001 | `risk_model.py:181` | Legacy `atr_key` fallback — ALL FORWARD violation |
| 5 | DSL-RISK-002 | `risk_model.py:224` | Same `atr_key` fallback in `TakeProfitRule` |
| 6 | DSL-EXEC-002 | `execution_validation.py:492` | Duration window nodes not walked for warmup refs |
| 7 | DSL-FREG-001 | `feature_registry.py:502` | Silent 50-bar warmup default on error — ALL FORWARD violation |
| 8 | DSL-002 | `dsl_parser.py:117` | `is_condition_list` relies on disjoint operator sets |
| 9 | DSL-004 | `condition_ops.py:171` | Cross-above uses `<=` (touch-and-cross semantic) |
| 10 | ENG-002 | `play_engine.py` | `EngineState.WARMING_UP` defined but never transitioned to |
| 11 | ENG-004 | `signal/subloop.py:128` | `TF_MINUTES` duplicated to avoid circular imports |
| 12 | ENG-007 | `live_runner.py:197` | `_candle_queue` unbounded — OOM possible during stalls |
| 13 | ENG-BUG-002 | `play_engine.py:436` | `exchange.step()` double-step latent risk |
| 14 | ENG-BUG-004 | `play_engine.py:397` | `SizingModel.update_equity()` uses stale equity on WS failure |
| 15 | ENG-BUG-006 | `signal/subloop.py:196` | `end_1m` clamping silently truncates last 1m bars |
| 16 | ENG-BUG-010 | `live_runner.py:976` | `_seen_candles` not cleared on reconnect |
| 17 | ENG-BUG-014 | `adapters/live.py:611` | TF dedup cross-contaminates caches when TFs are equal |
| 18 | ENG-BUG-015 | `adapters/live.py:265` | `LiveIndicatorCache.update()` uses `np.append()` — O(n) per bar |

- [ ] Fix all 18 items above
- [ ] **GATE**: `python trade_cli.py validate standard` passes
- [ ] **GATE**: pyright 0 errors

### Gate 6: Sim & Backtest MED Fixes

15 medium-severity bugs in simulation, metrics, risk sizing, and backtest infrastructure.

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | SIM-001 | `exchange.py:636` | TP/SL exit timestamp is exec bar `ts_open`, not 1m trigger time |
| 2 | SIM-006 | `liquidation_model.py:307` | `estimate_liquidation_price()` ignores `mm_deduction` |
| 3 | SIM-MED-1 | `ledger.py:285` | Margin not recalculated after `apply_partial_exit()` within same bar |
| 4 | SIM-MED-2 | `execution_model.py:551` | Slippage applied to limit TP exits |
| 5 | SIM-MED-3 | `metrics/metrics.py` | `ExchangeMetrics` built but never wired |
| 6 | SIM-MED-4 | `constraints/constraints.py` | `Constraints` built but never wired |
| 7 | BT-002 | `runner.py:1050` | `_finalize_logger_on_error` catches silently |
| 8 | BT-005 | `feed_store.py:43` | Deprecated `utcfromtimestamp` (Python 3.12+) |
| 9 | BT-WARN-2 | `simulated_risk_manager.py:330` | `_size_risk_based()` missing `* max_lev` multiplier |
| 10 | BT-WARN-4 | `preflight.py:327` | Legacy warmup wrapper still in use |
| 11 | BT-WARN-5 | `rollup_bucket.py:85` | `freeze()` returns `inf`/`-inf` when empty |
| 12 | IND-FISHER-001 | `stateful.py` | Fisher `is_ready` fires on seeding bar (value=0.0) |
| 13 | IND-FACTORY-001 | `factory.py:262` | Unknown indicator type silently returns `None` |
| 14 | IND-001 | `core.py` | Inconsistent `is_ready` semantics across indicators |
| 15 | IND-REG-003 | `indicator_registry.py:154` | `_warmup_fisher` under-estimates by 1 bar |

- [ ] Fix all 15 items above
- [ ] **GATE**: `python trade_cli.py validate standard` passes

### Gate 7: Data, CLI & Forge MED Fixes

20 medium-severity bugs in data layer, CLI tools, and forge validation.

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | DATA-003 | `realtime_state.py` | No staleness enforcement on WS data reads (GAP-2) |
| 2 | DATA-006 | `safety.py:281` | `panic_close_all` doesn't retry `get_all_positions` |
| 3 | DATA-016 | `safety.py:~206` | `RiskManager.check()` bypasses `_seed_failed` block |
| 4 | DATA-011 | `realtime_bootstrap.py:1079` | `_handle_stale_connection()` never triggers reconnect |
| 5 | CLI-004 | `order_tools.py` | No dedicated `market_close_tool` with `reduce_only=True` |
| 6 | CLI-006 | `validate.py:1379` | Double-timeout in `_run_staged_gates()` — gate can take 2x timeout |
| 7 | CLI-008 | `validate.py:462` | G4/G4b no per-play timeout |
| 8 | CLI-020 | `tools/shared.py:60` | `_get_exchange_manager()` singleton not thread-safe |
| 9 | CLI-027 | `order_tools.py:928` | Batch tools return `success=True` on partial failure |
| 10 | CLI-032 | `account_tools.py:76` | Key mismatch: `exposure_usd` vs `total_exposure_usdt` |
| 11 | FORGE-007 | `play_validator.py:153` | Error code mismatch between validator variants |
| 12 | FORGE-010 | `structure_validators.py:69` | `validate_no_lookahead()` checks only first pivot |
| 13 | FORGE-011 | `structure_validators.py:119` | `validate_determinism()` uses only exec TF |
| 14 | FORGE-019 | `config.py:599` | `.env` silently shadows `api_keys.env` — no warning |
| 15 | FORGE-032 | `time_range.py:195` | `"1m"` window = 30 days — collides with 1-minute convention |
| 16 | FORGE-035 | `run_full_suite.py:104` | DB lock retry misses some DuckDB error variants |
| 17 | IND-007 | `indicator_vendor.py` | Anchored VWAP excluded from parity audit |
| 18 | FORGE-001 | `synthetic_data.py` | Multi-TF bar dilation dilutes patterns ~96x |
| 19 | FORGE-008 | `audit_incremental_parity.py` | PSAR parity check uses faked `mean_abs_diff=0.0` |
| 20 | DATA-001 | `historical_data_store.py` | DuckDB file locking on Windows (mitigated by 3-DB arch) |

- [ ] Fix all 20 items above
- [ ] **GATE**: `python trade_cli.py validate full` passes

### Gate 8: LOW Priority Cleanup

44 low-severity findings. Code hygiene, dead code removal, minor edge cases.
Full list in `docs/architecture/FINDINGS_SUMMARY.md` under "LOW (44)".

**Engine** (5 items): ENG-003, ENG-BUG-001, ENG-BUG-003, ENG-BUG-005, ENG-005

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | ENG-003 | `play_engine.py` | Threading import used minimally |
| 2 | ENG-BUG-001 | `play_engine.py:427` | Hardcoded `bar_index == 100` debug sentinel |
| 3 | ENG-BUG-003 | `play_engine.py:453` | Duplicate max drawdown check |
| 4 | ENG-BUG-005 | `factory.py:422` | `create_backtest_engine()` mutates private engine attrs |
| 5 | ENG-005 | `subloop.py:157` | Fallback evaluation warns once (OK) |

**Sim** (5 items): SIM-002, SIM-003, SIM-004, SIM-005, SIM-007

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | SIM-002 | `exchange.py:674` | Liquidation check duplicates equity projection |
| 2 | SIM-003 | `exchange.py:786` | MAE/MFE not tracked on exit bar |
| 3 | SIM-004 | `ledger.py` | No validation on negative `initial_capital` |
| 4 | SIM-005 | `ledger.py` | `debug_check_invariants` defaults to False |
| 5 | SIM-007 | `liquidation_model.py:68` | Bankruptcy price omits fee-to-close term |

**Backtest** (6 items): BT-001, BT-003, BT-004, BT-006, BT-WARN-1, BT-WARN-3

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | BT-001 | `runner.py` | GateFailure catch relies on default `success=False` (OK) |
| 2 | BT-003 | `runner.py:965` | Terminal risk gate uses try/except ValueError |
| 3 | BT-004 | `metrics.py` | Drawdown decimal/percent convention (documented, OK) |
| 4 | BT-006 | `feed_store.py` | FeedStore mutable despite "immutable" contract |
| 5 | BT-WARN-1 | `hashes.py:39` | Defensive fallback in hash functions degrades determinism |
| 6 | BT-WARN-3 | `artifact_standards.py` | Legacy path silently skips Sharpe/Sortino/Calmar/CAGR |

**DSL** (3 items): DSL-003, DSL-005, DSL-SB-002, DSL-WIN-001

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | DSL-003 | `dsl_parser.py:409` | `_KNOWN_ENUM_VALUES` hardcoded |
| 2 | DSL-005 | `condition_ops.py` | `dispatch_operator` incomplete (between/in elsewhere, OK) |
| 3 | DSL-SB-002 | `strategy_blocks.py:71` | `Intent.action` not validated against `VALID_ACTIONS` |
| 4 | DSL-WIN-001 | `window_ops.py:44` | `offset_scale` can be 0 — window looks at bar 0 |

**Indicators** (3 items): IND-002, IND-003, IND-005, IND-CMO-001

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | IND-002 | `core.py:364` | BBands running sum accumulates float drift (OK) |
| 2 | IND-003 | `core.py:884` | ADX `_adx_history.pop(0)` is O(n) |
| 3 | IND-005 | `swing.py` | PairState `(str, Enum)` mixin unusual but correct (OK) |
| 4 | IND-CMO-001 | `buffer_based.py:334` | CMO `list.pop(0)` is O(n) |

**Data** (5 items): DATA-002, DATA-004, DATA-008, DATA-012, DATA-017

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | DATA-002 | `historical_data_store.py` | `_detect_ascii_mode` runs emoji test on import (OK) |
| 2 | DATA-004 | `realtime_state.py` | Bar buffer sizes hardcoded (OK) |
| 3 | DATA-008 | `exchange_orders_market.py` | `_extract_fill_price` falls back to quote price silently |
| 4 | DATA-012 | `realtime_bootstrap.py:1139` | `get_health()` returns healthy before any data |
| 5 | DATA-017 | `safety.py:265` | `panic_close_all()` cancel-before-close ordering |

**CLI** (6 items): CLI-002, CLI-003, CLI-005, CLI-006b, CLI-007, CLI-014

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | CLI-002 | `validate.py` | Gate timeout 300s generous for quick tier (OK) |
| 2 | CLI-003 | `validate.py` | `RISK_PLAY_EXPECTATIONS` hardcoded |
| 3 | CLI-005 | `order_tools.py` | `trading_env` validated before order params (OK) |
| 4 | CLI-006b | `backtest_play_tools.py` | Backtest tool double-catches exceptions (OK) |
| 5 | CLI-007 | `trade_cli.py` | Exit codes properly propagated (OK) |
| 6 | CLI-014 | `subcommands.py:988` | `_run_play_backtest` drops CLI flags |

**Forge** (5 items): FORGE-002, FORGE-003, FORGE-004, FORGE-005, FORGE-006, FORGE-007b, FORGE-013b, FORGE-027

| # | ID | File | Issue |
|---|-----|------|-------|
| 1 | FORGE-002 | `synthetic_data.py` | Seed determinism depends on numpy RNG version (OK) |
| 2 | FORGE-003 | `synthetic_data.py` | No impossible candle validation |
| 3 | FORGE-004 | `constants.py` | DEFAULTS loaded at import time (OK) |
| 4 | FORGE-005 | `constants.py` | TABLE_SUFFIXES maps backtest to _live (documented, OK) |
| 5 | FORGE-006 | `logger.py` | Redaction over-matches on substring (safety-positive, OK) |
| 6 | FORGE-007b | `logger.py:219` | JSONL event file never rotates across midnight |
| 7 | FORGE-013b | `synthetic_data.py:1939` | `generate_synthetic_bars()` exposes only 4 of 34 patterns |
| 8 | FORGE-027 | `logger.py:52` | `REDACT_KEY_PATTERNS` missing OAuth/HTTP patterns |

- [ ] Fix actionable items (skip items marked OK)
- [ ] **GATE**: `python trade_cli.py validate full` passes
- [ ] **GATE**: pyright 0 errors

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
python trade_cli.py validate quick              # Pre-commit (~7s)
python trade_cli.py validate standard           # Pre-merge (~20s)
python trade_cli.py validate full               # Pre-release (~50s)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)

# Options
python trade_cli.py validate full --workers 4         # Control parallelism
python trade_cli.py validate full --timeout 60        # Per-play timeout (default 120s)
python trade_cli.py validate full --gate-timeout 180  # Per-gate timeout (default 300s)

# Backtest / verification
python trade_cli.py backtest run --play X --sync      # Single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/verify_trade_math.py --play X          # Math verification
```
