---
allowed-tools: Bash, Read, Grep, Glob, Task
description: Multi-agent verification of changes before commit
argument-hint:
---

# Verify Changes Command

Spawn multiple agents to verify changes are safe to commit.

## Usage

```
/verify-changes
```

## Process

1. **Gather Changes**

```bash
git diff --staged
git diff HEAD
```

2. **Spawn Verification Agents**

Launch in parallel:
- `validate` - Run `python trade_cli.py validate quick`
- `code-reviewer` - Review code quality and TRADE rules
- `security-auditor` - Check for security issues (if trading code changed)

3. **Aggregate Results**

```
## Verification Report

### Validation Agent
- G1 YAML Parse: PASS (5/5)
- G2 Toolkit Audit: PASS (43/43)
- G3 Incremental Parity: PASS
- G4 Core Plays: PASS (5/5)

### Code Review Agent
- Rule compliance: OK
- Code quality: OK
- Suggestions: [list]

### Security Agent
- API key exposure: OK
- Mode validation: OK
- Trading safety: OK

### Verdict
READY TO COMMIT / NEEDS FIXES
```

## Automatic Triggers

This command should be run:
- Before any commit to main
- After significant code changes
- When engine code is modified
