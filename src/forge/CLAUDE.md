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

| Submodule | Purpose |
|-----------|---------|
| `audits/` | Parity and correctness audits |
| `validation/` | Play schema and indicator validation |
| `generation/` | Play generation from templates |
| `setups/` | Reusable Setup blocks (W4) |
| `playbooks/` | Playbook collections (W4) |

## Key Entry Points

```python
from src.forge import (
    validate_play,        # Validate single Play
    validate_batch,       # Validate directory of Plays
    run_audit_toolkit,    # Run indicator registry audit
)
```

## Trading Hierarchy

| Level | Description | Config Location |
|-------|-------------|-----------------|
| **Setup** | Reusable market condition | `configs/setups/` |
| **Play** | Complete tradeable strategy | `configs/plays/` |
| **Playbook** | Collection of Plays | `configs/playbooks/` |
| **System** | Full trading system | `configs/systems/` |

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

## Migration Status

**Audits Migration** (in progress):
- Source: `src/backtest/audits/` (current location)
- Target: `src/forge/audits/` (target location)
- Status: Directory created, files pending migration

## Active TODOs

| Document | Focus |
|----------|-------|
| `docs/todos/TODO.md` | W1-F1: Complete audit migration |
