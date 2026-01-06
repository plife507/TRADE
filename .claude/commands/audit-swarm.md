---
allowed-tools: Bash, Read, Grep, Glob, Task
description: Launch parallel audit agents to review architecture and find bugs
argument-hint:
---

# Audit Swarm Command

Launch multiple parallel agents to audit the codebase for bugs and architectural issues.

## Usage

```
/trade-workflow:audit-swarm
```

## Process

1. **Spawn Parallel Agents**

Launch these agents simultaneously:
- `code-reviewer` focusing on engine core
- `code-reviewer` focusing on sim/exchange
- `security-auditor` for trading safety
- `validate` for full test suite

2. **Audit Areas**

| Agent Focus | Path | Checks |
|-------------|------|--------|
| Engine Core | src/backtest/engine*.py | Lookahead, timing, snapshots |
| Sim/Exchange | src/backtest/sim/ | Fills, fees, position sizing |
| Runtime | src/backtest/runtime/ | State tracking, snapshots |
| Integration | strategies/idea_cards/_validation/ | End-to-end paths |

3. **Consolidate Findings**

Categorize by severity:
- **P0 (Critical)**: Bugs causing incorrect results
- **P1 (High)**: Missing functionality, edge cases
- **P2 (Medium)**: Code quality, minor issues
- **P3 (Low)**: Polish, documentation

## Report Format

```
## Audit Swarm Report

### Summary
| Category | P0 | P1 | P2 | P3 |
|----------|----|----|----|----|
| Engine Core | X | X | X | X |
| Sim/Exchange | X | X | X | X |
| Runtime | X | X | X | X |
| Integration | X | X | X | X |

### P0 Critical Issues
[List with file:line references]

### P1 High Priority
[List]

### Recommended Fixes
[Prioritized action items]

### Validation Status
- audit-toolkit: X/X
- normalize-batch: X/X
- smoke: PASS/FAIL
```
