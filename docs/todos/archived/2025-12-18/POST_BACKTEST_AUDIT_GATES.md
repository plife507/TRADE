# Post-Backtest Audit & Verification Gates

**Status**: ✅ PHASES 1-4 COMPLETE (Phase 5 is FUTURE work)  
**Created**: December 18, 2025  
**Goal**: Implement post-backtest audits that verify determinism, hash matching, and artifact integrity as part of the standard workflow  
**Dependencies**: REFACTOR_BEFORE_ADVANCING.md (✅ Complete), PREFLIGHT_BACKFILL_PHASES.md (✅ Complete)

---

## Summary of Completed Work

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Auto-sync integration (--fix-gaps in preflight/run) | ✅ Complete |
| 2 | Post-backtest artifact validation gate | ✅ Complete |
| 3 | Hash-based determinism verification (verify-determinism CLI) | ✅ Complete |
| 4 | Smoke test audit integration (TEST 5 & TEST 6) | ✅ Complete |
| 5 | Drift detection system (baseline storage) | 📋 Future |

**Key Accomplishments**:
- ✅ Backtest runs automatically fetch missing data with `--fix-gaps` (default enabled)
- ✅ Backtest runs automatically validate artifacts before returning success
- ✅ Missing/invalid `pipeline_signature.json` is a **hard failure**
- ✅ `trades_hash`, `equity_hash`, `run_hash` stored in `result.json`
- ✅ `backtest verify-determinism` CLI command for hash comparison
- ✅ Smoke tests validate audit gates (TRADE_SMOKE_INCLUDE_DETERMINISM=1 for determinism check)

---

## Problem Statement (Resolved)

**Previous State**: Audit tools existed but ran separately from the backtest workflow.

**Current State**: Every backtest run automatically validates:
1. ✅ Pipeline signature is valid (production pipeline was used) - HARD FAIL
2. ✅ All required artifacts exist with correct structure
3. ✅ Hash values recorded for determinism checks
4. ✅ Optional: Re-run verification via `backtest verify-determinism --re-run`

---

## Audit Tool Inventory

| Tool | CLI Command | Purpose | Integrated? |
|------|-------------|---------|-------------|
| Pipeline Signature | (auto-generated) | Proves production pipeline used | ✅ Generated |
| Artifact Validator | (automatic) | Validates file presence/structure | ✅ Active |
| Determinism Check | `verify-determinism` | Proves re-run reproducibility | ✅ Active |
| Financial Metrics | (auto-generated) | Canonical math for all PnL/Risk | ✅ [Docs Created](../session_reviews/2025-12-18_backtest_financial_metrics_audit.md) |
| Result Hashes | (in manifest) | `trades_hash`, `equity_hash` | ✅ Generated |
| CSV ↔ Parquet Parity | `verify-suite --compare-csv-parquet` | Artifact format consistency | ❌ Not in workflow |
| Math Audit | `indicators --audit-math-from-snapshots` | Indicator correctness | ❌ Not in workflow |
| Toolkit Contract | `audit-toolkit` | Registry contracts | ❌ Not in workflow |
| In-memory Parity | `phase2-audit` | Fresh vs cached | ❌ Not in workflow |
| Snapshot Plumbing | `audit-snapshot-plumbing` | Accessor parity | ❌ Not in workflow |

---

## Phase 1: Auto-Sync Integration ✅ COMPLETE

**Goal**: Data fetching is part of the backtest workflow, not a separate manual step.  
**Completed**: December 18, 2025

### Checklist

- [x] 1.1 Add `fix_gaps: bool` parameter to `backtest_preflight_idea_card_tool()`
- [x] 1.2 When `fix_gaps=True`, pass `auto_sync_missing=True` to `run_preflight_gate()`
- [x] 1.3 Create `AutoSyncConfig` with correct data environment
- [x] 1.4 Add `fix_gaps: bool = True` to `backtest_run_idea_card_tool()` (default enabled)
- [x] 1.5 Add `--fix-gaps` / `--no-fix-gaps` CLI flags to `backtest preflight`
- [x] 1.6 Add `--fix-gaps` / `--no-fix-gaps` CLI flags to `backtest run`
- [x] 1.7 Verify single-TF auto-sync (DOTUSDT test)
- [x] 1.8 Verify multi-TF auto-sync (AVAXUSDT test)
- [x] 1.9 Full smoke test passes

### Acceptance Criteria

- ✅ `backtest run --idea-card X` automatically fetches missing data
- ✅ No manual `data-fix` required before backtest
- ✅ Multi-TF cards fetch all required timeframes
- ✅ `--no-fix-gaps` disables auto-fetch for explicit control

---

## Phase 2: Post-Backtest Validation Gate ✅ COMPLETE

**Goal**: Add automatic validation after every backtest run to ensure artifacts are correct.  
**Files**: `src/tools/backtest_cli_wrapper.py`, `src/backtest/artifacts/artifact_standards.py`  
**Completed**: December 18, 2025

### Checklist

- [x] 2.1 Extend `validate_artifacts(run_dir: Path) -> ArtifactValidationResult`
  - Check all required files exist:
    - `equity.parquet` with `ts_ms` column ✅
    - `trades.parquet` with required columns ✅
    - `result.json` with metrics ✅
    - `pipeline_signature.json` ✅
  - Return structured ArtifactValidationResult with pass/fail per artifact ✅
  - `preflight_report.json` made optional (CLI runs its own preflight) ✅

- [x] 2.2 Add `PipelineSignature.validate()` check to post-run validation
  - Verify `config_source == "IdeaCard"` ✅
  - Verify `uses_system_config_loader == False` ✅
  - Verify `placeholder_mode == False` ✅
  - Verify `feature_keys_match == True` ✅
  - **HARD FAIL**: Any variance fails validation (enables drift detection) ✅

- [x] 2.3 Wire validation into `backtest_run_idea_card_tool()`
  - After successful backtest, call `validate_artifacts(run_dir)` ✅
  - Include validation results in ToolResult.data ✅
  - Log validation summary: `[GATE] Artifact validation: PASSED` ✅
  - Log pipeline signature: `[GATE] Pipeline signature: VALID` ✅

- [x] 2.4 Add `--validate` / `--no-validate` CLI flags (default: enabled)
  - `validate_artifacts_after` parameter added to tool ✅
  - CLI flags wired to `backtest run` command ✅
  - Log message when skipped: `[GATE] Artifact validation: SKIPPED` ✅

### Acceptance Criteria

- ✅ Every backtest run automatically validates artifacts before returning success
- ✅ Missing or invalid artifacts cause backtest to **HARD FAIL** (not warning)
- ✅ Validation results included in ToolResult.data.artifact_validation
- ✅ Pipeline signature validation catches non-production runs
- ✅ Full smoke tests pass

---

## Phase 3: Hash-Based Determinism Verification [x] COMPLETE

**Goal**: Enable verification that re-running same inputs produces same outputs.  
**Files**: `src/backtest/artifacts/determinism.py`, `src/backtest/artifacts/artifact_standards.py`, `trade_cli.py`

### Checklist

- [x] 3.1 Create determinism verification module
  - Created `src/backtest/artifacts/determinism.py`
  - `compare_runs(run_a, run_b)` compares two run folders
  - Compares `trades_hash`, `equity_hash`, `run_hash`, `idea_hash`
  - Reports any differences with details ✅

- [x] 3.2 Add `backtest verify-determinism` CLI command
  - `--run-a <path>` and `--run-b <path>` arguments ✅
  - `--re-run` mode: re-runs IdeaCard and compares to specified run ✅
  - `--json` output for CI integration ✅
  - `--fix-gaps` flag for data sync during re-run ✅

- [x] 3.3 Store `trades_hash` and `equity_hash` in result.json
  - Added `trades_hash` and `equity_hash` fields to `ResultsSummary` ✅
  - Updated `compute_results_summary()` to accept and store these hashes ✅
  - Updated `runner.py` to pass individual hashes ✅
  - `full_hash` (input hash) already stored in `run_manifest.json` ✅

- [x] 3.4 Add re-run verification mode
  - `backtest verify-determinism --run-a <path> --re-run` ✅
  - Loads manifest from existing run to get IdeaCard and window ✅
  - Execute same IdeaCard with same window ✅
  - Compare output hashes ✅
  - Report PASS if identical, FAIL with diff if not ✅

### Acceptance Criteria

- ✅ Can verify two runs produced identical results (`compare_runs()`)
- ✅ Re-run mode proves determinism by re-executing (`--re-run`)
- ✅ Any drift detected and reported with specific differences (hash comparisons)
- ✅ Input hash stored in manifest (`full_hash`), output hashes in result.json

---

## Phase 4: Smoke Test Audit Integration [x] COMPLETE

**Goal**: Smoke tests verify audit infrastructure works correctly.  
**Files**: `src/cli/smoke_tests.py`

### Checklist

- [x] 4.1 Add audit verification to Phase 6 backtest smoke (TEST 5)
  - Run a backtest (`backtest_run_idea_card_tool`) ✅
  - Validate `pipeline_signature.json` exists and is valid ✅
  - Validate all required artifacts present ✅
  - Check result hashes are populated (trades_hash, equity_hash, run_hash, idea_hash) ✅

- [x] 4.2 Add determinism spot-check (optional, TEST 6)
  - Only when `TRADE_SMOKE_INCLUDE_DETERMINISM=1` ✅
  - Self-comparison sanity check (run compared to itself) ✅
  - Verify hash match ✅
  - Report pass/fail with hash details ✅

- [x] 4.3 Parity check deferred to separate workflow
  - Parity check (`verify-suite --compare-csv-parquet`) is already available as a CLI command
  - Can be run separately when needed
  - Not integrated into smoke tests to keep them fast

- [x] 4.4 Updated smoke test output and docstring
  - Added TEST 5: Audit Verification ✅
  - Added TEST 6: Determinism Spot-Check ✅
  - Updated docstring to list new tests ✅
  - Clear [OK]/[FAIL] reporting for each gate ✅

### Acceptance Criteria

- ✅ `--smoke full` validates audit artifacts (when `TRADE_SMOKE_INCLUDE_BACKTEST=1`)
- ✅ Optional determinism check via `TRADE_SMOKE_INCLUDE_DETERMINISM=1`
- ✅ Clear reporting of audit gate pass/fail with hash values
- ✅ Pipeline signature validation as hard gate

---

## Phase 5: Drift Detection System [ ] FUTURE

**Goal**: Detect when code changes cause result drift from baseline.  
**Status**: Future work (requires baseline storage)

### Checklist

- [ ] 5.1 Define baseline storage format
  - Store canonical run results for key IdeaCards
  - Include input hashes and output hashes
  - Version control or artifact storage

- [ ] 5.2 Create `backtest verify-baseline` command
  - Run IdeaCard and compare to stored baseline
  - Report drift if hashes differ
  - Support multiple baseline sets

- [ ] 5.3 Integrate with CI
  - GitHub Action runs baseline verification on PR
  - Drift detected → PR flagged for review
  - Expected drift → update baseline with comment

### Acceptance Criteria

- Can detect when code changes cause different backtest results
- Intentional changes can update baseline
- Unintentional drift caught before merge

---

## CLI Commands Summary

| Command | Phase | Purpose |
|---------|-------|---------|
| `backtest run --idea-card X` | 1 ✅ | Auto-fetch data, run backtest, validate artifacts |
| `backtest run --no-fix-gaps` | 1 ✅ | Run without auto-fetch |
| `backtest run --no-validate` | 2 ✅ | Run without artifact validation |
| `backtest verify-determinism --run-a X --run-b Y` | 3 ✅ | Compare two runs |
| `backtest verify-determinism --run X --re-run` | 3 ✅ | Re-run and compare |
| `backtest verify-baseline --idea-card X` | 5 | Compare to stored baseline (future) |

---

## Validation Gates Summary

| Gate | When | What | Fail Behavior |
|------|------|------|---------------|
| **Preflight** | Before run | Data coverage, warmup | Hard fail |
| **Auto-Sync** | During preflight | Fetch missing data | Retry then fail |
| **Artifact Validation** | After run | File existence, structure | Hard fail |
| **Pipeline Signature** | After run | Production pipeline proof | Hard fail |
| **Hash Recording** | After run | Store for determinism | Never fails |
| **Determinism Check** | Optional | Re-run comparison | Report only |
| **Parity Check** | Optional | CSV ↔ Parquet | Report only |

---

## Files to Modify

| File | Phase | Change |
|------|-------|--------|
| `src/tools/backtest_cli_wrapper.py` | 1 ✅, 2, 3 | Add fix_gaps, validation, determinism |
| `trade_cli.py` | 1 ✅, 2, 3 | Add CLI flags |
| `src/backtest/artifacts/hashes.py` | 3 | Input hash storage |
| `src/backtest/artifacts/pipeline_signature.py` | 2 | Validation integration |
| `src/cli/smoke_tests.py` | 4 | Audit smoke tests |

---

## Cross-References

| Topic | Document |
|-------|----------|
| Refactor Complete | `docs/todos/REFACTOR_BEFORE_ADVANCING.md` |
| Preflight Phases | `docs/todos/PREFLIGHT_BACKFILL_PHASES.md` |
| Artifact Standards | `docs/architecture/ARTIFACT_STORAGE_FORMAT.md` |
| Pipeline Signature | `src/backtest/artifacts/pipeline_signature.py` |
| Hashes | `src/backtest/artifacts/hashes.py` |
| Existing Audits | `src/backtest/audits/` |

---

## Execution Checklist

- [x] **Phase 1 complete**: Auto-sync integrated ✅ (Dec 18, 2025)
- [x] **Phase 2 complete**: Post-backtest artifact validation gate ✅ (Dec 18, 2025)
- [x] **Phase 3 complete**: Hash-based determinism verification ✅ (Dec 18, 2025)
- [x] **Phase 4 complete**: Smoke test audit integration ✅ (Dec 18, 2025)
- [ ] **Phase 5 future**: Drift detection system (requires baseline storage)

---

**Document Version**: 1.1  
**Last Updated**: December 18, 2025  
**Status**: Phases 1-4 ✅ COMPLETE; Phase 5 📋 FUTURE

