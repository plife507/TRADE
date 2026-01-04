# Backtest Engine Code Review Report

**Date**: 2025-12-31
**Scope**: Module-by-module review of backtest engine
**Focus**: Array layering, data calculation patterns, IdeaCard value flow

---

## Executive Summary

Comprehensive code review identified **critical value flow issues** where IdeaCard configuration values are IGNORED, while confirming the **hot loop and indicator systems are clean**.

| Priority | Area | Status |
|----------|------|--------|
| P0 | IdeaCard → Engine value flow | **ISSUES FOUND** |
| P1 | SimulatedExchange hardcoded defaults | **ISSUES FOUND** |
| P2 | Hot loop O(1) array access | **VERIFIED CLEAN** |
| P3 | Indicator registry-driven | **VERIFIED CLEAN** |

---

## P0 Critical: IdeaCard Values IGNORED

### Issue 1: `slippage_bps` from IdeaCard is IGNORED

**Location**: [engine_factory.py](../../src/backtest/engine_factory.py)

**IdeaCard declares**:
```yaml
account:
  slippage_bps: 2.0  # User expects 2 bps slippage
```

**Current behavior**: Engine ALWAYS uses 5.0 bps (hardcoded in `sim/types.py:564`)

**Root cause trace**:
1. `IdeaCard.account.slippage_bps` exists ([idea_card.py:109](../../src/backtest/idea_card.py#L109))
2. `engine_factory.py` **NEVER extracts it**
3. `engine.py:211-214` creates ExecutionConfig from `config.params`
4. `config.params` = `StrategyInstanceConfig.params` which only contains `history` config
5. ExecutionConfig falls back to hardcoded `slippage_bps=5.0`

### Issue 2: `maker_bps` from IdeaCard is IGNORED

**Location**: [engine_factory.py:110-112](../../src/backtest/engine_factory.py#L110-L112)

**IdeaCard declares**:
```yaml
account:
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0  # IGNORED
```

**Current behavior**: Only `taker_bps` is extracted. `maker_bps` is never used anywhere.

### Issue 3: ExecutionConfig hardcoded in engine.py

**Location**: [engine.py:211-214](../../src/backtest/engine.py#L211-L214)

```python
self.execution_config = ExecutionConfig(
    taker_fee_bps=params.get("taker_fee_bps", 6.0),  # HARDCODED
    slippage_bps=params.get("slippage_bps", 5.0),    # HARDCODED
)
```

**Problem**: `params` dict is never populated with these values from IdeaCard.

---

## P0: Value Flow Audit (IdeaCard → Engine)

| IdeaCard Field | Expected Consumer | Current Status |
|----------------|-------------------|----------------|
| `account.starting_equity_usdt` | RiskProfileConfig.initial_equity | ✅ Working |
| `account.max_leverage` | RiskProfileConfig.max_leverage | ✅ Working |
| `account.fee_model.taker_bps` | RiskProfileConfig.taker_fee_rate | ✅ Working |
| `account.fee_model.maker_bps` | ??? | ❌ **IGNORED** |
| `account.slippage_bps` | ExecutionConfig.slippage_bps | ❌ **IGNORED (always 5.0)** |
| `account.min_trade_notional_usdt` | RiskProfileConfig.min_trade_usdt | ⚠️ Fallback to 1.0 |
| `tf_configs[role].warmup_bars` | Engine warmup calculation | ✅ Working |
| `tf_configs[role].feature_specs` | FeatureFrameBuilder | ✅ Working |
| `signal_rules` | IdeaCardSignalEvaluator | ✅ Working |
| `risk_model` | SimulatedRiskManager | ✅ Working |

---

## P1: SimulatedExchange Hardcoded Values

### Issue 1: Maintenance Margin Rate hardcoded

**Location**: [system_config.py:268](../../src/backtest/system_config.py#L268)

```python
maintenance_margin_rate: float = 0.005  # 0.5% - ALWAYS this value
```

**Impact**: IdeaCard cannot configure maintenance margin rate. Always uses Bybit lowest tier (0.5%).

**Recommendation**: Add `account.maintenance_margin_rate` to IdeaCard schema.

### Issue 2: ExecutionConfig defaults in types.py

**Location**: [sim/types.py:558-567](../../src/backtest/sim/types.py#L558-L567)

```python
class ExecutionConfig:
    slippage_bps: float = 5.0   # HARDCODED default
    taker_fee_bps: float = 6.0  # HARDCODED default (legacy)
```

### Issue 3: SpreadConfig hardcoded

**Location**: [sim/pricing/spread_model.py:18-26](../../src/backtest/sim/pricing/spread_model.py#L18-L26)

```python
class SpreadConfig:
    mode: str = "fixed"
    fixed_spread_bps: float = 2.0    # HARDCODED
    min_spread_bps: float = 1.0      # HARDCODED
    max_spread_bps: float = 20.0     # HARDCODED
```

### Issue 4: SlippageConfig hardcoded

**Location**: [sim/execution/slippage_model.py:23-31](../../src/backtest/sim/execution/slippage_model.py#L23-L31)

```python
class SlippageConfig:
    mode: str = "fixed"
    fixed_bps: float = 5.0           # HARDCODED
    min_bps: float = 1.0             # HARDCODED
    max_bps: float = 50.0            # HARDCODED
```

---

## P2: Hot Loop - VERIFIED CLEAN

### Findings

The hot loop in [engine.py:703-898](../../src/backtest/engine.py#L703-L898) is confirmed O(1):

1. **FeedStore array access**: `exec_feed.open[i]`, `exec_feed.indicators[key][i]` - O(1)
2. **Timestamp lookups**: `exec_feed.get_ts_close_datetime(i)` - O(1)
3. **Snapshot creation**: `build_snapshot_view_impl()` just sets indices, no copying - O(1)
4. **No DataFrame.iloc calls** in hot loop

### Key Files Verified

| File | Status |
|------|--------|
| [engine.py](../../src/backtest/engine.py) (hot loop) | ✅ O(1) access |
| [engine_snapshot.py](../../src/backtest/engine_snapshot.py) | ✅ O(1) creation |
| [runtime/feed_store.py](../../src/backtest/runtime/feed_store.py) | ✅ Array-backed |
| [runtime/snapshot_view.py](../../src/backtest/runtime/snapshot_view.py) | ✅ Reference-only |

---

## P3: Indicator System - VERIFIED CLEAN

### Findings

1. **Single source of truth**: SUPPORTED_INDICATORS dict in [indicator_registry.py:196](../../src/backtest/indicator_registry.py#L196)
2. **No DEFAULT_INDICATORS**: Legacy pattern fully removed
3. **Warmup formulas**: Registry-driven via `info.warmup_formula(params)` ([indicator_registry.py:819-820](../../src/backtest/indicator_registry.py#L819-L820))
4. **Math parity**: Already validated (42/42 indicators pass)
5. **Mutually exclusive outputs**: Fixed in previous session

---

## Recommended Fixes

### Fix 1: Extract slippage_bps from IdeaCard (CRITICAL)

**File**: `engine_factory.py`

```python
# After line 117, add:
slippage_bps = 5.0  # Default
if idea_card.account.slippage_bps is not None:
    slippage_bps = idea_card.account.slippage_bps

# Add to strategy_params:
strategy_params["slippage_bps"] = slippage_bps
strategy_params["taker_fee_bps"] = idea_card.account.fee_model.taker_bps if idea_card.account.fee_model else 6.0
```

### Fix 2: Add maintenance_margin_rate to IdeaCard

**File**: `idea_card.py` AccountConfig

```python
@dataclass(frozen=True)
class AccountConfig:
    # ... existing fields ...
    maintenance_margin_rate: Optional[float] = None  # 0.005 = 0.5%
```

### Fix 3: Remove fallback defaults (fail-loud)

**File**: `engine_factory.py`

Replace silent fallbacks with fail-loud validation:

```python
# Instead of: taker_fee_rate = 0.0006
if idea_card.account.fee_model is None:
    raise ValueError(
        f"IdeaCard '{idea_card.id}' is missing account.fee_model. "
        "Fee model is required (taker_bps, maker_bps)."
    )
```

---

## Success Criteria Checklist

- [x] Hot loop verified O(1) array access
- [x] No DataFrame operations in hot loop
- [x] Indicator system is registry-driven (no DEFAULT_INDICATORS)
- [x] Warmup formulas from registry
- [x] Math parity validated (42/42 indicators)
- [x] Rollup parity validated (21/21 intervals)
- [ ] **FIX NEEDED**: All execution params traceable to IdeaCard
- [ ] **FIX NEEDED**: No silent defaults for required values
- [ ] **FIX NEEDED**: Add missing IdeaCard fields (maintenance_margin_rate)

---

## Files Modified by Fixes

| File | Change |
|------|--------|
| `engine_factory.py` | Extract slippage_bps, taker_fee_bps from IdeaCard |
| `engine.py` | Use params from IdeaCard, not hardcoded |
| `idea_card.py` | Add maintenance_margin_rate field |
| `sim/types.py` | Consider removing default values (fail-loud) |

---

## Audit Trail

| Audit | Result |
|-------|--------|
| Rollup Parity | PASSED 21/21 intervals, 140 comparisons |
| Math Parity | PASSED 42/42 indicators, 19/19 columns |
| 1m Alignment | PASSED 5/5 spot checks |
| Hot Loop O(1) | VERIFIED CLEAN |
| Indicator Registry | VERIFIED CLEAN |
