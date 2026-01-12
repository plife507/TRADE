# Legacy Code Cleanup & Modular Refactoring

**Created**: 2026-01-11
**Status**: PLANNING
**Priority**: P1

---

## ⚠️ LESSONS LEARNED (2026-01-10)

A previous legacy cleanup attempt was **ABANDONED** due to widespread breakage. The deprecated aliases are deeply embedded. This plan uses **micro-gates** with validation between each step to prevent regression.

**Key Principle**: Every gate is a commit point. If validation fails, revert to the previous gate.

---

## Validation Commands Reference

```bash
# TIER 0 - Quick Check (~10 sec)
python trade_cli.py backtest play-normalize tests/validation/plays/V_130_last_price_vs_close.yml

# TIER 1 - Full Normalization (~30 sec)
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays

# TIER 2 - Unit Audits (~60 sec)
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup
python trade_cli.py backtest metrics-audit
python trade_cli.py backtest metadata-smoke

# TIER 3 - Structure Smoke (~30 sec)
python trade_cli.py backtest structure-smoke

# TIER 4 - Full Smoke (requires data)
python trade_cli.py --smoke full
```

---

## Phase 0: Baseline Capture (PRE-REQUISITE)

**Objective**: Establish passing baseline before ANY changes.

- [ ] 0.1 Run full validation suite and capture output
  ```bash
  python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays > baseline_normalize.txt 2>&1
  python trade_cli.py backtest audit-toolkit > baseline_audit.txt 2>&1
  python trade_cli.py backtest audit-rollup > baseline_rollup.txt 2>&1
  ```
- [ ] 0.2 Verify all pass (343 stress tests + tier0-tier4)
- [ ] 0.3 Create git tag: `git tag -a legacy-cleanup-baseline -m "Pre-cleanup baseline"`

**GATE 0 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
# Expected: All plays normalize without errors
```

---

## Phase 1: Typing Modernization (LOW RISK)

**Objective**: Replace legacy `typing` imports with modern Python 3.12+ syntax.

**Risk Level**: LOW - Pure syntax changes, no behavioral impact.

### Gate 1.1: CLI Module Typing (2 files)

**Files**:
- `src/cli/styles.py:14` - `Optional, List, Dict, Any`
- `src/cli/art_stylesheet.py:17` - `Optional`

**Changes**:
- [ ] 1.1.1 `src/cli/styles.py`: Replace `from typing import Optional, List, Dict, Any` → remove import
- [ ] 1.1.2 Replace all `Optional[X]` → `X | None`
- [ ] 1.1.3 Replace all `Dict[K, V]` → `dict[K, V]`
- [ ] 1.1.4 Replace all `List[T]` → `list[T]`
- [ ] 1.1.5 `src/cli/art_stylesheet.py`: Same pattern
- [ ] 1.1.6 Run import check: `python -c "from src.cli.styles import *; from src.cli.art_stylesheet import *"`

**GATE 1.1 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
# Both must pass before proceeding
```

### Gate 1.2: Tools Module Typing (1 file)

**Files**:
- `src/tools/diagnostics_tools.py:9` - `Optional, Dict, Any`

**Changes**:
- [ ] 1.2.1 Replace typing imports with modern syntax
- [ ] 1.2.2 Run import check: `python -c "from src.tools.diagnostics_tools import *"`

**GATE 1.2 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
```

### Gate 1.3: Backtest Module Typing (4 files)

**Files**:
- `src/backtest/simulated_risk_manager.py:15` - `Optional`
- `src/backtest/prices/validation.py:10` - `Optional`
- `src/backtest/runtime/quote_state.py:43` - `Optional`
- `src/backtest/rules/dsl_nodes/base.py:15,218` - `Union`

**Changes**:
- [ ] 1.3.1 `simulated_risk_manager.py`: Replace `Optional[X]` → `X | None`
- [ ] 1.3.2 `prices/validation.py`: Same pattern
- [ ] 1.3.3 `runtime/quote_state.py`: Same pattern
- [ ] 1.3.4 `dsl_nodes/base.py:15`: Remove `Union` import
- [ ] 1.3.5 `dsl_nodes/base.py:218`: Replace `Union[A, B, ...]` → `A | B | ...`
- [ ] 1.3.6 Run import check for all 4 files

**GATE 1.3 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest structure-smoke
# All must pass
```

### Gate 1.4: Core Module Typing (1 file)

**Files**:
- `src/core/exchange_instruments.py:12` - `Dict`

**Changes**:
- [ ] 1.4.1 Replace `Dict[K, V]` → `dict[K, V]`
- [ ] 1.4.2 Run import check

**GATE 1.4 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
```

### Phase 1 Commit Point

- [ ] 1.5.1 All Gate 1.x validations pass
- [ ] 1.5.2 Commit: `git commit -m "refactor: modernize typing imports (Phase 1)"`
- [ ] 1.5.3 Tag: `git tag -a legacy-cleanup-phase1 -m "Typing modernization complete"`

---

## Phase 2: Remove UNUSED Backward Compat Aliases (MEDIUM RISK)

**Objective**: Remove backward compatibility aliases that have NO callers.

**Risk Level**: MEDIUM - Must verify zero callers first.

### Gate 2.1: Audit Alias Usage

Before removing ANY alias, search for callers:

- [ ] 2.1.1 Search for `TIMEFRAMES` usage (alias for `TIMEFRAME_TO_BYBIT`)
  ```bash
  grep -r "TIMEFRAMES" src/ --include="*.py" | grep -v "TIMEFRAME_TO_BYBIT" | grep -v "constants.py"
  ```
- [ ] 2.1.2 Search for `GATE_CODE_DESCRIPTIONS` usage (deprecated alias)
  ```bash
  grep -r "GATE_CODE_DESCRIPTIONS" src/ --include="*.py"
  ```
- [ ] 2.1.3 Search for `registry` usage in feature_frame_builder.py callers
  ```bash
  grep -r "\.registry\(" src/ --include="*.py"
  ```
- [ ] 2.1.4 Search for `parse_play_blocks` usage (alias for `parse_play_actions`)
  ```bash
  grep -r "parse_play_blocks" src/ --include="*.py"
  ```
- [ ] 2.1.5 Document findings in table below

**Alias Usage Audit Results**:
| Alias | Location | Callers Found | Can Remove? |
|-------|----------|---------------|-------------|
| `TIMEFRAMES` | constants.py:283 | TBD | TBD |
| `GATE_CODE_DESCRIPTIONS` | state_types.py:113 | TBD | TBD |
| `registry` (deprecated) | feature_frame_builder.py:335 | TBD | TBD |
| `parse_play_blocks` | dsl_parser.py:849 | TBD | TBD |

**GATE 2.1 VALIDATION**: No code changes yet - audit only.

### Gate 2.2: Remove Zero-Caller Aliases

For each alias with ZERO callers from Gate 2.1:

- [ ] 2.2.1 Remove alias (one at a time)
- [ ] 2.2.2 Run validation after EACH removal
- [ ] 2.2.3 If validation fails, revert and mark as "HAS CALLERS"

**GATE 2.2 VALIDATION** (after each removal):
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
```

### Phase 2 Commit Point

- [ ] 2.3.1 All zero-caller aliases removed
- [ ] 2.3.2 All validations pass
- [ ] 2.3.3 Commit: `git commit -m "refactor: remove unused backward compat aliases (Phase 2)"`
- [ ] 2.3.4 Tag: `git tag -a legacy-cleanup-phase2 -m "Unused aliases removed"`

---

## Phase 3: Remove USED Backward Compat Aliases (HIGH RISK)

**Objective**: Update callers, then remove remaining backward compat aliases.

**Risk Level**: HIGH - Must update all callers first.

### Gate 3.1: `stop_reason` → `exit_type` Migration

**Location**: `src/backtest/types.py:554-556`

- [ ] 3.1.1 Find all `stop_reason` callers
  ```bash
  grep -r "\.stop_reason" src/ --include="*.py"
  grep -r "stop_reason=" src/ --include="*.py"
  ```
- [ ] 3.1.2 Update each caller to use `exit_type`
- [ ] 3.1.3 Remove `stop_reason` property alias
- [ ] 3.1.4 Validate

**GATE 3.1 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-rollup
```

### Gate 3.2: `start_time/end_time` → `start_ts/end_ts` Migration

**Location**: `src/backtest/types.py:568-575`

- [ ] 3.2.1 Find all `start_time`/`end_time` callers
- [ ] 3.2.2 Update each caller to use `start_ts`/`end_ts`
- [ ] 3.2.3 Remove property aliases
- [ ] 3.2.4 Validate

**GATE 3.2 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest metrics-audit
```

### Gate 3.3: Runtime Types Aliases Migration

**Location**: `src/backtest/runtime/types.py:323-337`
**Aliases**: `ltf_tf`, `bar_ltf`, `features_ltf`

- [ ] 3.3.1 Find all callers for each alias
- [ ] 3.3.2 Update callers to canonical names
- [ ] 3.3.3 Remove aliases (one at a time, validate between each)
- [ ] 3.3.4 Validate

**GATE 3.3 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest structure-smoke
```

### Gate 3.4: Config Legacy Key Migration

**Location**:
- `src/config/config.py:252` - Legacy "data" key
- `src/tools/diagnostics_tools.py:497` - Legacy "data" key

- [ ] 3.4.1 Find all code using legacy "data" key in configs
- [ ] 3.4.2 Update to use new key structure
- [ ] 3.4.3 Remove legacy key handling
- [ ] 3.4.4 Validate

**GATE 3.4 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py --smoke data
```

### Gate 3.5: epoch_tracking `timeframes` → `tfs`

**Location**: `src/utils/epoch_tracking.py:248-252`

- [ ] 3.5.1 Find all `timeframes` attribute callers
- [ ] 3.5.2 Update to use `tfs`
- [ ] 3.5.3 Remove alias
- [ ] 3.5.4 Validate

**GATE 3.5 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
```

### Phase 3 Commit Point

- [ ] 3.6.1 All backward compat aliases removed
- [ ] 3.6.2 All callers updated
- [ ] 3.6.3 Full validation suite passes
- [ ] 3.6.4 Commit: `git commit -m "refactor: remove all backward compat aliases (Phase 3)"`
- [ ] 3.6.5 Tag: `git tag -a legacy-cleanup-phase3 -m "All aliases removed"`

---

## Phase 4: Minor Cleanups (LOW RISK)

**Objective**: Fix remaining minor legacy patterns.

### Gate 4.1: os.path → pathlib

**Location**: `src/forge/generation/indicator_stress_test.py:7`

- [ ] 4.1.1 Replace `os.path` usage with `pathlib.Path`
- [ ] 4.1.2 Validate imports work

**GATE 4.1 VALIDATION**:
```bash
python -c "from src.forge.generation.indicator_stress_test import *"
```

### Gate 4.2: .format() → f-strings (WHERE APPROPRIATE)

**Note**: Some `.format()` usage is legitimate for dynamic templates. Only convert static cases.

**Files to review**:
- `src/forge/audits/audit_in_memory_parity.py:89`

- [ ] 4.2.1 Review each `.format()` usage
- [ ] 4.2.2 Convert static string cases to f-strings
- [ ] 4.2.3 Leave dynamic template cases unchanged
- [ ] 4.2.4 Validate

**GATE 4.2 VALIDATION**:
```bash
python trade_cli.py backtest audit-toolkit
```

### Phase 4 Commit Point

- [ ] 4.3.1 All minor cleanups complete
- [ ] 4.3.2 Commit: `git commit -m "refactor: minor legacy cleanups (Phase 4)"`
- [ ] 4.3.3 Tag: `git tag -a legacy-cleanup-phase4 -m "Minor cleanups complete"`

---

## Phase 5: Modular Refactoring - CLI Display (HIGH EFFORT)

**Objective**: Split `src/utils/cli_display.py` (2507 lines) into focused modules.

**Risk Level**: HIGH - Large structural change.

### Gate 5.0: Pre-Analysis

- [ ] 5.0.1 Map all public exports from `cli_display.py`
- [ ] 5.0.2 Identify natural module boundaries
- [ ] 5.0.3 Document proposed split structure

**Proposed Structure**:
```
src/utils/cli_display/
├── __init__.py          # Re-exports for backward compat (temporary)
├── action_registry.py   # BacktestActionRegistry, descriptors
├── formatters.py        # Formatting utilities
├── tables.py            # Table rendering
├── progress.py          # Progress bars, spinners
└── output.py            # Output helpers
```

### Gate 5.1: Create Module Structure

- [ ] 5.1.1 Create `src/utils/cli_display/` directory
- [ ] 5.1.2 Create `__init__.py` with ALL current exports (no breaking changes)
- [ ] 5.1.3 Validate all imports still work

**GATE 5.1 VALIDATION**:
```bash
python -c "from src.utils.cli_display import *"
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
```

### Gate 5.2: Extract Action Registry

- [ ] 5.2.1 Move `BacktestActionRegistry` and related to `action_registry.py`
- [ ] 5.2.2 Update `__init__.py` to re-export
- [ ] 5.2.3 Validate

**GATE 5.2 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
```

### Gate 5.3: Extract Formatters

- [ ] 5.3.1 Move formatting functions to `formatters.py`
- [ ] 5.3.2 Update `__init__.py`
- [ ] 5.3.3 Validate

### Gate 5.4: Extract Tables

- [ ] 5.4.1 Move table rendering to `tables.py`
- [ ] 5.4.2 Update `__init__.py`
- [ ] 5.4.3 Validate

### Gate 5.5: Extract Progress

- [ ] 5.5.1 Move progress bars/spinners to `progress.py`
- [ ] 5.5.2 Update `__init__.py`
- [ ] 5.5.3 Validate

### Gate 5.6: Update Callers (Remove __init__.py re-exports)

- [ ] 5.6.1 Find all `from src.utils.cli_display import X` statements
- [ ] 5.6.2 Update to import from specific submodule
- [ ] 5.6.3 Remove re-exports from `__init__.py`
- [ ] 5.6.4 Delete original monolithic file
- [ ] 5.6.5 Full validation

**GATE 5.6 VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup
python trade_cli.py --smoke full
```

### Phase 5 Commit Point

- [ ] 5.7.1 `cli_display.py` fully modularized
- [ ] 5.7.2 All validations pass
- [ ] 5.7.3 Commit: `git commit -m "refactor: modularize cli_display (Phase 5)"`
- [ ] 5.7.4 Tag: `git tag -a legacy-cleanup-phase5 -m "cli_display modularized"`

---

## Phase 6: Modular Refactoring - Historical Data Store (HIGH EFFORT)

**Objective**: Split `src/data/historical_data_store.py` (1854 lines) by data type.

### Gate 6.0: Pre-Analysis

- [ ] 6.0.1 Map all public methods
- [ ] 6.0.2 Identify data type boundaries (OHLCV, funding, OI)
- [ ] 6.0.3 Document proposed split

**Proposed Structure**:
```
src/data/historical_data_store/
├── __init__.py          # HistoricalDataStore facade
├── base.py              # Base DB connection, common utilities
├── ohlcv.py             # OHLCV operations
├── funding.py           # Funding rate operations
├── open_interest.py     # OI operations
└── maintenance.py       # Heal, cleanup, vacuum
```

### Gate 6.1-6.6: Similar pattern to Phase 5

(Follow same gated extraction pattern as Phase 5)

**GATE 6.x VALIDATION**:
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py --smoke data_extensive
```

---

## Phase 7: Modular Refactoring - Snapshot View (MEDIUM EFFORT)

**Objective**: Split `src/backtest/runtime/snapshot_view.py` (1748 lines).

**Proposed Structure**:
```
src/backtest/runtime/snapshot_view/
├── __init__.py          # RuntimeSnapshotView main class
├── accessors.py         # Property accessors (prices, indicators)
├── history.py           # Historical lookback methods
└── helpers.py           # Utility methods
```

(Follow same gated extraction pattern)

---

## Phase 8: Future Refactoring Candidates (BACKLOG)

These files are >1000 lines but lower priority:

| File | Lines | Notes |
|------|-------|-------|
| `src/backtest/engine.py` | 1685 | Already well-structured |
| `src/tools/backtest_play_tools.py` | 1400 | Group by operation type |
| `src/cli/smoke_tests/structure.py` | 1359 | Split by test category |
| `src/forge/generation/generate_100_setups.py` | 1300 | Split generator + templates |
| `src/backtest/execution_validation.py` | 1262 | Split validation types |
| `src/backtest/indicator_registry.py` | 1198 | Already well-organized |
| `src/backtest/runtime/preflight.py` | 1196 | Split checks + reporting |
| `src/tools/position_tools.py` | 1165 | Group by operation |
| `src/data/realtime_bootstrap.py` | 1078 | Split by bootstrap stage |
| `src/tools/order_tools.py` | 1069 | Group by order type |
| `src/backtest/runner.py` | 1033 | Consider splitting run modes |
| `src/backtest/metrics.py` | 1030 | Group by metric category |

---

## Execution Rules

### Before EVERY Code Change

1. **Read the file** - Never modify without reading first
2. **Small changes** - One logical change per gate
3. **Validate immediately** - Run gate validation after each change
4. **Commit on green** - Only commit when validation passes

### If Validation Fails

1. **STOP** - Do not continue to next gate
2. **Diagnose** - Understand what broke
3. **Revert if needed** - `git checkout -- <file>` to restore
4. **Fix forward** - Address the root cause, don't work around it

### Commit Message Format

```
refactor: <what changed> (Phase X.Y)

- Specific change 1
- Specific change 2

GATE X.Y VALIDATION: PASSED
```

---

## Summary

| Phase | Risk | Effort | Description |
|-------|------|--------|-------------|
| 0 | None | Low | Baseline capture |
| 1 | Low | Low | Typing modernization (9 files) |
| 2 | Medium | Low | Remove unused aliases |
| 3 | High | Medium | Remove used aliases |
| 4 | Low | Low | Minor cleanups |
| 5 | High | High | Modularize cli_display.py |
| 6 | High | High | Modularize historical_data_store.py |
| 7 | Medium | Medium | Modularize snapshot_view.py |
| 8 | - | - | Backlog |

**Total Estimated Gates**: 25+ validation checkpoints

---

## Quick Start

```bash
# Start Phase 0
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
git tag -a legacy-cleanup-baseline -m "Pre-cleanup baseline"

# Then proceed gate by gate...
```
