# Active TODO

**Last Updated**: 2026-01-04
**Status**: W1+W2 COMPLETE, W3 ACTIVE

---

## Current State

**Architecture Evolution (5 Workstreams)**:
- ✅ **W1: The Forge** (2026-01-04) - `src/forge/` with validation framework
- ✅ **W2: StateRationalizer** (2026-01-04) - Layer 2 transitions, derived state, conflicts
- 🔄 **W3: Price Source Abstraction** - NEXT
- ⏳ **W4: Trading Hierarchy** - Pending (Setup/Play/Playbook/System)
- ⏳ **W5: Live/Demo Integration** - Pending (bundled with W3)

**Prior Work Complete:**
- Forge Migration (2026-01-04) - IdeaCard -> Play rename (8 phases, 221 files)
- Mega-file refactoring (2026-01-03) - Phases 1-3 done
- Incremental State Architecture (2026-01-03)
- 1m Evaluation Loop (2026-01-02)
- Market Structure Stages 0-7 (2026-01-01)
- 72 bugs fixed across P0-P3

**Validation Status**:
- 80 tools registered, 23 categories
- 15/15 Plays normalize (V_100+ blocks format only)
- 42/42 indicators pass audit
- 6 structures in STRUCTURE_REGISTRY
- All smoke tests pass

**New API**:
```python
from src.backtest import Play, load_play, create_engine_from_play
from src.backtest.rationalization import StateRationalizer, RationalizedState
```

---

## Active Work: W3 Price Source Abstraction

**Goal**: Unified interface for backtest/demo/live price feeds

### W3-P1: Protocol Definition
- [ ] Create `src/backtest/prices/source.py` with PriceSource Protocol
- [ ] Define PricePoint dataclass
- [ ] Define methods: get_mark_price, get_ohlcv, get_1m_marks, healthcheck

### W3-P2: Backtest Implementation
- [ ] Create `src/backtest/prices/backtest_source.py`
- [ ] Wrap HistoricalDataStore
- [ ] Inject into BacktestEngine

### W3-P3 + W5: Demo/Live Sources (bundled)
- [ ] Create `src/backtest/prices/demo_source.py`
- [ ] Create `src/core/prices/live_source.py`
- [ ] WebSocket integration
- [ ] Live engine mode

---

## Trading Hierarchy (W4 - After W3)

**Hierarchy Model (Setup -> Play -> Playbook -> System)**:
- **Setup**: Market condition detection (structure, zones, patterns)
- **Play**: A single tradeable idea with entry/exit rules
- **Playbook**: Collection of Plays for a market regime
- **System**: Complete trading system with Playbooks + risk management

---

## Next Steps

| Feature | Priority | Description |
|---------|----------|-------------|
| **W3 Price Source** | ACTIVE | Unified price interface |
| **W5 Live/Demo** | Bundled | WebSocket + live engine mode |
| **W4 Hierarchy** | Next | Setup/Playbook/System dataclasses |
| **BOS/CHoCH Detection** | Medium | Break of Structure / Change of Character |

---

## Quick Reference

```bash
# Validate
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
| **Forge Migration** | 2026-01-04 | IdeaCard -> Play (8 phases, 221 files) |
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
