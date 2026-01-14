# TODO Index

Documentation index for work tracking in the TRADE project.
**Last Updated**: 2026-01-10

---

## Active Work

| Document | Description | Status |
|----------|-------------|--------|
| [TODO.md](TODO.md) | Current focus, next steps | **STRESS TEST 4.x COMPLETE (343/343)** |
| [STRESS_TESTING.md](STRESS_TESTING.md) | Progressive complexity validation | COMPLETE (163/163 plays) |
| [STRESS_TEST_2_TODO.md](STRESS_TEST_2_TODO.md) | Stress Test 2.0 (320 plays) | COMPLETE |
| [STRESS_TEST_3_TODO.md](STRESS_TEST_3_TODO.md) | Stress Test 3.0 (163 plays) | COMPLETE |
| [FUNCTIONAL_TEST_COVERAGE.md](FUNCTIONAL_TEST_COVERAGE.md) | Real-data engine validation | Complete (43/43 indicators) |
| [ICT_MARKET_STRUCTURE.md](ICT_MARKET_STRUCTURE.md) | ICT/SMC structure detectors | PLANNING |
| [../audits/OPEN_BUGS.md](../audits/OPEN_BUGS.md) | Bug tracker | All Fixed |

**Recent Completions (2026-01-10)**:
- Stress Test 4.0: Order/risk/leverage (30/30)
- Stress Test 4.1: Edge cases, TF expansion (100/100)
- Stress Test 4.2: Multi-pair TF verification (50/50)
- Architecture docs: Hybrid Engine Design, OI/Funding Integration

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
| `2026-01-10` | Jan 10, 2026 | Stress Test 4.x (343 plays), Hybrid Engine Design, OI/Funding Integration |
| `2026-01-09` | Jan 9, 2026 | Stress Test 3.0 (163 plays), Structure module production |
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
