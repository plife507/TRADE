# Code Reviews Index

**Last Updated**: 2026-01-07

---

## Current Reviews

| Review | Date | Status | Topic |
|--------|------|--------|-------|
| [ARCHITECTURE_EXPERT_REVIEW.md](ARCHITECTURE_EXPERT_REVIEW.md) | 2026-01-04 | Active | Engine design, Sim-Live parity gaps |
| [SIMULATOR_VS_LIVE_PARITY_REVIEW.md](SIMULATOR_VS_LIVE_PARITY_REVIEW.md) | 2026-01-04 | Active | Detailed capability matrix: sim vs live |
| [BACKTEST_VISUALIZATION_BEST_PRACTICES.md](BACKTEST_VISUALIZATION_BEST_PRACTICES.md) | 2026-01-05 | Active | Visualization system best practices |
| [CODE_COMPLEXITY_REFACTOR_REVIEW.md](CODE_COMPLEXITY_REFACTOR_REVIEW.md) | 2026-01-04 | Active | Code complexity analysis |

---

## Key Findings

### ARCHITECTURE_EXPERT_REVIEW

Comprehensive review of engine architecture:
- Hot loop: A grade (O(1) access)
- Multi-TF: A- grade (forward-fill correct)
- Blocks DSL: B+ grade (needs limit order extensions)
- Simulated Exchange: C+ grade (single-order limitation)
- Sim-Live Parity: D grade (major gap - different code paths)

### SIMULATOR_VS_LIVE_PARITY_REVIEW

Current simulator supports ~15% of Bybit live capabilities:
- Order Types: Only market orders (limit/stop not implemented)
- Position Management: No scaling, no partial close
- TP/SL: Basic only (no trailing, no partial)

---

## Active Documentation

For current project state, see:
- `docs/PROJECT_STATUS.md` - Current status
- `docs/todos/TODO.md` - Active work
- `docs/audits/OPEN_BUGS.md` - Bug tracker (0 open)
- `docs/specs/` - Architecture specs
