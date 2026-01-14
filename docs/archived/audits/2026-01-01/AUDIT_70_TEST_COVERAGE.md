# AUDIT_70: Test/Smoke/Validation Coverage Audit

**Agent**: H (Test/Smoke/Validation Coverage Auditor)
**Date**: 2026-01-01
**Status**: COMPLETE

---

## Executive Summary

All critical paths have smoke tests. All 42 indicators have validation Play coverage. Determinism verification exists at multiple levels. One critical gap: no test that compares state tracking on/off to verify the record-only guarantee.

---

## 1. Scope

### What Was Reviewed

- `src/cli/smoke_tests/` - All 9 smoke test modules
- `strategies/plays/_validation/` - All 24 validation Plays
- `src/backtest/audits/` - All 7 audit modules
- `src/backtest/artifacts/determinism.py` - Determinism verification
- `src/backtest/runtime/state_tracker.py` - State tracking (Stage 7)
- `src/backtest/indicator_registry.py` - 42 indicators definition

---

## 2. Contract Checks

### 2.1 Smoke Test Coverage - PASS

15 smoke test functions covering all major subsystems.

### 2.2 Determinism Checks - PASS

Determinism verified at multiple levels:
- `artifacts/determinism.py`: `compare_runs()` compares hashes
- `run_structure_smoke()`: Builder runs twice, arrays compared
- Zone instance_id determinism tested
- State tracking determinism tested

### 2.3 Validation Plays - PASS (24 cards)

| Range | Category | Count |
|-------|----------|-------|
| V_01-V_09 | Single-TF | 3 |
| V_11-V_19 | MTF | 3 |
| V_21-V_29 | Warmup | 2 |
| V_31-V_39 | Coverage (42 indicators) | 7 |
| V_41-V_49 | Math Parity | 2 |
| V_51-V_59 | 1m Drift | 1 |
| V_61+ | Structure/Zones | 3 |
| V_E01-V_E99 | Error cases | 3 |

### 2.4 Indicator Coverage - 42/42 PASS

All indicators covered across V_31 through V_37.

### 2.5 Record-Only Guarantee - RISK

**Critical Gap**: No test runs same Play with `record_state_tracking=True/False` and compares hashes.

---

## 3. Findings

### P0 (Correctness) - None

### P1 (High-Risk)

#### P1-1: No state tracking on/off comparison test

If `record_state_tracking=True` accidentally affects trade logic, the bug would go undetected.

**Recommendation**: Add explicit comparison test.

#### P1-2: Play count mismatch in CLAUDE.md

CLAUDE.md says 21 cards, but 24 exist (V_61, V_62, V_65 added).

**Recommendation**: Update CLAUDE.md.

### P2 (Maintainability)

- **P2-1**: Determinism spot-check is opt-in via environment variable
- **P2-2**: Zone interaction smoke embedded in structure.py
- **P2-3**: `run_state_tracking_smoke` not in `__all__` exports

### P3 (Polish)

- Smoke test naming inconsistent
- Magic numbers in structure smoke

---

## 4. Performance Notes

| Smoke Test | Estimated Time |
|------------|---------------|
| `run_structure_smoke` | <5s |
| `run_state_tracking_smoke` | <2s |
| `run_rules_smoke` | <3s |
| `run_metadata_smoke` | <5s |
| `run_phase6_backtest_smoke` | 30-60s |

Structure, rules, metadata, and state tracking smoke tests are suitable for pre-commit hooks (<10s combined).

---

## 5. Recommendations

### Immediate (Before Next Release)

1. **Add record-only guarantee test**: Run same Play with flag on/off, assert hash equality
2. **Update CLAUDE.md**: Change "21 Plays" to "24 Plays"

### Short-Term

3. **Enable determinism in CI**: Set `TRADE_SMOKE_INCLUDE_DETERMINISM=1`
4. **Export `run_state_tracking_smoke`**: Add to `__all__`

---

**Audit Complete**

Auditor: Agent H (Test Coverage Auditor)
