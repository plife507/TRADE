# Legacy Cleanup Execution Plan

**Created**: 2026-01-12
**Status**: READY FOR EXECUTION
**Baseline**: ALL TESTS PASSING (4 validation + 21 stress plays)

---

## Overview

This execution plan uses **orchestration agents** with **gated validation** between each phase. Backtests are run using stress test plays after each gate to ensure no regressions.

### Agent Roles

| Agent Type | Role | When Used |
|------------|------|-----------|
| `orchestrator` | Coordinate multi-file changes | Phase execution |
| `code-reviewer` | Review changes for TRADE patterns | After each gate |
| `security-auditor` | Audit for trading safety issues | Phase 3 (alias removal) |
| `docs-writer` | Update documentation | Phase completion |
| `validate` | Run validation suite | Every gate |

### Validation Tiers (CLI Commands Only)

```bash
# TIER 0 - Quick Check (~5 sec)
python trade_cli.py backtest play-normalize tests/validation/plays/V_130_last_price_vs_close.yml

# TIER 1 - Full Normalization (~15 sec)
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest play-normalize-batch --dir tests/stress/plays

# TIER 2 - Unit Audits (~30 sec)
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup

# TIER 3 - Stress Test Backtests (~2-5 min per play)
# Run after each PHASE completion
python trade_cli.py backtest run --play tests/stress/plays/S_14_btc_swing_structure.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_18_btc_derived_zones.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_21_btc_full_complexity.yml --smoke
```

---

## Phase 0: Baseline Capture

**Objective**: Verify all tests pass before any changes.

### Gate 0.1: Validation Baseline

```bash
# Run these commands and verify output
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
# Expected: 4/4 passed

python trade_cli.py backtest play-normalize-batch --dir tests/stress/plays
# Expected: 21/21 passed

python trade_cli.py backtest audit-toolkit
# Expected: 43/43 indicators OK

python trade_cli.py backtest audit-rollup
# Expected: 11/11 intervals OK
```

### Gate 0.2: Create Git Tag

```bash
git tag -a legacy-cleanup-baseline -m "Pre-cleanup baseline - all tests passing"
```

### Gate 0.3: Run Stress Test Backtests

Run these 3 key stress tests to capture baseline metrics:

```bash
# Structure test (swing detection)
python trade_cli.py backtest run --play tests/stress/plays/S_14_btc_swing_structure.yml --smoke

# Derived zones test
python trade_cli.py backtest run --play tests/stress/plays/S_18_btc_derived_zones.yml --smoke

# Full complexity test (all structures)
python trade_cli.py backtest run --play tests/stress/plays/S_21_btc_full_complexity.yml --smoke
```

**Capture expected trade counts for regression detection.**

- [ ] 0.1 Validation passes (4 + 21 plays)
- [ ] 0.2 Audits pass (43 indicators + 11 rollup intervals)
- [ ] 0.3 Git tag created
- [ ] 0.4 Stress test metrics captured

---

## Phase 1: Typing Modernization (LOW RISK)

**Objective**: Replace legacy `typing` imports with Python 3.12+ syntax.
**Risk**: LOW - Pure syntax changes, no behavioral impact.
**Agent**: `orchestrator` with `code-reviewer`

### Files to Modify

| File | Legacy Imports | Line |
|------|----------------|------|
| `src/cli/styles.py` | `Optional, List, Dict, Any` | 14 |
| `src/cli/art_stylesheet.py` | `Optional` | 17 |
| `src/tools/diagnostics_tools.py` | `Optional, Dict, Any` | 9 |
| `src/backtest/simulated_risk_manager.py` | `Optional` | 15 |
| `src/backtest/prices/validation.py` | `Optional` | 10 |
| `src/backtest/runtime/quote_state.py` | `Optional` | 43 |
| `src/backtest/rules/dsl_nodes/base.py` | `Union` | 15, 218 |
| `src/core/exchange_instruments.py` | `Dict` | 12 |

### Gate 1.1: CLI Modules (2 files)

**Files**: `src/cli/styles.py`, `src/cli/art_stylesheet.py`

**Changes**:
- Remove `from typing import Optional, List, Dict, Any`
- Replace `Optional[X]` → `X | None`
- Replace `Dict[K, V]` → `dict[K, V]`
- Replace `List[T]` → `list[T]`

**Validation**:
```bash
python -c "from src.cli.styles import *; from src.cli.art_stylesheet import *"
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
```

- [ ] 1.1.1 styles.py modernized
- [ ] 1.1.2 art_stylesheet.py modernized
- [ ] 1.1.3 Import check passes
- [ ] 1.1.4 Normalization passes

### Gate 1.2: Tools Module (1 file)

**File**: `src/tools/diagnostics_tools.py`

**Validation**:
```bash
python -c "from src.tools.diagnostics_tools import *"
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
```

- [ ] 1.2.1 diagnostics_tools.py modernized
- [ ] 1.2.2 Validation passes

### Gate 1.3: Backtest Module (4 files)

**Files**:
- `src/backtest/simulated_risk_manager.py`
- `src/backtest/prices/validation.py`
- `src/backtest/runtime/quote_state.py`
- `src/backtest/rules/dsl_nodes/base.py`

**Validation**:
```bash
python -c "from src.backtest.simulated_risk_manager import *"
python -c "from src.backtest.prices.validation import *"
python -c "from src.backtest.runtime.quote_state import *"
python -c "from src.backtest.rules.dsl_nodes.base import *"
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
```

- [ ] 1.3.1 simulated_risk_manager.py modernized
- [ ] 1.3.2 prices/validation.py modernized
- [ ] 1.3.3 runtime/quote_state.py modernized
- [ ] 1.3.4 rules/dsl_nodes/base.py modernized (Union → |)
- [ ] 1.3.5 All imports pass
- [ ] 1.3.6 Normalization + audit passes

### Gate 1.4: Core Module (1 file)

**File**: `src/core/exchange_instruments.py`

**Validation**:
```bash
python -c "from src.core.exchange_instruments import *"
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
```

- [ ] 1.4.1 exchange_instruments.py modernized
- [ ] 1.4.2 Validation passes

### Gate 1.5: Phase 1 Stress Test Validation

**Run stress test backtests to verify no regression**:

```bash
python trade_cli.py backtest run --play tests/stress/plays/S_14_btc_swing_structure.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_18_btc_derived_zones.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_21_btc_full_complexity.yml --smoke
```

- [ ] 1.5.1 S_14 trades match baseline
- [ ] 1.5.2 S_18 trades match baseline
- [ ] 1.5.3 S_21 trades match baseline

### Gate 1.6: Phase 1 Commit

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: modernize typing imports (Phase 1)

- Replace Optional[X] with X | None
- Replace Dict[K, V] with dict[K, V]
- Replace List[T] with list[T]
- Replace Union[A, B] with A | B

Files: 8 files modernized
GATE 1.5 VALIDATION: PASSED (stress tests match baseline)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
git tag -a legacy-cleanup-phase1 -m "Typing modernization complete"
```

- [ ] 1.6.1 Commit created
- [ ] 1.6.2 Tag created

---

## Phase 2: Remove UNUSED Backward Compat Aliases (MEDIUM RISK)

**Objective**: Remove aliases with ZERO callers.
**Risk**: MEDIUM - Must verify zero callers first.
**Agent**: `orchestrator` with `security-auditor`

### Gate 2.1: Audit Alias Usage

**CRITICAL**: Search for callers BEFORE removing anything.

```bash
# Search for each alias
grep -r "TIMEFRAMES" src/ --include="*.py" | grep -v "TIMEFRAME_TO_BYBIT" | grep -v "constants.py"
grep -r "GATE_CODE_DESCRIPTIONS" src/ --include="*.py" | grep -v "state_types.py"
grep -r "\.registry\(" src/ --include="*.py" | grep -v "feature_frame_builder.py"
grep -r "parse_play_blocks" src/ --include="*.py" | grep -v "dsl_parser.py"
```

**Document findings in this table**:

| Alias | Location | Callers Found | Can Remove? |
|-------|----------|---------------|-------------|
| `TIMEFRAMES` | constants.py:283 | | |
| `GATE_CODE_DESCRIPTIONS` | state_types.py:113 | | |
| `registry` (deprecated) | feature_frame_builder.py:335 | | |
| `parse_play_blocks` | dsl_parser.py:849 | | |

- [ ] 2.1.1 TIMEFRAMES usage audited
- [ ] 2.1.2 GATE_CODE_DESCRIPTIONS usage audited
- [ ] 2.1.3 registry() usage audited
- [ ] 2.1.4 parse_play_blocks usage audited
- [ ] 2.1.5 Table populated with findings

### Gate 2.2: Remove Zero-Caller Aliases

For EACH alias with zero callers:

1. Remove the alias (one at a time)
2. Run validation immediately
3. If fails, revert and mark as "HAS HIDDEN CALLERS"

**Validation after each removal**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
```

- [ ] 2.2.1 First zero-caller alias removed
- [ ] 2.2.2 Validation passes
- [ ] 2.2.3 Repeat for remaining zero-caller aliases

### Gate 2.3: Phase 2 Stress Test Validation

```bash
python trade_cli.py backtest run --play tests/stress/plays/S_14_btc_swing_structure.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_18_btc_derived_zones.yml --smoke
```

- [ ] 2.3.1 Stress tests pass
- [ ] 2.3.2 Trade counts match baseline

### Gate 2.4: Phase 2 Commit

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove unused backward compat aliases (Phase 2)

- Removed: [list aliases removed]
- Kept (still has callers): [list aliases kept]

GATE 2.3 VALIDATION: PASSED

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
git tag -a legacy-cleanup-phase2 -m "Unused aliases removed"
```

- [ ] 2.4.1 Commit created
- [ ] 2.4.2 Tag created

---

## Phase 3: Remove USED Backward Compat Aliases (HIGH RISK)

**Objective**: Update all callers, then remove remaining aliases.
**Risk**: HIGH - Must update ALL callers first.
**Agent**: `orchestrator` with `code-reviewer` + `security-auditor`

### Gate 3.1: stop_reason → exit_type

**Location**: `src/backtest/types.py:554-556`

```bash
# Find all callers
grep -r "\.stop_reason" src/ --include="*.py"
grep -r "stop_reason=" src/ --include="*.py"
```

**Steps**:
1. Update each caller to use `exit_type`
2. Remove `stop_reason` property alias
3. Validate

**Validation**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-rollup
```

- [ ] 3.1.1 Callers identified
- [ ] 3.1.2 All callers updated
- [ ] 3.1.3 Alias removed
- [ ] 3.1.4 Validation passes

### Gate 3.2: start_time/end_time → start_ts/end_ts

**Location**: `src/backtest/types.py:568-575`

- [ ] 3.2.1 Callers identified
- [ ] 3.2.2 All callers updated
- [ ] 3.2.3 Aliases removed
- [ ] 3.2.4 Validation passes

### Gate 3.3: Runtime Types Aliases (ltf_tf, bar_ltf, features_ltf)

**Location**: `src/backtest/runtime/types.py:323-337`

- [ ] 3.3.1 Each alias's callers identified
- [ ] 3.3.2 All callers updated
- [ ] 3.3.3 Aliases removed (one at a time, validate between)
- [ ] 3.3.4 Validation passes

### Gate 3.4: Config Legacy Key ("data")

**Locations**:
- `src/config/config.py:252`
- `src/tools/diagnostics_tools.py:497`

- [ ] 3.4.1 Legacy "data" key callers identified
- [ ] 3.4.2 Callers updated to new key
- [ ] 3.4.3 Legacy handling removed
- [ ] 3.4.4 Validation passes

### Gate 3.5: epoch_tracking timeframes → tfs

**Location**: `src/utils/epoch_tracking.py:248-252`

- [ ] 3.5.1 Callers identified
- [ ] 3.5.2 Callers updated
- [ ] 3.5.3 Alias removed
- [ ] 3.5.4 Validation passes

### Gate 3.6: Phase 3 Full Stress Test Suite

**Run ALL stress tests** (not just sample):

```bash
# Full stress test validation (21 plays)
python trade_cli.py backtest play-normalize-batch --dir tests/stress/plays

# Key backtests
python trade_cli.py backtest run --play tests/stress/plays/S_14_btc_swing_structure.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_18_btc_derived_zones.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_20_btc_multi_tf_structures.yml --smoke
python trade_cli.py backtest run --play tests/stress/plays/S_21_btc_full_complexity.yml --smoke
```

- [ ] 3.6.1 All 21 stress plays normalize
- [ ] 3.6.2 S_14 trades match baseline
- [ ] 3.6.3 S_18 trades match baseline
- [ ] 3.6.4 S_20 trades match baseline
- [ ] 3.6.5 S_21 trades match baseline

### Gate 3.7: Security Audit

**Invoke security-auditor agent** to verify:
- No trading logic affected
- No risk calculation changes
- No position sizing changes

- [ ] 3.7.1 Security audit complete
- [ ] 3.7.2 No safety issues found

### Gate 3.8: Phase 3 Commit

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: remove all backward compat aliases (Phase 3)

Breaking Changes:
- stop_reason → exit_type
- start_time/end_time → start_ts/end_ts
- ltf_tf, bar_ltf, features_ltf → canonical names
- Legacy "data" config key removed
- epoch_tracking.timeframes → tfs

All callers updated. Security audit passed.
GATE 3.6 VALIDATION: PASSED (21/21 stress tests)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
git tag -a legacy-cleanup-phase3 -m "All backward compat aliases removed"
```

- [ ] 3.8.1 Commit created
- [ ] 3.8.2 Tag created

---

## Phase 4: Minor Cleanups (LOW RISK)

**Objective**: Fix remaining legacy patterns.
**Risk**: LOW
**Agent**: `orchestrator`

### Gate 4.1: os.path → pathlib

**File**: `src/forge/generation/indicator_stress_test.py:7`

**Validation**:
```bash
python -c "from src.forge.generation.indicator_stress_test import *"
```

- [ ] 4.1.1 Replaced os.path with pathlib
- [ ] 4.1.2 Import check passes

### Gate 4.2: .format() → f-strings (selective)

**Review**: `src/forge/audits/audit_in_memory_parity.py:89`

Only convert STATIC string cases. Keep dynamic templates.

- [ ] 4.2.1 Reviewed .format() usages
- [ ] 4.2.2 Static cases converted
- [ ] 4.2.3 Dynamic templates preserved

### Gate 4.3: Phase 4 Validation

```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
```

- [ ] 4.3.1 All validation passes

### Gate 4.4: Phase 4 Commit

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: minor legacy cleanups (Phase 4)

- os.path → pathlib in forge generation
- Static .format() → f-strings

GATE 4.3 VALIDATION: PASSED

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
git tag -a legacy-cleanup-phase4 -m "Minor cleanups complete"
```

- [ ] 4.4.1 Commit created
- [ ] 4.4.2 Tag created

---

## Phase 5-7: Modular Refactoring (DEFERRED)

**Status**: DEFERRED - High effort, separate initiative.

These phases involve splitting large files (2500+ lines) into modules:
- Phase 5: `src/utils/cli_display.py` (2507 lines)
- Phase 6: `src/data/historical_data_store.py` (1854 lines)
- Phase 7: `src/backtest/runtime/snapshot_view.py` (1748 lines)

**Recommendation**: Execute these as a separate workstream after Phases 1-4 are stable.

---

## Post-Cleanup: Documentation Update

**Agent**: `docs-writer`

After all phases complete, update:
- [ ] `docs/SESSION_HANDOFF.md` - Summary of changes
- [ ] `docs/todos/TODO.md` - Mark cleanup complete
- [ ] `CLAUDE.md` - Remove references to removed aliases (if any)

---

## Rollback Procedures

### Per-Gate Rollback

If validation fails at any gate:

```bash
# Revert specific file
git checkout -- <file>

# Or revert all uncommitted changes
git checkout -- .
```

### Per-Phase Rollback

If phase commit causes issues later:

```bash
# Return to previous phase tag
git reset --hard legacy-cleanup-phase<N-1>
```

### Full Rollback

```bash
git reset --hard legacy-cleanup-baseline
```

---

## Stress Test Cards Reference

| Play | Description | Key Feature Tested |
|------|-------------|-------------------|
| S_01_btc_single_ema | Single indicator | Basic EMA |
| S_02_btc_rsi_threshold | RSI threshold | Momentum |
| S_06_btc_ema_crossover | EMA crossover | Cross operators |
| S_14_btc_swing_structure | Swing detection | Structure system |
| S_15_btc_fibonacci | Fibonacci levels | Derived structures |
| S_18_btc_derived_zones | Derived zones | K slots + aggregates |
| S_20_btc_multi_tf_structures | Multi-TF | HTF forward-fill |
| S_21_btc_full_complexity | All structures | Full integration |

---

## Execution Summary

| Phase | Risk | Gates | Key Validation |
|-------|------|-------|----------------|
| 0 | None | 4 | Baseline capture |
| 1 | Low | 6 | Typing modernization |
| 2 | Medium | 4 | Unused alias removal |
| 3 | High | 8 | Used alias removal + security audit |
| 4 | Low | 4 | Minor cleanups |
| **Total** | - | **26** | - |

**Estimated Time**: 2-3 hours with validation
