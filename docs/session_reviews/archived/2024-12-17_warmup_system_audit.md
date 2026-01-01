# Warmup System Architecture Audit

**Date**: December 17, 2024  
**Type**: Comprehensive System Audit  
**Scope**: Warmup computation, validation, and data flow  
**Status**: Post-P0 Fix Documentation

---

## Executive Summary

This document provides a comprehensive audit of the warmup system architecture following the P0 warmup synchronization fix. It answers 30 critical questions about warmup computation, validation, data flow, and implementation details.

**Key Findings**:
- ✅ Warmup computation is centralized in `compute_warmup_requirements()`
- ✅ Per-TF warmup is supported via `warmup_bars_by_role`
- ⚠️ YAML loader and audit tools do NOT populate warmup (broken paths)
- ✅ Engine now fails loud on missing warmup config
- ✅ Preflight validates timestamp coverage with warmup buffer
- ⚠️ No max expansion policy or exchange limit handling

---

## Table of Contents

1. [Warmup Computation](#warmup-computation)
2. [SystemConfig Schema](#systemconfig-schema)
3. [Population Paths](#population-paths)
4. [Engine Behavior](#engine-behavior)
5. [Evaluation Start Logic](#evaluation-start-logic)
6. [Preflight System](#preflight-system)
7. [MTF Handling](#mtf-handling)
8. [Indicator Warmup](#indicator-warmup)
9. [Data Tools & CLI](#data-tools--cli)
10. [Testing & Validation](#testing--validation)
11. [Known Issues](#known-issues)

---

## Warmup Computation

### Q1: Where is warmup requirement computed and what function owns it?

**Owner Function**: `compute_warmup_requirements(idea_card: IdeaCard) -> WarmupRequirements`

**Location**: `src/backtest/execution_validation.py:421-461`

**Formula**:
```python
# Per-TF role (exec/htf/mtf):
effective_warmup = max(
    max(spec.warmup_bars for spec in tf_config.feature_specs),  # Indicator-derived
    tf_config.warmup_bars,                                       # Explicit declaration
    idea_card.bars_history_required                              # Global minimum
)
```

**Returns**: `WarmupRequirements` dataclass with:
- `warmup_by_role: Dict[str, int]` - Per-TF warmup (e.g., `{"exec": 200, "htf": 150}`)
- `max_warmup_bars: int` - Overall maximum across all TFs
- `feature_warmup: Dict[str, int]` - Indicator-derived warmup only
- `bars_history_required: int` - IdeaCard global setting

**Example**:
```python
# IdeaCard with:
# - exec TF: SMA(20) → warmup_bars property = 20
# - tf_config.warmup_bars: 200 (explicit)
# - bars_history_required: 0
# Result: effective_warmup = max(20, 200, 0) = 200
```

**Design Intent**: Single source of truth that respects user declarations over computed values.

---

## SystemConfig Schema

### Q2: Is warmup_bars_by_role present in SystemConfig? What's its schema?

**YES**, added in P0 fix session (December 17, 2024).

**Location**: `src/backtest/system_config.py:499`

**Schema**:
```python
@dataclass
class SystemConfig:
    # IdeaCard-declared warmup bars per TF role (exec/htf/mtf)
    # This is the CANONICAL warmup source - engine MUST use this, not recompute
    warmup_bars_by_role: Dict[str, int] = field(default_factory=dict)
```

**Structure**:
- **Type**: `Dict[str, int]`
- **Keys**: TF role strings (`"exec"`, `"htf"`, `"mtf"`)
- **Values**: Warmup bar counts (integer)

**Example**:
```python
{
    "exec": 200,  # 200 bars on execution/LTF timeframe
    "htf": 150,   # 150 bars on HTF timeframe
    "mtf": 100    # 100 bars on MTF timeframe (if present)
}
```

**Serialization**: Included in `SystemConfig.to_dict()` output (line 563).

**Comment Warning**: Code says *"If empty, engine will compute from feature specs (legacy path)"* — **This legacy path was removed in the P0 fix**.

---

## Population Paths

### Q3: Does runner always populate warmup_bars_by_role from IdeaCard?

**NO**. Found 3 SystemConfig creation paths with different behaviors:

| Path | File | Line | Populates warmup? | Status |
|------|------|------|-------------------|--------|
| **IdeaCard runner** | `runner.py` | 188-241 | ✅ YES | Working |
| **YAML loader** | `system_config.py` | 852-864 | ❌ NO | Broken |
| **Snapshot audit** | `audit_snapshot_plumbing_parity.py` | 541-556 | ❌ NO | Broken |

**Working Path** (IdeaCard runner):
```python
# src/backtest/runner.py:188-189
warmup_req = compute_warmup_requirements(idea_card)
warmup_bars_by_role = warmup_req.warmup_by_role

# Line 241
system_config = SystemConfig(
    # ...
    warmup_bars_by_role=warmup_bars_by_role,  # ✅ Populated
)
```

**Broken Path 1** (YAML loader):
```python
# src/backtest/system_config.py:852
config = SystemConfig(
    system_id=raw.get("system_id", system_id),
    symbol=raw.get("symbol", ""),
    # ...
    warmup_multiplier=warmup_multiplier,
    # ❌ warmup_bars_by_role NOT passed - defaults to {}
)
```

**Broken Path 2** (Audit tool):
```python
# src/backtest/audit_snapshot_plumbing_parity.py:541
system_config = SystemConfig(
    system_id=idea_card.id,
    symbol=symbol,
    # ...
    feature_specs_by_role=feature_specs_by_role,
    # ❌ warmup_bars_by_role NOT passed - defaults to {}
)
```

**Impact**:
- Legacy YAML-based SystemConfigs will trigger `MISSING_WARMUP_CONFIG` error
- Snapshot plumbing parity audit will fail unless updated
- Any direct SystemConfig construction bypassing runner is broken

**Recommendation**: Wire warmup to all construction paths or deprecate YAML/audit paths.

---

## Engine Behavior

### Q4: Does engine contain fallback warmup derivation? Where?

**NO FALLBACKS** as of P0 fix. Engine now **fails loud** on missing warmup config.

**Enforcement Locations**:

**Single-TF Mode** (`src/backtest/engine.py:460-465`):
```python
warmup_bars_by_role = getattr(self.config, 'warmup_bars_by_role', {})
if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
    raise ValueError(
        "MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set. "
        "Ensure IdeaCard warmup is wired through compute_warmup_requirements() to SystemConfig."
    )
warmup_bars = warmup_bars_by_role['exec']
```

**Multi-TF Mode** (`src/backtest/engine.py:646-659`):
```python
if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
    raise ValueError("MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set for multi-TF mode...")

if 'htf' not in warmup_bars_by_role:
    raise ValueError("MISSING_WARMUP_CONFIG: warmup_bars_by_role['htf'] not set for multi-TF mode...")
```

**Exception**: `get_warmup_from_specs()` still called for `max_lookback` computation (indicator validation only):
```python
# Line 469, 664 - NOT used for data fetching
max_lookback = get_warmup_from_specs(exec_specs, warmup_multiplier=1) if exec_specs else 0
```

**Previous Behavior** (before P0 fix):
```python
# REMOVED - was silently recomputing warmup
warmup_multiplier = self.config.warmup_multiplier
exec_specs = self.config.feature_specs_by_role.get('exec', [])
warmup_bars = get_warmup_from_specs(exec_specs, warmup_multiplier)
```

**Design Philosophy**: Fail loud, no silent defaults, forward-facing only.

---

## Evaluation Start Logic

### Q5: What defines "evaluation start" and how is it offset by warmup?

**Evaluation Start**: Defined by `sim_start_idx` (integer index in full DataFrame).

**Computation Logic** (`src/backtest/engine.py:547-561`):

```python
# Step 1: Find first bar where ALL indicators are valid (non-NaN)
first_valid_idx = find_first_valid_bar(df, required_indicator_columns)
first_valid_ts = df.iloc[first_valid_idx]["timestamp"]

# Step 2: Simulation starts at max(first_valid_bar, window_start)
if first_valid_ts >= requested_start:
    sim_start_idx = first_valid_idx
else:
    # Find first bar >= requested_start
    mask = df["timestamp"] >= requested_start
    sim_start_idx = mask.idxmax()
```

**Warmup is IMPLICIT**:
- Data is fetched with warmup buffer: `extended_start = requested_start - warmup_span`
- Bars `[0, sim_start_idx)` constitute the warmup period
- Bars `[sim_start_idx, end]` are the evaluation period
- Main loop explicitly skips warmup: `if i < sim_start_idx: continue` (line 1150)

**NOT stored as "warmup offset"** — derived from timestamps and indicator validity.

**Example**:
```
DataFrame indices: [0, 1, 2, ..., 299]
Window start: 2024-11-01 00:00 (index 200)
First valid indicators: index 198
sim_start_idx: 200 (max(198, 200))
Warmup bars: [0:200] (200 bars)
Eval bars: [200:300] (100 bars)
```

**Multi-TF Simulation Start** (line 772-790): Same logic applied to LTF DataFrame.

---

## Preflight System

### Q6: Does preflight compute required bars? Where and formula?

**YES**, preflight computes warmup-adjusted start time.

**Function**: `calculate_warmup_start(window_start, warmup_bars, tf_minutes) -> datetime`

**Location**: `src/backtest/runtime/preflight.py:255-262`

**Formula**:
```python
def calculate_warmup_start(window_start: datetime, warmup_bars: int, tf_minutes: int) -> datetime:
    warmup_minutes = warmup_bars * tf_minutes
    return window_start - timedelta(minutes=warmup_minutes)
```

**Example**:
```python
window_start = datetime(2024, 11, 1, 0, 0)
warmup_bars = 200
tf_minutes = 15  # 15m timeframe
warmup_minutes = 200 × 15 = 3000 minutes = 50 hours
effective_start = window_start - 3000 minutes
                = 2024-10-29 22:00:00
```

**Source of warmup_bars** (line 660):
```python
for role, tf_config in idea_card.tf_configs.items():
    warmup = tf_config.effective_warmup_bars  # Uses IdeaCard's declared warmup
    pairs_to_check.append((symbol, tf_config.tf, warmup))
```

**`effective_warmup_bars`** property (IdeaCard):
```python
@property
def effective_warmup_bars(self) -> int:
    return max(self.warmup_bars, self.max_warmup_from_specs)
```

---

### Q7: Does preflight validate using bar counts, timestamps, or both?

**BOTH**, with timestamp-based coverage as primary check.

**Validation Checks** (`src/backtest/runtime/preflight.py:validate_tf_data`):

| Check | Method | Lines | Type | Fail Condition |
|-------|--------|-------|------|----------------|
| **Data exists** | `df.empty` | 306-308 | Bar count | Empty DataFrame |
| **Timestamp coverage** | `min_ts <= eff_start AND max_ts >= req_end` | 332-342 | **Timestamp** | Outside range |
| **Bar count** | `len(df)` | 325 | Bar count | Informational only |
| **Monotonic timestamps** | `df["timestamp"].diff() > 0` | 346-349 | Timestamp | Non-increasing |
| **Unique timestamps** | `df["timestamp"].duplicated()` | 352-356 | Timestamp | Duplicates found |
| **Alignment** | `mode_step == expected_step` | 358-370 | Timestamp | Warning only |
| **Gap detection** | `diff > gap_threshold × tf_minutes` | 372-397 | Timestamp | Large gaps |

**Primary Coverage Check** (line 332-342):
```python
# Normalize to naive for comparison (DuckDB stores naive UTC)
eff_start_cmp = effective_start.replace(tzinfo=None) if effective_start.tzinfo else effective_start
req_end_cmp = required_end.replace(tzinfo=None) if required_end.tzinfo else required_end

if min_ts <= eff_start_cmp and max_ts >= req_end_cmp:
    result.covers_range = True
else:
    if min_ts > eff_start_cmp:
        result.errors.append(f"Data starts too late: {min_ts} > {eff_start_cmp} (need {warmup_bars} warmup bars)")
    if max_ts < req_end_cmp:
        result.errors.append(f"Data ends too early: {max_ts} < {req_end_cmp}")
```

**Bar count is logged but NOT used for pass/fail** — timestamp coverage determines result.

---

### Q8: When preflight finds insufficient data, what does it do?

**Depends on `auto_sync_missing` flag**.

**Mode 1: Manual (default)** (`auto_sync_missing=False`):
- Sets `status = PreflightStatus.FAILED`
- Logs errors to `TFPreflightResult.errors`
- **Does NOT auto-expand** or fetch data
- **Does NOT silently proceed**
- Runner checks status and raises `GateFailure` exception
- User must manually run data sync commands

**Mode 2: Auto-sync** (`auto_sync_missing=True`):

**Location**: `src/backtest/runtime/preflight.py:675-720`

**Heal Loop**:
```python
max_attempts = auto_sync_config.max_attempts  # Default: 3
attempt = 0

while failed_pairs and attempt < max_attempts:
    attempt += 1
    
    # Run auto-sync via tools
    sync_result = _run_auto_sync(pairs_to_sync=failed_pairs, auto_sync_config=config)
    sync_result.attempts_made = attempt
    
    # Re-validate after sync
    tf_results, failed_pairs = _validate_all_pairs(...)
    
    if not failed_pairs:
        break  # Success
```

**Auto-sync calls** (line 689-692):
```python
sync_result = _run_auto_sync(
    pairs_to_sync=failed_pairs,
    auto_sync_config=auto_sync_config,
)
```

**Tools used** (`_run_auto_sync` implementation):
1. `sync_range_tool(symbol, tf, start, end, env)` - Fetch missing data
2. `fill_gaps_tool(symbol, tf, env)` - Fill gaps in existing data
3. `heal_data_tool(symbol, tf, env)` - Comprehensive cleanup

**Tool Discipline** (comment line 637-641):
```python
# TOOL DISCIPLINE (MANDATORY):
# - When auto_sync_missing=True, preflight MUST call data tools to fix issues
# - All data fixes go through sync_range_tool, fill_gaps_tool, heal_data_tool
# - Simulator/backtest MUST NOT modify DuckDB directly
```

**Stop conditions**:
1. All pairs pass validation → `PreflightStatus.PASSED`
2. Max attempts reached → `PreflightStatus.FAILED`
3. Auto-sync returns `success=False` → `PreflightStatus.FAILED`

**Result**: Auto-sync metadata stored in `PreflightReport.auto_sync_result`.

---

### Q9: Is there a "window planner" or "range expander" function?

**NO dedicated planner**. Range expansion is **inline** in multiple locations.

**Expansion Sites**:

**1. Preflight** (`src/backtest/runtime/preflight.py:255-262`):
```python
def calculate_warmup_start(window_start: datetime, warmup_bars: int, tf_minutes: int) -> datetime:
    warmup_minutes = warmup_bars * tf_minutes
    return window_start - timedelta(minutes=warmup_minutes)
```

**2. Engine Single-TF** (`src/backtest/engine.py:471-474`):
```python
tf_delta = self._timeframe_to_timedelta(self.config.tf)
warmup_span = tf_delta * warmup_bars
extended_start = requested_start - warmup_span
```

**3. Engine Multi-TF** (`src/backtest/engine.py:666-673`):
```python
ltf_delta = tf_duration(ltf_tf)
warmup_span = ltf_delta * warmup_bars

htf_delta = tf_duration(htf_tf)
htf_warmup_span = htf_delta * htf_warmup_bars

# Use the larger warm-up span
data_start = min(extended_start, requested_start - htf_warmup_span)
```

**Pattern**: Each component computes its own `extended_start` independently.

**NO centralized "window planner"** — duplication across preflight/engine.

**Recommendation**: Create `compute_data_window(window, warmup_by_role, tf_mapping)` utility.

---

### Q10: How do you measure "available bars before eval"?

**Method**: Count closed candles in DataFrame before `sim_start_idx`.

**Implementation** (implicit, not explicitly computed):

**Preflight** (line 325):
```python
result.bar_count = len(df)  # Total bars in range
```

**Engine** (line 573):
```python
sim_bars = len(df) - sim_start_idx  # Bars available for trading
```

**Warmup bars** (implicit):
```python
warmup_bars_available = sim_start_idx  # Index of first eval bar
```

**Example**:
```
DataFrame length: 300 bars
sim_start_idx: 200
warmup_bars_available: 200 bars [0:200]
sim_bars: 100 bars [200:300]
```

**NOT explicitly counted** as "warmup bars available" metric — must be inferred from index.

**Closed-candle enforcement**: All bars in DataFrame are closed candles (no partial bars).

---

## MTF Handling

### Q11: For MTF, how is alignment handled? Where?

**Alignment Method**: Exec/LTF close timestamps drive evaluation; HTF/MTF forward-fill between closes.

**Location**: `src/backtest/engine.py` (multi-TF run loop, ~line 1130-1190)

**Mechanism**:

**1. Close-ts Maps** (pre-computed, line 722-735):
```python
# Build maps of which LTF indices trigger HTF/MTF updates
close_ts_maps = {}
for role, frame in frames.items():
    close_ts_maps[role] = set(frame["timestamp"].values)
```

**2. Update Detection** (line ~1155):
```python
htf_updated, mtf_updated = self._update_htf_mtf_indices(bar.ts_close)
```

**3. Cache Behavior** (`TFCache`):
- Holds last-closed HTF/MTF snapshots
- Between HTF closes, cache returns same snapshot (forward-fill)
- On HTF close, cache updates to new snapshot

**4. Snapshot Access** (`RuntimeSnapshotView`):
```python
snapshot.htf_ema_fast  # Returns last-closed HTF value (forward-filled)
```

**TradingView-style**: `lookahead_off` semantics enforced:
- HTF indicator values remain constant between HTF closes
- No "future" data visible to strategy
- Matches TradingView repainting prevention

**Alignment Formula**:
```
LTF bar timestamp == HTF bar timestamp → Update HTF cache
Otherwise → Forward-fill last HTF snapshot
```

**Example**:
```
LTF bars (15m): 00:00, 00:15, 00:30, 00:45, 01:00, ...
HTF bars (1h):  00:00,                       01:00, ...

At LTF 00:15: HTF cache holds 00:00 snapshot (forward-fill)
At LTF 00:30: HTF cache holds 00:00 snapshot (forward-fill)
At LTF 00:45: HTF cache holds 00:00 snapshot (forward-fill)
At LTF 01:00: HTF cache updates to 01:00 snapshot (new data)
```

---

### Q12: In MTF, is warmup per-TF or single max?

**PER-TF** as of P0 fix (December 17, 2024).

**Structure** (`src/backtest/engine.py:646-659`):
```python
warmup_bars = warmup_bars_by_role['exec']      # e.g., 200 bars on 15m
htf_warmup_bars = warmup_bars_by_role['htf']   # e.g., 150 bars on 1h
```

**Data Fetch Strategy** (line 666-673):
```python
# LTF warmup span
ltf_delta = tf_duration(ltf_tf)
warmup_span = ltf_delta * warmup_bars  # e.g., 200 × 15min = 3000min

# HTF warmup span
htf_delta = tf_duration(htf_tf)
htf_warmup_span = htf_delta * htf_warmup_bars  # e.g., 150 × 60min = 9000min

# Use the LARGER span to ensure both TFs have enough warmup
data_start = min(extended_start, requested_start - htf_warmup_span)
```

**NOT a single max bar count** — respects per-TF bar requirements, then takes larger time span.

**Example**:
```
Window: 2024-11-01 to 2024-11-02
Exec (15m): 200 bars warmup = 3000 minutes = 2.08 days → start: 2024-10-29 22:00
HTF (1h):   150 bars warmup = 9000 minutes = 6.25 days → start: 2024-10-25 18:00

Data fetched from: 2024-10-25 18:00 (earlier of the two)
Both TFs get sufficient warmup in their respective timeframes.
```

**Formula Correctness**: 
- ✅ Exec gets ≥200 bars of 15m data
- ✅ HTF gets ≥150 bars of 1h data
- Approach is **time-based** after bar-to-time conversion

---

## Indicator Warmup

### Q13: Do indicators declare warmup in registry, or inferred from params?

**INFERRED from params** via `FeatureSpec.warmup_bars` property.

**Location**: `src/backtest/features/feature_spec.py:450-463`

**Implementation**:
```python
@property
def warmup_bars(self) -> int:
    """
    Minimum bars needed for this indicator to produce valid values.
    
    Returns proper warmup for each indicator type:
    - EMA: 3x length for stabilization
    - SMA: length
    - RSI: length + 1
    - ATR: length + 1
    - MACD: 3x slow + signal
    - BBANDS: length
    - STOCH: k + smooth_k + d
    - STOCHRSI: rsi_length + length + max(k, d)
    """
    from ..indicator_vendor import (
        get_ema_warmup,
        get_sma_warmup,
        # ... other warmup functions
    )
    # Type-specific dispatch based on self.indicator_type
```

**Warmup Computation** (delegated to vendor):
```python
# src/backtest/indicator_vendor.py
def get_ema_warmup(params: Dict) -> int:
    length = params.get("length", 20)
    return 3 * length  # 3x length for EMA stabilization

def get_macd_warmup(params: Dict) -> int:
    slow = params.get("slow", 26)
    signal = params.get("signal", 9)
    return 3 * slow + signal  # Slow EMA stabilization + signal EMA
```

**NO external registry file** — warmup is computed on-demand from:
1. Indicator type (from `FeatureSpec.indicator_type`)
2. Indicator params (from `FeatureSpec.params`)

**Dynamic computation**: Each `FeatureSpec` computes its own warmup when `.warmup_bars` property is accessed.

---

### Q14: Do any indicators need special warmup beyond period-based?

**YES**, multi-stage indicators have enhanced warmup requirements.

**Special Cases**:

| Indicator | Formula | Reason | Source |
|-----------|---------|--------|--------|
| **EMA** | `3 × length` | Stabilization (97% of true value) | `get_ema_warmup()` |
| **MACD** | `3 × slow + signal` | Slow EMA stabilization + signal EMA | `get_macd_warmup()` |
| **STOCHRSI** | `rsi_length + length + max(k, d)` | RSI → STOCH cascade | `get_stochrsi_warmup()` |
| **STOCH** | `k + smooth_k + d` | %K smoothing + %D | `get_stoch_warmup()` |
| **ADX** | `2 × length` (typical) | DI smoothing + ADX smoothing | `get_adx_warmup()` |
| **ATR** | `length + 1` | Initial true range + smoothing | `get_atr_warmup()` |
| **RSI** | `length + 1` | Initial gain/loss + smoothing | `get_rsi_warmup()` |

**EMA Example**:
```python
# Why 3x length?
# EMA converges exponentially to true value
# After 3×length bars, EMA is ~97% accurate
# EMA(20) needs 60 bars warmup
```

**MACD Example**:
```python
# MACD = EMA(fast) - EMA(slow)
# Signal = EMA(MACD, signal_length)
# Need slow EMA to stabilize (3×slow) + signal EMA (signal_length)
# MACD(12,26,9) needs 3×26 + 9 = 87 bars
```

**Representation**: Hardcoded formulas in `indicator_vendor.py` warmup functions.

**NO metadata system** — logic embedded in Python functions.

---

## Data Tools & CLI

### Q15-Q22: Data Tools, CLI, Storage

**Q15: Which components call CLI data tool?**

**Callers**:
1. **Preflight auto-sync** (`src/backtest/runtime/preflight.py:_run_auto_sync`)
2. **Manual CLI** (`trade_cli.py data sync/fill-gaps/heal`)

**Python API**: `src/tools/data_tools.py`
```python
from src.tools.data_tools import sync_range_tool, fill_gaps_tool, heal_data_tool

result = sync_range_tool(
    symbol="BTCUSDT",
    tf="15m",
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 1),
    env="live"
)
# Returns: ToolResult(success=bool, message=str, data=dict)
```

**Q16: CLI command interface**

**Commands**:
```bash
# Sync range (date-based)
python trade_cli.py data sync --symbol BTCUSDT --tf 15m --start 2024-01-01 --end 2024-12-01 --env live

# Fill gaps (scans existing data)
python trade_cli.py data fill-gaps --symbol BTCUSDT --tf 15m --env live

# Heal (sync + fill + cleanup)
python trade_cli.py data heal --symbol BTCUSDT --tf 15m --env live
```

**Args**:
- `--symbol` (required): Trading symbol
- `--tf` (required): Timeframe
- `--start`, `--end`: Datetime (ISO format or recognized strings)
- `--env`: "live" or "demo" (default: live)

**NO "bars" or "to-ts" args** — date-range based only.

**Q17: Storage mechanisms**

**DuckDB is authoritative**:
- OHLCV data: `data/market_data_live.duckdb` or `data/market_data_demo.duckdb`
- Table: `ohlcv_live` or `ohlcv_demo`

**Parquet for artifacts**:
- Backtest trades: `backtests/.../trades.parquet`
- Equity curve: `backtests/.../equity_curve.parquet`
- Manifest: `backtests/.../run_manifest.json`

**No CSV output** — legacy removed.

**Q18: Preflight data source**

**Source**: DuckDB

**Module**: `src/data/historical_data_store.py`

**DataLoader Type** (line 738):
```python
DataLoader = Callable[[str, str, datetime, datetime], pd.DataFrame]
```

**Implementation** (passed by runner):
```python
from src.data.historical_data_store import get_historical_store

data_loader = lambda symbol, tf, start, end: \
    get_historical_store(env="live").get_ohlcv(symbol, tf, start, end)
```

**Q19: In-process CLI invocation**

**YES**, preflight calls tools in-process (no subprocess).

**Method** (`src/backtest/runtime/preflight.py:689-692`):
```python
sync_result = _run_auto_sync(
    pairs_to_sync=failed_pairs,
    auto_sync_config=auto_sync_config,
)
```

**Internal** (`_run_auto_sync`):
```python
from src.tools.data_tools import sync_range_tool, fill_gaps_tool

# Direct Python function calls
result = sync_range_tool(symbol, tf, start, end, env)
# Returns ToolResult object
```

**NO subprocess.run()** — pure Python API.

**Q20: Heal loop**

**YES**, implemented in preflight.

**Location**: `src/backtest/runtime/preflight.py:685-721`

**Loop**:
```python
max_attempts = auto_sync_config.max_attempts  # Default: 3
attempt = 0

while failed_pairs and attempt < max_attempts:
    attempt += 1
    sync_result = _run_auto_sync(pairs_to_sync=failed_pairs, config=auto_sync_config)
    
    # Re-validate after sync
    tf_results, failed_pairs = _validate_all_pairs(...)
    
    if not failed_pairs:
        break  # Success - all pairs now valid
```

**Stop conditions**:
1. All pairs pass → exit with `PreflightStatus.PASSED`
2. Max attempts reached → exit with `PreflightStatus.FAILED`
3. Sync tool returns `success=False` → exit with `PreflightStatus.FAILED`

**Q21-Q22: Expansion policy, historical limits**

**NO EXPLICIT CAP** in current code.

**Implicit limits**:
- DuckDB storage capacity
- API rate limits (enforced by `rate_limiter.py`)
- Bybit historical data availability (varies by symbol)

**NO checks for**:
- Max warmup bars allowed
- Earliest allowed date (exchange launch date)
- Historical API limit (Bybit-specific)

**Risk**: Misconfigured IdeaCard with `warmup_bars: 10000` could request years of data.

**Recommendation**: Add validation:
```python
MAX_WARMUP_BARS = 1000  # ~2 weeks on 15m
EARLIEST_BYBIT_DATE = datetime(2018, 1, 1)  # Bybit launch

if warmup_bars > MAX_WARMUP_BARS:
    raise ValueError(f"Warmup {warmup_bars} exceeds max {MAX_WARMUP_BARS}")
if extended_start < EARLIEST_BYBIT_DATE:
    raise ValueError(f"Start {extended_start} before exchange launch {EARLIEST_BYBIT_DATE}")
```

---

## Testing & Validation

### Q23-Q30: Test Coverage, Smoke Tests, Issue Reproduction

**Q23: Existing tests around warmup/windowing**

**NO pytest files** (project rule: CLI-only validation).

**Validation methods**:
```bash
# Warmup validation
python trade_cli.py backtest preflight --idea-card test__stress_indicator_dense__BTCUSDT_5m --start 2024-11-01 --end 2024-11-02

# Integration tests
python trade_cli.py backtest run --smoke full

# Specific validation
python trade_cli.py backtest run --idea-card test__stress_indicator_dense__BTCUSDT_5m --start 2024-11-01 --end 2024-11-02
```

**Test IdeaCards** in `configs/idea_cards/_validation/`:
- `test__batch1_close_single__BTCUSDT_15m` (100 bars warmup)
- `test__stress_indicator_dense__BTCUSDT_5m` (200 bars exec, 150 bars HTF)
- `test__system_validation_1year__BTCUSDT_1h` (large window)

**NO unit tests** for `compute_warmup_requirements()` — validated through CLI.

**Q24: Test mocking**

**NO MOCKS** (CLI-only validation philosophy).

**Data sources**:
- **Real DuckDB**: All validation against `market_data_live.duckdb`
- **Smoke tests**: Use pre-synced demo data
- **Metadata smoke**: Synthetic in-memory data (no DuckDB)

**Example**:
```bash
# Uses real DuckDB
python trade_cli.py backtest run --idea-card test__stress_indicator_dense__BTCUSDT_5m

# Uses synthetic data (no DB)
python trade_cli.py backtest metadata-smoke
```

**Preflight uses real DuckDB reads** — no mocking layer exists.

**Q25: Issue reproduction**

**Mismatch occurred in BOTH** single-TF and multi-TF (before fix).

**Fastest repro** (before P0 fix):
```bash
# Multi-TF with explicit warmup:200
python trade_cli.py backtest run \
  --idea-card test__batch6_hlc_multi__BTCUSDT_15m \
  --start 2024-11-01 --end 2024-11-02

# Showed:
# [PREFLIGHT] Warmup: 200 bars
# [ENGINE]    warm-up: 100 bars  ← MISMATCH
```

**After fix**: All tests show synchronized warmup.

**Q26: Smoke test behavior**

**YES**, smoke tests include preflight.

**Smoke modes**:
```bash
--smoke full           # Data + trading + diagnostics (uses demo DuckDB)
--smoke data           # Data builder only
--smoke data_extensive # Clean DB → build → fill → validate
--smoke orders         # All order types (demo trading)
--smoke live_check     # Live API connectivity (opt-in, needs live keys)
```

**Preflight in smoke**:
- Validates data coverage with warmup
- Uses `auto_sync_missing=False` (fail fast)
- Expects data pre-synced before test runs
- Logs warmup requirements and coverage

**Data sources**:
- `--smoke full/orders`: Real DuckDB (demo environment)
- `backtest metadata-smoke`: Synthetic (no DuckDB, in-memory only)

**Example**:
```bash
# Smoke test output
[PREFLIGHT] Running Data Preflight Gate...
  Warmup: 200 bars (1000 minutes)
  DB Coverage: 12,673 bars
  Status: PASSED
```

**Note**: `--smoke data_extensive` rebuilds entire DB from scratch:
1. Delete all data
2. Build sparse history
3. Fill gaps
4. Sync to current
5. Validate

---

## Known Issues

### Critical Issues Identified in Audit

**1. YAML Loader Path - BROKEN**
- **Issue**: `load_system_config()` does NOT populate `warmup_bars_by_role`
- **Impact**: Legacy YAML-based SystemConfigs trigger `MISSING_WARMUP_CONFIG`
- **Location**: `src/backtest/system_config.py:852`
- **Status**: 🔴 Blocking legacy YAML usage
- **Fix Required**: Wire warmup computation into YAML loader

**2. Audit Tool Path - BROKEN**
- **Issue**: `audit_snapshot_plumbing_parity.py` does NOT populate `warmup_bars_by_role`
- **Impact**: Snapshot plumbing parity audit fails on engine init
- **Location**: `src/backtest/audit_snapshot_plumbing_parity.py:541`
- **Status**: 🔴 Blocking snapshot audit
- **Fix Required**: Add warmup computation before SystemConfig creation

**3. No Max Expansion Policy**
- **Issue**: No cap on warmup bars or earliest date
- **Impact**: Misconfigured IdeaCard could request years of data
- **Example**: `warmup_bars: 100000` would attempt to fetch massive history
- **Status**: ⚠️ Potential performance/cost issue
- **Fix Required**: Add `MAX_WARMUP_BARS` and `EARLIEST_ALLOWED_DATE` validation

**4. No Exchange Historical Limit Handling**
- **Issue**: No special case for "exchange cannot provide older history"
- **Impact**: Fails with generic "No data available" vs informative message
- **Example**: Requesting data before Bybit launch date
- **Status**: ⚠️ Poor UX on invalid date ranges
- **Fix Required**: Check against exchange-specific earliest dates

**5. No Centralized Window Planner**
- **Issue**: Range expansion logic duplicated across preflight/engine
- **Impact**: Risk of divergence if formulas updated in one place
- **Status**: ⚠️ Maintainability concern
- **Fix Required**: Create `compute_data_window(window, warmup_by_role, tf_mapping)` utility

---

## Architecture Diagrams

### Warmup Data Flow (Current State)

```
┌─────────────┐
│  IdeaCard   │
│   (YAML)    │
└──────┬──────┘
       │
       ├─────────────────────┬────────────────────┐
       │                     │                    │
       v                     v                    v
┌─────────────────┐   ┌─────────────┐   ┌────────────────┐
│ compute_warmup  │   │  Preflight  │   │     Engine     │
│  _requirements  │   │  (direct)   │   │   (indirect)   │
└────────┬────────┘   └──────┬──────┘   └────────┬───────┘
         │                   │                    │
         │                   │                    │
         v                   v                    v
┌─────────────────────────────────────────────────────┐
│           WarmupRequirements                        │
│  warmup_by_role = {"exec": 200, "htf": 150}        │
└────────┬──────────────────────────────────┬────────┘
         │                                   │
         v                                   v
┌─────────────────┐                 ┌────────────────┐
│  SystemConfig   │                 │   Preflight    │
│ warmup_bars_by  │                 │   effective_   │
│     _role       │                 │  warmup_bars   │
└────────┬────────┘                 └────────┬───────┘
         │                                   │
         v                                   v
┌─────────────────┐                 ┌────────────────┐
│  Engine.prepare │                 │   validate_tf  │
│ _backtest_frame │                 │      _data     │
└────────┬────────┘                 └────────┬───────┘
         │                                   │
         v                                   v
┌─────────────────────────────────────────────────────┐
│         Data Fetch (DuckDB)                         │
│  extended_start = requested_start - warmup_span     │
└─────────────────────────────────────────────────────┘
```

### Warmup Computation Formula

```
Per TF role:
───────────────────────────────────────────────────────
effective_warmup = max(
    ├─ max(spec.warmup_bars for spec in tf_config.feature_specs)
    │   └─ Indicator-derived (e.g., EMA(20) → 60 bars)
    ├─ tf_config.warmup_bars
    │   └─ Explicit user declaration in IdeaCard
    └─ idea_card.bars_history_required
        └─ Global minimum for all TFs
)

Time conversion:
───────────────────────────────────────────────────────
warmup_span = warmup_bars × tf_duration
extended_start = requested_start - warmup_span

Example:
  warmup_bars = 200
  tf = 15m
  requested_start = 2024-11-01 00:00
  ───────────────────────────────────────
  warmup_span = 200 × 15min = 3000min = 50h
  extended_start = 2024-10-29 22:00
```

---

## Recommendations

### Immediate (P1)

1. **Fix YAML loader path**: Wire warmup computation into `load_system_config()`
2. **Fix audit tool path**: Add warmup computation to snapshot plumbing parity
3. **Add max warmup validation**: Cap at 1000 bars with override flag
4. **Add earliest date validation**: Check against exchange launch dates

### Short-term (P2)

5. **Create window planner utility**: Centralize range expansion logic
6. **Enhanced logging**: Log warmup computation breakdown (feature/explicit/history)
7. **Warmup audit tool**: CLI command to show warmup for all IdeaCards
8. **Preflight enhancement**: Log actual data fetched vs required warmup

### Long-term (P3)

9. **Warmup metadata**: Export warmup provenance to manifest
10. **Smart warmup**: Auto-adjust for indicator complexity
11. **Warmup profiling**: Measure actual bars needed for stability
12. **Exchange-aware limits**: Per-exchange historical data constraints

---

## Appendix: Key Code Locations

### Core Functions

| Function | File | Line | Purpose |
|----------|------|------|---------|
| `compute_warmup_requirements` | `execution_validation.py` | 421 | Canonical warmup computation |
| `calculate_warmup_start` | `runtime/preflight.py` | 255 | Time-based warmup offset |
| `validate_tf_data` | `runtime/preflight.py` | 265 | Preflight validation |
| `prepare_backtest_frame` | `engine.py` | 423 | Single-TF data loading |
| `prepare_multi_tf_frames` | `engine.py` | 625 | Multi-TF data loading |
| `run_preflight_gate` | `runtime/preflight.py` | 626 | Preflight orchestration |

### Data Structures

| Class | File | Line | Purpose |
|-------|------|------|---------|
| `WarmupRequirements` | `execution_validation.py` | 399 | Warmup computation result |
| `SystemConfig` | `system_config.py` | 452 | Engine configuration |
| `PreparedFrame` | `engine.py` | 93 | Single-TF prepared data |
| `MultiTFPreparedFrames` | `engine.py` | 115 | Multi-TF prepared data |
| `TFPreflightResult` | `runtime/preflight.py` | 115 | Per-TF validation result |
| `PreflightReport` | `runtime/preflight.py` | 185 | Overall preflight result |

### Configuration

| Field | Location | Type | Purpose |
|-------|----------|------|---------|
| `warmup_bars_by_role` | `SystemConfig` | `Dict[str, int]` | Canonical warmup per TF |
| `warmup_bars` | `TFConfig` | `int` | Explicit per-TF warmup |
| `bars_history_required` | `IdeaCard` | `int` | Global minimum warmup |
| `effective_warmup_bars` | `TFConfig` (property) | `int` | Computed effective warmup |

---

**Document Version**: 1.0  
**Last Updated**: December 17, 2024  
**Status**: Authoritative (post-P0 fix)  
**Next Review**: After YAML loader fix

