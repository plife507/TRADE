# Active TODO

**Last Updated**: 2026-01-04
**Status**: All major work COMPLETE - ready for new features

---

## Current State

**All major work complete:**
- Legacy cleanup (2026-01-04) - All signal_rules IdeaCards removed
- Mega-file refactoring (2026-01-03) - Phases 1-3 done
- Incremental State Architecture (2026-01-03)
- 1m Evaluation Loop (2026-01-02)
- Market Structure Stages 0-7 (2026-01-01)
- 72 bugs fixed across P0-P3

**Validation Status**:
- 80 tools registered, 23 categories
- 11/11 IdeaCards normalize (V_100+ blocks format only)
- 42/42 indicators pass audit
- 6 structures in STRUCTURE_REGISTRY
- All smoke tests pass

**Refactoring Results**:
- `data_tools.py`: 2,205 → 4 modules + wrapper
- `tool_registry.py`: 1,472 → 303 LOC + 8 spec files
- `datetime_utils.py`: New (150 LOC)

---

## Next Steps (Choose One)

| Feature | Priority | Description |
|---------|----------|-------------|
| **Phase 4 Refactor** | Next | Split idea_card.py into focused modules |
| **Streaming (Stage 8)** | High | Demo/Live websocket integration |
| **BOS/CHoCH Detection** | Medium | Break of Structure / Change of Character |
| **Advanced Operators** | Medium | `crosses_up`, `crosses_down`, `within_bps` |
| **Agent Module** | Future | Automated strategy generation |

---

## Quick Reference

```bash
# Validate
python trade_cli.py backtest idea-card-normalize-batch --dir configs/idea_cards/_validation
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup

# Full smoke
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full
```

---

## Completed Work

| Phase | Date | Notes |
|-------|------|-------|
| Legacy Cleanup | 2026-01-04 | Removed all signal_rules IdeaCards |
| Mega-file Refactor | 2026-01-03 | Phases 1-3 complete |
| Incremental State | 2026-01-03 | O(1) hot loop |
| 1m Eval Loop | 2026-01-02 | mark_price in snapshot |
| Bug Remediation | 2026-01-03 | 72 bugs fixed |
| Market Structure | 2026-01-01 | Stages 0-7 |

---

## Rules

- **ALL FORWARD, NO LEGACY** - No backward compatibility ever
- **LF LINE ENDINGS ONLY** - Never CRLF on Windows
- MUST NOT write code before TODO exists
- Every code change maps to a TODO checkbox
