---
allowed-tools: Bash, Read, Grep, Glob
description: Run TRADE validation suite (Play normalize, audits, smoke tests)
argument-hint: [tier: quick|standard|full|real|module]
---

# Validate Command

Run the unified TRADE validation suite at the specified tier.

## Usage

```
/validate [tier]
```

- `quick` - Core plays + audits (~7s, default)
- `standard` - + structure/rollup/sim/suite/metrics (~20s)
- `full` - + full indicator/pattern suites, determinism (~50s)
- `real` - Real-data verification, sync-once + parallel (~2min)
- `module --module X` - Run a single module independently
- `pre-live` - Connectivity + readiness gate for specific play
- `exchange` - Exchange integration (~30s)

## Execution Strategy

### Quick (direct CLI call)
```bash
python trade_cli.py validate quick
```

### Standard (staged orchestration)
Step 1: Run critical path serially
```bash
python trade_cli.py validate module --module audits --json
python trade_cli.py validate module --module core --json
python trade_cli.py validate module --module risk --json
```

Step 2: If Step 1 passes, run remaining modules as parallel background Bash tasks
```bash
# Launch all in parallel background:
python trade_cli.py validate module --module operators --json
python trade_cli.py validate module --module structures --json
python trade_cli.py validate module --module complexity --json
python trade_cli.py validate module --module parity --json
python trade_cli.py validate module --module sim --json
python trade_cli.py validate module --module metrics --json
```

### Full (staged orchestration)
Same as standard, plus additional parallel background tasks:
```bash
python trade_cli.py validate module --module indicators --json
python trade_cli.py validate module --module patterns --json
python trade_cli.py validate module --module determinism --json
```

### Real-data (direct CLI call, handles sync + parallel internally)
```bash
python trade_cli.py validate real
```

### Single module (direct CLI call)
```bash
python trade_cli.py validate module --module indicators --json
python trade_cli.py validate module --module core
```

## Available Modules

| Module | Gates | What it tests |
|--------|-------|---------------|
| `core` | G4 | 5 core plays |
| `risk` | G4b | 9 risk plays |
| `audits` | G2 + G3 | registry + parity audits |
| `operators` | G8 | 25 operator plays |
| `structures` | G9 | 14 structure plays |
| `complexity` | G10 | 13 complexity plays |
| `indicators` | G12 | 84 indicator plays |
| `patterns` | G13 | 34 pattern plays |
| `parity` | G5 + G6 | structure + rollup parity |
| `sim` | G7 | sim order smoke |
| `metrics` | G11 | financial math audit |
| `determinism` | G14 | 5 plays x2 runs |
| `real-accumulation` | RD1 | 15 accumulation plays |
| `real-markup` | RD2 | 16 markup plays |
| `real-distribution` | RD3 | 15 distribution plays |
| `real-markdown` | RD4 | 15 markdown plays |

## CLI Options

```bash
# JSON output for CI/parsing
python trade_cli.py validate quick --json

# Skip fail-fast (run all gates even on failure)
python trade_cli.py validate standard --no-fail-fast

# Control parallelism
python trade_cli.py validate full --workers 4
```

## Debug Commands

For targeted investigation when a gate fails:

```bash
python trade_cli.py debug math-parity --play <play_name> --start <date> --end <date>
python trade_cli.py debug snapshot-plumbing --play <play_name> --start <date> --end <date>
python trade_cli.py debug determinism --run-a <path_a> --run-b <path_b>
python trade_cli.py debug metrics
```

## Report Format

```
## Validation Report

### Quick Tier
- G1 YAML Parse: PASS (5/5)
- G2 Registry Contract: PASS (44/44)
- G3 Incremental Parity: PASS
- G4 Core Plays: PASS (5/5, 2134 trades)

### Summary
All gates passed.
```
