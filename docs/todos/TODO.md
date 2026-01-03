# Active TODO

**Last Updated**: 2026-01-02
**Status**: All audit bugs fixed, ready for 1m eval loop refactor

---

## Current Focus

| Priority | Item | Status |
|----------|------|--------|
| **ACTIVE** | 1m Evaluation Loop Refactor | See [1M_EVAL_LOOP_REFACTOR.md](1M_EVAL_LOOP_REFACTOR.md) |

---

## 1m Evaluation Loop Refactor

**Goal**: Mandatory 1m signal evaluation for zone-touch detection
**Status**: ✅ COMPLETE (2026-01-02)

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | 1m Index Mapping | [x] |
| Phase 2 | Snapshot mark_price Resolution | [x] |
| Phase 3 | Engine 1m Sub-Loop | [x] |
| Phase 4 | Exchange 1m Fill Timing | [x] |
| Phase 5 | Data Loading Verification | [x] |
| Phase 6 | Validation IdeaCards | [x] |

Full spec: [1M_EVAL_LOOP_REFACTOR.md](1M_EVAL_LOOP_REFACTOR.md)

---

## Completed (2026-01-02)

All P0-P3 bugs from Architecture Review are **FIXED**.

See [OPEN_BUGS.md](../audits/OPEN_BUGS.md) for full audit history:
- P0: 7 fixed, 0 open
- P1: 25 fixed, 0 open
- P2: 28 fixed, 0 open
- P3: 12 fixed, 0 open

---

## Structural Refactoring (Deferred)

From Architecture Review - do after 1m refactor:

### Phase 3: Code Consolidation
- [ ] Unify data preparation paths in engine
- [ ] Consolidate manifest/hash implementations
- [ ] Merge duplicate IndicatorRegistry classes
- [ ] Extract shared validation logic in CLI

### Phase 4: Complete Integrations
- [ ] Wire LiquidationModel into exchange simulation
- [ ] Enable ExchangeMetrics recording
- [ ] Apply Constraints validation to orders
- [ ] Integrate ImpactModel into execution

### Phase 5: Architecture Cleanup
- [ ] Split BacktestEngine.run() (~500 LOC) into smaller methods
- [ ] Refactor IdeaCard (1165 LOC) into smaller focused classes
- [ ] Split tool_registry.py (1200+ LOC) by category
- [ ] Complete RuntimeSnapshot -> RuntimeSnapshotView migration

---

## Quick Reference

```bash
# Validate before commit
python trade_cli.py backtest idea-card-normalize --idea-card BTCUSDT_1h_ema_basic

# Backtest smoke test
python trade_cli.py --smoke backtest

# Full smoke (requires TRADE_SMOKE_INCLUDE_BACKTEST=1)
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full
```

---

## Rules

- **MUST NOT write code before TODO exists**
- Every code change maps to a TODO checkbox
- New work discovered → STOP → update TODO → continue
- 1m refactor phases are the current work

---

## Archive

Completed work archived in `docs/todos/archived/` by date.
