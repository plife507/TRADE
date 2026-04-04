# TradingView Parity Verification System

## Context

TRADE's 13 incremental structure detectors are validated via synthetic data + vectorized Python reference implementations (G5 gate). Both sides were written by the same author — if both share a conceptual bug, parity passes but the detection is wrong. **TradingView provides an independent ground truth**: Pine Script implementations running on real SOLUSDT charts, with outputs extracted via the [tradesdontlie/tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp) bridge.

SOLUSDT (Bybit USDT perpetual) is available on TradingView, so OHLCV data is 1:1 with DuckDB.

## Architecture

```
DuckDB (SOLUSDT 1h)                    TradingView Desktop (SOLUSDT 1h)
        |                                          |
        v                                          v
  run_detector_batch()                    Pine Script detector
  (13 incremental detectors)             (injected via `tv` CLI)
        |                                          |
        v                                          v
  dict[str, np.ndarray]                  `tv` CLI JSON output
        |                                          |
        +---------> Comparison Engine <------------+
                   (timestamp-aligned)
                          |
                          v
                   TVParityReport
```

**Key insight**: The tradesdontlie/tradingview-mcp exposes every MCP tool as a `tv` CLI command with JSON output. Python calls it via subprocess — no MCP client library needed. This keeps the validation fully automated and runnable via `python trade_cli.py validate module --module tv-parity`.

## Communication Layer: `tv` CLI (not MCP protocol)

The MCP bridge provides a `tv` CLI that mirrors all 78 MCP tools:

```bash
tv chart_set_symbol --symbol SOLUSDT.P       # Navigate chart
tv chart_set_timeframe --timeframe 60        # Set to 1h
tv data_get_ohlcv | jq '.bars'               # Extract OHLCV (JSON)
tv pine_set_source --source "$(cat swing.pine)"  # Inject Pine Script
tv pine_smart_compile                        # Compile
tv data_get_study_values                     # Read plotted values (JSON)
tv pine_get_errors                           # Debug compilation
tv capture_screenshot --path /tmp/debug.png  # Visual debug
```

Python wraps these via `subprocess.run()` with JSON parsing. No async needed.

## File Layout

```
src/forge/audits/tv_parity/
    __init__.py
    bridge.py              # TVBridge: subprocess wrapper around `tv` CLI
    ohlcv_alignment.py     # OHLCV parity check (DuckDB vs TradingView)
    comparison.py          # 4 comparison strategies (numeric, event, zone, level)
    runner.py              # Orchestrates full audit, calls run_detector_batch()
    report.py              # TVParityReport dataclass + Rich console + JSON
    pine_scripts/
        rolling_window.pine
        swing.pine
        trend.pine
        market_structure.pine
        zone.pine
        fibonacci.pine
        derived_zone.pine
        displacement.pine
        fair_value_gap.pine
        order_block.pine
        liquidity_zones.pine
        premium_discount.pine
        breaker_block.pine
```

## Module Design

### `bridge.py` — TV CLI Wrapper

```python
class TVBridge:
    """Wraps `tv` CLI commands via subprocess."""

    def is_available(self) -> bool:
        """Run `tv tv_health_check`, return True if TV Desktop responds."""

    def set_chart(self, symbol: str, timeframe_minutes: int) -> None:
        """chart_set_symbol + chart_set_timeframe."""

    def get_ohlcv(self) -> pd.DataFrame:
        """data_get_ohlcv -> DataFrame with timestamp, O, H, L, C, V."""

    def inject_pine(self, source: str) -> tuple[bool, str]:
        """pine_set_source + pine_smart_compile. Returns (success, error_msg)."""

    def get_study_values(self) -> dict[str, list[float]]:
        """data_get_study_values -> {plot_name: [values]}."""

    def get_pine_boxes(self) -> list[dict]:
        """data_get_pine_boxes -> [{left_time, right_time, top, bottom}]."""

    def remove_indicator(self) -> None:
        """chart_manage_indicator remove last."""

    def screenshot(self, path: str) -> None:
        """capture_screenshot."""

    def _run(self, cmd: list[str], timeout: int = 30) -> dict:
        """subprocess.run(['tv', ...]), parse JSON, raise on error."""
```

**Graceful degradation**: If `is_available()` returns False, the entire module returns SKIP.

### `ohlcv_alignment.py` — Data Foundation

```python
@dataclass
class AlignmentResult:
    matched_bars: int
    total_trade_bars: int
    total_tv_bars: int
    max_price_diff: float
    common_timestamps: list[int]   # epoch ms — the intersection
    mismatches: list[dict]

def align_ohlcv(trade_df: pd.DataFrame, tv_df: pd.DataFrame,
                tolerance: float = 1e-4) -> AlignmentResult:
    """Inner join on timestamp. Reports price discrepancies."""
```

Uses existing `load_real_ohlcv("SOLUSDT", timeframe)` from `src/forge/audits/vectorized_references/data_generators.py` for the TRADE side. TV side from `bridge.get_ohlcv()`.

### `comparison.py` — Four Strategies

| Strategy | Used For | Tolerance |
|----------|----------|-----------|
| `compare_numeric` | rolling_window value, trend direction/strength, zone state | abs 1e-4 |
| `compare_events` | bos_this_bar, choch_this_bar, is_displacement, new_this_bar, sweep_this_bar | exact bar match |
| `compare_levels` | fib levels, zone upper/lower, equilibrium, nearest_* levels | 0.05% relative |
| `compare_zones` | (future) box-based zone matching if needed | 0.1% relative |

All comparisons skip the first `warmup_bars` using `STRUCTURE_WARMUP_FORMULAS` from registry.

### `runner.py` — Orchestration

```python
def run_tv_parity_audit(
    symbol: str = "SOLUSDT",
    timeframe: str = "1h",
    detectors: list[str] | None = None,  # None = all 13
    warmup_skip: int = 30,
    screenshots: bool = False,
) -> TVParityAuditResult:
    """
    1. Check TV available (skip if not)
    2. Set chart to SOLUSDT / 1h
    3. Get TV OHLCV, load DuckDB OHLCV
    4. Align by timestamp -> common_timestamps
    5. For each detector:
       a. Load .pine from pine_scripts/
       b. Inject + compile (report errors if fail)
       c. Extract study values
       d. Run TRADE detector via run_detector_batch() on DuckDB OHLCV
       e. Align both sides to common_timestamps
       f. Compare each output field
       g. Remove indicator from chart
    6. Compile TVParityAuditResult
    """
```

**TRADE side**: Calls `run_detector_batch()` from `src/structures/batch_wrapper.py` — identical to what the existing G5 parity audit uses.

### CLI Integration

In `src/cli/validate.py`:

```python
# In _make_module_definitions() (~line 1564):
"tv-parity": [_gate_tv_parity],

# In MODULE_NAMES (~line 1588):
"tv-parity",
```

```python
def _gate_tv_parity() -> GateResult:
    from src.forge.audits.tv_parity.runner import run_tv_parity_audit
    result = run_tv_parity_audit()
    if not result.available:
        return GateResult(gate_id="TV1", name="TV Parity", passed=True,
                          checked=0, duration_sec=result.duration_sec,
                          detail="SKIP: TradingView Desktop not available")
    return GateResult(
        gate_id="TV1", name="TV Parity",
        passed=result.success,
        checked=result.total_detectors,
        duration_sec=result.duration_sec,
        failures=[...per-detector failures...])
```

**Not** wired into quick/standard/full tiers (requires TradingView Desktop).

## Pine Script Strategy

### Output Extraction: `plot()` + `data_get_study_values`

Every detector outputs via `plot()` calls. The `data_get_study_values` MCP tool reads all plotted series as numeric arrays. This is the most reliable extraction path — avoids the 500 drawing object limit.

```pine
// Standard template
//@version=6
indicator("trade_parity_swing", overlay=false, max_bars_back=500)

// Parameters match TRADE detector params
LEFT  = input.int(5, "Left")
RIGHT = input.int(5, "Right")

// ... algorithm ...

// Outputs — display.status_line keeps them invisible on chart
plot(high_level, "high_level", display=display.status_line)
plot(low_level,  "low_level",  display=display.status_line)
plot(direction,  "pair_direction", display=display.status_line)
```

Enum/bool values encoded as integers (1.0=bullish, -1.0=bearish, 0.0=none; 1.0=true, 0.0=false).

### Per-Detector Pine Script Approach

| # | Detector | Pine Approach | Plots | Complexity |
|---|----------|--------------|-------|------------|
| 1 | rolling_window | `ta.lowest()`/`ta.highest()` built-in | 1 | Trivial ~15 lines |
| 2 | swing | `ta.pivothigh()`/`ta.pivotlow()` built-in + pairing logic | 7 | ~120 lines |
| 3 | trend | Embed swing + HH/HL/LH/LL wave classification | 5 | ~140 lines |
| 4 | market_structure | Embed swing + BOS/CHoCH break detection | 8 | ~160 lines |
| 5 | zone | Embed swing + ATR-width zones | 4 | ~90 lines |
| 6 | fibonacci | Embed swing pairs + fib level calculation | 8 | ~90 lines |
| 7 | displacement | `ta.atr()` + body/wick ratio thresholds | 5 | ~50 lines |
| 8 | fair_value_gap | 3-candle gap + array-based tracking | 8 | ~130 lines |
| 9 | order_block | Embed swing + displacement + opposing candle | 8 | ~160 lines |
| 10 | liquidity_zones | Embed swing + cluster detection + sweep | 6 | ~140 lines |
| 11 | premium_discount | Embed swing pairs + equilibrium calculation | 5 | ~50 lines |
| 12 | derived_zone | Embed swing pairs + multi-slot fib zones | 6 | ~180 lines |
| 13 | breaker_block | Embed OB + MS + flip detection | 6 | ~200 lines |

**Dependency embedding**: Each Pine Script is self-contained. `trend.pine` includes swing logic inline. `breaker_block.pine` embeds swing + OB + MS. Code duplication is intentional — these are verification artifacts, not production code. Pine Script lacks imports.

### Bar Index Alignment

TRADE uses 0-based `bar_idx`. Pine uses absolute `bar_index`. Solution:
- Pine Scripts plot `time` (bar open timestamp in ms) alongside detection timestamps
- The comparison engine maps via the `common_timestamps` list from OHLCV alignment
- For outputs like `high_idx` (bar index of swing high), Pine plots the pivot bar's `time` instead; the comparator maps it to TRADE's bar_idx via the timestamp index

## Key Challenges and Solutions

| Challenge | Solution |
|-----------|----------|
| Bar index mismatch | Timestamp-based alignment (epoch ms inner join) |
| Warmup differences | Skip first N bars per `STRUCTURE_WARMUP_FORMULAS` |
| Visible chart limit (~300-500 bars) | Sufficient for validation; can zoom out or use higher TF |
| Pine 64-plot limit | Each detector uses 4-8 plots (well under limit) |
| Pine 500 drawing limit | Using `plot()` not drawing objects |
| Float precision (Python vs Pine) | Relative tolerance 0.05% for levels, 1e-4 absolute for numeric |
| TV Desktop not running | Graceful SKIP (not FAIL) |
| NaN handling | NaN-vs-NaN treated as match (same as G5 audit) |

## Match Rate Thresholds

- **>=95%**: PASS
- **80-95%**: WARN (investigate)
- **<80%**: FAIL (likely conceptual bug)

## MCP Server Setup

Create `.mcp.json` at project root:

```json
{
  "tradingview": {
    "command": "npx",
    "args": ["-y", "tradingview-mcp"]
  }
}
```

Prerequisites:
- TradingView Desktop installed and running
- Launch with remote debugging: `--remote-debugging-port=9222`
- Node.js installed (for npx)

## 13 Structure Detectors — Output Field Reference

### 1. rolling_window
- `value` (FLOAT) — current min/max

### 2. swing (24 fields, 7 key plots)
- `high_level`, `high_idx`, `low_level`, `low_idx` — latest confirmed pivots
- `pair_high_level`, `pair_low_level`, `pair_direction` — paired swing data

### 3. trend (5 fields)
- `direction` (INT: 1/-1/0), `strength` (INT: 0/1/2), `bars_in_trend`, `wave_count`, `last_wave_direction`

### 4. market_structure (8 key fields)
- `bias`, `bos_this_bar`, `choch_this_bar`, `bos_direction`, `choch_direction`
- `break_level_high`, `break_level_low`, `version`

### 5. zone (4 fields)
- `state` (ENUM: active/broken/none), `upper`, `lower`, `anchor_idx`

### 6. fibonacci (8+ dynamic fields)
- `level_0.382`, `level_0.5`, `level_0.618`, etc., `anchor_high`, `anchor_low`, `range`, `anchor_direction`

### 7. derived_zone (11+ per-slot fields)
- `active_count`, `any_active`, `zone0_upper`, `zone0_lower`, `zone0_state`, `source_version`

### 8. displacement (5 fields)
- `is_displacement`, `direction`, `body_atr_ratio`, `wick_ratio`, `version`

### 9. fair_value_gap (8 key fields)
- `new_this_bar`, `new_direction`, `new_upper`, `new_lower`
- `nearest_bull_upper`, `nearest_bull_lower`, `nearest_bear_upper`, `nearest_bear_lower`

### 10. order_block (8 key fields)
- `new_this_bar`, `new_direction`, `new_upper`, `new_lower`
- `nearest_bull_upper`, `nearest_bull_lower`, `nearest_bear_upper`, `nearest_bear_lower`

### 11. liquidity_zones (6 fields)
- `sweep_this_bar`, `sweep_direction`, `swept_level`
- `nearest_high_level`, `nearest_low_level`, `version`

### 12. premium_discount (5 fields)
- `equilibrium`, `premium_level`, `discount_level`, `zone`, `depth_pct`

### 13. breaker_block (6 fields)
- `new_this_bar`, `new_direction`, `new_upper`, `new_lower`
- `active_bull_count`, `active_bear_count`

## Dependency Graph

```
swing (independent)
  +-- trend
  +-- market_structure
  +-- zone
  +-- fibonacci (optional: + trend)
  +-- derived_zone
  +-- premium_discount
  +-- liquidity_zones
  +-- order_block
        +-- breaker_block (+ market_structure)

displacement (independent)
fair_value_gap (independent)
rolling_window (independent)
```

## Comparison Strategy Per Output Field

| Strategy | Fields | Comparison Method |
|----------|--------|------------------|
| NUMERIC | direction, strength, wave_count, state, version, active_count, body_atr_ratio, wick_ratio, depth_pct | Exact or abs tolerance 1e-4 |
| EVENT | bos_this_bar, choch_this_bar, is_displacement, new_this_bar, sweep_this_bar, any_mitigated_this_bar | Boolean exact match per bar |
| LEVEL | high_level, low_level, upper, lower, level_*, equilibrium, premium_level, discount_level, nearest_*, swept_level | 0.05% relative tolerance |
| TIMESTAMP | high_idx, low_idx, anchor_idx | Map via timestamp, then compare bar_idx |
