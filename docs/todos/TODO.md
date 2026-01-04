# Active TODO

**Last Updated**: 2026-01-04
**Status**: ALL WORKSTREAMS COMPLETE (W1-W5)

---

## Current State

**Architecture Evolution (5 Workstreams) - ALL COMPLETE**:
- ✅ **W1: The Forge** (2026-01-04) - `src/forge/` with validation framework
- ✅ **W2: StateRationalizer** (2026-01-04) - Layer 2 transitions, derived state, conflicts
- ✅ **W3: Price Source Abstraction** (2026-01-04) - PriceSource protocol, BacktestPriceSource
- ✅ **W4: Trading Hierarchy** (2026-01-04) - Setup/Play/Playbook/System complete
- ✅ **W5: Live/Demo Stubs** (2026-01-04) - DemoPriceSource, LivePriceSource stubs

**Prior Work Complete:**
- Forge Migration (2026-01-04) - IdeaCard -> Play rename (8 phases, 221 files)
- Mega-file refactoring (2026-01-03) - Phases 1-3 done
- Incremental State Architecture (2026-01-03)
- 1m Evaluation Loop (2026-01-02)
- Market Structure Stages 0-7 (2026-01-01)
- 72 bugs fixed across P0-P3

**Validation Status**:
- 80 tools registered, 23 categories
- 17/17 Plays normalize (V_100+ blocks format, V_300+ hierarchy)
- 42/42 indicators pass audit
- 6 structures in STRUCTURE_REGISTRY
- All smoke tests pass

**New APIs**:
```python
# Backtest
from src.backtest import Play, load_play, create_engine_from_play
from src.backtest.rationalization import StateRationalizer, RationalizedState

# Trading Hierarchy
from src.forge import (
    Setup, load_setup, list_setups,
    Playbook, load_playbook, list_playbooks,
    System, load_system, list_systems,
)
```

---

## Trading Hierarchy (W4 Complete)

**Full Hierarchy Operational**:
```
System (btc_trend_v1)
└── Playbook (trend_following)
    ├── Play (T_001_ema_crossover)
    └── Play (T_002_multi_indicator_momentum)
        └── Setup (rsi_oversold)  ← DSL: `setup: rsi_oversold`
```

**Config Locations**:
| Level | Directory | Example |
|-------|-----------|---------|
| Setup | `configs/setups/` | rsi_oversold.yml |
| Play | `configs/plays/` | T_001_ema_crossover.yml |
| Playbook | `configs/playbooks/` | trend_following.yml |
| System | `configs/systems/` | btc_trend_v1.yml |

**Validation Plays**:
- V_300_setup_basic.yml - Setup reference
- V_301_setup_composition.yml - Multiple setups
- V_400_playbook_basic.yml - Playbook loading

---

## Next Steps

| Feature | Priority | Description |
|---------|----------|-------------|
| **W5 Full Implementation** | Future | WebSocket + live engine mode |
| **BOS/CHoCH Detection** | Medium | Break of Structure / Change of Character |
| **Forge CLI Menu** | Medium | Interactive forge workflow |
| **Playbook Runner** | Medium | Run all plays in a playbook |

---

## Quick Reference

```bash
# Validate
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup

# Full smoke
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full

# Trading Hierarchy
python -c "from src.forge import list_setups, list_playbooks, list_systems; print(list_setups(), list_playbooks(), list_systems())"
```

---

## Completed Work

| Phase | Date | Notes |
|-------|------|-------|
| **W4 Trading Hierarchy** | 2026-01-04 | Setup/Playbook/System complete |
| **W3 Price Source** | 2026-01-04 | PriceSource protocol |
| **W2 StateRationalizer** | 2026-01-04 | Layer 2 complete |
| **W1 Forge** | 2026-01-04 | Forge framework |
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
