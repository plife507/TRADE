# Market Structure & Indicator Integration Analysis

**Generated**: Stage 5 (Zone Implementation)
**Purpose**: Document integration points between market structure and indicator modules

## Executive Summary

The market structure module (`src/backtest/market_structure/`) is architecturally **parallel and decoupled** from the indicators module (`src/backtest/features/`). Both:
- Produce numpy arrays precomputed outside the hot loop
- Store outputs in FeedStore.indicators/structures dictionaries
- Access data via RuntimeSnapshotView with O(1) semantics
- Follow the same registry pattern for type management

**Key Finding**: Stage 5 zone implementation extends existing patterns without requiring changes to indicator computation.

---

## Architecture Overview

### Shared Design Pattern

Both indicators and market structure follow the **Precompute → Store → Access** pipeline:

```
Feature/Structure Spec (YAML)
  ↓
FeatureSpec/StructureSpec (dataclass)
  ↓
FeatureFrameBuilder/StructureBuilder (vectorized computation)
  ↓
FeatureArrays/StructureArrays (numpy arrays)
  ↓
FeedStore (unified storage)
  ↓
RuntimeSnapshotView (O(1) hot loop access)
```

---

## Integration Points

### 1. FeedStore Unified Storage

Both indicators and structures stored in FeedStore:

```python
@dataclass
class FeedStore:
    # Indicator arrays (from FeatureArrays)
    indicators: Dict[str, np.ndarray]

    # Structure arrays (from StructureBuilder)
    structures: Dict[str, "StructureStore"]
    structure_key_map: Dict[str, str]
```

### 2. RuntimeSnapshotView Access

Both accessed via snapshot with O(1) semantics:

```python
# Indicators
ema_fast = snapshot.get("indicator.ema_fast")

# Structures
swing_high = snapshot.get("structure.ms_5m.swing_high_level")

# Zones (Stage 5+)
demand_lower = snapshot.get("structure.ms_5m.zones.demand_1.lower")
```

### 3. Warmup Calculation

Both contribute to max warmup calculation:
- Indicators: per-type formulas (e.g., EMA: 3× length)
- Structures: SWING uses `left + right`, TREND uses `(left+right)*5`
- Zones: inherit from parent SWING

---

## Zone Impact on Indicators

### Zone → Indicator Dependencies

| Dependency | Description | Impact |
|------------|-------------|--------|
| ATR for width | Zone may reference ATR for atr_mult width model | ATR computed first |
| No other deps | Zones only use OHLCV + swing outputs | Isolated |

### No Breaking Changes

1. ✅ Zone storage in StructureStore (already modeled)
2. ✅ FeedStore zone access methods (added in Stage 5)
3. ✅ Snapshot path resolution supports zones
4. ✅ Indicator registry unchanged

---

## Path Resolution Summary

| Path Pattern | Example | Resolution |
|--------------|---------|------------|
| `indicator.*` | `indicator.rsi_14` | FeedStore.indicators |
| `structure.*.<field>` | `structure.ms_5m.swing_high_level` | FeedStore.structures |
| `structure.*.zones.*.*` | `structure.ms_5m.zones.demand_1.lower` | FeedStore.structures → zones |
| `price.*` | `price.mark.close` | OHLCV arrays |

---

## Recommendations

1. **Keep Separate Registries**: Indicators (42) and structures (2+zones) serve different purposes
2. **Lazy ATR Resolution**: For atr_mult zones, pass ATR array to ZoneDetector if available
3. **Metadata Separation**: Indicators use IndicatorMetadata; structures use StructureManifestEntry
4. **Future**: Consider unified `feature_registry` if structure indicators grow significantly

---

## Conclusion

The indicator and market structure modules are **architecturally well-separated and mutually compatible**. Stage 5 zone implementation extends existing patterns with no breaking changes to the indicator system.
