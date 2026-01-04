# TODO Index

Documentation index for work tracking in the TRADE project.
**Last Updated**: 2026-01-04

---

## Active Work

| Document | Description | Status |
|----------|-------------|--------|
| [TODO.md](TODO.md) | Current focus, next steps | **Forge Migration in Progress** |
| [MEGA_FILE_REFACTOR.md](MEGA_FILE_REFACTOR.md) | Engine file size refactoring | Phases 1-3 COMPLETE, Phase 4 pending |
| [../audits/OPEN_BUGS.md](../audits/OPEN_BUGS.md) | Bug tracker (4 open) | Active |

---

## Forge Migration (Active)

Major refactoring effort to restructure the project:

| Document | Purpose |
|----------|---------|
| [FORGE_MIGRATION_RULES.md](FORGE_MIGRATION_RULES.md) | Forward-only rules (NO legacy fallbacks) |
| [FORGE_MIGRATION_PHASES.md](FORGE_MIGRATION_PHASES.md) | 8 phases with detailed checkboxes |
| [FORGE_CLEANUP_AGENT.md](FORGE_CLEANUP_AGENT.md) | Final verification checklist |

**Terminology Changes**:
- "IdeaCard" -> "Play"
- "configs/idea_cards/" -> "configs/plays/"
- "sandbox" -> "forge"

**Hierarchy Model**: Setup -> Play -> Playbook -> System

**Migration Phases**: P1 (dirs) -> P2 (files) -> P3 (classes) -> P4 (functions) -> P5 (vars) -> P6 (CLI) -> P7 (config) -> P8 (cleanup)

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

## Bug Archives

| Date | Document | Summary |
|------|----------|---------|
| 2026-01-03 | [../audits/archived/2026-01-03_BUGS_RESOLVED.md](../audits/archived/2026-01-03_BUGS_RESOLVED.md) | 72 bugs fixed (P0:7, P1:25, P2:28, P3:12) |

---

## TODO Workflow

1. **Before coding**: Create or update TODO.md with planned work
2. **During work**: Check off items as completed
3. **New discoveries**: STOP, update TODOs, continue
4. **Completion**: Archive completed phase documents by date
5. **Phases**: Completed phases are FROZEN - do not modify

See [CLAUDE.md](../../CLAUDE.md) for full TODO-driven execution rules.
