# Forge / Config / Utils Review

## Module Overview

The **Forge** domain (`src/forge/`) is the validation and auditing infrastructure:
it generates synthetic market data, validates Play configurations, and verifies
that incremental indicators match their vectorized equivalents. The **Config**
domain (`src/config/`) owns environment-variable-driven configuration and
canonical constants. The **Utils** domain (`src/utils/`) owns the logging
system, time-range abstractions, and CLI display helpers. The suite runner
(`scripts/run_full_suite.py`) ties it together for the 170-play synthetic
regression suite.

---

## File-by-File Findings

---

### `src/forge/validation/synthetic_data.py`

**Role**: Canonical source for all synthetic OHLCV generation. 30+ named
pattern generators, multi-TF alignment, hash tracing.

---

- **[FORGE-001] Severity: MED** -- Legacy `generate_synthetic_bars()` exposes
  only 4 of the 34 named patterns (lines 1939-1949).

  - Root cause: `generate_synthetic_bars()` defines its own local
    `pattern_generators` dict hard-coded to `{"trending", "ranging",
    "volatile", "multi_tf_aligned"}` instead of delegating to
    `PATTERN_GENERATORS` (the module-level registry at line 1306).
  - Impact: Structure detection audits that call `generate_synthetic_bars()`
    cannot exercise the 30 newer patterns (e.g. `reversal_v_bottom`,
    `range_tight`, `breakout_false`). Callers are silently rejected with a
    `ValueError` when any non-legacy pattern is requested.
  - Fix: Replace the local dict at line 1939 with `PATTERN_GENERATORS` and
    remove the dead code. The `PatternType` `Literal` already covers the full
    set.

---

- **[FORGE-002] Severity: LOW** -- `generate_synthetic_ohlcv_df()` (line 1724)
  uses `datetime(2024, 1, 1)` as its default `base_timestamp` (line 1758)
  while every other generator defaults to `datetime(2025, 1, 1)` (line 1617).

  - Root cause: The function was written independently from the main
    `generate_synthetic_candles()` and its default was never synchronized.
  - Impact: Minor inconsistency; callers that compare outputs from the two
    generators across different contexts may get mismatched wall-clock
    timestamps in logs. Not a correctness issue.

---

- **[FORGE-003] Severity: LOW** -- The `_prices_to_ohlcv()` function (line
  1355) does not guarantee `high >= open >= close >= low` for every bar.

  - Root cause: `opens[i]` is set as `close_prices[i-1] * (1 + normal(0,
    0.001))` (line 1391). `lows[i]` is computed from `min(opens[i], close)`
    minus an absolute normal draw (line 1399). When `close` is negative
    (possible in pathological `_generate_volatile_prices` runs at high spike
    magnitude), `lows[i]` can exceed `close`. In practice very rare but not
    asserted.
  - Impact: Downstream indicators (ATR, KC, Williams %R) that require
    `high >= low` can receive malformed candles and return NaN. The parity
    audit still passes because NaN values are excluded from `_compare_series()`
    (line 251).
  - Fix: Add a post-generation assertion: `assert (df["high"] >= df["low"]).all()`.

---

- **[FORGE-004] Severity: LOW** -- `generate_synthetic_candles()` uses
  `inspect.signature()` at runtime for every call (lines 1634-1636) to detect
  whether a generator accepts a `config` parameter.

  - Root cause: The pattern registry holds both legacy 4-argument generators
    and new 5-argument generators. Detection is done via introspection rather
    than a protocol or subtype.
  - Impact: Minor performance cost (`inspect` is non-trivial). For validation
    runs generating hundreds of timeframes this adds measurable overhead. It
    also silently ignores any `config` argument passed to legacy generators.
  - Fix: Add a module-level `LEGACY_PATTERN_GENERATORS` set listing the 4
    legacy keys, or dispatch with `try/except TypeError`. Avoids importing
    `inspect` in the hot path.

---

- **[FORGE-005] Severity: LOW** -- `SyntheticCandles.generated_at` (line 153)
  uses `datetime.utcnow().isoformat()` which produces a naive datetime. The
  `datetime.utcnow()` call is deprecated in Python 3.12+.

  - Root cause: Standard library deprecation.
  - Impact: Runtime `DeprecationWarning` in Python 3.12 strict mode.
  - Fix: Change to `datetime.now(timezone.utc).isoformat()` and add
    `from datetime import timezone` import.

---

- **[FORGE-006] Severity: LOW** -- `generate_synthetic_for_play()` (line 1472)
  only adds `play.exec_tf` and features' `.tf` attribute to the timeframes
  set. It never adds `play.low_tf`, `play.med_tf`, or `play.high_tf` as
  declared in the play's `timeframes:` block.

  - Root cause: The function queries features for their `tf` attribute
    (line 1521) but ignores the Play's own TF role declarations.
  - Impact: For plays that declare `high_tf: "D"` but have no feature
    explicitly tagged with `tf: D`, the daily TF is never generated. The
    resulting synthetic data set is incomplete for multi-TF plays.
  - Fix: Also iterate `play.low_tf`, `play.med_tf`, `play.high_tf` when
    collecting timeframes, identical to the pattern used in
    `run_play_with_synthetic()` in `structure_validators.py` (which adds `"1m"`
    explicitly, line 216).

---

### `src/forge/validation/play_validator.py`

**Role**: Pure-function Play config validation. Two entry points: `validate_play()`
(basic, normalize-only) and `validate_play_unified()` (full two-phase).

---

- **[FORGE-007] Severity: MED** -- Error code mismatch in `validate_play_file()`
  (line 120) vs `validate_play_file_unified()` (line 227).

  - Root cause: `validate_play_file()` at line 153 uses
    `ValidationErrorCode.MISSING_REQUIRED_FIELD` for a YAML parse error, while
    `validate_play_file_unified()` at line 261 correctly uses
    `ValidationErrorCode.DSL_PARSE_ERROR` for the same condition.
  - Impact: Callers that switch between the two validators receive different
    error codes for identical errors. Tools that filter by error code behave
    inconsistently depending on which validator path was taken.
  - Fix: Standardize both to `DSL_PARSE_ERROR` for YAML parse failures, and
    reserve `MISSING_REQUIRED_FIELD` only for structural dict issues.

---

- **[FORGE-008] Severity: LOW** -- `validate_play()` (line 72) swallows all
  exceptions from `normalize_play_yaml()` into a single
  `MISSING_REQUIRED_FIELD` error code (lines 106-116).

  - Root cause: The broad `except Exception` at line 106 loses the original
    exception type. A `KeyError`, `TypeError`, and `ValueError` all produce
    the same error code.
  - Impact: Error messages in the CLI are vague: "Normalization failed: ..."
    without indicating the category. Harder for agents to fix programmatically.
  - Fix: Catch `KeyError`, `TypeError`, `ValueError` separately and map to
    appropriate `ValidationErrorCode` values.

---

- **[FORGE-009] Severity: LOW** -- `validate_play_unified()` (line 184) only
  catches `ValueError`, `KeyError`, and `TypeError` from `Play.from_dict()`
  (line 213). `AttributeError` (from DSL operator resolution) will propagate
  and crash the caller.

  - Root cause: The `except` clause at line 213 is intentionally narrow but
    misses `AttributeError`.
  - Impact: Unexpected crash of the validation gate when a play has a malformed
    DSL expression that resolves to an attribute access error.

---

### `src/forge/validation/structure_validators.py`

**Role**: Structural validation helpers: lookahead check, determinism check,
allowlist check, and `run_play_with_synthetic()`.

---

- **[FORGE-010] Severity: MED** -- `validate_no_lookahead()` (line 36) only
  checks the **first** confirmed pivot, not all pivots in the series.

  - Root cause: The loop at line 69 breaks on the first non-NaN pair and
    returns immediately. A detector could pass lookahead on bar 1 but exhibit
    lookahead later in the series on a subsequent pivot.
  - Impact: A detector that front-runs its second or third pivot passes this
    check undetected. The check provides weak coverage for re-entrant pivot
    detection.
  - Fix: Iterate all pivot/confirmation pairs, not just the first. Return
    failure on the first violation found.

---

- **[FORGE-011] Severity: MED** -- `validate_determinism()` (line 92) uses
  only `play.exec_tf` for the synthetic data timeframes (line 119). Multi-TF
  plays that rely on `high_tf` or `med_tf` structure will not be tested for
  determinism on those feeds.

  - Root cause: `timeframes = [play.exec_tf]` ignores the play's full TF role
    set.
  - Impact: A non-deterministic multi-TF structure detector could pass the
    determinism check if the non-determinism only manifests on a non-exec TF.
  - Fix: Collect all TFs used by the play (same fix as FORGE-006).

---

- **[FORGE-012] Severity: LOW** -- `validate_strict_allowlist()` (line 151)
  catches only `ValueError` (line 181) for invalid field access. If
  `RuntimeSnapshotView.get()` raises `KeyError` instead, the check produces an
  unexpected exception rather than a clean test failure.

  - Root cause: Expected exception type is hardcoded to `ValueError`.
  - Fix: Catch `(ValueError, KeyError)` at line 181.

---

### `src/forge/audits/audit_incremental_parity.py`

**Role**: Compares 43 incremental indicators against pandas_ta vectorized
implementations bar-by-bar.

---

- **[FORGE-013] Severity: HIGH** -- `generate_synthetic_ohlcv()` (line 187)
  uses the **legacy** `np.random.seed(seed)` global seed API (line 196) rather
  than `np.random.default_rng(seed)`.

  - Root cause: The function pre-dates the module's migration to
    `np.random.default_rng`. The canonical synthetic generators in
    `synthetic_data.py` all use `np.random.default_rng` for isolated,
    non-global state.
  - Impact: **Calling `generate_synthetic_ohlcv()` mutates the global numpy
    random state.** Any test or function sharing a process with the parity
    audit gets a different random stream than expected. This is a hidden
    cross-test contamination vector. The parity audit itself is deterministic
    only because it always reseeds with `np.random.seed(seed)` first -- but any
    `rng.normal()` call between the seed and the first `np.random.randn()`
    call (e.g. from a concurrent import or parallel audit step) will shift
    results.
  - Fix: Refactor to `rng = np.random.default_rng(seed)` and replace all
    `np.random.*` calls with `rng.*`. Or delegate to
    `generate_synthetic_ohlcv_df()` from `synthetic_data.py` which already
    uses `default_rng`.

---

- **[FORGE-014] Severity: MED** -- The parity audit docstring at line 7 says
  "43 indicators" but `INDICATOR_REGISTRY` in `src/indicators/` registers 44
  indicators (per CLAUDE.md). The excluded indicator is not documented in the
  audit module.

  - Root cause: MEMORY.md documents "Parity audit intentionally excludes
    anchored_vwap" but this exclusion is not stated in the audit module itself.
  - Impact: Future maintainers may add the 44th indicator to the registry and
    not notice it is missing from parity coverage.
  - Fix: Add a comment at the top of the audit listing excluded indicators with
    the reason, e.g. `# Excluded: anchored_vwap -- batch-precomputed; parity
    excluded by design (see MEMORY.md)`.

---

- **[FORGE-015] Severity: LOW** -- `_compare_series()` (line 230) returns
  `(True, 0.0, 0.0, 0)` when `valid_count == 0` (line 255). A zero-comparison
  result is reported as `passed=True`, silently masking indicators that never
  produce a non-NaN value.

  - Root cause: The convention is "no data = no failure," but a valid parity
    test requires at least one data point.
  - Impact: An indicator whose incremental implementation always returns NaN
    (e.g. due to a parameter misconfiguration) would report as `passed=True`
    with `valid_comparisons=0`. False positive.
  - Fix: Return `passed=False` with a descriptive `error_message` when
    `valid_count == 0`, or at minimum emit a warning.

---

- **[FORGE-016] Severity: LOW** -- The default tolerance (`1e-6`) is uniform
  across all 43 indicators. Some indicators inherently accumulate larger
  floating-point error (KAMA, ALMA, ZLMA involve recursive convolutions).

  - Root cause: Per-indicator tolerance tuning is not implemented.
  - Impact: Potential flaky failures on unusual synthetic seeds. Low risk at
    the standard seed=42 used in CI.

---

### `src/forge/audits/stress_test_suite.py`

**Role**: Hash-traced stress test pipeline: synthetic data -> batch validation
-> toolkit audit -> rollup parity -> structure detection.

---

- **[FORGE-017] Severity: LOW** -- `StressTestReport.generated_at` (line 93)
  uses `datetime.utcnow().isoformat()` (same issue as FORGE-005).

  - Fix: `datetime.now(timezone.utc).isoformat()`.

---

- **[FORGE-018] Severity: LOW** -- `_compute_hash()` (line 164) in
  `stress_test_suite.py` is a local re-implementation of the canonical hashing
  convention. It produces hashes in a different domain than `compute_trades_hash()`
  in `src/backtest/artifacts/hashes.py`.

  - Root cause: The stress test predates the canonical hash module.
  - Impact: The stress test's `hash_chain` cannot be cross-referenced against
    artifact hashes. Violates the CLAUDE.md rule: "Always use
    `compute_trades_hash()` from `hashes.py` -- never ad-hoc `repr()`/`hash()`."
  - Fix: Import canonical hash functions from `hashes.py` or use
    `compute_play_hash()` / `compute_input_hash()` where applicable.

---

### `src/config/config.py`

**Role**: Singleton `Config` class. Loads `.env` / `api_keys.env`. Provides
typed sub-configs: `BybitConfig`, `RiskConfig`, `DataConfig`, `WebSocketConfig`,
`LogConfig`, `TradingConfig`, `SmokeTestConfig`.

---

- **[FORGE-019] Severity: MED** -- `Config.__init__()` loads env files in
  priority order `["api_keys.env", ".env", env_file]` (line 599) with
  `override=True` on every file. The **last** file wins, meaning `.env` values
  silently override `api_keys.env` values when both files set the same key.

  - Root cause: The comment says "Priority: .env > api_keys.env" which is
    intentional, but counter-intuitive. A developer who puts secrets in
    `api_keys.env` and then accidentally sets the same key in `.env` finds the
    `.env` value wins with no warning.
  - Impact: Silent credential override. A stale `BYBIT_DEMO_API_KEY=placeholder`
    in `.env` shadows the real key in `api_keys.env`.
  - Fix: Log a `WARNING` when a key present in `api_keys.env` is overridden by
    `.env`. Or document the counter-intuitive priority more prominently.

---

- **[FORGE-020] Severity: MED** -- `Config.reload()` (line 739) sets
  `_initialized = False` but does not hold `_singleton_lock` during the reload.

  - Root cause: The initial `__new__` is lock-protected (line 583) but
    `reload()` is not.
  - Impact: Theoretical TOCTOU race in live trading multi-threaded scenarios:
    a thread could see `_initialized = False` during reload and call `__init__()`
    again. Current usage appears single-threaded on reload, so risk is low.

---

- **[FORGE-021] Severity: LOW** -- `_load_risk_config()` (line 642) does not
  wire `default_leverage`, `max_total_exposure_usd`, `max_daily_loss_percent`,
  `max_risk_per_trade_percent`, or `min_viable_size_usdt` to env vars. These
  `RiskConfig` fields (lines 327-345) retain their hardcoded Python defaults.

  - Root cause: Incomplete wiring in `_load_risk_config()`.
  - Impact: These fields cannot be overridden at deployment time via env vars,
    forcing code changes. Violates the env-var-driven pattern established
    elsewhere.

---

- **[FORGE-022] Severity: LOW** -- `BybitConfig.get_mode_warning()` (line 124)
  returns a string containing a Unicode warning emoji. On Windows consoles
  without UTF-8 codepage (e.g. cp850, cp1252), printing this string raises
  `UnicodeEncodeError`.

  - Root cause: The logger's console handler uses the system default encoding
    on Windows, which may not be UTF-8.
  - Impact: `UnicodeEncodeError` in the console when printing the config
    summary on non-UTF-8 Windows terminals.

---

- **[FORGE-023] Severity: LOW** -- `SmokeTestConfig.__post_init__()` period
  validation (line 559) raises `ValueError` at line 562 referencing
  `self.period` before the `.upper()` normalization at line 564.

  - Root cause: Normalize-then-validate ordering is reversed.
  - Fix: Move `self.period = self.period.upper()` before the validation check.

---

### `src/config/constants.py`

**Role**: All project-wide constants. `TradingEnv`, `DataEnv`, DB path
resolution, timeframe maps, `SystemDefaults` loaded from `config/defaults.yml`.

---

- **[FORGE-024] Severity: LOW** -- `TABLE_SUFFIXES["backtest"] == "_live"` (line
  170) is a documented but fragile convention. A developer calling
  `resolve_table_name("ohlcv", "backtest")` and getting `"ohlcv_live"` back
  without reading the comment will be confused.

  - Root cause: The `backtest` -> `_live` mapping is intentional (both
    `backtest` and `live` envs share Bybit live API data), but the indirection
    is only explained in a block comment, not at call sites.
  - Impact: Developer confusion; no runtime bug.
  - Fix: Add the explanation to `resolve_table_name()` docstring, or emit a
    debug log noting the effective suffix differs from the env name.

---

- **[FORGE-025] Severity: LOW** -- `load_system_defaults()` is decorated with
  `@lru_cache(maxsize=1)` (line 494) AND the result is also stored in `DEFAULTS`
  at module import time (line 592: `DEFAULTS = load_system_defaults()`). Both
  patterns co-exist.

  - Root cause: Dual-cache pattern.
  - Impact: If `load_system_defaults.cache_clear()` is ever called, subsequent
    calls to `load_system_defaults()` re-read the YAML file but `DEFAULTS`
    is already bound and not updated. Dual-cache inconsistency risk.
  - Fix: Remove `@lru_cache` and rely solely on `DEFAULTS`, or remove
    the module-level `DEFAULTS` and always call `load_system_defaults()` via
    the cache.

---

- **[FORGE-026] Severity: LOW** -- `engine.warmup_bars = 100` in
  `config/defaults.yml` (line 86) is correctly surfaced via
  `DEFAULTS.engine.warmup_bars` but some engine code paths still read a
  hardcoded `100` instead of this value.

  - Root cause: Confirmed open GAP-1 documented in MEMORY.md as CRITICAL.
  - Impact: Changing `engine.warmup_bars` in `defaults.yml` may not propagate
    to all engine code paths.

---

### `src/utils/logger.py`

**Role**: Singleton `TradingLogger`. Console + file + JSONL event stream.
Centralized `redact_value()` for sensitive field scrubbing.

---

- **[FORGE-027] Severity: MED** -- `REDACT_KEY_PATTERNS` (lines 52-55) is
  missing common HTTP and OAuth patterns: `"bearer"`, `"jwt"`,
  `"access_token"`, `"refresh_token"`, `"x-api-key"`, `"x-api-secret"`.

  - Root cause: The pattern list was built for Bybit-specific key names and
    does not cover HTTP header conventions or JWT patterns.
  - Impact: If tool call arguments include `{"access_token": "...", "bearer":
    "..."}`, these are logged in plaintext to JSONL event files.
  - Fix: Add `"bearer"`, `"jwt"`, `"access_token"`, `"refresh_token"`,
    `"x-api-key"`, `"x-api-secret"` to `REDACT_KEY_PATTERNS`.

---

- **[FORGE-028] Severity: MED** -- The JSONL file is opened once at startup
  with today's date baked into the filename (line 219). If the process runs
  across midnight, all events after midnight are written to the prior day's
  file.

  - Root cause: `_setup_jsonl_handler()` runs once during `__init__`. No
    periodic date check.
  - Impact: Long-running live sessions (overnight) produce a single JSONL file
    spanning multiple calendar days, making date-based log querying unreliable.
  - Fix: Check the current date before each `_write_jsonl()` call and re-open
    the file if the date has changed.

---

- **[FORGE-029] Severity: LOW** -- `setup_logger()` (line 495) resets the
  singleton by setting `TradingLogger._initialized = False`,
  `TradingLogger._instance = None`, and `_logger = None` (lines 498-500).
  This bypasses the double-check lock in `__new__` and leaves a window where
  a concurrent thread that cached a reference to the old `_logger` continues
  using the stale instance.

  - Root cause: Singleton reset is not thread-safe. In practice `setup_logger`
    is called at startup only, so real-world impact is minimal.

---

- **[FORGE-030] Severity: LOW** -- `TradingLogger.trade()` (line 297) embeds
  ANSI color codes into the `pnl` portion of `msg` (line 322) then passes the
  pre-formatted string directly to both `trade_logger.info(msg)` (line 328)
  and `main_logger.info(msg)` (line 329). Both the console and file handlers
  receive the identical string with embedded ANSI escapes.

  - Root cause: The `trade()` method pre-formats with ANSI codes before logging;
    the `ColoredFormatter` only activates on `console_handler` via the
    formatter pipeline, not on a pre-formatted string.
  - Impact: `trades_YYYYMMDD.log` files contain raw ANSI escape sequences
    (`\033[92m`, `\033[91m`, `\033[0m`), making them hard to parse.
  - Fix: Build two separate strings (colored for console, plain for file), or
    strip ANSI codes before writing to the trade logger.

---

### `src/utils/time_range.py`

**Role**: Validated `TimeRange` abstraction for Bybit API queries. Preset
factory methods, window-string parsing, max-range enforcement.

---

- **[FORGE-031] Severity: MED** -- `_to_utc()` (line 434) silently assumes
  naive datetimes are UTC by calling `dt.replace(tzinfo=timezone.utc)` (line
  438) with no warning or error.

  - Root cause: "Assume naive = UTC" is a common convention, but causes silent
    wrong results when a caller passes a local-time naive datetime (e.g. from
    `datetime.now()` without `timezone.utc`).
  - Impact: On an EST-timezone machine, `TimeRange.from_dates(datetime.now(), ...)`
    produces `start_ms` that is off by the local UTC offset (e.g. -5h). The
    endpoint receives wrong time bounds with no error raised.
  - Fix: Raise `ValueError` for naive datetimes and require callers to pass
    timezone-aware datetimes. Document this requirement in the docstring.

---

- **[FORGE-032] Severity: MED** -- `from_window_string()` (line 164) maps
  `"1m"` to `TimeRangePreset.LAST_30D` (line 195). This directly collides with
  the project's universal convention where `"1m"` means "1 minute" (see
  `TIMEFRAME_TO_BYBIT` in `constants.py` line 288 and `TF_TO_MINUTES` in
  `synthetic_data.py` line 43).

  - Root cause: The window string parser uses calendar conventions (`m` =
    month) but the rest of the codebase uses trading conventions (`m` =
    minute).
  - Impact: A developer who passes `window="1m"` expecting a 1-minute range
    silently gets a 30-day range. This is a trap for any integration that
    derives a `TimeRange` from a play's exec timeframe string.
  - Fix: Remove the `"1m"` -> `LAST_30D` alias. Use `"30d"` or `"1mo"` for
    one-month windows. Add a comment explicitly noting `"1m"` is not supported.

---

- **[FORGE-033] Severity: LOW** -- `TimeRange.last_30d()` (line 125) defaults
  `endpoint_type="default"` which has a max of 7 days. Calling
  `TimeRange.last_30d()` without specifying `endpoint_type="borrow_history"`
  always raises `ValueError`.

  - Root cause: The preset factory was not wired to the only endpoint type for
    which 30 days is valid.
  - Impact: `TimeRange.last_30d()` is effectively unusable without knowing to
    pass the endpoint type.
  - Fix: Change `last_30d()` to default `endpoint_type="borrow_history"`.

---

### `src/utils/cli_display.py`

**Role**: Stateless CLI display helpers. Maps action keys to emoji-enhanced
status/completion descriptions.

---

- **[FORGE-034] Severity: LOW** -- `cli_display.py` uses emoji throughout the
  `ACTION_REGISTRY` (line 32 onward). On Windows terminals without UTF-8
  encoding (codepage 850 or 1252), printing these strings raises
  `UnicodeEncodeError`.

  - Root cause: The `TradingLogger._create_logger()` handles Windows specially
    for bracket formatting but does not enforce UTF-8 on stdout.
  - Impact: Crashes in any CLI action that calls `format_action_status()` on a
    non-UTF-8 Windows console.

---

### `scripts/run_full_suite.py`

**Role**: Orchestrates the 170-play synthetic (and real-data) regression suite
sequentially via subprocess calls.

---

- **[FORGE-035] Severity: MED** -- The retry logic (lines 89-109) only retries
  on `"being used by another process"` in `stderr` (line 104). It does NOT
  retry on the alternative DuckDB lock error message `"Could not set lock on
  file"` which appears on some Windows configurations.

  - Root cause: String matching on one error variant misses other DuckDB lock
    messages. DuckDB produces different lock error text depending on OS and
    version.
  - Impact: On Windows with older DuckDB versions, DB lock conflicts cause
    immediate failure rather than retry, breaking the suite.
  - Fix: Also match `"Could not set lock"` and `"database is locked"` in the
    retry condition.

---

- **[FORGE-036] Severity: MED** -- The retry backoff is linear: `wait = 3 *
  (attempt + 1)` seconds (line 108), producing waits of 3s, 6s, 9s, 12s, 15s.
  For real-data runs where a backtest holds the DuckDB lock for 90+ seconds,
  the total 45s of retry wait is insufficient.

  - Root cause: The retry delay is hardcoded for fast synthetic runs.
  - Impact: Real-data suite runs may exhaust all 5 retries (total 45s wait)
    while a concurrent real-data backtest holds the lock for 90+ seconds.
  - Fix: Scale `wait` by `timeout_s / 120` for real-data runs, or use
    exponential backoff with jitter.

---

- **[FORGE-037] Severity: LOW** -- `get_play_pattern()` (line 28) reads and
  regex-parses each play's YAML file. It is called twice per play: once from
  `main()` at line 233 (for display) and once inside `run_play()` at line 65
  (for the command). For 170 plays, the YAML file is read 340 times.

  - Root cause: No caching of the pattern lookup.
  - Impact: 340 unnecessary file reads during a full suite run. Minor
    performance issue.
  - Fix: Cache the result in `discover_plays()` returning `(stem, pattern)`
    tuples.

---

- **[FORGE-038] Severity: LOW** -- `run_play()` parses `Trades:` and `PnL:`
  from stdout (lines 114-119) using unanchored regex. If a play emits a
  `"Trades:"` line in debug output before the summary line, the wrong value
  may be captured.

  - Root cause: Parsing CLI output via regex rather than a structured output
    format.
  - Impact: Incorrect trade count in the suite report CSV if debug output
    interferes. Low probability in practice.

---

## Cross-Module Dependencies

```
run_full_suite.py
  └── subprocess: trade_cli.py backtest run
        └── src/backtest/ (engine_factory, play, runner)

stress_test_suite.py
  ├── src/forge/validation/  (generate_synthetic_candles, validate_batch)
  ├── src/forge/audits/      (run_toolkit_contract_audit, run_rollup_parity_audit)
  ├── src/structures/        (STRUCTURE_REGISTRY)
  └── src/indicators/        (get_registry)

audit_incremental_parity.py
  ├── src/indicators/incremental/  (43 IncrementalXxx classes)
  └── src/indicators/              (compute_indicator, vectorized)

structure_validators.py
  ├── src/backtest/            (load_play, create_engine_from_play, run_engine_with_play)
  ├── src/backtest/artifacts/  (compute_trades_hash)
  └── src/forge/validation/    (generate_synthetic_candles, SyntheticCandlesProvider)

play_validator.py
  └── src/backtest/play_yaml_builder/  (validate_play_yaml, normalize_play_yaml)

config.py
  └── python-dotenv            (load_dotenv)

constants.py
  ├── config/defaults.yml      (YAML load at import time)
  └── PyYAML                   (yaml.safe_load)

logger.py
  └── src/utils/log_context    (optional, lazy import)
```

---

## ASCII Diagram

```
  +-----------------------------------------------------------------+
  |                        Forge Domain                             |
  |                                                                 |
  |  synthetic_data.py                                              |
  |    generate_synthetic_candles()  34 patterns                    |
  |    generate_synthetic_ohlcv_df() single-TF, regime-change       |
  |    generate_synthetic_bars()     [FORGE-001: only 4 patterns]   |
  |    generate_synthetic_quotes()   rollup audits                  |
  |                                                                 |
  |  play_validator.py               structure_validators.py        |
  |    validate_play()               validate_no_lookahead()        |
  |    validate_play_unified()       [FORGE-010: first pivot only]  |
  |    [FORGE-007: error code mismatch]  validate_determinism()     |
  |                                  [FORGE-011: exec TF only]      |
  |                                                                 |
  |  audit_incremental_parity.py     stress_test_suite.py           |
  |    43 indicator parity checks    hash-traced pipeline           |
  |    [FORGE-013: global seed!]     step1: synthetic data          |
  |    [FORGE-015: zero-cmp pass]    step2: batch validate          |
  |    [FORGE-014: 44th undoc'd]     step3: toolkit audit           |
  |                                  [FORGE-018: ad-hoc hash]       |
  +-----------------------------------------------------------------+
                          |
                          | imports
                          v
  +--------------------------------------+
  |           Config Domain              |
  |                                      |
  |  config.py                           |
  |    Config (singleton, thread-safe    |
  |      __new__ but not reload)         |
  |    [FORGE-019: silent .env override] |
  |    [FORGE-020: reload not locked]    |
  |    [FORGE-021: partial RiskConfig]   |
  |                                      |
  |  constants.py                        |
  |    TABLE_SUFFIXES [FORGE-024]        |
  |    DEFAULTS = load_system_defaults() |
  |    [FORGE-025: dual-cache]           |
  |                                      |
  |  config/defaults.yml                 |
  |    warmup_bars: 100 [FORGE-026/GAP-1]|
  +--------------------------------------+
                          |
                          | imports
                          v
  +--------------------------------------+
  |            Utils Domain              |
  |                                      |
  |  logger.py                           |
  |    TradingLogger (singleton)         |
  |    [FORGE-027: redact gaps]          |
  |    [FORGE-028: JSONL no rotation]    |
  |    [FORGE-030: ANSI in file logs]    |
  |                                      |
  |  time_range.py                       |
  |    TimeRange (frozen dataclass)      |
  |    [FORGE-032: "1m" -> 30d]          |
  |    [FORGE-031: naive UTC assumed]    |
  |    [FORGE-033: last_30d() default]   |
  |                                      |
  |  cli_display.py                      |
  |    ACTION_REGISTRY (emoji strings)   |
  |    [FORGE-034: Windows UTF-8]        |
  +--------------------------------------+

  scripts/run_full_suite.py
    170-play subprocess runner
    [FORGE-035: partial lock retry]
    [FORGE-036: linear backoff too short]
    [FORGE-037: double YAML read per play]
```

---

## Priority Summary

| ID | Severity | File | Line | Short Description |
|----|----------|------|------|-------------------|
| FORGE-013 | HIGH | `audit_incremental_parity.py` | 196 | Global `np.random.seed()` mutates shared state |
| FORGE-001 | MED | `synthetic_data.py` | 1939 | `generate_synthetic_bars()` exposes only 4 of 34 patterns |
| FORGE-007 | MED | `play_validator.py` | 153 | Error code mismatch for YAML parse errors between validators |
| FORGE-010 | MED | `structure_validators.py` | 69 | Lookahead check validates first pivot only |
| FORGE-011 | MED | `structure_validators.py` | 119 | Determinism check uses exec TF only, misses multi-TF plays |
| FORGE-014 | MED | `audit_incremental_parity.py` | 7 | 44th indicator excluded from parity with no documentation |
| FORGE-019 | MED | `config.py` | 599 | Silent credential override: `.env` shadows `api_keys.env` |
| FORGE-020 | MED | `config.py` | 739 | `reload()` not holding singleton lock (TOCTOU race) |
| FORGE-027 | MED | `logger.py` | 52 | `redact_value()` misses bearer/jwt/access_token patterns |
| FORGE-028 | MED | `logger.py` | 217 | JSONL file never rotates across midnight |
| FORGE-031 | MED | `time_range.py` | 438 | Naive datetime silently assumed UTC, no warning |
| FORGE-032 | MED | `time_range.py` | 195 | `"1m"` window maps to 30d (minute vs month collision) |
| FORGE-035 | MED | `run_full_suite.py` | 104 | DB lock retry misses alternate DuckDB error strings |
| FORGE-036 | MED | `run_full_suite.py` | 108 | Linear backoff insufficient for real-data run lock duration |
| FORGE-002 | LOW | `synthetic_data.py` | 1758 | Inconsistent default `base_timestamp` across generators |
| FORGE-003 | LOW | `synthetic_data.py` | 1399 | No assertion that `high >= low` in generated candles |
| FORGE-004 | LOW | `synthetic_data.py` | 1634 | `inspect.signature()` called in generation hot path |
| FORGE-005 | LOW | `synthetic_data.py` | 153 | `datetime.utcnow()` deprecated in Python 3.12+ |
| FORGE-006 | LOW | `synthetic_data.py` | 1517 | `generate_synthetic_for_play()` misses play TF role declarations |
| FORGE-008 | LOW | `play_validator.py` | 106 | Broad `except Exception` loses error type on normalization |
| FORGE-009 | LOW | `play_validator.py` | 213 | `AttributeError` not caught from `Play.from_dict()` |
| FORGE-012 | LOW | `structure_validators.py` | 181 | Allowlist check catches `ValueError` only, misses `KeyError` |
| FORGE-015 | LOW | `audit_incremental_parity.py` | 255 | Zero valid comparisons reported as `passed=True` |
| FORGE-016 | LOW | `audit_incremental_parity.py` | 7 | Uniform tolerance across all 43 indicators |
| FORGE-017 | LOW | `stress_test_suite.py` | 93 | `datetime.utcnow()` deprecated |
| FORGE-018 | LOW | `stress_test_suite.py` | 164 | Ad-hoc hash in stress test violates canonical hash rule |
| FORGE-021 | LOW | `config.py` | 642 | Several `RiskConfig` fields not wired to env vars |
| FORGE-022 | LOW | `config.py` | 124 | Emoji in warning strings fails on non-UTF-8 Windows terminals |
| FORGE-023 | LOW | `config.py` | 562 | Smoke period error message shows un-normalized value |
| FORGE-024 | LOW | `constants.py` | 170 | `TABLE_SUFFIXES["backtest"] == "_live"` undocumented at call sites |
| FORGE-025 | LOW | `constants.py` | 494 | `@lru_cache` + module-level `DEFAULTS` dual-cache inconsistency |
| FORGE-026 | LOW | `config/defaults.yml` | 86 | `warmup_bars: 100` confirms open GAP-1 |
| FORGE-029 | LOW | `logger.py` | 498 | `setup_logger()` singleton reset not thread-safe |
| FORGE-030 | LOW | `logger.py` | 322 | ANSI escape codes written to trade log files |
| FORGE-033 | LOW | `time_range.py` | 125 | `last_30d()` default endpoint type allows only 7 days, always raises |
| FORGE-034 | LOW | `cli_display.py` | 32 | Emoji in display strings breaks non-UTF-8 Windows terminals |
| FORGE-037 | LOW | `run_full_suite.py` | 65 | YAML file read twice per play (no pattern cache) |
| FORGE-038 | LOW | `run_full_suite.py` | 114 | Unanchored regex for CLI output may capture wrong trade count |
