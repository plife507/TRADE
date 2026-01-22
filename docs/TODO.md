# TRADE TODO

Active work tracking for the TRADE trading bot.

---

## Current Phase: Validation & Stabilization

### COMPLETED: Engine Migration (Phase 1)
- [x] Delete BacktestEngine class
- [x] Implement PlayEngine (src/engine/play_engine.py - 1,166 lines)
- [x] Create unified factory pattern (create_engine_from_play, PlayEngineFactory)
- [x] Migrate all callers to PlayEngine
- [x] Verify src/backtest/ contains only infrastructure (not an engine)

### COMPLETED: Validation Suite (Phase 1.5)
- [x] Create 125 validation plays across 14 tiers (T0-T13)
- [x] Add SyntheticConfig to Play class for auto-synthetic data
- [x] Update engine_factory to auto-create synthetic provider
- [x] Add recursive play loading for tier subdirectories
- [x] Fix all plays with required account fields (fee_model, min_trade_notional_usdt)
- [x] Verify validation plays use same code path as regular backtests

### P0: Validation Suite Testing
- [ ] Run full validation suite batch test (125 plays)
- [ ] Fix any failing plays
- [ ] Document coverage gaps

### P1: Smoke Test & Extended Testing
- [x] Run `--smoke full` and verify all passes (2026-01-22)
- [x] Verify artifact generation (equity curves, trade logs)
- [ ] Enable TRADE_SMOKE_INCLUDE_BACKTEST=1 for extended backtest smoke

---

## Backlog

### P2: DSL Enhancement (Phase 2 per roadmap)
- [ ] Build DSL validator
- [ ] Implement typed block layer
- [ ] Add block composition

### P3: Live Trading (Phase 3)
- [ ] Complete live adapter stubs
- [ ] Paper trading integration
- [ ] Position management

---

## Completed

### 2026-01-22: Comprehensive Validation Suite
- [x] Created 125 validation plays across 14 tiers:
  - T0: Smoke (1 play)
  - T1: Operators (12 plays) - >, <, >=, <=, ==, !=, between, near, in, cross
  - T2: Boolean (4 plays) - all, any, not, nested
  - T3: Arithmetic (6 plays) - add, subtract, multiply, divide, modulo
  - T4: Windows (6 plays) - holds_for, occurred_within, count_true
  - T5: Indicators (43 plays) - 27 single-output + 16 multi-output
  - T6: Structures (7 plays) - swing, trend, zone, fib, derived
  - T7: Price features (5 plays) - close, open, high, low, last_price
  - T8: Multi-TF (5 plays) - high_tf filter, cross_tf confluence
  - T9: Risk (11 plays) - stop loss, take profit, sizing types
  - T10: Position policy (6 plays) - long/short modes, exit modes
  - T11: Actions (8 plays) - entry/exit, case actions, alerts
  - T12: Combinations (5 plays) - mtf+indicators, structure+indicator
  - T13: Stress (6 plays) - many indicators, deep nesting, max features
- [x] Added SyntheticConfig dataclass to Play class
- [x] Auto-create synthetic provider in engine_factory from play.synthetic
- [x] Updated load_play() for recursive tier subdirectory search
- [x] Fixed all plays with fee_model and min_trade_notional_usdt

### 2026-01-22: Comprehensive Synthetic Market Conditions
- [x] Designed 34 market condition patterns for validation
- [x] Implemented all pattern generators in `synthetic_data.py`:
  - Trends: `trend_up_clean`, `trend_down_clean`, `trend_grinding`, `trend_parabolic`, `trend_exhaustion`, `trend_stairs`
  - Ranges: `range_tight`, `range_wide`, `range_ascending`, `range_descending`
  - Reversals: `reversal_v_bottom`, `reversal_v_top`, `reversal_double_bottom`, `reversal_double_top`
  - Breakouts: `breakout_clean`, `breakout_false`, `breakout_retest`
  - Volatility: `vol_squeeze_expand`, `vol_spike_recover`, `vol_spike_continue`, `vol_decay`
  - Liquidity: `liquidity_hunt_lows`, `liquidity_hunt_highs`, `choppy_whipsaw`, `accumulation`, `distribution`
  - Multi-TF: `mtf_aligned_bull`, `mtf_aligned_bear`, `mtf_pullback_bull`, `mtf_pullback_bear`
- [x] Added `PatternConfig` for customizing pattern parameters
- [x] Updated CLI `--synthetic-pattern` to accept all 34 patterns
- [x] Updated PLAY_DSL_COOKBOOK.md with synthetic data section
- [x] Updated validate.md and backtest-specialist.md agents

### 2026-01-22: Synthetic Data Mode Fix
- [x] Fixed TIMEFRAME_NOT_AVAILABLE error in synthetic mode
- [x] Updated `trade_cli.py:_handle_synthetic_backtest_run()` to collect Play timeframes
- [x] Added low_tf/med_tf/high_tf to required timeframe collection
- [x] Verified both data paths working:
  - Real (DuckDB): trend_follower +60.0%, 311 trades, 3.8% max DD
  - Synthetic: T_001_minimal -22.2%, 5805 trades, 22.2% max DD
  - Synthetic: trend_follower +0.2%, 1 trade, 0.1% max DD

### 2026-01-21: Position Sizing Enhancement
- [x] Investigated unrealistic backtest results (50,000%+ returns)
- [x] Added max_position_equity_pct (95% default) to cap positions
- [x] Added reserve_fee_buffer to reserve balance for entry/exit fees
- [x] Fixed SizingModel and SimulatedRiskManager with new caps
- [x] Fixed validation Plays with conservative settings:
  - T_001_minimal: 10% → 1% risk
  - trend_follower: 5x → 1x leverage, 20% → 2% risk
- [x] Verified realistic results: +88% (2yr), +60% (1yr)

### 2026-01-21: Engine Migration Verification
- [x] Verified BacktestEngine is deleted (src/backtest/engine.py = re-exports only)
- [x] Verified PlayEngine is fully implemented (1,166 lines)
- [x] Verified all engine_*.py files in src/backtest/ are infrastructure
- [x] Updated SESSION_HANDOFF.md with actual state
- [x] Updated PROJECT_STATUS.md
- [x] Updated TODO.md

### 2026-01-17: Validation Infrastructure
- [x] Fixed Play directory paths (strategies/plays/ → tests/*/plays/)
- [x] Created T_001_minimal.yml smoke test Play
- [x] Created V_STRUCT_001-004 structure validation Plays
- [x] Verified --smoke backtest passes with new Plays
- [x] Engine verified: preflight, data loading, execution, artifact generation

### 2026-01-17: Agent Configuration Update
- [x] Updated all agents with correct validation mapping
- [x] Removed deprecated paths (strategies/plays/, docs/todos/)
- [x] Updated structure count to 7
- [x] Updated timeframe syntax in templates
