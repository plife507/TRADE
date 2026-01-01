# Architecture Review — Intraday Adaptive Trading System

**STATUS:** DESIGN REVIEW  
**PURPOSE:** Evaluate brainstorm summary against current TRADE architecture  
**DATE:** December 18, 2025

---

## Executive Summary

This document reviews the proposed "Intraday Adaptive Trading System" architecture against the current TRADE codebase. The review identifies alignment points, integration opportunities, missing components, and implementation challenges.

**Overall Assessment:** The proposed architecture is **highly compatible** with TRADE's existing foundation, with clear extension points and minimal conflicts. The separation of concerns (Feature Layer → Strategy Layer → Position Management → Risk Governor → Arbitration) maps naturally to existing components.

---

## Architecture Alignment Analysis

### ✅ Strong Alignment Points

#### 1. Runtime Snapshot Foundation

**Proposed:** Immutable snapshot built on closed candles, multi-TF aligned arrays, contains OHLCV + indicators + market structure + magnet features.

**Current State:**
- `RuntimeSnapshotView` provides O(1) array-backed snapshot (no materialization)
- Built on closed candles only (TradingView-style MTF)
- Multi-TF support via `TFContext` (exec/htf/mtf roles)
- Feature access via `get_feature(tf_role, indicator_key, offset)`
- History access via index offset (`prev_ema_fast(1)`, `bars_exec_low(20)`)

**Gap:** Market structure and magnet features not yet implemented.

**Verdict:** ✅ **Fully compatible.** Snapshot architecture is ready; needs feature extensions.

---

#### 2. Feature Layer (Data Eye)

**Proposed:** Produces aligned arrays (indicators, structure, magnets, regime metrics). No decisions, no trading logic.

**Current State:**
- `FeatureFrameBuilder` computes indicators outside hot loop (vectorized)
- `FeatureSpec` declares required indicators per TF
- Indicator registry with 42+ indicators validated
- Metadata system tracks indicator provenance (`feature_spec_id`)

**Gap:** 
- Market structure features (trend, pivots, BOS/CHOCH) not implemented
- Magnet proxies (POC, S/R, liquidity pools) not implemented
- Regime metrics (volatility, chop, instability) not implemented

**Verdict:** ✅ **Extension path clear.** Feature layer is production-ready; needs new feature types.

---

#### 3. Strategy Layer ("Eyes" on Data)

**Proposed:** Multiple strategies run in parallel, each maintains scenario state, emits intents (not orders).

**Current State:**
- `BaseStrategy` interface: `generate_signal(snapshot, params) -> Optional[Signal]`
- Strategy registry supports multiple strategies
- `Signal` object contains: `symbol`, `direction`, `size_usd`, `strategy`, `confidence`, `metadata`
- Backtest engine supports single strategy per run (current limitation)

**Gap:**
- No parallel strategy execution (single strategy per backtest run)
- No scenario state management (strategies are stateless functions)
- No intent abstraction (signals are direct orders)

**Verdict:** ⚠️ **Needs extension.** Core interface compatible; requires parallel execution and state management.

---

#### 4. Position Management (Edge Concentrator)

**Proposed:** Fast invalidation, time stops, structure-based exits, BE moves, pyramiding winners (anti-martingale only).

**Current State:**
- `SimulatedExchange` handles position lifecycle
- `Position` object tracks: `size_usdt`, `entry_price`, `unrealized_pnl`, `stop_loss`, `take_profit`
- TP/SL checked within each bar (deterministic tie-break)
- No pyramiding logic (single position per symbol)
- No time stops
- No structure-based exits

**Gap:**
- No position management layer above exchange (exchange handles execution only)
- No add-to-winner logic
- No time-based stops
- No structure invalidation

**Verdict:** ⚠️ **New component needed.** Exchange handles execution; position management layer must be built.

---

#### 5. Risk Governor (Auto-Adaptation Engine)

**Proposed:** Hierarchy: Regime Gate (permission) → Performance Throttle (sizing). Controls trade permission, max size, strategy enable/disable, adds approval, daily stops.

**Current State:**
- `RiskManager` (live domain): Daily loss limits, position size caps, exposure limits, leverage caps
- `SimulatedRiskManager` (simulator domain): Position sizing based on risk profile
- `RiskPolicy` (simulator): Rule-based filtering (`check(signal, equity, available, exposure)`)
- No regime detection
- No performance-based throttling
- No strategy enable/disable

**Gap:**
- No regime gate (trend vs range vs chop detection)
- No performance throttle (drawdown-based scaling, loss streaks, cooldowns)
- No strategy-level enable/disable
- No dynamic risk scaling

**Verdict:** ⚠️ **Needs extension.** Risk infrastructure exists; needs regime detection and adaptive scaling.

---

#### 6. Arbitration Layer

**Proposed:** Resolves conflicts from parallel strategies, enforces net position per symbol, prevents overexposure, attributes virtual PnL per strategy.

**Current State:**
- No parallel strategy execution (single strategy per run)
- No conflict resolution
- No strategy attribution

**Gap:** Entire layer missing.

**Verdict:** ❌ **New component needed.** Requires parallel strategy execution first.

---

## Domain Mapping

### SIMULATOR Domain (`src/backtest/`)

| Proposed Component | Current Location | Status |
|-------------------|------------------|--------|
| Runtime Snapshot | `src/backtest/runtime/snapshot_view.py` | ✅ Production |
| Feature Layer | `src/backtest/features/` | ✅ Production (needs extensions) |
| Strategy Layer | `src/strategies/base.py` | ⚠️ Single-strategy only |
| Position Management | `src/backtest/sim/exchange.py` | ⚠️ Execution only |
| Risk Governor | `src/backtest/sim/risk_policy.py` | ⚠️ Basic rules only |
| Arbitration | — | ❌ Missing |

### LIVE Domain (`src/core/`, `src/exchanges/`)

| Proposed Component | Current Location | Status |
|-------------------|------------------|--------|
| Risk Manager | `src/core/risk_manager.py` | ✅ Production |
| Position Manager | `src/core/position_manager.py` | ✅ Production (tracking only) |
| Order Execution | `src/core/order_executor.py` | ✅ Production |

**Note:** Proposed architecture is primarily for **SIMULATOR domain** (backtesting). Live trading would need separate implementation.

---

## Implementation Challenges

### Challenge 1: Parallel Strategy Execution

**Current Limitation:** Backtest engine runs one strategy per run.

**Required Changes:**
- `BacktestEngine.run()` must accept `List[BaseStrategy]` instead of single strategy
- Each strategy maintains independent state (scenario phases)
- Strategies emit intents (not direct signals)
- Arbitration layer resolves conflicts before order submission

**Complexity:** Medium. Engine architecture supports this; requires refactoring.

---

### Challenge 2: Intent Abstraction

**Current:** `Signal` objects are direct order intents (LONG/SHORT/FLAT with size).

**Proposed:** Strategies emit higher-level intents:
- Enter long/short
- Add position
- Exit
- Move stop
- Partial take profit

**Required Changes:**
- New `Intent` type hierarchy
- Intent → Signal conversion layer
- Position management layer interprets intents

**Complexity:** Medium. Clean separation; requires new types.

---

### Challenge 3: Position Management Layer

**Current:** `SimulatedExchange` handles execution only. No position management above exchange.

**Proposed:** Position management layer handles:
- Fast invalidation (structure-based, time-based)
- BE moves
- Pyramiding (anti-martingale)
- Time stops

**Required Changes:**
- New `PositionManager` class (simulator domain)
- Integrates with `SimulatedExchange` for execution
- Maintains position state (adds, stops, exits)
- Interprets intents from strategies

**Complexity:** High. New component; must integrate with existing exchange.

---

### Challenge 4: Regime Detection

**Current:** No regime detection (trend vs range vs chop).

**Proposed:** Regime gate controls trade permission.

**Required Changes:**
- Regime detection features (volatility, trend strength, chop metrics)
- Regime classification (trend/range/chop)
- Regime gate in risk governor
- Regime-based strategy enable/disable

**Complexity:** Medium. Feature layer extension; classification logic needed.

---

### Challenge 5: Performance-Based Throttling

**Current:** Risk manager uses fixed limits (daily loss, position size, exposure).

**Proposed:** Dynamic scaling based on:
- Drawdown from high-watermark
- Loss streaks
- Cooldowns
- Risk scaling formula: `risk = regime_multiplier × performance_multiplier`

**Required Changes:**
- High-watermark tracking
- Drawdown calculation
- Loss streak tracking
- Cooldown timers
- Dynamic multiplier calculation

**Complexity:** Medium. Extends existing risk infrastructure.

---

### Challenge 6: Market Structure Features

**Current:** No market structure features (trend, pivots, BOS/CHOCH).

**Proposed:** Structure features in snapshot for position management decisions.

**Required Changes:**
- Market structure feature computation
- Structure state tracking (trend direction, pivot levels, BOS/CHOCH flags)
- Integration into `RuntimeSnapshotView`

**Complexity:** High. New feature category; requires definition of structure rules.

---

### Challenge 7: Magnet Features

**Current:** No magnet proxies (POC, S/R, liquidity pools).

**Proposed:** Magnet features for entry/exit decisions.

**Required Changes:**
- POC (Point of Control) calculation
- Support/resistance level detection
- Liquidity pool identification
- Distance-to-magnet metrics
- Integration into snapshot

**Complexity:** High. New feature category; requires market microstructure analysis.

---

## Integration Points

### Point 1: Feature Layer Extension

**Location:** `src/backtest/features/`

**Extension Path:**
1. Add market structure features to `FeatureSpec`
2. Implement structure computation in `FeatureFrameBuilder`
3. Add magnet features to `FeatureSpec`
4. Implement magnet computation
5. Add regime metrics to `FeatureSpec`
6. Implement regime computation

**Compatibility:** ✅ High. Feature system designed for extension.

---

### Point 2: Strategy State Management

**Location:** `src/strategies/base.py`

**Extension Path:**
1. Add state management to `BaseStrategy` (scenario phases)
2. Add `generate_intent()` method (returns `Intent` instead of `Signal`)
3. Maintain backward compatibility (keep `generate_signal()` for existing strategies)

**Compatibility:** ✅ High. Interface extension; backward compatible.

---

### Point 3: Position Management Integration

**Location:** `src/backtest/` (new module)

**Extension Path:**
1. Create `src/backtest/position_manager.py`
2. Integrate with `SimulatedExchange` (wraps exchange, manages position lifecycle)
3. Handle intents (add, exit, move stop, partial TP)
4. Maintain position state (adds, stops, exits)

**Compatibility:** ✅ High. New component; minimal changes to exchange.

---

### Point 4: Risk Governor Extension

**Location:** `src/backtest/sim/risk_policy.py` or new module

**Extension Path:**
1. Add regime detection to risk policy
2. Add performance tracking (high-watermark, drawdown, loss streaks)
3. Add dynamic multiplier calculation
4. Add strategy enable/disable logic

**Compatibility:** ✅ High. Extends existing risk infrastructure.

---

### Point 5: Arbitration Layer

**Location:** `src/backtest/` (new module)

**Extension Path:**
1. Create `src/backtest/arbitration.py`
2. Accept intents from multiple strategies
3. Resolve conflicts (net position per symbol)
4. Prevent overexposure
5. Attribute virtual PnL per strategy

**Compatibility:** ✅ High. New component; integrates with engine.

---

## Missing Components (Not in Current Codebase)

### 1. Intent Abstraction

**Required:**
- `Intent` base class
- `EnterIntent`, `AddIntent`, `ExitIntent`, `MoveStopIntent`, `PartialTPIntent`
- Intent → Signal conversion

**Status:** ❌ Missing

---

### 2. Position Management Layer (Simulator)

**Required:**
- Position state tracking (adds, stops, exits)
- Time-based stops
- Structure-based invalidation
- BE moves
- Pyramiding logic (anti-martingale)

**Status:** ❌ Missing

---

### 3. Regime Detection

**Required:**
- Volatility metrics
- Trend strength metrics
- Chop detection
- Regime classification (trend/range/chop)

**Status:** ❌ Missing

---

### 4. Magnet Features

**Required:**
- POC calculation
- S/R level detection
- Liquidity pool identification
- Distance-to-magnet metrics

**Status:** ❌ Missing

---

### 5. Market Structure Features

**Required:**
- Trend detection
- Pivot identification
- BOS/CHOCH detection
- Structure state tracking

**Status:** ❌ Missing

---

### 6. Performance Tracking

**Required:**
- High-watermark tracking
- Drawdown calculation
- Loss streak tracking
- Cooldown timers

**Status:** ⚠️ Partial (daily PnL exists, but no high-watermark/drawdown tracking)

---

### 7. Arbitration Layer

**Required:**
- Conflict resolution
- Net position enforcement
- Strategy attribution
- Virtual PnL tracking

**Status:** ❌ Missing

---

## Compatibility Assessment

### ✅ Fully Compatible

1. **Runtime Snapshot:** Architecture ready; needs feature extensions
2. **Feature Layer:** Extension path clear; system designed for new features
3. **Risk Infrastructure:** Base exists; needs regime detection and performance tracking
4. **Exchange Execution:** Execution model compatible; needs position management layer above

### ⚠️ Needs Extension

1. **Strategy Layer:** Interface compatible; needs parallel execution and state management
2. **Position Management:** Exchange handles execution; needs management layer
3. **Risk Governor:** Base exists; needs regime detection and adaptive scaling

### ❌ New Components Required

1. **Intent Abstraction:** New type system
2. **Arbitration Layer:** New component
3. **Market Structure Features:** New feature category
4. **Magnet Features:** New feature category
5. **Regime Detection:** New feature category

---

## Architectural Principles Alignment

### ✅ Aligned Principles

1. **Closed-Candle Only:** ✅ Matches current architecture
2. **TradingView-Style MTF:** ✅ Matches current architecture
3. **O(1) Snapshot Access:** ✅ Matches current architecture
4. **Deterministic Execution:** ✅ Matches current architecture
5. **Explicit Over Implicit:** ✅ Matches current architecture
6. **Domain Separation:** ✅ Matches current architecture (SIMULATOR vs LIVE)

### ⚠️ New Principles (Not Conflicting)

1. **Multiple Eyes (Separation of Concerns):** ✅ Compatible with current design
2. **Intent Abstraction:** ✅ Compatible (extends Signal concept)
3. **Anti-Martingale Pyramiding:** ✅ Compatible (new position management logic)
4. **Regime-Based Gating:** ✅ Compatible (extends risk infrastructure)

---

## Implementation Roadmap (High-Level)

### Phase 1: Foundation Extensions

1. **Market Structure Features**
   - Define structure feature spec
   - Implement structure computation
   - Integrate into snapshot

2. **Magnet Features**
   - Define magnet feature spec
   - Implement magnet computation
   - Integrate into snapshot

3. **Regime Detection**
   - Define regime metrics
   - Implement regime computation
   - Implement classification logic

**Estimated Effort:** 40-60 hours

---

### Phase 2: Strategy Layer Extension

1. **Intent Abstraction**
   - Define Intent type hierarchy
   - Add `generate_intent()` to BaseStrategy
   - Implement intent → signal conversion

2. **Strategy State Management**
   - Add state management to BaseStrategy
   - Implement scenario phase tracking
   - Maintain backward compatibility

**Estimated Effort:** 20-30 hours

---

### Phase 3: Position Management Layer

1. **Position Manager (Simulator)**
   - Create position management module
   - Implement add-to-winner logic (anti-martingale)
   - Implement time stops
   - Implement structure-based invalidation
   - Implement BE moves

2. **Integration with Exchange**
   - Wrap SimulatedExchange
   - Handle intent interpretation
   - Maintain position state

**Estimated Effort:** 40-60 hours

---

### Phase 4: Risk Governor Extension

1. **Regime Gate**
   - Integrate regime detection into risk policy
   - Implement regime-based trade permission
   - Implement strategy enable/disable

2. **Performance Throttle**
   - Implement high-watermark tracking
   - Implement drawdown calculation
   - Implement loss streak tracking
   - Implement cooldown timers
   - Implement dynamic multiplier calculation

**Estimated Effort:** 30-40 hours

---

### Phase 5: Parallel Strategy Execution

1. **Engine Extension**
   - Modify BacktestEngine to accept multiple strategies
   - Implement parallel strategy evaluation
   - Implement intent collection

2. **Arbitration Layer**
   - Create arbitration module
   - Implement conflict resolution
   - Implement net position enforcement
   - Implement strategy attribution

**Estimated Effort:** 40-60 hours

---

### Phase 6: Compounding + Extraction Model

1. **Trading Equity vs Vault Equity**
   - Implement equity separation
   - Implement extraction rules
   - Implement high-watermark-based extraction

**Estimated Effort:** 20-30 hours

---

**Total Estimated Effort:** 190-280 hours (4-7 weeks full-time)

---

## Risk Assessment

### Low Risk

- ✅ Feature layer extensions (proven extension path)
- ✅ Risk infrastructure extensions (base exists)
- ✅ Snapshot architecture (production-ready)

### Medium Risk

- ⚠️ Parallel strategy execution (engine refactoring)
- ⚠️ Position management layer (new component, integration complexity)
- ⚠️ Intent abstraction (new type system)

### High Risk

- ⚠️ Market structure features (definition complexity, edge cases)
- ⚠️ Magnet features (market microstructure analysis complexity)
- ⚠️ Regime detection (classification accuracy, false positives)

---

## Recommendations

### 1. Start with Feature Extensions

**Rationale:** Feature layer is proven and low-risk. Market structure and magnet features are foundational for position management decisions.

**Action:** Implement market structure features first, then magnet features, then regime detection.

---

### 2. Build Position Management Incrementally

**Rationale:** Position management is complex. Build incrementally:
1. Basic position state tracking
2. Time stops
3. Structure-based invalidation
4. BE moves
5. Pyramiding (last, most complex)

**Action:** Create position management module, integrate with exchange, add features incrementally.

---

### 3. Extend Risk Infrastructure Before Parallel Strategies

**Rationale:** Risk governor (regime gate + performance throttle) is needed before parallel strategies can be safely executed.

**Action:** Implement regime detection and performance tracking first, then enable parallel strategies.

---

### 4. Maintain Backward Compatibility

**Rationale:** Existing strategies and backtests must continue to work.

**Action:** 
- Keep `generate_signal()` for existing strategies
- Add `generate_intent()` as optional extension
- Default to single-strategy mode (opt-in parallel)

---

### 5. Validate Each Phase Before Proceeding

**Rationale:** Complex system; validate incrementally.

**Action:** 
- Use CLI smoke tests for each phase
- Validate feature computation (no repaint, correct semantics)
- Validate position management (correct adds, exits, stops)
- Validate risk governor (correct gating, throttling)

---

## Conclusion

The proposed "Intraday Adaptive Trading System" architecture is **highly compatible** with TRADE's existing foundation. The separation of concerns maps naturally to current components, with clear extension points for new functionality.

**Key Strengths:**
- Snapshot architecture ready for feature extensions
- Feature layer designed for new feature types
- Risk infrastructure extensible
- Domain separation maintained (SIMULATOR vs LIVE)

**Key Challenges:**
- Parallel strategy execution requires engine refactoring
- Position management layer is new component (integration complexity)
- Market structure and magnet features require definition and implementation
- Regime detection requires classification logic

**Recommendation:** ✅ **Proceed with implementation** following phased approach. Start with feature extensions (low risk, high value), then build position management incrementally, then extend risk infrastructure, then enable parallel strategies.

---

## Next Steps

1. **Create TODO document** for implementation phases
2. **Define market structure feature spec** (trend, pivots, BOS/CHOCH)
3. **Define magnet feature spec** (POC, S/R, liquidity pools)
4. **Define regime detection spec** (volatility, trend strength, chop metrics)
5. **Design intent abstraction** (Intent type hierarchy)
6. **Design position management API** (integration with SimulatedExchange)

---

**Document Status:** Ready for review. Not yet referenced in other files (as requested).

