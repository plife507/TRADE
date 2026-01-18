# Codebase Cleanup - Gated Execution Plan

**Created:** 2026-01-14
**Status:** COMPLETED
**Lines Removed:** ~1,000 lines

---

## Summary

| Gate | Task | Status | Lines |
|------|------|--------|-------|
| 0 | Analyze imports/dependencies | COMPLETED | - |
| 1 | Delete epoch_tracking.py | COMPLETED | ~921 |
| 2 | Delete deprecated tool stubs | COMPLETED | ~90 |
| 3 | Delete empty directories | COMPLETED | ~2 |
| 4 | Final validation | COMPLETED | - |
| - | market_structure/ refactor | DEFERRED | ~1,645 |

---

## Baseline vs Final Results

| Test | Baseline | Final | Status |
|------|----------|-------|--------|
| audit-toolkit | 43/43 PASS | 43/43 PASS | OK |
| structure-smoke | Stage 6 PASS | Stage 6 PASS | OK |
| audit-rollup | 11/11 PASS | 11/11 PASS | OK |
| F_001 synthetic | 25 trades | 25 trades | OK |
| F_001 real data | 2 trades | 6 trades (longer window) | OK |

---

## Files Changed

### Deleted
- `src/utils/epoch_tracking.py` (~921 lines)
- `src/forge/synthetic/generators/__init__.py` (2 lines)

### Modified
- `src/tools/backtest_tools.py` - removed epoch_tracking import and dead functions
- `src/tools/__init__.py` - removed deprecated exports
- `src/tools/specs/backtest_specs.py` - removed deprecated specs

### Added (Validation)
- `strategies/plays/V_GATE_001_ema_cross.yaml` - gate validation play
- `strategies/plays/V_GATE_002_structure.yaml` - structure validation play

---

## DEFERRED: market_structure/ Refactor

**Why deferred:** The module has external dependencies that require careful refactoring:
- `src/backtest/play_yaml_builder.py` imports TrendState, ZoneState
- `src/backtest/rules/compile.py` imports types
- `src/cli/smoke_tests/structure.py` tests the module

**Refactor plan for future sprint:**
1. Create `src/backtest/structure_types.py` with shared enums
2. Update all imports to use new location
3. Update smoke tests to use incremental/ detectors
4. Delete redundant market_structure/ detectors (~1,645 lines)

---

## Verification Commands

```bash
# All tests should pass
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest structure-smoke
python trade_cli.py backtest audit-rollup
python trade_cli.py backtest run --play F_001_ema_simple --dir tests/functional/plays --synthetic
python trade_cli.py backtest run --play F_001_ema_simple --dir tests/functional/plays --start 2025-01-01 --end 2025-01-10 --fix-gaps
```
