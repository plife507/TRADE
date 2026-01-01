# TRADE Repository Reorganization Plan

**STATUS:** EXECUTED (December 17, 2025)  
**PURPOSE:** Document reorganization decisions and track execution  
**AUTHORITY:** Per user authorization to reorganize for audit alignment

---

## Summary

This document tracks all file/folder moves made during the December 2025 audit.

---

## Executed Moves

### Move 1: Create Docs Structure (Phase 0)

| Action | Details |
|--------|---------|
| Created | `docs/architecture/` |
| Created | `docs/domains/` |
| Created | `docs/modules/` |
| Created | `docs/data/` |
| Created | `docs/strategy_factory/` |
| Created | `docs/runbooks/` |
| Created | `docs/audits/` |
| Created | `docs/audits/tests/` |
| Created | `docs/audits/bugs/` |
| Created | `docs/audits/validations/` |
| Created | `docs/reference/` |
| Created | `docs/index/` |

**Rationale:** Establish normalized docs structure matching domain model.

### Move 2: Create TODOs Structure

| Action | Details |
|--------|---------|
| Created | `docs/todos/` |
| Created | `docs/todos/archived/` |
| Copied | `docs/_archived/todos__array_backed_hot_loop_phases.md` → `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md` |
| Copied | `docs/_archived/todos__backtest_analytics_phases.md` → `docs/todos/BACKTEST_ANALYTICS_PHASES.md` |
| Created | `docs/todos/INDEX.md` |

**Rationale:** CLAUDE.md references `docs/todos/` as canonical location for active TODO documents. Moved active TODOs from `_archived/` to proper location.

---

## Recommended Moves (Not Yet Executed)

### Recommendation 1: Consolidate Audit Code

**Current State:**
```
src/backtest/
├── audit_in_memory_parity.py
├── audit_math_parity.py
├── audit_snapshot_plumbing_parity.py
├── artifact_parity_verifier.py
├── toolkit_contract_audit.py
```

**Proposed State:**
```
src/backtest/audits/
├── __init__.py
├── in_memory_parity.py
├── math_parity.py
├── snapshot_plumbing.py
├── artifact_verifier.py
└── contract_audit.py
```

**Rationale:** Group related audit code for discoverability.

**Follow-up Fixes Required:**
- Update imports in `src/backtest/__init__.py`
- Update imports in `src/tools/backtest_cli_wrapper.py`
- Update CLI menu references

**Status:** DOCUMENTED, NOT EXECUTED (would require import updates)

---

### Recommendation 2: Clean Up Strategy Locations

**Current State:**
```
src/strategies/
├── configs/
│   ├── SOLUSDT_5m_ema_rsi_atr_pure.yml
│   └── SOLUSDT_5m_ema_rsi_atr_rules.yml
└── idea_cards/
    └── SOLUSDT_15m_ema_crossover.yml
```

**Proposed Actions:**
1. Move `src/strategies/configs/*.yml` → `configs/legacy/` (or delete if unused)
2. Delete `src/strategies/idea_cards/` contents (examples only)
3. Add README to `src/strategies/` explaining it contains base classes only

**Rationale:** Canonical IdeaCard location is `configs/idea_cards/`. These are confusing duplicates.

**Follow-up Fixes Required:**
- Check if any code references these files
- Update any hardcoded paths

**Status:** DOCUMENTED, NOT EXECUTED (need to verify no references)

---

### Recommendation 3: Resolve Duplicate ExchangeState

**Current State:**
- `src/backtest/sim/types.py` — `ExchangeState` dataclass
- `src/backtest/runtime/types.py` — `ExchangeState` dataclass

**Proposed Action:**
1. Audit which is used where
2. Keep one, alias or delete the other
3. Update imports

**Rationale:** Duplicate definitions cause confusion and potential bugs.

**Status:** DOCUMENTED, NOT EXECUTED (needs usage audit)

---

### Recommendation 4: Rename tests/ Folder

**Current State:**
```
tests/
├── helpers/
│   ├── test_indicator_metadata.py
│   └── test_metadata_integration.py
```

**Proposed State:**
```
test_helpers/
├── indicator_metadata.py
└── metadata_integration.py
```

**Rationale:** 
- No pytest files exist in this codebase (by design)
- Folder name `tests/` implies pytest, which is misleading
- Files are helpers, not tests

**Follow-up Fixes Required:**
- Update any imports of these files

**Status:** DOCUMENTED, NOT EXECUTED (low priority)

---

## Created Documents

| Document | Path | Purpose |
|----------|------|---------|
| DOCS_INDEX.md | `docs/DOCS_INDEX.md` | Navigation hub |
| REPO_INVENTORY.md | `docs/index/REPO_INVENTORY.md` | File inventory |
| COVERAGE_CHECKLIST.md | `docs/index/COVERAGE_CHECKLIST.md` | Review tracking |
| DOMAIN_MAP.md | `docs/domains/DOMAIN_MAP.md` | Domain ownership |
| MODULE_NOTES.md | `docs/modules/MODULE_NOTES.md` | Module documentation |
| DATA_MODULE.md | `docs/data/DATA_MODULE.md` | Data deep-dive |
| AUDIT_MODULE.md | `docs/audits/AUDIT_MODULE.md` | Audit deep-dive |
| STRATEGY_FACTORY.md | `docs/strategy_factory/STRATEGY_FACTORY.md` | Strategy factory |
| ARCH_SNAPSHOT.md | `docs/architecture/ARCH_SNAPSHOT.md` | Architecture |
| PROJECT_STATUS.md | `docs/runbooks/PROJECT_STATUS.md` | Current status |
| tests/INDEX.md | `docs/audits/tests/INDEX.md` | Test index |
| bugs/INDEX.md | `docs/audits/bugs/INDEX.md` | Bug index |
| validations/INDEX.md | `docs/audits/validations/INDEX.md` | Validation index |
| REORGANIZATION_PLAN.md | `docs/index/REORGANIZATION_PLAN.md` | This document |

---

## Follow-up Actions (For Future Execution)

1. **Fix P0 blocker first** — All reorganization secondary to fixing input-source bug
2. **Consolidate audit code** — After P0 fixed, move audit files
3. **Clean up strategy configs** — Low priority, document in meantime
4. **Resolve duplicate types** — Needs careful usage audit

---

