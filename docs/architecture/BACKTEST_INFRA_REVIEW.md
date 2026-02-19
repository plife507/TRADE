# Backtest Infrastructure Review

> **STATUS (2026-02-18):** All findings resolved. 1 CRIT not-a-bug (GAP-1), 1 CRIT fixed (BT-CRIT-1), 4 MED fixed, 4 LOW OK/not-a-bug.
> See `FINDINGS_SUMMARY.md` for current status of each finding.

## Module Overview

The backtest infrastructure (`src/backtest/`) provides the runner, engine factory, data preparation, metrics computation, preflight validation, and feed store. It is NOT an engine -- the engine lives in `src/engine/`.

Key files reviewed:
- `runner.py` -- Gate-enforced backtest runner (16 phases)
- `engine_factory.py` -- Creates PlayEngine from Play YAML
- `engine_data_prep.py` -- Loads and prepares multi-TF data
- `metrics.py` -- Financial metric computation (Sharpe, CAGR, drawdown)
- `runtime/preflight.py` -- Data availability validation
- `runtime/feed_store.py` -- Immutable O(1) array store for hot loop

## File-by-File Findings

### runner.py

- **[BT-001] Severity: LOW** -- GateFailure catch relies on default success=False
  - Root cause: Line 1027 catches `GateFailure`. `result.success` was initialized to `False` and is only set to `True` at line 994. Works correctly by construction, but the safety depends on initialization ordering.

- **[BT-002] Severity: MED** -- `_finalize_logger_on_error` catches exceptions silently
  - Root cause: Line 1050-1053 catches `(OSError, IOError, AttributeError)` with `pass`. Documented as "BUG-004 fix" but could mask logger initialization errors that should be reported.

- **[BT-003] Severity: LOW** -- Terminal risk gate uses try/except ValueError for classification
  - Root cause: Line 965 does `StopReason(_classification)` wrapped in try/except ValueError. Fragile if new stop reasons are added without updating the enum.

### metrics.py

- **[BT-004] Severity: LOW** -- Drawdown stored as decimal internally, displayed as percent
  - This is a documented convention ("UNIT RULE (HARD)" in the docstring). Not a bug, but a common source of confusion. All internal comparisons use decimal (0.25 = 25%).

### runtime/feed_store.py

- **[BT-005] Severity: MED** -- `_np_dt64_to_datetime` uses deprecated `utcfromtimestamp`
  - Root cause: Line 43 calls `datetime.utcfromtimestamp()` which is deprecated in Python 3.12+ (PEP 615). Returns a naive datetime without timezone info.
  - Impact: Deprecation warning on Python 3.12+. Timezone-naive datetime may cause comparison issues with tz-aware datetimes elsewhere.
  - Fix: Use `datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)`.

- **[BT-006] Severity: LOW** -- FeedStore is mutable despite "immutable" contract
  - Root cause: The docstring says "immutable once built" but the dataclass has no `frozen=True`. Convention-based immutability.

### Warmup (Cross-File)

- **[BT-007] Severity: CRITICAL** -- Warmup fallback to hardcoded 100 bars (GAP-1)
  - Root cause: When preflight is skipped (`skip_preflight=True`), `_get_warmup_config()` at runner.py line 478 calls `compute_warmup_requirements(play)`. However, the engine defaults in `config/defaults.yml` set `warmup_bars: 100`, which is used as a fallback when no indicator-specific warmup is computed.
  - Impact: For plays with indicators requiring >100 bars warmup (e.g., EMA-200), the first signals evaluate on unready indicators. Documented as GAP-1 (CRITICAL) in MEMORY.md.
  - Fix: Warmup must always be computed from actual indicator requirements, never from a hardcoded default.

## Cross-Module Dependencies

```
runner.py
  |-- engine_factory.py (create_engine_from_play)
  |-- engine_data_prep.py (load multi-TF data)
  |-- preflight.py (data validation)
  |-- metrics.py (post-run metrics)
  |-- artifacts/ (hashes, parquet, signatures)
  |-- execution_validation.py (warmup, play_hash)
```

## ASCII Diagram

```
  Play YAML
    |
    v
  load_play() -> Play object
    |
    v
  run_backtest_with_gates()
    |
    +-> Phase 1-3: Setup (synthetic, window, symbol)
    +-> Phase 4: Artifacts (hashes, manifest)
    +-> Phase 6: Preflight gate (data availability)
    +-> Phase 7: Indicator gate
    +-> Phase 8: Warmup config
    +-> Phase 9: create_engine_from_play() + run_engine_with_play()
    +-> Phase 10-11: Write trades/equity + results summary
    +-> Phase 12-14: Pipeline sig + artifact validation
    |
    v
  RunnerResult (success, artifacts, summary)
```

## Findings

### CRIT-1: Silent Default Equity in create_risk_policy()

**File**: src/backtest/risk_policy.py:274
**Severity**: CRITICAL (ALL FORWARD, NO LEGACY violation)

When risk_mode=rules is requested but risk_profile=None is passed,
the function silently constructs RiskProfileConfig(initial_equity=10000.0).
This violates the ALL FORWARD, NO LEGACY prime directive.
A caller that passes risk_mode=rules explicitly expects rules enforcement,
but if they forget risk_profile, they get the wrong equity silently.

Code at risk_policy.py:274:
    elif risk_mode == rules:
        if risk_profile is None:
            risk_profile = RiskProfileConfig(initial_equity=10000.0)  # SILENT DEFAULT

**Fix**: Raise ValueError if risk_mode=rules and risk_profile is None.
The risk_profile parameter should be required when risk_mode=rules.

---

### WARN-1: Defensive Fallback in Hash Functions Breaks Determinism Guarantee

**File**: src/backtest/artifacts/hashes.py:39-47 and :67-76
**Severity**: WARNING

compute_trades_hash() and compute_equity_hash() have an else branch that extracts
a subset of fields if to_dict() is missing. This fallback produces a hash over
fewer fields. Two runs with the same trades but different to_dict() implementations
would produce identical hashes via the fallback but different hashes via the primary path.
The fallback activates silently with no warning.

**Fix**: Remove the else branch. Trade and EquityPoint always have to_dict().
If they do not, the caller should see TypeError, not a silently degraded hash.

---

### WARN-2: Cap Inconsistency in _size_risk_based()

**File**: src/backtest/simulated_risk_manager.py:330
**Severity**: WARNING

In _size_percent_equity() line 255:
    max_by_equity_pct = equity * (max_pos_pct / 100.0) * max_lev

In _size_risk_based() line 330:
    max_by_equity_pct = equity * (max_pos_pct / 100.0)  # MISSING: * max_lev

The risk_based method omits the leverage multiplier, applying a much tighter cap
than percent_equity for the same profile. This silently produces smaller positions
than expected when risk_mode=risk_based with high leverage.

**Fix**: Apply leverage multiplier consistently in both methods, or document the
intentional difference.

---

### WARN-3: compute_results_summary() Legacy Path Silently Skips Metrics

**File**: src/backtest/artifacts/artifact_standards.py
**Severity**: WARNING

compute_results_summary() has a legacy path where metrics=None is passed.
In that case, Sharpe, Sortino, Calmar ratios, and CAGR are silently omitted
from ResultsSummary with no error or warning.

**Fix**: Make metrics required, or emit warnings.warn() when legacy path is taken.

---

### WARN-4: Legacy Warmup Wrapper Still In Use in Preflight

**File**: src/backtest/runtime/preflight.py:327
**Severity**: WARNING

calculate_warmup_start() is labeled as a legacy wrapper in the docstring
but is still called inside _validate_all_pairs(). The canonical path is
compute_warmup_requirements(play) called in run_preflight_gate(). If this
is a legacy wrapper, its callers should be updated and the wrapper deleted.

**Fix**: Migrate all callers to compute_warmup_requirements(), delete the wrapper.

---

### WARN-5: ExecRollupBucket.freeze() Returns inf/-inf When Empty

**File**: src/backtest/runtime/rollup_bucket.py:85-90
**Severity**: WARNING

The rollup bucket initializes price extremes as sentinel values:
    min_price_1m: float = float(inf)
    max_price_1m: float = float(-inf)

When freeze() is called with no 1m bars accumulated (bar_count_1m == 0),
it returns inf for px.rollup.min_1m and -inf for px.rollup.max_1m.
The docstring notes this and says strategies should check px.rollup.bars_1m > 0,
but there is no enforcement. A strategy that accesses px.rollup.min_1m without
the guard will silently receive inf, potentially producing incorrect TP/SL logic.

**Fix**: Return 0.0 or NaN for extremes when bar_count_1m == 0, or enforce
the guard at the strategy interface layer.

---

### SUGG-1: Risk Mode Warning Could Be Earlier

**File**: src/backtest/engine_factory.py
**Severity**: SUGGESTION

The risk_mode=none warning is emitted after engine construction. Emitting it
before the preflight gate would let users see it before spending time on data loading.

---

### SUGG-2: Remove Redundant None Guards in engine_feed_builder.py

**File**: src/backtest/engine_feed_builder.py
**Severity**: SUGGESTION

Several None guards check for objects that are guaranteed non-None by earlier
construction. Remove checks that cannot be None by construction.

---

### SUGG-3: Add Min-Sample Guard to Sharpe/Sortino Metrics

**File**: src/backtest/metrics.py
**Severity**: SUGGESTION

For very short backtests (5-10 trades), Sharpe and Sortino ratios are statistically
meaningless but reported with the same precision as longer backtests. Consider
emitting UserWarning when computed with insufficient samples (e.g., < 30 trades).

---

### SUGG-4: Document ts_open Passthrough to Indicator Compute

**File**: src/backtest/features/feature_frame_builder.py
**Severity**: SUGGESTION

FeatureFrameBuilder.build() passes ts_open to all indicator compute calls,
but only VWAP uses it. Add a comment explaining ts_open is passed universally
for VWAP anchoring compatibility.

---

## File-by-File Review

### runner.py

The 16-phase pipeline is well-structured and gate-enforced. Key observations:
- Line 965: StopReason(_classification) in try/except ValueError is fragile.
  Adding a new stop reason without updating the enum will silently produce ValueError.
- Line 1027: GateFailure catch relies on result.success=False initialization default.
  Works by construction but depends on initialization ordering.
- Lines 1050-1053: _finalize_logger_on_error catches (OSError, IOError, AttributeError)
  with pass. Could mask logger errors that should be surfaced.
- Phase ordering (preflight before indicator gate before warmup) is correct.
Overall: solid. Gate-enforced phase system is the right pattern.

### engine_factory.py

- create_engine_from_play() correctly delegates to canonical engine. Clean.
- run_engine_with_play() is a thin wrapper. Clean.
- Risk mode warning present but emitted post-construction (see SUGG-1).

### engine_data_prep.py

- load_multi_tf_data() correctly loads all three TFs plus 1m data.
- Timeframe resolution uses exec_tf pattern. Correct.
- No silent fallbacks found in data loading paths.

### engine_feed_builder.py

- Constructs MultiTFFeedStore from loaded data.
- Contains redundant None guards (see SUGG-2).
- exec_role aliasing logic (pointing exec_tf to low_tf/med_tf/high_tf) is correct.

### metrics.py

- Crypto-correct: TF_BARS_PER_YEAR uses 365 days/year, not 252. Correct.
- Bybit intervals only: 8h explicitly excluded (not a Bybit interval). Correct.
- get_bars_per_year(strict=True): raises ValueError for unknown TF. Appropriate.
- Drawdown decimal convention: documented and enforced. Not a bug.
- Tail risk small sample: no min-sample guard (see SUGG-3).

### simulated_risk_manager.py

- validate_stop_vs_liquidation() uses LiquidationModel as single canonical formula.
- Three sizing models: percent_equity, risk_based, fixed_notional.
- Cap inconsistency in risk_based (see WARN-2).
- update_equity() only updates when trade.is_closed. Correct.
- sync_equity() allows override from exchange state. Clean.

### risk_policy.py

- NoneRiskPolicy passes all signals. Appropriate for backtest mode.
- RulesRiskPolicy enforces daily loss limits, drawdown, exposure.
- create_risk_policy(): silent default equity bug (see CRIT-1).

### system_config.py

- RiskProfileConfig is a frozen dataclass with defaults.
- initial_equity defaults to 10000.0. Acceptable as a dataclass default.
  The bug is in create_risk_policy() constructing it without caller intent.

### indicator_vendor.py

- Batch precomputation for all TFs.
- Anchored VWAP returns NaN placeholders; engine overwrites per-bar. Correct.
- ts_open passed to all compute calls (see SUGG-4).

### indicators.py

- Canonical incremental indicator runner.
- Delegates warmup computation to IndicatorRegistry.
- No legacy warmup fallbacks found here.

### data_builder.py

- Stateless builder pattern: 6 construction steps, each returns new state.
- No mutable shared state. Clean functional style.

### runtime/preflight.py

- run_preflight_gate() calls compute_warmup_requirements(play) ONCE as single
  source of truth. Correct.
- parse_tf_to_minutes() duplicates TF_MINUTES from data store. Minor DRY violation.
- calculate_warmup_start() legacy wrapper still in use (see WARN-4).
- 6-check validation per TF (exists, coverage, bar count, monotonic, unique,
  alignment, gaps). Thorough.
- _validate_exec_to_1m_mapping() validates each exec close has a 1m bar. Correct.
- _compute_safety_buffer(): max(10, ceil(warmup_bars * 0.05)) is reasonable.

### runtime/feed_store.py

- _np_dt64_to_datetime() uses deprecated datetime.utcfromtimestamp() (Python 3.12+).
  Returns naive datetime. Should use datetime.fromtimestamp(ts, tz=timezone.utc).
- FeedStore documented as immutable but uses mutable dataclass without frozen=True.
  Convention-only immutability.
- O(1) hot-loop access via direct array indexing. Correct.
- Bisect for timestamp lookups. O(log N). Appropriate.

### runtime/snapshot_view.py

- Uses __slots__ for O(1) attribute access. Correct.
- LRU-cached path tokenization avoids repeated string splitting.
- Requires RuntimeSnapshotView, not legacy RuntimeSnapshot. Correctly enforced.

### runtime/state_tracker.py

- Record-only state orchestrator. Pure observation, no triggering.
- on_bar_start/on_signal_evaluated/on_gates_checked/on_action_taken/on_bar_end lifecycle.
- Block history pruning: removes from dict index first, then slices list. O(excess).
- StateTrackerConfig.max_drawdown_pct defaults to 100.0 (gate effectively disabled
  in record-only mode). Documented and intentional.

### runtime/gate_state.py

- evaluate_gates() collects ALL failed codes but returns first-failure as primary.
  Useful for debugging (can inspect all failures, not just first).
- 9 gate types cover the full risk surface.
- GateContext uses >= for drawdown comparison. Conservative boundary. Correct.

### runtime/cache.py

- TimeframeCache uses data-driven close detection (close_ts sets), not modulo math.
  Correct for irregular intervals (DST transitions, gaps).
- Carry-forward semantics between closes. High_tf updated before med_tf. Correct.

### runtime/windowing.py

- Two warmup APIs: compute_load_window() (indicator-lookback-based) and
  compute_data_window() (preflight-based). Clean separation.
- compute_data_window() takes minimum across exec, med_tf, high_tf data starts.
  Most conservative wins. Correct.
- compute_safety_buffer_span() at line 152 assumes tf_mapping[high_tf] and
  tf_mapping[med_tf] always exist. Fine given validated 3-feed model, but
  would KeyError with a 2-TF play.

### runtime/action_state.py

- Pure transition function for action state.
- ACTION_TRANSITIONS dict maps valid state transitions. Clean.
- States: IDLE -> ACTIONABLE -> SIZING -> SUBMITTED -> FILLED/REJECTED/CANCELED.
- No side effects in transition function. Correct.

### runtime/signal_state.py

- Pure transition function for signal state.
- One-bar confirmation model (v1 semantics).
- States: NONE -> CANDIDATE -> CONFIRMING -> CONFIRMED -> CONSUMED/EXPIRED.

### runtime/block_state.py

- BlockState unified container for per-bar state.
- is_actionable property is observational (record-only, not a trigger). Correct.

### runtime/state_types.py

- SignalStateValue, ActionStateValue: IntEnum with explicit values for array storage.
- GateCode: additive-only codes. Correct additive design.
- GateResult: frozen dataclass with pass_() and fail_() factory methods.
- Lines 168-169: SignalState = SignalStateValue and ActionState = ActionStateValue
  type aliases still present. Minor legacy residue, harmless but inconsistent with
  ALL FORWARD directive.

### runtime/rollup_bucket.py

- ExecRollupBucket: O(1) accumulate/freeze/reset cycle.
- freeze() returns inf/-inf when empty (see WARN-5).
- accumulate() correctly uses actual 1m open (not close proxy). Correct.

### runtime/quote_state.py

- QuoteState frozen dataclass.
- Validates high_1m >= low_1m, prices > 0, mark_source enum. Good validation.
- Two prices: last (actual trade proxy) and mark (index-derived for PnL/liq/risk).
  Clean separation of trading price vs risk price.

### runtime/timeframe.py

- validate_tf_mapping() enforces hierarchy: high_tf >= med_tf >= low_tf. Correct.
- ceil_to_tf_close() handles timezone-aware datetimes via .timestamp() (UTC epoch).
- ACTION_TF = 1m constant. Correct: 1m is always the action timeframe.

### artifacts/hashes.py

- All canonical hash functions in one module. Correct single source of truth.
- _canonicalize_tf() handles Bybit numeric format (15 -> 15m). Correct.
- DEFAULT_SHORT_HASH_LENGTH = 12, EXTENDED_SHORT_HASH_LENGTH = 16. Used consistently.
- compute_universe_id() uses 8-char hash for multi-symbol (vs 12-char for run folders).
  Minor inconsistency in hash lengths, but documented.
- Defensive fallback in hash functions (see WARN-1).

### artifacts/determinism.py

- compare_runs() compares trades_hash, equity_hash, run_hash, play_hash. Thorough.
- verify_determinism_rerun() uses lazy import to avoid circular deps. Correct.

### artifacts/artifact_standards.py

- RunManifest: major-version compatibility check raises VersionMismatchError. Hard-fail.
- ArtifactPathConfig: separates _validation (overwrite) from strategies (append-only).
- validate_artifacts(): validates required files, parquet schemas, result.json fields,
  pipeline signature. Comprehensive.
- compute_results_summary() legacy no-metrics path (see WARN-3).

### features/feature_spec.py

- FeatureSpec (frozen dataclass): validated against IndicatorRegistry in __post_init__.
- FeatureSpecSet: validates unique keys and dependency order. Clean.
- warmup_bars delegates to IndicatorRegistry.get_warmup_bars(). Single source.

### features/feature_frame_builder.py

- FeatureArrays.__post_init__ enforces strict metadata coverage. Prevents undocumented keys.
- FeatureFrameBuilder.build() validates all expected keys present after computation.
- prefer_float32=True default. Correct for memory efficiency.
- ts_open passed to all indicators, only VWAP uses it (see SUGG-4).

### market_structure/spec.py

- StructureSpec (frozen dataclass): hard-fail on legacy structure_type key. ALL FORWARD.
- spec_id excludes zones (zone_spec_id is separate). Allows zone iteration without
  invalidating structure caches. Clean design.
- zones only supported for SWING blocks. Validated at parse time. Correct.
- depends_on_swing only valid for TREND blocks. Validated. Correct.

### execution_validation.py

- MAX_WARMUP_BARS = 1000 cap. Prevents runaway warmup configs.
- BUILTIN_FEATURES set documents which features are always available.
- EARLIEST_BYBIT_DATE_YEAR = 2018, EARLIEST_BYBIT_DATE_MONTH = 11.
  Correct: Bybit USDT perpetuals launched November 2018.
- compute_play_hash(): play.to_dict() -> canonical JSON -> SHA256 first 16 chars.
  Consistent with CLAUDE.md specification.

---

## Cross-Module Architecture Notes

runner.py
  -- engine_factory.py        (create_engine_from_play)
  -- engine_data_prep.py      (load_multi_tf_data)
  -- engine_feed_builder.py   (build MultiTFFeedStore)
  -- runtime/preflight.py     (run_preflight_gate -- single warmup source)
  -- metrics.py               (compute_backtest_metrics -- post-run)
  -- artifacts/hashes.py      (canonical hash functions)
  -- execution_validation.py  (warmup, play_hash, MAX_WARMUP_BARS)

runtime/preflight.py
  -- compute_warmup_requirements(play)  [SINGLE SOURCE OF TRUTH]
  -- calculate_warmup_start()           [LEGACY WRAPPER -- see WARN-4]

---

## Summary Table

| ID     | Severity   | File                          | Line    | Finding |
|--------|------------|-------------------------------|---------|---------|
| CRIT-1 | CRITICAL   | risk_policy.py                | 274     | Silent default equity when risk_mode=rules |
| WARN-1 | WARNING    | artifacts/hashes.py           | 39-47   | Defensive fallback breaks determinism |
| WARN-2 | WARNING    | simulated_risk_manager.py     | 330     | Cap inconsistency in risk_based sizing |
| WARN-3 | WARNING    | artifact_standards.py         | --      | Legacy no-metrics path skips Sharpe/Sortino |
| WARN-4 | WARNING    | runtime/preflight.py          | 327     | Legacy warmup wrapper still in use |
| WARN-5 | WARNING    | runtime/rollup_bucket.py      | 85-90   | inf/-inf returned when rollup empty |
| SUGG-1 | SUGGESTION | engine_factory.py             | --      | Risk mode warning before run |
| SUGG-2 | SUGGESTION | engine_feed_builder.py        | --      | Remove redundant None guards |
| SUGG-3 | SUGGESTION | metrics.py                    | --      | Add min-sample guard to Sharpe/Sortino |
| SUGG-4 | SUGGESTION | feature_frame_builder.py      | --      | Document ts_open passthrough |

---

## Validation Reminder

After any fixes from this review:

    python trade_cli.py validate quick
    python trade_cli.py validate standard
