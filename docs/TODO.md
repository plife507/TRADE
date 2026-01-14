# Active TODO

**Last Updated**: 2026-01-12
**Status**: ALL VALIDATION PASSING + Manual Verification Complete

---

## Session Notes (2026-01-12)

### Stress Test Manual Verification - COMPLETE

Executed 21 stress tests with synthetic data and manually verified:

**Stress Tests**: 21/21 PASSING
| Test | Trades | Net PnL | Win Rate | Focus |
|------|--------|---------|----------|-------|
| S_01_btc_single_ema | 16 | +1,532.78 | 37.5% | Single indicator |
| S_02_btc_rsi_threshold | 0 | 0.00 | 0% | RSI threshold |
| S_03_btc_two_indicators | 77 | -1,832.11 | 52.0% | Multi-indicator |
| S_04_btc_basic_and | 12 | -826.19 | 33.3% | Boolean AND |
| S_05_btc_multi_output | 7 | -1,257.91 | 0% | Multi-output |
| S_06_btc_ema_crossover | 0 | 0.00 | 0% | EMA crossover |
| S_07_btc_macd_cross | 57 | -2,437.39 | 8.8% | MACD crossover |
| S_08_btc_or_conditions | 7 | -1,257.91 | 0% | Boolean OR |
| S_09_btc_arithmetic | 1 | -54.28 | 0% | Arithmetic DSL |
| S_10_btc_holds_for | 7 | +2,307.92 | 85.7% | Window operator |
| S_11_btc_occurred_within | 0 | 0.00 | 0% | Window operator |
| S_12_btc_duration_window | 99 | -1,001.09 | 39.4% | Duration windows |
| S_13_btc_multi_tf | 15 | +1,449.32 | 40.0% | Multi-timeframe |
| S_14_btc_swing_structure | 8 | +1,452.60 | 62.5% | Swing detection |
| S_15_btc_fibonacci | 58 | -988.46 | 17.2% | Fib levels |
| S_16_btc_complex_arithmetic | 6 | +1,960.50 | 100% | Complex DSL |
| S_17_btc_count_true | 1 | -217.52 | 0% | count_true |
| S_18_btc_derived_zones | 12 | -19.20 | 41.7% | Derived zones |
| S_19_btc_case_actions | 13 | +2,043.11 | 61.5% | Case actions |
| S_20_btc_multi_tf_structures | 39 | -3,202.77 | 17.9% | MTF structures |
| S_21_btc_full_complexity | 286 | -4,082.86 | 37.1% | Full complexity |

**Trade Math Verification** (S_16):
- Entry Size: price × qty = 9,499.99 ✓
- Gross PnL: (exit - entry) × qty = 378.03 ✓
- Fees: (entry_usdt + exit_usdt) × 5.5 bps = 10.66 ✓
- Net PnL: gross - fees = 367.38 ✓
- PnL %: net / entry_usdt × 100 = 3.867% ✓

**Indicator Verification**:
- EMA(20): Manual calculation matches pandas_ta ✓
- RSI(14): Values verified via pandas_ta ✓
- MACD(12,26,9): Output columns verified ✓

**Structure Detection Verification**:
- Swing Detection: Identifies highs at [5, 25, 45, 65, 85] in oscillating pattern ✓
- Derived Zones: Properly tracks states (NONE/ACTIVE/BROKEN) ✓

### Legacy Cleanup Phases 1-4 - COMPLETE

- [x] Phase 1: Typing modernization (8 files)
- [x] Phase 2: Remove unused aliases (3 locations)
- [x] Phase 3: Remove property aliases (5 properties)
- [x] Phase 4: Minor cleanups (2 files)
- [x] Git tags created for each phase

See: `docs/SESSION_HANDOFF.md` for complete details

---

## Session Notes (2026-01-10)

### Deprecation Refactor - ABANDONED

A "Legacy Code Removal & Modernization Plan" was attempted to remove deprecated type aliases and shims. The refactor was partially executed but caused widespread breakage across the codebase. After evaluation, the refactor was fully rewound via `git checkout HEAD -- .` to restore the working state.

**Lesson learned**: The deprecated aliases (e.g., `Candle`, type shims) are deeply embedded and their removal requires a more careful, phased approach than attempted.

### Validation Fixes Applied

- Fixed operator naming in validation plays: `gt` -> `>`, `eq` -> `==`
- Updated `V_104_operators.yml` and related files to use standard comparison operators

### Verification Status

- All 343 stress test plays: PASSING
- Tier 0 (Quick Check): PASSING
- Tier 1 (Normalization): PASSING
- Tier 2 (Unit Audits): PASSING
- Tier 3 (Error Cases): PASSING
- Tier 4 (Integration): PASSING

---

## Current Focus: Structure Module Production Ready

**Stress Test 3.0: Comprehensive Structure Coverage** - ✅ COMPLETE:
- [x] Gate 0: Foundation (8/8 PASSED) - swing + rolling_window structures
- [x] Gate 1: Swing Basics (20/20 PASSED) - high_level, low_level, idx, version
- [x] Gate 3: Trend (16/16 PASSED) - direction, strength, bars_in_trend
- [x] Gate 4: Rolling Window (16/16 PASSED) - max/min modes, size params
- [x] Gate 6: Fib Retracement (18/18 PASSED) - retracement levels
- [x] Gate 8: DZ Slots (16/16 PASSED) - zone0_* fields, ENUM state
- [x] Gate 9: DZ Aggregates (24/24 PASSED) - any_active, active_count, closest_*
- [x] Gate 11: Struct+Indicator (8/8 PASSED) - structure + indicator combinations
- [x] Gate 12: Multi-Structure (6/6 PASSED) - multiple structures combined
- [x] Gate 17: Ultimate (4/4 PASSED) - all 6 structures + complex boolean
- [x] Gate 13: HTF Structures (5/5 PASSED) - 1h/4h swing, 4h trend
- [x] Gate 14: MTF Confluence (6/6 PASSED) - exec+HTF alignment patterns
- [x] Gate 15: Zone Structure (10/10 PASSED) - demand/supply zones, state machine
- [x] Gate 15b: last_price + Zone (6/6 PASSED) - live trading parity, 1m granularity

**Final Progress**: 163/163 plays PASSED (100%)
**Coverage**: 6/6 structure types tested (swing, trend, fibonacci, zone, rolling_window, derived_zone)
**Live Parity**: last_price + zone interaction validated for live trading

**Bugs Fixed**: 4 bugs (BUG-016, BUG-017, BUG-018, BUG-019)
- BUG-016: derived_zone wrong dependency key (source: vs swing:)
- BUG-017: ENUM literal treated as feature reference
- BUG-018: Gate 17 wrong dependency keys after bulk fix
- BUG-019: Zone detector lowercase states (fixed to uppercase)

See: `docs/reviews/STRUCTURE_VERIFICATION_LOG.md` for complete results

---

## Stress Test 4.0: Order/Risk/Leverage - ✅ COMPLETE

**ROI-Based SL/TP Fix Validated** (2026-01-10):
- [x] Gate 00: Baseline (6/6 PASSED) - BTC/ETH/SOL long+short
- [x] Gate 01: Leverage (6/6 PASSED) - 1x, 2x, 3x validated
- [x] Gate 02: Risk/SL/TP (8/8 PASSED) - All ratios correct
- [x] Gate 03: Sizing (4/4 PASSED) - Position limits work
- [x] Gate 05: Exit Modes (6/6 PASSED) - sl_tp_only, signal, first_hit

**Key Validation**: ROI on margin is consistent across leverage levels:
- 1x leverage: 2% SL = 2% price move = -2% ROI ✅
- 2x leverage: 2% SL = 1% price move = -2% ROI ✅
- 3x leverage: 2% SL = 0.67% price move = -2% ROI ✅

See: `docs/reviews/STRESS_TEST_4_RESULTS.md` for complete results

---

## Stress Test 4.1: Edge Cases & Plumbing - ✅ COMPLETE

**Edge Gate 09: Execution Timeframe Expansion** (2026-01-10):
- [x] Added missing TFs: 3m, 30m, 2h, 6h, 12h to data layer
- [x] Updated `historical_data_store.py`, `backtest_play_tools.py`, `data_tools_sync.py`
- [x] Single-pair verification: BTC on each new TF (5/5 PASSED)
- [x] Multi-pair verification: ETH/SOL/AVAX/DOGE/LINK (5/5 PASSED)
- [x] 1m plumbing tests: last_price vs close code path verification (3/3 PASSED)

**1m Plumbing Verification**:
- `last_price`: From quote_provider (1m ticker) - snapshot_view.py:658
- `close`: From feed.close[target_idx] (candle array) - snapshot_view.py:724
- Verified different code paths even when values identical at tf=1m

**Final Progress**: 100/100 plays PASSED (edge_gate_09)
**TF Coverage**: Now supports 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, D
**NOTE**: 8h is NOT a valid Bybit interval - use 6h or 12h instead

---

## Stress Test 4.2: Multi-Pair TF Verification - ✅ COMPLETE

**Multi-Pair Data Fetch Verification** (2026-01-10):
- [x] S42_E_019_eth_30m.yml - ETH 30m (362 candles, 7 trades) ✅
- [x] S42_E_020_sol_3m.yml - SOL 3m (2,954 candles, 64 trades) ✅
- [x] S42_E_021_avax_2h.yml - AVAX 2h (146 candles, 1 trade) ✅
- [x] S42_E_022_doge_6h.yml - DOGE 6h (98 candles, 1 trade) ✅
- [x] S42_E_023_link_12h.yml - LINK 12h (86 candles, 1 trade) ✅

**Final Progress**: 50/50 plays PASSED (multi-pair TF verification)
**Data Fetch**: All 5 new TFs verified across 5 different crypto pairs
**Gap Fill**: Forward-fill semantics confirmed working correctly

---

## Recent Completed Work

**Stress Test Manual Verification (2026-01-12)** - COMPLETE:
- [x] Executed 21 stress tests with synthetic data
- [x] Manual trade math verification (S_16): entry size, gross PnL, fees, net PnL, PnL %
- [x] Indicator calculation verification: EMA, RSI, MACD against pandas_ta
- [x] Structure detection verification: swing highs/lows, derived zones

**Legacy Cleanup Phases 1-4 (2026-01-12)** - COMPLETE:
- [x] Phase 1: Typing modernization (8 files) - removed legacy typing imports
- [x] Phase 2: Removed unused aliases (3 locations) - TIMEFRAMES, registry param, parse_play_blocks
- [x] Phase 3: Removed property aliases (5 properties) - start_time, end_time, ltf_tf, bar_ltf, features_ltf
- [x] Phase 4: Minor cleanups (2 files) - os.path → pathlib, .format() → f-string
- [x] Created git tags for each phase

**Architecture Designs (2026-01-10)** - COMPLETE:
- [x] Created `docs/architecture/HYBRID_ENGINE_DESIGN.md` - complete backtest→live bridge design
  - TradingSnapshot Protocol, ExchangeAPI Protocol definitions
  - RingBuffer architecture for live multi-TF handling
  - Incremental indicator formulas (EMA, RSI, ATR, SMA, BBands)
  - Historical warmup → live transition flow diagram
  - Implementation roadmap (8 phases: A-H)
- [x] Created `docs/architecture/OI_FUNDING_STRATEGY_INTEGRATION.md` - OI/funding DSL integration
  - 90% complete infrastructure, only DSL wiring missing (~50-60 lines)
  - Strategic value analysis: funding as crowd positioning, OI as conviction measure
  - Complete strategy patterns with YAML examples
  - Implementation plan for DSL feature resolution

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
- 6 structures in STRUCTURE_REGISTRY (163/163 stress tests pass)
- All smoke tests pass (including sim_orders, structure, forge)
- Live trading parity validated (last_price + zone interaction)
- Trade math manually verified (PnL, fees, ROI)
- Indicator math verified against pandas_ta
- Structure detection verified (swing, derived zones)

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

# Stress tests (synthetic data)
python trade_cli.py backtest run --play S_01_btc_single_ema --dir tests/stress/plays --synthetic

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
| **Stress Test Verification** | 2026-01-12 | 21/21 pass, trade/indicator/structure math manually verified |
| **Legacy Cleanup Phases 1-4** | 2026-01-12 | 15 files cleaned, typing modernized, aliases removed |
| **Hybrid Engine Design** | 2026-01-10 | Complete backtest→live architecture, TradingSnapshot/ExchangeAPI protocols |
| **OI/Funding Integration** | 2026-01-10 | 90% complete, DSL wiring documented (~50 lines to implement) |
| **Stress Test 4.2 Multi-Pair** | 2026-01-10 | 50/50 pass, 5 TFs across 5 pairs verified |
| **Stress Test 4.1 Edge Cases** | 2026-01-10 | 100/100 pass, TF expansion (3m,30m,2h,6h,12h), 1m plumbing verified |
| **Stress Test 4.0 Order/Risk** | 2026-01-10 | 30/30 pass, ROI-based SL/TP validated |
| **Stress Testing Complete** | 2026-01-10 | 163/163 pass, 4 bugs fixed, live trading parity validated |
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
