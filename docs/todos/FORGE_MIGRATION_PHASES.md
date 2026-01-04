# Forge Migration Phases

**Status**: NOT STARTED
**Total Phases**: 8
**Cleanup Agent**: Runs after Phase 7

See `FORGE_MIGRATION_RULES.md` for forward-only migration rules.

---

## Phase Overview

| Phase | Description | Files Affected | Est. Complexity |
|-------|-------------|----------------|-----------------|
| P1 | Directory renames | 21 YAML files, paths | Low |
| P2 | Core file renames | 5 Python files | Medium |
| P3 | Class/type renames | ~30 files | High |
| P4 | Function renames | ~40 files | High |
| P5 | Variable/param renames | ~50 files | Medium |
| P6 | CLI menu updates | ~10 files | Low |
| P7 | Config/constant updates | ~5 files | Low |
| P8 | Cleanup agent sweep | All files | Low |

---

## Phase 1: Directory Renames

**Goal**: Move config directories to new names

### Tasks
- [ ] P1.1: Rename `configs/idea_cards/` → `configs/plays/`
  - [ ] Move `_validation/` subdirectory (15 files)
  - [ ] Move `_stress_test/` subdirectory (6 files)
  - [ ] Move `README.md`
- [ ] P1.2: Rename `src/strategies/idea_cards/` → `src/strategies/plays/`
  - [ ] Move YAML files
  - [ ] Move `__init__.py`
- [ ] P1.3: Update all path references in code
  - [ ] `src/config/constants.py` - IDEA_CARDS_DIR constant
  - [ ] `src/backtest/idea_card.py` - default paths
  - [ ] `src/cli/menus/backtest_menu.py` - menu paths
  - [ ] `src/tools/backtest_ideacard_tools.py` - tool paths
- [ ] P1.4: Update `.gitignore` if needed
- [ ] P1.5: Validate - all paths resolve correctly

**Acceptance**:
- `configs/plays/` exists with all files
- `configs/idea_cards/` does NOT exist
- Zero `idea_cards` in path strings (grep check)

---

## Phase 2: Core File Renames

**Goal**: Rename the main IdeaCard Python files

### Tasks
- [ ] P2.1: `src/backtest/idea_card.py` → `src/backtest/play.py`
- [ ] P2.2: `src/backtest/idea_card_yaml_builder.py` → `src/backtest/play_yaml_builder.py`
- [ ] P2.3: `src/backtest/gates/idea_card_generator.py` → `src/backtest/gates/play_generator.py`
- [ ] P2.4: `src/tools/backtest_ideacard_tools.py` → `src/tools/backtest_play_tools.py`
- [ ] P2.5: `src/backtest/audits/audit_ideacard_value_flow.py` → `src/backtest/audits/audit_play_value_flow.py`
- [ ] P2.6: `src/cli/menus/backtest_ideacard_menu.py` → `src/cli/menus/backtest_play_menu.py`
- [ ] P2.7: Update all imports in `__init__.py` files
  - [ ] `src/backtest/__init__.py`
  - [ ] `src/backtest/gates/__init__.py`
  - [ ] `src/backtest/audits/__init__.py`
  - [ ] `src/tools/__init__.py`
  - [ ] `src/cli/menus/__init__.py`
- [ ] P2.8: Update all import statements across codebase (~74 files)
- [ ] P2.9: Validate - `python -c "from src.backtest import play"`

**Acceptance**:
- All renamed files exist at new paths
- Zero imports from old file names
- Import check passes

---

## Phase 3: Class and Type Renames

**Goal**: Rename IdeaCard class and related types

### Primary Renames
- [ ] P3.1: `class IdeaCard` → `class Play` in `src/backtest/play.py`
- [ ] P3.2: `class IdeaCardConfig` → `class PlayConfig` (if exists)
- [ ] P3.3: `class IdeaCardBuilder` → `class PlayBuilder`
- [ ] P3.4: `class IdeaCardYamlBuilder` → `class PlayYamlBuilder`
- [ ] P3.5: `class IdeaCardGenerator` → `class PlayGenerator`

### Type Hints
- [ ] P3.6: Update all type hints `IdeaCard` → `Play` across codebase
- [ ] P3.7: Update all type hints `list[IdeaCard]` → `list[Play]`
- [ ] P3.8: Update TypedDict definitions if any

### Dataclass Fields
- [ ] P3.9: Rename fields named `idea_card` to `play` in dataclasses

### Files to Update (grep IdeaCard in src/)
```
src/backtest/engine.py
src/backtest/engine_factory.py
src/backtest/engine_data_prep.py
src/backtest/engine_feed_builder.py
src/backtest/runner.py
src/backtest/runtime/snapshot_view.py
src/backtest/runtime/preflight.py
src/backtest/rules/eval.py
src/backtest/rules/types.py
src/backtest/rules/compile.py
src/backtest/rules/strategy_blocks.py
src/backtest/rules/dsl_parser.py
src/backtest/rules/dsl_eval.py
src/backtest/features/feature_frame_builder.py
src/backtest/incremental/registry.py
src/backtest/incremental/base.py
src/backtest/incremental/state.py
src/backtest/incremental/detectors/*.py (6 files)
src/backtest/gates/*.py (3 files)
src/backtest/audits/*.py (7 files)
src/backtest/artifacts/*.py (4 files)
src/backtest/prices/*.py (4 files)
src/backtest/market_structure/spec.py
src/tools/backtest_*.py (4 files)
src/cli/menus/backtest_*.py (4 files)
src/cli/smoke_tests/*.py (3 files)
```

**Acceptance**:
- Zero `class IdeaCard` definitions
- Zero `IdeaCard` type hints
- All tests pass

---

## Phase 4: Function Renames

**Goal**: Rename all idea_card functions

### Primary Functions
- [ ] P4.1: `load_idea_card()` → `load_play()`
- [ ] P4.2: `save_idea_card()` → `save_play()`
- [ ] P4.3: `validate_idea_card()` → `validate_play()`
- [ ] P4.4: `parse_idea_card()` → `parse_play()`
- [ ] P4.5: `create_engine_from_idea_card()` → `create_engine_from_play()`
- [ ] P4.6: `normalize_idea_card()` → `normalize_play()`
- [ ] P4.7: `build_idea_card()` → `build_play()`
- [ ] P4.8: `generate_idea_card()` → `generate_play()`

### Factory/Builder Methods
- [ ] P4.9: `IdeaCardBuilder.from_yaml()` → `PlayBuilder.from_yaml()`
- [ ] P4.10: `IdeaCardYamlBuilder.build()` → `PlayYamlBuilder.build()`

### Tool Functions
- [ ] P4.11: `run_idea_card_tool()` → `run_play_tool()`
- [ ] P4.12: `list_idea_cards_tool()` → `list_plays_tool()`
- [ ] P4.13: `validate_idea_card_tool()` → `validate_play_tool()`

### Update All Call Sites
- [ ] P4.14: Update all function calls across codebase

**Acceptance**:
- Zero `idea_card` function names (grep check)
- All function calls updated
- Smoke test passes

---

## Phase 5: Variable and Parameter Renames

**Goal**: Rename variables, parameters, dict keys

### Variable Patterns
- [ ] P5.1: `idea_card` → `play` (local variables)
- [ ] P5.2: `idea_card_path` → `play_path`
- [ ] P5.3: `idea_card_config` → `play_config`
- [ ] P5.4: `idea_card_id` → `play_id`
- [ ] P5.5: `idea_card_name` → `play_name`
- [ ] P5.6: `idea_cards` → `plays` (lists/collections)

### Function Parameters
- [ ] P5.7: All function params `idea_card:` → `play:`
- [ ] P5.8: All function params `idea_card_path:` → `play_path:`

### Dict Keys (YAML structure stays same)
- [ ] P5.9: Internal dict keys if any

### Docstrings
- [ ] P5.10: Update all docstrings mentioning IdeaCard/idea_card

**Acceptance**:
- Zero `idea_card` variable names in Python (grep check)
- Docstrings updated
- No functional changes (pure rename)

---

## Phase 6: CLI Menu Updates

**Goal**: Update CLI menus and user-facing strings

### Menu Items
- [ ] P6.1: Update menu titles containing "IdeaCard"
- [ ] P6.2: Update menu option text
- [ ] P6.3: Update help strings
- [ ] P6.4: Update command names if exposed

### User Messages
- [ ] P6.5: Update print statements
- [ ] P6.6: Update error messages
- [ ] P6.7: Update logging messages

### Files
```
src/cli/menus/backtest_play_menu.py (renamed in P2)
src/cli/menus/backtest_menu.py
src/cli/menus/backtest_audits_menu.py
src/cli/menus/backtest_analytics_menu.py
trade_cli.py
```

**Acceptance**:
- User sees "Play" not "IdeaCard" in CLI
- Help text updated
- Error messages use new terminology

---

## Phase 7: Config and Constants

**Goal**: Update constants, env vars, config keys

### Constants
- [ ] P7.1: `IDEA_CARDS_DIR` → `PLAYS_DIR` in `src/config/constants.py`
- [ ] P7.2: Any `IDEACARD_*` constants → `PLAY_*`

### Environment Variables (if any)
- [ ] P7.3: Update env var names
- [ ] P7.4: Update `env.example`

### Config Schemas
- [ ] P7.5: Update any schema definitions

### Registry Entries
- [ ] P7.6: Update tool registry entries
- [ ] P7.7: Update any feature registry entries

**Acceptance**:
- Zero `IDEACARD` or `IDEA_CARD` constants
- Env vars updated
- Registry entries correct

---

## Phase 8: Cleanup Agent Sweep

**Goal**: Final verification and cleanup

### Verification Checks
- [ ] P8.1: Grep `IdeaCard` in `src/` - expect 0 matches
- [ ] P8.2: Grep `idea_card` in `src/` - expect 0 matches (except comments)
- [ ] P8.3: Grep `IDEACARD` in `src/` - expect 0 matches
- [ ] P8.4: Grep `idea_cards` in paths - expect 0 matches
- [ ] P8.5: Find files with `idea_card` in name - expect 0
- [ ] P8.6: Find directories with `idea_card` in name - expect 0

### Documentation Check
- [ ] P8.7: All CLAUDE.md files use new terminology
- [ ] P8.8: All README.md files updated
- [ ] P8.9: docs/specs/*.md use new terminology
- [ ] P8.10: docs/todos/*.md use new terminology

### Import Health
- [ ] P8.11: `python -c "import src.backtest"` passes
- [ ] P8.12: `python -c "from src.backtest import Play"` passes
- [ ] P8.13: `python -c "from src.tools import backtest_play_tools"` passes

### Smoke Tests
- [ ] P8.14: `python trade_cli.py --smoke data` passes
- [ ] P8.15: `python trade_cli.py --smoke full` passes (if backtest enabled)

### Final Cleanup
- [ ] P8.16: Remove any TODO comments about migration
- [ ] P8.17: Update this document status to COMPLETE
- [ ] P8.18: Archive this document to `docs/todos/archived/`

**Acceptance**:
- ALL checks pass
- Zero legacy references remain
- Codebase fully migrated

---

## Progress Tracking

| Phase | Status | Started | Completed | Commit |
|-------|--------|---------|-----------|--------|
| P1 | NOT STARTED | - | - | - |
| P2 | NOT STARTED | - | - | - |
| P3 | NOT STARTED | - | - | - |
| P4 | NOT STARTED | - | - | - |
| P5 | NOT STARTED | - | - | - |
| P6 | NOT STARTED | - | - | - |
| P7 | NOT STARTED | - | - | - |
| P8 | NOT STARTED | - | - | - |

---

## Rollback Plan

**There is no rollback plan.**

This is a forward-only migration. If something breaks:
1. Identify what's broken
2. Fix it forward
3. Continue migration

Do NOT:
- Revert commits
- Add compatibility shims
- Restore old file names
