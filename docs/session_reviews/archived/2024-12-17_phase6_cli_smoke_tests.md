# Phase 6 CLI Smoke Tests - Implementation Review

**Date**: December 17, 2024  
**Status**: ✅ Complete  
**Scope**: Phase 6 CLI Smoke Tests for Backtest Infrastructure

---

## Overview

Phase 6 completes the IdeaCard to Engine integration pipeline by adding comprehensive CLI smoke tests that validate:
- Preflight gate integration with structured PreflightReport
- Data-fix bounded enforcement with deterministic backfill
- Artifact standards (epoch-ms timestamps, eval_start_ts_ms)
- MTF alignment with delay_bars requirements

## Key Deliverables

### 1. IdeaCards for Phase 6 Testing

**`test__phase6_warmup_matrix__BTCUSDT_5m.yml`**
- Single timeframe (5m exec)
- warmup_bars=100, delay_bars=0
- Trivial indicators (EMA fast/slow)
- Tests: warmup computation, PreflightReport structure

**`test__phase6_mtf_alignment__BTCUSDT_5m_1h_4h.yml`**
- Multi-timeframe (5m/1h/4h)
- Different delay_bars per role: exec=5, mtf=2, htf=1
- Tests: MTF alignment, delay_bars across roles

Both IdeaCards:
- ✅ Pass normalization via `backtest idea-card-normalize --write`
- ✅ Validate via `validate_idea_card_full()`

### 2. PreflightReport JSON Contract Extension

**`src/backtest/runtime/preflight.py`**

Extended `PreflightReport` dataclass:
```python
@dataclass
class PreflightReport:
    # ... existing fields ...
    error_code: Optional[str] = None           # NEW: INSUFFICIENT_COVERAGE, HISTORY_UNAVAILABLE
    error_details: Optional[dict] = None       # NEW: structured error context
```

Extended `TFPreflightResult.to_dict()`:
```python
# NEW: epoch-ms timestamps for assertions
"coverage": {
    "db_start_ts_ms": int(db_earliest.timestamp() * 1000),
    "db_end_ts_ms": int(db_latest.timestamp() * 1000),
    # ... other fields ...
}
```

Extended `PreflightReport.to_dict()` to include:
- `computed_warmup_requirements.warmup_by_role`
- `computed_warmup_requirements.delay_by_role`
- `required_range` (exec role only)
- `coverage` (exec role only)
- `error_code`, `error_details` on failure

**Updated `run_preflight_gate()`**:
- Sets `error_code` and `error_details` when validation fails
- Provides structured failure context for automated assertions

### 3. CLI Preflight Calls Production Gate

**`src/tools/backtest_cli_wrapper.py`**

**Replaced** `backtest_preflight_idea_card_tool()` (forward-only, no backward compat):
- Now calls `run_preflight_gate()` directly using DuckDB data_loader
- Returns `ToolResult.data == preflight_report.to_dict()` unchanged
- Added `symbol_override` parameter for smoke test support
- **Deleted** unused `PreflightDiagnostics` class

**Before** (legacy):
```python
def backtest_preflight_idea_card_tool(...):
    # Own diagnostics class
    diagnostics = PreflightDiagnostics(...)
    return ToolResult(..., data=diagnostics.to_dict())
```

**After** (Phase 6):
```python
def backtest_preflight_idea_card_tool(...):
    # Call production gate
    preflight_report = run_preflight_gate(...)
    return ToolResult(..., data=preflight_report.to_dict())
```

### 4. Data-Fix Bounded Enforcement

**`src/tools/backtest_cli_wrapper.py`**

Extended `backtest_data_fix_tool()`:
```python
def backtest_data_fix_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,           # NEW: required for bounded mode
    max_lookback_days: int = 7,               # NEW: hard cap on lookback
    sync_to_now: bool = False,
    fill_gaps: bool = True,
    heal: bool = False,
    idea_cards_dir: Optional[Path] = None,
) -> ToolResult:
```

**Bounded enforcement logic**:
```python
if start:
    requested_days = (end - start).days
    if requested_days > max_lookback_days:
        start = end - timedelta(days=max_lookback_days)
        bounds_applied = True
```

**Structured return**:
```python
{
    "env": env,
    "symbol": symbol,
    "bounds": {
        "start_ts_ms": int(start.timestamp() * 1000),
        "end_ts_ms": int(end.timestamp() * 1000),
        "cap": {"max_lookback_days": max_lookback_days},
        "applied": bounds_applied,
    },
    "operations": [...],
    "progress_lines_count": progress_lines_count,
}
```

### 5. RunManifest: eval_start_ts_ms

**`src/backtest/artifacts/artifact_standards.py`**

Extended `RunManifest` dataclass:
```python
@dataclass
class RunManifest:
    # ... existing fields ...
    eval_start_ts_ms: Optional[int] = None           # NEW: engine-truth eval start
    equity_timestamp_column: str = "ts_ms"           # NEW: standardized column name
```

**`src/backtest/runner.py`**

Populate `eval_start_ts_ms` after engine run:
```python
# Extract from engine result
eval_start_ts_ms = None
if hasattr(engine_result, 'metrics') and engine_result.metrics:
    if hasattr(engine_result.metrics, 'simulation_start'):
        sim_start = engine_result.metrics.simulation_start
        if sim_start is not None:
            eval_start_ts_ms = int(sim_start.timestamp() * 1000)

# Fallback to first equity timestamp
if eval_start_ts_ms is None and not equity_df.empty:
    eval_start_ts_ms = int(equity_df["ts_ms"].iloc[0])

# Update manifest
manifest.eval_start_ts_ms = eval_start_ts_ms
manifest.equity_timestamp_column = "ts_ms"
manifest.write_json(artifact_path / "run_manifest.json")
```

### 6. Equity Parquet: ts_ms Column

**`src/backtest/runner.py`**

Add `ts_ms` column to equity.parquet:
```python
# Write equity.parquet (Phase 3.2: Parquet-only, Phase 6: add ts_ms)
equity_df = pd.DataFrame(equity_curve) if equity_curve else pd.DataFrame(columns=[
    "timestamp", "equity",
])

# Phase 6: Add ts_ms column (epoch milliseconds)
if not equity_df.empty and "timestamp" in equity_df.columns:
    equity_df["ts_ms"] = pd.to_datetime(equity_df["timestamp"]).astype("int64") // 10**6
else:
    equity_df["ts_ms"] = pd.Series(dtype="int64")

write_parquet(equity_df, artifact_path / "equity.parquet")
```

**`src/backtest/artifacts/artifact_standards.py`**

Updated required columns:
```python
REQUIRED_EQUITY_COLUMNS = {
    "timestamp",
    "equity",
    "ts_ms",  # Phase 6: epoch-ms for smoke test assertions
}
```

### 7. ASCII-Only Progress Output

**`src/data/historical_sync.py`**

Replaced non-ASCII character:
```python
# Before: store.logger.info(f"Syncing {len(symbols)} symbol(s) × {len(timeframes)} TF(s): ...")
# After:
store.logger.info(f"Syncing {len(symbols)} symbol(s) x {len(timeframes)} TF(s): ...")
```

**Note**: `ActivityEmoji` class already has ASCII fallback via `_USE_ASCII` detection for Windows.

### 8. Phase 6 Smoke Suite

**`src/cli/smoke_tests.py`**

Added `run_phase6_backtest_smoke()`:

**TEST 1: PreflightReport Structure**
- Validates required fields: `overall_status`, `computed_warmup_requirements`, `error_code`, `error_details`
- Checks epoch-ms timestamps in coverage: `db_start_ts_ms`, `db_end_ts_ms`
- Asserts warmup/delay requirements present

**TEST 2: Data-fix Bounded Enforcement**
- Requests 30-day window with max_lookback_days=7
- Asserts `bounds.applied == true`
- Validates epoch-ms timestamps in bounds
- Checks progress_lines_count > 0

**TEST 3: MTF Alignment IdeaCard**
- Loads MTF IdeaCard with different delay_bars per role
- Validates via `validate_idea_card_full()`
- Asserts different delay_bars across roles

**TEST 4: Artifact Standards**
- Checks `ts_ms` in REQUIRED_EQUITY_COLUMNS
- Validates RunManifest has `eval_start_ts_ms` field
- Checks `equity_timestamp_column` default value

Added `run_backtest_smoke()` wrapper:
```python
def run_backtest_smoke(smoke_config, app, config) -> int:
    import os
    include_backtest = os.environ.get("TRADE_SMOKE_INCLUDE_BACKTEST", "0")
    if include_backtest not in ("1", "true", "True", "TRUE"):
        console.print(f"\n[dim]Backtest smoke tests skipped (set TRADE_SMOKE_INCLUDE_BACKTEST=1 to enable)[/]")
        return 0
    return run_phase6_backtest_smoke()
```

Wired into `run_full_cli_smoke()` as Part 7.

### 9. Opt-In Environment Variable

**`env.example`**

Added:
```bash
# Include backtest smoke tests (Phase 6)
# These validate preflight, data-fix, and artifact structure
# Set to 1/true to enable (off by default as they require IdeaCards)
TRADE_SMOKE_INCLUDE_BACKTEST=0
```

---

## Test Results

### Smoke Test Execution

```bash
TRADE_SMOKE_INCLUDE_BACKTEST=1 python trade_cli.py --smoke full
```

**All tests passed ✅**:
```
============================================================
PHASE 6 BACKTEST SMOKE TEST COMPLETE
============================================================

OK PHASE 6 VERIFIED

Full CLI Smoke Test Complete
  Symbols tested: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
  Total failures: 0

============================================================
SMOKE TEST PASSED - All tests completed successfully
============================================================
```

### Individual Test Results

| Test | Status | Key Validations |
|------|--------|-----------------|
| TEST 1 | ✅ | PreflightReport fields, epoch-ms timestamps, warmup={exec:100}, delay={exec:0} |
| TEST 2 | ✅ | Bounds clamped (30d→7d), bounds.applied=true, progress_lines_count=1 |
| TEST 3 | ✅ | MTF IdeaCard valid, delay_bars={exec:5, mtf:2, htf:1}, different across roles |
| TEST 4 | ✅ | ts_ms in REQUIRED_EQUITY_COLUMNS, eval_start_ts_ms field exists |

---

## Files Modified

| File | Changes |
|------|---------|
| `docs/todos/PREFLIGHT_BACKFILL_PHASES.md` | ✅ Phase 6 checklist complete |
| `configs/idea_cards/test__phase6_warmup_matrix__BTCUSDT_5m.yml` | ✅ Created & normalized |
| `configs/idea_cards/test__phase6_mtf_alignment__BTCUSDT_5m_1h_4h.yml` | ✅ Created & normalized |
| `src/backtest/runtime/preflight.py` | Extended PreflightReport, epoch-ms, error fields |
| `src/tools/backtest_cli_wrapper.py` | Replaced preflight tool, extended data-fix, added symbol_override |
| `src/backtest/artifacts/artifact_standards.py` | Added eval_start_ts_ms, equity_timestamp_column, ts_ms |
| `src/backtest/runner.py` | Populate ts_ms, extract eval_start_ts_ms, update manifest |
| `src/data/historical_sync.py` | ASCII-only progress (× → x) |
| `src/cli/smoke_tests.py` | Phase 6 smoke suite (4 tests), wired into full smoke |
| `env.example` | Added TRADE_SMOKE_INCLUDE_BACKTEST=0 |

---

## Architecture Impact

### 1. Build-Forward Only ✅

No backward compatibility shims:
- Deleted `PreflightDiagnostics` class entirely
- Replaced `backtest_preflight_idea_card_tool` without preserving old behavior
- No fallback to legacy preflight logic

### 2. Structured Data Over Log Scraping ✅

All assertions based on JSON fields:
- `PreflightReport.to_dict()` provides machine-readable structure
- `bounds.applied` boolean for backfill assertions
- `progress_lines_count` for progress tracking
- Epoch-ms timestamps for deterministic date comparisons

### 3. CLI-Only Validation ✅

No pytest files created:
- All validation via `python trade_cli.py --smoke full`
- Smoke tests are executable CLI commands
- No `tests/test_*.py` files added

### 4. Domain Separation Maintained ✅

Phase 6 changes respect domain boundaries:
- **SIMULATOR**: PreflightReport, data-fix, RunManifest (all src/backtest/)
- **SHARED**: Smoke tests (src/cli/), data sync (src/data/)
- **LIVE**: No changes to live trading code

---

## Integration Points

### Preflight Gate → CLI → Smoke Tests

```
run_preflight_gate()           [SIMULATOR - src/backtest/runtime/preflight.py]
    ↓
backtest_preflight_idea_card_tool()  [SHARED - src/tools/backtest_cli_wrapper.py]
    ↓
backtest preflight --json       [CLI - trade_cli.py]
    ↓
run_phase6_backtest_smoke()     [VALIDATION - src/cli/smoke_tests.py]
```

### Data-Fix → Bounded Backfill

```
backtest_data_fix_tool()        [SHARED - src/tools/backtest_cli_wrapper.py]
    ↓ (calls)
sync_range_tool()               [SHARED - src/tools/data_tools.py]
    ↓ (uses)
HistoricalDataStore.sync_range() [DATA - src/data/historical_data_store.py]
```

### Engine → Artifacts → Manifest

```
BacktestEngine.run()            [SIMULATOR - src/backtest/engine.py]
    ↓
equity_curve (with timestamp)
    ↓
runner.py adds ts_ms column     [SIMULATOR - src/backtest/runner.py]
    ↓
extract eval_start_ts_ms
    ↓
update RunManifest              [ARTIFACT - src/backtest/artifacts/]
```

---

## Breaking Changes

### 1. PreflightReport Structure

**Old** (pre-Phase 6):
```python
# PreflightReport.to_dict() was minimal
{
    "overall_status": "passed",
    "tf_results": [...],
}
```

**New** (Phase 6):
```python
# PreflightReport.to_dict() includes top-level fields
{
    "overall_status": "passed",
    "tf_results": [...],
    "computed_warmup_requirements": {
        "warmup_by_role": {"exec": 100},
        "delay_by_role": {"exec": 0},
    },
    "required_range": {"start_ts_ms": ..., "end_ts_ms": ...},
    "coverage": {"db_start_ts_ms": ..., "db_end_ts_ms": ...},
    "error_code": None,
    "error_details": None,
}
```

**Impact**: Any external code parsing PreflightReport must handle new fields.

### 2. REQUIRED_EQUITY_COLUMNS

**Old**:
```python
REQUIRED_EQUITY_COLUMNS = {"timestamp", "equity"}
```

**New**:
```python
REQUIRED_EQUITY_COLUMNS = {"timestamp", "equity", "ts_ms"}
```

**Impact**: Artifact validation now requires `ts_ms` column in equity.parquet.

### 3. RunManifest Schema

**Old**:
```python
@dataclass
class RunManifest:
    # ... fields ...
    # No eval_start_ts_ms or equity_timestamp_column
```

**New**:
```python
@dataclass
class RunManifest:
    # ... fields ...
    eval_start_ts_ms: Optional[int] = None
    equity_timestamp_column: str = "ts_ms"
```

**Impact**: RunManifest serialization includes new fields. Old manifests can be loaded (optional fields), but new manifests require these for Phase 6 validation.

---

## Performance Notes

### Preflight Performance

No performance regression:
- `run_preflight_gate()` unchanged (existing production code)
- Additional fields in `to_dict()` are O(1) operations
- Epoch-ms conversion is trivial math

### Data-Fix Bounded Enforcement

Performance improvement:
- `max_lookback_days` cap prevents unbounded historical sync
- Default 7-day window = faster smoke tests
- Progress callback adds negligible overhead

### Equity ts_ms Column

Minimal overhead:
- Single vectorized pandas operation
- `pd.to_datetime().astype("int64") // 10**6`
- Adds ~0.1-1ms to equity.parquet write

---

## Validation Commands

### Normalize IdeaCards
```bash
python trade_cli.py backtest idea-card-normalize --id test__phase6_warmup_matrix__BTCUSDT_5m --write
python trade_cli.py backtest idea-card-normalize --id test__phase6_mtf_alignment__BTCUSDT_5m_1h_4h --write
```

### Run Preflight
```bash
python trade_cli.py backtest preflight --idea test__phase6_warmup_matrix__BTCUSDT_5m --env live --json
```

### Run Data-Fix (Bounded)
```bash
python trade_cli.py backtest data-fix --idea test__phase6_warmup_matrix__BTCUSDT_5m --env live --start 2024-11-01 --end 2024-12-01 --max-lookback-days 7
```

### Run Phase 6 Smoke Tests
```bash
# Enable Phase 6 tests
TRADE_SMOKE_INCLUDE_BACKTEST=1 python trade_cli.py --smoke full

# Or in PowerShell
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full
```

---

## Next Steps (Out of Scope for Phase 6)

### Phase 7 (Completed)
- ✅ Delay bars requirements
- ✅ `market_structure.delay_bars` per TF role
- ✅ Engine delay-only evaluation shift

### Future Phases

**Phase 8: Array-Backed Hot Loop** (BLOCKED - pending numpy warmup discussion)
- NumPy array implementation for SnapshotView
- O(1) history access with integer indexing
- Remove pandas DataFrame dependency from hot loop

**Phase 9+: Analytics & Factory**
- Advanced metrics (Sortino, Calmar, max favorable excursion)
- Strategy factory orchestration
- Automated strategy promotion

---

## Lessons Learned

### 1. Build-Forward Philosophy Works

Deleting `PreflightDiagnostics` without shims:
- ✅ Cleaner codebase
- ✅ Forces migration to better patterns
- ✅ No legacy code paths to maintain

### 2. Structured Data > Log Scraping

Epoch-ms timestamps enable:
- Deterministic date comparisons
- Cross-language compatibility (JavaScript, Python, etc.)
- Precise temporal assertions in tests

### 3. CLI-First Validation Scales

Phase 6 smoke tests:
- Run in real environment (not mocked)
- Use production code paths
- Catch integration issues pytest misses

### 4. Opt-In Defaults Reduce Friction

`TRADE_SMOKE_INCLUDE_BACKTEST=0` by default:
- Doesn't break existing workflows
- Requires explicit opt-in for new tests
- Allows gradual adoption

---

## Acknowledgments

**Project Rules Applied**:
- ✅ Build-Forward Only
- ✅ TODO-Driven Execution
- ✅ Phase Discipline (Phase 7 complete, Phase 6 added)
- ✅ No Implicit Defaults
- ✅ CLI-Only Validation
- ✅ Domain Separation (SIMULATOR, LIVE, SHARED)

**Critical Rules Enforced**:
- No backward compatibility shims
- No pytest files created
- Forward-only coding (deleted PreflightDiagnostics)
- ASCII-only progress output
- Structured JSON over log scraping

---

## Conclusion

Phase 6 completes the CLI validation infrastructure for the IdeaCard backtest pipeline. All tests pass in a single end-to-end smoke run, validating:

1. ✅ Preflight integration with production gate
2. ✅ Data-fix bounded enforcement
3. ✅ Artifact standards (epoch-ms, eval_start_ts_ms)
4. ✅ MTF alignment with delay_bars

The implementation follows project rules strictly:
- Build-forward only (no backward compat)
- CLI-only validation (no pytest files)
- Structured data over log scraping
- Domain separation maintained

**Phase 6 Status**: ✅ **COMPLETE**

**Next**: Phase 8 (Array-Backed Hot Loop) or future analytics work.

