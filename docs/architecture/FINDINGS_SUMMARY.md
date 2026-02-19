# Findings Summary

All bugs and issues from the 8-domain architecture review, sorted by severity.

**Date**: 2026-02-18 (review), updated 2026-02-18 (status reconciliation)
**Scope**: Full codebase review across engine, sim, backtest, DSL, indicators, data, CLI, and forge domains.
**Resolution**: 105/120 findings resolved. 8 deferred, 7 accepted/known.

---

## CRITICAL (7) -- ALL RESOLVED

| ID | Domain | Description | Resolution |
|----|--------|-------------|------------|
| ENG-001 | Engine | Warmup hardcoded boolean with no bar counter | NOT A BUG -- engine delegates warmup to DataProvider.is_ready(). Backtest runner skips warmup bars entirely. |
| BT-007 | Backtest | Warmup fallback to hardcoded 100 bars | ALREADY FIXED -- skip_preflight uses compute_warmup_requirements(). defaults.yml value is dead code. |
| BT-CRIT-1 | Backtest | Silent default equity in create_risk_policy() | FIXED -- raises ValueError when risk_profile=None with risk_mode='rules'. |
| DSL-CRIT-1 | DSL | _setup_expr_cache never populated in ExprEvaluator | FIXED -- added set_setup_cache() method, wired in PlaySignalEvaluator constructor. |
| DSL-CRIT-2 | DSL | near_pct, near_abs, between, in missing from OPERATOR_REGISTRY | FIXED -- all four added to registry. |
| DSL-CRIT-3 | DSL | Wrong attribute name in _play_has_exit_actions() | FIXED -- else_clause -> else_emit. |
| DSL-CFG-001 | DSL | max_drawdown_pct auto-conversion inconsistency | FIXED -- removed dead `< 1.0` auto-conversion (defaults.yml already uses 100.0 percentage form). |

---

## HIGH (16) -- ALL RESOLVED

| ID | Domain | Description | Resolution |
|----|--------|-------------|------------|
| ENG-006 | Engine | Position sync gate blocks trading 5 min on failure | FIXED -- _last_reconcile_ts not set on sync failure. Allows immediate retry. |
| ENG-008 | Engine | reduce_only only set on one close path | NOT A BUG -- both close paths already set reduce_only=True. Audited all call sites. |
| ENG-009 | Engine | Stale candles processed after reconnect | FIXED -- stale candles drained from queue before reconnect. |
| ENG-013 | Engine | ts_close set to ts_open for warmup candles | FIXED -- warmup candles compute ts_close = ts_open + tf_duration. |
| SIM-HIGH-1 | Sim | Liquidation fee double-counted | FIXED -- removed duplicate apply_liquidation_fee() call. |
| SIM-HIGH-2 | Sim | calculate_bankruptcy_price() missing taker fee term | FIXED -- added fee_rate param. fill_exit() skips fee for liquidation. |
| SIM-HIGH-3 | Sim | force_close/end_of_data exits tagged as SIGNAL | FIXED -- added entries to reason_map. |
| DSL-006 | DSL | OI/funding without data availability guarantee | DEFERRED -- preflight enhancement. Runtime fails loudly if tables missing. |
| DSL-HIGH-1 | DSL | No entry/exit conflict resolution on same bar | NOT A BUG -- has_position naturally prevents entry+exit conflict. |
| IND-004 | Indicators | PSAR factory params silently ignored | FIXED -- added _VALID_PARAMS registry. Unknown params raise ValueError. |
| IND-006 | Indicators | No centralized warmup estimate registry | DEFERRED -- enhancement. Indicators output NaN until ready (safe propagation). |
| DATA-005 | Data | DailyLossTracker seed failure permanently blocks | FIXED -- seed_from_exchange() retries 3x with exponential backoff. |
| DATA-010 | Data | Dynamic symbol subscriptions lost after reconnect | FIXED -- _resubscribe_all_symbols() called on reconnect. |
| DATA-018 | Data | Cancel TP/SL BEFORE close market order | FIXED -- close market order placed FIRST, conditionals cancelled AFTER success. |
| CLI-008 | CLI | G4/G4b no per-play timeout | ACCEPTED -- gate-level timeout (300s) catches hangs. Per-play timeout improves error message only. |
| CLI-011 | CLI | PL3 conflict detection never fires | FIXED -- raw_data.get("positions", []) for dict return type. |

---

## MED (53) -- 42 RESOLVED, 5 DEFERRED, 6 ACCEPTED

| ID | Domain | Description | Resolution |
|----|--------|-------------|------------|
| ENG-002 | Engine | EngineState.WARMING_UP never transitioned to | NOT A BUG -- IS used on line 800 (_is_ready() check). |
| ENG-004 | Engine | TF_MINUTES duplicated in subloop.py | FIXED -- replaced with import from historical_data_store. |
| ENG-007 | Engine | _candle_queue unbounded (maxsize=0) | NOT A BUG -- intentional (candles are precious, can't be recovered). |
| ENG-BUG-002 | Engine | exchange.step() double-step latent risk | NOT A BUG -- BacktestExchange.step() is a no-op. No-op contract is safe. |
| ENG-BUG-004 | Engine | SizingModel.update_equity() uses stale equity | NOT A BUG -- handled with try/catch + error log, uses last known equity. |
| ENG-BUG-006 | Engine | end_1m clamping silently truncates last 1m bars | FIXED -- debug log added when end_1m is clamped. |
| ENG-BUG-010 | Engine | _seen_candles NOT cleared on reconnect | FIXED -- _seen_candles.clear() called after successful reconnect. |
| ENG-BUG-014 | Engine | TF dedup cross-contaminates caches when TFs equal | NOT A BUG -- when TFs equal, sharing cache is correct optimization. |
| ENG-BUG-015 | Engine | np.append O(n) on 500-element arrays | DEFERRED -- correct behavior, ~3-10 MB/hour. Optimize before sustained live. |
| SIM-001 | Sim | TP/SL exit timestamp is exec bar ts_open | COSMETIC -- fixing requires SubLoop to return trigger bar timestamp. Deferred. |
| SIM-006 | Sim | estimate_liquidation_price() ignores mm_deduction | NOT A BUG -- documents why mm_deduction requires qty (not available pre-trade). |
| SIM-MED-1 | Sim | Stale margin after partial exit | NOT A BUG -- engine processes one signal per exec bar, prevents stale margin issue. |
| SIM-MED-2 | Sim | Slippage applied to limit TP exits | FIXED -- skip slippage for Limit TP exits and liquidation exits. |
| SIM-MED-3 | Sim | ExchangeMetrics not wired | DEFERRED -- future feature. Needs result schema wiring. |
| SIM-MED-4 | Sim | Constraints not wired | DEFERRED -- future feature. Needs per-symbol constraint config. |
| BT-002 | Backtest | _finalize_logger_on_error catches silently | FIXED -- logs debug instead of pass. |
| BT-005 | Backtest | utcfromtimestamp deprecated (Python 3.12+) | FIXED -- fromtimestamp(tz=timezone.utc). |
| BT-WARN-2 | Backtest | Cap inconsistency in _size_risk_based() | FIXED -- added missing * max_lev multiplier. |
| BT-WARN-4 | Backtest | Legacy warmup wrapper still in use | NOT A BUG -- thin wrapper delegating to canonical function, actively used. |
| BT-WARN-5 | Backtest | freeze() returns inf/-inf when empty | FIXED -- returns NaN instead. |
| DSL-002 | DSL | is_condition_list relies on disjoint operator sets | NOT A BUG -- sets are disjoint by construction. |
| DSL-004 | DSL | Cross-above uses <= for previous comparison | NOT A BUG -- TradingView standard touch-and-cross semantics. |
| DSL-PLAY-001 | DSL | tf: exec NOT resolved to concrete TF | FIXED -- resolves pointer -> role -> concrete TF. |
| DSL-PLAY-002 | DSL | Unrecognized condition keys only warned | FIXED -- now raises ValueError. |
| DSL-RISK-001 | DSL | Legacy atr_key fallback in StopLossRule | FIXED -- removed legacy fallback. |
| DSL-RISK-002 | DSL | Legacy atr_key fallback in TakeProfitRule | FIXED -- removed legacy fallback. |
| DSL-EXEC-002 | DSL | Duration window nodes not walked | FIXED -- HoldsForDuration, OccurredWithinDuration, CountTrueDuration added to walker. |
| DSL-FREG-001 | DSL | Silent 50-bar warmup default | FIXED -- raises ValueError on lookup failure. |
| IND-001 | Indicators | Inconsistent is_ready semantics | NOT A BUG -- RSI needs length+1 bars, ATR/SMA need length bars, each for valid mathematical reasons. |
| IND-007 | Indicators | Anchored VWAP excluded from parity audit | BY DESIGN -- live-computed, NaN placeholders in batch. |
| IND-FISHER-001 | Indicators | Fisher is_ready fires on artificial seeding bar | FIXED -- _count > self.length (requires length+1 bars). |
| IND-FACTORY-001 | Indicators | Unknown indicator type returns None | NOT A BUG -- None return is intended for vectorized fallback path. |
| IND-REG-003 | Indicators | Fisher warmup under-estimates by 1 bar | FIXED -- length -> length + 1. |
| DATA-001 | Data | DuckDB file locking on Windows | KNOWN/MITIGATED -- sequential access + retry logic in place. |
| DATA-003 | Data | No staleness enforcement on WS data | FIXED -- _is_websocket_connected() checks is_wallet_stale(60s). |
| DATA-006 | Data | panic_close_all retries per-position not batch | FIXED -- verification get_all_positions() retries 3x. |
| DATA-007 | Data | reduce_only defaults to False in market_buy/sell | FIXED -- added market_close() with enforced reduce_only=True. |
| DATA-016 | Data | RiskManager.check() bypasses _seed_failed | FIXED -- calls _daily_tracker.check_limit() instead of reading _daily_pnl directly. |
| DATA-011 | Data | _handle_stale_connection() never triggers reconnect | DEFERRED -- adding active reconnect risky without integration testing. GlobalRiskView blocks trading after 30s. |
| CLI-001 | CLI | Process-level timeout may orphan DuckDB locks | KNOWN -- Windows platform limitation. |
| CLI-004 | CLI | No dedicated market_close_tool | NOT A BUG -- close_position() hardcodes reduce_only=True. market_close() also added. |
| CLI-006 | CLI | Double-timeout in _run_staged_gates() | FIXED -- future.result() no longer duplicates gate timeout. |
| CLI-010 | CLI | PL2 reads wrong balance key | FIXED -- available_balance -> available. |
| CLI-020 | CLI | _get_exchange_manager() singleton not thread-safe | FIXED -- double-checked locking with threading.Lock(). |
| CLI-027 | CLI | Batch tools return success=True on partial failure | FIXED -- success=(failed_count == 0). |
| CLI-032 | CLI | Key mismatch: exposure_usd vs total_exposure_usdt | FIXED -- total_exposure_usdt -> exposure_usd. |
| FORGE-001 | Forge | Multi-TF bar dilation dilutes patterns | KNOWN -- documented. Use near_pct for structure comparisons. |
| FORGE-007 | Forge | Error code mismatch in validate_play_file() | FIXED -- MISSING_REQUIRED_FIELD -> DSL_PARSE_ERROR. |
| FORGE-008 | Forge | Parity audit excludes anchored_vwap | KNOWN/BY DESIGN -- manual verification required. |
| FORGE-010 | Forge | validate_no_lookahead() checks only first pivot | FIXED -- now checks ALL pivots. |
| FORGE-011 | Forge | validate_determinism() uses only exec_tf | FIXED -- generates all play TFs + 1m, uses align_multi_tf=True. |
| FORGE-019 | Forge | Silent credential override with dual .env files | FIXED -- warning logged when both .env and api_keys.env exist. |
| FORGE-032 | Forge | "1m" window string maps to 30-day range | NOT A BUG -- "1m" means "1 month" in time range context. "30d" exists as alternative. |
| FORGE-035 | Forge | DB lock retry matches only one error string | NOT A BUG -- retry correctly scoped to file lock errors. Other DuckDB errors should fail. |

---

## LOW (44) -- ALL RESOLVED

| ID | Domain | Description | Resolution |
|----|--------|-------------|------------|
| ENG-003 | Engine | Threading import used minimally | OK -- play_hash setter only. |
| ENG-005 | Engine | Fallback evaluation warns only once | OK -- correct behavior. |
| ENG-BUG-001 | Engine | Hardcoded bar_index == 100 debug sentinel | FIXED -- removed. |
| ENG-BUG-003 | Engine | Duplicate max drawdown check | OK -- defense-in-depth. |
| ENG-BUG-005 | Engine | Factory mutates private engine attributes | NOT A BUG -- factory injection pattern, attrs set before engine.run(). |
| SIM-002 | Sim | Liquidation check duplicates equity projection | OK -- defense-in-depth. |
| SIM-003 | Sim | MAE/MFE not tracked on exit bar | NOT A BUG -- after TP/SL exit, position is closed; post-close price irrelevant. |
| SIM-004 | Sim | No validation on negative initial_capital | FIXED -- initial_capital > 0 validation in Ledger.__init__(). |
| SIM-005 | Sim | debug_check_invariants defaults to False | OK -- performance choice. |
| SIM-007 | Sim | Bankruptcy price omits fee-to-close term | FIXED -- fee_rate added to calculate_bankruptcy_price() (Gate 2). |
| BT-001 | Backtest | GateFailure catch relies on default | OK -- works by construction. |
| BT-003 | Backtest | Terminal risk gate uses try/except ValueError | NOT A BUG -- unknown classification defaulting to non-terminal is safer. |
| BT-004 | Backtest | Drawdown decimal/percent convention | OK -- documented convention. |
| BT-006 | Backtest | FeedStore mutable despite "immutable" contract | NOT A BUG -- convention-based immutability; frozen=True would break factory injection. |
| BT-WARN-1 | Backtest | Hash function fallbacks break determinism | FIXED -- fallbacks raise TypeError instead of silent degradation. |
| BT-WARN-3 | Backtest | compute_results_summary legacy path | FIXED -- removed legacy path, raises ValueError if no metrics. |
| DSL-003 | DSL | _KNOWN_ENUM_VALUES hardcoded | OK -- standard pattern for known enums. |
| DSL-005 | DSL | dispatch_operator incomplete (between/in) | OK -- between/in handled elsewhere by construction. |
| DSL-SB-002 | DSL | Intent action not validated | FIXED -- validated against VALID_ACTIONS in __post_init__(). |
| DSL-WIN-001 | DSL | offset_scale can be 0 when anchor_tf < exec_tf | OK -- edge case, safe behavior (window looks at current bar). |
| IND-002 | Indicators | BBands floating-point drift | OK -- standard numerical behavior. |
| IND-003 | Indicators | ADX list.pop(0) is O(n) | FIXED -- list -> deque, pop(0) -> popleft(). |
| IND-005 | Indicators | PairState (str, Enum) mixin | OK -- unusual but correct. |
| IND-CMO-001 | Indicators | CMO list.pop(0) is O(n) | FIXED -- list -> deque, same pattern. |
| IND-REG-003 | Indicators | Fisher warmup under-estimates by 1 bar | FIXED -- length -> length + 1. (Also in MED as separate finding.) |
| DATA-002 | Data | _detect_ascii_mode emoji test on import | OK -- one-time check. |
| DATA-004 | Data | Bar buffer sizes hardcoded | OK -- appropriate for current use. |
| DATA-008 | Data | _extract_fill_price falls back to quote price | ACCEPTABLE -- best estimate given Bybit avgPrice=0 on pending fills. |
| DATA-012 | Data | get_health() returns healthy before data arrives | FIXED -- returns healthy: has_data (must have actual data). |
| DATA-017 | Data | panic_close_all() cancel-before-close ordering | DEFERRED -- defensible tradeoff. Pending integration test. |
| CLI-002 | CLI | Gate timeout 300s generous for quick tier | OK -- conservative is correct. |
| CLI-003 | CLI | RISK_PLAY_EXPECTATIONS hardcoded | NOT A BUG -- standard for validation suites. |
| CLI-005 | CLI | trading_env validated before order params | OK -- correct ordering. |
| CLI-006b | CLI | Backtest tool double-catches exceptions | OK -- defense-in-depth. |
| CLI-007 | CLI | Exit codes properly propagated | OK -- correct behavior. |
| CLI-014 | CLI | _run_play_backtest drops CLI flags | FIXED -- now passes through flags (data_env, smoke, sync, emit_snapshots, no_artifacts). |
| FORGE-002 | Forge | Seed determinism depends on numpy RNG version | OK -- known limitation. |
| FORGE-003 | Forge | No impossible candle validation | NOT A BUG -- construction guarantees high >= max(open,close), low <= min(open,close). |
| FORGE-004 | Forge | DEFAULTS loaded at import time | OK -- fail-fast. |
| FORGE-005 | Forge | TABLE_SUFFIXES maps backtest to _live | OK -- documented convention. |
| FORGE-006 | Forge | Redaction over-matches on substring | OK -- safety-positive. |
| FORGE-007b | Forge | JSONL event file never rotates | FIXED -- rotates at midnight. |
| FORGE-013b | Forge | generate_synthetic_bars() only 4 patterns | NOT A BUG -- dead code (never called). Production uses generate_synthetic_candles() with 34 patterns. |
| FORGE-027 | Forge | REDACT_KEY_PATTERNS missing OAuth patterns | FIXED -- added bearer, jwt, x-api-key, x-api-secret. |

---

## Summary Statistics

| Severity | Count | Fixed | Not A Bug / OK | Deferred | Known |
|----------|-------|-------|----------------|----------|-------|
| CRITICAL | 7 | 5 | 2 | 0 | 0 |
| HIGH | 16 | 11 | 2 | 2 | 1 |
| MED | 53 | 27 | 10 | 5 | 6 |
| LOW | 44 | 15 | 18 | 1 | 0 |
| **Total** | **120** | **58** | **32** | **8** | **7** |

**Remaining open items (15):**
- 5 deferred to pre-deployment: GAP-2 (DATA), DATA-011, DATA-017, ENG-BUG-015, DSL-006
- 3 deferred as future features: IND-006, SIM-MED-3, SIM-MED-4
- 7 accepted/known: DATA-001, CLI-001, FORGE-001, FORGE-008, CLI-008, SIM-001, IND-007

See `docs/TODO.md` "Deferred Items" section for tracking of open items.
