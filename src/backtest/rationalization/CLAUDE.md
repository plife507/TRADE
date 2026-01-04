# Rationalization Module (Layer 2)

Layer 2 state processing: transition detection, derived values, regime classification.

## Purpose

The rationalization layer sits between raw structure detection (Layer 1) and
signal generation (Layer 3). It provides:

1. **Transition Detection** - When structure values change
2. **Derived Values** - Computed from multiple structures (confluence, alignment)
3. **Regime Classification** - Market state (trending, ranging, volatile)
4. **Conflict Resolution** - Priority rules when signals conflict (W2-P4)

## Architecture Principle: Pure Math

All components define WHAT to compute, not WHEN:

```python
# CORRECT: Pure computation
class StateRationalizer:
    def rationalize(self, bar_idx, state, bar) -> RationalizedState:
        # Pure function: inputs -> output
        transitions = self._detect_transitions(state)
        derived = self._compute_derived(state, bar)
        return RationalizedState(transitions=transitions, derived=derived)

# WRONG: Module controls invocation
class StateRationalizer:
    def maybe_rationalize(self, bar_idx, state, bar):
        if self.should_run:  # NO - engine decides this
            return self._compute(...)
```

## Key Types

| Type | Purpose |
|------|---------|
| `Transition` | Records when a structure value changes |
| `RationalizedState` | Aggregated state for one bar |
| `MarketRegime` | Enum: TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE |
| `TransitionFilter` | Query criteria for transition history |

## Engine Integration Point

```python
# In engine hot loop (src/backtest/engine.py):

# Step 1: Update structures (Layer 1)
self._incremental_state.update_exec(bar_data)

# Step 2: Rationalize (Layer 2) - NEW
rationalized = self._rationalizer.rationalize(
    bar_idx=bar_idx,
    incremental_state=self._incremental_state,
    bar=bar_data,
)

# Step 3: Build snapshot with rationalized state
snapshot = self._build_snapshot_view(bar_idx, rationalized)
```

## Transition Detection

Transitions are emitted when ANY structure output changes:

```python
Transition(
    detector="swing",           # Which detector
    field="high_level",         # Which output key
    old_value=50000.0,          # Previous value
    new_value=50500.0,          # New value
    bar_idx=100,                # When it happened
    timeframe="exec",           # Which timeframe
)
```

### Tracked Fields by Detector

| Detector | Key Fields |
|----------|------------|
| `swing` | `high_level`, `low_level`, `version` |
| `zone` | `state`, `upper`, `lower`, `version` |
| `trend` | `direction`, `strength`, `version` |
| `derived_zone` | `zone{N}_state`, `any_active`, `active_count` |

## Derived Values (W2-P3)

Computed from multiple structure outputs:

| Value | Description | Range |
|-------|-------------|-------|
| `confluence_score` | How many signals align | 0.0 - 1.0 |
| `alignment` | HTF/MTF/LTF agreement | 0.0 - 1.0 |
| `momentum` | Aggregate momentum signal | -1.0 - 1.0 |

## Regime Classification (W2-P3)

Uses trend direction + volatility:

| Regime | Condition |
|--------|-----------|
| TRENDING_UP | Trend direction UP + strength > threshold |
| TRENDING_DOWN | Trend direction DOWN + strength > threshold |
| RANGING | Low volatility + no clear trend |
| VOLATILE | High ATR + frequent direction changes |

## Accessing in DSL Blocks

After W2-P5 engine integration:

```yaml
blocks:
  - id: entry
    cases:
      - when:
          all:
            - lhs: {feature_id: "rationalize", field: "confluence_score"}
              op: gt
              rhs: 0.7
            - lhs: {feature_id: "rationalize", field: "regime"}
              op: eq
              rhs: "trending_up"
        emit:
          - action: entry_long
```

## Play Schema Extension (W2-P4)

```yaml
rationalization:
  strategy: priority           # first_wins | priority | unanimous
  priority_order: [htf, mtf, exec]
  veto_on: [zone_broken, trend_reversal]
```

## Implementation Phases

| Phase | Focus | Status |
|-------|-------|--------|
| W2-P1 | Core infrastructure (types, rationalizer) | CURRENT |
| W2-P2 | Transition detection (TransitionManager) | PENDING |
| W2-P3 | Derived state computation | PENDING |
| W2-P4 | Conflict resolution | PENDING |
| W2-P5 | Engine integration | PENDING |

## Critical Rules

**ALL FORWARD**: No legacy adapters. Fresh module from scratch.

**Pure Functions**: StateRationalizer defines math only. Engine orchestrates.

**O(1) Access**: Transition history uses bounded buffer. No unbounded growth.

**Immutable Output**: RationalizedState is frozen dataclass. No mutation.

## Files

| File | Purpose |
|------|---------|
| `types.py` | Transition, RationalizedState, MarketRegime dataclasses |
| `rationalizer.py` | StateRationalizer main class |
| `transitions.py` | TransitionManager (W2-P2) |
| `derived.py` | DerivedStateComputer (W2-P3) |
| `conflicts.py` | ConflictResolver (W2-P4) |

## Testing

```python
# Basic import test
from src.backtest.rationalization import StateRationalizer, RationalizedState

# Instantiation test
rationalizer = StateRationalizer()

# Validation Plays (W2-P2+)
# V_200_transitions.yml
# V_201_derived_state.yml
# V_202_conflict_resolution.yml
```
