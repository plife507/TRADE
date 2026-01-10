# Active TODO

**Last Updated**: 2026-01-10
**Status**: STRESS TESTING - Phase 3 (Comprehensive Structure Testing)

---

## Current Focus: Stress Testing

**Stress Test 3.0: Comprehensive Structure Coverage (2026-01-09 - ongoing)** - IN_PROGRESS:
- [x] Gate 0: Foundation (8/8 PASSED) - swing + rolling_window structures
  - BUG-016 found and fixed: rolling_window param naming consistency
- [ ] Gate 1: Swing Basics (20 plays) - NEXT
- [ ] Gate 3: Trend (16 plays)
- [ ] Gate 4: Rolling Window (16 plays)
- [ ] Gate 6: Fib Retracement (18 plays)
- [ ] Gate 8: DZ Slots (16 plays)
- [ ] Gate 9: DZ Aggregates (24 plays)
- [ ] Gate 11: Struct+Indicator (8 plays)
- [ ] Gate 12: Multi-Structure (6 plays)
- [ ] Gate 17: Ultimate (4 plays)

**Progress**: 8/136 plays PASSED (5.9%)
**Coverage**: 2/6 structure types tested (swing, rolling_window)

See: `docs/todos/STRESS_TEST_3_MASTER.md` for complete roadmap and bug tracking

---

## Recent Completed Work

**Documentation: Backtest Engine Concepts Guide (2026-01-10)** - COMPLETE:
- [x] Created `docs/guides/BACKTEST_ENGINE_CONCEPTS.md` - comprehensive conceptual guide
- [x] Covers: Time machine analogy, no lookahead rule, hot loop architecture
- [x] Deep dive: Data caching (FeedStore + RuntimeSnapshotView), O(1) lookups
- [x] Multi-timeframe forward-fill semantics with visual timeline diagrams
- [x] Window operators explained (holds_for, occurred_within, count_true)
- [x] Complete ASCII flow diagram (initialization → loop → post-processing)
- [x] Common pitfalls section (mark vs last price, warmup, window confusion, etc.)
- [x] Self-test Q&A boxes after each major section
- [x] Target audience: Developers new to the codebase

**DSL Bug Fixes & Enhancements (2026-01-07)** - COMPLETE:
- [x] P2-SIM-02: Fixed frozen Fill dataclass crash - added `close_ratio` param to `fill_exit()`
- [x] P2-005: Added `last_price` offset=1 support for crossover operators - `prev_last_price` tracking
- [x] P1-001: Aligned crossover semantics to TradingView standard (`prev <= rhs AND curr > rhs`)
- [x] P1-002: Implemented `anchor_tf` in window operators - offsets now scale by anchor_tf minutes
- [x] P2-004: Added duration bar ceiling check in `duration_to_bars()`

**Documentation & Cleanup (2026-01-07)** - COMPLETE:
- [x] Created `docs/guides/DSL_STRATEGY_PATTERNS.md` with 7 strategy patterns
- [x] Deleted all 41 validation YAMLs from `strategies/plays/_validation/`
- [x] Created `tests/validation/plays/` and `tests/validation/blocks/` directories

**ExitMode Enum & Strategy Testing (2026-01-06)** - COMPLETE:
- [x] Added `ExitMode` enum to `src/backtest/play.py` (sl_tp_only, signal, first_hit)
- [x] Added `exit_mode` field to `PositionPolicy` with validation in `execution_validation.py`
- [x] Updated all 34 validation plays with explicit `exit_mode` field
- [x] Verified Bybit math parity (17 formulas: PnL, margin, fees, funding, liquidation)
- [x] Created test plays: TF_001_eth_trend, TF_002_sol_long_only, TF_003_sol_short_only
- [x] SOL short strategy: EMA 200 filter + EMA 13/21 crossover = +19% (74 trades, 33.8% win rate)
- [x] Leverage/risk testing: 2% risk/3x leverage optimal; high risk % causes entry rejection

**Key Finding**: EMA 200 trend filter significantly outperformed EMA 50 for SOL shorts (Jan-Mar 2025).
High risk % with percent_equity sizing causes margin exhaustion and 100% entry rejection.

**Visualization System (2026-01-05)** - COMPLETE:
- [x] FastAPI backend (`src/viz/`) with 6 API endpoints
- [x] React + TypeScript frontend (`ui/`) with TradingView-style charts
- [x] Candlestick charts, equity curves, indicator overlays, trade markers
- [x] CLI command: `python trade_cli.py viz serve --port 8765`
- [x] Dev mode with separate API/UI servers for hot reload

**Validation Play Reorganization (2026-01-05)** - COMPLETE:
- [x] 26 validation plays with categorized prefix structure
- [x] **I_** (Indicators): I_001-I_010 (EMA, SMA, RSI, ATR, MACD, BBands, Stoch, ADX, SuperTrend, EMA_Cross)
- [x] **M_** (Multi-TF): M_001_mtf
- [x] **O_** (Operators): O_001-O_003 (between, all_any, holds_for)
- [x] **R_** (Risk): R_001-R_005 (ATR stop, RR ratio, fixed sizing, short-only, long-short)
- [x] **S_** (Structures): S_001-S_006 (swing, fib, trend, rolling, zone, derived_zone)
- [x] TEMPLATE.yml for new play creation

**Legacy Cleanup (2026-01-05)** - COMPLETE:
- [x] Removed `src/forge/playbooks/` module (no longer needed)
- [x] Removed `strategies/playbooks/`, `strategies/setups/` directories
- [x] Simplified to Block -> Play -> System hierarchy

**Simulator Order Parity (2026-01-05)** - COMPLETE:
- [x] Limit orders (buy/sell with time-in-force: GTC, IOC, FOK, PostOnly)
- [x] Stop market orders (trigger + market fill)
- [x] Stop limit orders (trigger + limit fill)
- [x] Reduce-only orders (partial position closes)
- [x] Order book management (cancel, cancel_all, amend)
- [x] Smoke test: `run_sim_orders_smoke()` in CLI suite

**Architecture Evolution (5 Workstreams) - ALL COMPLETE**:
- [x] **W1: The Forge** (2026-01-04) - `src/forge/` with validation framework
- [x] **W2: StateRationalizer** (2026-01-04) - Layer 2 transitions, derived state, conflicts
- [x] **W3: Price Source Abstraction** (2026-01-04) - PriceSource protocol, BacktestPriceSource
- [x] **W4: Trading Hierarchy** (2026-01-04) - Block/Play/System complete
- [x] **W5: Live/Demo Stubs** (2026-01-04) - DemoPriceSource, LivePriceSource stubs

**Validation Status**:
- 84 tools registered
- Validation plays relocated to `tests/validation/plays/`
- 43/43 indicators pass audit
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
  +-- Play (complete backtest strategy)
        +-- System (regime-weighted ensemble)
```

**Config Locations**:
| Level | Directory | Example |
|-------|-----------|---------|
| Block | `strategies/blocks/` | ema_cross.yml |
| Play | `strategies/plays/` | I_001_ema.yml |
| System | `strategies/systems/` | (future) |

**Validation Relocated**:
| Location | Purpose |
|----------|---------|
| `tests/validation/plays/` | Play validation tests |
| `tests/validation/blocks/` | Block validation tests |

---

## DSL Features (2026-01-07)

### Crossover Semantics (TradingView-aligned)
- `cross_above`: `prev_lhs <= rhs AND curr_lhs > rhs`
- `cross_below`: `prev_lhs >= rhs AND curr_lhs < rhs`
- Supports `last_price` with offset=1 via `prev_last_price`

### Window Operators with anchor_tf
- `holds_for`, `occurred_within`, `count_true` now scale by anchor_tf
- `bars: 3, anchor_tf: "1h"` = look back 180 minutes (3 * 60min)
- Duration operators: `holds_for_duration`, `occurred_within_duration`

### Strategy Patterns Guide
See: `docs/guides/DSL_STRATEGY_PATTERNS.md` for 7 documented patterns:
1. Momentum Confirmation (holds_for_duration)
2. Dip Buying / Mean Reversion (occurred_within_duration)
3. Multi-Timeframe Confirmation (anchor_tf)
4. Breakout with Volume Confirmation (count_true_duration)
5. Price Action Crossovers (last_price + cross_above/below)
6. Cooldown / Anti-Chop Filter (occurred_within)
7. Exhaustion Detection (count_true + trend)

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
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays
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
| **Stress Testing Phase 1** | 2026-01-09 | 5 gates passed, 3 bugs fixed (BUG-001/002/003) |
| **DSL Foundation Freeze** | 2026-01-08 | 259 synthetic tests, all operators frozen |
| **Cookbook Alignment** | 2026-01-08 | 7 phases, module extraction complete |
| **Tiered Testing** | 2026-01-08 | 137 tests across 6 tiers |
| **DSL Bug Fixes & Patterns** | 2026-01-07 | 5 bug fixes, DSL_STRATEGY_PATTERNS.md, validation relocated |
| **ExitMode & Strategy Testing** | 2026-01-06 | ExitMode enum, 34 plays updated, SOL short +19% |
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
