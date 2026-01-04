# Incremental State Architecture

**Status**: Implementation Complete (Phase 12 done)
**Created**: 2026-01-02
**Updated**: 2026-01-04
**Purpose**: Unified bar-by-bar state for market structure and rolling windows

## Vision Alignment

This architecture supports the IdeaCard Vision (see `IDEACARD_VISION.md`):

- **Agent-ready**: Structures are blocks that can be composed programmatically
- **Registry-based**: New structure types added without core changes
- **Fail-loud**: Every error includes actionable fix suggestions
- **Schema-flexible**: YAML format can evolve; engine contract is stable

## Problem Statement

| Type | Current Approach | Hot Loop | Live Parity |
|------|------------------|----------|-------------|
| Indicators | Vectorized precompute | O(1) lookup | N/A |
| Market Structure | Batch loop | O(1) lookup | Incompatible |
| Rolling Windows | On-the-fly O(n) | O(n) per call | Incompatible |

**Issues**:
1. `bars_exec_low(20)` / `bars_exec_high(20)` are O(n) in the hot loop
2. Market structure uses batch loops incompatible with live trading
3. No HTF structure support

**Key Insight**: Batch loops are already bar-by-bar internally - just extract the state.

## Architecture Overview

### What's Locked vs Flexible

| Layer | Locked? | Description |
|-------|---------|-------------|
| Incremental State Engine | Mostly locked | Core data flow, O(1) guarantees |
| Structure Registry | Extensible | Add new types anytime |
| IdeaCard Schema | Fully flexible | Just YAML + parser |
| Rule Syntax | Fully flexible | Just string parsing |

### Multi-Timeframe Structure

```
┌─────────────────────────────────────────────────────────────┐
│                  MultiTFIncrementalState                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  exec (15m) ─────────────────────────────────────────────   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ TFIncrementalState                                  │   │
│  │   structures: {swing, fib, zone, trend, low_20,     │   │
│  │                derived_zone}                        │   │
│  │   UPDATE: Every exec bar                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  htf["1h"] ──────────────────────────────────────────────   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ TFIncrementalState                                  │   │
│  │   structures: {swing_1h, trend_1h}                  │   │
│  │   UPDATE: Only when 1h bar closes                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Core Primitives

### MonotonicDeque

O(1) amortized sliding window min/max.

```python
from collections import deque
from typing import Literal

class MonotonicDeque:
    """
    O(1) amortized sliding window min or max.

    Maintains monotonic property:
    - MIN mode: deque values increase (front = smallest)
    - MAX mode: deque values decrease (front = largest)
    """

    def __init__(self, window_size: int, mode: Literal["min", "max"]):
        self.window_size = window_size
        self.mode = mode
        self._deque: deque[tuple[int, float]] = deque()

    def push(self, idx: int, value: float) -> None:
        # Evict entries outside window
        while self._deque and self._deque[0][0] <= idx - self.window_size:
            self._deque.popleft()

        # Maintain monotonic property
        if self.mode == "min":
            while self._deque and self._deque[-1][1] >= value:
                self._deque.pop()
        else:
            while self._deque and self._deque[-1][1] <= value:
                self._deque.pop()

        self._deque.append((idx, value))

    def get(self) -> float | None:
        if not self._deque:
            return None
        return self._deque[0][1]
```

### RingBuffer

Fixed-size circular buffer for swing detection.

```python
import numpy as np

class RingBuffer:
    """Fixed-size circular buffer. O(1) push and index access."""

    def __init__(self, size: int):
        self.size = size
        self._buffer = np.full(size, np.nan, dtype=np.float64)
        self._head = 0
        self._count = 0

    def push(self, value: float) -> None:
        self._buffer[self._head] = value
        self._head = (self._head + 1) % self.size
        if self._count < self.size:
            self._count += 1

    def __getitem__(self, idx: int) -> float:
        if idx < 0 or idx >= self._count:
            raise IndexError(f"Index {idx} out of range [0, {self._count})")
        physical = (self._head - self._count + idx) % self.size
        return self._buffer[physical]

    def is_full(self) -> bool:
        return self._count == self.size
```

## Structure Registry

### Base Class Contract

```python
from abc import ABC, abstractmethod
from typing import Any

class BaseIncrementalDetector(ABC):
    """Base class for all incremental structure detectors."""

    REQUIRED_PARAMS: list[str] = []
    OPTIONAL_PARAMS: dict[str, Any] = {}
    DEPENDS_ON: list[str] = []

    @classmethod
    def validate_and_create(
        cls,
        struct_type: str,
        key: str,
        params: dict,
        deps: dict,
    ) -> "BaseIncrementalDetector":
        """Validate params and dependencies, create instance."""

        # Check required params
        missing = [p for p in cls.REQUIRED_PARAMS if p not in params]
        if missing:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}) missing required params: {missing}\n"
                f"\n"
                f"Fix in IdeaCard:\n"
                f"  - type: {struct_type}\n"
                f"    key: {key}\n"
                f"    params:\n"
                + "\n".join(f"      {p}: <value>  # REQUIRED" for p in missing)
            )

        # Check dependencies
        missing_deps = [d for d in cls.DEPENDS_ON if d not in deps]
        if missing_deps:
            raise ValueError(
                f"Structure '{key}' (type: {struct_type}) missing dependencies: {missing_deps}\n"
                f"\n"
                f"Fix in IdeaCard:\n"
                f"  - type: {struct_type}\n"
                f"    key: {key}\n"
                f"    depends_on:\n"
                + "\n".join(f"      {d}: <key>  # REQUIRED" for d in missing_deps)
            )

        # Type-specific validation
        cls._validate_params(struct_type, key, params)

        return cls(params, deps)

    @classmethod
    def _validate_params(cls, struct_type: str, key: str, params: dict) -> None:
        """Override for type-specific validation."""
        pass

    @abstractmethod
    def update(self, bar_idx: int, bar: "BarData") -> None:
        """Process one bar. Called on TF bar close."""
        pass

    @abstractmethod
    def get_output_keys(self) -> list[str]:
        """List of readable output keys."""
        pass

    @abstractmethod
    def get_value(self, key: str) -> float | int | str:
        """Get output by key. Must be O(1)."""
        pass

    def get_value_safe(self, key: str) -> float | int | str:
        """Get output with validation."""
        valid_keys = self.get_output_keys()
        if key not in valid_keys:
            raise KeyError(
                f"Structure '{self._key}' has no output '{key}'\n"
                f"\n"
                f"Available outputs: {valid_keys}"
            )
        return self.get_value(key)
```

### Registration

```python
STRUCTURE_REGISTRY: dict[str, type[BaseIncrementalDetector]] = {}

def register_structure(name: str):
    """Decorator to register structure detector."""
    def decorator(cls: type[BaseIncrementalDetector]):
        STRUCTURE_REGISTRY[name] = cls
        return cls
    return decorator
```

## Structure Detectors

### Swing Detector

```python
@register_structure("swing")
class IncrementalSwingDetector(BaseIncrementalDetector):

    REQUIRED_PARAMS = ["left", "right"]
    DEPENDS_ON = []

    @classmethod
    def _validate_params(cls, struct_type: str, key: str, params: dict) -> None:
        for p in ["left", "right"]:
            val = params.get(p)
            if not isinstance(val, int) or val < 1:
                raise ValueError(
                    f"Structure '{key}': '{p}' must be integer >= 1, got {val!r}\n"
                    f"\n"
                    f"Fix: {p}: 5  # Must be >= 1"
                )

    def __init__(self, params: dict, deps: dict = None):
        self.left = params["left"]
        self.right = params["right"]
        window = self.left + self.right + 1

        self._high_buf = RingBuffer(window)
        self._low_buf = RingBuffer(window)

        self.high_level: float = np.nan
        self.high_idx: int = -1
        self.low_level: float = np.nan
        self.low_idx: int = -1

    def update(self, bar_idx: int, bar: BarData) -> None:
        self._high_buf.push(bar.high)
        self._low_buf.push(bar.low)

        if not self._high_buf.is_full():
            return

        pivot_idx = self.left
        pivot_bar = bar_idx - self.right

        if self._is_swing_high(pivot_idx):
            self.high_level = self._high_buf[pivot_idx]
            self.high_idx = pivot_bar

        if self._is_swing_low(pivot_idx):
            self.low_level = self._low_buf[pivot_idx]
            self.low_idx = pivot_bar

    def _is_swing_high(self, pivot_idx: int) -> bool:
        pivot_val = self._high_buf[pivot_idx]
        for i in range(len(self._high_buf)):
            if i != pivot_idx and self._high_buf[i] >= pivot_val:
                return False
        return True

    def _is_swing_low(self, pivot_idx: int) -> bool:
        pivot_val = self._low_buf[pivot_idx]
        for i in range(len(self._low_buf)):
            if i != pivot_idx and self._low_buf[i] <= pivot_val:
                return False
        return True

    def get_output_keys(self) -> list[str]:
        return ["high_level", "high_idx", "low_level", "low_idx"]

    def get_value(self, key: str) -> float | int:
        return getattr(self, key)
```

### Fibonacci Detector

```python
@register_structure("fibonacci")
class IncrementalFibonacci(BaseIncrementalDetector):

    REQUIRED_PARAMS = ["levels"]
    OPTIONAL_PARAMS = {"mode": "retracement"}
    DEPENDS_ON = ["swing"]

    @classmethod
    def _validate_params(cls, struct_type: str, key: str, params: dict) -> None:
        levels = params.get("levels")
        if not isinstance(levels, list) or len(levels) == 0:
            raise ValueError(
                f"Structure '{key}': 'levels' must be non-empty list\n"
                f"\n"
                f"Fix: levels: [0.236, 0.382, 0.5, 0.618, 0.786]"
            )

        mode = params.get("mode", "retracement")
        if mode not in ("retracement", "extension"):
            raise ValueError(
                f"Structure '{key}': 'mode' must be 'retracement' or 'extension'\n"
                f"\n"
                f"Fix: mode: retracement"
            )

    def __init__(self, params: dict, deps: dict):
        self.swing = deps["swing"]
        self.levels = params["levels"]
        self.mode = params.get("mode", "retracement")

        self._values: dict[str, float] = {}
        self._last_high_idx = -1
        self._last_low_idx = -1

        for lvl in self.levels:
            self._values[f"level_{lvl}"] = np.nan

    def update(self, bar_idx: int, bar: BarData) -> None:
        if (self.swing.high_idx != self._last_high_idx or
            self.swing.low_idx != self._last_low_idx):
            self._recalculate()
            self._last_high_idx = self.swing.high_idx
            self._last_low_idx = self.swing.low_idx

    def _recalculate(self) -> None:
        high = self.swing.high_level
        low = self.swing.low_level

        if np.isnan(high) or np.isnan(low):
            return

        range_ = high - low

        for lvl in self.levels:
            if self.mode == "retracement":
                self._values[f"level_{lvl}"] = high - (range_ * lvl)
            else:
                self._values[f"level_{lvl}"] = high + (range_ * lvl)

    def get_output_keys(self) -> list[str]:
        return list(self._values.keys())

    def get_value(self, key: str) -> float:
        return self._values.get(key, np.nan)
```

### Zone Detector

```python
@register_structure("zone")
class IncrementalZoneDetector(BaseIncrementalDetector):

    REQUIRED_PARAMS = ["zone_type", "width_atr"]
    DEPENDS_ON = ["swing"]

    @classmethod
    def _validate_params(cls, struct_type: str, key: str, params: dict) -> None:
        zone_type = params.get("zone_type")
        if zone_type not in ("demand", "supply"):
            raise ValueError(
                f"Structure '{key}': 'zone_type' must be 'demand' or 'supply'\n"
                f"\n"
                f"Fix: zone_type: demand"
            )

        width_atr = params.get("width_atr")
        if not isinstance(width_atr, (int, float)) or width_atr <= 0:
            raise ValueError(
                f"Structure '{key}': 'width_atr' must be positive number\n"
                f"\n"
                f"Fix: width_atr: 1.5"
            )

    def __init__(self, params: dict, deps: dict):
        self.swing = deps["swing"]
        self.zone_type = params["zone_type"]
        self.width_atr = params["width_atr"]

        self.state: str = "none"
        self.upper: float = np.nan
        self.lower: float = np.nan
        self.anchor_idx: int = -1
        self._last_swing_idx: int = -1

    def update(self, bar_idx: int, bar: BarData) -> None:
        if self.zone_type == "demand":
            swing_level = self.swing.low_level
            swing_idx = self.swing.low_idx
        else:
            swing_level = self.swing.high_level
            swing_idx = self.swing.high_idx

        if swing_idx != self._last_swing_idx and swing_idx >= 0:
            atr = bar.indicators.get("atr", np.nan)
            width = atr * self.width_atr if not np.isnan(atr) else 0

            if self.zone_type == "demand":
                self.lower = swing_level - width
                self.upper = swing_level
            else:
                self.lower = swing_level
                self.upper = swing_level + width

            self.state = "active"
            self.anchor_idx = swing_idx
            self._last_swing_idx = swing_idx

        if self.state == "active":
            if self.zone_type == "demand" and bar.close < self.lower:
                self.state = "broken"
            elif self.zone_type == "supply" and bar.close > self.upper:
                self.state = "broken"

    def get_output_keys(self) -> list[str]:
        return ["state", "upper", "lower", "anchor_idx"]

    def get_value(self, key: str) -> float | int | str:
        return getattr(self, key)
```

### Trend Detector

```python
@register_structure("trend")
class IncrementalTrendDetector(BaseIncrementalDetector):

    REQUIRED_PARAMS = []
    DEPENDS_ON = ["swing"]

    def __init__(self, params: dict, deps: dict):
        self.swing = deps["swing"]

        self._prev_high: float = np.nan
        self._prev_low: float = np.nan
        self._last_high_idx: int = -1
        self._last_low_idx: int = -1

        self.direction: int = 0
        self.strength: float = 0.0
        self.bars_in_trend: int = 0

    def update(self, bar_idx: int, bar: BarData) -> None:
        high_changed = self.swing.high_idx != self._last_high_idx
        low_changed = self.swing.low_idx != self._last_low_idx

        if not high_changed and not low_changed:
            self.bars_in_trend += 1
            return

        hh = self.swing.high_level > self._prev_high if not np.isnan(self._prev_high) else None
        hl = self.swing.low_level > self._prev_low if not np.isnan(self._prev_low) else None

        if hh is True and hl is True:
            new_dir = 1
        elif hh is False and hl is False:
            new_dir = -1
        else:
            new_dir = 0

        if new_dir != self.direction:
            self.direction = new_dir
            self.bars_in_trend = 0

        if high_changed:
            self._prev_high = self.swing.high_level
            self._last_high_idx = self.swing.high_idx
        if low_changed:
            self._prev_low = self.swing.low_level
            self._last_low_idx = self.swing.low_idx

    def get_output_keys(self) -> list[str]:
        return ["direction", "strength", "bars_in_trend"]

    def get_value(self, key: str) -> int | float:
        return getattr(self, key)
```

### Rolling Window Detector

```python
@register_structure("rolling_window")
class IncrementalRollingWindow(BaseIncrementalDetector):

    REQUIRED_PARAMS = ["size", "field", "mode"]
    DEPENDS_ON = []

    @classmethod
    def _validate_params(cls, struct_type: str, key: str, params: dict) -> None:
        size = params.get("size")
        if not isinstance(size, int) or size < 1:
            raise ValueError(
                f"Structure '{key}': 'size' must be integer >= 1\n"
                f"\n"
                f"Fix: size: 20"
            )

        field = params.get("field")
        if field not in ("open", "high", "low", "close", "volume"):
            raise ValueError(
                f"Structure '{key}': 'field' must be open/high/low/close/volume\n"
                f"\n"
                f"Fix: field: low"
            )

        mode = params.get("mode")
        if mode not in ("min", "max"):
            raise ValueError(
                f"Structure '{key}': 'mode' must be 'min' or 'max'\n"
                f"\n"
                f"Fix: mode: min"
            )

    def __init__(self, params: dict, deps: dict = None):
        self.size = params["size"]
        self.field = params["field"]
        self.mode = params["mode"]
        self._deque = MonotonicDeque(self.size, self.mode)

    def update(self, bar_idx: int, bar: BarData) -> None:
        value = getattr(bar, self.field)
        self._deque.push(bar_idx, value)

    def get_output_keys(self) -> list[str]:
        return ["value"]

    def get_value(self, key: str) -> float:
        return self._deque.get()
```

### Derived Zone Detector (Phase 12)

K slots + aggregates pattern for derived zones from market structure.
See `DERIVATION_RULE_INVESTIGATION.md` for complete specification.

```python
@register_structure("derived_zone")
class IncrementalDerivedZone(BaseIncrementalDetector):

    REQUIRED_PARAMS = ["levels", "price_source"]
    OPTIONAL_PARAMS = {"max_active": 5, "mode": "retracement"}
    DEPENDS_ON = ["source"]  # e.g., swing detector

    @classmethod
    def _validate_params(cls, struct_type: str, key: str, params: dict) -> None:
        levels = params.get("levels")
        if not isinstance(levels, list) or len(levels) == 0:
            raise ValueError(
                f"Structure '{key}': 'levels' must be non-empty list\n"
                f"\n"
                f"Fix: levels: [0.236, 0.382, 0.5, 0.618, 0.786]"
            )

        price_source = params.get("price_source", "mark_close")
        if price_source not in ("mark_close", "last_close"):
            raise ValueError(
                f"Structure '{key}': 'price_source' must be 'mark_close' or 'last_close'\n"
                f"\n"
                f"Fix: price_source: mark_close"
            )

    def __init__(self, params: dict, deps: dict):
        self.source = deps["source"]  # Swing detector
        self.levels = params["levels"]
        self.max_active = params.get("max_active", 5)
        self.mode = params.get("mode", "retracement")
        self.price_source = params.get("price_source", "mark_close")

        self._zones: list[dict] = []  # Internal zone storage
        self._source_version: int = 0

    def update(self, bar_idx: int, bar: BarData) -> None:
        # REGEN PATH: Only on source version change
        current_version = self.source.get_value("version")
        if current_version != self._source_version:
            self._regenerate_zones(bar_idx, bar)
            self._source_version = current_version

        # INTERACTION PATH: Every exec bar
        self._update_zone_interactions(bar_idx, bar)

    def get_output_keys(self) -> list[str]:
        # Slot fields (0 to max_active-1)
        keys = []
        for n in range(self.max_active):
            keys.extend([
                f"zone{n}_lower", f"zone{n}_upper", f"zone{n}_state",
                f"zone{n}_anchor_idx", f"zone{n}_age_bars",
                f"zone{n}_touched_this_bar", f"zone{n}_touch_count",
                f"zone{n}_inside", f"zone{n}_instance_id",
            ])
        # Aggregate fields
        keys.extend([
            "active_count", "any_active", "any_touched", "any_inside",
            "closest_active_lower", "closest_active_upper", "closest_active_idx",
            "newest_active_idx", "source_version",
        ])
        return keys

    def get_value(self, key: str) -> float | int | str | None:
        # Returns None for empty float slots (JSON-safe null)
        # Returns "NONE" for empty state slots
        # Returns -1 for empty int slots
        # Returns False for empty bool slots
        ...
```

**Key design decisions:**

| Decision | Choice |
|----------|--------|
| Slot ordering | Most recent first (`zone0` = newest) |
| Empty float encoding | `null` (not NaN) for JSON safety |
| Zone hash | blake2b for platform stability |
| Touched semantics | Event (reset each bar), not sticky |
| Regen trigger | Source structure version change only |
| Interaction update | Every exec bar |

## State Containers

### BarData

```python
@dataclass
class BarData:
    """Single bar passed to structure updates."""
    idx: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    indicators: dict[str, float]
```

### TFIncrementalState

```python
class TFIncrementalState:
    """Incremental state for a single timeframe."""

    def __init__(self, timeframe: str, structure_specs: list[dict]):
        self.timeframe = timeframe
        self._bar_idx = -1
        self.structures: dict[str, BaseIncrementalDetector] = {}
        self._update_order: list[str] = []

        self._build_structures(structure_specs)

    def _build_structures(self, specs: list[dict]) -> None:
        for spec in specs:
            struct_type = spec["type"]
            key = spec["key"]
            params = spec.get("params", {})
            depends_on = spec.get("depends_on", {})

            if struct_type not in STRUCTURE_REGISTRY:
                available = list(STRUCTURE_REGISTRY.keys())
                raise ValueError(
                    f"Unknown structure type: '{struct_type}'\n"
                    f"\n"
                    f"Available: {available}"
                )

            cls = STRUCTURE_REGISTRY[struct_type]

            # Resolve dependencies
            deps = {}
            for dep_type, dep_key in depends_on.items():
                if dep_key not in self.structures:
                    raise ValueError(
                        f"Structure '{key}' depends on '{dep_key}' not yet defined.\n"
                        f"\n"
                        f"Define '{dep_key}' BEFORE '{key}' in IdeaCard."
                    )
                deps[dep_type] = self.structures[dep_key]

            detector = cls.validate_and_create(struct_type, key, params, deps)
            detector._key = key
            detector._type = struct_type

            self.structures[key] = detector
            self._update_order.append(key)

    def update(self, bar: BarData) -> None:
        if bar.idx <= self._bar_idx:
            raise ValueError(
                f"Bar index must increase. Got {bar.idx}, last was {self._bar_idx}"
            )
        self._bar_idx = bar.idx

        for key in self._update_order:
            self.structures[key].update(bar.idx, bar)

    def get_value(self, struct_key: str, output_key: str) -> float | int | str:
        if struct_key not in self.structures:
            available = list(self.structures.keys())
            raise KeyError(
                f"Structure '{struct_key}' not defined for '{self.timeframe}'\n"
                f"\n"
                f"Available: {available}"
            )
        return self.structures[struct_key].get_value_safe(output_key)
```

### MultiTFIncrementalState

```python
class MultiTFIncrementalState:
    """Unified container for all timeframe states."""

    def __init__(
        self,
        exec_tf: str,
        exec_specs: list[dict],
        htf_configs: dict[str, list[dict]],
    ):
        self.exec = TFIncrementalState(exec_tf, exec_specs)
        self.htf: dict[str, TFIncrementalState] = {
            tf: TFIncrementalState(tf, specs)
            for tf, specs in htf_configs.items()
        }

    def update_exec(self, bar: BarData) -> None:
        self.exec.update(bar)

    def update_htf(self, timeframe: str, bar: BarData) -> None:
        if timeframe not in self.htf:
            available = list(self.htf.keys())
            raise KeyError(
                f"HTF '{timeframe}' not configured.\n"
                f"\n"
                f"Available: {available}"
            )
        self.htf[timeframe].update(bar)

    def get_value(self, path: str) -> float | int | str:
        parts = path.split(".", 2)
        if len(parts) < 3:
            raise ValueError(
                f"Invalid path: '{path}'\n"
                f"\n"
                f"Format: <tf>.<structure>.<output>\n"
                f"Example: exec.swing.high_level"
            )

        tf_role, struct_key, output_key = parts[0], parts[1], parts[2]

        if tf_role == "exec":
            return self.exec.get_value(struct_key, output_key)
        elif tf_role.startswith("htf_"):
            tf_name = tf_role[4:]
            if tf_name not in self.htf:
                raise KeyError(f"HTF '{tf_name}' not configured")
            return self.htf[tf_name].get_value(struct_key, output_key)
        else:
            raise ValueError(f"Invalid tf_role: '{tf_role}'. Use 'exec' or 'htf_<tf>'")
```

## Engine Integration

### Hot Loop Changes

```python
class BacktestEngine:

    def __init__(self, config: BacktestConfig):
        self._feeds = self._build_feeds()
        self._incremental = self._build_incremental()  # NEW

    def _build_incremental(self) -> MultiTFIncrementalState:
        structures_config = self._idea_card.get("structures", {})

        if not structures_config:
            raise ValueError(
                "IdeaCard missing 'structures' section.\n"
                "\n"
                "Add:\n"
                "  structures:\n"
                "    exec:\n"
                "      - type: swing\n"
                "        key: swing\n"
                "        params: { left: 5, right: 5 }"
            )

        return MultiTFIncrementalState(
            exec_tf=self._exec_tf,
            exec_specs=structures_config.get("exec", []),
            htf_configs=structures_config.get("htf", {}),
        )

    def run(self):
        for exec_idx in range(self._num_bars):
            # Build bar data
            exec_bar = self._build_bar_data(exec_idx)

            # Update exec structures (every bar)
            self._incremental.update_exec(exec_bar)

            # Check HTF closes
            htf_updated = self._update_htf_mtf_indices(exec_bar.close_time)

            # Update HTF structures (only on close)
            if htf_updated:
                htf_bar = self._build_htf_bar_data(self._current_htf_idx)
                self._incremental.update_htf(self._htf_tf, htf_bar)

            # Build snapshot with incremental state
            snapshot = self._build_snapshot(exec_idx)

            # Evaluate & execute
            signal = self._evaluate_rules(snapshot)
            if signal:
                self._execute_signal(signal)
```

### Snapshot Changes

```python
class RuntimeSnapshotView:

    def __init__(self, feeds, exec_idx, htf_idx, incremental):
        self._feeds = feeds
        self._exec_idx = exec_idx
        self._htf_idx = htf_idx
        self._incremental = incremental

    def get_structure(self, path: str) -> float | int | str:
        """Get structure value by path. O(1)."""
        return self._incremental.get_value(path)

    def bars_exec_low(self, n: int) -> float:
        """Lowest low of last n bars. O(1)."""
        key = f"low_{n}"
        try:
            return self._incremental.exec.get_value(key, "value")
        except KeyError:
            raise KeyError(
                f"Rolling window 'low_{n}' not defined.\n"
                f"\n"
                f"Add to IdeaCard:\n"
                f"  - type: rolling_window\n"
                f"    key: low_{n}\n"
                f"    params: {{ size: {n}, field: low, mode: min }}"
            )
```

## IdeaCard Schema

### Structure Block

```yaml
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: "{{ swing_lookback }}"
        right: "{{ swing_lookback }}"

    - type: fibonacci
      key: fib
      depends_on:
        swing: swing
      params:
        levels: "{{ fib_levels }}"
        mode: retracement

    - type: rolling_window
      key: low_20
      params:
        size: 20
        field: low
        mode: min

    - type: derived_zone
      key: fib_zones
      depends_on:
        source: swing
      params:
        levels: [0.236, 0.382, 0.5, 0.618, 0.786]
        mode: retracement
        price_source: mark_close
        max_active: 5

  htf:
    "1h":
      - type: swing
        key: swing_1h
        params:
          left: 3
          right: 3

      - type: trend
        key: trend_1h
        depends_on:
          swing: swing_1h
```

### Schema Flexibility

The YAML format can evolve. The engine only needs parsed specs:

```python
# Engine contract - stable
exec_specs = [
    {"type": "swing", "key": "swing", "params": {...}, "depends_on": {}},
    {"type": "fibonacci", "key": "fib", "params": {...}, "depends_on": {"swing": "swing"}},
]
```

How YAML maps to this is up to the parser.

## Validation Summary

| Level | When | What |
|-------|------|------|
| Registration | Code load | Class contract |
| Parse-time | IdeaCard load | Schema, types exist |
| Instantiation | Engine init | Params, dependencies |
| Runtime | Access | Output keys |

Every error includes actionable fix suggestions.

## Implementation Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Core primitives (MonotonicDeque, RingBuffer) | ✅ Complete |
| 2 | Base class + registry + validation | ✅ Complete |
| 3 | Detectors (swing, fib, zone, trend, rolling_window) | ✅ Complete |
| 4 | TFIncrementalState + MultiTFIncrementalState | ✅ Complete |
| 5 | IdeaCard schema + parser | ✅ Complete |
| 6 | Engine integration | ✅ Complete |
| 7 | Remove batch code | ✅ Complete |
| 8 | Validation + docs | ✅ Complete |
| 12 | Derived zones (K slots + aggregates) | ✅ Complete |

## What Gets Removed

After migration:
- `build_structures_into_feed()` - DELETE
- `FeedStore.structures` field - DELETE
- O(n) `bars_exec_low()` fallback - DELETE

## Related Documents

- `IDEACARD_VISION.md` - Vision and goals
- `IDEACARD_SYNTAX.md` - Blocks DSL v3.0.0 syntax reference
- `DERIVATION_RULE_INVESTIGATION.md` - Phase 12 derived zones (K slots + aggregates)
- `../project/PROJECT_OVERVIEW.md` - Project roadmap
