# CLAUDE.md

## Project Overview

This is a Python project. Primary language is Python with YAML for configuration and Markdown for documentation. Use pyright for type checking. Always validate changes with existing test suites before committing.

## General Principles

- Always use the project's existing CLI tools and infrastructure before building custom scripts or solutions. Ask the user which CLI commands are available if unsure.
- When spawning agent teams for audits or large tasks, begin executing promptly rather than spending excessive time on codebase exploration and orchestration planning. The user prefers action over preparation.

## Prime Directives

- **ALL FORWARD, NO LEGACY** - Delete old code, don't wrap it
- **MODERN PYTHON 3.12+** - Type hints, f-strings, pathlib, `X | None` not `Optional[X]`
- **LF LINE ENDINGS** - Use `newline='\n'` on Windows
- **TODO-DRIVEN** - Every change maps to `docs/TODO.md`
- **CLI VALIDATION** - Use CLI commands, not pytest

## Project Structure

When working with this codebase, target `src/` not `scripts/` unless explicitly told otherwise. The main source tree is under `src/`.

## Architecture

```text
src/engine/        # ONE unified engine (PlayEngine) for backtest/live
src/indicators/    # 44 indicators (all incremental O(1))
src/structures/    # 7 structure types (swing, trend, zone, fib, derived_zone, rolling_window, market_structure)
src/backtest/      # Infrastructure only (sim, runtime, features) - NOT an engine
src/data/          # DuckDB historical data (1m candles mandatory for all runs)
src/tools/         # CLI/API surface
```

**1m data is mandatory**: Every backtest/live run pulls 1m candles regardless of exec timeframe. Drives fill simulation, TP/SL evaluation, and signal subloop.

## Database & Concurrency

When running parallel agents or sub-tasks, NEVER use parallel file access to DuckDB databases. Always run DuckDB operations sequentially to avoid file lock conflicts.

## Key Patterns

| Pattern | Rule |
|---------|------|
| Engine | Always use `create_engine_from_play()` + `run_engine_with_play()` |
| Indicators | Declare in Play YAML, access via snapshot |
| Database | Sequential access only (DuckDB limitation) |
| Hashing | Always use `compute_trades_hash()` from `hashes.py` -- never ad-hoc `repr()`/`hash()` |

## Hash Tracing

Deterministic hashes flow through the entire pipeline for reproducibility and debugging.

| Hash | Source | Length | Purpose |
|------|--------|--------|---------|
| `play_hash` | `compute_play_hash(play)` SHA256 | 16 hex | Play config identity |
| `input_hash` | `compute_input_hash(components)` SHA256 | 12 hex | Artifact folder name |
| `trades_hash` | `compute_trades_hash(trades)` SHA256 | 16 hex | Output determinism |
| `equity_hash` | `compute_equity_hash(curve)` SHA256 | 16 hex | Output determinism |
| `run_hash` | `compute_run_hash(trades, equity, play)` | 16 hex | Combined fingerprint |
| `data_hash` | SHA256 of synthetic data | 12 hex | Synthetic data integrity |

**Canonical functions**: All in `src/backtest/artifacts/hashes.py`. `DEFAULT_SHORT_HASH_LENGTH = 12`.

**Pipeline flow**: runner computes `play_hash` → sets on engine via `set_play_hash()` → engine uses in debug logging → after run, computes `trades_hash`/`equity_hash`/`run_hash` → stored in `result.json` → displayed in console → logged to `index.jsonl`.

**Field naming**: The field is `play_hash` everywhere (not `idea_hash`). `ResultsSummary.play_hash`, `result.json["play_hash"]`, `determinism.py` hash_fields.

## Trading Domain Rules

For trading logic: Take Profit (TP) and Stop Loss (SL) orders fire BEFORE signal-based closes. Do not assume signal closes have priority over TP/SL.

## Type Checking

When fixing type errors or pyright issues, run the full pyright check after each batch of fixes to catch cascading errors early. Fixing one category of errors often exposes hidden ones.

**Config ownership**: `pyrightconfig.json` is the single source of truth for all type checking settings. When it exists, Pylance **ignores** all `python.analysis.*` settings in `.vscode/settings.json`. Never duplicate type checking config in both files. VS Code settings should only contain interpreter path and language server choice.

## Code Cleanup Rules

Before claiming code is 'dead' or unused, verify by grepping for all references including dynamic imports, CLI entry points, and test fixtures. Do not remove code without confirmed zero references.

## Timeframe Naming (ENFORCED)

**3-Feed + Exec Role System:**

| Term | Type | Example Values | Purpose |
|------|------|----------------|---------|
| `low_tf` | Timeframe | 1m, 3m, 5m, 15m | Fast: execution, entries |
| `med_tf` | Timeframe | 30m, 1h, 2h, 4h | Medium: structure, bias |
| `high_tf` | Timeframe | 12h, D | Slow: trend, context |
| `exec` | Pointer | "low_tf", "med_tf", "high_tf" | Which TF to step on |

**YAML keys (ENFORCED):**
- ~~htf~~, ~~HTF~~ → use `high_tf`
- ~~ltf~~, ~~LTF~~ → use `low_tf`
- In YAML: `exec` is a pointer (`"low_tf"`, `"med_tf"`, `"high_tf"`), never a raw value like `"15m"`

**Python identifiers (ENFORCED):**
- `exec_tf` = resolved concrete timeframe string (e.g., `"15m"`) -- standard name
- ~~execution_tf~~ → use `exec_tf` everywhere in Python code
- ~~ltf~~, ~~htf~~, ~~LTF~~, ~~HTF~~, ~~MTF~~ → banned

**Prose/comments:**
- "higher timeframe" not HTF
- "medium timeframe" not MTF
- "lower timeframe" not LTF
- "exec TF" is acceptable shorthand in comments and log messages
- "multi-timeframe" for strategies using multiple timeframes
- "last price" and "mark price" written out fully

```yaml
# Correct Play structure:
timeframes:
  low_tf: "15m"    # Concrete timeframe
  med_tf: "1h"     # Concrete timeframe
  high_tf: "D"     # Concrete timeframe (12h or D)
  exec: "low_tf"   # POINTER to which TF to step on
```

## Quick Commands

```bash
# Validation (single entry point)
python trade_cli.py validate quick                    # Pre-commit (~10s)
python trade_cli.py validate standard                 # Pre-merge (~2min)
python trade_cli.py validate full                     # Pre-release (~10min)
python trade_cli.py validate pre-live --play X        # Deployment gate
python trade_cli.py validate exchange                  # Exchange integration (~30s)

# Backtest
python trade_cli.py backtest run --play X --sync  # Run single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/run_full_suite.py --real --start 2025-01-01 --end 2025-06-30  # Real data suite
python scripts/run_real_verification.py               # 60-play real verification
python scripts/verify_trade_math.py --play X          # Math verification for a play

# Debug (diagnostic tools)
python trade_cli.py debug math-parity --play X        # Real-data math audit
python trade_cli.py debug snapshot-plumbing --play X   # Snapshot field check
python trade_cli.py debug determinism --run-a A --run-b B  # Compare runs
python trade_cli.py debug metrics                      # Financial calc audit

# Live/Demo
python trade_cli.py play run --play X --mode demo   # Demo mode (no real money)
python trade_cli.py play run --play X --mode live --confirm  # Live (REAL MONEY)
```

## Where to Find Details

| Topic | Location |
|-------|----------|
| Project status & session context | `docs/TODO.md` |
| DSL syntax | `docs/PLAY_DSL_REFERENCE.md` |
| Synthetic data patterns | `docs/SYNTHETIC_DATA_REFERENCE.md` |
| CLI redesign open gates | `docs/CLI_REDESIGN.md` |
| System defaults | `config/defaults.yml` |

## Reference Documentation

| Topic | Location |
|-------|----------|
| Bybit API docs | `reference/exchanges/bybit/` |
| pybit SDK docs | `reference/exchanges/pybit/` |
