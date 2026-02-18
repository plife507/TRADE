# Findings Summary

All bugs and issues from the 8-domain architecture review, sorted by severity.

**Date**: 2026-02-18
**Scope**: Full codebase review across engine, sim, backtest, DSL, indicators, data, CLI, and forge domains.

---

## CRITICAL (7)

| ID | Domain | Description | File | Status |
|----|--------|-------------|------|--------|
| ENG-001 | Engine | Warmup is hardcoded boolean with no bar counter (GAP-1). Engine has no internal warmup counter; relies entirely on runner to skip correct number of bars. If runner misconfigures, indicators evaluate on insufficient data. | play_engine.py | OPEN (GAP-1) |
| BT-007 | Backtest | Warmup fallback to hardcoded 100 bars from defaults.yml. When preflight is skipped, warmup may be insufficient for indicators requiring >100 bars (e.g., EMA-200). | runner.py, config/defaults.yml | OPEN (GAP-1) |
| BT-CRIT-1 | Backtest | Silent default equity in `create_risk_policy()`. When `risk_mode=rules` is requested but `risk_profile=None`, function silently constructs `RiskProfileConfig(initial_equity=10000.0)` instead of raising. Caller gets wrong equity silently. | src/backtest/risk_policy.py:274 | OPEN |
| DSL-CRIT-1 | DSL | `_setup_expr_cache` never populated in `ExprEvaluator`. The cache is initialized empty and there is no API to populate it. All `setup:` references in plays fail at runtime with `UNKNOWN_SETUP_REF`. | src/backtest/rules/evaluation/core.py:92 | OPEN |
| DSL-CRIT-2 | DSL | `near_pct`, `near_abs`, `between`, `in` missing from `OPERATOR_REGISTRY`. All four are fully implemented and parsed but absent from the registry. `validate_operator()` rejects valid plays using these operators; `SUPPORTED_OPERATORS` incorrectly excludes them. | src/backtest/rules/registry.py:52 | OPEN |
| DSL-CRIT-3 | DSL | Wrong attribute name in `_play_has_exit_actions()`. Checks `action_block.else_clause` but `Block` dataclass uses `else_emit`. `hasattr()` always returns `False`. Exit actions in `else:` branches are NEVER detected; exit mode guarantee is silently broken. | src/backtest/execution_validation.py:213 | OPEN |
| DSL-CFG-001 | DSL | `max_drawdown_pct` format inconsistency. `AccountConfig.from_dict()` auto-converts the default `0.20` to `20.0` (percent) via `< 1.0` threshold, but does NOT apply the same conversion to user-supplied values. `max_drawdown_pct: 0.25` silently becomes a 0.25% stop instead of 25%. | src/backtest/play/config_models.py:183 | OPEN |

---

## HIGH (16)

| ID | Domain | Description | File | Status |
|----|--------|-------------|------|--------|
| ENG-006 | Engine | Position sync gate blocks trading for up to 5 min on startup failure. No retry with backoff; only periodic reconciliation can unblock. | live_runner.py:176 | OPEN |
| ENG-008 | Engine | reduce_only only set on one close path in live adapter. Other close paths may not set the flag, risking accidental reverse positions. | adapters/live.py:2287 | OPEN |
| ENG-009 | Engine | Stale queued candles processed immediately after reconnect with stale indicator state. `_reconnect()` transitions to RUNNING before `_sync_positions_on_startup()` completes. Candles queued during outage are processed against stale indicator buffers. | src/engine/runners/live_runner.py:995 | OPEN |
| ENG-013 | Engine | `ts_close` set to `ts_open` for warmup candles loaded from DuckDB/REST. `SubLoopEvaluator` uses `ts_close` for 1m range lookup; structure detectors receive zero-duration candles. | src/engine/adapters/live.py:896 | OPEN |
| SIM-HIGH-1 | Sim | Liquidation fee double-counted. `_close_position()` passes `fee=liquidation_fee` into `apply_exit()`, then `apply_liquidation_fee()` is called again, deducting the same fee twice. Every liquidation understates equity. | src/backtest/sim/exchange.py:702, liquidation_model.py:159 | OPEN |
| SIM-HIGH-2 | Sim | `calculate_bankruptcy_price()` missing taker fee term. Bybit formula requires subtracting `fee_rate * entry_price` for longs. Settlement price is systematically more favorable than Bybit. | src/backtest/sim/liquidation/liquidation_model.py:94 | OPEN |
| SIM-HIGH-3 | Sim | `force_close` and `end_of_data` exits tagged as `FillReason.SIGNAL`. `_determine_fill_reason()` does not map `"force_close"` or `"end_of_data"` exit types. Metrics for forced exits are mislabeled. | src/backtest/sim/exchange.py:1048 | OPEN |
| DSL-006 | DSL | BUILTIN_FEATURES includes open_interest/funding_rate without data availability guarantee. Preflight checks OHLCV but not OI/funding tables. | execution_validation.py:93 | OPEN |
| DSL-HIGH-1 | DSL | No conflict resolution when entry and exit both fire on same bar from different blocks. `BlockSet.execute()` returns intents from ALL firing blocks with no priority contract. Undefined behavior at DSL layer. | src/backtest/rules/strategy_blocks.py:256 | OPEN |
| IND-004 | Indicators | PSAR factory param names silently ignored. Wrong names (af_start, af_max) produce default behavior without error. | stateful.py (PSAR) | OPEN |
| IND-006 | Indicators | No centralized warmup estimate registry. Warmup calculator must know exact bar count per indicator but no validation that estimates match actual is_ready thresholds. | indicator_registry.py | OPEN (GAP-1) |
| DATA-005 | Data | DailyLossTracker seed failure permanently blocks trading. No retry mechanism; requires process restart. | safety.py:86 | OPEN |
| DATA-010 | Data | Dynamic symbol subscriptions lost after WebSocket reconnect. pybit does not persist dynamically added subscriptions. After reconnect, symbols added via `subscribe_symbol_dynamic()` silently stop receiving data. Trades execute blind. | src/data/realtime_bootstrap.py:559 | OPEN |
| DATA-018 | Data | Cancel TP/SL conditional orders BEFORE placing close market order. If the close order fails, position is left open with no SL/TP protection. Direct violation of fail-closed live safety principle. | src/core/exchange_orders_manage.py (close_position) | OPEN |
| CLI-008 | CLI | G4/G4b run sequential plays with no per-play timeout. A single hung play blocks the entire gate thread indefinitely. Inconsistent with G8-G13 which use `ProcessPoolExecutor` with per-play timeouts. | src/cli/validate.py:462-508 | OPEN |
| CLI-011 | CLI | PL3 (pre-live conflict detection) never fires. `list_open_positions_tool()` returns a dict but code checks `isinstance(raw_data, list)` which is always `False`. Gate silently passes regardless of open positions. | src/cli/validate.py:1144 | OPEN |

---

## MED (53)

| ID | Domain | Description | File | Status |
|----|--------|-------------|------|--------|
| ENG-002 | Engine | EngineState.WARMING_UP defined but never transitioned to in process_bar. Dead state. | play_engine.py | OPEN |
| ENG-004 | Engine | TF_MINUTES duplicated in subloop.py to avoid circular imports. Maintenance drift risk. | signal/subloop.py:128 | OPEN |
| ENG-007 | Engine | _candle_queue is unbounded (maxsize=0). OOM possible during long processing stalls. | live_runner.py:197 | OPEN |
| ENG-BUG-002 | Engine | `exchange.step()` double-step latent risk. `BacktestExchange.step()` is a no-op today; if made non-trivial, double-processing will silently corrupt fills. No contract enforcement. | src/engine/play_engine.py:436 | OPEN |
| ENG-BUG-004 | Engine | `SizingModel.update_equity()` uses potentially stale equity on WS failure. Called unconditionally; on WS gap, `get_equity()` may return the stale initial_equity default. | src/engine/play_engine.py:397 | OPEN |
| ENG-BUG-006 | Engine | `end_1m` clamping silently truncates last 1m bars of exec candle. No warning emitted when 1m quote feed is behind. Signals near exec-close may be missed. | src/engine/signal/subloop.py:196 | OPEN |
| ENG-BUG-010 | Engine | `_seen_candles` set NOT cleared on reconnect. Catch-up candles re-delivered after reconnect may be rejected as duplicates. | src/engine/runners/live_runner.py:976 | OPEN |
| ENG-BUG-014 | Engine | TF deduplication logic cross-contaminates indicator caches when non-adjacent TFs are equal (e.g., `med_tf=1h` and `high_tf=1h`). High TF role falls back to low TF indicators. | src/engine/adapters/live.py:611 | OPEN |
| ENG-BUG-015 | Engine | `LiveIndicatorCache.update()` uses `np.append()` -- O(n) per bar. At 1m frequency: ~100 MB/hour of allocation pressure causing GC pauses. | src/engine/adapters/live.py:265 | OPEN |
| SIM-001 | Sim | TP/SL exit timestamp is exec bar ts_open, not actual 1m trigger time. Wrong holding time in trade records. | exchange.py:636 | OPEN |
| SIM-006 | Sim | estimate_liquidation_price() silently ignores mm_deduction parameter. | liquidation_model.py:307 | OPEN |
| SIM-MED-1 | Sim | After `apply_partial_exit()`, `_used_margin_usdt` and `_maintenance_margin_usdt` reflect pre-close size until next mark-price update. New entry in same bar may be incorrectly rejected. | src/backtest/sim/ledger.py:285 | OPEN |
| SIM-MED-2 | Sim | Slippage applied to limit TP exits. For `tp_order_type == "Limit"`, market-order slippage is added in addition to the correct maker fee, overstating costs. | src/backtest/sim/execution/execution_model.py:551 | OPEN |
| SIM-MED-3 | Sim | `ExchangeMetrics` fully built but not wired into `SimulatedExchange`. Exchange-level slippage, fee, and liquidation metrics never collected during backtests. | src/backtest/sim/metrics/metrics.py | OPEN |
| SIM-MED-4 | Sim | `Constraints` fully built but not wired into execution pipeline. Tick size, lot size, and min notional constraints never applied to orders before execution. | src/backtest/sim/constraints/constraints.py | OPEN |
| BT-002 | Backtest | _finalize_logger_on_error catches exceptions silently with pass. | runner.py:1050 | OPEN |
| BT-005 | Backtest | _np_dt64_to_datetime uses deprecated utcfromtimestamp (Python 3.12+). | feed_store.py:43 | OPEN |
| BT-WARN-2 | Backtest | Cap inconsistency in `_size_risk_based()`. Omits `* max_lev` multiplier vs `_size_percent_equity()`. Produces silently smaller positions than expected when `risk_mode=risk_based` with high leverage. | src/backtest/simulated_risk_manager.py:330 | OPEN |
| BT-WARN-4 | Backtest | Legacy warmup wrapper `calculate_warmup_start()` still in use inside `_validate_all_pairs()` despite being labeled as legacy. Canonical path is `compute_warmup_requirements(play)`. | src/backtest/runtime/preflight.py:327 | OPEN |
| BT-WARN-5 | Backtest | `ExecRollupBucket.freeze()` returns `inf`/`-inf` when no 1m bars accumulated. No enforcement of the guard at the strategy interface layer. | src/backtest/runtime/rollup_bucket.py:85 | OPEN |
| DSL-002 | DSL | is_condition_list relies on disjoint operator sets. Future collision risk. | dsl_parser.py:117 | OPEN |
| DSL-004 | DSL | Cross-above uses <= for previous comparison (touch-and-cross semantic). | condition_ops.py:171 | OPEN |
| DSL-PLAY-001 | DSL | `tf: exec` in feature config NOT resolved to concrete TF. `_parse_features()` explicitly skips resolution for the exec role. Feature retains literal `"exec"` and fails to match any buffer at runtime. | src/backtest/play/play.py:698 | OPEN |
| DSL-PLAY-002 | DSL | Unrecognized condition keys only warned, not rejected. A typo like `near_pects: 5` is silently dropped. | src/backtest/play/play.py:349 | OPEN |
| DSL-RISK-001 | DSL | Legacy `atr_key` fallback in `StopLossRule.from_dict()`. `atr_feature_id=d.get("atr_feature_id") or d.get("atr_key")` silently masks typos. ALL FORWARD, NO LEGACY violation. | src/backtest/play/risk_model.py:181 | OPEN |
| DSL-RISK-002 | DSL | Same legacy `atr_key` fallback in `TakeProfitRule.from_dict()`. | src/backtest/play/risk_model.py:224 | OPEN |
| DSL-EXEC-002 | DSL | Duration window nodes (`HoldsForDuration`, `OccurredWithinDuration`, `CountTrueDuration`) not walked in `extract_rule_feature_refs()`. Feature refs inside duration-based windows are invisible to warmup calculation. | src/backtest/execution_validation.py:492 | OPEN |
| DSL-FREG-001 | DSL | Silent 50-bar warmup default in `get_warmup_for_tf()`. `except Exception: return 50` masks misconfigured features. ALL FORWARD, NO LEGACY violation. | src/backtest/feature_registry.py:502 | OPEN |
| IND-001 | Indicators | Inconsistent is_ready semantics (> vs >= vs len check) across indicators. | core.py | KNOWN |
| IND-007 | Indicators | Anchored VWAP excluded from parity audit. No automated validation. | indicator_vendor.py | KNOWN |
| IND-FISHER-001 | Indicators | `IncrementalFisher.is_ready` fires on artificial seeding bar where `value == 0.0`. Conditions like `fisher_value > 0` can trigger falsely. Fix: change to `_count > length`. | src/indicators/incremental/stateful.py | OPEN |
| IND-FACTORY-001 | Indicators | Unknown indicator type strings silently return `None` from factory. Caller cannot distinguish typo from registry-known vectorized-only indicator. Should raise `ValueError`. | src/indicators/incremental/factory.py:262 | OPEN |
| DATA-001 | Data | DuckDB file locking on Windows prevents concurrent access. Mitigated by 3-DB architecture. | historical_data_store.py | KNOWN |
| DATA-003 | Data | No staleness enforcement on WebSocket data reads. Relates to GAP-2. | realtime_state.py | OPEN (GAP-2) |
| DATA-006 | Data | panic_close_all retries per-position but not the batch get_all_positions call. | safety.py:281 | OPEN |
| DATA-007 | Data | reduce_only defaults to False in market_buy/sell. Callers must explicitly set True for closes. | exchange_orders_market.py:48 | OPEN |
| DATA-016 | Data | `RiskManager.check()` reads `_daily_pnl` directly, bypassing `_seed_failed` block. If seed failed, loss check trivially passes. | src/core/safety.py:~206 | OPEN |
| DATA-011 | Data | `_handle_stale_connection()` marks disconnected but never triggers reconnect. Relies on pybit internal reconnect which may not fire on half-open TCP state. | src/data/realtime_bootstrap.py:1079 | OPEN |
| CLI-001 | CLI | Process-level play timeout may orphan DuckDB locks on Windows. | validate.py | KNOWN |
| CLI-004 | CLI | No dedicated market_close_tool with enforced reduce_only=True. | order_tools.py | OPEN |
| CLI-006 | CLI | Double-timeout in `_run_staged_gates()`. Both `as_completed(timeout=gate_timeout)` and `future.result(timeout=gate_timeout)` use same value. Gate can consume up to `2 * gate_timeout` before being detected as hung. | src/cli/validate.py:1379 | OPEN |
| CLI-010 | CLI | PL2 reads wrong key `"available_balance"` instead of `"available"`. Gate always sees `0.0` available funds. Balance check logic is broken for the pre-live gate. | src/cli/validate.py:1111 | OPEN |
| CLI-020 | CLI | `_get_exchange_manager()` singleton not thread-safe. `hasattr` + `setattr` is not atomic; two threads can each construct a separate `ExchangeManager`, orphaning one. | src/tools/shared.py:60 | OPEN |
| CLI-027 | CLI | Batch tools return `success=True` on partial failure (`success_count > 0`). A 9/10 failure reports as success. | src/tools/order_tools.py:928 | OPEN |
| CLI-032 | CLI | Key mismatch: tool returns `"exposure_usd"` but handler reads `"total_exposure_usdt"`. Handler always displays `"N/A"`. | src/tools/account_tools.py:76 / src/cli/subcommands.py:1641 | OPEN |
| FORGE-001 | Forge | Multi-TF bar dilation dilutes patterns ~96x in synthetic data. | synthetic_data.py | KNOWN |
| FORGE-007 | Forge | Error code mismatch between `validate_play_file()` (uses `MISSING_REQUIRED_FIELD`) and `validate_play_file_unified()` (uses `DSL_PARSE_ERROR`) for identical YAML parse errors. Tools filtering by error code behave inconsistently. | src/forge/validation/play_validator.py:153 | OPEN |
| FORGE-008 | Forge | Parity audit intentionally excludes anchored_vwap. Manual verification required. | audit_incremental_parity.py | KNOWN |
| FORGE-010 | Forge | `validate_no_lookahead()` checks only the first confirmed pivot. A detector that front-runs its second or third pivot passes undetected. | src/forge/validation/structure_validators.py:69 | OPEN |
| FORGE-011 | Forge | `validate_determinism()` uses only `exec_tf` for synthetic data. Non-determinism on `high_tf`/`med_tf` feeds goes undetected. | src/forge/validation/structure_validators.py:119 | OPEN |
| FORGE-019 | Forge | Silent credential override: `.env` values silently shadow `api_keys.env` values when both set the same key. No warning emitted. | src/config/config.py:599 | OPEN |
| FORGE-032 | Forge | `"1m"` window string in `TimeRange.from_window_string()` maps to 30-day range (calendar month convention). Collides with project's universal `"1m"` = 1 minute convention. Silent wrong behavior. | src/utils/time_range.py:195 | OPEN |
| FORGE-035 | Forge | DB lock retry in `run_full_suite.py` only matches one DuckDB error string. Misses `"Could not set lock on file"` variant on some Windows configurations. Real-data suite may fail immediately instead of retrying. | scripts/run_full_suite.py:104 | OPEN |

---

## LOW (42)

| ID | Domain | Description | File | Status |
|----|--------|-------------|------|--------|
| ENG-003 | Engine | Threading import used minimally (play_hash setter only). | play_engine.py | OPEN |
| ENG-005 | Engine | Fallback evaluation warns only once (correct behavior). | subloop.py:157 | OK |
| ENG-BUG-001 | Engine | Hardcoded `bar_index == 100` debug sentinel. Never fires in live mode. Belongs to GAP-1 cleanup. | src/engine/play_engine.py:427 | OPEN |
| ENG-BUG-003 | Engine | Duplicate max drawdown check in `process_bar` and `BacktestRunner`. Wastes one `get_equity()` call per bar. | play_engine.py:453 / backtest_runner.py:413 | OPEN |
| ENG-BUG-005 | Engine | `create_backtest_engine()` directly mutates private engine attributes post-construction. Bypasses initialization guards. | src/engine/factory.py:422 | OPEN |
| SIM-002 | Sim | Liquidation check duplicates equity projection logic. | exchange.py:674 | OPEN |
| SIM-003 | Sim | MAE/MFE not tracked on exit bar. Slightly understated. | exchange.py:786 | OPEN |
| SIM-004 | Sim | No validation on negative initial_capital. | ledger.py | OPEN |
| SIM-005 | Sim | debug_check_invariants defaults to False. | ledger.py | OPEN |
| SIM-007 | Sim | Bankruptcy price formula omits fee-to-close term. | liquidation_model.py:68 | OPEN |
| BT-001 | Backtest | GateFailure catch relies on default success=False. | runner.py | OK |
| BT-003 | Backtest | Terminal risk gate uses try/except ValueError. | runner.py:965 | OPEN |
| BT-004 | Backtest | Drawdown decimal/percent convention documented but confusing. | metrics.py | OK |
| BT-006 | Backtest | FeedStore mutable despite "immutable" contract. | feed_store.py | OPEN |
| BT-WARN-1 | Backtest | Defensive fallback in hash functions breaks determinism guarantee. `compute_trades_hash()` falls back to subset of fields if `to_dict()` missing, with no warning. | src/backtest/artifacts/hashes.py:39 | OPEN |
| BT-WARN-3 | Backtest | `compute_results_summary()` legacy path silently skips Sharpe, Sortino, Calmar, CAGR when `metrics=None`. | src/backtest/artifacts/artifact_standards.py | OPEN |
| DSL-003 | DSL | _KNOWN_ENUM_VALUES hardcoded. Unknown enums treated as features. | dsl_parser.py:409 | OPEN |
| DSL-005 | DSL | dispatch_operator incomplete (between/in handled elsewhere). | condition_ops.py | OK |
| DSL-SB-002 | DSL | `Intent` action not validated against `VALID_ACTIONS` in `__post_init__`. Typos pass construction and only fail at engine dispatch. | src/backtest/rules/strategy_blocks.py:71 | OPEN |
| DSL-WIN-001 | DSL | `offset_scale` can be 0 when `anchor_tf < exec_tf`. All window offsets silently become 0 -- window looks at bar 0 repeatedly. Should raise `ValueError`. | src/backtest/rules/evaluation/window_ops.py:44 | OPEN |
| IND-002 | Indicators | BBands running sum accumulates floating-point drift. | core.py:364 | OK |
| IND-003 | Indicators | ADX _adx_history uses list.pop(0) which is O(n). | core.py:884 | OPEN |
| IND-005 | Indicators | PairState uses (str, Enum) mixin. Unusual but correct. | swing.py | OK |
| IND-CMO-001 | Indicators | `IncrementalCMO` uses `list.pop(0)` O(n) for gains/losses lists. Should use `collections.deque(maxlen=length)`. | src/indicators/incremental/buffer_based.py:334 | OPEN |
| IND-REG-003 | Indicators | `_warmup_fisher` under-estimates warmup by 1 bar. Returns `length` but seeding bar outputs artificial `0.0`. | src/backtest/indicator_registry.py:154 | OPEN |
| DATA-002 | Data | _detect_ascii_mode runs emoji test on every import. | historical_data_store.py | OK |
| DATA-004 | Data | Bar buffer sizes hardcoded in realtime_models.py. | realtime_state.py | OK |
| DATA-008 | Data | _extract_fill_price falls back to quote price silently. | exchange_orders_market.py | OPEN |
| DATA-017 | Data | `panic_close_all()` cancel-before-close leaves position unprotected on partial failure. Cancel happens before close. | src/core/safety.py:265 | OPEN |
| DATA-012 | Data | `get_health()` returns `healthy=True` before any data at startup. At startup with pybit still connecting, `using_rest_fallback=True` making health report as healthy when not ready. | src/data/realtime_bootstrap.py:1139 | OPEN |
| CLI-002 | CLI | Gate timeout (300s) generous for quick tier. | validate.py | OK |
| CLI-003 | CLI | RISK_PLAY_EXPECTATIONS hardcoded. | validate.py | OPEN |
| CLI-005 | CLI | trading_env validated before order params. | order_tools.py | OK |
| CLI-006 | CLI | Backtest tool double-catches exceptions. | backtest_play_tools.py | OK |
| CLI-007 | CLI | Exit codes properly propagated. | trade_cli.py | OK |
| CLI-014 | CLI | `_run_play_backtest` drops CLI flags (`--sync`, `--smoke`, `--validate`, `--strict`). Not forwarded to `backtest_run_play_tool`. | src/cli/subcommands.py:988 | OPEN |
| FORGE-002 | Forge | Seed determinism depends on numpy RNG version. | synthetic_data.py | OK |
| FORGE-003 | Forge | No impossible candle validation in synthetic generation. | synthetic_data.py | OPEN |
| FORGE-004 | Forge | DEFAULTS loaded at import time (fail-fast). | constants.py | OK |
| FORGE-005 | Forge | TABLE_SUFFIXES maps backtest to _live (documented). | constants.py | OK |
| FORGE-006 | Forge | Redaction over-matches on substring (safety-positive). | logger.py | OK |
| FORGE-007b | Forge | JSONL event file never rotates across midnight. Long-running sessions produce single file spanning multiple days. | src/utils/logger.py:219 | OPEN |
| FORGE-013b | Forge | `generate_synthetic_bars()` exposes only 4 of 34 patterns. Local dict hard-coded to legacy patterns instead of delegating to `PATTERN_GENERATORS` registry. | src/forge/validation/synthetic_data.py:1939 | OPEN |
| FORGE-027 | Forge | `REDACT_KEY_PATTERNS` missing common HTTP/OAuth patterns: `bearer`, `jwt`, `access_token`, `refresh_token`, `x-api-key`, `x-api-secret`. These log in plaintext. | src/utils/logger.py:52 | OPEN |

---

## Summary Statistics

| Severity | Count | Open | Known | OK |
|----------|-------|------|-------|----|
| CRITICAL | 7 | 7 | 0 | 0 |
| HIGH | 16 | 16 | 0 | 0 |
| MED | 53 | 47 | 6 | 0 |
| LOW | 44 | 28 | 0 | 16 |
| **Total** | **120** | **98** | **6** | **16** |

---

## Priority Remediation Order

1. **DSL Correctness (CRITICAL)**: DSL-CRIT-1, DSL-CRIT-2, DSL-CRIT-3 -- Setup cache never populated (all setup: refs fail), 4 operators missing from registry (validation rejects valid plays), else_emit typo (exit mode guarantee broken).
2. **Config Safety (CRITICAL)**: BT-CRIT-1, DSL-CFG-001 -- Silent default equity in risk policy, max_drawdown_pct user value not converted from decimal to percent.
3. **GAP-1 (CRITICAL)**: ENG-001, BT-007, IND-006 -- Add warmup bar counter to engine, compute warmup from actual indicator requirements, validate estimates match is_ready.
4. **Live Safety (HIGH)**: DATA-018, DATA-010, ENG-009, ENG-013 -- Fix close-before-cancel ordering, re-subscribe dynamic symbols on reconnect, flush stale queue after reconnect, fix ts_close for warmup candles.
5. **Sim Correctness (HIGH)**: SIM-HIGH-1, SIM-HIGH-2, SIM-HIGH-3 -- Liquidation fee double-counted, bankruptcy price missing fee term, forced closes mislabeled as SIGNAL.
6. **Pre-Live Gate Integrity (HIGH)**: CLI-011, CLI-008 -- PL3 conflict detection never fires, G4/G4b no per-play timeout.
7. **Live Safety Existing (HIGH)**: ENG-006, ENG-008, DATA-005, DATA-007 -- Fix position sync retry, audit reduce_only on all close paths, add DailyLossTracker retry.
8. **Data Gaps (HIGH)**: DSL-006, DATA-003 -- Preflight checks for OI/funding, fail-closed staleness enforcement.
9. **Risk Sizing (MED)**: BT-WARN-2 -- Leverage multiplier missing in risk_based sizing.
10. **Config Safety (MED)**: FORGE-032 -- "1m" window string maps to 30 days (silent wrong behavior).
11. **Code Hygiene (LOW)**: Remaining items per domain review.
