# TRADE Project Status

**Last Updated**: 2026-01-17
**Branch**: feature/unified-engine

---

## What This Is

A crypto trading bot with backtesting and live trading capabilities.

---

## Directory Layout

```
src/
├── engine/        # Unified PlayEngine (backtest + live)
├── indicators/    # 43 indicators
├── structures/    # 7 structure detectors
├── backtest/      # Backtest infrastructure
├── data/          # DuckDB historical data
├── cli/           # CLI interface
└── tools/         # CLI tools

tests/
├── stress/plays/       # (empty - needs new plays)
├── validation/plays/   # (empty - needs new plays)
└── functional/plays/   # (empty - needs new plays)

docs/
├── PLAY_DSL_COOKBOOK.md   # DSL reference
├── SESSION_HANDOFF.md     # Quick reference
└── PROJECT_STATUS.md      # This file
```

---

## Quick Commands

```bash
python trade_cli.py --smoke full
python trade_cli.py backtest run --play <name> --fix-gaps
python trade_cli.py backtest audit-toolkit
```
