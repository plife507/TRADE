---
allowed-tools: Bash, Read, Grep, Glob, Task
description: Multi-agent verification of changes before commit
argument-hint:
---

# Verify Changes Command

Spawn multiple agents to verify changes are safe to commit.

## Usage

```
/trade-workflow:verify-changes
```

## Process

1. **Gather Changes**

```bash
git diff --staged
git diff HEAD
```

2. **Spawn Verification Agents**

Launch in parallel:
- `validate` - Run TIER 1-2 validation
- `code-reviewer` - Review code quality
- `security-auditor` - Check for security issues (if trading code changed)

3. **Aggregate Results**

```
## Verification Report

### Validation Agent
- IdeaCard normalize: PASS (9/9)
- audit-toolkit: PASS (42/42)
- structure-smoke: PASS

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
- When backtest engine is modified
