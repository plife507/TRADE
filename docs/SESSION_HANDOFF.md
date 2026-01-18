# Session Handoff

**Date**: 2026-01-17
**Branch**: feature/unified-engine

---

## Quick Commands

```bash
# Smoke test
python trade_cli.py --smoke full

# Run backtest
python trade_cli.py backtest run --play <name> --fix-gaps

# Indicator audit
python trade_cli.py backtest audit-toolkit
```

---

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project rules |
| `docs/PLAY_DSL_COOKBOOK.md` | DSL reference |

---

## Directory Structure

```
src/engine/       # PlayEngine
src/indicators/   # 43 indicators
src/structures/   # 7 structure types
src/backtest/     # Backtest infrastructure
src/data/         # DuckDB data layer
src/cli/          # CLI interface
```
