# Active TODO

**Last Updated**: 2026-01-05
**Status**: VISUALIZATION SYSTEM COMPLETE

---

## Current State

**Visualization System (2026-01-05)** - COMPLETE:
- ✅ FastAPI backend (`src/viz/`) with 6 API endpoints
- ✅ React + TypeScript frontend (`ui/`) with TradingView-style charts
- ✅ Candlestick charts, equity curves, indicator overlays, trade markers
- ✅ CLI command: `python trade_cli.py viz serve --port 8765`
- ✅ Dev mode with separate API/UI servers for hot reload

**Validation Play Reorganization (2026-01-05)** - COMPLETE:
- ✅ 26 validation plays with categorized prefix structure
- ✅ **I_** (Indicators): I_001-I_010 (EMA, SMA, RSI, ATR, MACD, BBands, Stoch, ADX, SuperTrend, EMA_Cross)
- ✅ **M_** (Multi-TF): M_001_mtf
- ✅ **O_** (Operators): O_001-O_003 (between, all_any, holds_for)
- ✅ **R_** (Risk): R_001-R_005 (ATR stop, RR ratio, fixed sizing, short-only, long-short)
- ✅ **S_** (Structures): S_001-S_006 (swing, fib, trend, rolling, zone, derived_zone)
- ✅ TEMPLATE.yml for new play creation

**Legacy Cleanup (2026-01-05)** - COMPLETE:
- ✅ Removed `src/forge/playbooks/` module (no longer needed)
- ✅ Removed `configs/playbooks/`, `configs/setups/` directories
- ✅ Simplified to Block → Play → System hierarchy

**Simulator Order Parity (2026-01-05)** - COMPLETE:
- ✅ Limit orders (buy/sell with time-in-force: GTC, IOC, FOK, PostOnly)
- ✅ Stop market orders (trigger + market fill)
- ✅ Stop limit orders (trigger + limit fill)
- ✅ Reduce-only orders (partial position closes)
- ✅ Order book management (cancel, cancel_all, amend)
- ✅ Smoke test: `run_sim_orders_smoke()` in CLI suite

**Architecture Evolution (5 Workstreams) - ALL COMPLETE**:
- ✅ **W1: The Forge** (2026-01-04) - `src/forge/` with validation framework
- ✅ **W2: StateRationalizer** (2026-01-04) - Layer 2 transitions, derived state, conflicts
- ✅ **W3: Price Source Abstraction** (2026-01-04) - PriceSource protocol, BacktestPriceSource
- ✅ **W4: Trading Hierarchy** (2026-01-04) - Block/Play/System complete
- ✅ **W5: Live/Demo Stubs** (2026-01-04) - DemoPriceSource, LivePriceSource stubs

**Validation Status**:
- 84 tools registered
- 26 validation plays (I_, M_, O_, R_, S_ prefixes)
- 42/42 indicators pass audit
- 6 structures in STRUCTURE_REGISTRY
- All smoke tests pass (including sim_orders, structure, forge)

**New APIs**:
```python
# Backtest
from src.backtest import Play, load_play, create_engine_from_play
from src.backtest.rationalization import StateRationalizer, RationalizedState

# Visualization
# python trade_cli.py viz serve --port 8765
# Then visit http://localhost:8765

# Forge
from src.forge import Block, load_block, System, load_system
```

---

## Trading Hierarchy (Simplified)

```
Block (reusable condition)
  └── Play (complete backtest strategy)
        └── System (regime-weighted ensemble)
```

**Config Locations**:
| Level | Directory | Example |
|-------|-----------|---------|
| Block | `configs/blocks/` | ema_cross.yml |
| Play | `configs/plays/` | I_001_ema.yml |
| System | `configs/systems/` | (future) |

**Validation Play Prefixes**:
| Prefix | Purpose | Count |
|--------|---------|-------|
| I_ | Individual indicators | 10 |
| M_ | Multi-timeframe | 1 |
| O_ | Operators/DSL | 3 |
| R_ | Risk/sizing | 5 |
| S_ | Structures | 6 |

---

## Next Steps

| Feature | Priority | Description |
|---------|----------|-------------|
| **ICT Market Structure** | **P1** | See [ICT_MARKET_STRUCTURE.md](ICT_MARKET_STRUCTURE.md) |
| **Visualization Primitives** | P2 | Zone boxes, Fib levels, market structure overlays |
| **W5 Full Implementation** | Future | WebSocket + live engine mode |
| **Multi-Symbol Backtests** | Future | Run multiple symbols in single backtest |

### ICT/SMC Implementation (2026-01-05)

New structure types planned for ICT (Inner Circle Trader) concepts:

| Structure | Description | Phase |
|-----------|-------------|-------|
| `market_structure` | BOS/CHoCH detection | P2 (P1 priority) |
| `order_block` | Last opposing candle before impulse | P3 |
| `fair_value_gap` | 3-candle imbalance pattern | P4 |
| `liquidity_zone` | Equal highs/lows (BSL/SSL) | P5 |

**Full plan**: [ICT_MARKET_STRUCTURE.md](ICT_MARKET_STRUCTURE.md)

---

## Quick Reference

```bash
# Visualization
python trade_cli.py viz serve                    # Start viz server on :8765
python trade_cli.py viz serve --port 3000        # Custom port
python trade_cli.py viz serve --reload           # Dev mode with auto-reload

# Validate
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation
python trade_cli.py backtest audit-toolkit
python trade_cli.py backtest audit-rollup

# Forge verification (smoke test)
python trade_cli.py --smoke forge

# Simulator order type smoke test
python -c "from src.cli.smoke_tests import run_sim_orders_smoke; run_sim_orders_smoke()"

# Full smoke
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full
```

---

## Completed Work

| Phase | Date | Notes |
|-------|------|-------|
| **Visualization System** | 2026-01-05 | FastAPI + React, TradingView-style charts |
| **Validation Reorganization** | 2026-01-05 | 26 plays with I_/M_/O_/R_/S_ prefixes |
| **Legacy Cleanup** | 2026-01-05 | Removed playbooks, setups, simplified hierarchy |
| **Simulator Order Parity** | 2026-01-05 | Limit/stop orders, order book, reduce-only |
| **Stress Test Baseline** | 2026-01-04 | 8-step suite, playbook runner, synthetic data |
| **W4 Trading Hierarchy** | 2026-01-04 | Block/Play/System complete |
| **W3 Price Source** | 2026-01-04 | PriceSource protocol |
| **W2 StateRationalizer** | 2026-01-04 | Layer 2 complete |
| **W1 Forge** | 2026-01-04 | Forge framework |
| **Forge Migration** | 2026-01-04 | IdeaCard -> Play (8 phases, 221 files) |
| Legacy Code Cleanup | 2026-01-04 | Removed signal_rules, CLI renamed (--play, play-normalize) |
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
