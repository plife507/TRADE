# Market Structure Features — Reference

> **Status**: All 6 ICT structure detectors implemented and validated
> **Created**: 2026-02-26
> **Purpose**: Detailed specs for ICT/SMC structure detectors and indicators

---

## Why These Features

The 7 core structure detectors (swing, trend, zone, fibonacci, rolling_window, derived_zone, market_structure) cover *price action mechanics*. The 6 ICT detectors add the *institutional narrative*. ICT/SMC theory describes a sequence:

```
Liquidity sweep --> Displacement --> FVG creation --> Order block forms
    --> Price returns to OB/FVG for entry --> Continuation or reversal
```

We have the endpoints (swings, BOS/CHoCH, zones) but lack the connective tissue. Adding these features enables:
1. **Complete ICT trade setups** in Play YAML
2. **Market Intelligence (M6)** training data — "what institutional patterns precede profitable moves?"
3. **Higher-quality Play generation** — agents can build plays using the full SMC vocabulary

---

## Build Order (all Tier 1, 2, 3 structure detectors complete)

```
Tier 1 (core ICT chain) — COMPLETE:
  1. Displacement ────────── simple candle analysis, no deps
  2. Fair Value Gap ──────── 3-candle pattern, no deps
  3. Order Block ─────────── depends on swing + displacement
  4. Liquidity Zones ─────── depends on swing (cluster detection)

Tier 2 (M6 intelligence):
  5. Volume Profile / POC ── indicator (not structure), volume bucketing
  6. Anchored Vol Profile ── indicator, extends #5 with event-based reset
  7. Premium/Discount ────── COMPLETE (structure detector)

Tier 3 (refinements):
  8. Breaker Blocks ──────── COMPLETE (depends on order blocks + CHoCH)
  9. Session Highs/Lows ──── indicator (not structure), time-based reference levels
 10. Mitigation Tracking ─── deferred enhancement to FVG + OB lifecycle
```

Note: Items 5, 6, and 9 are indicators, not structure detectors. The 6 ICT structure detectors
(displacement, fair_value_gap, order_block, liquidity_zones, premium_discount, breaker_block)
are all implemented and validated.

**Dependency graph:**
```
swing (exists) ──+──> order_block ──> breaker_block
                 |
                 +──> liquidity_zones
                 |
                 +──> premium_discount
                 |
ATR (exists) ────+──> displacement ──> order_block

(none) ──────────+──> fair_value_gap ──> mitigation_tracking
                 |
                 +──> volume_profile ──> anchored_volume_profile

(time-based) ────+──> session_highs_lows
```

---

## Tier 1: Core ICT Chain

---

### 1. Displacement

**Type**: Structure detector
**Depends on**: None (uses ATR from `bar.indicators`)
**Registry name**: `displacement`

#### What It Is

A displacement is a strong impulsive candle — large body, small wicks relative to ATR. It signals institutional activity: a large order was executed and moved price decisively. Displacements are the *cause* that creates FVGs and validates Order Blocks.

#### Trading Logic

- Bullish displacement: large green body, close near high, body > threshold * ATR
- Bearish displacement: large red body, close near low, body > threshold * ATR
- Wick ratio: small wicks relative to body (wick_total / body < wick_threshold)
- A valid Order Block must be preceded by a displacement candle

#### Implementation Spec

```python
@register_structure("displacement")
class IncrementalDisplacement(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "atr_key": "atr",          # Which ATR indicator to read
        "body_atr_min": 1.5,       # Minimum body size as ATR multiple
        "wick_ratio_max": 0.4,     # Max (upper_wick + lower_wick) / body
    }
    DEPENDS_ON = []
```

**State**:
```python
# Reset each bar
self._is_displacement: bool = False      # True if current bar qualifies
self._direction: int = 0                 # 1 = bullish, -1 = bearish
self._body_atr_ratio: float = nan        # How many ATRs the body spans
self._wick_ratio: float = nan            # Total wick / body

# Persistent
self._last_displacement_idx: int = -1    # Most recent displacement bar
self._last_displacement_dir: int = 0     # Direction of most recent
self._version: int = 0                   # Increments on each displacement
```

**Update logic**:
```python
def update(self, bar_idx: int, bar: BarData) -> None:
    # Reset per-bar flags
    self._is_displacement = False
    self._direction = 0

    atr = bar.indicators.get(self.atr_key, nan)
    if isnan(atr) or atr <= 0:
        return

    body = abs(bar.close - bar.open)
    upper_wick = bar.high - max(bar.open, bar.close)
    lower_wick = min(bar.open, bar.close) - bar.low

    self._body_atr_ratio = body / atr
    total_wick = upper_wick + lower_wick
    self._wick_ratio = total_wick / body if body > 0 else inf

    if self._body_atr_ratio >= self.body_atr_min and self._wick_ratio <= self.wick_ratio_max:
        self._is_displacement = True
        self._direction = 1 if bar.close > bar.open else -1
        self._last_displacement_idx = bar_idx
        self._last_displacement_dir = self._direction
        self._version += 1
```

#### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `is_displacement` | BOOL | True if this bar is a displacement |
| `direction` | INT | 1 = bullish, -1 = bearish, 0 = none |
| `body_atr_ratio` | FLOAT | Body size as multiple of ATR |
| `wick_ratio` | FLOAT | Total wick / body ratio |
| `last_idx` | INT | Bar index of most recent displacement |
| `last_direction` | INT | Direction of most recent displacement |
| `version` | INT | Monotonic counter |

#### Edge Cases

- **Zero ATR**: Skip (no displacement on zero-volatility bars)
- **Doji candle** (body = 0): Never a displacement (wick_ratio = inf)
- **Gap candles**: Body calculation uses open/close, not high/low — gaps are in wicks
- **First bar**: No displacement possible if ATR not ready

#### Warmup

```python
"displacement": lambda params, swing_params: 1  # Ready after 1 bar (if ATR is ready)
```

Note: Actual warmup depends on the ATR indicator's warmup (typically 14 bars). The structure detector itself needs 0 warmup — it just reads ATR from `bar.indicators`.

#### Validation Play

```yaml
name: "val_displacement_basic"
validation:
  synthetic: displacement_impulse  # Needs new synthetic pattern
  expected_trades: 2
  expected_direction: both
features:
  atr_14: { indicator: atr, params: { length: 14 } }
structures:
  exec:
    - type: displacement
      key: disp
      params: { atr_key: atr_14, body_atr_min: 1.5, wick_ratio_max: 0.4 }
actions:
  entry_long:
    all:
      - ["disp.is_displacement", "==", true]
      - ["disp.direction", "==", 1]
```

#### DSL Usage Examples

```yaml
# Entry on displacement
- ["disp.is_displacement", "==", true]
- ["disp.direction", "==", 1]

# Filter: only trade after strong displacement
- ["disp.body_atr_ratio", ">=", 2.0]

# Combine with BOS
- ["ms.bos_this_bar", "==", true]
- ["disp.is_displacement", "==", true]
```

---

### 2. Fair Value Gap (FVG)

**Type**: Structure detector
**Depends on**: None (pure price pattern)
**Registry name**: `fair_value_gap`

#### What It Is

An FVG is a 3-candle pattern where a strong move creates a gap between candle 1's range and candle 3's range. This gap represents a price imbalance — the market moved so fast that not all orders were filled. Price tends to return to fill these gaps ~70% of the time.

```
Bullish FVG:          Bearish FVG:
candle_1.high         candle_1.low
    |  <-- GAP -->        |  <-- GAP -->
candle_3.low          candle_3.high
```

#### Trading Logic

- **Bullish FVG**: `candle_3.low > candle_1.high` — gap between candle 1 high and candle 3 low
- **Bearish FVG**: `candle_3.high < candle_1.low` — gap between candle 1 low and candle 3 high
- **Midpoint (CE)**: Center of the gap — common target/entry level (Consequent Encroachment)
- **Mitigation**: When price returns and fills 50%+ of the gap
- **Invalidation**: When price fully closes through the gap

#### Implementation Spec

```python
@register_structure("fair_value_gap")
class IncrementalFVG(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "atr_key": "atr",          # For significance filtering
        "min_gap_atr": 0.0,        # Minimum gap size as ATR multiple (0 = no filter)
        "max_active": 5,           # Maximum tracked active FVGs
    }
    DEPENDS_ON = []
```

**State**:
```python
# Ring buffer for 3-candle lookback
self._candle_buf: deque[tuple[float, float, float, float]]  # (open, high, low, close) x 3

# Active FVG slots (fixed-size array, oldest evicted)
self._fvgs: list[FVGSlot]  # Each: direction, upper, lower, anchor_idx, mitigated, fill_pct
self._max_active: int

# Current bar outputs
self._new_fvg_this_bar: bool = False
self._new_fvg_direction: int = 0  # 1 = bullish, -1 = bearish
self._new_fvg_upper: float = nan
self._new_fvg_lower: float = nan

# Most recent active FVG (for simple DSL access)
self._nearest_bull_upper: float = nan
self._nearest_bull_lower: float = nan
self._nearest_bear_upper: float = nan
self._nearest_bear_lower: float = nan

# Aggregate stats
self._active_bull_count: int = 0
self._active_bear_count: int = 0
self._any_mitigated_this_bar: bool = False

self._version: int = 0
```

**Update logic**:
```python
def update(self, bar_idx: int, bar: BarData) -> None:
    # Reset per-bar flags
    self._new_fvg_this_bar = False
    self._new_fvg_direction = 0
    self._any_mitigated_this_bar = False

    # Push current bar to buffer
    self._candle_buf.append((bar.open, bar.high, bar.low, bar.close))
    if len(self._candle_buf) < 3:
        return

    c1_open, c1_high, c1_low, c1_close = self._candle_buf[-3]  # Candle 1 (oldest)
    c2_open, c2_high, c2_low, c2_close = self._candle_buf[-2]  # Candle 2 (middle)
    c3_open, c3_high, c3_low, c3_close = self._candle_buf[-1]  # Candle 3 (newest = current)

    # Detect bullish FVG: gap between c1 high and c3 low
    if c3_low > c1_high:
        gap_size = c3_low - c1_high
        if self._passes_filter(gap_size, bar):
            self._create_fvg(1, c3_low, c1_high, bar_idx - 1)  # Anchor on middle candle

    # Detect bearish FVG: gap between c1 low and c3 high
    elif c3_high < c1_low:
        gap_size = c1_low - c3_high
        if self._passes_filter(gap_size, bar):
            self._create_fvg(-1, c1_low, c3_high, bar_idx - 1)

    # Update mitigation state for all active FVGs
    for fvg in self._fvgs:
        if fvg.state == "active":
            self._check_mitigation(fvg, bar)

    # Recompute nearest/aggregate outputs
    self._recompute_aggregates()
```

**Mitigation logic**:
```python
def _check_mitigation(self, fvg: FVGSlot, bar: BarData) -> None:
    if fvg.direction == 1:  # Bullish FVG
        # Price dips into the gap
        if bar.low <= fvg.upper:
            # Calculate fill percentage
            gap_range = fvg.upper - fvg.lower
            if gap_range > 0:
                penetration = fvg.upper - max(bar.low, fvg.lower)
                fvg.fill_pct = min(1.0, penetration / gap_range)

            # Full invalidation: price closes below lower bound
            if bar.close < fvg.lower:
                fvg.state = "invalidated"
            # Partial mitigation: price entered gap (50%+ fill)
            elif fvg.fill_pct >= 0.5:
                fvg.state = "mitigated"
                self._any_mitigated_this_bar = True

    elif fvg.direction == -1:  # Bearish FVG
        if bar.high >= fvg.lower:
            gap_range = fvg.upper - fvg.lower
            if gap_range > 0:
                penetration = min(bar.high, fvg.upper) - fvg.lower
                fvg.fill_pct = min(1.0, penetration / gap_range)

            if bar.close > fvg.upper:
                fvg.state = "invalidated"
            elif fvg.fill_pct >= 0.5:
                fvg.state = "mitigated"
                self._any_mitigated_this_bar = True
```

#### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `new_this_bar` | BOOL | True if a new FVG formed on this bar |
| `new_direction` | INT | Direction of new FVG (1/-1/0) |
| `new_upper` | FLOAT | Upper boundary of new FVG |
| `new_lower` | FLOAT | Lower boundary of new FVG |
| `nearest_bull_upper` | FLOAT | Upper bound of nearest active bullish FVG |
| `nearest_bull_lower` | FLOAT | Lower bound of nearest active bullish FVG |
| `nearest_bear_upper` | FLOAT | Upper bound of nearest active bearish FVG |
| `nearest_bear_lower` | FLOAT | Lower bound of nearest active bearish FVG |
| `active_bull_count` | INT | Number of active bullish FVGs |
| `active_bear_count` | INT | Number of active bearish FVGs |
| `any_mitigated_this_bar` | BOOL | True if any FVG was mitigated this bar |
| `version` | INT | Monotonic counter |

#### Edge Cases

- **Consecutive FVGs**: Multiple FVGs can form in a strong trend. `max_active` caps tracking.
- **Overlapping FVGs**: Two FVGs can overlap in price. Both tracked independently.
- **Tiny gaps**: `min_gap_atr` filter prevents noise FVGs in choppy markets.
- **Gap on first 3 bars**: Valid — no warmup needed beyond 3 candles.
- **FVG formed then immediately filled**: State goes `active -> mitigated` in same bar sequence.

#### Warmup

```python
"fair_value_gap": lambda params, swing_params: 3  # Need 3 candles minimum
```

#### Validation Play

```yaml
name: "val_fvg_basic"
validation:
  synthetic: trending_up  # Strong trend creates FVGs naturally
  expected_trades: 1
features:
  atr_14: { indicator: atr, params: { length: 14 } }
structures:
  exec:
    - type: fair_value_gap
      key: fvg
      params: { atr_key: atr_14, min_gap_atr: 0.5, max_active: 5 }
actions:
  entry_long:
    all:
      - ["fvg.active_bull_count", ">", 0]
      - ["close", "near_abs", "fvg.nearest_bull_upper"]
```

#### DSL Usage Examples

```yaml
# Enter on FVG creation
- ["fvg.new_this_bar", "==", true]
- ["fvg.new_direction", "==", 1]

# Enter on price returning to bullish FVG
- ["fvg.active_bull_count", ">", 0]
- ["close", "<=", "fvg.nearest_bull_upper"]
- ["close", ">=", "fvg.nearest_bull_lower"]

# Combine FVG with market structure
- ["ms.bias", "==", 1]
- ["fvg.active_bull_count", ">", 0]
```

---

### 3. Order Block (OB)

**Type**: Structure detector
**Depends on**: `swing`, optionally `displacement`
**Registry name**: `order_block`

#### What It Is

An Order Block is the last opposing candle before a displacement move. In a bullish scenario: the last bearish candle before a strong bullish displacement. This candle represents where institutions accumulated their position. When price returns to this zone, institutions defend it.

```
Bullish Order Block:
  ... bearish candle (THE OB) ...
  ... DISPLACEMENT UP (strong bullish candle) ...
  ... continuation ...
  ... price returns to OB zone -> ENTRY

Bearish Order Block:
  ... bullish candle (THE OB) ...
  ... DISPLACEMENT DOWN (strong bearish candle) ...
  ... continuation ...
  ... price returns to OB zone -> ENTRY
```

#### Trading Logic

- **Bullish OB**: Last bearish candle before a bullish displacement. Zone = [OB candle low, OB candle high].
- **Bearish OB**: Last bullish candle before a bearish displacement. Zone = [OB candle low, OB candle high].
- **Refinement**: Use OB candle body (open-close range) instead of full range for tighter zone.
- **Validation**: OB must be followed by a BOS or swing break to confirm institutional intent.
- **Mitigation**: When price returns and wicks into the OB zone.
- **Invalidation**: When price fully closes through the OB (institutions abandoned the level).

#### Implementation Spec

```python
@register_structure("order_block")
class IncrementalOrderBlock(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "atr_key": "atr",
        "use_body": True,            # True = OB zone is body (open-close), False = full range (high-low)
        "require_displacement": True, # Must follow a displacement candle
        "body_atr_min": 1.5,         # Displacement threshold (if no displacement detector)
        "wick_ratio_max": 0.4,       # Displacement wick filter
        "max_active": 5,             # Max tracked OBs
        "lookback": 3,               # How many candles back to search for opposing candle
    }
    DEPENDS_ON = ["swing"]
    OPTIONAL_DEPS = ["displacement"]
```

**State**:
```python
# Candle history buffer (for lookback)
self._candle_history: deque[tuple]  # (idx, open, high, low, close, volume)

# Active OB slots
self._obs: list[OBSlot]  # Each: direction, upper, lower, anchor_idx, state, volume, strength

# Per-bar outputs
self._new_ob_this_bar: bool = False
self._new_ob_direction: int = 0
self._new_ob_upper: float = nan
self._new_ob_lower: float = nan

# Nearest active OB for simple access
self._nearest_bull_upper: float = nan
self._nearest_bull_lower: float = nan
self._nearest_bear_upper: float = nan
self._nearest_bear_lower: float = nan

self._active_bull_count: int = 0
self._active_bear_count: int = 0
self._any_mitigated_this_bar: bool = False
self._version: int = 0
```

**Update logic**:
```python
def update(self, bar_idx: int, bar: BarData) -> None:
    self._new_ob_this_bar = False
    self._new_ob_direction = 0
    self._any_mitigated_this_bar = False

    # Check for displacement (via dependency or inline calculation)
    is_disp, disp_dir = self._check_displacement(bar)

    if is_disp:
        # Search backward for opposing candle
        ob_candle = self._find_opposing_candle(disp_dir)
        if ob_candle is not None:
            self._create_ob(disp_dir, ob_candle, bar_idx)

    # Store current candle in history
    self._candle_history.append((bar_idx, bar.open, bar.high, bar.low, bar.close, bar.volume))
    if len(self._candle_history) > self.lookback + 2:
        self._candle_history.popleft()

    # Update mitigation/invalidation for all active OBs
    for ob in self._obs:
        if ob.state == "active":
            self._check_ob_mitigation(ob, bar)

    self._recompute_aggregates()

def _find_opposing_candle(self, disp_direction: int) -> tuple | None:
    """Find the last candle opposing the displacement direction."""
    for candle in reversed(self._candle_history):
        idx, o, h, l, c, v = candle
        is_bearish = c < o
        is_bullish = c > o
        if disp_direction == 1 and is_bearish:
            return candle  # Last bearish candle before bullish displacement
        if disp_direction == -1 and is_bullish:
            return candle  # Last bullish candle before bearish displacement
    return None
```

#### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `new_this_bar` | BOOL | True if new OB formed |
| `new_direction` | INT | 1 = bullish OB, -1 = bearish OB |
| `new_upper` | FLOAT | Upper boundary of new OB |
| `new_lower` | FLOAT | Lower boundary of new OB |
| `nearest_bull_upper` | FLOAT | Nearest active bullish OB upper |
| `nearest_bull_lower` | FLOAT | Nearest active bullish OB lower |
| `nearest_bear_upper` | FLOAT | Nearest active bearish OB upper |
| `nearest_bear_lower` | FLOAT | Nearest active bearish OB lower |
| `active_bull_count` | INT | Active bullish OBs |
| `active_bear_count` | INT | Active bearish OBs |
| `any_mitigated_this_bar` | BOOL | True if any OB was touched this bar |
| `version` | INT | Monotonic counter |

#### Edge Cases

- **No opposing candle found**: No OB created (displacement without setup)
- **Multiple displacements in sequence**: Each creates its own OB from its preceding opposing candle
- **OB and FVG overlap**: Normal and expected — they often coincide. DSL can require both.
- **OB immediately mitigated**: Next bar retraces into OB zone — valid, state transitions correctly
- **Swing not yet confirmed**: OBs form on displacement, not on swing confirmation — they are forward-looking

#### Warmup

```python
"order_block": lambda params, swing_params: max(
    params.get("lookback", 3) + 2,
    swing_params["left"] + swing_params["right"]
)
```

#### DSL Usage Examples

```yaml
# Classic OB entry: price returns to bullish OB in uptrend
- ["ms.bias", "==", 1]
- ["ob.active_bull_count", ">", 0]
- ["close", "<=", "ob.nearest_bull_upper"]
- ["close", ">=", "ob.nearest_bull_lower"]

# OB + FVG confluence (strongest setup)
- ["ob.active_bull_count", ">", 0]
- ["fvg.active_bull_count", ">", 0]
- ["close", "near_abs", "ob.nearest_bull_lower"]

# New OB event
- ["ob.new_this_bar", "==", true]
- ["ob.new_direction", "==", 1]
```

---

### 4. Liquidity Zones (Equal Highs/Lows)

**Type**: Structure detector
**Depends on**: `swing`
**Registry name**: `liquidity_zones`

#### What It Is

Liquidity zones form when multiple swing highs or swing lows cluster at similar price levels. These clusters represent pools of stop-loss orders. When price sweeps through a liquidity zone, it triggers stop losses and provides institutional fills. A sweep followed by reversal is a high-probability trade setup.

```
Equal Highs (EQH):       Equal Lows (EQL):
  H1 ≈ H2 ≈ H3             L1 ≈ L2 ≈ L3
  ─────────── <-- liquidity  ─────────── <-- liquidity
              above                       below

Sweep: price pierces the     Sweep: price pierces the
cluster then reverses        cluster then reverses
```

#### Trading Logic

- **Detection**: Two or more swing highs (or lows) within `tolerance_atr * ATR` of each other
- **Level**: Average of the clustered swing prices
- **Sweep**: Price exceeds the level by at least `sweep_atr * ATR` then returns below
- **Entry**: After sweep + reversal signal (BOS, CHoCH, or displacement in opposite direction)
- **More touches = more liquidity**: Track touch count for strength scoring

#### Implementation Spec

```python
@register_structure("liquidity_zones")
class IncrementalLiquidityZones(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "atr_key": "atr",
        "tolerance_atr": 0.3,     # Max distance between clustered swings (ATR multiple)
        "sweep_atr": 0.1,         # Min penetration to count as sweep
        "min_touches": 2,          # Min swing touches to form a zone
        "max_active": 5,           # Max tracked zones
    }
    DEPENDS_ON = ["swing"]
```

**State**:
```python
# Track swing history for clustering
self._swing_highs: deque[tuple[int, float]]  # (bar_idx, price) recent swing highs
self._swing_lows: deque[tuple[int, float]]    # (bar_idx, price) recent swing lows

# Active liquidity zones
self._zones: list[LiquiditySlot]  # direction (1=above/highs, -1=below/lows),
                                   # level, touches, state, sweep_bar_idx

# Per-bar flags
self._new_zone_this_bar: bool = False
self._sweep_this_bar: bool = False
self._sweep_direction: int = 0      # 1 = swept highs (bearish signal), -1 = swept lows (bullish signal)
self._swept_level: float = nan

# Nearest zones
self._nearest_high_level: float = nan  # Nearest EQH above current price
self._nearest_low_level: float = nan   # Nearest EQL below current price
self._nearest_high_touches: int = 0
self._nearest_low_touches: int = 0

self._version: int = 0
```

**Update logic**:
```python
def update(self, bar_idx: int, bar: BarData) -> None:
    self._new_zone_this_bar = False
    self._sweep_this_bar = False
    self._sweep_direction = 0

    atr = bar.indicators.get(self.atr_key, nan)

    # Track new swing pivots from dependency
    high_idx = self.swing.get_value("high_idx")
    low_idx = self.swing.get_value("low_idx")

    if high_idx != self._last_high_idx and high_idx >= 0:
        self._swing_highs.append((high_idx, self.swing.get_value("high_level")))
        self._last_high_idx = high_idx
        self._try_form_zone("high", atr)

    if low_idx != self._last_low_idx and low_idx >= 0:
        self._swing_lows.append((low_idx, self.swing.get_value("low_level")))
        self._last_low_idx = low_idx
        self._try_form_zone("low", atr)

    # Check sweeps on active zones
    for zone in self._zones:
        if zone.state == "active":
            self._check_sweep(zone, bar, atr)

    self._recompute_nearest(bar.close)

def _try_form_zone(self, side: str, atr: float) -> None:
    """Check if recent swing pivots cluster into a liquidity zone."""
    swings = self._swing_highs if side == "high" else self._swing_lows
    tolerance = self.tolerance_atr * atr if not isnan(atr) else 0

    # Check last N swings for clustering
    recent = list(swings)[-10:]  # Look at last 10 swings
    for i, (idx_i, price_i) in enumerate(recent):
        cluster = [(idx_i, price_i)]
        for j in range(i + 1, len(recent)):
            idx_j, price_j = recent[j]
            if abs(price_j - price_i) <= tolerance:
                cluster.append((idx_j, price_j))

        if len(cluster) >= self.min_touches:
            avg_level = sum(p for _, p in cluster) / len(cluster)
            # Create or update zone at this level
            self._upsert_zone(side, avg_level, len(cluster))
```

#### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `new_zone_this_bar` | BOOL | New liquidity zone formed |
| `sweep_this_bar` | BOOL | A liquidity zone was swept this bar |
| `sweep_direction` | INT | 1 = swept highs (sell signal), -1 = swept lows (buy signal) |
| `swept_level` | FLOAT | Price level that was swept |
| `nearest_high_level` | FLOAT | Nearest EQH level above price |
| `nearest_low_level` | FLOAT | Nearest EQL level below price |
| `nearest_high_touches` | INT | Touch count of nearest EQH |
| `nearest_low_touches` | INT | Touch count of nearest EQL |
| `version` | INT | Monotonic counter |

#### Edge Cases

- **Sparse swings**: If swing detector uses large `left`/`right`, clusters may be rare. That's correct.
- **One-touch "cluster"**: Not a cluster. `min_touches=2` enforced.
- **Zone swept then reformed**: A swept zone is removed. New swings can form a new zone at same level.
- **Multiple sweeps same bar**: Track most significant (highest liquidity zone).

#### Warmup

```python
"liquidity_zones": lambda params, swing_params: (
    (swing_params["left"] + swing_params["right"]) * params.get("min_touches", 2)
)
```

#### DSL Usage Examples

```yaml
# Classic liquidity sweep reversal
- ["liq.sweep_this_bar", "==", true]
- ["liq.sweep_direction", "==", -1]  # Swept lows = bullish signal
- ["ms.bias", "==", 1]

# Enter near liquidity (anticipate sweep)
- ["close", "near_pct", "liq.nearest_low_level", 0.002]

# Strength filter: only trade high-touch zones
- ["liq.nearest_low_touches", ">=", 3]
```

---

## Tier 2: M6 Intelligence

---

### 5. Volume Profile / POC

**Type**: Indicator (multi-output)
**Depends on**: None (uses OHLCV data)
**Registry name**: `volume_profile`

#### What It Is

Volume Profile distributes volume across price levels (not time). The Point of Control (POC) is the price with the highest volume. Value Area High (VAH) and Value Area Low (VAL) bound 70% of volume. This tells you WHERE institutions are positioned.

#### Implementation Approach

**Incremental O(1) design**: Use fixed-size price buckets. On each bar, distribute the bar's volume across the price levels it touched (proportional to time-in-level approximation using OHLC).

```python
@dataclass
class IncrementalVolumeProfile(IncrementalIndicator):
    num_buckets: int = 100         # Price resolution
    lookback: int = 50             # Rolling window (bars)
    value_area_pct: float = 0.70   # 70% value area

    # State
    _price_min: float              # Dynamic range tracking
    _price_max: float
    _bucket_volumes: ndarray       # shape (num_buckets,) - volume per price level
    _bar_contributions: deque      # For rolling window eviction
```

**Key challenge**: Price range changes over time. Two approaches:
- **A. Fixed range**: Set min/max from first N bars, rebin if price escapes. Simple but jumpy.
- **B. Rolling range**: Track range from lookback window, rebin each bar. Smooth but O(buckets) per rebin.

**Recommendation**: Approach B with lazy rebinning (only rebin when price exceeds range by 10%+).

#### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `poc` | FLOAT | Point of Control price level |
| `vah` | FLOAT | Value Area High |
| `val` | FLOAT | Value Area Low |
| `poc_volume` | FLOAT | Volume at POC level |
| `value_area_volume_pct` | FLOAT | % of total volume in value area |
| `above_poc` | BOOL | Current price above POC |
| `in_value_area` | BOOL | Current price between VAH and VAL |

#### Warmup

```python
"volume_profile": lambda params: params.get("lookback", 50)
```

---

### 6. Anchored Volume Profile

**Type**: Indicator (multi-output)
**Depends on**: Volume Profile logic + anchor event
**Registry name**: `anchored_volume_profile`

#### What It Is

Same as Volume Profile but resets on a structural event (BOS, swing pair, session boundary). Answers: "Since the last BOS, where has the most volume traded?"

**Follows the same pattern as `anchored_vwap`**: Uses `kwargs` to receive swing/structure metadata, resets accumulation on version change.

#### Output Fields

Same as `volume_profile` plus `bars_since_anchor`.

---

### 7. Premium/Discount Zones

**Type**: Structure detector
**Depends on**: `swing` (pair range)
**Registry name**: `premium_discount`

#### What It Is

Divides the current swing range (pair_high to pair_low) into premium (upper 50%) and discount (lower 50%). Equilibrium is the midpoint.

**Trivial implementation**: Reads `pair_high_level` and `pair_low_level` from swing dependency.

#### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `equilibrium` | FLOAT | Midpoint of swing range |
| `premium_level` | FLOAT | 75% of range (deep premium) |
| `discount_level` | FLOAT | 25% of range (deep discount) |
| `zone` | ENUM | "premium", "discount", "equilibrium", "none" |
| `depth_pct` | FLOAT | 0.0 (at low) to 1.0 (at high) — current price position in range |

---

## Tier 3: Refinements

---

### 8. Breaker Blocks

**Type**: Structure detector
**Depends on**: `order_block` + `market_structure`
**Registry name**: `breaker_block`

A Breaker Block is a failed Order Block. When price breaks through an OB (invalidating it) during a CHoCH, the OB flips polarity: a failed bullish OB becomes bearish resistance, and vice versa. Breaker Blocks are among the strongest levels because they represent a trapped institutional position.

**Deferred**: Build after OB is proven. Implementation inherits OB slot management and adds polarity flip on CHoCH events.

---

### 9. Session Highs/Lows

**Type**: Indicator (multi-output)
**Depends on**: None (time-based)
**Registry name**: `session_levels`

Tracks previous daily/weekly/monthly highs and lows as reference levels. Implementation follows the same boundary-detection pattern as VWAP session resets. Straightforward but needs `ts_open` from bar data.

**Output Fields**: `prev_day_high`, `prev_day_low`, `prev_week_high`, `prev_week_low`, `prev_month_high`, `prev_month_low`, `current_day_high`, `current_day_low`.

---

### 10. Mitigation Tracking

**Type**: Enhancement to FVG and OB detectors
**Depends on**: `fair_value_gap`, `order_block`

Adds lifecycle tracking to FVGs and OBs: formation -> first touch -> partial fill -> full mitigation -> invalidation. Tracks fill percentage and touch count. Already partially designed into FVG and OB specs above (`fill_pct`, `mitigated` state).

**Deferred**: Enhance after FVG and OB are proven in backtests.

---

## Implementation Checklist Per Feature (Reference)

For each structure detector (all 6 ICT detectors have been implemented following this checklist):

1. [ ] Create `src/structures/detectors/<name>.py`
   - Inherit `BaseIncrementalDetector`
   - Decorate with `@register_structure("<name>")`
   - Define `REQUIRED_PARAMS`, `OPTIONAL_PARAMS`, `DEPENDS_ON`
   - Implement `__init__`, `update`, `get_output_keys`, `get_value`
2. [ ] Export from `src/structures/detectors/__init__.py`
3. [ ] Add output types to `STRUCTURE_OUTPUT_TYPES` in `registry.py`
4. [ ] Add warmup formula to `STRUCTURE_WARMUP_FORMULAS` in `registry.py`
5. [ ] Create validation play in `plays/validation/structures/`
6. [ ] Run `python trade_cli.py validate module --module coverage` — no gaps
7. [ ] Run `python trade_cli.py backtest run --play <val_play> --synthetic` — passes
8. [ ] Run `python trade_cli.py validate quick` — all gates green

For each new indicator:

1. [ ] Create class in `src/indicators/incremental/<module>.py`
   - Inherit `IncrementalIndicator`
   - Implement `update`, `reset`, `value` property, `is_ready` property
2. [ ] Export from `src/indicators/incremental/__init__.py`
3. [ ] Add warmup formula to `indicator_registry.py`
4. [ ] Add to `SUPPORTED_INDICATORS` dict
5. [ ] Add to `INDICATOR_OUTPUT_TYPES` dict
6. [ ] Add factory lambda to `factory.py`
7. [ ] Create validation play in `plays/validation/indicators/`
8. [ ] Run coverage check + validation

---

## Synthetic Data Patterns Needed

| Feature | Pattern Name | Description |
|---------|-------------|-------------|
| Displacement | `displacement_impulse` | Strong impulsive candles with clear body/wick ratios |
| FVG | `trending_with_gaps` | Trending market that creates clear 3-candle gaps |
| Order Block | `ob_retest` | Displacement from opposing candle, then retracement to OB zone |
| Liquidity Zones | `equal_highs_lows` | Multiple swing highs/lows at similar levels, then sweep |
| Volume Profile | `volume_concentration` | Volume clustered at specific price levels |

All 4 ICT patterns have been added to `src/forge/validation/synthetic_data.py` (38 patterns total).

---

## How These Feed M6 (Market Intelligence)

When running on the Shadow Exchange (M4), these features generate data that M6 uses to learn:

| Feature | M6 Signal | What M6 Learns |
|---------|-----------|----------------|
| Displacement | Institutional activity detection | "BTC shows 3x more displacements in trending vs ranging" |
| FVG | Imbalance tracking | "FVGs fill 80% in ranging, 40% in trending" |
| Order Block | Institutional positioning | "OBs at daily level hold 2x longer than 1h OBs" |
| Liquidity Zones | Stop-loss pool mapping | "Liquidity sweeps precede reversals 65% of the time" |
| Volume Profile | Volume distribution | "POC acts as support in uptrends, resistance in downtrends" |
| Premium/Discount | Value assessment | "Entries in discount zone have 30% better R:R" |

This is the raw data M6 needs to build play-selection intelligence.
