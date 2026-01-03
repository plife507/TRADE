# Active TODO

**Last Updated**: 2026-01-03
**Status**: Post-Refactor - Ready for New Work

---

## Current State

**All major refactors complete:**
- Incremental State Architecture (2026-01-03)
- 1m Evaluation Loop (2026-01-02)
- Market Structure Stages 0-7 (2026-01-01)
- 72 bugs fixed across P0-P3

**Validation Status**:
- 30/30 IdeaCards normalize
- 42/42 indicators pass audit
- All smoke tests pass

---

## Next Steps (Priority Order)

### 1. Commit Uncommitted Work
```bash
git add -A
git commit -m "feat: incremental state architecture, 72 bug fixes, validation complete"
```

### 2. Deferred Structural Refactoring

| Task | Effort | Notes |
|------|--------|-------|
| Split BacktestEngine.run() (~500 LOC) | 4h | Too large for single method |
| Refactor IdeaCard (1165 LOC) | 8h | Split into focused classes |
| Split tool_registry.py (1200+ LOC) | 4h | Split by category |
| Unify data preparation paths | 4h | Consolidate duplicate code |

### 3. Future Features

| Feature | Status | Notes |
|---------|--------|-------|
| Streaming (Stage 8) | Future | Demo/Live websocket |
| BOS/CHoCH Detection | Future | Break of Structure / Change of Character |
| Advanced Operators | Future | crosses_up, crosses_down, within_bps |
| Agent Module | Future | Automated strategy generation |

---

## Quick Reference

```bash
# Validate
python trade_cli.py backtest idea-card-normalize-batch --dir configs/idea_cards/_validation
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup
python trade_cli.py backtest structure-smoke

# Backtest smoke (requires env var)
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full
```

---

## Completed Work (Archived)

| Phase | Date | Archive |
|-------|------|---------|
| Incremental State | 2026-01-03 | [INCREMENTAL_STATE_IMPLEMENTATION.md](INCREMENTAL_STATE_IMPLEMENTATION.md) |
| 1m Eval Loop | 2026-01-02 | [1M_EVAL_LOOP_REFACTOR.md](1M_EVAL_LOOP_REFACTOR.md) |
| Bug Remediation | 2026-01-03 | [../audits/archived/2026-01-03_BUGS_RESOLVED.md](../audits/archived/2026-01-03_BUGS_RESOLVED.md) |
| Market Structure | 2026-01-01 | [archived/2026-01-01/MARKET_STRUCTURE_PHASES.md](archived/2026-01-01/MARKET_STRUCTURE_PHASES.md) |

---

## Rules

- **MUST NOT write code before TODO exists**
- Every code change maps to a TODO checkbox
- New work discovered: STOP -> update TODO -> continue
- Completed phases are FROZEN
