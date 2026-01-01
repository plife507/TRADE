# CLI Menu & Tools Alignment

**Status**: Phases 1-6 ✅ COMPLETE
**Created**: 2026-01-01
**Goal**: Align CLI menus with all available tools, refactor for modularity

## Problem Statement

The CLI has **14 tools** defined but not exposed in menus:
- IdeaCard execution tools (7)
- Audit suite tools (5)
- Artifact verification (1)
- Time-based analytics (1)

The `backtest_cli_wrapper.py` (1,808 lines) mixes multiple concerns.
The backtest menu only exposes legacy SystemConfig path.

## Architecture Principle

```
CLI Menus (human interface)
    └── Tools Layer (reusable functions)
            └── Called by: CLI, other .py files, agents
```

All functionality MUST be in tools layer. Menus are thin wrappers.

---

## Phase 1: IdeaCard Submenu ✅

**Goal**: Expose IdeaCard workflow in CLI

### 1.1 Create IdeaCard Submenu Handler

- [x] Create `src/cli/menus/backtest_ideacard_menu.py`
- [x] Menu options:
  1. List IdeaCards → `backtest_list_idea_cards_tool`
  2. Run IdeaCard Backtest → `backtest_run_idea_card_tool`
  3. Preflight Check → `backtest_preflight_idea_card_tool`
  4. Data Fix (sync/heal) → `backtest_data_fix_tool`
  5. View Indicators → `backtest_indicators_tool`
  6. Normalize IdeaCard → `backtest_idea_card_normalize_tool`
  7. Back

### 1.2 Wire to Backtest Menu

- [x] Update `src/cli/menus/backtest_menu.py`
- [x] Add "IdeaCard Backtests" as option 1
- [x] Import and call ideacard submenu handler
- [x] Removed all legacy SystemConfig code (forward-only)

### 1.3 Verify Tools Export

- [x] Ensure all IdeaCard tools exported from `src/tools/__init__.py`
- [x] Added `backtest_idea_card_normalize_tool` to exports
- [x] Test each tool can be imported and called

**Acceptance**: Can run IdeaCard backtest from CLI menu ✅

---

## Phase 2: Audits Submenu ✅

**Goal**: Expose full audit suite in CLI

### 2.1 Create Audits Submenu Handler

- [x] Create `src/cli/menus/backtest_audits_menu.py`
- [x] Menu options:
  1. Toolkit Contract Audit → `backtest_audit_toolkit_tool`
  2. Rollup Parity Audit → `backtest_audit_rollup_parity_tool`
  3. Math Parity Audit → `backtest_math_parity_tool`
  4. Snapshot Plumbing Audit → `backtest_audit_snapshot_plumbing_tool`
  5. Artifact Parity Check → `verify_artifact_parity_tool`
  6. Run All Quick Audits → sequential run of quick audits
  7. Back

### 2.2 Export Missing Audit Tools

- [x] Add to `src/tools/__init__.py`:
  - `backtest_audit_toolkit_tool`
  - `backtest_math_parity_tool`
  - `backtest_audit_snapshot_plumbing_tool`
  - `backtest_audit_rollup_parity_tool`
  - `backtest_audit_in_memory_parity_tool`

### 2.3 Wire to Backtest Menu

- [x] Add "Audits & Verification" as option 2

**Acceptance**: Can run any audit from CLI menu ✅

---

## Phase 3: Analytics Submenu ✅

**Goal**: Expose analytics and results viewing

### 3.1 Create Analytics Submenu Handler

- [x] Create `src/cli/menus/backtest_analytics_menu.py`
- [x] Menu options:
  1. List Recent Runs → scan backtests/ for result.json
  2. View Run Results → display result.json formatted
  3. View Time-Based Returns → display returns.json (Phase 4 feature)
  4. Compare Two Runs → side-by-side metrics comparison
  5. Back

### 3.2 Implementation Notes

- All analytics functions implemented inline (simple file operations)
- Scans `backtests/` directory for result.json files
- Displays best/worst periods from returns.json (time-based analytics)
- Color-coded comparison table with diffs

### 3.3 Wire to Backtest Menu

- [x] Add "Analytics & Results" as option 3

**Acceptance**: Can view backtest results and time-based returns from CLI ✅

---

## Phase 4: Tools Layer Refactor ✅

**Goal**: Split `backtest_cli_wrapper.py` for maintainability

### 4.1 Split by Category

- [x] Create `src/tools/backtest_ideacard_tools.py`
  - Moved: preflight, run, data_fix, list, indicators, normalize, normalize_batch tools

- [x] Create `src/tools/backtest_audit_tools.py`
  - Moved: toolkit, math_parity, snapshot_plumbing, rollup, in_memory_parity, artifact_parity tools

- [x] Combined artifact tools into audit tools (simpler structure)

- [x] Keep `backtest_cli_wrapper.py` as re-export hub (for backward compat)

### 4.2 Update Imports

- [x] `backtest_cli_wrapper.py` re-exports from new modules
- [x] `src/tools/__init__.py` imports from `backtest_cli_wrapper.py` (unchanged)
- [x] Backward compatibility preserved (all import paths still work)

### 4.3 Verify No Breakage

- [x] Run `python -m compileall src/tools/` - PASSED
- [x] Import check passed for all tools

**Acceptance**: Tools split into focused modules, all imports work ✅

### Implementation Notes

- `backtest_cli_wrapper.py`: 1,808 → 83 lines (re-export hub)
- `backtest_ideacard_tools.py`: 890 lines (IdeaCard execution)
- `backtest_audit_tools.py`: 320 lines (audit & verification)

---

## Phase 5: Reorganize Backtest Menu Structure ✅

**Goal**: Clean top-level backtest menu

### 5.1 Final Menu Structure

```
Backtest Engine
├── 1. IdeaCard Backtests      → ideacard submenu ✅
├── 2. Audits & Verification   → audits submenu ✅
├── 3. Analytics & Results     → analytics submenu ✅
└── 9. Back to Main Menu
```

### 5.2 Implementation Notes

- [x] Legacy SystemConfig code removed (forward-only principle)
- [x] Data preparation integrated into IdeaCard submenu (Data Fix option)
- [x] Menu is clean and focused on IdeaCard workflow
- [x] No redundancy - each option leads to a focused submenu

**Acceptance**: Clean, organized menu structure ✅

---

## Phase 6: Tool Registry Integration ✅

**Goal**: Register backtest tools for agent access

### 6.1 Add to ToolRegistry

- [x] Register 6 IdeaCard tools in registry (category: backtest.ideacard)
- [x] Register 5 audit tools in registry (category: backtest.audit)
- [x] Add tool metadata (descriptions, parameters) for all tools

### 6.2 Verify Agent Access

- [x] Test `registry.list_tools(category="backtest")` → 17 tools
- [x] Test `registry.list_tools(category="backtest.ideacard")` → 6 tools
- [x] Test `registry.list_tools(category="backtest.audit")` → 5 tools

**Acceptance**: Agents can discover and call backtest tools ✅

### Tools Registered

**IdeaCard Tools (backtest.ideacard)**:
- `backtest_list_idea_cards` - List all IdeaCards
- `backtest_preflight` - Preflight check for backtest
- `backtest_run_idea_card` - Run backtest (Golden Path)
- `backtest_data_fix` - Fix data for backtest
- `backtest_indicators` - Discover indicator keys
- `backtest_normalize_idea_card` - Validate IdeaCard YAML

**Audit Tools (backtest.audit)**:
- `backtest_audit_toolkit` - Toolkit contract audit (42 indicators)
- `backtest_audit_rollup` - Rollup parity audit
- `backtest_audit_math_parity` - Math parity audit
- `backtest_audit_snapshot_plumbing` - Snapshot plumbing audit
- `backtest_verify_artifacts` - Artifact integrity check

---

## Files Created/Modified

| File | Action | Status |
|------|--------|--------|
| `src/cli/menus/backtest_ideacard_menu.py` | CREATE | ✅ Phase 1 |
| `src/cli/menus/backtest_audits_menu.py` | CREATE | ✅ Phase 2 |
| `src/cli/menus/backtest_analytics_menu.py` | CREATE | ✅ Phase 3 |
| `src/cli/menus/backtest_menu.py` | MODIFY - add submenus | ✅ Phase 1-3 |
| `src/tools/backtest_ideacard_tools.py` | CREATE (890 lines) | ✅ Phase 4 |
| `src/tools/backtest_audit_tools.py` | CREATE (320 lines) | ✅ Phase 4 |
| `src/tools/backtest_cli_wrapper.py` | MODIFY - re-export hub (83 lines) | ✅ Phase 4 |
| `src/tools/__init__.py` | MODIFY - export new tools | ✅ Phase 2 |
| `src/tools/tool_registry.py` | MODIFY - register 11 backtest tools | ✅ Phase 6 |

---

## Validation

After each phase:
```bash
python -m compileall src/cli/ src/tools/
python trade_cli.py  # Test menu navigation
python trade_cli.py --smoke full  # Ensure no regressions
```

---

## Dependencies

- Phase 1 can start immediately
- Phase 2 can start immediately (parallel with Phase 1)
- Phase 3 depends on Phase 4 returns.json (already complete)
- Phase 4 can start after Phase 1-2 (tools are stable)
- Phase 5 depends on Phase 1-3 (all submenus exist)
- Phase 6 depends on Phase 4 (tools are split)
