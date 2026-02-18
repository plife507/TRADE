# Validation Best Practices

How to use the TRADE validation system effectively.

---

## Which Tier to Run

| Situation | Command | Why |
|-----------|---------|-----|
| Before every commit | `validate quick` | Catches indicator/engine regressions fast |
| Before merging a branch | `validate standard` | Adds structure parity, play suites, metrics |
| Before a release | `validate full` | Full coverage: all 170+ plays + determinism |
| Before deploying a play live | `validate pre-live --play X` | Connectivity, balance, conflict, config checks |
| After changing exchange/API code | `validate exchange` | Tests real Bybit API endpoints |
| Verifying real-data coverage | `validate real` | Syncs data once, runs 61 RV plays in parallel |

**Rule of thumb**: run the minimum tier that covers what you changed.

---

## Match Validation to What Changed

| Changed module | Minimum validation | Why |
|----------------|-------------------|-----|
| `src/indicators/` | `validate module --module audits` | Registry contract + incremental parity |
| `src/engine/` | `validate module --module core` | Core plays exercise the engine |
| `src/backtest/sim/` | `validate module --module sim` | Sim order smoke tests |
| `src/structures/` | `validate module --module parity` | Structure detector parity |
| `src/backtest/metrics.py` | `validate module --module metrics` | Financial math correctness |
| Play YAML files | `validate quick` | Parses + runs core plays |
| Multiple modules | `validate standard` or `full` | Broad coverage |
| Exchange/API code | `validate exchange` | Live API integration |
| Pre-deploy a play | `validate pre-live --play X` | Full readiness gate |

---

## Using Modules for Fast Feedback

Modules let you validate a single concern without running the full suite. This is the fastest way to get feedback during development.

```bash
# Run a single module
python trade_cli.py validate module --module core

# JSON output (for parsing or CI)
python trade_cli.py validate module --module indicators --json

# Control parallelism (useful on constrained machines)
python trade_cli.py validate module --module indicators --workers 2
```

### Available modules

| Module | Gates | Plays | Typical time |
|--------|-------|-------|-------------|
| `core` | G4 | 5 | ~5s |
| `risk` | G4b | 9 | ~30s |
| `audits` | G2+G3 | - | ~2s |
| `operators` | G8 | 25 | ~20s |
| `structures` | G9 | 14 | ~15s |
| `complexity` | G10 | 13 | ~15s |
| `indicators` | G12 | 84 | ~30s |
| `patterns` | G13 | 34 | ~20s |
| `parity` | G5+G6 | - | ~1s |
| `sim` | G7 | - | ~1s |
| `metrics` | G11 | - | <1s |
| `determinism` | G14 | 5x2 | ~10s |

---

## Parallelism

### How it works

- **Play suites** (G8-G13): each play runs in a separate process via `ProcessPoolExecutor`. Safe because synthetic plays never touch DuckDB.
- **Independent gates**: gates within the same stage run concurrently via `ThreadPoolExecutor` (e.g., G2 and G3 run at the same time).
- **Real-data tier**: DuckDB is synced once (serial writes), then all 61 plays run in parallel (read-only).

### Controlling workers

```bash
# Default: cpu_count - 1
python trade_cli.py validate full

# Limit to 4 workers (e.g., on a machine with heavy load)
python trade_cli.py validate full --workers 4

# Single-threaded (for debugging)
python trade_cli.py validate full --workers 1
```

### Stage schedule (quick/standard/full)

```
Stage 0: [G1]                    -- YAML parse
Stage 1: [G2, G3]                -- registry + parity audits (parallel)
Stage 2: [G4, G4b]               -- core + risk plays (parallel)
Stage 3: [G5, G6, G7]            -- structure/rollup/sim (parallel, standard+)
Stage 4: [G8, G9, G10]           -- play suites (parallel, each internally parallel, standard+)
Stage 5: [G11]                   -- metrics (standard+)
Stage 6: [G12, G13]              -- indicator + pattern suites (parallel, full only)
Stage 7: [G14]                   -- determinism (full only)
```

Stages are barriers: if any gate in a stage fails and `--no-fail-fast` is not set, subsequent stages are skipped.

---

## Claude Code Agent Orchestration

When validating from Claude Code, use modules for parallel agent execution:

**For standard-tier validation:**

1. Run critical path serially (audits -> core -> risk)
2. If all pass, launch remaining modules as parallel background Bash tasks
3. Collect results

**For full-tier validation:**

Same as standard, plus `indicators`, `patterns`, `determinism` as additional background tasks.

**For real-data validation:**

Use the `validate real` tier directly -- it handles sync-once + parallel internally.

```bash
# Example: run two modules in parallel background
python trade_cli.py validate module --module operators --json &
python trade_cli.py validate module --module structures --json &
wait
```

---

## Debugging Failures

### A gate fails -- now what?

1. **Read the failure message**: it tells you which play and what went wrong
2. **Run the failing module alone** to get focused output:
   ```bash
   python trade_cli.py validate module --module structures
   ```
3. **Run the specific play** to see full engine output:
   ```bash
   python trade_cli.py backtest run --play STR_001_swing_basic --synthetic
   ```
4. **Use debug tools** for deeper investigation:
   ```bash
   python trade_cli.py debug math-parity --play X --start 2025-01-01 --end 2025-06-30
   python trade_cli.py debug snapshot-plumbing --play X --start 2025-01-01 --end 2025-06-30
   ```

### Common failure patterns

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "zero trades" | Signal conditions too tight for synthetic data | Widen `near_pct`, check dilated patterns |
| Registry contract breach | Indicator output format changed | Fix indicator `compute()` return shape |
| Incremental parity mismatch | Incremental vs vectorized divergence | Check `is_ready` logic, rounding |
| Determinism hash mismatch | Non-deterministic state (random, time) | Ensure all state is seed-controlled |

---

## Adding New Validation Plays

1. Create YAML in the appropriate `plays/validation/<suite>/` directory
2. Include a `validation:` block with `pattern:` for synthetic data
3. Ensure the play produces trades on its synthetic pattern
4. Run the module to verify: `python trade_cli.py validate module --module <suite>`
5. The play is automatically picked up by `_gate_play_suite()` -- no registration needed

---

## CI Integration

All commands support `--json` for machine-readable output:

```bash
# Quick gate for PRs
python trade_cli.py validate quick --json

# Full gate for releases
python trade_cli.py validate full --json --no-fail-fast

# Exit code: 0 = all pass, 1 = any fail
echo $?
```

JSON output includes per-gate timing, checked counts, and failure details.
