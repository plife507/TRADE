# CLAUDE.md

## Prime Directives

- **ALL FORWARD, NO LEGACY** - Delete old code, don't wrap it
- **MODERN PYTHON 3.12+** - Type hints, f-strings, pathlib, `X | None` not `Optional[X]`
- **LF LINE ENDINGS** - Use `newline='\n'` on Windows
- **TODO-DRIVEN** - Every change maps to `docs/TODO.md`
- **CLI VALIDATION** - Use CLI commands, not pytest

## Architecture

```
src/engine/        # ONE unified engine (PlayEngine) for backtest/live
src/indicators/    # 43 indicators + 6 incremental (O(1))
src/structures/    # 6 structure types (swing, trend, zone, fib, derived_zone, rolling_window)
src/backtest/      # Infrastructure only (sim, runtime, features) - NOT an engine
src/data/          # DuckDB historical data
src/tools/         # CLI/API surface
```

## Key Patterns

| Pattern | Rule |
|---------|------|
| Engine | Always use `create_engine_from_play()` + `run_engine_with_play()` |
| TF roles | Use `high_tf/med_tf/low_tf` (NOT htf/mtf/ltf) |
| Indicators | Declare in Play YAML, access via snapshot |
| Database | Sequential access only (DuckDB limitation) |

## Quick Commands

```bash
python trade_cli.py --smoke full                    # Validate everything
python trade_cli.py backtest run --play X --fix-gaps  # Run backtest
python trade_cli.py backtest audit-toolkit          # Check indicators
```

## Where to Find Details

| Topic | Location |
|-------|----------|
| Current status | `docs/TODO.md` |
| Session context | `docs/SESSION_HANDOFF.md` |
| What runs today | `docs/PROJECT_STATUS.md` |
| DSL syntax | `docs/PLAY_DSL_COOKBOOK.md` |
| Incremental indicators | `docs/INCREMENTAL_INDICATORS.md` |
| Play examples | `tests/stress/plays/` |
