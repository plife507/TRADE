# Active TODO

**Last Updated**: 2026-01-04
**Status**: FORGE MIGRATION IN PROGRESS

---

## Current State

**All major work complete:**
- Legacy cleanup (2026-01-04) - All signal_rules Plays removed
- Mega-file refactoring (2026-01-03) - Phases 1-3 done
- Incremental State Architecture (2026-01-03)
- 1m Evaluation Loop (2026-01-02)
- Market Structure Stages 0-7 (2026-01-01)
- 72 bugs fixed across P0-P3

**Validation Status**:
- 80 tools registered, 23 categories
- 11/11 Plays normalize (V_100+ blocks format only)
- 42/42 indicators pass audit
- 6 structures in STRUCTURE_REGISTRY
- All smoke tests pass

**Refactoring Results**:
- `data_tools.py`: 2,205 → 4 modules + wrapper
- `tool_registry.py`: 1,472 → 303 LOC + 8 spec files
- `datetime_utils.py`: New (150 LOC)

---

## Active Work: Forge Migration

**Terminology Changes**:
- "IdeaCard" → "Play"
- "configs/idea_cards/" → "configs/plays/"
- "sandbox" → "forge"
- "src/backtest/audits/" → "src/forge/audits/" (planned)

**Hierarchy Model (Setup → Play → Playbook → System)**:
- **Setup**: Market condition detection (structure, zones, patterns)
- **Play**: A single tradeable idea with entry/exit rules
- **Playbook**: Collection of Plays for a market regime
- **System**: Complete trading system with Playbooks + risk management

### Phase F1: Rename Paths and References
- [ ] Rename `configs/idea_cards/` → `configs/plays/`
- [ ] Update all imports referencing "idea_card" → "play"
- [ ] Update CLI commands (idea-card-normalize → play-normalize, etc.)
- [ ] Update CLAUDE.md and module docs

### Phase F2: Forge Structure
- [ ] Create `src/forge/` directory
- [ ] Move `src/backtest/audits/` → `src/forge/audits/`
- [ ] Create `src/forge/plays/` for Play loading/validation
- [ ] Update all imports

### Phase F3: Hierarchy Implementation
- [ ] Define `Setup` dataclass (market condition specs)
- [ ] Define `Playbook` dataclass (collection of Plays)
- [ ] Define `System` dataclass (Playbooks + global risk)
- [ ] Update engine to support hierarchy

---

## Next Steps (After Forge Migration)

| Feature | Priority | Description |
|---------|----------|-------------|
| **Phase 4 Refactor** | Next | Split play.py into focused modules |
| **Streaming (Stage 8)** | High | Demo/Live websocket integration |
| **BOS/CHoCH Detection** | Medium | Break of Structure / Change of Character |
| **Advanced Operators** | Medium | `crosses_up`, `crosses_down`, `within_bps` |
| **Agent Module** | Future | Automated strategy generation |

---

## Quick Reference

```bash
# Validate (current paths - will change after migration)
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup

# Full smoke
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full
```

---

## Completed Work

| Phase | Date | Notes |
|-------|------|-------|
| Legacy Cleanup | 2026-01-04 | Removed all signal_rules Plays |
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
