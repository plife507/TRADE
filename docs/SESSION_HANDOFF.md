# Session Handoff

**Date**: 2026-01-11
**Status**: Ready for Legacy Cleanup Execution

---

## What Was Done This Session

### Comprehensive Codebase Audit

Launched an orchestrator agent with parallel code-reviewer agents to audit the entire codebase for:
- Legacy code patterns violating CLAUDE.md rules
- Modular refactoring opportunities
- Backward compatibility shims that should be removed

### Findings Summary

**P0 - Critical (9 files with legacy typing)**:
| File | Issue |
|------|-------|
| `src/cli/styles.py` | `Optional, List, Dict, Any` imports |
| `src/cli/art_stylesheet.py` | `Optional` import |
| `src/tools/diagnostics_tools.py` | `Optional, Dict, Any` imports |
| `src/backtest/simulated_risk_manager.py` | `Optional` import |
| `src/backtest/prices/validation.py` | `Optional` import |
| `src/backtest/runtime/quote_state.py` | `Optional` import |
| `src/core/exchange_instruments.py` | `Dict` import |
| `src/backtest/rules/dsl_nodes/base.py` | `Union` type usage |

**P1 - Backward Compat Aliases (11 locations)**:
- `TIMEFRAMES` alias in constants.py
- `stop_reason`, `start_time/end_time` aliases in types.py
- `ltf_tf`, `bar_ltf`, `features_ltf` aliases in runtime/types.py
- `GATE_CODE_DESCRIPTIONS` deprecated alias
- `registry` deprecated method in feature_frame_builder.py
- `parse_play_blocks` alias in dsl_parser.py
- Legacy "data" key handling in config.py and diagnostics_tools.py

**Large Files for Modular Refactoring**:
- `src/utils/cli_display.py` (2507 lines)
- `src/data/historical_data_store.py` (1854 lines)
- `src/backtest/runtime/snapshot_view.py` (1748 lines)

### Created Gated Refactoring Plan

Created `docs/todos/LEGACY_CLEANUP_TODO.md` with:
- 8 phases, 25+ validation gates
- Real backtest validation between each gate
- Git tags at phase completion for rollback
- Learned from previous failed cleanup attempt (2026-01-10)

---

## Next Session: Execute Legacy Cleanup

### Starting Point

```bash
# 1. Verify baseline is passing
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays

# 2. Create baseline tag
git tag -a legacy-cleanup-baseline -m "Pre-cleanup baseline"

# 3. Begin Phase 1, Gate 1.1
```

### Execution Order

1. **Phase 0**: Capture baseline (tag it)
2. **Phase 1**: Typing modernization (LOW RISK)
   - Gate 1.1: CLI modules (2 files)
   - Gate 1.2: Tools module (1 file)
   - Gate 1.3: Backtest modules (4 files)
   - Gate 1.4: Core module (1 file)
3. **Phase 2**: Remove unused aliases (MEDIUM RISK)
4. **Phase 3**: Remove used aliases (HIGH RISK)
5. **Phase 4**: Minor cleanups
6. **Phases 5-7**: Modular refactoring (HIGH EFFORT)

### Key Validation Commands

```bash
# Quick check (use between small changes)
python trade_cli.py backtest play-normalize tests/validation/plays/V_130_last_price_vs_close.yml

# Full normalization (use at gate completion)
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays

# Unit audits (use at phase completion)
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup
```

### Safety Rules

1. **One gate at a time** - Never skip validation
2. **Commit on green** - Only commit when validation passes
3. **Revert on red** - If validation fails, `git checkout -- <file>`
4. **Tag at phase end** - `git tag -a legacy-cleanup-phaseN`

---

## Files Changed This Session

| File | Change |
|------|--------|
| `docs/todos/LEGACY_CLEANUP_TODO.md` | **NEW** - Comprehensive gated cleanup plan |
| `docs/todos/TODO.md` | Updated Next Steps to reference cleanup plan |
| `docs/SESSION_HANDOFF.md` | **NEW** - This file |

---

## Context for Next Agent

- All 343 stress tests currently passing
- Validation tiers 0-4 all green
- Previous cleanup attempt (2026-01-10) was abandoned - this plan is more cautious
- The TODO document has explicit validation commands for each gate
- Start with Phase 1 (typing) as it's lowest risk
