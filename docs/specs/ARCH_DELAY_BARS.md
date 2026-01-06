# Delay Bars & Market Structure Configuration

**STATUS:** CANONICAL
**PURPOSE:** Delay bars functionality, market structure configuration, evaluation start offset
**LAST UPDATED:** January 4, 2026 (Terminology update)

---

## Terminology (2026-01-04)

This document uses the new trading hierarchy terminology:

| Term | Definition |
|------|------------|
| **Setup** | Reusable rule blocks, filters, entry/exit logic |
| **Play** | Complete strategy specification |
| **Playbook** | Collection of plays with regime routing |
| **System** | Full trading operation with risk/execution |
| **Forge** | Development/validation environment (src/forge/) |

See: `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` for complete architecture.

---

## Executive Summary

Delay bars allow strategies to specify an evaluation start delay (in bars) independent of data lookback requirements, preventing lookahead bias in multi-timeframe strategies. The feature separates **data requirements** (lookback_bars) from **evaluation offset** (delay_bars), ensuring proper closed-candle alignment.

**Key Principles:**
- ✅ Delay ≠ Lookback: Lookback for data fetching only; delay for evaluation start offset
- ✅ Closed-candle aligned: Uses `ceil_to_tf_close()` to ensure delay offset lands on TF close
- ✅ Preflight source-of-truth: Engine consumes delay from Preflight, never re-computes
- ✅ Fail-loud validation: Missing delay config raises `ValueError` before simulation starts
- ✅ Per-role granularity: Each TF role (exec, mtf, htf) can have independent delay

---

## Market Structure Configuration

### Play Schema

```yaml
tf_configs:
  exec:
    tf: "15m"
    warmup_bars: 50
    market_structure:  # NEW (optional)
      lookback_bars: 80   # Data fetch/warmup requirement
      delay_bars: 12      # Evaluation start delay
```

### Semantics

| Field | Purpose | Used By |
|-------|---------|---------|
| **lookback_bars** | Additional bars for market structure analysis (swing highs/lows, etc.) | Preflight (data fetch range) |
| **delay_bars** | Bars to skip at evaluation start (no-lookahead guarantee) | Engine (evaluation offset) |

**Critical**: Engine MUST NOT apply lookback to evaluation start (only delay applies).

### Data Flow

```
Play market_structure
    |
compute_warmup_requirements() -> delay_by_role
    |
Preflight -> delay_by_role in PreflightReport
    |
SystemConfig.delay_bars_by_role
    |
Engine applies delay offset (closed-candle aligned)
```

---

## Delay Bars Implementation

### Integration Points

1. **Play** (`src/backtest/play.py`): Added `MarketStructureConfig` to `TFConfig`
2. **Preflight** (`src/backtest/execution_validation.py`): Computes `delay_by_role` from Play
3. **SystemConfig** (`src/backtest/system_config.py`): Added `delay_bars_by_role` to system UID
4. **Engine** (`src/backtest/engine.py`): Applies delay offset to `simulation_start_ts` using `ceil_to_tf_close()`
5. **Artifacts** (`src/backtest/artifacts/artifact_standards.py`): Added `computed_delay_bars_by_role` to `RunManifest`

### Engine Logic

**Single-TF Mode** (`src/backtest/engine.py`):
```python
# After indicator readiness check
exec_delay_bars = delay_bars_by_role.get('exec', 0)
if exec_delay_bars > 0:
    aligned_start = ceil_to_tf_close(sim_start_ts, tf)
    delay_offset = tf_duration(tf) * exec_delay_bars
    eval_start_ts = aligned_start + delay_offset
    sim_start_idx = find_bar_at_or_after(eval_start_ts)
```

**Multi-TF Mode**:
```python
# Applies delay for all roles (exec, htf, mtf)
# Takes max delay across all roles to ensure all TFs are ready
max_delay_offset = max([delay * tf_duration(tf) for role, delay in delay_bars_by_role.items()])
sim_start_ts = requested_start + max_delay_offset
```

### Closed-Candle Alignment

**Implementation**:
```python
aligned_start = ceil_to_tf_close(sim_start_ts, tf)
delay_offset = tf_duration(tf) * exec_delay_bars
eval_start_ts = aligned_start + delay_offset
```

**Examples**:
- 5m delay of 12 bars → 60 minutes → eval_start at `08:00:00` ✅
- 15m delay of 5 bars → 75 minutes → eval_start at `01:15:00` ✅

---

## Validation & Error Handling

### Fail-Loud Enforcement

**Engine** (`src/backtest/engine.py`):
```python
if not delay_bars_by_role or 'exec' not in delay_bars_by_role:
    raise ValueError(
        "MISSING_DELAY_CONFIG: delay_bars_by_role['exec'] not set. "
        "Preflight gate must run first."
    )
```

**No silent defaults. No implicit computations. Fail loud.**

### Backward Compatibility

Existing Plays without `market_structure` will use:
- `lookback_bars = max(warmup_bars, feature_warmup, bars_history_required)`
- `delay_bars = 0`

**Backward Compatibility**: **NONE** (per project rules: build-forward only)

---

## Breaking Changes

### SystemConfig Changes

**Added Field**:
```python
@dataclass
class SystemConfig:
    # ... existing fields ...
    delay_bars_by_role: Dict[str, int] = field(default_factory=dict)  # NEW
```

**Impact**: Changes `system_uid` hash when delay bars are modified

### RunManifest Changes

**Renamed Field**:
- ❌ `computed_warmup_by_role`
- ✅ `computed_lookback_bars_by_role`

**Added Field**:
- ✅ `computed_delay_bars_by_role`

---

## Performance Impact

### Runtime

No measurable impact on backtest execution time:
- Delay bars only affect **start index**, not simulation speed
- Single-TF: <1s total
- Multi-TF: ~1s total

### Memory

Negligible impact:
- `delay_bars_by_role` adds ~48 bytes to `SystemConfig`
- No additional data structures required

### Data Fetching

**Benefit**: Separating delay from lookback allows more precise data queries:

**Before** (implicit delay in warmup):
```python
warmup_bars = 100  # Includes both warmup AND delay
```

**After** (explicit separation):
```python
lookback_bars = 80   # Data requirement
delay_bars = 20      # Evaluation offset
# Engine fetches exactly 80 bars before window, delays eval by 20
```

---

## Known Limitations

### Cross-TF Delay Synchronization

**Current Behavior**: Multi-TF mode takes `max(delay_bars)` across all roles

**Limitation**: Cannot have exec start evaluating before HTF is ready

**Future Enhancement**: Allow per-role independent delay starts with explicit HTF/MTF readiness checks

### Dynamic Delay Adjustment

**Current Behavior**: Delay is static per backtest run

**Limitation**: Cannot adjust delay based on runtime conditions (e.g., volatility)

**Workaround**: Run multiple backtests with different delay configs

### Partial Candle Handling

**Current Behavior**: Delay offset uses `ceil_to_tf_close()` to ensure closed candles only

**Limitation**: Real-time strategies may need partial candle delay

**Scope**: Out of scope for backtest-only feature (live trading has different requirements)

---

## Code Locations

| Component | File | Purpose |
|-----------|------|---------|
| **MarketStructureConfig** | `src/backtest/play.py` | Data structure definition |
| **Delay Computation** | `src/backtest/execution_validation.py` | `compute_warmup_requirements()` extracts delay |
| **SystemConfig** | `src/backtest/system_config.py` | Stores `delay_bars_by_role` |
| **Engine Application** | `src/backtest/engine.py` | Applies delay offset (2 locations: single-TF, multi-TF) |
| **Timeframe Utils** | `src/backtest/runtime/timeframe.py` | `ceil_to_tf_close()` function |
| **Artifact Export** | `src/backtest/artifacts/artifact_standards.py` | `RunManifest.computed_delay_bars_by_role` |

---

## References

- Market Structure Config: `src/backtest/play.py:638-677`
- Delay Computation: `src/backtest/execution_validation.py:421-461`
- Engine Application: `src/backtest/engine.py:460-465` (single-TF), `646-659` (multi-TF)
- Timeframe Utils: `src/backtest/runtime/timeframe.py`

---

**See Also:**
- `ARCH_SNAPSHOT.md` - Overall system architecture
- `ARCH_INDICATOR_WARMUP.md` - Indicator warmup computation
- `docs/session_reviews/2024-12-17_delay_bars_implementation_and_validation.md` - Implementation details
