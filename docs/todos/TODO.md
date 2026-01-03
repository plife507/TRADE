# Active TODO

**Last Updated**: 2026-01-03
**Status**: Mega-file refactoring COMPLETE

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

### 2. Mega-File Refactoring (QUEUED)

**See**: [MEGA_FILE_REFACTOR.md](MEGA_FILE_REFACTOR.md) for comprehensive 5-phase plan

| Phase | Target | LOC | Split Into |
|-------|--------|-----|------------|
| 1 | datetime_utils.py | new | Consolidate datetime parsing |
| 2 | data_tools.py | 2,205 | 4 focused modules |
| 3 | tool_registry.py | 1,472 | 8 spec modules |
| 4 | idea_card.py | 1,705 | 5 focused modules |
| 5 | Final validation | - | All smoke tests |

**Status**: Ready for execution after stress testing baseline established

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
