# ICT/SMC Market Structure Implementation

Goal: Implement ICT (Inner Circle Trader) and SMC (Smart Money Concepts) market structure types as incremental detectors.

**Status**: PLANNING
**Created**: 2026-01-05

---

## Background

ICT/SMC trading concepts are widely used by institutional and retail traders. The current structure registry (6 types) covers basic market structure but lacks:

1. **Order Blocks (OB)** - Last opposing candle before impulsive move
2. **Fair Value Gaps (FVG)** - 3-candle imbalance pattern
3. **Liquidity Zones (BSL/SSL)** - Equal highs/lows where stops accumulate
4. **Break of Structure (BOS)** - Continuation pattern
5. **Change of Character (CHoCH)** - Reversal pattern

These concepts map to the existing structure system but require new detectors.

---

## Current State

### Existing Structure Registry (6 types)

| Type | Description | ICT Equivalent |
|------|-------------|----------------|
| `swing` | Swing high/low detection | ✅ Direct match |
| `trend` | Trend direction | ⚠️ Partial BOS/CHoCH |
| `zone` | Demand/supply zones | ⚠️ Missing OB semantics |
| `fibonacci` | Fib retracements/extensions | ✅ OTE zone (0.618-0.786) |
| `rolling_window` | Rolling min/max | N/A |
| `derived_zone` | Multi-zone from pivots | ⚠️ Could model OBs |

### Gap Analysis

| ICT Concept | Can Build With Current | Needs |
|-------------|------------------------|-------|
| Order Blocks | No | Candle body anchoring, impulse detection |
| Fair Value Gaps | No | 3-candle pattern detection |
| Liquidity Zones | Partial (swing) | Equal highs/lows grouping |
| BOS/CHoCH | Partial (trend) | Explicit break events |
| Premium/Discount | Yes (fibonacci) | OTE zone already possible |

---

## Implementation Plan

### Phase 1: Zone Detector Enhancements

Enhance existing `zone` detector to match `derived_zone` capabilities.

**Files to modify:**
- `src/backtest/incremental/detectors/zone.py`
- `src/backtest/incremental/registry.py`

**New output fields for `zone`:**
- [ ] `age_bars` (INT) - Bars since zone formation
- [ ] `touch_count` (INT) - Times price entered zone
- [ ] `inside` (BOOL) - Price currently in zone
- [ ] `touched_this_bar` (BOOL) - Price entered zone this bar
- [ ] `just_activated` (BOOL) - Zone just formed this bar
- [ ] `just_broken` (BOOL) - Zone just broke this bar

**Acceptance criteria:**
- [ ] Zone detector outputs match derived_zone slot fields
- [ ] Validation Play `V_050_zone_enhanced.yml` passes

---

### Phase 2: Market Structure Detector (BOS/CHoCH)

New detector for Break of Structure and Change of Character.

**Files to create:**
- `src/backtest/incremental/detectors/market_structure.py`

**Detector specification:**

```python
@register_structure("market_structure")
class MarketStructureDetector(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "swing_source": "swing",  # Which swing detector to use
    }
    DEPENDS_ON = ["swing"]
```

**Output fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bias` | ENUM | "bullish", "bearish", "ranging" |
| `last_bos_idx` | INT | Bar index of last BOS |
| `last_choch_idx` | INT | Bar index of last CHoCH |
| `bos_this_bar` | BOOL | BOS occurred this bar |
| `choch_this_bar` | BOOL | CHoCH occurred this bar |
| `last_hh` | FLOAT | Last higher high price |
| `last_hl` | FLOAT | Last higher low price |
| `last_lh` | FLOAT | Last lower high price |
| `last_ll` | FLOAT | Last lower low price |
| `swing_sequence` | INT | Encoded swing sequence (HH-HL-HH vs LH-LL-LH) |
| `version` | INT | Monotonic counter, increments on bias change |

**Detection logic:**

```
BULLISH structure: HH → HL → HH → HL (higher highs, higher lows)
BEARISH structure: LH → LL → LH → LL (lower highs, lower lows)

BOS (continuation):
  - Bullish BOS: Price breaks above prior swing high (continue uptrend)
  - Bearish BOS: Price breaks below prior swing low (continue downtrend)

CHoCH (reversal):
  - Bullish CHoCH: Price makes higher low after bearish structure
  - Bearish CHoCH: Price makes lower high after bullish structure
```

**Tasks:**
- [ ] Create `market_structure.py` detector
- [ ] Implement swing sequence tracking (last 4 pivots)
- [ ] Implement BOS detection (break continuation)
- [ ] Implement CHoCH detection (reversal)
- [ ] Add to `STRUCTURE_OUTPUT_TYPES` in registry
- [ ] Add warmup formula to `STRUCTURE_WARMUP_FORMULAS`
- [ ] Create validation Play `V_051_market_structure.yml`
- [ ] Create validation Play `V_052_bos_entry.yml`
- [ ] Create validation Play `V_053_choch_reversal.yml`

**Acceptance criteria:**
- [ ] All validation Plays normalize
- [ ] Backtest runs produce expected BOS/CHoCH events
- [ ] Detector is O(1) per bar (no lookback loops)

---

### Phase 3: Order Block Detector

New detector for ICT Order Blocks.

**Files to create:**
- `src/backtest/incremental/detectors/order_block.py`

**Detector specification:**

```python
@register_structure("order_block")
class OrderBlockDetector(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "lookback": 20,           # Bars to search for impulse
        "impulse_atr_mult": 1.5,  # Min impulse size in ATR
        "block_type": "bullish",  # "bullish" or "bearish"
        "use_body": True,         # Use candle body (not wicks)
    }
    DEPENDS_ON = ["swing"]
```

**Output fields:**

| Field | Type | Description |
|-------|------|-------------|
| `state` | ENUM | "none", "active", "mitigated" |
| `high` | FLOAT | Block upper boundary |
| `low` | FLOAT | Block lower boundary |
| `anchor_idx` | INT | Bar when OB formed |
| `age_bars` | INT | Bars since formation |
| `touched` | BOOL | Price entered but didn't close through |
| `touch_count` | INT | Times price entered block |
| `mitigated_this_bar` | BOOL | Just got mitigated |
| `breaker` | BOOL | OB became breaker block (broken then retested) |
| `version` | INT | Monotonic counter |

**Detection logic:**

```
Bullish Order Block:
1. Find swing low (confirmed by depends_on swing)
2. Trace back to find last RED candle before the bullish impulse
3. OB = that candle's body (open to close range)
4. Mitigated when price closes through the block

Bearish Order Block:
1. Find swing high (confirmed by depends_on swing)
2. Trace back to find last GREEN candle before the bearish impulse
3. OB = that candle's body (open to close range)
4. Mitigated when price closes through the block
```

**Tasks:**
- [ ] Create `order_block.py` detector
- [ ] Implement bullish OB detection (last red before bullish impulse)
- [ ] Implement bearish OB detection (last green before bearish impulse)
- [ ] Implement mitigation detection (price closes through)
- [ ] Implement breaker block logic (broken OB becomes resistance/support)
- [ ] Add to `STRUCTURE_OUTPUT_TYPES` in registry
- [ ] Add warmup formula to `STRUCTURE_WARMUP_FORMULAS`
- [ ] Create validation Play `V_054_order_block_bullish.yml`
- [ ] Create validation Play `V_055_order_block_bearish.yml`
- [ ] Create validation Play `V_056_breaker_block.yml`

**Acceptance criteria:**
- [ ] All validation Plays normalize
- [ ] OBs anchor to candle bodies, not wicks
- [ ] Mitigation detected correctly
- [ ] Detector is O(1) per bar

---

### Phase 4: Fair Value Gap Detector

New detector for ICT Fair Value Gaps (Imbalances).

**Files to create:**
- `src/backtest/incremental/detectors/fair_value_gap.py`

**Detector specification:**

```python
@register_structure("fair_value_gap")
class FairValueGapDetector(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "min_gap_atr": 0.3,       # Minimum gap size in ATR
        "gap_type": "bullish",    # "bullish" or "bearish"
        "max_active": 3,          # Max concurrent FVGs to track
    }
    DEPENDS_ON = []  # Standalone - no swing dependency
```

**Output fields (K slots + aggregates, like derived_zone):**

**Slot fields (per FVG, 0 to K-1):**

| Field | Type | Description |
|-------|------|-------------|
| `fvg{N}_state` | ENUM | "none", "active", "filled" |
| `fvg{N}_high` | FLOAT | Gap upper boundary |
| `fvg{N}_low` | FLOAT | Gap lower boundary |
| `fvg{N}_ce` | FLOAT | Consequent Encroachment (50% level) |
| `fvg{N}_anchor_idx` | INT | Bar when FVG formed |
| `fvg{N}_age_bars` | INT | Bars since formation |
| `fvg{N}_filled_pct` | FLOAT | Percentage filled (0-100) |
| `fvg{N}_touched_this_bar` | BOOL | Price entered gap this bar |

**Aggregate fields:**

| Field | Type | Description |
|-------|------|-------------|
| `active_count` | INT | Number of active FVGs |
| `any_active` | BOOL | At least one active FVG |
| `any_touched` | BOOL | Price entered any FVG this bar |
| `closest_active_high` | FLOAT | Nearest active FVG upper |
| `closest_active_low` | FLOAT | Nearest active FVG lower |
| `newest_active_idx` | INT | Slot index of most recent FVG |

**Detection logic:**

```
Bullish FVG (gap up):
  bar[0].low > bar[2].high
  Gap = bar[2].high to bar[0].low

Bearish FVG (gap down):
  bar[0].high < bar[2].low
  Gap = bar[0].high to bar[2].low

Filled when:
  Price closes through 50%+ of gap (CE level)
```

**Tasks:**
- [ ] Create `fair_value_gap.py` detector
- [ ] Implement 3-candle pattern detection
- [ ] Implement K-slot management (like derived_zone)
- [ ] Implement CE (50% fill) logic
- [ ] Implement partial fill tracking
- [ ] Add to `STRUCTURE_OUTPUT_TYPES` in registry
- [ ] Add warmup formula (needs 3 bars minimum)
- [ ] Create validation Play `V_057_fvg_bullish.yml`
- [ ] Create validation Play `V_058_fvg_bearish.yml`
- [ ] Create validation Play `V_059_fvg_ce_entry.yml`

**Acceptance criteria:**
- [ ] All validation Plays normalize
- [ ] FVG detected on bar[0] using bar[-2], bar[-1], bar[0]
- [ ] K-slot rotation works (oldest filled slot reused)
- [ ] Detector is O(1) per bar

---

### Phase 5: Liquidity Zone Detector

New detector for ICT Liquidity Zones (equal highs/lows).

**Files to create:**
- `src/backtest/incremental/detectors/liquidity_zone.py`

**Detector specification:**

```python
@register_structure("liquidity_zone")
class LiquidityZoneDetector(BaseIncrementalDetector):
    REQUIRED_PARAMS = []
    OPTIONAL_PARAMS = {
        "tolerance_pct": 0.1,     # Max % difference for "equal"
        "min_touches": 2,         # Minimum equal points
        "zone_type": "bsl",       # "bsl" (buyside) or "ssl" (sellside)
        "max_active": 3,          # Max concurrent zones
    }
    DEPENDS_ON = ["swing"]
```

**Output fields (K slots + aggregates):**

**Slot fields:**

| Field | Type | Description |
|-------|------|-------------|
| `liq{N}_state` | ENUM | "none", "active", "swept" |
| `liq{N}_level` | FLOAT | The liquidity level |
| `liq{N}_touches` | INT | Number of times price touched |
| `liq{N}_anchor_idx` | INT | First touch bar |
| `liq{N}_age_bars` | INT | Bars since first touch |
| `liq{N}_swept_this_bar` | BOOL | Just got swept |

**Aggregate fields:**

| Field | Type | Description |
|-------|------|-------------|
| `active_count` | INT | Number of active liquidity zones |
| `any_active` | BOOL | At least one active zone |
| `any_swept` | BOOL | Any zone swept this bar |
| `closest_active_level` | FLOAT | Nearest active level |

**Detection logic:**

```
Buyside Liquidity (BSL):
  Multiple swing highs at same level (within tolerance)
  Swept when price trades through the level

Sellside Liquidity (SSL):
  Multiple swing lows at same level (within tolerance)
  Swept when price trades through the level
```

**Tasks:**
- [ ] Create `liquidity_zone.py` detector
- [ ] Implement equal highs detection (BSL)
- [ ] Implement equal lows detection (SSL)
- [ ] Implement sweep detection
- [ ] Add K-slot management
- [ ] Add to `STRUCTURE_OUTPUT_TYPES` in registry
- [ ] Add warmup formula
- [ ] Create validation Play `V_060_liquidity_bsl.yml`
- [ ] Create validation Play `V_061_liquidity_ssl.yml`
- [ ] Create validation Play `V_062_liquidity_sweep.yml`

**Acceptance criteria:**
- [ ] All validation Plays normalize
- [ ] Equal highs/lows grouped correctly
- [ ] Sweep detected on wick or close through level
- [ ] Detector is O(1) per bar

---

### Phase 6: Integration Plays

Create comprehensive Plays combining ICT structures.

**Validation Plays:**
- [ ] `V_063_ict_ob_fvg_combo.yml` - OB + FVG confluence entry
- [ ] `V_064_ict_bos_ob.yml` - BOS then OB retest entry
- [ ] `V_065_ict_choch_fvg.yml` - CHoCH with FVG fill entry
- [ ] `V_066_ict_liquidity_sweep.yml` - Liquidity sweep reversal
- [ ] `V_067_ict_premium_discount.yml` - Premium/discount with OTE

**Stress Test Plays:**
- [ ] `T_010_ict_full_model.yml` - All ICT structures combined

**Acceptance criteria:**
- [ ] All Plays normalize
- [ ] All Plays backtest without errors
- [ ] Trades generated match ICT entry logic

---

## Validation Plays Summary

| Play | Purpose | Phase |
|------|---------|-------|
| V_050_zone_enhanced.yml | Zone with time fields | 1 |
| V_051_market_structure.yml | BOS/CHoCH detection | 2 |
| V_052_bos_entry.yml | BOS continuation entry | 2 |
| V_053_choch_reversal.yml | CHoCH reversal entry | 2 |
| V_054_order_block_bullish.yml | Bullish OB entry | 3 |
| V_055_order_block_bearish.yml | Bearish OB entry | 3 |
| V_056_breaker_block.yml | Breaker block flip | 3 |
| V_057_fvg_bullish.yml | Bullish FVG detection | 4 |
| V_058_fvg_bearish.yml | Bearish FVG detection | 4 |
| V_059_fvg_ce_entry.yml | FVG CE level entry | 4 |
| V_060_liquidity_bsl.yml | Buyside liquidity | 5 |
| V_061_liquidity_ssl.yml | Sellside liquidity | 5 |
| V_062_liquidity_sweep.yml | Liquidity sweep | 5 |
| V_063_ict_ob_fvg_combo.yml | OB + FVG combo | 6 |
| V_064_ict_bos_ob.yml | BOS + OB combo | 6 |
| V_065_ict_choch_fvg.yml | CHoCH + FVG combo | 6 |
| V_066_ict_liquidity_sweep.yml | Sweep reversal | 6 |
| V_067_ict_premium_discount.yml | Premium/discount | 6 |

**Total**: 18 new validation Plays

---

## Registry Updates Summary

After all phases, `STRUCTURE_REGISTRY` will have:

| Type | Status |
|------|--------|
| `swing` | Existing |
| `trend` | Existing |
| `zone` | Enhanced (Phase 1) |
| `fibonacci` | Existing |
| `rolling_window` | Existing |
| `derived_zone` | Existing |
| `market_structure` | NEW (Phase 2) |
| `order_block` | NEW (Phase 3) |
| `fair_value_gap` | NEW (Phase 4) |
| `liquidity_zone` | NEW (Phase 5) |

**Total**: 10 structure types (6 existing + 4 new)

---

## Files to Create/Modify

### New Files

| File | Phase |
|------|-------|
| `src/backtest/incremental/detectors/market_structure.py` | 2 |
| `src/backtest/incremental/detectors/order_block.py` | 3 |
| `src/backtest/incremental/detectors/fair_value_gap.py` | 4 |
| `src/backtest/incremental/detectors/liquidity_zone.py` | 5 |
| `strategies/plays/_validation/V_050_zone_enhanced.yml` | 1 |
| `strategies/plays/_validation/V_051_market_structure.yml` | 2 |
| `strategies/plays/_validation/V_052_bos_entry.yml` | 2 |
| `strategies/plays/_validation/V_053_choch_reversal.yml` | 2 |
| `strategies/plays/_validation/V_054_order_block_bullish.yml` | 3 |
| `strategies/plays/_validation/V_055_order_block_bearish.yml` | 3 |
| `strategies/plays/_validation/V_056_breaker_block.yml` | 3 |
| `strategies/plays/_validation/V_057_fvg_bullish.yml` | 4 |
| `strategies/plays/_validation/V_058_fvg_bearish.yml` | 4 |
| `strategies/plays/_validation/V_059_fvg_ce_entry.yml` | 4 |
| `strategies/plays/_validation/V_060_liquidity_bsl.yml` | 5 |
| `strategies/plays/_validation/V_061_liquidity_ssl.yml` | 5 |
| `strategies/plays/_validation/V_062_liquidity_sweep.yml` | 5 |
| `strategies/plays/_validation/V_063_ict_ob_fvg_combo.yml` | 6 |
| `strategies/plays/_validation/V_064_ict_bos_ob.yml` | 6 |
| `strategies/plays/_validation/V_065_ict_choch_fvg.yml` | 6 |
| `strategies/plays/_validation/V_066_ict_liquidity_sweep.yml` | 6 |
| `strategies/plays/_validation/V_067_ict_premium_discount.yml` | 6 |
| `strategies/plays/_stress_test/T_010_ict_full_model.yml` | 6 |

### Modified Files

| File | Changes | Phase |
|------|---------|-------|
| `src/backtest/incremental/detectors/zone.py` | Add time fields | 1 |
| `src/backtest/incremental/registry.py` | Add output types for new structures | 2-5 |
| `src/backtest/incremental/__init__.py` | Import new detectors | 2-5 |

---

## Testing Strategy

After each phase:

1. **Normalize**: `python trade_cli.py backtest play-normalize-batch --dir strategies/plays/_validation`
2. **Smoke**: Run new validation Plays with synthetic data
3. **Backtest**: Run with real DuckDB data (BTCUSDT 1h, 30 days)
4. **Verify**: Check structure outputs match expected patterns

**Final validation:**
```bash
# All validation Plays
python trade_cli.py backtest play-normalize-batch --dir strategies/plays/_validation

# Structure audit
python trade_cli.py backtest structure-smoke

# ICT-specific stress test
python trade_cli.py backtest run --play T_010_ict_full_model --smoke
```

---

## Priority Order

| Phase | Complexity | Trading Value | Priority |
|-------|------------|---------------|----------|
| Phase 2: Market Structure | Medium | Very High | **P1** |
| Phase 3: Order Blocks | Medium | High | P2 |
| Phase 4: Fair Value Gaps | Low | High | P2 |
| Phase 1: Zone Enhancements | Low | Medium | P3 |
| Phase 5: Liquidity Zones | Medium | Medium | P3 |
| Phase 6: Integration | Low | High | P4 |

**Recommended execution order**: 2 → 3 → 4 → 1 → 5 → 6

---

## Not Implementing (Out of Scope)

| Concept | Reason |
|---------|--------|
| Inducement | Too pattern-specific, can be built from OB + liquidity |
| Mitigation blocks | Variant of OB, same detector handles it |
| Turtle soup | Can be expressed with liquidity_zone + time filter |
| Silver bullet | Time-of-day filter, not structure |
| Judas swing | Can be expressed with existing swing + time filter |
| SMT divergence | Requires multi-symbol correlation, future work |

---

## References

- ICT Mentorship: Order Blocks, FVG, BOS/CHoCH definitions
- TradingView LuxAlgo SMC indicator: Implementation reference
- Python smart-money-concepts library: Algorithm reference
- Existing detector: `src/backtest/incremental/detectors/derived_zone.py` (K-slot pattern)
