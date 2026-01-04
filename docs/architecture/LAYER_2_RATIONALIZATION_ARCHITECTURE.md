# Layer 2: State Rationalization Architecture

> **Version**: 1.0.0
> **Date**: 2026-01-04
> **Status**: Design Complete - Implementation Pending

---

## Executive Summary

This document defines a **three-layer architecture** for the TRADE backtesting and live trading engine:

| Layer | Name | Responsibility |
|-------|------|----------------|
| **Layer 1** | Structure Detectors | Individual state machines (swing, zone, trend) |
| **Layer 2** | StateRationalizer | Cross-structure logic, transitions, derived state |
| **Layer 3** | DSL Evaluator | Signal generation from rationalized state |

The **StateRationalizer** is the key architectural addition. It provides:
- **Transition Detection**: What changed this bar vs previous
- **Derived State**: Confluence scores, regime classification, alignment
- **Conflict Resolution**: When signals from different sources disagree
- **Unified Debugging**: Single point to inspect all state changes

---

## Architecture Overview

```
+---------------------------------------------------------------------------------+
|                           ENGINE HOT LOOP (PER BAR)                             |
+---------------------------------------------------------------------------------+
|                                                                                 |
|  PRICE SOURCE                                                                   |
|  +--------------------+  +--------------------+  +--------------------+          |
|  | SeedDataSource     |  | BacktestSource     |  | WebSocketSource    |          |
|  | (Math validation)  |  | (DuckDB 1m arrays) |  | (Live/Demo WS)     |          |
|  +--------------------+  +--------------------+  +--------------------+          |
|            |                      |                      |                      |
|            +----------------------+----------------------+                      |
|                                   |                                             |
|                                   v                                             |
|  +-----------------------------------------------------------------------+      |
|  |                      LAYER 1: INCREMENTAL DETECTORS                   |      |
|  |                                                                       |      |
|  |  +----------+  +----------+  +----------+  +---------------+          |      |
|  |  |  Swing   |  |  Trend   |  |   Zone   |  | Derived Zone  |   ...    |      |
|  |  | O(1)/bar |  | O(1)/bar |  | O(1)/bar |  |   O(1)/bar    |          |      |
|  |  +----------+  +----------+  +----------+  +---------------+          |      |
|  |       |              |            |               |                   |      |
|  |       +-------+------+------+-----+---------------+                   |      |
|  |               |                                                       |      |
|  |         MultiTFIncrementalState.update()                              |      |
|  +-----------------------------------------------------------------------+      |
|                                   |                                             |
|                                   v                                             |
|  +-----------------------------------------------------------------------+      |
|  |                   LAYER 2: STATE RATIONALIZER (NEW)                   |      |
|  |                                                                       |      |
|  |  +------------------+  +------------------+  +--------------------+   |      |
|  |  | TransitionMgr    |  | DerivedCompute   |  | ConflictResolver   |   |      |
|  |  | - detect changes |  | - confluence     |  | - priority rules   |   |      |
|  |  | - emit events    |  | - regime         |  | - veto handling    |   |      |
|  |  +------------------+  +------------------+  +--------------------+   |      |
|  |                               |                                       |      |
|  |         StateRationalizer.rationalize() -> RationalizedState         |      |
|  +-----------------------------------------------------------------------+      |
|                                   |                                             |
|                                   v                                             |
|  +-----------------------------------------------------------------------+      |
|  |                      LAYER 3: DSL EVALUATOR                           |      |
|  |                                                                       |      |
|  |  RuntimeSnapshotView.get_feature_value() <- RationalizedState        |      |
|  |                               |                                       |      |
|  |         StrategyBlocksExecutor.execute(blocks, snapshot)              |      |
|  +-----------------------------------------------------------------------+      |
|                                   |                                             |
|                                   v                                             |
|                            Signal / Intent                                      |
+---------------------------------------------------------------------------------+
```

---

## 1. Price Source Abstraction

### 1.1 The Problem

The engine needs to work in three modes with different price sources:

| Mode | Source | Update Model | Characteristics |
|------|--------|--------------|-----------------|
| **Backtest** | DuckDB 1m arrays | Pull: engine controls time | Deterministic, O(1) random access |
| **Demo** | WebSocket (demo API) | Push: real-time stream | Fake money, same API as live |
| **Live** | WebSocket (live API) | Push: real-time stream | Real money, high reliability |

### 1.2 PricePoint - Universal Price Container

```python
@dataclass(frozen=True)
class PricePoint:
    """Immutable point-in-time price snapshot."""
    ts_ms: int           # Epoch milliseconds
    mark: float          # Mark price (risk/liquidation)
    last: float          # Last trade price (order fills)
    high_1m: float       # 1m bar high (zone touch detection)
    low_1m: float        # 1m bar low (zone touch detection)
    open_1m: float       # 1m bar open
    close_1m: float      # 1m bar close
    volume_1m: float     # 1m bar volume
    source: str          # Provenance ("backtest_1m", "ws_ticker")
    is_stale: bool       # Staleness flag
    staleness_ms: int    # Ms since last update
```

### 1.3 PriceSource - Abstract Interface

```python
class PriceSource(ABC):
    """Abstract price source - same interface for all modes."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_current_price(self) -> PricePoint | None: ...

    @abstractmethod
    def get_price_at_timestamp(self, ts: datetime) -> PricePoint | None: ...

    @abstractmethod
    def step(self) -> PricePoint | None:
        """
        Advance to next price.
        - Backtest: Returns immediately with next bar
        - Live: Blocks until next price update
        """
        ...

    @property
    @abstractmethod
    def is_exhausted(self) -> bool:
        """
        - Backtest: True when past last bar
        - Live: Always False (runs until stopped)
        """
        ...
```

### 1.4 Backtest vs Live Stepping Model

**Backtest Mode** (Pull):
```python
for exec_idx in range(num_bars):
    prices_1m = price_source.get_1m_prices_for_exec_bar(exec_idx)
    for price in prices_1m:
        snapshot = build_snapshot(price)
        signal = strategy(snapshot)
        if signal: break
```

**Live Mode** (Push/Block):
```python
while not stopped:
    price = price_source.step()  # BLOCKS until price arrives
    accumulate_1m_prices(price)
    if is_exec_bar_close(price.timestamp):
        snapshot = build_snapshot(accumulated_prices)
        signal = strategy(snapshot)
        submit_order_if_signal(signal)
```

### 1.5 Key Insight: Same Strategy Logic

The strategy function signature is **identical** across all modes:
```python
def strategy(snapshot: RuntimeSnapshotView) -> Signal | None
```

Only the price source differs. This ensures backtest-live parity.

---

## 2. Layer 2: StateRationalizer

### 2.1 Why Layer 2 Is Needed

| Problem | Without Layer 2 | With Layer 2 |
|---------|-----------------|--------------|
| Cross-detector logic | Awkward DSL conditions | Clean derived values |
| Transition detection | Manual prev/curr comparison | Automatic event emission |
| Regime classification | Inline in blocks | Centralized, reusable |
| Conflict resolution | Implicit in block order | Explicit priority rules |
| Debugging | Per-detector logs | Unified state view |

### 2.2 Core Data Structures

```python
class TransitionType(IntEnum):
    """Types of state transitions detected."""
    NONE = 0
    SWING_HIGH_CONFIRMED = 1
    SWING_LOW_CONFIRMED = 2
    TREND_UP_STARTED = 3
    TREND_DOWN_STARTED = 4
    ZONE_ENTERED = 5
    ZONE_BROKEN = 6
    ZONE_TOUCHED = 7
    CONFLUENCE_CROSSED = 8
    REGIME_CHANGED = 9


@dataclass(frozen=True)
class Transition:
    """A state transition detected this bar."""
    type: TransitionType
    source_key: str      # e.g., "swing", "fib_zones"
    field: str           # e.g., "zone0_state"
    prev_value: Any
    curr_value: Any
    bar_idx: int


@dataclass
class RationalizedState:
    """Output of StateRationalizer.rationalize()."""
    bar_idx: int
    transitions: list[Transition]

    # Derived scalars
    confluence_score: float      # 0.0-1.0
    regime: str                  # "trending_bull", "ranging", etc.
    alignment_score: float       # -1.0 to 1.0

    # Conflict resolution
    resolved_direction: int      # 1=long, -1=short, 0=neutral
    resolution_reason: str
    conflicting_sources: list[str]

    # Debug
    raw_states: dict[str, dict[str, Any]]
```

### 2.3 StateRationalizer Class

```python
class StateRationalizer:
    """
    Layer 2: Rationalize state from multiple detectors.

    Runs AFTER all detectors update, BEFORE DSL evaluation.
    Performance: O(structures * outputs + rules) per bar.
    """

    def __init__(self, config: StateRationalizerConfig):
        self._config = config
        self._prev_states: dict[str, dict[str, Any]] = {}

    def rationalize(
        self,
        bar_idx: int,
        state: MultiTFIncrementalState,
        bar: BarData,
    ) -> RationalizedState:
        """
        Main entry point. Called each bar after detector updates.

        1. Collect current state from all detectors
        2. Detect transitions vs previous bar
        3. Compute derived values
        4. Resolve conflicts
        5. Return RationalizedState
        """
        current = self._collect_states(state)
        transitions = self._detect_transitions(bar_idx, current)
        derived = self._compute_derived(current, transitions, bar)
        resolved = self._resolve_conflicts(current, transitions)

        result = RationalizedState(
            bar_idx=bar_idx,
            transitions=transitions,
            confluence_score=derived["confluence_score"],
            regime=derived["regime"],
            # ... etc
        )

        self._prev_states = current
        return result
```

### 2.4 Engine Integration Point

```python
# In BacktestEngine.run() - after detector updates, before snapshot

for i in range(num_bars):
    # Layer 1: Update detectors
    if self._incremental_state:
        self._incremental_state.update_exec(bar_data)

    # Layer 2: Rationalize state (NEW)
    if self._rationalizer and self._incremental_state:
        self._rationalized = self._rationalizer.rationalize(
            bar_idx=i,
            state=self._incremental_state,
            bar=bar_data,
        )

    # Build snapshot (now includes rationalized state)
    snapshot = self._build_snapshot_view(i, rollups=rollups)

    # Layer 3: Evaluate DSL
    signal = strategy(snapshot)
```

---

## 3. IdeaCard Schema: `rationalization` Section

### 3.1 Overview

```yaml
meta:
  id: my_strategy
  version: 2

# ... existing sections ...

rationalization:
  derived: [...]        # Computed values from structures
  transitions: [...]    # State change detection rules
  regimes: [...]        # Meta-state classification
  resolution: {...}     # Conflict resolution policy
```

### 3.2 Derived Values

```yaml
rationalization:
  derived:
    # Arithmetic expression
    - id: zone_distance_pct
      type: float
      expr:
        op: mul
        lhs:
          op: div
          lhs:
            op: abs
            value: {op: sub, lhs: {ref: mark_price}, rhs: {ref: zones.zone0_mid}}
          rhs: {ref: mark_price}
        rhs: {literal: 100}

    # Categorical (enum) derivation
    - id: trend_alignment
      type: enum
      values: [ALIGNED_BULL, ALIGNED_BEAR, MIXED, NONE]
      expr:
        match:
          - when:
              all:
                - {ref: ema_fast, op: gt, rhs: {ref: ema_slow}}
                - {ref: htf_ema_fast, op: gt, rhs: {ref: htf_ema_slow}}
            then: ALIGNED_BULL
          # ... other cases
          - else: NONE
```

### 3.3 Transition Rules

```yaml
rationalization:
  transitions:
    # State change detection
    - id: zone_broken
      trigger:
        type: state_change
        ref: zones.zone0_state
        from: ACTIVE
        to: BROKEN
      emit: zone_0_broken

    # Threshold crossing
    - id: rsi_overbought
      trigger:
        type: crosses_above
        ref: rsi_14
        threshold: 70
      emit: rsi_entered_overbought

    # Compound trigger
    - id: breakout_with_volume
      trigger:
        type: compound
        all:
          - {type: crosses_above, ref: bar_close, threshold_ref: zones.zone0_high}
          - {type: crosses_above, ref: volume, threshold_ref: volume_sma_20}
      emit: confirmed_breakout
```

### 3.4 Regime Classification

```yaml
rationalization:
  regimes:
    - id: market_regime
      type: exclusive  # Only one active at a time
      categories:
        - name: TRENDING_BULL
          when:
            all:
              - {ref: derived.trend_alignment, op: eq, rhs: {literal: ALIGNED_BULL}}
              - {ref: adx_14, op: gt, rhs: {literal: 25}}
        - name: TRENDING_BEAR
          when:
            all:
              - {ref: derived.trend_alignment, op: eq, rhs: {literal: ALIGNED_BEAR}}
              - {ref: adx_14, op: gt, rhs: {literal: 25}}
        - name: RANGING
          when:
            all:
              - {ref: adx_14, op: lt, rhs: {literal: 20}}
        - name: UNDEFINED
          default: true
```

### 3.5 Conflict Resolution

```yaml
rationalization:
  resolution:
    mode: veto_first

    # Veto rules (block signals regardless of priority)
    vetoes:
      - name: no_entries_in_volatile
        blocks: [entry_long, entry_short]
        when:
          ref: regimes.market_regime
          op: eq
          rhs: {literal: VOLATILE}

    # Priority ordering
    priorities:
      - action: exit_all
        priority: 100
      - action: entry_long
        priority: 50
        conflicts_with: [entry_short]
      - action: entry_short
        priority: 50
        conflicts_with: [entry_long]
```

---

## 4. Using Rationalized State in DSL

### 4.1 Accessing Derived Values

```yaml
blocks:
  - id: entry
    cases:
      - when:
          all:
            - lhs: {feature_id: rationalize, field: confluence_score}
              op: gt
              rhs: {literal: 0.7}
            - lhs: {feature_id: rationalize, field: trend_alignment}
              op: eq
              rhs: {literal: ALIGNED_BULL}
        emit:
          - action: entry_long
```

### 4.2 Consuming Transition Events

```yaml
blocks:
  - id: breakout_entry
    cases:
      - when:
          all:
            - event: confirmed_breakout  # From transition emit
            - lhs: {feature_id: rationalize, field: regime}
              op: eq
              rhs: {literal: TRENDING_BULL}
        emit:
          - action: entry_long
```

### 4.3 Regime-Based Block Filtering

```yaml
blocks:
  - id: trend_entry
    # Entire block disabled if condition false
    enabled_when:
      ref: regimes.market_regime
      op: neq
      rhs: {literal: RANGING}
    cases:
      # ... only evaluated if enabled_when is true
```

---

## 5. Edge Cases and Defensive Design

### 5.1 Timing Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Detector A depends on B, B not updated | Topological sort on dependencies |
| HTF stale between closes | Wrap values in TimeframedValue with freshness |
| Rule A depends on Rule B output | Topological sort, fail on cycles |

### 5.2 State Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Zone created and broken same bar | Track intermediate transitions, expose both |
| Multiple zones break simultaneously | Return list of all broken zones |
| All structures invalid | Expose `structure_void=true`, guard in DSL |
| First bar (no prev state) | Explicit null state, `is_first_bar=true` |

### 5.3 Conflict Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Invalidate vs force_entry | Invalidation always wins (architectural) |
| Circular rule dependency | Detect at init, fail loud |
| Duplicate derived key | Detect at init, fail loud |

### 5.4 Live Trading Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Price slippage | Configurable max slippage, skip or recalculate |
| WebSocket reconnect | Fetch ground truth from REST, recovery_mode |
| External position close | Poll REST, detect divergence, reset context |

---

## 6. Implementation Roadmap

### Phase R1: Core Infrastructure
- [ ] `PricePoint` and `PriceSource` base classes
- [ ] `BacktestPriceSource` using existing FeedStore
- [ ] Refactor `BacktestEngine` to use `PriceSource`
- [ ] `MockPriceSource` for testing

### Phase R2: StateRationalizer Core
- [ ] `TransitionType`, `Transition`, `RationalizedState` types
- [ ] `StateRationalizer` with transition detection
- [ ] Engine integration point
- [ ] Snapshot access via `feature_id="rationalize"`

### Phase R3: Rule System
- [ ] YAML parser for `rationalization:` section
- [ ] `DerivedRule` expression evaluator
- [ ] `TransitionRule` matcher
- [ ] `ConflictRule` resolver

### Phase R4: IdeaCard Schema
- [ ] Schema validation for rationalization section
- [ ] Type inference for expressions
- [ ] Circular dependency detection
- [ ] Validation IdeaCards (V_130+)

### Phase R5: Live Integration
- [ ] `WebSocketPriceSource` with reconnection
- [ ] `LiveRunner` using price source abstraction
- [ ] REST fallback for state reconciliation
- [ ] Staleness detection and handling

### Phase R6: Agent Integration
- [ ] Proposal format for agent-generated rules
- [ ] Validation workflow with backtest comparison
- [ ] Version tracking for agent contributions

---

## 7. File Layout

```
src/
  backtest/
    rationalize/            # NEW
      __init__.py
      types.py              # Transition, RationalizedState
      rationalizer.py       # StateRationalizer
      rules.py              # DerivedRule, TransitionRule, ConflictRule
      parser.py             # YAML parsing for rationalization section
  prices/                   # NEW
    __init__.py
    price_source.py         # PriceSource ABC, PricePoint
    backtest_source.py      # BacktestPriceSource
    websocket_source.py     # WebSocketPriceSource
    mock_source.py          # MockPriceSource
  live/                     # NEW
    live_runner.py          # LiveRunner using WebSocketPriceSource

configs/idea_cards/_validation/
  V_130_rationalize_basic.yml
  V_131_rationalize_transitions.yml
  V_132_rationalize_regimes.yml
  V_133_rationalize_conflicts.yml
```

---

## 8. Backward Compatibility

**Existing IdeaCards work unchanged.** The `rationalization:` section is optional. Cards without it:
- Skip Layer 2 entirely
- Have `snapshot._rationalized = None`
- Cannot reference `feature_id: rationalize` (will fail validation)

Adoption is incremental - add `rationalization:` sections as needed.

---

## 9. Summary

The Layer 2 StateRationalizer provides:

| Capability | Before | After |
|------------|--------|-------|
| Transition detection | Manual | Automatic with events |
| Derived values | Not possible | First-class support |
| Regime classification | Inline in blocks | Centralized, reusable |
| Conflict resolution | Implicit | Explicit policy |
| Debugging | Per-detector | Unified state view |
| Live trading | Separate codebase | Same price interface |

The price source abstraction ensures:

| Capability | Before | After |
|------------|--------|-------|
| Backtest-live parity | Hope | Guaranteed (same strategy code) |
| Testing | Hard | MockPriceSource for unit tests |
| Mode switching | Rewrite | Config change only |

This architecture scales to support:
- Forecasting (ML model outputs as derived values)
- Agent consensus (multiple agents vote, rationalize resolves)
- Multi-strategy playbooks (regime-based strategy switching)
- Real-time live trading (WebSocket with REST fallback)

---

## 10. The Forge: Strategy Factory Development Environment

### 10.1 Purpose

The **Forge** (`src/forge/`) is where strategy components are **built and hardened** before being consumed by the backtest engine. Components must be mathematically proven before testing on market data.

```
STRATEGY FACTORY ARCHITECTURE (2026-01-04)
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  THE FORGE (src/forge/) - Component Development & Validation            │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                                                                    │ │
│  │  audits/                  # ALL validation audits (unified)        │ │
│  │  ├── indicators/          # Indicator validation (42/42 pass)     │ │
│  │  │   ├── toolkit_contract_audit.py                                │ │
│  │  │   ├── audit_math_parity.py                                     │ │
│  │  │   └── audit_in_memory_parity.py                                │ │
│  │  ├── structures/          # Structure validation (NEW)            │ │
│  │  │   └── structure_contract_audit.py                              │ │
│  │  ├── rollups/             # Rollup validation                     │ │
│  │  │   └── audit_rollup_parity.py                                   │ │
│  │  └── artifacts/           # Artifact validation                   │ │
│  │      └── artifact_parity_verifier.py                              │ │
│  │                                                                    │ │
│  │  detectors/               # WIP structure detectors               │ │
│  │  forecasting/             # WIP ML/forecasting models             │ │
│  │  rationalization/         # WIP derived state rules               │ │
│  │                                                                    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              │ proven components                        │
│                              ▼                                          │
│  BACKTEST ENGINE (src/backtest/) - Consumes Proven Components           │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ indicator_registry.py     # Production indicators                 │ │
│  │ incremental/detectors/    # Production structure detectors        │ │
│  │ rationalize/              # Production rationalization            │ │
│  │ engine.py                 # Runs strategies using proven parts    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

VALIDATION PIPELINE
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  STAGE 1: MATH PROOF (Seed Data)                                       │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Indicators: src/forge/audits/indicators/*                         │ │
│  │ Structures: src/forge/audits/structures/*                         │ │
│  │                                                                    │ │
│  │ - Controlled input sequences (seed=1337, deterministic)           │ │
│  │ - Known expected outputs                                           │ │
│  │ PROVES: "Given X, component outputs Y"                             │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  STAGE 2: MARKET PROOF (Historical Data - DuckDB)                      │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ BacktestSource                                                     │ │
│  │ - Real market conditions                                           │ │
│  │ - Edge cases from actual trading                                   │ │
│  │ - Validation IdeaCards (V_100+ in configs/idea_cards/_validation/) │ │
│  │ PROVES: "Works correctly on real markets"                          │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  STAGE 3: LIVE PROOF (Demo Trading)                                    │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ WebSocketSource (Demo API)                                         │ │
│  │ - Real-time execution                                              │ │
│  │ - Order handling, fills, latency                                   │ │
│  │ PROVES: "Works in live conditions"                                  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  PRODUCTION (Live Trading)                                              │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ WebSocketSource (Live API)                                         │ │
│  │ - Real money                                                        │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Migration Plan

The existing indicator audits in `src/backtest/audits/` will be **moved to** `src/forge/audits/indicators/`:

| Current Location | New Location | Status |
|------------------|--------------|--------|
| `src/backtest/audits/toolkit_contract_audit.py` | `src/forge/audits/indicators/` | Move |
| `src/backtest/audits/audit_math_parity.py` | `src/forge/audits/indicators/` | Move |
| `src/backtest/audits/audit_in_memory_parity.py` | `src/forge/audits/indicators/` | Move |
| `src/backtest/audits/audit_snapshot_plumbing_parity.py` | `src/forge/audits/snapshots/` | Move |
| `src/backtest/audits/audit_rollup_parity.py` | `src/forge/audits/rollups/` | Move |
| `src/backtest/audits/artifact_parity_verifier.py` | `src/forge/audits/artifacts/` | Move |

**Supporting Infrastructure (stays in backtest - production code):**
- `src/backtest/indicator_vendor.py` - Production pandas_ta wrapper
- `src/backtest/indicator_registry.py` - Production registry

### 10.3 Trading Hierarchy

The Forge uses a **trading-native naming hierarchy**:

| Level | Name | Trading Meaning | Contains |
|-------|------|-----------------|----------|
| **Setup** | Conditions that define opportunity | Reusable rule blocks, filters, entry/exit logic |
| **Play** | A specific trade idea to execute | Complete strategy (replaces "IdeaCard") |
| **Playbook** | Collection of plays for scenarios | Strategy collection with regime routing |
| **System** | Full trading operation | Multi-playbook deployment, risk, execution |

```
TRADING HIERARCHY
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  SETUP (atomic)           PLAY (strategy)         PLAYBOOK (collection) │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐   │
│  │ breakout_entry  │     │ trend_breakout  │     │ bull_market     │   │
│  │ trailing_stop   │ ──► │ - uses setups   │ ──► │ - play A        │   │
│  │ volume_filter   │     │ - adds sizing   │     │ - play B        │   │
│  │ regime_filter   │     │ - risk rules    │     │ - regime rules  │   │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘   │
│                                                           │             │
│                                                           ▼             │
│                                                  ┌─────────────────┐   │
│                                    SYSTEM        │ full_deployment │   │
│                                                  │ - playbook A    │   │
│                                                  │ - playbook B    │   │
│                                                  │ - global risk   │   │
│                                                  │ - execution     │   │
│                                                  └─────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.4 Forge Structure

```
src/forge/
├── CLAUDE.md                    # Forge-specific rules
├── runner.py                    # Standalone execution (no engine deps)
├── seed_loader.py               # Load seed data YAMLs
│
├── audits/                      # ALL validation audits (unified)
│   ├── __init__.py
│   ├── indicators/              # Indicator audits (moved from backtest/audits/)
│   │   ├── toolkit_contract_audit.py
│   │   ├── audit_math_parity.py
│   │   └── audit_in_memory_parity.py
│   ├── structures/              # Structure audits (NEW)
│   │   └── structure_contract_audit.py
│   ├── snapshots/               # Snapshot plumbing audits
│   │   └── audit_snapshot_plumbing_parity.py
│   ├── rollups/                 # Rollup audits
│   │   └── audit_rollup_parity.py
│   └── artifacts/               # Artifact audits
│       └── artifact_parity_verifier.py
│
├── detectors/                   # WIP market structure detectors
│   ├── __init__.py
│   └── experimental_*.py        # In-development detectors
│
├── forecasting/                 # WIP ML/forecasting models
│   ├── __init__.py
│   └── experimental_*.py        # In-development forecasters
│
├── rationalization/             # WIP rationalization rules
│   ├── __init__.py
│   └── experimental_*.py        # In-development rules
│
├── setups/                      # WIP reusable rule blocks
│   ├── entries/                 # Entry condition setups
│   ├── exits/                   # Exit condition setups
│   └── filters/                 # Filter setups
│
├── plays/                       # WIP complete strategies
│   └── experimental_*.yml       # In-development plays
│
├── playbooks/                   # WIP strategy collections
│   └── experimental_*.yml       # In-development playbooks
│
├── systems/                     # WIP full deployments
│   └── experimental_*.yml       # In-development systems
│
├── notebooks/                   # Jupyter for exploration
│   └── *.ipynb
│
└── results/                     # Output from forge runs

configs/
├── setups/                      # PROVEN reusable setups
│   ├── entries/
│   ├── exits/
│   └── filters/
│
├── plays/                       # PROVEN strategies (was idea_cards/)
│   ├── _validation/             # V_100+ validation plays
│   └── production/              # Production plays
│
├── playbooks/                   # PROVEN strategy collections
│
├── systems/                     # PROVEN full deployments
│
├── risk_profiles/               # Risk configurations
│   ├── conservative.yml
│   ├── moderate.yml
│   └── aggressive.yml
│
├── symbol_sets/                 # Asset groupings
│   ├── btc_majors.yml
│   └── alt_momentum.yml
│
├── regimes/                     # Market state definitions
│   ├── trending.yml
│   ├── ranging.yml
│   └── volatile.yml
│
├── schedules/                   # Trading session rules
│   └── avoid_news.yml
│
├── execution/                   # Order execution profiles
│   ├── passive.yml
│   └── aggressive.yml
│
└── seed_data/                   # Deterministic test data
    ├── structures/
    ├── rationalization/
    └── forecasting/
```

### 10.5 Seed Data Format

```yaml
# configs/seed_data/structures/swing_basic.yml
name: swing_high_low_detection
description: "Verify swing detection with left=2, right=2"
component_type: structure
component_id: swing

params:
  left: 2
  right: 2

bars:
  - {o: 100, h: 102, l: 99, c: 101}   # bar 0
  - {o: 101, h: 105, l: 100, c: 104}  # bar 1
  - {o: 104, h: 110, l: 103, c: 108}  # bar 2 - swing high forms (110)
  - {o: 108, h: 109, l: 102, c: 103}  # bar 3
  - {o: 103, h: 104, l: 95, c: 96}    # bar 4 - swing high confirmed, swing low forms
  - {o: 96, h: 100, l: 94, c: 99}     # bar 5

expected:
  - bar: 4
    outputs:
      high_level: 110
      high_idx: 2
      version: 1
  - bar: 6
    outputs:
      low_level: 95
      low_idx: 4
      version: 2
```

### 10.6 Structure Audit (Parallel to Indicator Audit)

```python
# src/forge/audits/structures/structure_contract_audit.py
"""
Structure validation audit - parallel to toolkit_contract_audit.py

Validates all registered structures in STRUCTURE_REGISTRY against seed data.
Uses same deterministic data pattern (seed=1337).
"""

from src.backtest.incremental.registry import STRUCTURE_REGISTRY

@dataclass
class StructureAuditResult:
    structure_type: str
    seed_file: str
    bars_processed: int
    expected_outputs: int
    matched: int
    mismatches: list[dict]
    passed: bool

def run_structure_contract_audit(seed_dir: str = "configs/seed_data/structures/") -> list[StructureAuditResult]:
    """
    Run all structure seed data validations.
    Returns list of results per structure type.
    """
    results = []
    for struct_type in STRUCTURE_REGISTRY:
        seed_files = glob(f"{seed_dir}/{struct_type}_*.yml")
        for seed_file in seed_files:
            result = validate_structure_against_seed(struct_type, seed_file)
            results.append(result)
    return results
```

### 10.7 Forge Runner

```python
# src/forge/runner.py
class ForgeRunner:
    """
    Run components in isolation against seed data.
    No engine, no FeedStore, minimal dependencies.
    """

    def run_structure(self, detector_class, seed_file: str) -> ValidationResult:
        seed = load_seed_data(seed_file)
        detector = detector_class(params=seed.params, deps={})

        results = []
        for i, bar in enumerate(seed.bars):
            bar_data = BarData.from_seed(bar)
            detector.update(i, bar_data)

            state = detector.get_all_values()
            results.append({"bar": i, "state": state})

            # Visual feedback during development
            print(f"Bar {i}: {state}")

        # Compare to expected
        return self.validate(results, seed.expected)

    def run_forecaster(self, forecaster_class, seed_file: str) -> ValidationResult:
        seed = load_seed_data(seed_file)
        forecaster = forecaster_class(params=seed.params)

        # Feed historical context
        for bar in seed.context_bars:
            forecaster.observe(bar)

        # Generate prediction
        prediction = forecaster.predict()
        return self.validate(prediction, seed.expected)
```

### 10.8 CLI Commands

```bash
# Run structure detector against seed data
python trade_cli.py forge structure swing --seed swing_basic.yml

# Run all structure audits
python trade_cli.py forge audit-structures

# Run all indicator audits
python trade_cli.py forge audit-indicators

# Interactive development mode
python trade_cli.py forge interactive swing

# List available seed data
python trade_cli.py forge seeds

# Validate all seed data for a component
python trade_cli.py forge validate-all swing
```

### 10.9 Promotion Path

| Stage | Location | Criteria |
|-------|----------|----------|
| **Forge (WIP)** | `src/forge/*/` | Under development |
| **Math Proven** | `src/forge/` + passing seed tests | All seed data passes |
| **Registered** | `src/backtest/` or `configs/` | Moved to production location |
| **Market Tested** | + `configs/plays/_validation/V_*.yml` | Validation plays pass |
| **Production** | Used in real plays/playbooks | Demo-proven, approved |

**Promotion by component type:**

| Component | Forge Location | Production Location |
|-----------|----------------|---------------------|
| Detectors | `src/forge/detectors/` | `src/backtest/incremental/detectors/` |
| Forecasting | `src/forge/forecasting/` | `src/backtest/forecasting/` |
| Setups | `src/forge/setups/` | `configs/setups/` |
| Plays | `src/forge/plays/` | `configs/plays/` |
| Playbooks | `src/forge/playbooks/` | `configs/playbooks/` |
| Systems | `src/forge/systems/` | `configs/systems/` |

### 10.10 Separation of Concerns

```
THE FORGE (src/forge/)                    BACKTEST ENGINE (src/backtest/)
Development & Validation                   Production Consumption
┌─────────────────────────────┐           ┌─────────────────────────────┐
│                             │           │                             │
│ audits/                     │           │ indicator_registry.py       │
│   indicators/               │ ─proves─► │ indicator_vendor.py         │
│   structures/               │           │                             │
│   rollups/                  │           │ incremental/                │
│   artifacts/                │ ─proves─► │   registry.py               │
│                             │           │   detectors/*.py            │
│ detectors/                  │           │                             │
│   experimental_*.py         │ ─promotes─► (registered detectors)      │
│                             │           │                             │
│ forecasting/                │           │ rationalize/                │
│   experimental_*.py         │ ─promotes─► (future)                    │
│                             │           │                             │
│ configs/seed_data/          │           │ engine.py                   │
│   structures/*.yml          │           │   (runs proven components)  │
│   forecasting/*.yml         │           │                             │
└─────────────────────────────┘           └─────────────────────────────┘
```

The Forge **develops and validates** components. Once proven, they're promoted to `src/backtest/` for production use:
- Deterministic inputs (reproducible testing)
- Registry as source of truth
- Contract enforcement (outputs match declaration)
- CLI integration via tool layer
