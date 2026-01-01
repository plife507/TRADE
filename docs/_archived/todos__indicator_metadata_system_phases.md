# Indicator Metadata System v1 — Implementation Phases

**Created:** 2024-12-15  
**Status:** ✅ COMPLETE (Phases 1-5, 7)  
**Goal:** Add lightweight, auditable indicator metadata for reproducibility and provenance tracking.

---

## Overview

Add in-memory metadata tracking to indicator computation that enables:
- Reproducibility: Know exactly how each indicator was computed
- Provenance: Trace which FeatureSpec produced which indicator
- Drift detection: Identify parameter/version changes across runs
- Auditability: Verify indicator correctness for money-adjacent decisions

**Hard Constraints:**
- Zero impact on indicator array shape, dtype, or O(1) access patterns
- In-memory only (no DB persistence)
- Deterministic `feature_spec_id` via stable hashing
- Multi-output indicators share `feature_spec_id`; `indicator_key` distinguishes outputs

---

## Phase 1: Core Data Model ✅ COMPLETE

### Tasks
- [x] Create `src/backtest/runtime/indicator_metadata.py`
- [x] Implement `IndicatorMetadata` frozen dataclass with all required fields
- [x] Implement `canonicalize_params()` (drop None, coerce numpy, sort keys, NO float rounding)
- [x] Implement `compute_feature_spec_id()` with stable hash (indicator_type, params, input_source)
- [x] Add `get_pandas_ta_version()` helper
- [x] Add `get_code_version()` helper (reuse `get_git_commit` from manifest_writer)

### Acceptance Criteria ✅
- `feature_spec_id` is stable across runs for same {type, params, input_source}
- Canonicalization handles numpy scalars, Enums, Paths deterministically
- Hash payload excludes tf, tf_role, symbol, output_key

---

## Phase 2: Metadata Capture in FeatureFrameBuilder ✅ COMPLETE

### Tasks
- [x] Modify `FeatureFrameBuilder._compute_and_store_with_metadata()` to create metadata
- [x] Metadata for multi-output indicators shares same `feature_spec_id`
- [x] Implement `find_first_valid_idx()` helper for first_valid_idx_observed
- [x] Pass metadata dict from `FeatureFrameBuilder.build()` to `FeatureArrays`
- [x] Add `metadata` field to `FeatureArrays` dataclass

### Acceptance Criteria ✅
- Metadata created at computation time (1:1 with indicator arrays)
- Multi-output indicators share same `feature_spec_id`
- `first_valid_idx_observed` correctly reflects first non-NaN index

---

## Phase 3: FeedStore Integration ✅ COMPLETE

### Tasks
- [x] Add `indicator_metadata` field to `FeedStore` dataclass
- [x] Modify `FeedStore.from_dataframe_with_features()` to accept and store metadata
- [x] Implement invariant check (warning log if mismatch, no hard fail for legacy compat)
- [x] Ensure legacy constructors still work (no metadata = empty dict, no strict check)

### Acceptance Criteria ✅
- Every indicator in `FeedStore.indicators` has matching metadata on computed-feature path
- Legacy paths without metadata continue to work (warning only)

---

## Phase 4: Validation Helpers ✅ COMPLETE

### Tasks
- [x] Implement `validate_metadata_coverage(feed_store)` → bool
- [x] Implement `validate_feature_spec_ids(feed_store)` → MetadataValidationResult
- [x] Add `indicator_key == key` consistency check

### Acceptance Criteria ✅
- Coverage check detects missing/extra metadata
- ID consistency check detects hash mismatches

---

## Phase 5: Export Utilities ✅ COMPLETE

### Tasks
- [x] Implement `export_metadata_jsonl()` with run header + one record per line
- [x] Implement `export_metadata_json()` with run header + indicators array
- [x] Implement `export_metadata_csv()` with flattened format
- [x] Serialize `computed_at_utc` as ISO8601 with Z suffix
- [x] Include schema_version, pandas_ta_version, code_version, exported_at_utc in header

### Acceptance Criteria ✅
- Exports are valid JSON/JSONL/CSV
- Timestamps are ISO8601 with Z suffix
- Run header included in all formats

---

## Phase 6: Gate/Audit Wiring (Minimal) — OPTIONAL

### Tasks
- [ ] Add coverage check to existing audit hook (if exists)
- [ ] Add ID consistency check to existing audit hook (if exists)
- [ ] Document audit integration point

### Acceptance Criteria
- Minimal integration with existing audit infrastructure
- No heavy checks or parity logic expansion

**NOTE**: Phase 6 is optional. Metadata is now captured and exportable. Audit wiring can be added incrementally as needed.

---

## Phase 7: CLI Smoke Test ✅ COMPLETE

### Tasks
- [x] Add `run_metadata_smoke()` function to `src/cli/smoke_tests.py`
- [x] Add argparse subparser for `backtest metadata-smoke` to `trade_cli.py`
- [x] Add handler dispatch in `trade_cli.py`
- [x] Implement synthetic OHLCV generator (seed-based, deterministic)
- [x] Implement validation checks (coverage, key match, ID consistency)
- [x] Implement export to chosen format (jsonl/json/csv)
- [x] Test end-to-end via CLI

### Command Interface
```
python trade_cli.py backtest metadata-smoke \
  --symbol BTCUSDT \
  --tf 15m \
  --sample-bars 2000 \
  --seed 1337 \
  --export artifacts/indicator_metadata.jsonl \
  --format jsonl
```

### Exit Codes
- 0: All validations pass, export successful
- 1: Validation failure
- 2: Export failure

### Acceptance Criteria ✅
- Command runs without DB dependency (uses synthetic data)
- All metadata invariants validated
- Export produces valid file in chosen format
- Exit code reflects success/failure

---

## Explicitly Deferred (v2+)

- DB persistence / schema changes
- Intermediate calculations tracking
- TradingView parity automation
- Storing raw OHLCV or intermediate arrays
- Historical query layer beyond export files
- Metadata versioning/migrations

---

## Files Modified

| File | Change |
|------|--------|
| `src/backtest/runtime/indicator_metadata.py` | NEW: Data model, hashing, validation, export |
| `src/backtest/features/feature_frame_builder.py` | Capture metadata at computation time |
| `src/backtest/runtime/feed_store.py` | Store metadata, invariant check |

---

## Testing Approach

Per project rules (CLI-only validation, no pytest files):
- Unit-level validation via inline assertions and manual verification
- Integration via `backtest run --smoke` to verify metadata attached
- Export validation via manual inspection of output files

**Helper test scripts (for development verification only):**
- `tests/helpers/test_indicator_metadata.py` - Unit tests for core functions
- `tests/helpers/test_metadata_integration.py` - Integration test for full pipeline

---

## Implementation Summary

**Completed 2024-12-15:**

1. **Core Data Model** (`src/backtest/runtime/indicator_metadata.py`):
   - `IndicatorMetadata` frozen dataclass with all provenance fields
   - `canonicalize_params()` - Deterministic parameter normalization (no float rounding)
   - `compute_feature_spec_id()` - Stable 12-char hash from {type, params, input_source}
   - `find_first_valid_idx()` - Detect first non-NaN index in arrays
   - Version helpers: `get_pandas_ta_version()`, `get_code_version()`

2. **Metadata Capture** (`src/backtest/features/feature_frame_builder.py`):
   - `_compute_and_store_with_metadata()` - Creates metadata at computation time
   - `FeatureArrays.metadata` field - Carries metadata to FeedStore
   - Multi-output indicators share same `feature_spec_id`

3. **FeedStore Integration** (`src/backtest/runtime/feed_store.py`):
   - `indicator_metadata` field added
   - `from_dataframe_with_features()` passes metadata through
   - Soft invariant check (warning log, no hard fail for legacy compat)

4. **Validation Helpers**:
   - `validate_metadata_coverage()` - Check indicator/metadata key parity
   - `validate_feature_spec_ids()` - Recompute and verify ID consistency
   - `MetadataValidationResult` - Structured validation output

5. **Export Utilities**:
   - `export_metadata_jsonl()` - Streaming format with header
   - `export_metadata_json()` - Single JSON with header + indicators array
   - `export_metadata_csv()` - Flattened tabular format
   - All timestamps serialized as ISO8601 with Z suffix

**Key Design Decisions:**
- `feature_spec_id` is timeframe-agnostic (excludes tf, tf_role, symbol, output_key)
- Multi-output indicators share same `feature_spec_id`; `indicator_key` distinguishes outputs
- In-memory only (no DB persistence)
- Zero impact on indicator array shape/dtype/access patterns

