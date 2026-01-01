# Market Structure Module Integration Proposal

**Status**: 📋 PROPOSAL  
**Created**: December 18, 2025  
**Goal**: Design and implement market structure features (swings, pivots, trends, regimes) following the same architectural pattern as indicators  
**Dependencies**: Phase 1-4 Complete ✅, P0 Input-Source Fix Complete ✅  
**Phase**: Phase 5 (Array-Backed Hot Loop)

---

## Executive Summary

This document proposes the integration of **market structure features** (swing highs/lows, pivot points, trend identification, market regimes) into the TRADE backtest engine. The design follows the same architectural pattern as the existing indicator system:

- **Precomputed** outside the hot loop (vectorized)
- **Array-based** storage (numpy arrays for O(1) access)
- **Declarative** specification (StructureSpec, similar to FeatureSpec)
- **Exposed** via RuntimeSnapshotView API
- **Timeframe-aware** (exec/htf/mtf support)

**Key Principle**: Market structure features are **first-class citizens** in the backtest system, not second-class indicators.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Design](#architecture-design)
3. [Directory Structure](#directory-structure)
4. [Core Components](#core-components)
5. [Integration Points](#integration-points)
6. [API Design](#api-design)
7. [Implementation Details](#implementation-details)
8. [Examples](#examples)
9. [Testing Strategy](#testing-strategy)
10. [Migration Plan](#migration-plan)
11. [Performance Considerations](#performance-considerations)
12. [Future Enhancements](#future-enhancements)

---

## Overview

### What is Market Structure?

Market structure refers to the **geometric patterns** in price action:

- **Swing Highs/Lows**: Local maxima/minima (peaks and valleys)
- **Pivot Points**: Significant reversal points
- **Trend Direction**: Uptrend, downtrend, sideways
- **Market Regimes**: Bull market, bear market, neutral

These features are **derived from price action** (OHLCV) but are **not indicators** in the traditional sense. They represent **structural patterns** that strategies can use for:

- Entry/exit timing
- Trend filtering
- Support/resistance identification
- Regime-based position sizing

### Why Separate from Indicators?

1. **Different Computation Model**: Structure features often require **lookback windows** and **pattern matching**, not just mathematical transforms
2. **Multi-Output Nature**: Many structure features produce **multiple outputs** (e.g., swing points produce both price and index)
3. **Timeframe Dependencies**: Structure features may need **cross-timeframe validation** (e.g., HTF trend confirms LTF swing)
4. **Declarative Requirements**: Structure features need **lookback_bars** and **delay_bars** configuration (already in MarketStructureConfig)

### Design Goals

1. ✅ **Consistency**: Follow the same pattern as indicators (FeatureSpec → FeatureFrameBuilder → FeedStore)
2. ✅ **Performance**: O(1) access in hot loop (no computation during backtest)
3. ✅ **Modularity**: Easy to add new structure types
4. ✅ **Extensibility**: New structure types don't require engine changes
5. ✅ **Testability**: Each detector can be tested independently
6. ✅ **No Lookahead**: Structure detection respects closed-candle-only rule

---

## Architecture Design

### High-Level Flow

```
IdeaCard (with structure_specs + market_structure config)
    ↓
StructureBuilder.build()  # Precompute all structure features
    ↓
StructureArrays (numpy arrays)
    ↓
Merge with FeatureArrays (from FeatureFrameBuilder)
    ↓
FeedStore (includes both indicators + structure features)
    ↓
RuntimeSnapshotView.get_structure()  # O(1) access in hot loop
```

### Comparison: Indicators vs Market Structure

| Aspect | Indicators | Market Structure |
|--------|-----------|------------------|
| **Computation** | Mathematical transforms (EMA, RSI, etc.) | Pattern detection (swings, pivots, trends) |
| **Input** | OHLCV + other indicators | OHLCV only (price action) |
| **Output** | Single or multi-value series | Multi-value (price, index, strength, etc.) |
| **Warmup** | Indicator-specific (e.g., EMA needs length) | Lookback-based (e.g., swing needs 50 bars) |
| **Timeframe** | Computed per TF independently | May need cross-TF validation |
| **Specification** | FeatureSpec | StructureSpec |
| **Builder** | FeatureFrameBuilder | StructureBuilder |
| **Storage** | FeatureArrays | StructureArrays (merged) |
| **Access** | `snapshot.get_feature()` | `snapshot.get_structure()` |

### Key Architectural Decisions

1. **Separate Module**: Market structure lives in `src/backtest/market_structure/` (not mixed with indicators)
2. **Parallel Pipeline**: Structure features computed **alongside** indicators, then merged
3. **Unified Storage**: Both indicators and structure features stored in same FeedStore arrays
4. **Unified Access**: RuntimeSnapshotView provides both `get_feature()` and `get_structure()` methods
5. **Declarative Config**: StructureSpec declares what to compute (like FeatureSpec)

---

## Directory Structure

### Proposed Layout

```
src/backtest/
├── features/                    # Existing indicator system
│   ├── __init__.py
│   ├── feature_spec.py         # FeatureSpec, IndicatorType
│   ├── feature_frame_builder.py
│   └── ...
│
├── market_structure/           # NEW: Market structure module
│   ├── __init__.py
│   ├── structure_spec.py       # StructureSpec, StructureSpecSet
│   ├── structure_types.py      # StructureType enum
│   ├── structure_builder.py    # StructureBuilder (main orchestrator)
│   ├── detectors/              # Structure detection algorithms
│   │   ├── __init__.py
│   │   ├── swing_detector.py   # Swing high/low detection
│   │   ├── pivot_detector.py   # Pivot point detection
│   │   ├── trend_detector.py   # Trend identification
│   │   └── regime_detector.py  # Market regime classification
│   ├── utils.py                # Helper functions (validation, etc.)
│   └── types.py                # Structure-specific types (SwingPoint, etc.)
│
├── runtime/                    # Existing runtime
│   ├── feed_store.py           # FeedStore (will store structure arrays)
│   ├── snapshot_view.py        # RuntimeSnapshotView (will add get_structure())
│   └── ...
│
└── engine.py                   # BacktestEngine (will integrate StructureBuilder)
```

### File Responsibilities

| File | Responsibility |
|------|---------------|
| `structure_spec.py` | StructureSpec dataclass, StructureSpecSet collection |
| `structure_types.py` | StructureType enum (swing_high, pivot, trend, etc.) |
| `structure_builder.py` | Main orchestrator (like FeatureFrameBuilder) |
| `detectors/swing_detector.py` | Swing high/low detection algorithm |
| `detectors/pivot_detector.py` | Pivot point detection algorithm |
| `detectors/trend_detector.py` | Trend direction/strength computation |
| `detectors/regime_detector.py` | Market regime classification |
| `utils.py` | Validation, helper functions |
| `types.py` | Structure-specific dataclasses (SwingPoint, PivotPoint, etc.) |

---

## Core Components

### 1. StructureType Enum

```python
# src/backtest/market_structure/structure_types.py

from enum import Enum

class StructureType(str, Enum):
    """
    Market structure feature types.
    
    Each type represents a different structural pattern in price action.
    """
    
    # =========================================================================
    # SWING DETECTION
    # =========================================================================
    SWING_HIGH = "swing_high"           # Local maxima (peaks)
    SWING_LOW = "swing_low"             # Local minima (valleys)
    SWING_POINTS = "swing_points"       # Both (multi-output: high, low)
    
    # =========================================================================
    # PIVOT POINTS
    # =========================================================================
    PIVOT_HIGH = "pivot_high"           # Significant pivot high
    PIVOT_LOW = "pivot_low"            # Significant pivot low
    PIVOT_POINTS = "pivot_points"      # Both (multi-output: high, low)
    
    # =========================================================================
    # TREND IDENTIFICATION
    # =========================================================================
    TREND_DIRECTION = "trend_direction" # Uptrend/Downtrend/Sideways (enum)
    TREND_STRENGTH = "trend_strength"   # Trend strength score (0-100)
    TREND_LINE = "trend_line"           # Trend line slope/intercept
    
    # =========================================================================
    # MARKET REGIMES
    # =========================================================================
    REGIME = "regime"                   # Bull/Bear/Neutral regime
    VOLATILITY_REGIME = "volatility_regime"  # High/Low volatility regime
    MOMENTUM_REGIME = "momentum_regime"      # Momentum-based regime
    
    # =========================================================================
    # SUPPORT/RESISTANCE
    # =========================================================================
    SUPPORT_LEVEL = "support_level"     # Support price level
    RESISTANCE_LEVEL = "resistance_level"  # Resistance price level
    S_R_LEVELS = "sr_levels"            # Both (multi-output)
```

### 2. StructureSpec

```python
# src/backtest/market_structure/structure_spec.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .structure_types import StructureType

@dataclass(frozen=True)
class StructureSpec:
    """
    Declarative market structure specification.
    
    Similar to FeatureSpec but for structure features:
    - structure_type: What structure to compute (swing_high, pivot, trend, etc.)
    - params: Parameters (lookback, threshold, min_strength, etc.)
    - output_key: Name for the structure feature
    - tf_role: Which timeframe (exec, htf, mtf)
    
    Example:
        spec = StructureSpec(
            structure_type=StructureType.SWING_HIGH,
            output_key="swing_high_50",
            params={"lookback": 50, "min_strength": 2.0},
            tf_role="exec"
        )
    """
    structure_type: StructureType
    output_key: str
    params: Dict[str, Any] = field(default_factory=dict)
    tf_role: str = "exec"
    
    def __post_init__(self):
        """Validate structure spec."""
        if not self.output_key:
            raise ValueError("output_key cannot be empty")
        if not isinstance(self.structure_type, StructureType):
            raise ValueError(f"Invalid structure_type: {self.structure_type}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "structure_type": self.structure_type.value,
            "output_key": self.output_key,
            "params": self.params,
            "tf_role": self.tf_role,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StructureSpec":
        """Deserialize from dict."""
        return cls(
            structure_type=StructureType(d["structure_type"]),
            output_key=d["output_key"],
            params=d.get("params", {}),
            tf_role=d.get("tf_role", "exec"),
        )


@dataclass
class StructureSpecSet:
    """
    Collection of StructureSpecs for a single timeframe role.
    
    Similar to FeatureSpecSet but for structure features.
    """
    symbol: str
    tf: str
    tf_role: str
    specs: list[StructureSpec] = field(default_factory=list)
    
    def add(self, spec: StructureSpec):
        """Add a structure spec."""
        if spec.tf_role != self.tf_role:
            raise ValueError(
                f"StructureSpec tf_role ({spec.tf_role}) must match "
                f"StructureSpecSet tf_role ({self.tf_role})"
            )
        self.specs.append(spec)
    
    def get_by_key(self, output_key: str) -> Optional[StructureSpec]:
        """Get spec by output_key."""
        for spec in self.specs:
            if spec.output_key == output_key:
                return spec
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "tf_role": self.tf_role,
            "specs": [spec.to_dict() for spec in self.specs],
        }
```

### 3. StructureArrays

```python
# src/backtest/market_structure/structure_builder.py

from dataclasses import dataclass
from typing import Dict
import numpy as np

@dataclass
class StructureArrays:
    """
    Container for precomputed structure feature arrays.
    
    Similar to FeatureArrays but for structure features.
    All arrays are numpy arrays (float32 preferred) for O(1) access.
    """
    symbol: str
    tf: str
    tf_role: str
    arrays: Dict[str, np.ndarray]  # output_key -> numpy array
    length: int
    lookback_bars: int  # Required lookback for structure computation
    
    def get(self, key: str) -> np.ndarray:
        """Get structure array by key."""
        if key not in self.arrays:
            raise KeyError(f"Structure feature '{key}' not found. Available: {list(self.arrays.keys())}")
        return self.arrays[key]
    
    def has(self, key: str) -> bool:
        """Check if structure feature exists."""
        return key in self.arrays
    
    def keys(self) -> list[str]:
        """Get all structure feature keys."""
        return list(self.arrays.keys())
```

### 4. StructureBuilder

```python
# src/backtest/market_structure/structure_builder.py

import pandas as pd
import numpy as np
from typing import Dict, Optional
from .structure_spec import StructureSpec, StructureSpecSet, StructureArrays
from .structure_types import StructureType
from .detectors.swing_detector import SwingDetector
from .detectors.pivot_detector import PivotDetector
from .detectors.trend_detector import TrendDetector
from .detectors.regime_detector import RegimeDetector

class StructureBuilder:
    """
    Builder that computes market structure features.
    
    Similar to FeatureFrameBuilder but for structure:
    - Takes OHLCV DataFrame + StructureSpecSet
    - Computes all structure features in one pass
    - Returns StructureArrays (numpy arrays)
    - All computation OUTSIDE hot loop
    
    Usage:
        builder = StructureBuilder()
        arrays = builder.build(df, spec_set, tf_role="exec")
        
        # Access arrays
        swing_highs = arrays.get("swing_high_50")
        trend_dir = arrays.get("trend_15m")
    """
    
    def __init__(self, prefer_float32: bool = True):
        """
        Initialize builder.
        
        Args:
            prefer_float32: If True, convert arrays to float32 (default: True)
        """
        self.prefer_float32 = prefer_float32
        
        # Initialize detectors
        self.swing_detector = SwingDetector()
        self.pivot_detector = PivotDetector()
        self.trend_detector = TrendDetector()
        self.regime_detector = RegimeDetector()
    
    def build(
        self,
        df: pd.DataFrame,
        spec_set: StructureSpecSet,
        tf_role: str = "exec",
    ) -> StructureArrays:
        """
        Compute all structure features from StructureSpecSet.
        
        Args:
            df: OHLCV DataFrame with columns: open, high, low, close, volume
            spec_set: StructureSpecSet with specs to compute
            tf_role: Timeframe role (exec, htf, mtf)
            
        Returns:
            StructureArrays with numpy arrays for each structure feature
            
        Raises:
            ValueError: If required columns missing or invalid spec
        """
        # Validate inputs
        required_cols = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        if not spec_set.specs:
            # Empty spec set - return empty arrays
            return StructureArrays(
                symbol=spec_set.symbol,
                tf=spec_set.tf,
                tf_role=tf_role,
                arrays={},
                length=len(df),
                lookback_bars=0,
            )
        
        # Compute all structure features
        arrays: Dict[str, np.ndarray] = {}
        max_lookback = 0
        
        for spec in spec_set.specs:
            # Compute structure feature
            result = self._compute_structure(spec, df)
            
            # Store arrays (handle multi-output)
            if isinstance(result, dict):
                # Multi-output structure (e.g., swing_points)
                for output_name, array in result.items():
                    key = spec.get_output_key(output_name) if hasattr(spec, 'get_output_key') else f"{spec.output_key}_{output_name}"
                    arrays[key] = self._convert_array(array)
            else:
                # Single-output structure
                arrays[spec.output_key] = self._convert_array(result)
            
            # Track max lookback
            lookback = spec.params.get("lookback", 0)
            max_lookback = max(max_lookback, lookback)
        
        return StructureArrays(
            symbol=spec_set.specs[0].tf_role if spec_set.specs else spec_set.symbol,
            tf=spec_set.tf,
            tf_role=tf_role,
            arrays=arrays,
            length=len(df),
            lookback_bars=max_lookback,
        )
    
    def _compute_structure(
        self,
        spec: StructureSpec,
        df: pd.DataFrame,
    ) -> Union[np.ndarray, Dict[str, np.ndarray]]:
        """
        Compute a single structure feature.
        
        Routes to appropriate detector based on structure_type.
        """
        stype = spec.structure_type
        
        if stype in (StructureType.SWING_HIGH, StructureType.SWING_LOW, StructureType.SWING_POINTS):
            return self.swing_detector.detect(df, spec)
        elif stype in (StructureType.PIVOT_HIGH, StructureType.PIVOT_LOW, StructureType.PIVOT_POINTS):
            return self.pivot_detector.detect(df, spec)
        elif stype in (StructureType.TREND_DIRECTION, StructureType.TREND_STRENGTH, StructureType.TREND_LINE):
            return self.trend_detector.detect(df, spec)
        elif stype in (StructureType.REGIME, StructureType.VOLATILITY_REGIME, StructureType.MOMENTUM_REGIME):
            return self.regime_detector.detect(df, spec)
        else:
            raise ValueError(f"Unknown structure type: {stype}")
    
    def _convert_array(self, array: np.ndarray) -> np.ndarray:
        """Convert array to float32 if preferred."""
        if self.prefer_float32 and array.dtype != np.float32:
            return array.astype(np.float32)
        return array
```

### 5. Detector Interface

```python
# src/backtest/market_structure/detectors/base_detector.py

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Union, Dict
from ..structure_spec import StructureSpec

class BaseDetector(ABC):
    """
    Base class for structure detectors.
    
    All detectors must implement detect() method.
    """
    
    @abstractmethod
    def detect(
        self,
        df: pd.DataFrame,
        spec: StructureSpec,
    ) -> Union[np.ndarray, Dict[str, np.ndarray]]:
        """
        Detect structure feature from OHLCV data.
        
        Args:
            df: OHLCV DataFrame
            spec: StructureSpec with parameters
            
        Returns:
            Single array for single-output, dict of arrays for multi-output
        """
        pass
```

### 6. Example Detector: SwingDetector

```python
# src/backtest/market_structure/detectors/swing_detector.py

import pandas as pd
import numpy as np
from typing import Union, Dict
from .base_detector import BaseDetector
from ..structure_spec import StructureSpec
from ..structure_types import StructureType

class SwingDetector(BaseDetector):
    """
    Detects swing highs and swing lows.
    
    Algorithm:
    1. Find local maxima (swing highs) and minima (swing lows)
    2. Filter by minimum strength (price distance from neighbors)
    3. Return array of swing point prices (NaN where no swing)
    """
    
    def detect(
        self,
        df: pd.DataFrame,
        spec: StructureSpec,
    ) -> Union[np.ndarray, Dict[str, np.ndarray]]:
        """
        Detect swing points.
        
        Returns:
            - Single array for SWING_HIGH or SWING_LOW
            - Dict with 'high' and 'low' arrays for SWING_POINTS
        """
        lookback = spec.params.get("lookback", 10)
        min_strength = spec.params.get("min_strength", 0.0)
        
        high = df["high"].values
        low = df["low"].values
        
        if spec.structure_type == StructureType.SWING_HIGH:
            return self._detect_swing_highs(high, lookback, min_strength)
        elif spec.structure_type == StructureType.SWING_LOW:
            return self._detect_swing_lows(low, lookback, min_strength)
        elif spec.structure_type == StructureType.SWING_POINTS:
            highs = self._detect_swing_highs(high, lookback, min_strength)
            lows = self._detect_swing_lows(low, lookback, min_strength)
            return {"high": highs, "low": lows}
        else:
            raise ValueError(f"Invalid structure type for SwingDetector: {spec.structure_type}")
    
    def _detect_swing_highs(
        self,
        high: np.ndarray,
        lookback: int,
        min_strength: float,
    ) -> np.ndarray:
        """Detect swing highs (local maxima)."""
        n = len(high)
        swings = np.full(n, np.nan, dtype=np.float32)
        
        for i in range(lookback, n - lookback):
            # Check if this is a local maximum
            is_max = True
            for j in range(i - lookback, i + lookback + 1):
                if j != i and high[j] >= high[i]:
                    is_max = False
                    break
            
            if is_max:
                # Check minimum strength
                left_min = np.min(high[max(0, i - lookback):i])
                right_min = np.min(high[i+1:min(n, i + lookback + 1)])
                strength = high[i] - max(left_min, right_min)
                
                if strength >= min_strength:
                    swings[i] = high[i]
        
        return swings
    
    def _detect_swing_lows(
        self,
        low: np.ndarray,
        lookback: int,
        min_strength: float,
    ) -> np.ndarray:
        """Detect swing lows (local minima)."""
        n = len(low)
        swings = np.full(n, np.nan, dtype=np.float32)
        
        for i in range(lookback, n - lookback):
            # Check if this is a local minimum
            is_min = True
            for j in range(i - lookback, i + lookback + 1):
                if j != i and low[j] <= low[i]:
                    is_min = False
                    break
            
            if is_min:
                # Check minimum strength
                left_max = np.max(low[max(0, i - lookback):i])
                right_max = np.max(low[i+1:min(n, i + lookback + 1)])
                strength = min(left_max, right_max) - low[i]
                
                if strength >= min_strength:
                    swings[i] = low[i]
        
        return swings
```

---

## Integration Points

### 1. IdeaCard Schema Extension

```yaml
# configs/idea_cards/example_with_structure.yml

id: "BTCUSDT_15m_swing_trend"
version: "1.0"

symbol: "BTCUSDT"
position_policy: "long_short"

tf_configs:
  exec:
    timeframe: "15m"
    feature_specs:
      - indicator_type: "ema"
        output_key: "ema_fast"
        params:
          length: 9
      - indicator_type: "ema"
        output_key: "ema_slow"
        params:
          length: 21
    market_structure:
      lookback_bars: 50      # Additional bars for structure analysis
      delay_bars: 5          # Bars to skip at evaluation start
    structure_specs:         # NEW: Market structure features
      - structure_type: "swing_high"
        output_key: "swing_high_50"
        params:
          lookback: 50
          min_strength: 2.0
      - structure_type: "swing_low"
        output_key: "swing_low_50"
        params:
          lookback: 50
          min_strength: 2.0
      - structure_type: "trend_direction"
        output_key: "trend_15m"
        params:
          lookback: 20
  htf:
    timeframe: "4h"
    feature_specs:
      - indicator_type: "ema"
        output_key: "htf_ema_trend"
        params:
          length: 50
    structure_specs:
      - structure_type: "trend_direction"
        output_key: "htf_trend"
        params:
          lookback: 10

account:
  starting_equity_usdt: 1000.0
  max_leverage: 10.0

risk_model:
  stop_loss:
    type: "percent"
    value: 2.0
  take_profit:
    type: "rr_ratio"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 1.0
    max_leverage: 3.0

signal_rules:
  conditions:
    - tf: "exec"
      indicator_key: "ema_fast"
      operator: "cross_above"
      value: "ema_slow"
      is_indicator_comparison: true
    - tf: "exec"
      structure_key: "trend_15m"      # NEW: Structure feature access
      operator: "equals"
      value: "uptrend"
    - tf: "htf"
      structure_key: "htf_trend"     # NEW: HTF structure feature
      operator: "equals"
      value: "uptrend"
```

### 2. Engine Integration

```python
# src/backtest/engine.py (additions)

from .market_structure import StructureBuilder, StructureSpecSet
from .market_structure.structure_spec import StructureSpec
from .features.feature_frame_builder import FeatureFrameBuilder, FeatureArrays

class BacktestEngine:
    """
    Add structure feature computation to engine.
    """
    
    def _build_feature_and_structure_arrays(
        self,
        df: pd.DataFrame,
        tf_role: str,
        feature_spec_set: FeatureSpecSet,
        structure_spec_set: Optional[StructureSpecSet],
    ) -> FeatureArrays:
        """
        Build both indicator and structure feature arrays.
        
        Returns merged FeatureArrays (indicators + structure features).
        """
        # Build indicator arrays (existing)
        feature_builder = FeatureFrameBuilder()
        feature_arrays = feature_builder.build(df, feature_spec_set, tf_role=tf_role)
        
        # Build structure arrays (new)
        if structure_spec_set and structure_spec_set.specs:
            structure_builder = StructureBuilder()
            structure_arrays = structure_builder.build(df, structure_spec_set, tf_role=tf_role)
            
            # Merge structure arrays into feature arrays
            for key, array in structure_arrays.arrays.items():
                feature_arrays.arrays[key] = array
            
            # Update lookback (max of indicator and structure lookback)
            feature_arrays.warmup_bars = max(
                feature_arrays.warmup_bars,
                structure_arrays.lookback_bars,
            )
        
        return feature_arrays
```

### 3. FeedStore Integration

```python
# src/backtest/runtime/feed_store.py (additions)

class FeedStore:
    """
    FeedStore already stores arrays in self.indicators dict.
    Structure features will be stored in the same dict (no changes needed).
    """
    
    # No changes required - structure arrays are merged into FeatureArrays
    # before FeedStore creation, so they're already in self.indicators
```

### 4. RuntimeSnapshotView Integration

```python
# src/backtest/runtime/snapshot_view.py (additions)

class RuntimeSnapshotView:
    """
    Add structure feature access methods.
    """
    
    def get_structure(
        self,
        key: str,
        tf_role: str = "exec",
        offset: int = 0,
    ) -> float:
        """
        Get market structure feature value.
        
        Similar to get_feature() but semantically for structure features.
        O(1) array access via FeedStore.
        
        Args:
            key: Structure feature output_key (e.g., "swing_high_50")
            tf_role: Timeframe role (exec, htf, mtf)
            offset: Bar offset (0 = current, 1 = previous, etc.)
            
        Returns:
            Structure feature value (float, or NaN if not available)
            
        Raises:
            KeyError: If structure feature not found
        """
        # Structure features are stored in same arrays as indicators
        # So we can use the same get_feature() method
        return self.get_feature(key=key, tf_role=tf_role, offset=offset)
    
    def has_structure(
        self,
        key: str,
        tf_role: str = "exec",
    ) -> bool:
        """
        Check if structure feature exists.
        
        Args:
            key: Structure feature output_key
            tf_role: Timeframe role
            
        Returns:
            True if structure feature exists, False otherwise
        """
        return self.has_feature(key=key, tf_role=tf_role)
    
    def get_structure_index(
        self,
        key: str,
        tf_role: str = "exec",
        offset: int = 0,
    ) -> Optional[int]:
        """
        Get index of structure point (for swing/pivot points).
        
        Some structure features (swings, pivots) may have index arrays
        that indicate where the structure point occurred.
        
        Args:
            key: Structure feature output_key (e.g., "swing_high_50")
            tf_role: Timeframe role
            offset: Bar offset
            
        Returns:
            Index of structure point, or None if not available
        """
        index_key = f"{key}_index"
        if self.has_feature(index_key, tf_role):
            idx = self.get_feature(index_key, tf_role, offset)
            return int(idx) if not np.isnan(idx) else None
        return None
```

### 5. IdeaCard Parser Integration

```python
# src/backtest/idea_card.py (additions)

from .market_structure.structure_spec import StructureSpec, StructureSpecSet
from .market_structure.structure_types import StructureType

@dataclass(frozen=True)
class TimeframeConfig:
    """
    Add structure_specs field.
    """
    # ... existing fields ...
    structure_specs: Optional[list[StructureSpec]] = None
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimeframeConfig":
        """Parse structure_specs from YAML."""
        # ... existing parsing ...
        
        # Parse structure_specs
        structure_specs = None
        if "structure_specs" in d and d["structure_specs"]:
            structure_specs = [
                StructureSpec.from_dict(spec_dict)
                for spec_dict in d["structure_specs"]
            ]
        
        return cls(
            # ... existing fields ...
            structure_specs=structure_specs,
        )
```

---

## API Design

### Structure Feature Access in Strategies

```python
# Example: Strategy using structure features

def evaluate(self, snapshot: RuntimeSnapshotView) -> Optional[Signal]:
    """
    Strategy evaluation using structure features.
    """
    # Get current trend direction
    trend = snapshot.get_structure("trend_15m", tf_role="exec")
    
    # Get latest swing high
    swing_high = snapshot.get_structure("swing_high_50", tf_role="exec", offset=0)
    prev_swing_high = snapshot.get_structure("swing_high_50", tf_role="exec", offset=1)
    
    # Get HTF trend for confirmation
    htf_trend = snapshot.get_structure("htf_trend", tf_role="htf")
    
    # Entry logic: Uptrend + higher swing high + HTF uptrend
    if (trend == "uptrend" and 
        not np.isnan(swing_high) and 
        not np.isnan(prev_swing_high) and
        swing_high > prev_swing_high and
        htf_trend == "uptrend"):
        return Signal(
            side=SignalSide.LONG,
            size_usdt=100.0,
            # ...
        )
    
    return None
```

### Signal Rules Integration

```yaml
# IdeaCard signal rules with structure features

signal_rules:
  conditions:
    # Indicator-based condition (existing)
    - tf: "exec"
      indicator_key: "ema_fast"
      operator: "cross_above"
      value: "ema_slow"
      is_indicator_comparison: true
    
    # Structure-based condition (new)
    - tf: "exec"
      structure_key: "trend_15m"
      operator: "equals"
      value: "uptrend"
    
    # Combined: structure + indicator
    - tf: "exec"
      structure_key: "swing_high_50"
      operator: "greater_than"
      value: "prev_swing_high_50"  # Reference to previous value
      is_structure_comparison: true
```

---

## Implementation Details

### 1. Lookback and Delay Bars

Market structure features require **lookback bars** for computation:

```python
# Structure features need lookback for pattern detection
structure_spec = StructureSpec(
    structure_type=StructureType.SWING_HIGH,
    output_key="swing_high_50",
    params={"lookback": 50},  # Need 50 bars to detect swing
)

# This is handled by MarketStructureConfig.lookback_bars
# Engine expands data window: data_start = window_start - lookback_bars
```

**Delay bars** ensure no lookahead:

```python
# Delay bars skip bars at evaluation start
# eval_start = aligned_start + delay_bars
# This ensures structure features don't "see" future data
```

### 2. Multi-Output Structure Features

Some structure features produce multiple outputs:

```python
# Example: Swing points produce both high and low arrays
spec = StructureSpec(
    structure_type=StructureType.SWING_POINTS,
    output_key: "swings",
    params={"lookback": 50},
)

# Result: Dict with "swings_high" and "swings_low" arrays
result = {
    "swings_high": np.array([...]),  # Swing high prices
    "swings_low": np.array([...]),   # Swing low prices
}
```

### 3. NaN Handling

Structure features use NaN to indicate "no structure point":

```python
# Swing high array example
swing_highs = np.array([
    np.nan,  # No swing at bar 0
    np.nan,  # No swing at bar 1
    42850.0, # Swing high at bar 2
    np.nan,  # No swing at bar 3
    np.nan,  # No swing at bar 4
    43200.0, # Swing high at bar 5
    # ...
])

# Access in snapshot
current_swing = snapshot.get_structure("swing_high_50")
if not np.isnan(current_swing):
    # There's a swing high at current bar
    pass
```

### 4. Timeframe Support

Structure features support exec/htf/mtf:

```python
# Structure features can be computed on any timeframe
spec_set_exec = StructureSpecSet(
    symbol="BTCUSDT",
    tf="15m",
    tf_role="exec",
    specs=[...],
)

spec_set_htf = StructureSpecSet(
    symbol="BTCUSDT",
    tf="4h",
    tf_role="htf",
    specs=[...],
)

# Access in snapshot
exec_trend = snapshot.get_structure("trend_15m", tf_role="exec")
htf_trend = snapshot.get_structure("htf_trend", tf_role="htf")
```

---

## Examples

### Example 1: Swing-Based Strategy

```yaml
# configs/idea_cards/swing_momentum.yml

id: "BTCUSDT_15m_swing_momentum"
symbol: "BTCUSDT"
position_policy: "long_short"

tf_configs:
  exec:
    timeframe: "15m"
    feature_specs:
      - indicator_type: "rsi"
        output_key: "rsi_14"
        params:
          length: 14
    market_structure:
      lookback_bars: 50
      delay_bars: 5
    structure_specs:
      - structure_type: "swing_high"
        output_key: "swing_high_50"
        params:
          lookback: 50
          min_strength: 1.0
      - structure_type: "swing_low"
        output_key: "swing_low_50"
        params:
          lookback: 50
          min_strength: 1.0

signal_rules:
  conditions:
    # Long: RSI oversold + higher swing low
    - tf: "exec"
      indicator_key: "rsi_14"
      operator: "less_than"
      value: 30
    - tf: "exec"
      structure_key: "swing_low_50"
      operator: "greater_than"
      value: "prev_swing_low_50"
      is_structure_comparison: true
```

### Example 2: Trend-Filtered Strategy

```yaml
# configs/idea_cards/trend_filtered_ema.yml

id: "BTCUSDT_15m_trend_filtered"
symbol: "BTCUSDT"
position_policy: "long_only"

tf_configs:
  exec:
    timeframe: "15m"
    feature_specs:
      - indicator_type: "ema"
        output_key: "ema_fast"
        params:
          length: 9
      - indicator_type: "ema"
        output_key: "ema_slow"
        params:
          length: 21
    structure_specs:
      - structure_type: "trend_direction"
        output_key: "trend_15m"
        params:
          lookback: 20
  htf:
    timeframe: "4h"
    structure_specs:
      - structure_type: "trend_direction"
        output_key: "htf_trend"
        params:
          lookback: 10

signal_rules:
  conditions:
    # EMA crossover
    - tf: "exec"
      indicator_key: "ema_fast"
      operator: "cross_above"
      value: "ema_slow"
      is_indicator_comparison: true
    # Trend filter: Only trade in uptrend
    - tf: "exec"
      structure_key: "trend_15m"
      operator: "equals"
      value: "uptrend"
    # HTF confirmation
    - tf: "htf"
      structure_key: "htf_trend"
      operator: "equals"
      value: "uptrend"
```

### Example 3: Regime-Based Strategy

```yaml
# configs/idea_cards/regime_adaptive.yml

id: "BTCUSDT_15m_regime_adaptive"
symbol: "BTCUSDT"
position_policy: "long_short"

tf_configs:
  exec:
    timeframe: "15m"
    feature_specs:
      - indicator_type: "rsi"
        output_key: "rsi_14"
        params:
          length: 14
    structure_specs:
      - structure_type: "regime"
        output_key: "market_regime"
        params:
          lookback: 50
          method: "trend_based"

signal_rules:
  conditions:
    # Bull regime: Only longs
    - tf: "exec"
      structure_key: "market_regime"
      operator: "equals"
      value: "bull"
    - tf: "exec"
      indicator_key: "rsi_14"
      operator: "less_than"
      value: 40
```

---

## Testing Strategy

### 1. Unit Tests (Per Detector)

```python
# tests/market_structure/test_swing_detector.py

def test_swing_high_detection():
    """Test swing high detection."""
    detector = SwingDetector()
    df = create_test_ohlcv()  # Create test data with known swings
    
    spec = StructureSpec(
        structure_type=StructureType.SWING_HIGH,
        output_key="swing_high_10",
        params={"lookback": 10, "min_strength": 1.0},
    )
    
    result = detector.detect(df, spec)
    
    # Verify known swing highs are detected
    assert result[20] == 42850.0  # Known swing high at index 20
    assert np.isnan(result[10])    # No swing at index 10
```

### 2. Integration Tests (StructureBuilder)

```python
# tests/market_structure/test_structure_builder.py

def test_structure_builder_integration():
    """Test StructureBuilder with multiple specs."""
    builder = StructureBuilder()
    df = create_test_ohlcv()
    
    spec_set = StructureSpecSet(
        symbol="BTCUSDT",
        tf="15m",
        tf_role="exec",
        specs=[
            StructureSpec(StructureType.SWING_HIGH, "swing_high_50", {"lookback": 50}),
            StructureSpec(StructureType.TREND_DIRECTION, "trend_15m", {"lookback": 20}),
        ],
    )
    
    arrays = builder.build(df, spec_set)
    
    assert arrays.has("swing_high_50")
    assert arrays.has("trend_15m")
    assert len(arrays.get("swing_high_50")) == len(df)
```

### 3. End-to-End Tests (Engine Integration)

```python
# tests/integration/test_market_structure_integration.py

def test_backtest_with_structure_features():
    """Test full backtest with structure features."""
    idea_card = load_idea_card("swing_momentum.yml")
    
    result = run_backtest(
        idea_card=idea_card,
        start="2024-01-01",
        end="2024-01-31",
    )
    
    # Verify backtest completed
    assert result.metrics.total_trades > 0
    
    # Verify structure features were computed
    assert "swing_high_50" in result.feature_keys
    assert "swing_low_50" in result.feature_keys
```

### 4. Parity Tests (Structure vs Reference)

```python
# tests/market_structure/test_structure_parity.py

def test_swing_detection_parity():
    """Test swing detection matches reference implementation."""
    df = load_reference_data()
    
    # Compute with our detector
    detector = SwingDetector()
    our_result = detector.detect(df, spec)
    
    # Compute with reference (e.g., TradingView script)
    reference_result = load_reference_swings()
    
    # Compare (allow small tolerance for floating point)
    np.testing.assert_allclose(our_result, reference_result, rtol=1e-5)
```

---

## Migration Plan

### Phase 5.1: Foundation (Week 1)

- [ ] Create `src/backtest/market_structure/` directory
- [ ] Implement `StructureType` enum
- [ ] Implement `StructureSpec` and `StructureSpecSet`
- [ ] Implement `StructureArrays`
- [ ] Create base detector interface
- [ ] Add unit tests for core types

### Phase 5.2: Detectors (Week 2)

- [ ] Implement `SwingDetector` (swing high/low)
- [ ] Implement `PivotDetector` (pivot points)
- [ ] Implement `TrendDetector` (trend direction/strength)
- [ ] Implement `RegimeDetector` (market regimes)
- [ ] Add unit tests for each detector
- [ ] Add parity tests vs reference implementations

### Phase 5.3: Builder Integration (Week 3)

- [ ] Implement `StructureBuilder`
- [ ] Integrate with `FeatureFrameBuilder` (merge arrays)
- [ ] Update `BacktestEngine` to compute structure features
- [ ] Update `FeedStore` to store structure arrays
- [ ] Add integration tests

### Phase 5.4: Runtime Integration (Week 4)

- [ ] Extend `RuntimeSnapshotView` with `get_structure()` method
- [ ] Update `IdeaCard` parser to support `structure_specs`
- [ ] Update `IdeaCardSignalEvaluator` to support structure conditions
- [ ] Add end-to-end tests

### Phase 5.5: Validation & Documentation (Week 5)

- [ ] Add structure parity audit (similar to indicator parity)
- [ ] Update CLI commands for structure features
- [ ] Create example IdeaCards with structure features
- [ ] Update documentation
- [ ] Performance benchmarking

---

## Performance Considerations

### Memory Usage

- **Structure arrays**: Same memory footprint as indicators (float32 arrays)
- **Multi-output structures**: Additional arrays (e.g., swing_points = 2 arrays)
- **Estimated overhead**: ~10-20% for typical structure feature set

### Computation Time

- **Precomputation**: All structure features computed before hot loop
- **Swing detection**: O(n × lookback) where n = bars, lookback = window size
- **Trend detection**: O(n) (linear scan)
- **Regime detection**: O(n) (linear scan)
- **Estimated overhead**: ~5-10% for typical structure feature set

### Hot Loop Performance

- **Access time**: O(1) array indexing (same as indicators)
- **No overhead**: Structure features accessed same way as indicators
- **No impact**: Zero performance impact on hot loop

### Optimization Opportunities

1. **Vectorized swing detection**: Use numpy operations instead of loops
2. **Caching**: Cache structure computations for repeated IdeaCards
3. **Parallel computation**: Compute structure features in parallel (future)

---

## Future Enhancements

### Phase 6: Advanced Structure Features

- [ ] **Support/Resistance Levels**: Automatic S/R level detection
- [ ] **Chart Patterns**: Head & shoulders, triangles, etc.
- [ ] **Market Microstructure**: Order flow, liquidity zones
- [ ] **Cross-Timeframe Validation**: HTF structure confirms LTF signals

### Phase 7: Structure-Based Risk Management

- [ ] **Dynamic Stop Loss**: Based on swing low/high
- [ ] **Position Sizing**: Based on market regime
- [ ] **Trend-Based Leverage**: Adjust leverage by trend strength

### Phase 8: Structure Visualization

- [ ] **Artifact Export**: Export structure points to visualization tools
- [ ] **Structure Reports**: Generate structure analysis reports
- [ ] **Interactive Charts**: Plot structure features on price charts

---

## Conclusion

This proposal outlines a comprehensive design for integrating market structure features into the TRADE backtest engine. The design:

✅ **Follows existing patterns** (FeatureSpec → FeatureFrameBuilder → FeedStore)  
✅ **Maintains performance** (O(1) access, precomputed)  
✅ **Enables extensibility** (easy to add new structure types)  
✅ **Preserves determinism** (closed-candle-only, no lookahead)  
✅ **Integrates cleanly** (minimal changes to existing code)

**Next Steps**: Review and approval, then begin Phase 5.1 implementation.

---

**Document Version**: 1.0  
**Last Updated**: December 18, 2025  
**Status**: 📋 PROPOSAL (Awaiting Review)

