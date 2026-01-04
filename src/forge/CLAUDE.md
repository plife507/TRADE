# The Forge

Development and validation environment for Plays.

## Purpose

The Forge is where strategies are:
1. **Created** - Generated from templates or composed from Setups
2. **Validated** - Checked for correctness before use
3. **Audited** - Verified for math parity and data flow
4. **Promoted** - Moved to production configs when ready

## Architecture Principle: Pure Math

All Forge components are pure functions:
- Input → Computation → Output
- No side effects
- No control flow about when to run
- Engine orchestrates invocation

```python
# CORRECT: Pure validation function
def validate_play(play: Play) -> ValidationResult:
    errors = check_schema(play)
    errors.extend(check_indicators(play))
    return ValidationResult(errors=errors, valid=len(errors) == 0)

# WRONG: Validation decides when to run
def maybe_validate(play: Play, force: bool = False):
    if force or self.should_validate:
        return self._do_validation(play)
```

## Submodule Structure

| Submodule | Purpose | Status |
|-----------|---------|--------|
| `audits/` | Parity and correctness audits | Migrating |
| `validation/` | Play schema and indicator validation | Planned |
| `generation/` | Play generation from templates | Planned |
| `setups/` | Reusable Setup blocks | ✅ Complete |
| `playbooks/` | Playbook collections | ✅ Complete |
| `systems/` | Trading system configs | ✅ Complete |

## Key Entry Points

```python
from src.forge import (
    # Setups (reusable market conditions)
    Setup, load_setup, list_setups, save_setup,

    # Playbooks (collections of Plays)
    Playbook, PlaybookEntry, load_playbook, list_playbooks,

    # Systems (complete trading configurations)
    System, PlaybookRef, load_system, list_systems,
)
```

## Trading Hierarchy (W4 Complete)

| Level | Description | Config Location | DSL Syntax |
|-------|-------------|-----------------|------------|
| **Setup** | Reusable market condition | `configs/setups/` | `setup: <id>` |
| **Play** | Complete tradeable strategy | `configs/plays/` | - |
| **Playbook** | Collection of Plays | `configs/playbooks/` | - |
| **System** | Full trading system | `configs/systems/` | - |

### Hierarchy Resolution

```python
# Full resolution: System → Playbook → Plays
from src.forge import load_system, load_playbook

system = load_system("btc_trend_v1")
for pb_ref in system.get_enabled_playbooks():
    playbook = load_playbook(pb_ref.playbook_id)
    for entry in playbook.get_enabled_plays():
        print(f"Play: {entry.play_id} ({entry.role})")
```

### Setup in DSL Blocks

```yaml
# In Play blocks, reference setups by ID:
blocks:
  - id: entry
    cases:
      - when:
          all:
            - setup: rsi_oversold    # References configs/setups/rsi_oversold.yml
            - setup: ema_pullback    # References configs/setups/ema_pullback.yml
        emit:
          - action: entry_long
```

## Critical Rules

**ALL FORWARD**: No legacy support. Delete old code, update all callers.

**Pure Functions**: Forge components define MATH only. No control flow about invocation.

**Fail Loud**: Invalid configs raise errors immediately. No silent defaults.

## Validation Flow

```
Play YAML → load_play() → validate_play() → ValidationResult
                                ↓
                        [errors] → FIX → retry
                        [valid] → promote to configs/plays/
```

## Audit Tools

| Audit | Purpose | Pure Function |
|-------|---------|---------------|
| `audit_toolkit` | Indicator registry consistency | (config) → ToolkitResult |
| `audit_math_parity` | Indicator math vs pandas_ta | (snapshots) → ParityResult |
| `audit_plumbing` | Snapshot data flow | (play, dates) → PlumbingResult |
| `audit_rollup` | 1m price aggregation | (config) → RollupResult |

## W4 Trading Hierarchy Status

**Completed** (2026-01-04):
- W4-P1: Setup dataclass and loader
- W4-P2: Setup DSL integration (`setup:` syntax in blocks)
- W4-P3: Playbook dataclass and loader
- W4-P4: System dataclass and loader

**Validation Plays**:
- `V_300_setup_basic.yml` - Basic setup reference
- `V_301_setup_composition.yml` - Multiple setups with all/any
- `V_400_playbook_basic.yml` - Basic playbook loading

## Active TODOs

| Document | Focus |
|----------|-------|
| `docs/todos/TODO.md` | Active work tracking |
