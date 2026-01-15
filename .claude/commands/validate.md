---
allowed-tools: Bash, Read, Grep, Glob
description: Run TRADE validation suite (Play normalize, audits, smoke tests)
argument-hint: [tier: 1|2|3|full]
---

# Validate Command

Run the TRADE validation suite at the specified tier.

## Usage

```
/validate [tier]
```

- `1` - TIER 1: Play normalization only (fastest)
- `2` - TIER 2: Unit audits (audit-toolkit, structure-smoke)
- `3` - TIER 3: Integration smoke tests
- `full` - All tiers (default)

## Execution

### TIER 1: Play Normalization

```bash
python trade_cli.py backtest play-normalize-batch --dir tests/functional/plays
```

### TIER 2: Unit Audits

```bash
python trade_cli.py backtest audit-toolkit       # 43/43 indicators
python trade_cli.py backtest structure-smoke     # Market structures
```

### TIER 3: Integration

```bash
python trade_cli.py --smoke backtest
```

Expected: Trades generated, artifacts created

## Report Format

```
## Validation Report

### TIER 1: Play Normalization
Result: PASS/FAIL (X/Y Plays)

### TIER 2: Unit Audits
- audit-toolkit: PASS/FAIL (43/43 indicators)
- structure-smoke: PASS/FAIL

### TIER 3: Integration
- backtest smoke: PASS/FAIL (X trades)

### Summary
[Overall status and any failures to address]
```
