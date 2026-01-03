---
allowed-tools: Bash, Read, Edit, Write
description: Quick fix for syntax errors, type issues, or import problems
argument-hint: [file]
---

# Quick Fix Command

Rapidly fix syntax errors, import issues, or simple type problems.

## Usage

```
/trade-workflow:quick-fix [file]
```

## Process

1. **Identify the Issue**

```bash
# Check for syntax errors
python -m py_compile [file]

# Check for import issues
python -c "import [module]"

# Run type check if applicable
mypy [file] --ignore-missing-imports
```

2. **Fix the Issue**

- Syntax errors: Fix directly
- Import errors: Add missing imports
- Type errors: Add type hints or fix mismatches

3. **Verify Fix**

```bash
# Re-check syntax
python -m py_compile [file]

# Quick validation
python trade_cli.py backtest audit-toolkit
```

## Common Fixes

### Missing Import
```python
from .module import Class
```

### Syntax Error
- Check for missing colons, parentheses, brackets
- Verify indentation

### Type Mismatch
```python
# Fix: Add proper type annotation
def func(param: Type) -> ReturnType:
```

## Report Format

```
## Quick Fix Report

### Issue
[Error message]

### Fix Applied
[What was changed]

### Verification
- Syntax check: PASS
- Import check: PASS
```
