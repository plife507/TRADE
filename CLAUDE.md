# CLAUDE.md

## Prime Directives

- **ALL FORWARD, NO LEGACY** - Delete old code, don't wrap it
- **MODERN PYTHON 3.12+** - Type hints, f-strings, pathlib, `X | None` not `Optional[X]`
- **LF LINE ENDINGS** - Use `newline='\n'` on Windows
- **TODO-DRIVEN** - Every change maps to `docs/TODO.md`
- **CLI VALIDATION** - Use CLI commands, not pytest

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

## Key Patterns

| Pattern | Rule |
|---------|------|
| Engine | Always use `create_engine_from_play()` + `run_engine_with_play()` |
| Indicators | Declare in Play YAML, access via snapshot |
| Database | Sequential access only (DuckDB limitation) |

## Timeframe Naming (ENFORCED)

**3-Feed + Exec Role System:**

| Term | Type | Example Values | Purpose |
|------|------|----------------|---------|
| `low_tf` | Timeframe | 1m, 3m, 5m, 15m | Fast: execution, entries |
| `med_tf` | Timeframe | 30m, 1h, 2h, 4h | Medium: structure, bias |
| `high_tf` | Timeframe | 12h, D | Slow: trend, context |
| `exec` | Pointer | "low_tf", "med_tf", "high_tf" | Which TF to step on |

**YAML keys/identifiers (ENFORCED):**
- ~~htf~~, ~~HTF~~ → use `high_tf`
- ~~ltf~~, ~~LTF~~ → use `low_tf`
- ~~exec_tf: 15m~~ → `exec` is a pointer, not a value

**Prose/comments (use full natural language):**
- "higher timeframe" not HTF
- "medium timeframe" not MTF
- "lower timeframe" not LTF
- "execution timeframe" not exec TF
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
# Validation
python trade_cli.py --smoke full                    # Validate everything
python trade_cli.py backtest audit-toolkit          # Check indicators

# Backtest
python trade_cli.py backtest run --play X --fix-gaps  # Run single backtest
python scripts/run_full_suite.py                    # 170-play synthetic suite
python scripts/run_full_suite.py --real --start 2025-01-01 --end 2025-06-30  # Real data suite
python scripts/run_real_verification.py             # 60-play real verification
python scripts/verify_trade_math.py --play X        # Math verification for a play

# Live/Demo
python trade_cli.py play run --play X --mode demo   # Demo mode (no real money)
python trade_cli.py play run --play X --mode live --confirm  # Live (REAL MONEY)
```

## Where to Find Details

| Topic | Location |
|-------|----------|
| Session context | `docs/SESSION_HANDOFF.md` |
| Project status | `docs/TODO.md` |
| DSL syntax | `docs/PLAY_DSL_COOKBOOK.md` |
| System defaults | `config/defaults.yml` |

## Reference Documentation

| Topic | Location |
|-------|----------|
| Bybit API docs | `reference/exchanges/bybit/` |
| pybit SDK docs | `reference/exchanges/pybit/` |
