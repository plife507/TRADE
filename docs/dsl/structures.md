# Structures

13 types. All incremental O(1) per bar. Declared under `structures:` grouped by TF role.

## Declaration syntax

```yaml
structures:
  exec:                            # TF role: exec, low_tf, med_tf, high_tf
    - type: swing                  # Structure type
      key: swing                   # Unique key (used in conditions + deps)
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing                  # Dependency — must be declared ABOVE
    - type: fibonacci
      key: fib
      uses: [swing, trend]         # Multiple deps as list

  high_tf:                         # Higher TF structures
    - type: swing
      key: swing_D
      params: { left: 3, right: 3 }
```

**Rules:** deps declared before dependents (top-to-bottom). Same-TF deps only.

**Access in conditions:** `"swing.high_level"`, `"fib.level[0.618]"`, `"zones.zone[0].state"`

## Warmup formulas

| Structure | Formula | left=5,right=5 |
|-----------|---------|-----------------|
| swing | left + right | 10 |
| trend | (left+right) * 5 | 50 |
| market_structure | (left+right) * 3 | 30 |
| fibonacci / zone | left + right | 10 |
| derived_zone | left + right + 1 | 11 |
| rolling_window | size | size |
| displacement | 1 | 1 |
| fair_value_gap | 3 | 3 |
| order_block | max(lookback+2, left+right) | varies |
| liquidity_zones | (left+right) * min_touches | varies |
| premium_discount | left + right | 10 |
| breaker_block | (left+right) * 4 | 40 |

---

## INDEPENDENT structures (no deps)

### swing

Pivot high/low detection with delayed confirmation.

```yaml
- type: swing
  key: swing
  params:
    left: 5                        # REQUIRED — bars left of pivot
    right: 5                       # REQUIRED — bars right of pivot
    atr_key: atr_14                # Optional — for significance scoring
    major_threshold: 1.5           # Optional — ATR multiple for "major"
    min_atr_move: 1.0              # Optional — filter small pivots
    min_pct_move: 1.5              # Optional — filter < N% moves
    strict_alternation: false      # Optional — enforce H-L-H-L
```

| Output | Type | Description |
|--------|------|-------------|
| `high_level` | FLOAT | Most recent swing high price |
| `low_level` | FLOAT | Most recent swing low price |
| `high_idx` | INT | Bar index of swing high |
| `low_idx` | INT | Bar index of swing low |
| `version` | INT | Increments on any confirmed pivot |
| `high_version` | INT | Increments only on confirmed high |
| `low_version` | INT | Increments only on confirmed low |
| `high_significance` | FLOAT | ATR multiple (requires atr_key) |
| `low_significance` | FLOAT | ATR multiple (requires atr_key) |
| `high_is_major` | BOOL | significance >= threshold |
| `low_is_major` | BOOL | significance >= threshold |
| `high_accepted` | BOOL | New high confirmed THIS bar |
| `low_accepted` | BOOL | New low confirmed THIS bar |
| `pair_high_level` | FLOAT | Paired swing high |
| `pair_low_level` | FLOAT | Paired swing low |
| `pair_direction` | ENUM | `"bullish"` / `"bearish"` |
| `pair_version` | INT | Increments on complete pair |
| `last_confirmed_pivot_type` | ENUM | `"high"` / `"low"` |

### rolling_window

O(1) sliding min/max via MonotonicDeque.

```yaml
- type: rolling_window
  key: low_20
  params:
    size: 20                       # REQUIRED — window size in bars
    source: low                    # REQUIRED — open|high|low|close|volume
    mode: min                      # REQUIRED — min | max
```

| Output | Type |
|--------|------|
| `value` | FLOAT |

### displacement

Strong impulsive candle detection (large body, small wicks).

```yaml
- type: displacement
  key: disp
  params:
    atr_key: atr_14                # REQUIRED — ATR indicator key
    body_atr_min: 1.5              # Optional — min body/ATR ratio (default 1.5)
    wick_ratio_max: 0.4            # Optional — max wick/body ratio (default 0.4)
```

| Output | Type | Description |
|--------|------|-------------|
| `is_displacement` | BOOL | Current bar is displacement |
| `direction` | INT | 1 bull, -1 bear, 0 none |
| `body_atr_ratio` | FLOAT | Body size / ATR |
| `wick_ratio` | FLOAT | Wicks / body |
| `last_idx` | INT | Bar index of most recent |
| `last_direction` | INT | Direction of most recent |
| `version` | INT | Increments on each |

### fair_value_gap

3-candle imbalance zones with mitigation tracking.

```yaml
- type: fair_value_gap
  key: fvg
  params:
    atr_key: atr_14                # Optional (default "atr")
    min_gap_atr: 0.5               # Optional — min gap as ATR multiple (default 0.0)
    max_active: 5                  # Optional — max tracked slots (default 5)
```

| Output | Type | Description |
|--------|------|-------------|
| `new_this_bar` | BOOL | New FVG detected |
| `new_direction` | INT | 1 bull, -1 bear, 0 none |
| `new_upper` | FLOAT | Upper of newest FVG |
| `new_lower` | FLOAT | Lower of newest FVG |
| `nearest_bull_upper` | FLOAT | Upper of nearest active bull FVG |
| `nearest_bull_lower` | FLOAT | Lower of nearest active bull FVG |
| `nearest_bear_upper` | FLOAT | Upper of nearest active bear FVG |
| `nearest_bear_lower` | FLOAT | Lower of nearest active bear FVG |
| `active_bull_count` | INT | Active bullish FVGs |
| `active_bear_count` | INT | Active bearish FVGs |
| `any_mitigated_this_bar` | BOOL | Any FVG mitigated |
| `nearest_bull_fill_pct` | FLOAT | Fill % of nearest bull (0.0-1.0) |
| `nearest_bear_fill_pct` | FLOAT | Fill % of nearest bear (0.0-1.0) |
| `version` | INT | Increments on new FVG |

---

## DEPENDENT structures (require deps)

### trend (uses: swing)

Wave-based trend classification from swing sequence (HH/HL vs LL/LH).

```yaml
- type: trend
  key: trend
  uses: swing
```

| Output | Type | Description |
|--------|------|-------------|
| `direction` | INT | 1 up, -1 down, 0 ranging |
| `strength` | INT | 0 weak, 1 normal, 2 strong |
| `bars_in_trend` | INT | Bars since trend started |
| `wave_count` | INT | Consecutive same-direction waves |
| `last_wave_direction` | ENUM | `"bullish"` / `"bearish"` / `"none"` |
| `last_hh` | BOOL | Last high was higher high |
| `last_hl` | BOOL | Last low was higher low |
| `last_lh` | BOOL | Last high was lower high |
| `last_ll` | BOOL | Last low was lower low |
| `version` | INT | Increments on direction change |

### market_structure (uses: swing)

ICT-style BOS (continuation) and CHoCH (reversal) detection.

```yaml
- type: market_structure
  key: ms
  uses: swing
  params:
    confirmation_close: true       # Optional — require close beyond level (default true)
```

| Output | Type | Description |
|--------|------|-------------|
| `bias` | INT | 1 bull, -1 bear, 0 ranging |
| `bos_this_bar` | BOOL | BOS occurred THIS bar (resets each bar) |
| `choch_this_bar` | BOOL | CHoCH occurred THIS bar (resets each bar) |
| `bos_direction` | ENUM | `"bullish"` / `"bearish"` / `"none"` |
| `choch_direction` | ENUM | `"bullish"` / `"bearish"` / `"none"` |
| `last_bos_idx` | INT | Bar index of last BOS |
| `last_bos_level` | FLOAT | Price of last BOS break |
| `last_choch_idx` | INT | Bar index of last CHoCH |
| `last_choch_level` | FLOAT | Price of last CHoCH break |
| `break_level_high` | FLOAT | Level to watch for bull break |
| `break_level_low` | FLOAT | Level to watch for bear break |
| `version` | INT | Increments on structure event |

### fibonacci (uses: swing, optionally trend)

Retracement/extension levels from swing anchors.

```yaml
- type: fibonacci
  key: fib
  uses: swing                      # Or [swing, trend] for trend-wave
  params:
    levels: [0.382, 0.5, 0.618]   # REQUIRED — ratios
    mode: retracement              # REQUIRED — retracement|extension|extension_up|extension_down
    use_paired_anchor: true        # Optional (default true)
    use_trend_anchor: false        # Optional — requires uses: [swing, trend]
```

**Formula:** `level = anchor_high - (ratio * range)`

| Output | Type | Description |
|--------|------|-------------|
| `level[0.382]` | FLOAT | Level at ratio (bracket syntax) |
| `level[0.5]` | FLOAT | Level at ratio |
| `level[0.618]` | FLOAT | Level at ratio |
| `anchor_high` | FLOAT | Swing high (0% reference) |
| `anchor_low` | FLOAT | Swing low (100% reference) |
| `range` | FLOAT | High - low |
| `anchor_direction` | ENUM | `"bullish"` / `"bearish"` / `""` |
| `anchor_hash` | ENUM | Unique hash for anchor pair |

**Note:** `use_trend_anchor: true` requires `use_paired_anchor: false` (mutually exclusive).

### zone (uses: swing)

Single demand/supply zone from swing pivots.

```yaml
- type: zone
  key: demand
  uses: swing
  params:
    zone_type: demand              # REQUIRED — demand | supply
    width_atr: 1.5                 # REQUIRED — ATR multiplier for width
    atr_key: atr_14                # Optional (default "atr")
```

| Output | Type | Description |
|--------|------|-------------|
| `state` | ENUM | `"none"` / `"active"` / `"broken"` |
| `upper` | FLOAT | Upper boundary |
| `lower` | FLOAT | Lower boundary |
| `anchor_idx` | INT | Creation bar index |
| `version` | INT | Increments on state change |

### derived_zone (uses: swing)

Multiple zones from fib ratios with K-slot tracking + aggregates.

```yaml
- type: derived_zone
  key: fib_zones
  uses: swing
  params:
    levels: [0.382, 0.5, 0.618]   # REQUIRED
    mode: retracement              # REQUIRED — retracement | extension
    max_active: 5                  # REQUIRED — number of zone slots
    width_pct: 0.002               # REQUIRED — zone width as fraction of level
    use_paired_source: true        # Optional
    break_tolerance_pct: 0.0       # Optional
```

**Per-slot outputs** (N = 0 to max_active-1):

| Output | Type | Description |
|--------|------|-------------|
| `zone[N].state` | ENUM | `"none"` / `"active"` / `"broken"` |
| `zone[N].upper` | FLOAT | Upper boundary |
| `zone[N].lower` | FLOAT | Lower boundary |
| `zone[N].touched_this_bar` | BOOL | Price touched zone THIS bar |
| `zone[N].inside` | BOOL | Price inside zone |
| `zone[N].touch_count` | INT | Cumulative touches |
| `zone[N].age_bars` | INT | Bars since creation |

**Aggregate outputs:**

| Output | Type | Description |
|--------|------|-------------|
| `active_count` | INT | Number of active zones |
| `any_active` | BOOL | Any zone active |
| `any_touched` | BOOL | Any active zone touched THIS bar |
| `any_inside` | BOOL | Price inside any active zone |
| `first_active_lower` | FLOAT | Lower of first active zone |
| `first_active_upper` | FLOAT | Upper of first active zone |

### order_block (uses: swing)

Last opposing candle before displacement — tracked for mitigation/invalidation.

```yaml
- type: order_block
  key: ob
  uses: swing
  params:
    atr_key: atr_14                # REQUIRED
    use_body: true                 # Optional — body or full range (default true)
    require_displacement: true     # Optional (default true)
    body_atr_min: 1.5              # Optional — displacement threshold
    wick_ratio_max: 0.4            # Optional
    max_active: 5                  # Optional
    lookback: 3                    # Optional — bars back to search
```

| Output | Type | Description |
|--------|------|-------------|
| `new_this_bar` | BOOL | New OB detected |
| `new_direction` | INT | 1 bull, -1 bear, 0 none |
| `new_upper` | FLOAT | Upper of newest OB |
| `new_lower` | FLOAT | Lower of newest OB |
| `nearest_bull_upper` | FLOAT | Upper of nearest bull OB |
| `nearest_bull_lower` | FLOAT | Lower of nearest bull OB |
| `nearest_bear_upper` | FLOAT | Upper of nearest bear OB |
| `nearest_bear_lower` | FLOAT | Lower of nearest bear OB |
| `active_bull_count` | INT | Active bullish OBs |
| `active_bear_count` | INT | Active bearish OBs |
| `any_mitigated_this_bar` | BOOL | Any OB mitigated |
| `any_invalidated_this_bar` | BOOL | Any OB invalidated |
| `version` | INT | Increments on new OB |

### liquidity_zones (uses: swing)

Cluster nearby swing highs/lows into pools, detect sweeps.

```yaml
- type: liquidity_zones
  key: liq
  uses: swing
  params:
    atr_key: atr_14                # Optional (default "atr")
    tolerance_atr: 0.3             # Optional — cluster tolerance
    sweep_atr: 0.1                 # Optional — sweep penetration
    min_touches: 2                 # Optional — min swings to form zone
    max_active: 5                  # Optional
    max_swing_history: 20          # Optional
```

| Output | Type | Description |
|--------|------|-------------|
| `sweep_this_bar` | BOOL | Zone swept THIS bar |
| `sweep_direction` | INT | 1 swept highs (bearish), -1 swept lows (bullish), 0 none |
| `swept_level` | FLOAT | Price level of swept zone |
| `nearest_high_level` | FLOAT | Nearest active high zone |
| `nearest_low_level` | FLOAT | Nearest active low zone |
| `nearest_high_touches` | INT | Touch count of nearest high |
| `nearest_low_touches` | INT | Touch count of nearest low |
| `new_zone_this_bar` | BOOL | New zone created |
| `version` | INT | Increments on new zone or sweep |

### premium_discount (uses: swing)

ICT premium/discount zone classification from swing pair.

```yaml
- type: premium_discount
  key: pd
  uses: swing
  # No params — derived from swing pair
```

| Output | Type | Description |
|--------|------|-------------|
| `zone` | ENUM | `"premium"` / `"discount"` / `"equilibrium"` / `"none"` |
| `equilibrium` | FLOAT | Midpoint of range |
| `premium_level` | FLOAT | 75th percentile |
| `discount_level` | FLOAT | 25th percentile |
| `depth_pct` | FLOAT | 0.0 (at low) to 1.0 (at high) |
| `version` | INT | Increments on zone change |

### breaker_block (uses: order_block)

Failed OBs flipped on CHoCH — polarity reversal zones.

```yaml
- type: breaker_block
  key: brk
  uses: ob                         # Reference to order_block key
  params:
    max_active: 5                  # Optional
    ms_key: ms                     # Optional — market_structure key
```

| Output | Type | Description |
|--------|------|-------------|
| `new_this_bar` | BOOL | New breaker detected |
| `new_direction` | INT | 1 bull support, -1 bear resistance, 0 none |
| `new_upper` | FLOAT | Upper of newest breaker |
| `new_lower` | FLOAT | Lower of newest breaker |
| `nearest_bull_upper` | FLOAT | Upper of nearest bull breaker |
| `nearest_bull_lower` | FLOAT | Lower of nearest bull breaker |
| `nearest_bear_upper` | FLOAT | Upper of nearest bear breaker |
| `nearest_bear_lower` | FLOAT | Lower of nearest bear breaker |
| `active_bull_count` | INT | Active bullish breakers |
| `active_bear_count` | INT | Active bearish breakers |
| `any_mitigated_this_bar` | BOOL | Any breaker mitigated |
| `version` | INT | Increments on new breaker |

---

## Dependency graph

```
swing ─┬─ trend
       ├─ market_structure
       ├─ fibonacci (+ optional trend)
       ├─ zone
       ├─ derived_zone
       ├─ order_block ── breaker_block (+ optional market_structure)
       ├─ liquidity_zones
       └─ premium_discount

rolling_window (independent)
displacement (independent)
fair_value_gap (independent)
```

## Operator compatibility by output type

| Type | Allowed operators |
|------|------------------|
| FLOAT | `>`, `<`, `>=`, `<=`, `between`, `near_pct`, `near_abs`, `cross_above`, `cross_below` |
| INT | `==`, `!=`, `in`, `>`, `<`, `>=`, `<=`, `between` |
| BOOL | `==`, `!=` |
| ENUM | `==`, `!=`, `in` |

**FLOAT cannot use `==`** — use `near_pct` or `near_abs` instead.
