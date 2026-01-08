# TRADE Documentation

Navigation hub for all project documentation.

**Last Updated**: 2026-01-07

---

## Quick Links

| Document | Purpose |
|----------|---------|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Current state, blockers, next steps |
| [SESSION_HANDOFF.md](SESSION_HANDOFF.md) | Inter-session context |
| [todos/TODO.md](todos/TODO.md) | Active work tracking |
| [audits/OPEN_BUGS.md](audits/OPEN_BUGS.md) | Bug tracker (0 open) |

---

## Current State

- 43 indicators in INDICATOR_REGISTRY
- 6 structures in STRUCTURE_REGISTRY (swing, fibonacci, zone, trend, rolling_window, derived_zone)
- Validation Plays relocated to `tests/validation/plays/`
- Blocks DSL v3.0.0 with 12 operators + 3 window operators
- All 5 DSL bugs fixed (crossover, anchor_tf, duration)

---

## Documentation Sections

| Folder | Index | Description |
|--------|-------|-------------|
| [specs/](specs/INDEX.md) | [INDEX.md](specs/INDEX.md) | 7 active specs: architecture, Play DSL, incremental state |
| [audits/](audits/INDEX.md) | [INDEX.md](audits/INDEX.md) | Bug tracking, audit reports |
| [todos/](todos/INDEX.md) | [INDEX.md](todos/INDEX.md) | Active and archived TODO documents |
| [data/](data/DATA_MODULE.md) | [DATA_MODULE.md](data/DATA_MODULE.md) | DuckDB stores, schemas, data pipeline |
| [strategy_factory/](strategy_factory/STRATEGY_FACTORY.md) | [STRATEGY_FACTORY.md](strategy_factory/STRATEGY_FACTORY.md) | Plays, promotion loops |
| [reviews/](reviews/INDEX.md) | [INDEX.md](reviews/INDEX.md) | Architecture and parity reviews |
| [guides/](guides/) | — | DSL patterns, best practices |

---

## Quick Start

```bash
python trade_cli.py                     # Run CLI
python trade_cli.py --smoke full        # Full smoke test
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
python trade_cli.py backtest audit-toolkit
```

---

## External References

| Topic | Location |
|-------|----------|
| AI Guidance | `CLAUDE.md` |
| Module Docs | `src/*/CLAUDE.md` |
| Plays | `strategies/plays/` |
| Validation Plays | `tests/validation/plays/` |
