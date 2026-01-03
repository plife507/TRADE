# TRADE Documentation

Navigation hub for all project documentation.

---

## Quick Links

| Document | Purpose |
|----------|---------|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Current state, blockers, next steps |
| [SESSION_HANDOFF.md](SESSION_HANDOFF.md) | Inter-session context |
| [todos/TODO.md](todos/TODO.md) | Active work tracking |
| [audits/OPEN_BUGS.md](audits/OPEN_BUGS.md) | Bug tracker (P0-P3) |

---

## Documentation Sections

| Folder | Index | Description |
|--------|-------|-------------|
| [architecture/](architecture/INDEX.md) | [INDEX.md](architecture/INDEX.md) | System architecture, domains, engine flow |
| [audits/](audits/INDEX.md) | [INDEX.md](audits/INDEX.md) | Audit reports, bug tracking, technical reviews |
| [reviews/](reviews/INDEX.md) | [INDEX.md](reviews/INDEX.md) | Code reviews, design decisions, validation |
| [todos/](todos/INDEX.md) | [INDEX.md](todos/INDEX.md) | Active and archived TODO documents |
| [data/](data/DATA_MODULE.md) | [DATA_MODULE.md](data/DATA_MODULE.md) | DuckDB stores, schemas, data pipeline |
| [strategy_factory/](strategy_factory/STRATEGY_FACTORY.md) | [STRATEGY_FACTORY.md](strategy_factory/STRATEGY_FACTORY.md) | IdeaCards, promotion loops |
| [session_reviews/](session_reviews/README.md) | [README.md](session_reviews/README.md) | Archived session summaries |
| [_archived/](_archived/INDEX.md) | [INDEX.md](_archived/INDEX.md) | Historical/obsolete documentation |

---

## Quick Start

```bash
python trade_cli.py                     # Run CLI
python trade_cli.py --smoke full        # Full smoke test
python trade_cli.py backtest run --idea-card <ID> --start <date> --end <date>
```

---

## External References

| Topic | Location |
|-------|----------|
| AI Guidance | `CLAUDE.md` |
| Module Docs | `src/*/CLAUDE.md` |
| IdeaCards | `configs/idea_cards/` |
| Validation IdeaCards | `configs/idea_cards/_validation/` |
