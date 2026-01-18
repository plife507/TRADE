# Pivot Foundation Gates

> **Status**: IN PROGRESS (Gates 0-5 Complete)
> **Priority**: P0 - Critical Foundation
> **Impact**: All structure-based trading (Fib, Trend, BOS/CHoCH, OB, FVG, Liquidity)

## Executive Summary

The pivot/swing detection system is the **foundation of all market structure analysis**. Every downstream structure depends on accurate, noise-filtered pivot detection:

```
swing (PIVOTS) ──┬──> trend (HH/HL/LH/LL)
                 │        └──> Fib anchoring stability
                 │        └──> Entry/exit bias
                 │
                 ├──> market_structure (BOS/CHoCH)
                 │        └──> Continuation vs reversal signals
                 │
                 ├──> fibonacci (retracement/extension)
                 │        └──> Entry zones, TP targets
                 │
                 ├──> order_block (institutional levels)
                 │        └──> Refined entries, stop placement
                 │
                 ├──> fair_value_gap (imbalance)
                 │        └──> High-probability entries
                 │
                 └──> liquidity_zone (equal H/L)
                          └──> Target levels, sweep detection
```

**Current Problem**: Fixed bar-count pivot detection creates:
- Too many pivots in choppy markets (noise)
- Unstable Fib anchors (constantly re-anchoring to minor swings)
- Trend detector state memory issues (stale HH/HL comparisons)
- No significance differentiation (major vs minor pivots)

**Solution**: Multi-mode pivot detection with significance filtering, strict alternation, and proper wave tracking.

---

## Design Principles

### 1. Backward Compatibility
- Default behavior MUST match current `fractal` mode exactly
- New features are opt-in via parameters
- Existing Plays continue to work without modification

### 2. Incremental/O(1) Requirement
- All updates must be O(1) or O(window) per bar
- No full-history rescans
- Hot-loop safe for live trading

### 3. Composability
- Modes and filters can be combined
- Each feature works independently
- Clear parameter validation with actionable errors

### 4. Testability
- Each gate has validation Plays
- Parity tests against known sequences
- Stress tests with real market data

---

## Gate 0: Significance Infrastructure

> **Goal**: Add infrastructure for measuring pivot significance without changing detection logic

### 0.1 ATR Dependency Option

Add optional ATR indicator dependency to swing detector.

```yaml
# Current (no change):
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }

# New option (opt-in):
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5
        atr_key: atr_14  # Reference to indicator

indicators:
  exec:
    - type: atr
      key: atr_14
      params: { length: 14 }
```

**Implementation**:
```python
class IncrementalSwingDetector:
    OPTIONAL_PARAMS = {
        # ... existing ...
        "atr_key": None,  # Key of ATR indicator in bar.indicators
    }

    def __init__(self, params, deps):
        self._atr_key = params.get("atr_key")

    def _get_atr(self, bar: BarData) -> float | None:
        """Get ATR value from bar indicators if configured."""
        if self._atr_key is None:
            return None
        return bar.indicators.get(self._atr_key)
```

### 0.2 Significance Calculation

Calculate and expose pivot significance as ATR multiple.

**New outputs**:
```python
# How many ATRs did price move from previous pivot?
high_significance: float  # e.g., 2.3 = moved 2.3× ATR
low_significance: float

# Is this pivot "major" (above threshold)?
high_is_major: bool  # significance >= major_threshold
low_is_major: bool
```

**Calculation**:
```python
def _calculate_significance(
    self,
    current_level: float,
    previous_level: float,
    atr: float
) -> float:
    """Calculate pivot significance as ATR multiple."""
    if atr is None or atr <= 0:
        return float('nan')

    move = abs(current_level - previous_level)
    return move / atr
```

### 0.3 Major/Minor Classification

```python
OPTIONAL_PARAMS = {
    "major_threshold": 1.5,  # ATR multiple to be "major"
}
```

### Gate 0 Validation Plays

| Play | Description | Validates |
|------|-------------|-----------|
| `V_PF_001_significance_calc` | Known ATR + price moves → expected significance | Math accuracy |
| `V_PF_002_major_minor_threshold` | Pivots above/below threshold → correct classification | Threshold logic |
| `V_PF_003_no_atr_fallback` | No ATR configured → significance = NaN, is_major = false | Graceful degradation |

### Gate 0 Deliverables

- [x] Add `atr_key` parameter to swing detector
- [x] Implement `_get_atr()` method
- [x] Add `high_significance`, `low_significance` outputs
- [x] Add `high_is_major`, `low_is_major` outputs
- [x] Add `major_threshold` parameter
- [x] Update registry with new output types
- [x] Create validation Plays V_PF_001-003
- [x] Run smoke tests

---

## Gate 1: Significance Filtering

> **Goal**: Filter out insignificant pivots based on ATR threshold

### 1.1 Minimum Move Filter

Only accept pivots that moved significantly from the previous pivot.

```yaml
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5
        atr_key: atr_14
        min_atr_move: 1.0  # Must move at least 1.0× ATR
```

**Implementation**:
```python
def _should_accept_pivot(
    self,
    pivot_type: str,  # "high" or "low"
    level: float,
    bar: BarData
) -> bool:
    """Determine if pivot should be accepted based on significance."""

    # No filter configured - accept all
    if self._min_atr_move is None:
        return True

    atr = self._get_atr(bar)
    if atr is None or atr <= 0:
        return True  # Can't filter without ATR

    # Get previous level of same type
    if pivot_type == "high":
        prev_level = self._prev_high
    else:
        prev_level = self._prev_low

    if math.isnan(prev_level):
        return True  # First pivot, always accept

    # Check significance
    move = abs(level - prev_level)
    threshold = atr * self._min_atr_move

    return move >= threshold
```

### 1.2 Visual Effect of Filtering

```
Without filter (current):
Price: ╱╲╱╲╱╲  ╱╲    ╱╲╱╲
       H H H  H     H H      ← 6 highs detected (noisy)
        L L L  L     L L     ← 6 lows detected

With min_atr_move=1.5:
Price: ╱╲╱╲╱╲  ╱╲    ╱╲╱╲
       H       H     H       ← 3 significant highs
        L       L     L      ← 3 significant lows

Result: Cleaner Fib anchors, more stable trend detection
```

### 1.3 Percentage-Based Alternative

For users who prefer percentage-based thresholds:

```yaml
params:
  min_pct_move: 2.0  # Must move at least 2% from previous pivot
```

**Implementation**:
```python
def _check_pct_threshold(self, level: float, prev_level: float) -> bool:
    if math.isnan(prev_level) or prev_level == 0:
        return True

    pct_move = abs(level - prev_level) / prev_level * 100
    return pct_move >= self._min_pct_move
```

### Gate 1 Validation Plays

| Play | Description | Validates |
|------|-------------|-----------|
| `V_PF_010_atr_filter_basic` | Pivots below threshold filtered out | Filter logic |
| `V_PF_011_atr_filter_edge` | Pivot exactly at threshold → accepted | Boundary condition |
| `V_PF_012_pct_filter_basic` | Percentage filter works | Alternative filter |
| `V_PF_013_combined_filters` | ATR + PCT together → both must pass | Filter composition |
| `V_PF_014_first_pivot_accepted` | First pivot always accepted (no previous) | Edge case |

### Gate 1 Deliverables

- [x] Add `min_atr_move` parameter
- [x] Add `min_pct_move` parameter
- [x] Implement `_should_accept_pivot()` with ATR filter
- [x] Implement percentage filter alternative
- [x] Handle edge cases (first pivot, no ATR, zero values)
- [x] Create validation Plays V_PF_010-014
- [x] Run smoke tests

---

## Gate 2: Strict Alternation

> **Goal**: Force H-L-H-L sequence, eliminating consecutive same-type pivots

### 2.1 The Problem

Current output can have consecutive highs or lows:

```
Raw detection: H  L  H  H  L  H  L  L  H
                     ↑        ↑
               Consecutive H  Consecutive L

This creates:
- Trend detector confusion (which H to compare?)
- Fib anchor instability (anchor to which H?)
- Noisy structure
```

### 2.2 Strict Alternation Mode

```yaml
params:
  strict_alternation: true  # Force H-L-H-L sequence
```

**Behavior**:
```
Raw:          H  L  H  H  L  H  L  L  H
                     ↑     ↑     ↑
Expected:          higher  ok   lower

Alternating:  H  L  H     L  H  L     H
                  └─ H(108) replaces H(105) because higher
                           └─ L(92) replaces L(95) because lower
```

### 2.3 Implementation

```python
def _process_alternating_pivot(
    self,
    pivot_type: str,
    level: float,
    idx: int,
    bar: BarData
) -> bool:
    """
    Process pivot with strict alternation.

    Rules:
    - If same type as last pivot:
        - High: Accept only if HIGHER than pending high
        - Low: Accept only if LOWER than pending low
    - If opposite type: Complete pair, start new

    Returns:
        True if pivot was accepted (new or replacement)
    """
    if self._last_pivot_type is None:
        # First pivot, always accept
        self._last_pivot_type = pivot_type
        self._pending_level = level
        self._pending_idx = idx
        return True

    if pivot_type == self._last_pivot_type:
        # Same type - check if better
        if pivot_type == "high":
            if level > self._pending_level:
                # Higher high - replace pending
                self._pending_level = level
                self._pending_idx = idx
                return True
            else:
                # Lower high - ignore
                return False
        else:
            if level < self._pending_level:
                # Lower low - replace pending
                self._pending_level = level
                self._pending_idx = idx
                return True
            else:
                # Higher low - ignore
                return False
    else:
        # Opposite type - complete pair
        self._complete_alternating_pair(pivot_type, level, idx)
        return True
```

### 2.4 New Outputs for Alternation

```python
# Was the raw pivot accepted or filtered?
high_accepted: bool  # True if high was accepted (not filtered by alternation)
low_accepted: bool

# Was this a replacement of pending pivot?
high_replaced_pending: bool  # True if this high replaced a lower pending high
low_replaced_pending: bool
```

### Gate 2 Validation Plays

| Play | Description | Validates |
|------|-------------|-----------|
| `V_PF_020_alternation_basic` | H-L-H-L sequence enforced | Core logic |
| `V_PF_021_higher_high_replace` | H-H where second is higher → replace | Replacement logic |
| `V_PF_022_lower_high_ignore` | H-H where second is lower → ignore | Ignore logic |
| `V_PF_023_lower_low_replace` | L-L where second is lower → replace | Replacement logic |
| `V_PF_024_higher_low_ignore` | L-L where second is higher → ignore | Ignore logic |
| `V_PF_025_double_pivot_bar` | H and L on same bar → proper sequence | Edge case |

### Gate 2 Deliverables

- [x] Add `strict_alternation` parameter (default: false)
- [x] Implement alternation state machine
- [x] Add replacement tracking outputs
- [x] Handle double-pivot bars correctly
- [x] Create validation Plays V_PF_020-022
- [x] Run smoke tests

---

## Gate 3: ATR ZigZag Mode

> **Goal**: Alternative detection mode using ATR threshold instead of fixed bar count

### 3.1 Mode Selection

```yaml
params:
  mode: "atr_zigzag"  # Instead of default "fractal"
  atr_key: atr_14
  atr_multiplier: 2.0  # Direction change requires 2× ATR move
```

### 3.2 Algorithm

```python
"""
ATR ZigZag Algorithm:

1. Track current direction (up/down)
2. Track current extreme (highest high in uptrend, lowest low in downtrend)
3. On each bar:
   - If uptrend:
       - New high > current extreme → update extreme
       - Low < extreme - (ATR × multiplier) → PIVOT! Switch to downtrend
   - If downtrend:
       - New low < current extreme → update extreme
       - High > extreme + (ATR × multiplier) → PIVOT! Switch to uptrend
"""

class ATRZigZagState:
    direction: int  # 1 = up, -1 = down
    extreme_price: float  # Current swing extreme
    extreme_idx: int  # Bar index of extreme

def update_atr_zigzag(self, bar_idx: int, bar: BarData) -> None:
    atr = self._get_atr(bar)
    threshold = atr * self._atr_multiplier

    if self._direction == 1:  # Uptrend
        # Extend swing high?
        if bar.high > self._extreme_price:
            self._extreme_price = bar.high
            self._extreme_idx = bar_idx

        # Reversal to downtrend?
        reversal_level = self._extreme_price - threshold
        if bar.low < reversal_level:
            # Confirm high pivot at extreme
            self._confirm_pivot("high", self._extreme_price, self._extreme_idx)
            # Start downtrend from this bar's low
            self._direction = -1
            self._extreme_price = bar.low
            self._extreme_idx = bar_idx

    else:  # Downtrend
        # Extend swing low?
        if bar.low < self._extreme_price:
            self._extreme_price = bar.low
            self._extreme_idx = bar_idx

        # Reversal to uptrend?
        reversal_level = self._extreme_price + threshold
        if bar.high > reversal_level:
            # Confirm low pivot at extreme
            self._confirm_pivot("low", self._extreme_price, self._extreme_idx)
            # Start uptrend from this bar's high
            self._direction = 1
            self._extreme_price = bar.high
            self._extreme_idx = bar_idx
```

### 3.3 Visual Comparison

```
FRACTAL MODE (left=5, right=5):
Detects pivot after 5 bars confirm it
Many small pivots in choppy market

    ╱╲   ╱╲╱╲   ╱╲
   ╱  ╲ ╱    ╲ ╱  ╲
  ╱    ╲      ╲    ╲
  H    H H    H H   H  ← 6 highs
   L    L L    L L     ← 5 lows


ATR ZIGZAG MODE (atr_multiplier=2.0):
Only pivots when price moves 2× ATR against trend
Fewer, more significant pivots

    ╱╲   ╱╲╱╲   ╱╲
   ╱  ╲ ╱    ╲ ╱  ╲
  ╱    ╲      ╲    ╲
  H              H     ← 2 significant highs
   L          L        ← 2 significant lows
```

### 3.4 Mode Comparison Table

| Aspect | Fractal | ATR ZigZag |
|--------|---------|------------|
| Detection trigger | Bar count (left/right) | ATR threshold |
| Adapts to volatility | No | Yes |
| Confirmation delay | Fixed (right bars) | Variable (until reversal) |
| Pivot count | More | Fewer |
| Best for | Precise timing | Trend following |
| Repainting | No (after right bars) | No (after threshold) |

### Gate 3 Validation Plays

| Play | Description | Validates |
|------|-------------|-----------|
| `V_PF_030_zigzag_uptrend` | Extending highs, then reversal | Uptrend logic |
| `V_PF_031_zigzag_downtrend` | Extending lows, then reversal | Downtrend logic |
| `V_PF_032_zigzag_threshold` | Exact threshold boundary | Threshold accuracy |
| `V_PF_033_zigzag_volatile` | High ATR = wider threshold | Volatility adaptation |
| `V_PF_034_zigzag_quiet` | Low ATR = tighter threshold | Volatility adaptation |
| `V_PF_035_zigzag_vs_fractal` | Same data, compare outputs | Mode comparison |

### Gate 3 Deliverables

- [ ] Add `mode` parameter with "fractal" (default) and "atr_zigzag"
- [ ] Add `atr_multiplier` parameter (default: 2.0)
- [ ] Implement ATR ZigZag state machine
- [ ] Ensure consistent output interface across modes
- [ ] Create validation Plays V_PF_030-035
- [ ] Run smoke tests

---

## Gate 4: Trend Detector Rewrite

> **Goal**: Fix state memory issue, add wave-based tracking

### 4.1 The Problem (Recap)

Current trend detector only remembers last comparison:

```python
# Current (broken):
self._last_hh: bool | None  # Only remembers LAST high comparison
self._last_hl: bool | None  # Only remembers LAST low comparison

# Problem sequence:
# 1. HH (self._last_hh = True)
# 2. HL (self._last_hl = True) → direction = 1 (uptrend) ✓
# 3. LL (self._last_hl = False) → direction = 0 (ranging) ✓
# 4. HH (self._last_hh = True, but _last_hl still False!)
#    → direction = 0 (ranging) ✗ WRONG - should consider recovery
```

### 4.2 Wave-Based Solution

Track complete waves, not individual comparisons:

```python
@dataclass
class Wave:
    """A complete swing wave (L→H or H→L)."""
    start_type: str  # "high" or "low"
    start_level: float
    start_idx: int
    end_type: str
    end_level: float
    end_idx: int
    direction: str  # "bullish" or "bearish"

    # Comparison to previous wave
    is_higher_high: bool | None
    is_higher_low: bool | None
    is_lower_high: bool | None
    is_lower_low: bool | None

class WaveBasedTrend:
    """
    Track last N waves for trend classification.

    Wave sequence analysis:
    - 2 consecutive bullish waves with HH+HL → Strong uptrend
    - 1 bullish wave with HH+HL → Uptrend
    - Mixed waves → Ranging
    - 1 bearish wave with LH+LL → Downtrend
    - 2 consecutive bearish waves with LH+LL → Strong downtrend
    """

    def __init__(self):
        self._waves: deque[Wave] = deque(maxlen=4)  # Last 4 waves
```

### 4.3 New Trend Outputs

```python
# Current outputs (keep):
direction: int  # 1, -1, 0
bars_in_trend: int
version: int

# New outputs:
strength: int  # 0=weak, 1=normal, 2=strong
wave_count: int  # Consecutive waves in same direction
last_wave_direction: str  # "bullish" or "bearish"

# Structure comparison (from last wave):
last_hh: bool  # Was last high a higher high?
last_hl: bool  # Was last low a higher low?
last_lh: bool  # Was last high a lower high?
last_ll: bool  # Was last low a lower low?
```

### 4.4 Classification Logic

```python
def _classify_trend(self) -> tuple[int, int]:
    """
    Classify trend direction and strength from wave history.

    Returns:
        (direction, strength) where:
        - direction: 1 (up), -1 (down), 0 (ranging)
        - strength: 0 (weak), 1 (normal), 2 (strong)
    """
    if len(self._waves) < 2:
        return (0, 0)  # Insufficient data

    recent = self._waves[-1]
    previous = self._waves[-2]

    # Check for clear trend
    if recent.is_higher_high and recent.is_higher_low:
        if previous.is_higher_high and previous.is_higher_low:
            return (1, 2)  # Strong uptrend (2 consecutive HH+HL)
        return (1, 1)  # Normal uptrend

    if recent.is_lower_high and recent.is_lower_low:
        if previous.is_lower_high and previous.is_lower_low:
            return (-1, 2)  # Strong downtrend (2 consecutive LH+LL)
        return (-1, 1)  # Normal downtrend

    # Mixed signals
    return (0, 0)  # Ranging
```

### Gate 4 Validation Plays

| Play | Description | Validates |
|------|-------------|-----------|
| `V_PF_040_wave_tracking` | Waves correctly captured from swings | Wave formation |
| `V_PF_041_hh_hl_uptrend` | HH+HL sequence → uptrend | Uptrend detection |
| `V_PF_042_lh_ll_downtrend` | LH+LL sequence → downtrend | Downtrend detection |
| `V_PF_043_mixed_ranging` | HH+LL or LH+HL → ranging | Ranging detection |
| `V_PF_044_strength_levels` | 2 consecutive waves → strong | Strength calculation |
| `V_PF_045_recovery_scenario` | LL then HH, HH, HH → detects recovery | State memory fix |
| `V_PF_046_trend_flip` | Direction change → version bump | Version tracking |

### Gate 4 Deliverables

- [x] Create `Wave` dataclass
- [x] Implement wave deque tracking (last 4 waves)
- [x] Rewrite trend classification with wave-based logic
- [x] Add `strength` output (int: 0=weak, 1=normal, 2=strong)
- [x] Add individual comparison outputs (last_hh, last_hl, last_lh, last_ll)
- [x] Add wave_count and last_wave_direction outputs
- [x] Ensure backward-compatible direction output
- [x] Create validation Plays V_PF_040-046
- [x] Run smoke tests

---

## Gate 5: Market Structure Detector (BOS/CHoCH)

> **Goal**: New detector for Break of Structure and Change of Character events

### 5.1 Concept

```
Break of Structure (BOS): Continuation signal
- Uptrend BOS: Price breaks above previous swing HIGH
- Downtrend BOS: Price breaks below previous swing LOW
- Meaning: Trend is continuing, look for entries in trend direction

Change of Character (CHoCH): Reversal signal
- In uptrend: Price breaks below previous swing LOW
- In downtrend: Price breaks above previous swing HIGH
- Meaning: Potential trend reversal, be cautious or reverse
```

### 5.2 Implementation

```python
@register_structure("market_structure")
class IncrementalMarketStructure(BaseIncrementalDetector):
    """
    ICT Market Structure: BOS + CHoCH detection.

    Depends on swing detector for pivot levels.
    Tracks structure breaks in real-time.
    """

    DEPENDS_ON = ["swing"]

    def __init__(self, params, deps):
        self.swing = deps["swing"]

        # Current bias
        self._bias: str = "ranging"  # "bullish", "bearish", "ranging"

        # Break tracking
        self._last_bos_idx: int = -1
        self._last_bos_level: float = float('nan')
        self._last_choch_idx: int = -1
        self._last_choch_level: float = float('nan')

        # Event flags (reset each bar)
        self._bos_this_bar: bool = False
        self._choch_this_bar: bool = False

        # Levels to watch for breaks
        self._bull_break_level: float = float('nan')  # High to break for bullish BOS
        self._bear_break_level: float = float('nan')  # Low to break for bearish BOS
        self._bull_choch_level: float = float('nan')  # Low to break for bullish CHoCH
        self._bear_choch_level: float = float('nan')  # High to break for bearish CHoCH

        self._version: int = 0

    def update(self, bar_idx: int, bar: BarData) -> None:
        # Reset event flags
        self._bos_this_bar = False
        self._choch_this_bar = False

        # Get current price
        high = bar.high
        low = bar.low

        # Check for breaks
        if self._bias == "bullish":
            # In uptrend, look for:
            # - BOS: Price breaks above last swing high (continuation)
            # - CHoCH: Price breaks below last swing low (reversal)

            if high > self._bull_break_level:
                self._bos_this_bar = True
                self._last_bos_idx = bar_idx
                self._last_bos_level = self._bull_break_level
                self._update_break_levels()
                self._version += 1

            elif low < self._bull_choch_level:
                self._choch_this_bar = True
                self._last_choch_idx = bar_idx
                self._last_choch_level = self._bull_choch_level
                self._bias = "bearish"
                self._update_break_levels()
                self._version += 1

        elif self._bias == "bearish":
            # In downtrend, look for:
            # - BOS: Price breaks below last swing low (continuation)
            # - CHoCH: Price breaks above last swing high (reversal)

            if low < self._bear_break_level:
                self._bos_this_bar = True
                self._last_bos_idx = bar_idx
                self._last_bos_level = self._bear_break_level
                self._update_break_levels()
                self._version += 1

            elif high > self._bear_choch_level:
                self._choch_this_bar = True
                self._last_choch_idx = bar_idx
                self._last_choch_level = self._bear_choch_level
                self._bias = "bullish"
                self._update_break_levels()
                self._version += 1

        else:  # Ranging - establish initial bias
            self._establish_initial_bias(bar_idx, bar)
```

### 5.3 Outputs

```python
def get_output_keys(self) -> list[str]:
    return [
        "bias",              # "bullish", "bearish", "ranging"
        "bos_this_bar",      # True if BOS occurred this bar
        "choch_this_bar",    # True if CHoCH occurred this bar
        "last_bos_idx",      # Bar index of last BOS
        "last_bos_level",    # Price level of last BOS
        "last_choch_idx",    # Bar index of last CHoCH
        "last_choch_level",  # Price level of last CHoCH
        "version",           # Increments on any structure event
    ]
```

### Gate 5 Validation Plays

| Play | Description | Validates |
|------|-------------|-----------|
| `V_PF_050_bos_bullish` | Uptrend, break above high → BOS | Bullish BOS |
| `V_PF_051_bos_bearish` | Downtrend, break below low → BOS | Bearish BOS |
| `V_PF_052_choch_bull_to_bear` | Uptrend, break below low → CHoCH | Reversal detection |
| `V_PF_053_choch_bear_to_bull` | Downtrend, break above high → CHoCH | Reversal detection |
| `V_PF_054_event_flags_reset` | Flags reset each bar | Event semantics |
| `V_PF_055_version_increment` | Version bumps on events | Version tracking |
| `V_PF_056_initial_bias` | First structure establishes bias | Initialization |

### Gate 5 Deliverables

- [x] Create `src/backtest/incremental/detectors/market_structure.py`
- [x] Register with `@register_structure("market_structure")`
- [x] Implement BOS detection logic (bullish and bearish)
- [x] Implement CHoCH detection logic (bias flips)
- [x] Add to registry output types (both registries)
- [x] Add warmup formula (both registries)
- [x] Create validation Plays V_PF_050-056
- [x] Run smoke tests

---

## Gate 6: Multi-Timeframe Pivot Coordination

> **Goal**: Ensure high_tf and exec_tf pivots work together correctly

### 6.1 The Pattern

```yaml
timeframes:
  high_tf: 4h    # Significant pivots, stable Fib
  exec_tf: 15m   # Entry timing

structures:
  high_tf:
    - type: swing
      key: swing
      params:
        left: 10
        right: 10
        mode: atr_zigzag     # Fewer, significant pivots
        atr_key: atr_14
        atr_multiplier: 2.0

    - type: fibonacci
      key: fib
      depends_on: { swing: swing }
      params:
        levels: [0.5, 0.618, 0.786]
        use_paired_anchor: true

    - type: market_structure
      key: ms
      depends_on: { swing: swing }

  exec:
    - type: swing
      key: swing
      params:
        left: 3
        right: 3
        mode: fractal        # More pivots for precise entry
        strict_alternation: true

    - type: market_structure
      key: ms
      depends_on: { swing: swing }
```

### 6.2 Coordination Rules

```
high_tf.ms.bias = "bullish"      # Direction from structure
    │
    ├── Only take LONG entries on exec_tf
    │
    └── Wait for exec_tf.ms.bos_this_bar = true
            │
            └── Entry confirmation within high_tf Fib zone
```

### 6.3 Validation Plays

| Play | Description | Validates |
|------|-------------|-----------|
| `V_PF_060_high_tf_stable_anchor` | ATR zigzag on high_tf → stable Fib | Anchor stability |
| `V_PF_061_exec_precise_entry` | Fractal on exec_tf → precise timing | Entry precision |
| `V_PF_062_bias_alignment` | exec entry only when high_tf bias matches | Multi-TF coordination |
| `V_PF_063_bos_within_fib` | exec BOS inside high_tf Fib zone | Zone + event combo |

### Gate 6 Deliverables

- [ ] Create Multi-TF pivot coordination documentation
- [ ] Create example Plays showing pattern
- [ ] Create validation Plays V_PF_060-063
- [ ] Update PLAY_DSL_COOKBOOK.md with Multi-TF pivot patterns
- [ ] Run smoke tests

---

## Gate 7: Integration & Stress Testing

> **Goal**: Comprehensive validation with real market data

### 7.1 Stress Test Plays

```yaml
# S_PF_001: BTC 1-year backtest with ATR zigzag
# S_PF_002: ETH high volatility period
# S_PF_003: SOL low volatility (ranging) period
# S_PF_004: Multi-symbol comparison
# S_PF_005: All modes comparison on same data
```

### 7.2 Regression Tests

Ensure all existing Plays continue to work:

```bash
# Run full smoke test suite
python trade_cli.py --smoke full

# Specifically test pivot-dependent structures
python trade_cli.py --smoke structure
```

### 7.3 Performance Benchmarks

| Metric | Target | Measured |
|--------|--------|----------|
| Swing update (fractal) | < 1ms | TBD |
| Swing update (zigzag) | < 1ms | TBD |
| Trend update | < 0.5ms | TBD |
| Market structure update | < 0.5ms | TBD |
| Full snapshot build | < 10ms | TBD |

### Gate 7 Deliverables

- [ ] Create stress test Plays S_PF_001-005
- [ ] Run regression on all existing Plays
- [ ] Performance benchmark all modes
- [ ] Document mode selection guidelines
- [ ] Update TODO.md with completion status

---

## Dependency Graph

```
Gate 0 (Significance Infrastructure)
    │
    ├──> Gate 1 (Significance Filtering)
    │        │
    │        └──> Gate 3 (ATR ZigZag Mode)
    │
    └──> Gate 2 (Strict Alternation)
             │
             └──> Gate 4 (Trend Rewrite)
                      │
                      └──> Gate 5 (Market Structure)
                               │
                               └──> Gate 6 (Multi-TF Coordination)
                                        │
                                        └──> Gate 7 (Integration)
```

---

## Timeline Estimate

| Gate | Complexity | Dependencies |
|------|------------|--------------|
| Gate 0 | Low | None |
| Gate 1 | Low | Gate 0 |
| Gate 2 | Medium | None |
| Gate 3 | Medium | Gate 0 |
| Gate 4 | Medium | Gate 2 |
| Gate 5 | Medium | Gate 4 |
| Gate 6 | Low | Gates 3, 5 |
| Gate 7 | Low | All |

---

## Success Criteria

### Functional
- [ ] All validation Plays pass
- [ ] All existing Plays continue to work (regression)
- [ ] Smoke tests green

### Quality
- [ ] ATR zigzag produces 50-70% fewer pivots than fractal in choppy markets
- [ ] Fib anchor changes reduced by 40%+ with significance filtering
- [ ] Trend direction matches manual analysis on test cases
- [ ] BOS/CHoCH events fire at correct bars

### Performance
- [ ] All updates remain O(1) or O(window)
- [ ] No measurable slowdown in backtest speed
- [ ] Memory usage increase < 10%

---

## Files to Create/Modify

### New Files
- `src/structures/detectors/market_structure.py`
- `docs/todos/PIVOT_FOUNDATION_GATES.md` (this file)
- `tests/validation/plays/pivot_foundation/V_PF_*.yml` (validation Plays)
- `tests/stress/plays/pivot_foundation/S_PF_*.yml` (stress tests)

### Modified Files
- `src/structures/detectors/swing.py` (Gates 0-3)
- `src/structures/detectors/trend.py` (Gate 4)
- `src/structures/registry.py` (new outputs)
- `docs/PLAY_DSL_COOKBOOK.md` (new parameters, modes)
- `docs/TODO.md` (track progress)

---

## References

- [TradingView ZigZag Scripts](https://www.tradingview.com/scripts/zigzag/)
- [Swing High/Low Adaptive](https://www.tradingview.com/script/yRh7OKsh-Swing-High-Low-Adaptive/)
- [Williams Fractal](https://in.tradingview.com/scripts/williamsfractal/)
- [TradingView ZigZag Library](https://www.tradingview.com/script/bzIRuGXC-ZigZag/)
- Internal: `src/structures/detectors/swing.py` (current implementation)
- Internal: `src/structures/detectors/trend.py` (current implementation)
