# TODO Index

Documentation index for work tracking in the TRADE project.
**Last Updated**: 2026-01-06

---

## Active Work

| Document | Description | Status |
|----------|-------------|--------|
| [TODO.md](TODO.md) | Current focus, next steps | **ICT Structures** |
| [ICT_MARKET_STRUCTURE.md](ICT_MARKET_STRUCTURE.md) | ICT/SMC structure detectors | PLANNING |
| [TV_WEBHOOK_MARKET_STRUCTURE_VERIFICATION.md](TV_WEBHOOK_MARKET_STRUCTURE_VERIFICATION.md) | TradingView webhook validation tool | READY |
| [MEGA_FILE_REFACTOR.md](MEGA_FILE_REFACTOR.md) | Engine file size refactoring | Phases 1-3 COMPLETE, Phase 4 pending |
| [../audits/OPEN_BUGS.md](../audits/OPEN_BUGS.md) | Bug tracker (4 open) | Active |

---

## Workstreams (TRADE Architecture Evolution)

| Workstream | Focus | Status |
|------------|-------|--------|
| **W1: Forge** | Development environment, audits | **ACTIVE** |
| W2: Blocks DSL | Pure expression evaluation | Planned |
| W3: Incremental | O(1) market structure detectors | ✅ Implemented |
| W4: Hierarchy | Block/Play/System | ✅ Implemented |

**W1 Goals**:
- Move audits from `src/backtest/audits/` to `src/forge/audits/`
- Pure function architecture (data flow, no control flow)
- Validation and generation tooling

---

## Archived Work

Completed work is archived by date in `archived/`:

| Folder | Period | Key Work |
|--------|--------|----------|
| `2026-01/` | Jan 2026 | Forge migration, simulator orders, incremental state, analytics |
| `2026-01-01/` | Jan 1, 2026 | Market structure, Play value flow, metrics, legacy cleanup |
| `2025-12-31/` | Dec 31, 2025 | Price feed 1m preflight |
| `2025-12-30/` | Dec 30, 2025 | Engine modular refactor, backtester fixes |
| `2025-12-18/` | Dec 18, 2025 | Production pipeline validation, financial metrics |
| `2025-12-17/` | Dec 17, 2025 | P0 input source fix, warmup sync |

---

## TODO Workflow

1. **Before coding**: Create or update TODO.md with planned work
2. **During work**: Check off items as completed
3. **New discoveries**: STOP, update TODOs, continue
4. **Completion**: Archive completed phase documents by date
5. **Phases**: Completed phases are FROZEN - do not modify

See [CLAUDE.md](../../CLAUDE.md) for full TODO-driven execution rules.
