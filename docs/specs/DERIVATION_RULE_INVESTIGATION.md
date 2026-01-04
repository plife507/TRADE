## INVESTIGATION REPORT: Generic DerivationRule System for Market Structure -> Derived Zones

---

## Terminology (2026-01-04)

This document uses the new trading hierarchy terminology:

| Term | Definition |
|------|------------|
| **Setup** | Reusable rule blocks, filters, entry/exit logic |
| **Play** | Complete strategy specification (formerly "IdeaCard") |
| **Playbook** | Collection of plays with regime routing |
| **System** | Full trading operation with risk/execution |
| **Forge** | Development/validation environment (src/forge/) |

See: `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` for complete architecture.

---

## IMPLEMENTATION STATUS: COMPLETE (2026-01-03)

Phase 12 implementation is **COMPLETE**. All locked decisions have been implemented:

| Phase | Status | Files Modified/Created |
|-------|--------|----------------------|
| 12.1: Version tracking | DONE | `swing.py`, `trend.py`, `zone.py`, `registry.py` |
| 12.2: derived_zone detector | DONE | `detectors/derived_zone.py` (NEW) |
| 12.3: Warmup computation | DONE | `execution_validation.py` |
| 12.4: Validation Plays | DONE | `V_120_*.yml`, `V_121_*.yml`, `V_122_*.yml` |
| 12.5: Documentation | DONE | This file |

**Key Implementation Details:**

- **Version tracking**: All three base detectors (swing, trend, zone) now expose `version` field
  - Swing: increments on confirmed pivot (after left+right confirmation)
  - Trend: increments on direction change
  - Zone: increments on state change (new zone or broken)

- **derived_zone detector**: K slots + aggregates pattern implemented
  - Slot outputs: `zone{N}_lower`, `zone{N}_upper`, `zone{N}_state`, etc.
  - Aggregate outputs: `active_count`, `any_active`, `any_touched`, `closest_active_*`
  - Empty encoding: `None` for floats, `"NONE"` for state, `-1` for ints, `false` for bools
  - Zone hash: blake2b for stability across platforms

- **Warmup**: `_compute_structure_warmup()` includes derived_zone cascading from source

---

### EXECUTIVE SUMMARY

The codebase has **modular but disconnected** structures that can be unified into a generic derivation framework:

1. **Market structures** (swing, trend, zone, fibonacci) exist as **incremental detectors** updated on TF closes
2. **Fibonacci already implements derivation** from swing (dependency-based, O(1) updates)
3. **No event stream or versioning currently exists** for tracking structure changes
4. **Zone interaction metrics** are computed separately but could be extended
5. **Feature Registry** provides clean abstraction for feature ID → TF → structure mapping

The minimal path forward is **Option A: Version-Based Derivation Triggers** with support for cheap event payloads. This avoids refactoring TFIncrementalState while enabling deterministic, bounded-time derivations.

---

## LOCKED IMPLEMENTATION DECISIONS

These decisions were finalized during review and MUST be followed in implementation:

### Decision 1: K Slots (Scalar Outputs) — NOT Vector Zones

**Rationale**: Minimal diff, avoids engine changes, matches existing snapshot patterns.

**Implementation**:
```yaml
# Derived zone exposes fixed slots, not a dynamic list
outputs:
  zone0_lower: FLOAT   # First active zone
  zone0_upper: FLOAT
  zone0_state: ENUM    # ACTIVE | BROKEN | NONE
  zone1_lower: FLOAT   # Second active zone
  zone1_upper: FLOAT
  zone1_state: ENUM
  # ... up to zoneK (K=max_active from params)
  active_count: INT    # How many slots are populated
```

**DSL Access**:
```yaml
# Condition checks against specific slot
- lhs:
    feature_id: "fib_zones_1h"
    field: "zone0_state"
  op: eq
  rhs: "ACTIVE"
```

**Why NOT Vector Zones**: Vector outputs require snapshot schema changes, DSL iteration syntax, and evaluator modifications. K slots works with existing scalar-only infrastructure.

---

### Decision 2: Version Bump = Pivot Confirmed Only

**Rationale**: Version must increment only when a swing pivot is **confirmed** (after left/right confirmation window), not on every tentative high/low.

**Implementation**:
```python
# In IncrementalSwingDetector.update():
def update(self, bar_idx: int, bar: BarData) -> None:
    # Existing swing detection...

    # Version bump ONLY on confirmed pivot (after right bars pass)
    if self._pivot_just_confirmed:
        self._version += 1
        self._last_confirmed_bar = bar_idx
```

**Why This Matters**: Noisy version bumps cause excessive zone regeneration. A confirmed pivot means the swing is locked and won't be revised by future bars.

---

### Decision 3: Explicit Price Source (`mark_close` | `last_close`)

**Rationale**: Zone interaction (touched/inside/broken) requires explicit price source, not implicit `bar.close`.

**Implementation**:
```yaml
# In Play feature params
- id: fib_zones_1h
  params:
    price_source: mark_close  # or "last_close"
```

```python
# In IncrementalDerivedZone.update():
def update(self, bar_idx: int, bar: BarData) -> None:
    price = bar.mark_close if self.price_source == "mark_close" else bar.close
    # Use `price` for zone interaction checks
```

**Why This Matters**: `mark_price` and `last_close` can diverge significantly in futures. Using the wrong price creates false zone breaks.

---

### Decision 4: Computed Warmup (Not Constant)

**Rationale**: Warmup requirements depend on source structure params, not a fixed constant.

**Implementation**:
```python
# In preflight.py or feature_registry.py
def get_derived_zone_warmup(feature: Feature) -> int:
    source_id = feature.depends_on["source"]
    source_feature = registry.get(source_id)

    if source_feature.structure_type == "swing":
        left = source_feature.params.get("left", 5)
        right = source_feature.params.get("right", 5)
        return left + right + 1 + feature.params.get("extra_warmup", 0)

    # Other source types...
    return 100  # Fallback
```

**Why This Matters**: Fixed warmup of 100 bars is wrong if swing uses `left=20, right=20`. Warmup must cascade from source structure.

---

### Decision 5: Separate Regen vs Interaction Paths

**Rationale**: Zone regeneration (new anchors) and zone interaction (touched/inside/broken) are separate concerns with different triggers.

**Implementation**:
```python
def update(self, bar_idx: int, bar: BarData) -> None:
    # REGEN PATH: Only on source version change
    if self._source_version != source.get_value("version"):
        self._regenerate_zones(bar_idx, bar)
        self._source_version = source.get_value("version")

    # INTERACTION PATH: Every exec close
    self._update_zone_interactions(bar_idx, bar)
```

**Why This Matters**:
- Regen is expensive (creates new zones) → only on confirmed pivot
- Interaction is cheap (state checks) → every bar
- Mixing them causes either missed breaks or excessive regen

---

## 1. CODEBASE MAP

### 1.1 Market Structure Detectors (Incremental)

| File | Class | Purpose | Key Methods |
|------|-------|---------|-------------|
| `/c/code/ai/trade/src/backtest/incremental/base.py` | `BaseIncrementalDetector` | Abstract base for all detectors | `update()`, `get_value()`, `get_output_keys()` |
| `/c/code/ai/trade/src/backtest/incremental/detectors/swing.py` | `IncrementalSwingDetector` | Swing high/low with left/right confirmation window | Outputs: `high_level`, `high_idx`, `low_level`, `low_idx` |
| `/c/code/ai/trade/src/backtest/incremental/detectors/trend.py` | `IncrementalTrendDetector` | HH/HL vs LL/LH classification | Outputs: `direction`, `bars_in_trend`, `strength` |
| `/c/code/ai/trade/src/backtest/incremental/detectors/zone.py` | `IncrementalZoneDetector` | Demand/supply zones from swing pivots | Outputs: `state`, `upper`, `lower`, `anchor_idx` |
| `/c/code/ai/trade/src/backtest/incremental/detectors/fibonacci.py` | `IncrementalFibonacci` | Fib levels from swing high/low | Outputs: `level_0.236`, `level_0.382`, ..., `level_1.618` |
| `/c/code/ai/trade/src/backtest/incremental/detectors/rolling_window.py` | `IncrementalRollingWindow` | Rolling min/max | Outputs: `value` |
| `/c/code/ai/trade/src/backtest/incremental/registry.py` | `STRUCTURE_REGISTRY` | Global detector class registry | `register_structure()` decorator |

**Key Pattern**: Each detector maintains internal state and returns O(1) on `get_value()`.

### 1.2 State Container & Snapshot

| File | Class | Purpose |
|------|-------|---------|
| `/c/code/ai/trade/src/backtest/incremental/state.py` | `TFIncrementalState` | Holds all detectors for a single TF; calls `update()` on each per bar |
| `/c/code/ai/trade/src/backtest/incremental/state.py` | `MultiTFIncrementalState` | Unified container for exec + HTF states; routes `update_exec()` / `update_htf()` by TF |
| `/c/code/ai/trade/src/backtest/runtime/snapshot_view.py` | `RuntimeSnapshotView` | O(1) access to structure values via `get_structure(path)` or `get_by_feature_id()` |
| `/c/code/ai/trade/src/backtest/runtime/snapshot_view.py` | `TFContext` | Per-TF context; holds FeedStore, current index, ready state |

**Key Flow**:
```
Engine hot loop:
  1. Load exec bar → create BarData
  2. Call MultiTFIncrementalState.update_exec(bar_data)
     → TFIncrementalState.update() on each detector
  3. On HTF close: MultiTFIncrementalState.update_htf(tf, bar_data)
  4. Build RuntimeSnapshotView with updated incremental state
  5. Conditions read via snapshot.get_structure("swing.high_level")
```

### 1.3 Feature Registry & IdeaCard

| File | Class | Purpose |
|------|-------|---------|
| `/c/code/ai/trade/src/backtest/feature_registry.py` | `Feature` | Single feature (indicator or structure) with ID, TF, type, params, dependencies |
| `/c/code/ai/trade/src/backtest/feature_registry.py` | `FeatureRegistry` | Maps feature ID → Feature; supports TF-based lookups |
| `/c/code/ai/trade/src/backtest/idea_card.py` | `IdeaCard` | Declarative strategy config with features list and signal rules |

**Feature Anatomy** (structure example):
```python
Feature(
    id="swing_1h",
    tf="1h",
    type=FeatureType.STRUCTURE,
    structure_type="swing",
    params={"left": 5, "right": 5},
    depends_on={}  # Empty for swing (base structure)
)

Feature(
    id="fib_1h",
    tf="1h",
    type=FeatureType.STRUCTURE,
    structure_type="fibonacci",
    params={"levels": [0.236, 0.382, 0.618], "mode": "retracement"},
    depends_on={"swing": "swing_1h"}  # References another feature ID
)
```

### 1.4 Zone Interaction Metrics

| File | Class | Purpose |
|------|-------|---------|
| `/c/code/ai/trade/src/backtest/market_structure/zone_interaction.py` | `ZoneInteractionComputer` | Computes `touched`, `inside`, `time_in_zone` for zones |
| `/c/code/ai/trade/src/backtest/market_structure/types.py` | `ZoneState` enum | NONE, ACTIVE, BROKEN |

**Current Use**: Zone interaction is computed separately (not yet integrated into incremental detectors).

### 1.5 Engine & Execution

| File | Function | Purpose |
|------|----------|---------|
| `/c/code/ai/trade/src/backtest/engine.py` | `_build_incremental_state()` | Creates MultiTFIncrementalState from feature registry |
| `/c/code/ai/trade/src/backtest/engine.py` | Hot loop ~line 918 | Calls `self._incremental_state.update_exec(bar_data)` each exec bar |
| `/c/code/ai/trade/src/backtest/execution_validation.py` | `compute_warmup_requirements()` | Computes required history per TF for indicators |

---

## 2. CURRENT-STATE CAPABILITY ASSESSMENT

### 2.1 What Exists (Strengths)

✅ **Incremental structure detection is already implemented** 
- All structures (swing, trend, zone, fibonacci) are detectors with O(1) update/read
- Dependencies are already modeled (`depends_on` dict in Feature)
- Fibonacci proves the concept: it regenerates levels only when swing changes

✅ **TF-based multiplexing is in place**
- MultiTFIncrementalState.update_exec() / update_htf() already routes by TF
- No lookahead: HTF values forward-fill between closes (see RuntimeSnapshotView)
- Closed-candle only semantics enforced

✅ **Feature Registry provides clean abstraction**
- Features have unique IDs, TF mappings, and dependency declarations
- No implicit defaults; all must be declared
- Feature → detector → value path is clean

✅ **Zone interaction metrics framework exists**
- `ZoneInteractionComputer` already computes touched/inside/time_in_zone
- Separates state (from zone detector) from interaction logic
- Can be extended to track lifecycle (ACTIVE/BROKEN/expired)

### 2.2 What's Missing (Gaps)

❌ **No event stream or version counter**
- Fibonacci detects swing changes by comparing current vs stored levels
- No explicit "swing changed" signal → relies on comparing `high_level`/`low_level` each bar
- This is workable but not explicit; hard to add derived-zone regen logic without plumbing events through

❌ **Derived zones not yet a detector type**
- Zone detector currently creates demand/supply from swing pivots
- No "derived_zone" type for fib-based zones, SR bands, etc.
- Zone interaction metrics not integrated into zone detector (separate computer)

❌ **No bounded active zone set**
- Current zone detector holds only current demand/supply per swing
- No `max_active` limit; no TTL or supersede policy
- Zone state machine (ACTIVE → BROKEN) exists but not lifecycle management

❌ **Preflight/warmup doesn't account for derived zones**
- `compute_warmup_requirements()` only computes for indicators
- No mechanism to say "I need N bars of swing history to derive fib zones"

---

## 3. INTEGRATION OPTIONS (RANKED)

### Option A: Version-Based Derivation Triggers (RECOMMENDED)

**Concept**: Add monotonic `version` field to base structure outputs. Whenever version increments, derived structures recompute. Optional lightweight event payload for context.

#### Implementation

**Step 1: Add version to TrendState enum output**

```python
# In incremental/detectors/trend.py (already has parent_version, just expose it)
class IncrementalTrendDetector(BaseIncrementalDetector):
    # ...
    def get_output_keys(self) -> list[str]:
        return ["direction", "bars_in_trend", "strength", "version"]
    
    def get_value(self, key: str) -> float | int | str:
        if key == "version":
            return self._version  # Existing field, just expose
        # ...
```

**Step 2: Add version counter to swing detector**

```python
# In incremental/detectors/swing.py
class IncrementalSwingDetector(BaseIncrementalDetector):
    def __init__(self, params, deps=None):
        # ... existing init ...
        self._version: int = 0  # NEW: increments on high/low change
    
    def update(self, bar_idx: int, bar: BarData) -> None:
        old_high = self.high_level
        old_low = self.low_level
        # ... compute new swings ...
        if self.high_level != old_high or self.low_level != old_low:
            self._version += 1  # Trigger derivations
    
    def get_output_keys(self) -> list[str]:
        return ["high_level", "high_idx", "low_level", "low_idx", "version"]
    
    def get_value(self, key: str) -> float | int | str:
        if key == "version":
            return self._version  # NEW
        # ... existing logic ...
```

**Step 3: Create derived_zone detector**

```python
# New file: incremental/detectors/derived_zone.py

@register_structure("derived_zone")
class IncrementalDerivedZone(BaseIncrementalDetector):
    """
    Derived zones from a source structure (e.g., fib levels, SR bands).
    
    Recomputes zone anchors only when source version changes.
    Maintains bounded active set with TTL and supersede policy.
    
    Parameters:
        source_structure: "swing" | "trend" | "zone" | "fibonacci"  (the base)
        derivation_mode: "fibonacci_zones" | "support_resistance" | "order_blocks"
        levels: [0.236, 0.382, ...] for fib; or [mid, width] for SR
        max_active: int = 5  (max zones in active set)
        ttl_bars: int | None = None  (bars until zone expires, None = never)
        supersede_on: "price_break" | "time_expired" | "source_change"
    
    Outputs:
        zones: List of {lower, upper, anchor_idx, instance_id, state}
        active_count: Current count of ACTIVE zones
    """
    
    REQUIRED_PARAMS = ["source_structure", "derivation_mode"]
    OPTIONAL_PARAMS = {
        "levels": [0.236, 0.382, 0.618],
        "max_active": 5,
        "ttl_bars": None,
        "supersede_on": "price_break",
    }
    DEPENDS_ON = ["source_structure"]  # String key of dependency
    
    def __init__(self, params, deps):
        self.source = deps["source_structure"]
        self.mode = params["derivation_mode"]
        self.levels = params.get("levels", [0.236, 0.382, 0.618])
        self.max_active = params.get("max_active", 5)
        self.ttl_bars = params.get("ttl_bars")
        self.supersede_on = params.get("supersede_on", "price_break")
        
        self._source_version = -1  # Track source change
        self._active_zones = []  # List of {lower, upper, anchor_idx, instance_id, created_bar}
        self._zone_counter = 0  # For instance_id hash
    
    def update(self, bar_idx: int, bar: BarData) -> None:
        # Check if source changed
        source_version = self.source.get_value("version")
        if source_version != self._source_version:
            self._source_version = source_version
            self._regenerate_zones(bar_idx, bar)
        
        # Update zone states (ACTIVE → BROKEN if price closes beyond bounds)
        for zone in self._active_zones:
            if zone["state"] == ZoneState.ACTIVE:
                if bar.close < zone["lower"] or bar.close > zone["upper"]:
                    zone["state"] = ZoneState.BROKEN
                zone["bars_alive"] = bar_idx - zone["created_bar"]
                
                # TTL check
                if self.ttl_bars and zone["bars_alive"] > self.ttl_bars:
                    zone["state"] = ZoneState.NONE
        
        # Trim expired zones
        self._active_zones = [z for z in self._active_zones if z["state"] != ZoneState.NONE]
    
    def _regenerate_zones(self, bar_idx: int, bar: BarData) -> None:
        """Called when source version changes."""
        if self.mode == "fibonacci_zones":
            high = self.source.get_value("high_level")
            low = self.source.get_value("low_level")
            if high > 0 and low > 0:
                range_ = high - low
                new_zones = []
                for level in self.levels:
                    zone_mid = high - (range_ * level)
                    new_zones.append({
                        "lower": zone_mid - 10,  # Use width_params in full version
                        "upper": zone_mid + 10,
                        "anchor_idx": bar_idx,
                        "instance_id": hash((level, high, low)) & 0xFFFFFFFF,
                        "state": ZoneState.ACTIVE,
                        "created_bar": bar_idx,
                    })
                
                # Enforce max_active: FIFO supersede
                self._active_zones = new_zones + self._active_zones
                if len(self._active_zones) > self.max_active:
                    self._active_zones = self._active_zones[:self.max_active]
        
        # Other modes: support_resistance, order_blocks, etc.
    
    def get_output_keys(self) -> list[str]:
        return ["active_count"]  # Plus maybe zone details
    
    def get_value(self, key: str) -> float | int | str:
        if key == "active_count":
            return len([z for z in self._active_zones if z["state"] == ZoneState.ACTIVE])
        raise KeyError(key)
```

**Step 4: Update IdeaCard feature declaration**

```yaml
features:
  - id: "swing_1h"
    tf: "1h"
    type: structure
    structure_type: swing
    params:
      left: 5
      right: 5

  - id: "fib_zones_1h"
    tf: "1h"
    type: structure
    structure_type: derived_zone
    depends_on:
      source_structure: "swing_1h"
    params:
      derivation_mode: "fibonacci_zones"
      levels: [0.236, 0.382, 0.618, 0.786]
      max_active: 3
      ttl_bars: 50
      supersede_on: "price_break"
```

#### Pros
- **Minimal diff**: Add version field to 2–3 detectors, create new detector type
- **Deterministic**: Version counter is monotonic; regeneration happens on defined signal
- **O(1) hot loop**: Derivation check is `if current_version != last_version`
- **Live-compatible**: Works identically in backtest and live (version increments same way)
- **Extensible**: Any detector can expose version; any derivation can subscribe
- **Bounded complexity**: `max_active` and `ttl_bars` cap the active set size

#### Cons
- **Requires detector changes**: Must add version to swing, trend, zone, etc.
- **Version conflicts**: If two structures on same TF both trigger derivations, both fire simultaneously (not necessarily bad, but worth noting)
- **Event payload is optional**: If you need rich context (e.g., "which leg changed?"), version alone is thin

#### Determinism Considerations
- Version counter is deterministic (increments once per change)
- If source structure is deterministic, derived zones are deterministic
- No randomness or ordering issues

#### Perf Considerations
- Version check: O(1) per bar per derived detector
- Regenerate: O(k) where k = number of levels (typically 3–8)
- Active zone trim: O(max_active) per bar

---

### Option B: Structured Event Stream (NOT RECOMMENDED)

**Concept**: Emit events like `ANCHOR_CONFIRMED`, `GEOMETRY_CHANGED`, `STRUCTURE_RESET` on TF close. Derived detectors subscribe to events.

#### Implementation Sketch

```python
# New: incremental/events.py
@dataclass(frozen=True)
class StructureEvent:
    event_type: str  # "anchor_confirmed", "geometry_changed", "reset", "invalidated"
    source_key: str  # e.g., "swing"
    bar_idx: int
    payload: dict[str, Any]  # {"old_high": 50000, "new_high": 50100, ...}

class TFIncrementalState:
    def __init__(self, ...):
        self._event_queue: deque[StructureEvent] = deque(maxlen=100)  # Ring buffer
    
    def update(self, bar):
        # Existing logic
        for struct_key in self._update_order:
            old_state = self.structures[struct_key].get_value("version")
            self.structures[struct_key].update(bar)
            new_state = self.structures[struct_key].get_value("version")
            
            if old_state != new_state:
                self._event_queue.append(StructureEvent(
                    event_type="version_change",
                    source_key=struct_key,
                    bar_idx=bar.idx,
                    payload={"old_version": old_state, "new_version": new_state}
                ))
    
    def consume_events(self) -> list[StructureEvent]:
        return list(self._event_queue)
```

**Derived detector subscribes**:
```python
class IncrementalDerivedZone(BaseIncrementalDetector):
    def update(self, bar_idx: int, bar: BarData) -> None:
        events = self._state.consume_events()  # Access to TFIncrementalState
        for event in events:
            if event.source_key == "swing":
                self._regenerate_zones(bar_idx, bar, event.payload)
```

#### Pros
- **Rich context**: Event payload can carry old/new values without recomputing
- **Extensible**: Easy to add new event types (LIQUIDATION, PATTERN_MATCHED, etc.)
- **Explicit coupling**: Derived detector clearly declares what events it cares about

#### Cons
- **Requires plumbing through TFIncrementalState**: Each derived detector needs access to state object
- **Ring buffer management**: Need to decide TTL/max size to prevent unbounded growth
- **Snapshot access complexity**: RuntimeSnapshotView must expose event stream (or use different accessor)
- **Live compatibility**: Need to ensure events are emitted identically in live trading (requires event emitter in live core too)

---

### Option C: Hybrid (Version + Lightweight Events)

**Concept**: Use version for cheap TF-close gating; optionally attach event payload for rich context.

```python
@dataclass(frozen=True)
class VersionEvent:
    version: int
    bar_idx: int
    change_type: str  # "high_changed" | "low_changed" | "both"
    old_high: float | None
    new_high: float | None
    old_low: float | None
    new_low: float | None

class IncrementalSwingDetector(BaseIncrementalDetector):
    def update(self, bar_idx: int, bar: BarData) -> None:
        old_high, old_low = self.high_level, self.low_level
        # ... compute new swings ...
        
        if self.high_level != old_high or self.low_level != old_low:
            self._version += 1
            self._last_event = VersionEvent(
                version=self._version,
                bar_idx=bar_idx,
                change_type=self._classify_change(old_high, old_low),
                old_high=old_high,
                new_high=self.high_level if self.high_level != old_high else None,
                old_low=old_low,
                new_low=self.low_level if self.low_level != old_low else None,
            )
    
    def get_last_event(self) -> VersionEvent | None:
        return self._last_event
```

#### Pros
- **Best of both**: Cheap version check for gating; rich payload for complex derivations
- **Backwards compatible**: Version alone still works; payload is optional
- **Lightweight**: Only one event cached (last change), not a queue

#### Cons
- **Still requires detector changes** (same as Option A)
- **Hybrid complexity**: Derived detectors must handle both version and optional payload

---

## 4. RECOMMENDED PATH: Option A + Hybrid

**Decision**: Implement **Option A (version-based) with lightweight event payload** (essentially Option C). This is the minimal, deterministic, and live-compatible approach.

### 4.1 Exact Insertion Points

#### File 1: `/c/code/ai/trade/src/backtest/incremental/detectors/swing.py`

Add to `IncrementalSwingDetector`:

```python
class IncrementalSwingDetector(BaseIncrementalDetector):
    def __init__(self, params, deps=None):
        # ... existing ...
        self._version: int = 0  # NEW
        self._last_change_bar: int = -1  # NEW
    
    def update(self, bar_idx: int, bar: BarData) -> None:
        old_high, old_low = self.high_level, self.low_level
        # ... existing swing detection logic ...
        
        # NEW: Track version
        if self.high_level != old_high or self.low_level != old_low:
            self._version += 1
            self._last_change_bar = bar_idx
    
    def get_output_keys(self) -> list[str]:
        return ["high_level", "high_idx", "low_level", "low_idx", "version"]  # Add "version"
    
    def get_value(self, key: str) -> float | int | str:
        # ... existing logic ...
        if key == "version":
            return self._version  # NEW
        # ... rest ...
```

#### File 2: `/c/code/ai/trade/src/backtest/incremental/detectors/trend.py`

Add to `IncrementalTrendDetector`:

```python
class IncrementalTrendDetector(BaseIncrementalDetector):
    # ... existing parent_version tracking ...
    
    def get_output_keys(self) -> list[str]:
        return ["direction", "bars_in_trend", "strength", "version"]  # Expose existing version
    
    def get_value(self, key: str) -> float | int | str:
        if key == "version":
            return self._version  # Already computed, just expose
        # ... existing logic ...
```

#### File 3: `/c/code/ai/trade/src/backtest/incremental/detectors/zone.py`

Add to `IncrementalZoneDetector`:

```python
class IncrementalZoneDetector(BaseIncrementalDetector):
    def __init__(self, params, deps):
        # ... existing ...
        self._version: int = 0  # NEW
    
    def update(self, bar_idx: int, bar: BarData) -> None:
        old_state = (self.state, self.upper, self.lower)
        # ... existing zone logic ...
        
        # NEW: Increment version if state/bounds changed
        if (self.state, self.upper, self.lower) != old_state:
            self._version += 1
    
    def get_output_keys(self) -> list[str]:
        return ["state", "upper", "lower", "anchor_idx", "version"]  # Add "version"
    
    def get_value(self, key: str) -> float | int | str:
        if key == "version":
            return self._version  # NEW
        # ... existing logic ...
```

#### File 4: **NEW** `/c/code/ai/trade/src/backtest/incremental/detectors/derived_zone.py`

```python
"""
Derived zone detector for fib-based, SR-based, and order-block zones.

Subscribes to a source structure and regenerates zones when source version changes.
Maintains bounded active set with optional TTL and supersede policy.

Example IdeaCard:
    features:
      - id: "swing_1h"
        tf: "1h"
        type: structure
        structure_type: swing
        params: {left: 5, right: 5}
      
      - id: "fib_zones_1h"
        tf: "1h"
        type: structure
        structure_type: derived_zone
        depends_on:
          source: "swing_1h"
        params:
          mode: "fibonacci_zones"
          levels: [0.236, 0.382, 0.618]
          max_active: 3
          ttl_bars: null
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import math
import numpy as np

from ..base import BaseIncrementalDetector, BarData
from ..registry import register_structure
from src.backtest.market_structure.types import ZoneState

if TYPE_CHECKING:
    pass


@register_structure("derived_zone")
class IncrementalDerivedZone(BaseIncrementalDetector):
    """
    Derived zones from a source structure.
    
    Recomputes zone anchors only when source version changes.
    Maintains bounded active set with optional TTL.
    
    Parameters:
        mode: "fibonacci_zones" | "support_resistance" | "order_blocks"
        levels: [0.236, 0.382, ...] for fib; [width] for SR
        max_active: Max zones in active set (default 5)
        ttl_bars: Bars until zone auto-expires (default None = never)
        width_model: "atr_mult" | "percent" | "fixed" (default "fixed")
        width_params: params for width calculation
    
    Outputs:
        zone_count: Number of ACTIVE zones
    """
    
    REQUIRED_PARAMS = ["mode"]
    OPTIONAL_PARAMS = {
        "levels": [0.236, 0.382, 0.618, 0.786],
        "max_active": 5,
        "ttl_bars": None,
        "width_model": "fixed",
        "width_params": {"width": 100},
    }
    DEPENDS_ON = ["source"]  # String key: the source structure to derive from
    
    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """Validate derived zone parameters."""
        mode = params.get("mode")
        if mode not in ("fibonacci_zones", "support_resistance", "order_blocks"):
            raise ValueError(
                f"Structure '{key}': mode must be one of "
                f"'fibonacci_zones', 'support_resistance', 'order_blocks', got {mode!r}"
            )
    
    def __init__(self, params: dict[str, Any], deps: dict[str, BaseIncrementalDetector]) -> None:
        """Initialize derived zone detector."""
        self.source = deps["source"]
        self.mode = params["mode"]
        self.levels = params.get("levels", [0.236, 0.382, 0.618, 0.786])
        self.max_active = params.get("max_active", 5)
        self.ttl_bars = params.get("ttl_bars")
        self.width_model = params.get("width_model", "fixed")
        self.width_params = params.get("width_params", {"width": 100})
        
        self._source_version = -1
        self._active_zones: list[dict[str, Any]] = []
    
    def update(self, bar_idx: int, bar: BarData) -> None:
        """Update derived zones."""
        # Check if source changed
        try:
            source_version = self.source.get_value("version")
        except KeyError:
            # Source doesn't expose version yet (backward compat)
            return
        
        if source_version != self._source_version:
            self._source_version = source_version
            self._regenerate_zones(bar_idx, bar)
        
        # Update zone states and TTL
        for zone in self._active_zones:
            if zone["state"] == ZoneState.ACTIVE:
                # Check price break
                if bar.close < zone["lower"] or bar.close > zone["upper"]:
                    zone["state"] = ZoneState.BROKEN
                
                zone["bars_alive"] = bar_idx - zone["created_bar"]
                
                # TTL check
                if self.ttl_bars and zone["bars_alive"] >= self.ttl_bars:
                    zone["state"] = ZoneState.NONE
        
        # Remove expired zones
        self._active_zones = [z for z in self._active_zones if z["state"] != ZoneState.NONE]
    
    def _regenerate_zones(self, bar_idx: int, bar: BarData) -> None:
        """Regenerate zones from source structure."""
        if self.mode == "fibonacci_zones":
            self._regenerate_fibonacci_zones(bar_idx, bar)
        elif self.mode == "support_resistance":
            self._regenerate_sr_zones(bar_idx, bar)
        elif self.mode == "order_blocks":
            self._regenerate_ob_zones(bar_idx, bar)
    
    def _regenerate_fibonacci_zones(self, bar_idx: int, bar: BarData) -> None:
        """Create fib zones from source (usually swing)."""
        try:
            high = self.source.get_value("high_level")
            low = self.source.get_value("low_level")
        except (KeyError, ValueError):
            return
        
        if math.isnan(high) or math.isnan(low) or high <= low:
            return
        
        range_ = high - low
        new_zones = []
        
        for level in self.levels:
            level_price = high - (range_ * level)
            
            # Compute width
            width = self._compute_zone_width(bar)
            
            zone = {
                "lower": level_price - width / 2,
                "upper": level_price + width / 2,
                "anchor_idx": bar_idx,
                "anchor_price": level_price,
                "instance_id": hash((level, high, low, bar_idx)) & 0xFFFFFFFF,
                "state": ZoneState.ACTIVE,
                "created_bar": bar_idx,
                "bars_alive": 0,
                "level": level,
            }
            new_zones.append(zone)
        
        # Enforce max_active: keep oldest zones (FIFO)
        self._active_zones = new_zones + self._active_zones
        if len(self._active_zones) > self.max_active:
            self._active_zones = self._active_zones[:self.max_active]
    
    def _regenerate_sr_zones(self, bar_idx: int, bar: BarData) -> None:
        """Create support/resistance zones from source."""
        # Placeholder for future implementation
        pass
    
    def _regenerate_ob_zones(self, bar_idx: int, bar: BarData) -> None:
        """Create order block zones from source."""
        # Placeholder for future implementation
        pass
    
    def _compute_zone_width(self, bar: BarData) -> float:
        """Compute zone width based on model."""
        if self.width_model == "fixed":
            return self.width_params.get("width", 100)
        elif self.width_model == "atr_mult":
            atr = bar.indicators.get("atr", 100)
            mult = self.width_params.get("mult", 1.0)
            return float(atr) * mult
        elif self.width_model == "percent":
            pct = self.width_params.get("pct", 0.01)
            close = bar.close
            return close * pct
        return 100  # Fallback
    
    def get_output_keys(self) -> list[str]:
        """K slots pattern: zone0_lower, zone0_upper, zone0_state, zone1_*, ..."""
        keys = ["active_count"]
        for i in range(self.max_active):
            keys.extend([f"zone{i}_lower", f"zone{i}_upper", f"zone{i}_state"])
        return keys

    def get_value(self, key: str) -> float | int | str:
        if key == "active_count":
            return len([z for z in self._active_zones if z["state"] == ZoneState.ACTIVE])

        # K slots: zone0_lower, zone1_state, etc.
        if key.startswith("zone"):
            parts = key.split("_", 1)  # ["zone0", "lower"]
            slot_idx = int(parts[0][4:])  # Extract number after "zone"
            field = parts[1]  # "lower", "upper", or "state"

            if slot_idx < len(self._active_zones):
                zone = self._active_zones[slot_idx]
                if field == "lower":
                    return zone["lower"]
                elif field == "upper":
                    return zone["upper"]
                elif field == "state":
                    return zone["state"].name  # Return enum name as string
            else:
                # Slot not populated: return NaN/NONE
                if field in ("lower", "upper"):
                    return float("nan")
                elif field == "state":
                    return "NONE"

        raise KeyError(f"Unknown output key: {key}")
```

#### File 5: `/c/code/ai/trade/src/backtest/incremental/registry.py`

Update `STRUCTURE_OUTPUT_TYPES`:

```python
STRUCTURE_OUTPUT_TYPES: dict[str, dict[str, FeatureOutputType]] = {
    "swing": {
        "high_level": FeatureOutputType.FLOAT,
        "high_idx": FeatureOutputType.INT,
        "low_level": FeatureOutputType.FLOAT,
        "low_idx": FeatureOutputType.INT,
        "version": FeatureOutputType.INT,  # NEW
    },
    "trend": {
        "direction": FeatureOutputType.INT,
        "strength": FeatureOutputType.FLOAT,
        "bars_in_trend": FeatureOutputType.INT,
        "version": FeatureOutputType.INT,  # NEW
    },
    "zone": {
        "state": FeatureOutputType.ENUM,
        "upper": FeatureOutputType.FLOAT,
        "lower": FeatureOutputType.FLOAT,
        "anchor_idx": FeatureOutputType.INT,
        "version": FeatureOutputType.INT,  # NEW
    },
    "derived_zone": {  # NEW - K slots pattern (dynamic based on max_active)
        "active_count": FeatureOutputType.INT,
        "zone0_lower": FeatureOutputType.FLOAT,
        "zone0_upper": FeatureOutputType.FLOAT,
        "zone0_state": FeatureOutputType.ENUM,
        "zone1_lower": FeatureOutputType.FLOAT,
        "zone1_upper": FeatureOutputType.FLOAT,
        "zone1_state": FeatureOutputType.ENUM,
        # ... up to zoneK where K = max_active - 1
    },
    # ... existing ...
}
```

#### File 6: `/c/code/ai/trade/src/backtest/runtime/preflight.py`

Add structure warmup requirements:

```python
def compute_warmup_requirements(idea_card: "IdeaCard") -> WarmupRequirements:
    """Compute warmup bars needed for all features."""
    # ... existing indicator logic ...
    
    # NEW: Add structure requirements
    for feature in idea_card.features:
        if feature.is_structure:
            tf = feature.tf
            
            if feature.structure_type == "swing":
                left = feature.params.get("left", 5)
                right = feature.params.get("right", 5)
                bars_needed = left + right + 1
                # Update per-TF requirement
            
            elif feature.structure_type == "derived_zone":
                # Needs source structure + base_warmup
                # For now: assume 100 bars (configurable in feature.params)
                bars_needed = feature.params.get("warmup_bars", 100)
    
    # ... rest ...
```

---

### 4.2 IdeaCard Syntax for Derived Zones

**Example 1: Fibonacci Zones**

```yaml
id: fib_zone_strategy
execution_tf: "1h"

features:
  - id: swing_1h
    tf: "1h"
    type: structure
    structure_type: swing
    params:
      left: 5
      right: 5
  
  - id: fib_zones_1h
    tf: "1h"
    type: structure
    structure_type: derived_zone
    depends_on:
      source: swing_1h
    params:
      mode: fibonacci_zones
      levels: [0.236, 0.382, 0.618, 0.786]
      max_active: 3
      ttl_bars: 100  # Auto-expire after 100 bars
      width_model: atr_mult
      width_params:
        atr: atr_1h  # Reference another feature? Or bar.indicators?
        mult: 0.5

signal_rules:
  entry_rules:
    - direction: long
      conditions:
        - feature_id: fib_zones_1h
          field: zone_count
          operator: gt
          value: 0  # At least one active fib zone
```

**Example 2: Support/Resistance from Range**

```yaml
features:
  - id: range_1h
    tf: "1h"
    type: structure
    structure_type: rolling_window
    params:
      mode: high
      length: 20
  
  - id: sr_zones_1h
    tf: "1h"
    type: structure
    structure_type: derived_zone
    depends_on:
      source: range_1h
    params:
      mode: support_resistance
      width_model: percent
      width_params:
        pct: 0.002  # 0.2% width
      max_active: 4
```

---

### 4.3 Zone Interaction Integration

Once derived zones are created, integrate interaction metrics:

```python
# In incremental/detectors/derived_zone.py or new zone_interaction_detector.py

class IncrementalZoneInteraction(BaseIncrementalDetector):
    """
    Computes interaction metrics for zones from a parent zone detector.
    """
    DEPENDS_ON = ["zones"]  # Parent zone detector (zone or derived_zone)
    
    def update(self, bar_idx: int, bar: BarData) -> None:
        # Reuse ZoneInteractionComputer
        zone_outputs = self._extract_zone_arrays()
        interaction = ZoneInteractionComputer().build_batch(
            zone_outputs,
            np.array([bar.high]),
            np.array([bar.low]),
            np.array([bar.close]),
        )
        self.touched = interaction["touched"][0]
        self.inside = interaction["inside"][0]
        self.time_in_zone = interaction["time_in_zone"][0]
    
    def get_output_keys(self) -> list[str]:
        return ["touched", "inside", "time_in_zone"]
    
    def get_value(self, key: str) -> float | int | str:
        if key == "touched":
            return self.touched
        elif key == "inside":
            return self.inside
        elif key == "time_in_zone":
            return self.time_in_zone
        raise KeyError(key)
```

---

## 5. RISKS & VALIDATION

### 5.1 Failure Modes

| Risk | Mitigation |
|------|-----------|
| **Stale anchors** (source_version not updated) | Require source detector to expose version; validation at load time ensures all depends_on sources have version output |
| **Regen on every bar** (version increments incorrectly) | Version only increments when geometry actually changes; unit tests verify monotonicity |
| **TF mismatch** (derived zones on wrong TF) | Feature Registry validates; depends_on must reference feature with matching TF |
| **Unbounded zone growth** | `max_active` and `ttl_bars` cap the set; trim on every bar |
| **Determinism breaks live** | Version-based logic is TF-close only; same TF cadence in live = same version increments |
| **Perf regression** | Version check is O(1); regenerate is O(k levels) only on version change; bounded by max_active |

### 5.2 Proposed Validation Tests

**Unit Tests** (no DB, synthetic data):

```python
# tests/unit/test_derived_zone_detector.py

def test_fib_zones_regen_on_source_version_change():
    """Fib zones regenerate when source swing version increments."""
    swing = IncrementalSwingDetector({"left": 5, "right": 5})
    fib_zones = IncrementalDerivedZone(
        {"mode": "fibonacci_zones", "levels": [0.382, 0.618]},
        {"source": swing}
    )
    
    # Create some bars
    for idx in range(20):
        bar = make_test_bar(idx, high=50000+idx*100, low=49000+idx*100)
        swing.update(idx, bar)
        fib_zones.update(idx, bar)
    
    # Verify zones were created when swing changed
    assert fib_zones.get_value("zone_count") > 0
    assert all(z["state"] == ZoneState.ACTIVE for z in fib_zones._active_zones)

def test_derived_zones_respect_max_active():
    """Active zone set never exceeds max_active."""
    # ... create many swing changes ...
    assert len(fib_zones._active_zones) <= fib_zones.max_active

def test_determinism_version_increments():
    """Version counter is monotonic and matches state changes."""
    swing = IncrementalSwingDetector({"left": 5, "right": 5})
    versions = []
    for idx in range(30):
        bar = make_test_bar(idx, ...)
        swing.update(idx, bar)
        versions.append(swing.get_value("version"))
    
    # Versions are non-decreasing
    assert all(versions[i] <= versions[i+1] for i in range(len(versions)-1))
```

**Integration Tests** (with smoke test):

```bash
# In CLI (e.g., backtest structure-smoke)
python trade_cli.py backtest structure-smoke
```

Smoke test YAML:

```yaml
# configs/idea_cards/_validation/V_90_derived_zones.yml

id: V_90_derived_zones
execution_tf: "1h"

features:
  - id: swing_1h
    tf: "1h"
    type: structure
    structure_type: swing
    params: {left: 5, right: 5}
  
  - id: fib_zones
    tf: "1h"
    type: structure
    structure_type: derived_zone
    depends_on:
      source: swing_1h
    params:
      mode: fibonacci_zones
      levels: [0.236, 0.382, 0.618]
      max_active: 2

  - id: ema_12
    tf: "1h"
    type: indicator
    indicator_type: ema
    params: {length: 12}

signal_rules:
  entry_rules:
    - direction: long
      conditions:
        - feature_id: fib_zones
          field: zone_count
          operator: gt
          value: 0
        - feature_id: ema_12
          field: value
          operator: gt
          value: 49500
```

---

## 6. SUMMARY TABLE

| Aspect | Finding | Evidence |
|--------|---------|----------|
| **Existing structures** | Swing, trend, zone, fibonacci detectors fully incremental | `/c/code/ai/trade/src/backtest/incremental/detectors/` |
| **Dependency model** | Already supports `depends_on`; fibonacci proves concept | `/c/code/ai/trade/src/backtest/feature_registry.py` Feature.depends_on |
| **Event stream** | None currently exists; recommend version-based instead | `/c/code/ai/trade/src/backtest/incremental/state.py` |
| **Version tracking** | Trend detector has `parent_version`; others lack explicit version | `/c/code/ai/trade/src/backtest/incremental/detectors/trend.py` |
| **Zone interaction** | Already computed but separate from detectors | `/c/code/ai/trade/src/backtest/market_structure/zone_interaction.py` |
| **Preflight warmup** | Only covers indicators; must extend for structures | `/c/code/ai/trade/src/backtest/execution_validation.py` compute_warmup_requirements |
| **IdeaCard syntax** | Feature ID + structure_type + depends_on already supported | `/c/code/ai/trade/src/backtest/idea_card.py` Feature class |
| **Snapshot access** | `get_structure()` and `get_by_feature_id()` work for any detector | `/c/code/ai/trade/src/backtest/runtime/snapshot_view.py` |

---

## 7. NEXT STEPS

1. **Implement version counter in swing, trend, zone detectors** (File 1–3, ~50 lines per file)
2. **Create derived_zone detector** (File 4, ~250 lines)
3. **Update structure registry** (File 5, ~10 lines)
4. **Extend preflight warmup** (File 6, ~30 lines)
5. **Add IdeaCard validation** (existing `id_card_yaml_builder.py`, ~20 lines)
6. **Create validation smoke test** (new YAML file)
7. **Add unit + integration tests** (new test file, ~300 lines)

**Estimated effort**: 750–1000 lines of production code + 300 lines of tests. No breaking changes to existing detectors; pure additive.
