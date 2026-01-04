# Forge Cleanup Agent Instructions

**Purpose**: Run after Phase 7 to verify complete migration and catch any missed references.

---

## When to Run

Run this cleanup agent:
1. After ALL phases P1-P7 are marked complete
2. Before marking P8 as complete
3. Any time you suspect missed references

---

## Cleanup Checklist

### 1. Code Grep Checks (Must All Return 0 Matches)

```bash
# Class names - should find ZERO
grep -r "class IdeaCard" src/
grep -r "IdeaCard\[" src/       # Type hints
grep -r ": IdeaCard" src/       # Type annotations

# Function names - should find ZERO
grep -r "def.*idea_card" src/
grep -r "load_idea_card" src/
grep -r "save_idea_card" src/
grep -r "validate_idea_card" src/
grep -r "create_engine_from_idea_card" src/

# Variable names - should find ZERO (except comments)
grep -r "idea_card\s*=" src/
grep -r "idea_card:" src/       # Function params
grep -r "idea_card_path" src/
grep -r "idea_card_config" src/

# Constants - should find ZERO
grep -r "IDEACARD" src/
grep -r "IDEA_CARD" src/
grep -r "IDEA_CARDS" src/

# Import statements - should find ZERO
grep -r "from.*idea_card import" src/
grep -r "import.*idea_card" src/

# Path strings - should find ZERO
grep -r "idea_cards/" src/
grep -r "configs/idea_cards" src/
```

### 2. File/Directory Name Checks

```bash
# Files with idea_card in name - should find ZERO
find src/ -name "*idea_card*"

# Directories with idea_card in name - should find ZERO
find . -type d -name "*idea_card*"

# Old config directory should NOT exist
ls configs/idea_cards/  # Should fail with "No such file"
```

### 3. Import Health Checks

```python
# All of these must succeed
python -c "import src.backtest"
python -c "from src.backtest import Play"
python -c "from src.backtest import play"
python -c "from src.backtest.play import Play"
python -c "from src.backtest.play_yaml_builder import PlayYamlBuilder"
python -c "from src.backtest.gates.play_generator import PlayGenerator"
python -c "from src.tools import backtest_play_tools"
python -c "from src.cli.menus import backtest_play_menu"
```

### 4. Config Path Checks

```python
# Verify new paths work
python -c "
from pathlib import Path
plays_dir = Path('configs/plays')
assert plays_dir.exists(), 'configs/plays/ must exist'
validation_dir = plays_dir / '_validation'
assert validation_dir.exists(), '_validation subdirectory must exist'
stress_dir = plays_dir / '_stress_test'
assert stress_dir.exists(), '_stress_test subdirectory must exist'
print('Config paths OK')
"
```

### 5. Documentation Checks

```bash
# Check CLAUDE.md files for old terms
grep -l "IdeaCard" CLAUDE.md src/*/CLAUDE.md
grep -l "idea_card" CLAUDE.md src/*/CLAUDE.md
grep -l "configs/idea_cards" CLAUDE.md src/*/CLAUDE.md

# Should only find references in migration docs or historical context
```

### 6. YAML File Checks

```bash
# Check for internal references to old paths in YAML files
grep -r "idea_card" configs/plays/
```

---

## Remediation Actions

### If Code References Found

1. Identify the file and line
2. Determine correct replacement:
   - `IdeaCard` → `Play`
   - `idea_card` → `play`
   - `IDEACARD` → `PLAY`
3. Update using Edit tool
4. Re-run check to verify fix

### If File Name Issues Found

1. Use `git mv old_name new_name`
2. Update all imports referencing old file
3. Update `__init__.py` exports

### If Import Errors

1. Check if module was renamed
2. Update import to new module path
3. Ensure `__init__.py` exports the symbol

### If Path Errors

1. Verify directory exists at new location
2. Update path constant/string to new location
3. Check for hardcoded paths

---

## Report Template

After running all checks, generate a report:

```markdown
# Forge Migration Cleanup Report

**Date**: YYYY-MM-DD
**Agent**: cleanup-agent

## Summary
- Code grep checks: PASS/FAIL
- File name checks: PASS/FAIL
- Import health: PASS/FAIL
- Config paths: PASS/FAIL
- Documentation: PASS/FAIL
- YAML files: PASS/FAIL

## Issues Found
1. [Issue description and file location]
2. [Issue description and file location]

## Issues Fixed
1. [Fix description]
2. [Fix description]

## Remaining Issues
- None / [List any unfixed issues]

## Recommendation
- [ ] Ready to mark P8 complete
- [ ] Needs additional fixes before completion
```

---

## Success Criteria

The cleanup agent declares SUCCESS when:

1. ALL grep checks return 0 matches (except allowed exceptions)
2. NO files/directories with old names exist
3. ALL import health checks pass
4. ALL config paths resolve
5. Documentation uses new terminology
6. Smoke tests pass

**Allowed Exceptions**:
- Comments explaining migration history (e.g., "# Renamed from IdeaCard")
- Git commit messages
- Archived documentation in `docs/_archived/`
- This cleanup document itself
