# AUDIT_30: Rules Compiler & Operator Semantics

**STATUS**: COMPLETE
**AGENT**: Agent D - Rules Compiler & Operator Semantics Auditor
**DATE**: 2026-01-01
**SCOPE**: Rules compilation, operator dispatch, hot-loop performance, NaN handling

---

## Executive Summary

The rules compiler is well-designed and correctly separates compile-time validation from hot-loop execution. The main risk is the optional nature of compilation - if not called, evaluations fall back to inefficient legacy path.

---

## 1. Scope

### What Was Reviewed

- **Rules Compiler**: `src/backtest/rules/compile.py`
- **Rules Evaluation**: `src/backtest/rules/eval.py`
- **Operator Registry**: `src/backtest/rules/registry.py`
- **Rule Types**: `src/backtest/rules/types.py`
- **Play Rule Parsing**: `src/backtest/play.py`
- **YAML Builder**: `src/backtest/play_yaml_builder.py`
- **Execution Validation**: `src/backtest/execution_validation.py`
- **Snapshot Resolution**: `src/backtest/runtime/snapshot_view.py`

---

## 2. Contract Checks

### 2.1 Rules Compilation at Normalization Time - PASS

Compilation is correctly separated from evaluation. Legacy fallback exists but is guarded.

### 2.2 Compiled Refs Used in Hot Loop - RISK (P2)

`snapshot_view.py:741` does `path.split(".")` - string parsing per condition evaluation. Impact is minimal but violates contract intent.

### 2.3 Operator Semantics Correct - PASS

- Float equality correctly rejected with `approx_eq` requirement
- Type contracts enforced at evaluation time
- NaN handling is explicit and consistent

### 2.4 No Per-Bar String Parsing - RISK (P2)

CompiledRef stores pre-parsed tokens, but `snapshot.get()` still splits the path string.

### 2.5 NaN Handling - PASS

- `ValueType.MISSING` for NaN detection
- Every evaluation returns ReasonCode explaining outcome
- Explicit failure propagation

---

## 3. Findings

### P0 (Correctness) - None Found

### P1 (High-Risk)

#### P1.1: Legacy Evaluation Path Still Active

**Location**: `execution_validation.py:931-985`

When `cond.has_compiled_refs()` returns False, falls back to legacy string-based evaluation.

**Recommendation**: Make compilation mandatory in engine initialization.

#### P1.2: cross_above/cross_below Operators Banned But Present

**Location**: `play.py:480-481`, `registry.py:101-120`

Play YAML can specify these operators but they fail at compile time.

**Recommendation**: Add YAML schema validation to reject early.

### P2 (Maintainability)

- **P2.1**: String split in hot path (`snapshot_view.py:741`)
- **P2.2**: Duplicate operator aliases in multiple places
- **P2.3**: RULE_EVAL_SCHEMA_VERSION defined but never used

### P3 (Polish)

- ReasonCode naming uses redundant `R_` prefix
- Logical operators (and/or/not) defined but not implemented

---

## 4. Performance Notes

### Hot-Loop Allocations

| Operation | Allocation | Frequency |
|-----------|------------|-----------|
| `EvalResult` creation | ~200 bytes | Per condition |
| `RefValue.from_resolved()` | ~100 bytes | 2 per condition |
| `path.split(".")` | ~100 bytes | 2 per condition |
| Operator dispatch | Dict lookup | Per condition |

**On 100K bar backtest with 4 conditions**: ~240MB total allocations

---

## 5. Recommendations

### Immediate (Before Next Release)

1. **Make compilation mandatory** - Add assertion in engine
2. **Add YAML schema validation** - Reject unsupported operators at parse time

### Short-Term

3. **Optimize snapshot.get()** - Accept pre-parsed tokens
4. **Consolidate operator aliases** - Single source of truth in registry

---

**Audit Complete**

Auditor: Agent D (Rules Compiler Auditor)
