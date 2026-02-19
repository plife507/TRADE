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
- **PLAN → TODO.md** - Every plan mode output MUST be written into `docs/TODO.md` (see Plan Mode Rules below)

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

## Logging & Debugging

### Logger Hierarchy

All loggers live under `trade.*`. Never create orphan loggers.

| Do | Don't |
|----|-------|
| `from src.utils.logger import get_module_logger` | `import logging` |
| `logger = get_module_logger(__name__)` | `logger = logging.getLogger(__name__)` |

`get_module_logger("src.backtest.runner")` → `logging.getLogger("trade.backtest.runner")`.

### Key Functions (all in `src/utils/`)

| Function | Module | Purpose |
|----------|--------|---------|
| `get_module_logger(name)` | `logger.py` | Create child logger under `trade.*` |
| `suppress_for_validation()` | `logger.py` | Set `trade.*` to WARNING (for validation workers) |
| `get_logger()` / `setup_logger()` | `logger.py` | Get/create the `TradingLogger` singleton |
| `verbose_log(play_hash, msg, **fields)` | `debug.py` | Log at INFO gated on verbose mode |
| `debug_log(play_hash, msg, **fields)` | `debug.py` | Log at DEBUG gated on debug mode |
| `is_verbose_enabled()` | `debug.py` | Check if `-v` or `--debug` is active |
| `is_debug_enabled()` | `debug.py` | Check if `--debug` is active |

### Verbosity Levels

| Flag | Level | When to use |
|------|-------|-------------|
| `-q` / `--quiet` | WARNING only | CI, scripted runs, validation workers |
| (default) | INFO | Normal interactive use |
| `-v` / `--verbose` | INFO + signal/structure traces | Debugging why signals don't fire |
| `--debug` | DEBUG + all traces | Full hash-traced debugging |

### Rules

- **NEVER** use `logging.disable()` — use `suppress_for_validation()` instead
- **NEVER** use bare `logging.getLogger(__name__)` — use `get_module_logger(__name__)`
- **NEVER** add per-bar logging without gating on `is_verbose_enabled()` or `is_debug_enabled()` — per-bar logs on 25k+ bars destroy performance
- **Env var**: `TRADE_LOG_LEVEL` controls global level (fallback: `LOG_LEVEL`, then `"INFO"`)
- **Validation workers** (ProcessPoolExecutor): call `suppress_for_validation()` at the top of each worker function
- **Verbose-only code**: use `verbose_log()` for signal traces, structure events, NaN warnings. Zero overhead when verbose is off (early return)

### Backtest Event Journal

Every backtest writes `events.jsonl` to its artifact folder via `BacktestJournal` (in `src/engine/journal.py`). Records fill and close events per trade. Live/demo uses `TradeJournal` which writes to `data/journal/`.

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

## Live Safety Principles

- **Fail-closed**: Safety guards (price deviation, WS health, position sync) must block trading when data is unavailable, not allow it.
- **Reduce-only for closes**: All close/partial-close market orders must pass `reduce_only=True` to the exchange. Never set flags on result objects after the order is placed.
- **Position sync gate**: LiveRunner blocks signal execution until `_position_sync_ok` is True. Periodic reconciliation can unblock.

## Type Checking

When fixing type errors or pyright issues, run the full pyright check after each batch of fixes to catch cascading errors early. Fixing one category of errors often exposes hidden ones.

**Config ownership**: `pyrightconfig.json` is the single source of truth for all type checking settings. When it exists, Pylance **ignores** all `python.analysis.*` settings in `.vscode/settings.json`. Never duplicate type checking config in both files. VS Code settings should only contain interpreter path and language server choice.

**Pyright vs Cursor/Pylance phantom errors**: Cursor (and VS Code with Pylance) may show phantom "import not found" errors that pyright CLI does not produce. This is because `pyrightconfig.json` sets `"reportMissingImports": "none"` and `"extraPaths": [".", "src"]`, which pyright CLI respects but Pylance may ignore or override. Always trust `pyright` CLI output over in-editor squiggles. The Claude Code hook (`.claude/hooks/scripts/pyright_check.py`) runs pyright from the project root to ensure correct config resolution.

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
# Verbosity flags (apply to any command)
python trade_cli.py -q ...                            # Quiet (WARNING only)
python trade_cli.py -v ...                            # Verbose (signal traces, structure events)
python trade_cli.py --debug ...                       # Debug (full hash tracing)

# Validation (parallel staged execution, with timeouts + incremental reporting)
python trade_cli.py validate quick                    # Pre-commit (~2min)
python trade_cli.py validate standard                 # Pre-merge (~4min)
python trade_cli.py validate full                     # Pre-release (~6min)
python trade_cli.py validate real                     # Real-data verification (~2min)
python trade_cli.py validate module --module X --json # Single module (PREFERRED for agents)
python trade_cli.py validate module --module coverage # Check for missing indicator/structure plays
python trade_cli.py validate pre-live --play X        # Deployment gate
python trade_cli.py validate exchange                  # Exchange integration (~30s)
python trade_cli.py validate full --timeout 60        # Per-play timeout (default 120s)
python trade_cli.py validate full --gate-timeout 300  # Per-gate timeout (default 600s)

# Backtest
python trade_cli.py backtest run --play X --sync  # Run single backtest
python trade_cli.py -v backtest run --play X --synthetic  # Verbose: see signal traces
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/run_full_suite.py --real --start 2025-01-01 --end 2025-06-30  # Real data suite
python scripts/run_real_verification.py               # 60-play real verification
python scripts/verify_trade_math.py --play X          # Math verification for a play

# Debug (diagnostic tools — all --json use {"status","message","data"} envelope)
python trade_cli.py debug math-parity --play X        # Real-data math audit
python trade_cli.py debug snapshot-plumbing --play X   # Snapshot field check
python trade_cli.py debug determinism --run-a A --run-b B  # Compare runs
python trade_cli.py debug metrics                      # Financial calc audit

# Live/Demo
python trade_cli.py play run --play X --mode demo   # Demo mode (no real money)
python trade_cli.py play run --play X --mode live --confirm  # Live (REAL MONEY)
```

## Validation Coverage

The `coverage` module (gate G15) automatically detects which indicators and structures lack validation plays. It compares the indicator registry (44 indicators) and structure registry (7 types) against the plays in `plays/validation/indicators/` and `plays/validation/structures/`.

```bash
# Check for gaps (human-readable)
python trade_cli.py validate module --module coverage

# Check for gaps (JSON, for agents)
python trade_cli.py validate module --module coverage --json
```

**When to run**: After adding a new indicator or structure detector. The gate fails if any registered indicator/structure has no corresponding validation play.

**Fixing gaps**: Use the `validate_updater` agent, which has templates and workflows for creating missing plays. Or create plays manually following existing examples in `plays/validation/indicators/` and `plays/validation/structures/`.

## Plan Mode Rules (ENFORCED)

When exiting plan mode, the plan MUST be written into `docs/TODO.md` as a new gated section. This is the **only** persistent record — conversation context gets compacted and lost.

**Format requirements:**

1. **New section** in TODO.md with a clear title and priority (e.g., `## P0: Liquidation Parity`)
2. **Gated phases** — each phase is a group of checkboxes that must ALL pass before the next phase starts
3. **Validation gate** between phases — a checkbox like `- [ ] **GATE**: validate quick passes` or `- [ ] **GATE**: backtest run --play X succeeds`
4. **Reference doc** — if the plan produced a detailed review/analysis, link it (e.g., `See docs/LIQUIDATION_PARITY_REVIEW.md`)

**Example structure:**

```markdown
## P0: Liquidation Parity

See `docs/LIQUIDATION_PARITY_REVIEW.md` for full analysis.

### Phase 1: Fix IM/MM formulas
- [ ] Add fee-to-close term to MM calculation in `ledger.py`
- [ ] Add mmDeduction to MM calculation
- [ ] Wire tiered MMR from risk-limit config
- [ ] **GATE**: `python trade_cli.py validate quick` passes

### Phase 2: Bankruptcy price settlement
- [ ] Implement bankruptcy price calculation in `liquidation_model.py`
- [ ] Change exchange sim to settle at bankruptcy price (not mark)
- [ ] **GATE**: `python scripts/run_full_suite.py` — 170/170 pass

### Phase 3: Unify liquidation price formulas
- [ ] Remove `calculate_liquidation_price_simple()`, use single canonical formula
- [ ] **GATE**: `python trade_cli.py validate standard` passes
```

**Rules:**
- Do NOT write plans only to temp plan files or conversation — they vanish on compaction
- Do NOT create separate plan markdown files — `docs/TODO.md` is the single source of truth
- Supporting analysis docs (like reviews, audits) go in `docs/` and are linked from TODO.md
- Mark items `[x]` as they are completed during implementation

## Where to Find Details

| Topic | Location |
|-------|----------|
| Project status & session context | `docs/TODO.md` |
| Validation best practices | `docs/VALIDATION_BEST_PRACTICES.md` |
| DSL syntax | `docs/PLAY_DSL_REFERENCE.md` |
| Synthetic data patterns | `docs/SYNTHETIC_DATA_REFERENCE.md` |
| CLI redesign open gates | `docs/CLI_REDESIGN.md` |
| System defaults | `config/defaults.yml` |

## Reference Documentation

| Topic | Location |
|-------|----------|
| Bybit API docs | `reference/exchanges/bybit/` |
| pybit SDK docs | `reference/exchanges/pybit/` |
