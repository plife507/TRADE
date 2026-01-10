# Open Interest & Funding Rate Strategy Integration

> Investigation: January 2026

## Executive Summary

The infrastructure for using open interest (OI) and funding rates in strategy conditions is **90% complete**. Data is synced, loaded, aligned, and accessible in snapshots. Only DSL wiring is missing.

**Recommendation**: Implement DSL integration (~30 lines of code) for a quick strategic win.

---

## Current State

| Data Source | Stored in DB | Loaded to Engine | In Snapshot | Used by Strategy |
|-------------|--------------|------------------|-------------|------------------|
| **Funding Rate** | 8h intervals | forward-filled | `snapshot.funding_rate` | Partial (PnL only) |
| **Open Interest** | configurable (5m-1d) | forward-filled | `snapshot.open_interest` | Not exposed to DSL |

---

## What's Already Working

### Funding Rates

Fully integrated for **position accounting**:

- Settlement times precomputed as `set[int]` for O(1) lookup
- Applied to positions at 00:00, 08:00, 16:00 UTC via `funding_model.py`
- Array access: `snapshot.funding_rate` returns current rate
- Forward-filled between settlements

**Key files**:
- `src/backtest/runtime/funding_scheduler.py` - settlement detection
- `src/backtest/sim/funding/funding_model.py` - PnL application
- `src/backtest/runtime/snapshot_view.py:1024-1035` - property accessor

### Open Interest

Loaded but **not yet usable in rules**:

- Array built and forward-filled to exec bar granularity
- Accessible via `snapshot.open_interest` property
- Configurable sync intervals: 5min, 15min, 30min, 1h, 4h, 1d

**Key files**:
- `src/data/historical_data_store.py:899-1149` - sync and storage
- `src/backtest/engine_feed_builder.py:488-527` - array alignment
- `src/backtest/runtime/snapshot_view.py:1037-1045` - property accessor

---

## What's Missing

The snapshot has accessors (`snapshot_view.py:677-695`), but the **DSL evaluator** doesn't recognize them as valid features for rule conditions.

```yaml
# This would NOT work today
blocks:
  - id: oi_filter
    when:
      all:
        - lhs: {feature_id: "open_interest"}  # Not in feature registry
          op: gte
          rhs: 500000000
```

### Gap Analysis

| Component | Status | Location |
|-----------|--------|----------|
| Data sync | Complete | `historical_data_store.py` |
| Data loading | Complete | `engine_data_prep.py:836-949` |
| Array alignment | Complete | `engine_feed_builder.py:395-529` |
| FeedStore wiring | Complete | `engine.py:770-782` |
| Snapshot accessor | Complete | `snapshot_view.py:677-695, 1024-1052` |
| DSL feature resolution | **Missing** | `dsl_evaluator.py` |
| Play validation | **Missing** | Feature registry recognition |

---

## Strategic Value Analysis

These signals don't generate entries alone — they **filter out bad entries** and **confirm good ones**. A trend system with OI/funding filters will have fewer trades but higher win rate.

---

## Funding Rate — Crowd Positioning Indicator

Funding is the cost longs pay shorts (or vice versa) every 8 hours. It's a **direct measure of market imbalance**.

### What Funding Tells You

| Funding Rate | Market State | Strategic Implication |
|--------------|--------------|----------------------|
| **High positive** (>0.05%) | Longs are crowded, paying shorts | Dangerous to go long — fade potential |
| **High negative** (<-0.05%) | Shorts are crowded, paying longs | Dangerous to short — squeeze potential |
| **Near zero** | Balanced positioning | Neutral — no crowd bias |
| **Extreme** (>0.1% or <-0.1%) | Euphoria/panic | Mean reversion setups |

### Funding Strategy Applications

**1. Contrarian Filter** — Avoid trading with the crowd at extremes

```
Your system: "Go long here"
Funding: +0.08% (very crowded long)
Action: SKIP — the crowd is already positioned, limited upside
```

**2. Mean Reversion Trigger** — Fade extremes

```
Funding hits -0.15% (extreme short crowding)
+ Price at support
= High probability long (shorts will cover)
```

**3. Trend Confirmation** — Healthy trends have moderate funding

```
Strong uptrend + funding near 0% = Sustainable (not crowded yet)
Strong uptrend + funding at 0.1% = Late stage (crowded, caution)
```

**Caveat**: 8-hour granularity limits tactical use. Best for filtering, not timing.

---

## Open Interest — Conviction Behind Price Moves

OI = total open contracts. Changes reveal **whether new money is entering** or **existing positions are closing**.

### What OI Tells You

| Price Move | OI Change | Meaning | Reliability |
|------------|-----------|---------|-------------|
| **Up** | **Up** | New longs entering | Strong — trend likely continues |
| **Up** | **Down** | Shorts covering (no new longs) | Weak — rally may fail |
| **Down** | **Up** | New shorts entering | Strong — downtrend likely continues |
| **Down** | **Down** | Longs exiting (no new shorts) | Weak — selloff may exhaust |

### OI Strategy Applications

**1. Trend Strength Filter** — Only trade confirmed moves

```
Breakout detected + OI surging = Real breakout (money committing)
Breakout detected + OI flat    = Fake breakout (no conviction)
```

**2. Exhaustion Detection** — Spot reversals early

```
Price makes new high
OI declining for 3 days
= Divergence → trend exhaustion likely
```

**3. Squeeze Detection** — Anticipate violent moves

```
OI at multi-week high (lots of open positions)
+ Price consolidating in tight range
= Powder keg — big move coming (squeeze one side)
```

**Caveat**: Requires rate-of-change calculation for divergence signals.

---

## Combined Patterns (The Real Power)

The strongest signals come from **combining both**:

| Pattern | Signals | Meaning |
|---------|---------|---------|
| **Squeeze Setup** | High OI + extreme funding + consolidation | Violent move coming, fade the crowded side |
| **Strong Trend** | Rising OI + moderate funding + trending price | Healthy trend, ride it |
| **Exhaustion** | Falling OI + extreme funding + new highs/lows | Late stage, prepare for reversal |
| **Capitulation** | Crashing OI + funding flip + volume spike | Washout complete, reversal imminent |

### Concrete Example

**BTC at $50k, your trend system says "long"**

| Check | Value | Interpretation |
|-------|-------|----------------|
| Funding | +0.03% | Moderate — acceptable |
| OI 24h change | +5% | New money entering — confirms conviction |
| **Verdict** | **Take the trade** | Both signals confirm |

**Same setup, different readings:**

| Check | Value | Interpretation |
|-------|-------|----------------|
| Funding | +0.12% | Extreme — longs crowded |
| OI 24h change | -3% | Money leaving — no conviction |
| **Verdict** | **Skip the trade** | Both signals warn against it |

---

## Quick Reference: When To Use Each Signal

| Signal | Primary Use | When Most Valuable |
|--------|-------------|-------------------|
| **Funding** | Avoid crowded trades | Extremes (>0.05% or <-0.05%) |
| **OI rising** | Confirm trend conviction | Breakouts, trend entries |
| **OI falling** | Spot exhaustion/reversals | Late-stage trends, divergences |
| **Combined** | High-conviction filters | Reduces false signals significantly |

---

## Performance Impact

**Zero concern** - both are O(1) array lookups.

| Operation | Complexity | Implementation |
|-----------|------------|----------------|
| Access current bar | O(1) | `feed.funding_rate[exec_idx]` |
| Access with offset | O(1) | `feed.open_interest[exec_idx - offset]` |
| Settlement detection | O(1) | `ts_ms in funding_settlement_times` |

All arrays are precomputed and aligned before the hot loop. No DataFrame operations or indicator recalculation during bar processing.

---

## Strategy Pattern Examples

### Funding-Based Filter (Avoid Crowded Trades)

```yaml
# Skip longs when funding is very positive (crowded long)
blocks:
  - id: funding_not_crowded
    when:
      any:
        - lhs: {feature_id: "funding_rate"}
          op: lt
          rhs: 0.0003  # < 0.03% = acceptable

  - id: entry_long
    when:
      all:
        - {ref: trend_up}
        - {ref: funding_not_crowded}  # Filter out crowded trades
```

### OI Confirmation (Trend Strength)

```yaml
# Only enter if OI is rising (confirms conviction)
features:
  - id: oi_sma_24
    indicator: sma
    params: {length: 24}
    source: open_interest  # Requires source wiring

blocks:
  - id: oi_rising
    when:
      - lhs: {feature_id: "open_interest"}
        op: gt
        rhs: {feature_id: "oi_sma_24"}
```

### Funding Extremes (Mean Reversion)

```yaml
# Fade extreme funding (crowd is wrong at extremes)
blocks:
  - id: extreme_short_funding
    when:
      - lhs: {feature_id: "funding_rate"}
        op: lt
        rhs: -0.001  # -0.1% = extreme bearish sentiment

  - id: contrarian_long
    when:
      all:
        - {ref: extreme_short_funding}
        - {ref: support_test}  # Technical confirmation
```

### OI Divergence (Exhaustion Warning)

```yaml
# Warn when price makes new high but OI is dropping
features:
  - id: oi_roc_24
    indicator: roc
    params: {length: 24}
    source: open_interest

blocks:
  - id: oi_divergence_bearish
    when:
      all:
        - lhs: {feature_id: "close"}
          op: gte
          rhs: {feature_id: "high", offset: 24}  # New 24-bar high
        - lhs: {feature_id: "oi_roc_24"}
          op: lt
          rhs: -5  # OI dropping >5%
```

---

## Implementation Plan

### Phase 1: DSL Feature Resolution (~20 lines)

Enable `funding_rate` and `open_interest` as valid feature IDs:

```python
# In dsl_evaluator.py or feature resolution logic
MARKET_DATA_FEATURES = {"funding_rate", "open_interest"}

def resolve_feature(feature_id: str, snapshot: RuntimeSnapshotView, offset: int = 0):
    if feature_id in MARKET_DATA_FEATURES:
        return snapshot.get_feature(feature_id, offset=offset)
    # ... existing indicator resolution
```

### Phase 2: Indicator Source Support (~30 lines)

Allow indicators to use OI/funding as source:

```python
# In feature computation
if feature_spec.source == "open_interest":
    input_series = feed.open_interest
elif feature_spec.source == "funding_rate":
    input_series = feed.funding_rate
```

### Phase 3: Validation Play (~10 lines)

Add validation coverage:

```yaml
# tests/validation/plays/V_140_market_data_features.yml
id: V_140_market_data
features:
  - id: funding_sma
    indicator: sma
    params: {length: 8}
    source: funding_rate
blocks:
  - id: test_oi_access
    when:
      - lhs: {feature_id: "open_interest"}
        op: gt
        rhs: 0
```

---

## Data Availability

### Sync Commands

```bash
# Sync funding rates (default 3 months)
python trade_cli.py data sync-funding BTCUSDT --period 6M

# Sync open interest (default 1 month, 1h intervals)
python trade_cli.py data sync-oi BTCUSDT --period 3M --interval 1h
```

### Granularity

| Data | Intervals Available | Default |
|------|---------------------|---------|
| Funding Rate | Fixed 8h | 8h |
| Open Interest | 5min, 15min, 30min, 1h, 4h, 1d | 1h |

### Storage

- Database: `data/market_data_{env}.duckdb`
- Tables: `funding_rates_{env}`, `open_interest_{env}`
- Metadata: `funding_metadata_{env}`, `open_interest_metadata_{env}`

---

## Verdict

| Question | Answer |
|----------|--------|
| Worth integrating? | **Yes** |
| Hot loop performance impact? | **None** (already O(1)) |
| Implementation effort? | **Low** (~50-60 lines total) |
| Strategic value? | **Medium-High** for filtering |
| Data already available? | **Yes** - just needs DSL wiring |

---

## Complete Strategy Example

A trend-following Play with OI/funding quality filters:

```yaml
id: trend_with_market_filters
symbol: BTCUSDT
tf: 15m
htf: 4h

features:
  # Trend indicators
  - id: ema_20
    indicator: ema
    params: {length: 20}
  - id: ema_50
    indicator: ema
    params: {length: 50}
  - id: atr_14
    indicator: atr
    params: {length: 14}

  # OI derivatives (requires Phase 2 implementation)
  - id: oi_sma_24
    indicator: sma
    params: {length: 24}
    source: open_interest
  - id: oi_roc_12
    indicator: roc
    params: {length: 12}
    source: open_interest

blocks:
  # === TREND CONDITIONS ===
  - id: uptrend
    when:
      all:
        - lhs: {feature_id: "ema_20"}
          op: gt
          rhs: {feature_id: "ema_50"}
        - lhs: {feature_id: "close"}
          op: gt
          rhs: {feature_id: "ema_20"}

  # === MARKET DATA FILTERS ===
  - id: funding_acceptable
    when:
      # Not too crowded long (< 0.05%)
      - lhs: {feature_id: "funding_rate"}
        op: lt
        rhs: 0.0005

  - id: oi_confirms_trend
    when:
      any:
        # OI above average (money in the market)
        - lhs: {feature_id: "open_interest"}
          op: gt
          rhs: {feature_id: "oi_sma_24"}
        # OR OI rising (new money entering)
        - lhs: {feature_id: "oi_roc_12"}
          op: gt
          rhs: 2  # >2% increase over 12 bars

  - id: not_exhausted
    when:
      # OI not crashing while price rising (divergence = exhaustion)
      - lhs: {feature_id: "oi_roc_12"}
        op: gt
        rhs: -10  # Not dropping more than 10%

  # === COMBINED ENTRY ===
  - id: quality_long_entry
    when:
      all:
        - {ref: uptrend}
        - {ref: funding_acceptable}
        - {ref: oi_confirms_trend}
        - {ref: not_exhausted}

actions:
  entry:
    when: {ref: quality_long_entry}
    direction: long
    size_usdt: 1000

  exit:
    when:
      any:
        # Trend reversal
        - lhs: {feature_id: "close"}
          op: lt
          rhs: {feature_id: "ema_50"}
        # Funding flipped extreme (crowd piled in)
        - lhs: {feature_id: "funding_rate"}
          op: gt
          rhs: 0.001  # >0.1% = very crowded
```

This Play:
1. Only enters longs when funding isn't crowded (<0.05%)
2. Requires OI confirmation (above average OR rising)
3. Avoids exhausted moves (OI not crashing)
4. Exits when funding gets extreme (crowd piled in)

---

## Related Files

| File | Purpose |
|------|---------|
| `src/data/historical_data_store.py` | Data sync and storage |
| `src/backtest/engine_data_prep.py` | Data loading for backtest |
| `src/backtest/engine_feed_builder.py` | Array alignment |
| `src/backtest/runtime/feed_store.py` | FeedStore with market data fields |
| `src/backtest/runtime/snapshot_view.py` | Snapshot accessors |
| `src/backtest/runtime/funding_scheduler.py` | Funding settlement logic |
| `src/backtest/sim/funding/funding_model.py` | Funding PnL application |
