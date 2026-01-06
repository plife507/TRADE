# TODO Index

Documentation index for work tracking in the TRADE project.
**Last Updated**: 2026-01-05

---

## Active Work

| Document | Description | Status |
|----------|-------------|--------|
| [TODO.md](TODO.md) | Current focus, next steps | **ICT Structures** |
| [ICT_MARKET_STRUCTURE.md](ICT_MARKET_STRUCTURE.md) | ICT/SMC structure detectors | PLANNING |
| [MEGA_FILE_REFACTOR.md](MEGA_FILE_REFACTOR.md) | Engine file size refactoring | Phases 1-3 COMPLETE, Phase 4 pending |
| [../audits/OPEN_BUGS.md](../audits/OPEN_BUGS.md) | Bug tracker (4 open) | Active |

---

## Workstreams (TRADE Architecture Evolution)

| Workstream | Focus | Status |
|------------|-------|--------|
| **W1: Forge** | Development environment, audits | **ACTIVE** |
| W2: Blocks DSL | Pure expression evaluation | Planned |
| W3: Incremental | O(1) market structure detectors | Implemented |
| W4: Hierarchy | Setup/Play/Playbook/System | Planned |

**W1 Goals**:
- Move audits from `src/backtest/audits/` to `src/forge/audits/`
- Pure function architecture (data flow, no control flow)
- Validation and generation tooling

---

## Forge Migration (COMPLETE)

✅ **Completed 2026-01-04** - 8 phases, 221 file changes

| Document | Purpose | Status |
|----------|---------|--------|
| [FORGE_MIGRATION_RULES.md](FORGE_MIGRATION_RULES.md) | Forward-only rules | Archive candidate |
| [FORGE_MIGRATION_PHASES.md](FORGE_MIGRATION_PHASES.md) | 8 phases with results | Archive candidate |
| [FORGE_CLEANUP_AGENT.md](FORGE_CLEANUP_AGENT.md) | Verification checklist | Archive candidate |

**Results**:
- IdeaCard -> Play (all references)
- configs/idea_cards/ -> configs/plays/
- Zero legacy references remain

---

## Archived Work

Completed work is archived by date in `archived/`:

| Folder | Period | Key Work |
|--------|--------|----------|
| `2026-01/` | Jan 2026 | Incremental state, 1m eval loop spec, backtest analytics, registry consolidation |
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
