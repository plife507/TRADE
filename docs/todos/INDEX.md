# TODO Index

Documentation index for work tracking in the TRADE project.
**Last Updated**: 2026-01-09

---

## Active Work

| Document | Description | Status |
|----------|-------------|--------|
| [TODO.md](TODO.md) | Current focus, next steps | **Stress Testing Phase 2** |
| [STRESS_TESTING.md](STRESS_TESTING.md) | Progressive complexity validation (0-100%) | IN_PROGRESS (Gate 2.2 next) |
| [FUNCTIONAL_TEST_COVERAGE.md](FUNCTIONAL_TEST_COVERAGE.md) | Real-data engine validation | Phase 2 Complete (43/43 indicators) |
| [ICT_MARKET_STRUCTURE.md](ICT_MARKET_STRUCTURE.md) | ICT/SMC structure detectors | PLANNING |
| [TV_WEBHOOK_MARKET_STRUCTURE_VERIFICATION.md](TV_WEBHOOK_MARKET_STRUCTURE_VERIFICATION.md) | TradingView webhook validation tool | READY |
| [../audits/OPEN_BUGS.md](../audits/OPEN_BUGS.md) | Bug tracker | All Fixed |
| [../audits/STRESS_TEST_BUGS.md](../audits/STRESS_TEST_BUGS.md) | Stress test bug tracker | 3 resolved, 3 open items |

**Open Items Requiring Decision**:
- DEBT-001: Symbol vs Word operators - see STRESS_TEST_BUGS.md for options
- DOC-001/DOC-002: Cookbook fixes blocked pending DEBT-001 decision

---

## Workstreams (TRADE Architecture Evolution)

| Workstream | Focus | Status |
|------------|-------|--------|
| W1: Forge | Development environment, audits | COMPLETE |
| W2: Blocks DSL | Pure expression evaluation | COMPLETE (anchor_tf fixed) |
| W3: Incremental | O(1) market structure detectors | COMPLETE |
| W4: Hierarchy | Block/Play/System | COMPLETE |

**DSL Improvements (2026-01-07)**:
- Crossover operators aligned to TradingView semantics
- Window operators now scale by `anchor_tf`
- Duration-based operators working correctly
- 7 strategy patterns documented in `docs/guides/DSL_STRATEGY_PATTERNS.md`

---

## Archived Work

Completed work is archived by date in `archived/`:

| Folder | Period | Key Work |
|--------|--------|----------|
| `2026-01-08/` | Jan 8, 2026 | DSL Foundation Freeze (259 tests), Cookbook Alignment, Tiered Testing |
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
