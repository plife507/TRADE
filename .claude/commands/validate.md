---
allowed-tools: Bash, Read, Grep, Glob
description: Run TRADE validation suite (IdeaCard normalize, audits, smoke tests)
argument-hint: [tier: 1|2|3|full]
---

# Validate Command

Run the TRADE validation suite at the specified tier.

## Usage

```
/trade-workflow:validate [tier]
```

- `1` - TIER 1: IdeaCard normalization only (fastest)
- `2` - TIER 2: Unit audits (audit-toolkit, structure-smoke)
- `3` - TIER 3: Integration smoke tests
- `full` - All tiers (default)

## Execution

### TIER 1: IdeaCard Normalization

```bash
python trade_cli.py backtest idea-card-normalize-batch --dir strategies/idea_cards/_validation
```

Expected: 9/9 cards pass

### TIER 2: Unit Audits

```bash
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest structure-smoke
```

Expected: 42/42 indicators, structure smoke pass

### TIER 3: Integration

```bash
python trade_cli.py --smoke backtest
```

Expected: 3 trades, artifacts generated

## Report Format

```
## Validation Report

### TIER 1: IdeaCard Normalization
Result: PASS/FAIL (X/Y cards)

### TIER 2: Unit Audits
- audit-toolkit: PASS/FAIL (X/Y indicators)
- structure-smoke: PASS/FAIL

### TIER 3: Integration
- backtest smoke: PASS/FAIL (X trades)

### Summary
[Overall status and any failures to address]
```
