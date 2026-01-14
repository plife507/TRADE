# Forge Migration Rules

## PRIME DIRECTIVE: ALL FORWARD, NO LEGACY

**This migration follows STRICT forward-only principles. NO backward compatibility. NO legacy fallbacks. NO shims. EVER.**

---

## Migration Scope

### Terminology Changes
| Old Term | New Term | Scope |
|----------|----------|-------|
| `IdeaCard` | `Play` | Class names, variables, docstrings |
| `idea_card` | `play` | File names, function names, parameters |
| `IDEACARD` | `PLAY` | Constants, env vars |
| `idea_cards` | `plays` | Directory names, config paths |
| `sandbox` | `forge` | All references |

### Directory Renames
| Old Path | New Path |
|----------|----------|
| `strategies/idea_cards/` | `strategies/plays/` |
| `src/strategies/idea_cards/` | `src/strategies/plays/` |
| `src/cli/menus/backtest_ideacard_menu.py` | `src/cli/menus/backtest_play_menu.py` |

### File Renames
| Old File | New File |
|----------|----------|
| `src/backtest/idea_card.py` | `src/backtest/play.py` |
| `src/backtest/idea_card_yaml_builder.py` | `src/backtest/play_yaml_builder.py` |
| `src/backtest/gates/idea_card_generator.py` | `src/backtest/gates/play_generator.py` |
| `src/tools/backtest_ideacard_tools.py` | `src/tools/backtest_play_tools.py` |
| `src/backtest/audits/audit_ideacard_value_flow.py` | `src/backtest/audits/audit_play_value_flow.py` |

---

## Forward-Only Rules

### Rule 1: DELETE, Don't Deprecate
```python
# WRONG - Creating backward compat alias
IdeaCard = Play  # Legacy alias - DO NOT DO THIS

# CORRECT - Just use the new name everywhere
class Play:
    ...
```

### Rule 2: UPDATE All Callers Immediately
When renaming a function/class:
1. Rename the definition
2. Update ALL callers in the same commit
3. Do NOT leave any references to old name

### Rule 3: NO Shim Files
```python
# WRONG - Creating idea_card.py that imports from play.py
# src/backtest/idea_card.py
from .play import Play as IdeaCard  # DO NOT DO THIS

# CORRECT - Delete idea_card.py entirely, update all imports
```

### Rule 4: NO "Renamed From" Comments
```python
# WRONG
class Play:  # Renamed from IdeaCard
    ...

# CORRECT
class Play:
    ...
```

### Rule 5: Break Fast, Fix Forward
- If something breaks after rename, FIX the caller
- Do NOT revert or add compatibility layer
- Broken imports are EXPECTED and GOOD - they show what needs updating

### Rule 6: One Phase at a Time
- Complete each phase fully before moving to next
- Each phase must leave codebase in working state
- Run validation after each phase

---

## Validation Requirements

### After Each Phase
1. `python -c "import src.backtest"` - Import check
2. `python trade_cli.py --smoke data` - Basic smoke test
3. Grep for OLD terms - must find ZERO matches in code

### Cleanup Agent Checklist
After all phases complete, the cleanup agent verifies:
- [ ] Zero `IdeaCard` references in Python files (except comments explaining migration)
- [ ] Zero `idea_card` in file/directory names
- [ ] Zero `IDEACARD` constants
- [ ] Zero imports from old module paths
- [ ] All YAML files reference new paths
- [ ] CLAUDE.md files updated
- [ ] README files updated

---

## Error Handling

### Import Errors
```
ImportError: cannot import name 'IdeaCard' from 'src.backtest'
```
**Fix**: Update the import to use `Play` from new location

### File Not Found
```
FileNotFoundError: strategies/idea_cards/...
```
**Fix**: Update path to `strategies/plays/...`

### Attribute Errors
```
AttributeError: module has no attribute 'load_idea_card'
```
**Fix**: Update to `load_play`

---

## Commit Strategy

Each phase gets ONE commit with format:
```
refactor(forge-P#): <description>

- List of changes
- Files renamed
- Imports updated

BREAKING: <what breaks and how to fix>
```

Example:
```
refactor(forge-P1): rename strategies/idea_cards/ to strategies/plays/

- Moved 21 YAML files to new location
- Updated all path references in src/
- Updated CLI menu paths

BREAKING: strategies/idea_cards/ no longer exists
```
