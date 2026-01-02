# AUDIT_60: Schema and Artifacts Audit

**Auditor**: Agent G (Artifacts/Schema/Caching Auditor)
**Date**: 2026-01-01
**Status**: COMPLETE

---

## Executive Summary

The hashing and determinism infrastructure is well-designed and correct. The main gap is that version information is **recorded but never validated**, creating risk of silently mixing artifacts from incompatible versions.

---

## 1. Scope

### What Was Reviewed

- **Manifest schema versioning**: `ARTIFACT_VERSION`, `PIPELINE_VERSION`, `STRUCTURE_SCHEMA_VERSION`
- **Identity hashing**: `InputHashComponents`, `compute_*_hash()` functions
- **Cache mechanisms**: `TimeframeCache`, market data caching
- **Artifact validation**: `validate_artifacts()`, `verify_run_folder()`, `RunManifest`
- **Determinism verification**: `compare_runs()`, `verify_determinism_rerun()`
- **Pipeline signature**: `PipelineSignature`

---

## 2. Contract Checks

### 2.1 Schema Safety - P1 RISK

Versions are recorded but never validated on read. A manifest from `PIPELINE_VERSION = "0.5.0"` would load into code expecting `"1.0.0"` without warning.

### 2.2 Identity Hashing - PASS

Well-designed canonicalization:
- Explicit sorting and normalization
- `sort_keys=True` in JSON dumps
- Normalized timeframe formats

### 2.3 Cache Invalidation - PASS

Folder-level isolation prevents cross-version mixing. Input hash includes all version fields.

### 2.4 Compatibility Behavior - P1 RISK

Hash integrity verified, but version compatibility NOT checked. No check for `engine_version` or `STRUCTURE_SCHEMA_VERSION` on load.

### 2.5 Determinism Verification - PASS

`compare_runs()` and `verify_determinism_rerun()` provide comprehensive verification.

---

## 3. Findings

### P0 (Correctness) - None Found

### P1 (High-Risk)

#### P1.1: Version fields are write-only

**Location**: `RunManifest.from_dict()` at `artifact_standards.py:491-548`

Version fields written to manifests but never checked when loading.

#### P1.2: ARTIFACT_VERSION is development placeholder

**Location**: `src/backtest/artifacts/__init__.py:35`

`ARTIFACT_VERSION = "0.1-dev"` - not production ready.

#### P1.3: Dual PIPELINE_VERSION constants

**Location**: `pipeline_signature.py:19` and `runner.py:89`

Two separate constants could diverge.

### P2 (Maintainability)

- **P2.1**: Hash truncation to 8-16 chars reduces collision resistance
- **P2.2**: Renamed fields handled via silent fallbacks
- **P2.3**: TimeframeCache has no persistence or versioning

### P3 (Polish)

- Inconsistent version string formats (semver vs "0.1-dev")
- Parquet version hardcoded

---

## 4. Recommendations

### R1: Implement Version Compatibility Checking (P1)

Add version comparison logic when loading manifests:
```python
if manifest.engine_version != CURRENT_PIPELINE_VERSION:
    raise VersionMismatchError(...)
```

### R2: Consolidate PIPELINE_VERSION (P1)

Move to single location and import from there.

### R3: Promote ARTIFACT_VERSION (P1)

Replace `"0.1-dev"` with `"1.0.0"` once format is stabilized.

### R4: Add Collision Detection (P2)

Check if folder exists with different full_hash before creating.

---

## 5. Summary

| Area | Status |
|------|--------|
| Schema Versioning | **P1 RISK** |
| Identity Hashing | **PASS** |
| Cache Invalidation | **PASS** |
| Version Compatibility | **P1 RISK** |
| Determinism Verification | **PASS** |

---

**Audit Complete**

Auditor: Agent G (Schema/Caching Auditor)
