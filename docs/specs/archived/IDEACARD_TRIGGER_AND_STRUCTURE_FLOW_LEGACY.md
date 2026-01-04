# IdeaCard Trigger Logic & Structure Data Flow

> **Last Updated**: 2026-01-03
> **Status**: Current (Feature Registry Architecture v2.0)

This document explains how IdeaCard signal rules are evaluated and how market structures (swing, trend, zone, fibonacci) are held in memory and accessed through the snapshot system.

---

## Table of Contents

1. [Overview](#overview)
2. [IdeaCard Schema](#ideacard-schema)
3. [Data Structures](#data-structures)
4. [Engine Initialization](#engine-initialization)
5. [Hot Loop Processing](#hot-loop-processing)
6. [Snapshot Access](#snapshot-access)
7. [Condition Evaluation](#condition-evaluation)
8. [Structure Detector Details](#structure-detector-details)
9. [Complete Data Flow Diagram](#complete-data-flow-diagram)

---

## Overview

The system follows a **declarative-first** approach:

1. **IdeaCard YAML** declares features (indicators + structures) and signal rules
2. **FeatureRegistry** indexes features by ID and timeframe
3. **MultiTFIncrementalState** holds structure detectors organized by timeframe
4. **RuntimeSnapshotView** provides O(1) access to all values
5. **Condition Evaluator** checks rules against snapshot values

**Key Design Principles:**
- All features referenced by unique ID (not indicator_key + tf)
- O(1) hot loop access (no DataFrame operations)
- Structures update incrementally per bar (not batch recompute)
- Snapshot is a view, not a copy

---

## IdeaCard Schema

### Feature Declaration

```yaml
# configs/idea_cards/_validation/V_93_structures_multi_tf.yml

id: V_93_structures_multi_tf
version: "2.0.0"
name: "Validation 93: Multi-TF Structures"

execution_tf: "15m"  # Bar stepping timeframe

features:
  # Exec TF (15m) swing detection
  - id: "swing_exec"           # Unique identifier
    tf: "15m"                  # Timeframe
    type: structure            # Feature type (indicator | structure)
    structure_type: swing      # Detector from STRUCTURE_REGISTRY
    params:
      left: 5                  # Bars to left of pivot
      right: 5                 # Bars to right of pivot

  # MTF (1h) swing detection
  - id: "swing_1h"
    tf: "1h"
    type: structure
    structure_type: swing
    params:
      left: 3
      right: 3

  # MTF (1h) trend - depends on swing
  - id: "trend_1h"
    tf: "1h"
    type: structure
    structure_type: trend
    depends_on:
      swing: "swing_1h"        # Dependency reference by ID
```

### Signal Rules

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        # Exec swing high exists (level > 0)
        - feature_id: "swing_exec"
          field: "high_level"      # Output field from detector
          operator: "gt"
          value: 0.0

        # 1h trend is up (direction = 1)
        - feature_id: "trend_1h"
          field: "direction"
          operator: "eq"
          value: 1

  exit_rules:
    - direction: "long"
      conditions:
        - feature_id: "swing_exec"
          field: "low_level"
          operator: "gt"
          value: 0.0
```

### Condition Types

| Field | Description | Example |
|-------|-------------|---------|
| `feature_id` | Unique feature ID | `"swing_exec"` |
| `field` | Output field from detector | `"high_level"`, `"direction"` |
| `operator` | Comparison operator | `gt`, `lt`, `eq`, `gte`, `lte`, `cross_above`, `cross_below` |
| `value` | Literal value to compare | `0.0`, `1`, `50.0` |
| `compare_to` | Another feature_id (instead of value) | `"ema_slow"` |
| `compare_field` | Field on compare_to feature | `"value"` |

---

## Data Structures

### Feature (from `feature_registry.py`)

```python
@dataclass(frozen=True)
class Feature:
    id: str                           # Unique ID (required)
    tf: str                           # Timeframe (e.g., "15m", "1h")
    type: FeatureType                 # INDICATOR or STRUCTURE

    # For indicators
    indicator_type: str | None        # e.g., "ema", "rsi", "atr"
    params: dict[str, Any]            # e.g., {"length": 14}
    input_source: InputSource         # CLOSE, OPEN, HIGH, LOW, etc.

    # For structures
    structure_type: str | None        # e.g., "swing", "trend", "zone"
    depends_on: dict[str, str]        # e.g., {"swing": "swing_1h"}
```

### FeatureRegistry (from `feature_registry.py`)

```python
class FeatureRegistry:
    """Central registry of all features."""

    _features: dict[str, Feature]     # id -> Feature
    _by_tf: dict[str, list[Feature]]  # tf -> [Features]
    _execution_tf: str

    def get(self, feature_id: str) -> Feature
    def get_for_tf(self, tf: str) -> list[Feature]
    def get_all_tfs(self) -> set[str]
    def get_indicators(self) -> list[Feature]
    def get_structures(self) -> list[Feature]
```

### Condition (from `idea_card.py`)

```python
@dataclass(frozen=True)
class Condition:
    feature_id: str              # Reference feature by ID
    operator: RuleOperator       # gt, lt, eq, cross_above, etc.

    # Compare to literal OR another feature
    value: float | None          # Literal value
    compare_to: str | None       # Another feature_id

    # For multi-output features
    field: str = "value"         # Output field (default: primary)
    compare_field: str = "value" # Field on compare_to
```

### MultiTFIncrementalState (from `incremental/state.py`)

```python
class MultiTFIncrementalState:
    """Unified container for all timeframe states."""

    exec_tf: str                              # e.g., "15m"
    exec: TFIncrementalState                  # Exec TF structures
    htf: dict[str, TFIncrementalState]        # tf -> state (e.g., "1h", "4h")

    def update_exec(self, bar: BarData) -> None
    def update_htf(self, timeframe: str, bar: BarData) -> None
    def get_value(self, path: str) -> float   # e.g., "exec.swing.high_level"
```

### TFIncrementalState (from `incremental/state.py`)

```python
class TFIncrementalState:
    """Container for all structures on a single timeframe."""

    timeframe: str
    structures: dict[str, BaseIncrementalDetector]  # key -> detector
    _update_order: list[str]                         # Dependency-sorted keys

    def update(self, bar: BarData) -> None
    def get_value(self, struct_key: str, output_key: str) -> float
```

### BarData (from `incremental/base.py`)

```python
@dataclass(frozen=True)
class BarData:
    """Bar data passed to structure detectors."""
    idx: int                          # Bar index (monotonic)
    open: float
    high: float
    low: float
    close: float
    volume: float
    indicators: dict[str, float]      # Precomputed indicator values
```

---

## Engine Initialization

### Step 1: Load IdeaCard

```python
# From load_idea_card() in idea_card.py
idea_card = IdeaCard.from_yaml("configs/idea_cards/V_93_structures_multi_tf.yml")

# IdeaCard fields populated:
# - id: "V_93_structures_multi_tf"
# - execution_tf: "15m"
# - features: tuple[Feature, ...]
# - signal_rules: SignalRules
# - feature_registry: FeatureRegistry (cached property)
```

### Step 2: Build Feature Registry

```python
# Automatically built as cached property
registry = idea_card.feature_registry

# Registry indexes:
# - _features["swing_exec"] -> Feature(id="swing_exec", tf="15m", type=STRUCTURE)
# - _features["trend_1h"] -> Feature(id="trend_1h", tf="1h", type=STRUCTURE)
# - _by_tf["15m"] -> [Feature(swing_exec)]
# - _by_tf["1h"] -> [Feature(swing_1h), Feature(trend_1h)]
```

### Step 3: Build Incremental State

```python
# In engine.py:_build_incremental_state()

def _build_incremental_state(self, idea_card: IdeaCard) -> MultiTFIncrementalState:
    exec_specs = []
    htf_configs = {}  # tf -> list[specs]

    for feature in idea_card.features:
        if feature.type == FeatureType.STRUCTURE:
            spec = {
                "type": feature.structure_type,    # "swing", "trend"
                "key": feature.id,                 # "swing_exec", "trend_1h"
                "params": feature.params,          # {"left": 5, "right": 5}
                "depends_on": feature.depends_on,  # {"swing": "swing_1h"}
            }

            if feature.tf == idea_card.execution_tf:
                exec_specs.append(spec)
            else:
                htf_configs.setdefault(feature.tf, []).append(spec)

    return MultiTFIncrementalState(
        exec_tf=idea_card.execution_tf,
        exec_specs=exec_specs,        # [{"type": "swing", "key": "swing_exec", ...}]
        htf_configs=htf_configs,      # {"1h": [{"type": "swing", ...}, {"type": "trend", ...}]}
    )
```

### Step 4: Create Structure Detectors

```python
# In TFIncrementalState._build_structures()

for spec in specs:
    struct_type = spec["type"]       # "swing"
    key = spec["key"]                # "swing_exec"
    params = spec["params"]          # {"left": 5, "right": 5}
    depends_on = spec["depends_on"]  # {}

    # Get detector class from STRUCTURE_REGISTRY
    cls = STRUCTURE_REGISTRY[struct_type]  # SwingDetector

    # Resolve dependencies (must be defined earlier)
    deps = {}
    for dep_type, dep_key in depends_on.items():
        deps[dep_type] = self.structures[dep_key]

    # Create detector instance
    detector = cls.validate_and_create(struct_type, key, params, deps)

    self.structures[key] = detector
    self._update_order.append(key)
```

---

## Hot Loop Processing

### Main Loop Structure

```python
# In engine.py:run()

for i, bar in enumerate(exec_feed.iter_bars()):

    # ===== STAGE 1: Update Exec Structures =====
    if self._incremental_state is not None:
        # Build BarData from current bar
        indicator_values = {}
        for key in exec_feed.indicators.keys():
            val = exec_feed.indicators[key][i]
            if not np.isnan(val):
                indicator_values[key] = float(val)

        bar_data = BarData(
            idx=i,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=float(bar.volume),
            indicators=indicator_values,
        )

        # O(1) update per structure
        self._incremental_state.update_exec(bar_data)

    # ===== STAGE 2: Update HTF Structures (on HTF close only) =====
    htf_updated, mtf_updated = self._update_htf_mtf_indices(bar.ts_close)

    if self._incremental_state is not None and htf_updated:
        htf_tf = self._tf_mapping.get("htf")  # e.g., "1h"
        if htf_tf and htf_tf in self._incremental_state.htf:
            htf_bar_data = BarData(
                idx=self._current_htf_idx,
                open=float(htf_feed.open[htf_idx]),
                high=float(htf_feed.high[htf_idx]),
                low=float(htf_feed.low[htf_idx]),
                close=float(htf_feed.close[htf_idx]),
                volume=float(htf_feed.volume[htf_idx]),
                indicators=htf_indicator_values,
            )
            self._incremental_state.update_htf(htf_tf, htf_bar_data)

    # ===== STAGE 3: Build Snapshot =====
    snapshot = self._build_snapshot_view(
        exec_idx=i,
        step_result=step_result,
        rollups=rollups,
        incremental_state=self._incremental_state,  # Reference passed
    )

    # ===== STAGE 4: Evaluate Strategy =====
    signal = strategy(snapshot)

    # ===== STAGE 5: Process Signal =====
    if signal is not None:
        self._process_signal(signal, bar, snapshot)
```

### Update Timing

| Timeframe Role | Update Frequency | Example |
|----------------|------------------|---------|
| exec (15m) | Every bar | 96 times/day |
| MTF (1h) | Every 4 exec bars | 24 times/day |
| HTF (4h) | Every 16 exec bars | 6 times/day |

**Forward-Fill Rule**: Between updates, structure values remain constant (last closed value).

---

## Snapshot Access

### RuntimeSnapshotView Construction

```python
# From engine_snapshot.py:build_snapshot_view_impl()

snapshot = RuntimeSnapshotView(
    exec_idx=exec_idx,
    exec_feed=exec_feed,
    htf_feed=htf_feed,
    mtf_feed=mtf_feed,
    current_htf_idx=current_htf_idx,
    current_mtf_idx=current_mtf_idx,
    mark_price=mark_price,
    incremental_state=incremental_state,  # Reference to MultiTFIncrementalState
    feature_registry=feature_registry,     # Reference to FeatureRegistry
)
```

### Feature ID Access

```python
# From snapshot_view.py:get_by_feature_id()

def get_by_feature_id(
    self,
    feature_id: str,
    offset: int = 0,
    field: str = "value",
) -> float | None:
    """Get feature value by Feature ID (unified TF lookup)."""

    # 1. Lookup feature in registry
    feature = self._feature_registry.get(feature_id)
    tf = feature.tf

    # 2. Check cache for resolved path
    cache_key = f"{feature_id}:{field}"
    cached = self._feature_id_cache.get(cache_key)

    if cached is None:
        if feature.type == FeatureType.STRUCTURE:
            # Structure: build path for incremental state
            if tf == self._exec_tf:
                indicator_key = f"structure.{feature_id}.{field}"
            else:
                indicator_key = f"structure.{feature_id}.{field}"
            cached = (tf, indicator_key)
        else:
            # Indicator: use feature_id directly
            indicator_key = feature_id if field == "value" else f"{feature_id}_{field}"
            cached = (tf, indicator_key)

        self._feature_id_cache[cache_key] = cached

    tf, indicator_key = cached

    # 3. Get value from appropriate source
    if feature.type == FeatureType.STRUCTURE:
        # Access via incremental state
        if tf == self._exec_tf:
            path = f"exec.{feature_id}.{field}"
        else:
            path = f"htf_{tf}.{feature_id}.{field}"
        return self._incremental_state.get_value(path)
    else:
        # Access via FeedStore array
        feed = self._get_feed_for_tf(tf)
        idx = self._get_context_idx_for_tf(tf)
        return float(feed.indicators[indicator_key][idx - offset])
```

### Path Resolution

| Feature Type | TF | Path Format | Example |
|--------------|-----|-------------|---------|
| Structure | exec | `exec.<id>.<field>` | `exec.swing_exec.high_level` |
| Structure | MTF/HTF | `htf_<tf>.<id>.<field>` | `htf_1h.trend_1h.direction` |
| Indicator | exec | Direct array lookup | `feed.indicators["ema_fast"][idx]` |
| Indicator | MTF/HTF | Direct array lookup | `htf_feed.indicators["rsi_1h"][htf_idx]` |

---

## Condition Evaluation

### Evaluator Flow

```python
# From execution_validation.py:_evaluate_conditions()

def _evaluate_conditions(self, conditions: list[Condition],
                         snapshot: RuntimeSnapshotView) -> bool:
    """Evaluate all conditions (AND logic)."""

    for cond in conditions:
        if cond.feature_id:
            # New path: Feature ID-based lookup
            result = self._evaluate_condition_feature_id(cond, snapshot)
        else:
            # Legacy path: indicator_key + tf
            result = self._evaluate_condition_legacy(cond, snapshot)

        if not result:
            return False  # Short-circuit on first failure

    return True
```

### Feature ID Evaluation

```python
# From execution_validation.py:_evaluate_condition_feature_id()

def _evaluate_condition_feature_id(self, cond: Condition,
                                    snapshot: RuntimeSnapshotView) -> bool:
    """Evaluate condition using Feature Registry."""

    # 1. Get current value
    current_val = snapshot.get_by_feature_id(
        cond.feature_id,
        offset=0,
        field=cond.field,
    )

    if current_val is None or np.isnan(current_val):
        return False

    # 2. Get comparison value
    if cond.compare_to:
        # Comparing to another feature
        compare_val = snapshot.get_by_feature_id(
            cond.compare_to,
            offset=0,
            field=cond.compare_field,
        )
    elif cond.value is not None:
        # Comparing to literal
        compare_val = float(cond.value)
    else:
        return False

    if compare_val is None or np.isnan(compare_val):
        return False

    # 3. Apply operator
    op = cond.operator
    if op == RuleOperator.GT:
        return current_val > compare_val
    elif op == RuleOperator.GTE:
        return current_val >= compare_val
    elif op == RuleOperator.LT:
        return current_val < compare_val
    elif op == RuleOperator.LTE:
        return current_val <= compare_val
    elif op == RuleOperator.EQ:
        return abs(current_val - compare_val) < 1e-9
    elif op == RuleOperator.CROSS_ABOVE:
        prev_val = snapshot.get_by_feature_id(cond.feature_id, offset=1, field=cond.field)
        prev_compare = snapshot.get_by_feature_id(cond.compare_to, offset=1, field=cond.compare_field) if cond.compare_to else compare_val
        return prev_val <= prev_compare and current_val > compare_val
    elif op == RuleOperator.CROSS_BELOW:
        prev_val = snapshot.get_by_feature_id(cond.feature_id, offset=1, field=cond.field)
        prev_compare = snapshot.get_by_feature_id(cond.compare_to, offset=1, field=cond.compare_field) if cond.compare_to else compare_val
        return prev_val >= prev_compare and current_val < compare_val

    return False
```

---

## Structure Detector Details

### Available Detectors (STRUCTURE_REGISTRY)

| Type | Description | Required Params | Depends On | Output Keys |
|------|-------------|-----------------|------------|-------------|
| `swing` | Swing high/low detection | `left`, `right` | None | `high_level`, `high_idx`, `low_level`, `low_idx` |
| `fibonacci` | Fib retracement/extension | `levels`, `mode` | `swing` | `level_<ratio>` (e.g., `level_0.618`) |
| `zone` | Demand/supply zones | `zone_type`, `width_atr` | `swing` | `state`, `upper`, `lower`, `anchor_idx` |
| `trend` | Trend classification | None | `swing` | `direction`, `strength`, `bars_in_trend` |
| `rolling_window` | O(1) rolling min/max | `size`, `field`, `mode` | None | `value` |

### SwingDetector Implementation

```python
# From incremental/detectors/swing.py

class SwingDetector(BaseIncrementalDetector):
    """O(1) swing high/low detection using RingBuffers."""

    REQUIRED_PARAMS = {"left", "right"}
    OUTPUT_KEYS = ["high_level", "high_idx", "low_level", "low_idx"]

    def __init__(self, left: int, right: int):
        self._left = left
        self._right = right
        self._window_size = left + right + 1

        # RingBuffers for O(1) min/max lookup
        self._high_buffer = RingBuffer(self._window_size)
        self._low_buffer = RingBuffer(self._window_size)

        # Current swing values
        self._high_level = float("nan")
        self._high_idx = -1
        self._low_level = float("nan")
        self._low_idx = -1

    def update(self, bar_idx: int, bar: BarData) -> None:
        """Update on each bar close."""
        # Push new values
        self._high_buffer.push(bar.high)
        self._low_buffer.push(bar.low)

        # Check if buffer is full (enough history)
        if not self._high_buffer.is_full():
            return

        # Check if center bar is swing high
        center_high = self._high_buffer.get(self._left)
        if center_high >= self._high_buffer.max():
            self._high_level = center_high
            self._high_idx = bar_idx - self._right

        # Check if center bar is swing low
        center_low = self._low_buffer.get(self._left)
        if center_low <= self._low_buffer.min():
            self._low_level = center_low
            self._low_idx = bar_idx - self._right

    def get_value(self, key: str) -> float | int:
        if key == "high_level":
            return self._high_level
        elif key == "high_idx":
            return self._high_idx
        elif key == "low_level":
            return self._low_level
        elif key == "low_idx":
            return self._low_idx
        raise KeyError(f"Unknown output key: {key}")
```

### TrendDetector Implementation

```python
# From incremental/detectors/trend.py

class TrendDetector(BaseIncrementalDetector):
    """Trend direction based on swing sequence."""

    REQUIRED_PARAMS = set()
    DEPENDS_ON = {"swing"}  # Requires swing detector
    OUTPUT_KEYS = ["direction", "strength", "bars_in_trend"]

    def __init__(self, swing: SwingDetector):
        self._swing = swing

        self._direction = 0      # 1=up, -1=down, 0=unknown
        self._strength = 0.0     # Trend strength metric
        self._bars_in_trend = 0

        # Track last swing levels for HH/LL detection
        self._last_high = float("nan")
        self._last_low = float("nan")

    def update(self, bar_idx: int, bar: BarData) -> None:
        """Update trend based on swing sequence."""
        current_high = self._swing.get_value("high_level")
        current_low = self._swing.get_value("low_level")

        # Detect higher-high / lower-low pattern
        if not np.isnan(current_high) and not np.isnan(self._last_high):
            if current_high > self._last_high and current_low > self._last_low:
                # Higher high + higher low = uptrend
                self._direction = 1
                self._bars_in_trend = 0
            elif current_high < self._last_high and current_low < self._last_low:
                # Lower high + lower low = downtrend
                self._direction = -1
                self._bars_in_trend = 0

        self._bars_in_trend += 1
        self._last_high = current_high
        self._last_low = current_low
```

---

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              IdeaCard YAML                                      │
│                                                                                 │
│  features:                              signal_rules:                           │
│    - id: "swing_exec"                     entry_rules:                          │
│      tf: "15m"                              - direction: "long"                 │
│      type: structure                          conditions:                       │
│      structure_type: swing                      - feature_id: "swing_exec"      │
│      params: {left: 5, right: 5}                  field: "high_level"           │
│                                                   operator: "gt"                │
│    - id: "trend_1h"                               value: 0                      │
│      tf: "1h"                                   - feature_id: "trend_1h"        │
│      type: structure                              field: "direction"            │
│      structure_type: trend                        operator: "eq"                │
│      depends_on: {swing: "swing_1h"}              value: 1                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Engine Initialization                                 │
│                                                                                 │
│  ┌─────────────────────────┐    ┌─────────────────────────────────────────────┐│
│  │    FeatureRegistry      │    │         MultiTFIncrementalState             ││
│  │                         │    │                                             ││
│  │  _features:             │    │  exec: TFIncrementalState("15m")            ││
│  │    "swing_exec" → F1    │    │    └── structures:                          ││
│  │    "swing_1h"   → F2    │    │          "swing_exec" → SwingDetector       ││
│  │    "trend_1h"   → F3    │    │                                             ││
│  │                         │    │  htf["1h"]: TFIncrementalState("1h")        ││
│  │  _by_tf:                │    │    └── structures:                          ││
│  │    "15m" → [F1]         │    │          "swing_1h" → SwingDetector         ││
│  │    "1h"  → [F2, F3]     │    │          "trend_1h" → TrendDetector         ││
│  └─────────────────────────┘    │               └── depends_on: swing_1h      ││
│                                 └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               Hot Loop                                          │
│                                                                                 │
│  for each exec bar (i):                                                         │
│                                                                                 │
│    ┌─────────────────────────────────────────────────────────────────────────┐ │
│    │ 1. UPDATE EXEC STRUCTURES                                               │ │
│    │    bar_data = BarData(idx=i, open, high, low, close, volume, indicators)│ │
│    │    incremental_state.update_exec(bar_data)                              │ │
│    │        └── SwingDetector.update(i, bar_data)  [O(1)]                    │ │
│    └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│    ┌─────────────────────────────────────────────────────────────────────────┐ │
│    │ 2. UPDATE HTF STRUCTURES (on HTF close only)                            │ │
│    │    if htf_closed:                                                       │ │
│    │        htf_bar_data = BarData(idx=htf_idx, ...)                         │ │
│    │        incremental_state.update_htf("1h", htf_bar_data)                 │ │
│    │            └── SwingDetector.update(htf_idx, htf_bar_data)              │ │
│    │            └── TrendDetector.update(htf_idx, htf_bar_data)              │ │
│    └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│    ┌─────────────────────────────────────────────────────────────────────────┐ │
│    │ 3. BUILD SNAPSHOT                                                       │ │
│    │    snapshot = RuntimeSnapshotView(                                      │ │
│    │        exec_feed=exec_feed,                                             │ │
│    │        incremental_state=incremental_state,  # Reference (not copy)     │ │
│    │        feature_registry=feature_registry,                               │ │
│    │    )                                                                    │ │
│    └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│    ┌─────────────────────────────────────────────────────────────────────────┐ │
│    │ 4. EVALUATE STRATEGY                                                    │ │
│    │    signal = strategy(snapshot)                                          │ │
│    │        └── evaluator._evaluate_conditions(conditions, snapshot)         │ │
│    └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Condition Evaluation                                   │
│                                                                                 │
│  for condition in entry_rule.conditions:                                        │
│                                                                                 │
│    ┌─────────────────────────────────────────────────────────────────────────┐ │
│    │ condition: feature_id="swing_exec", field="high_level", op="gt", val=0  │ │
│    │                                                                         │ │
│    │ 1. snapshot.get_by_feature_id("swing_exec", field="high_level")         │ │
│    │        │                                                                │ │
│    │        ├── FeatureRegistry.get("swing_exec")                            │ │
│    │        │       → Feature(type=STRUCTURE, tf="15m")                      │ │
│    │        │                                                                │ │
│    │        ├── Build path: "exec.swing_exec.high_level"                     │ │
│    │        │                                                                │ │
│    │        └── incremental_state.get_value("exec.swing_exec.high_level")    │ │
│    │                │                                                        │ │
│    │                └── exec.structures["swing_exec"].get_value("high_level")│ │
│    │                        │                                                │ │
│    │                        └── SwingDetector._high_level = 50000.0          │ │
│    │                                                                         │ │
│    │ 2. Compare: 50000.0 > 0.0 → True                                        │ │
│    └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│    ┌─────────────────────────────────────────────────────────────────────────┐ │
│    │ condition: feature_id="trend_1h", field="direction", op="eq", val=1     │ │
│    │                                                                         │ │
│    │ 1. snapshot.get_by_feature_id("trend_1h", field="direction")            │ │
│    │        │                                                                │ │
│    │        ├── FeatureRegistry.get("trend_1h")                              │ │
│    │        │       → Feature(type=STRUCTURE, tf="1h")                       │ │
│    │        │                                                                │ │
│    │        ├── Build path: "htf_1h.trend_1h.direction"                      │ │
│    │        │                                                                │ │
│    │        └── incremental_state.get_value("htf_1h.trend_1h.direction")     │ │
│    │                │                                                        │ │
│    │                └── htf["1h"].structures["trend_1h"].get_value("direction")│
│    │                        │                                                │ │
│    │                        └── TrendDetector._direction = 1                 │ │
│    │                                                                         │ │
│    │ 2. Compare: 1 == 1 → True                                               │ │
│    └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│  All conditions True → Entry signal generated                                   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways

1. **Declarative Configuration**: IdeaCard YAML defines everything - no code changes needed for new strategies

2. **Feature ID Abstraction**: All access is by unique ID, not indicator_key + tf combination

3. **O(1) Hot Loop**:
   - Structure updates: O(1) per bar via RingBuffers
   - Snapshot creation: O(1) - just sets indices, no copies
   - Value access: O(1) - direct field reads

4. **Incremental State**:
   - Structures maintain state between bars (not recomputed)
   - Dependencies resolved at construction time
   - Update order enforces dependency graph

5. **Forward-Fill Semantics**:
   - Exec structures update every bar
   - HTF structures update only on HTF close
   - Between closes, values remain constant

6. **No Lookahead**:
   - All values reflect last CLOSED bar
   - Engine asserts `snapshot.ts_close == bar.ts_close`
   - HTF values forward-fill from previous close

---

## Related Documentation

- `docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md` - Detailed incremental state design
- `docs/architecture/IDEACARD_VISION.md` - Agent-composable IdeaCard blocks
- `docs/architecture/IDEACARD_ENGINE_FLOW.md` - Full IdeaCard → Engine flow
- `src/backtest/CLAUDE.md` - Backtest module rules and patterns
