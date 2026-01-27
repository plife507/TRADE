# Synthetic Market Conditions Design

**Purpose**: Generate synthetic data that emulates real market conditions for:
1. Baseline validation of Plays (expected behavior under known conditions)
2. Error detection (edge cases, boundary conditions)
3. Regression testing (deterministic, reproducible)

---

## Pattern Categories

### 1. TREND PATTERNS

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `trend_up_clean` | Steady uptrend with small pullbacks (10-20%) | Test long entry/exit signals |
| `trend_down_clean` | Steady downtrend with small rallies | Test short entry/exit signals |
| `trend_grinding` | Slow, low-volatility trend | Test patience/holding behavior |
| `trend_parabolic` | Accelerating trend (blow-off) | Test profit-taking, trailing stops |
| `trend_exhaustion` | Strong trend that fails and reverses | Test reversal detection, stop losses |
| `trend_stairs` | Step pattern: trend, pause, trend, pause | Test trend continuation logic |

### 2. RANGE PATTERNS

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `range_tight` | Low volatility squeeze (Bollinger squeeze) | Test breakout anticipation |
| `range_wide` | High volatility but no direction | Test false signal filtering |
| `range_ascending` | Higher lows, flat resistance | Test ascending triangle breakout |
| `range_descending` | Flat support, lower highs | Test descending triangle breakdown |
| `range_symmetric` | Clean horizontal channel | Test support/resistance detection |

### 3. REVERSAL PATTERNS

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `reversal_v_bottom` | Sharp V-bottom recovery | Test bottom detection, aggressive entries |
| `reversal_v_top` | Sharp V-top crash | Test top detection, exit speed |
| `reversal_double_bottom` | Classic W pattern | Test pattern recognition |
| `reversal_double_top` | Classic M pattern | Test pattern recognition |
| `reversal_rounded` | Gradual U-shaped reversal | Test slow reversal detection |

### 4. BREAKOUT PATTERNS

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `breakout_clean` | Clear breakout with strong follow-through | Test breakout entry signals |
| `breakout_false` | Fakeout that reverses (stop hunt) | Test false breakout filtering |
| `breakout_retest` | Breakout, pullback to level, continuation | Test pullback entries |
| `breakout_failed` | Breakout attempt that fails completely | Test exit on failure |

### 5. VOLATILITY PATTERNS

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `vol_squeeze_expand` | Low vol squeeze then expansion | Test squeeze detection |
| `vol_spike_recover` | Flash crash with V-recovery | Test panic behavior, holding |
| `vol_spike_continue` | Flash crash that continues down | Test stop loss execution |
| `vol_decay` | High vol settling to low vol | Test position sizing adjustment |

### 6. LIQUIDITY/MANIPULATION PATTERNS

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `liquidity_hunt_lows` | Sweep below support then rally | Test stop placement |
| `liquidity_hunt_highs` | Sweep above resistance then drop | Test entry timing |
| `choppy_whipsaw` | Rapid direction changes, no trend | Test signal filtering |
| `accumulation` | Low vol drift up (smart money buying) | Test accumulation detection |
| `distribution` | Low vol drift down (smart money selling) | Test distribution detection |

### 7. MULTI-TIMEFRAME PATTERNS

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `mtf_aligned_bull` | All TFs trending up | Test aligned entry confidence |
| `mtf_aligned_bear` | All TFs trending down | Test aligned short confidence |
| `mtf_pullback_bull` | Higher TF up, lower TF pulling back | Test pullback entries |
| `mtf_pullback_bear` | Higher TF down, lower TF rallying | Test rally fade entries |
| `mtf_divergent` | Higher TF range, lower TF trending | Test conflicting signals |

---

## Pattern Parameters

Each pattern supports configuration:

```python
@dataclass
class PatternConfig:
    # Core parameters
    trend_magnitude: float = 0.20      # 20% price move for trends
    pullback_depth: float = 0.30       # 30% retracement on pullbacks
    volatility_base: float = 0.02      # 2% daily volatility
    volatility_spike: float = 0.10     # 10% for spike events

    # Timing parameters
    trend_bars: int = 100              # Bars for trend phase
    range_bars: int = 50               # Bars for range phase
    reversal_bars: int = 20            # Bars for reversal formation

    # Noise parameters
    noise_level: float = 0.3           # 0-1 scale for random noise

    # Multi-TF parameters
    htf_alignment: float = 1.0         # 1.0 = fully aligned, 0 = independent
```

---

## Implementation Architecture

### Phase Structure

Each pattern is built from composable phases:

```python
class Phase(Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    SPIKE_UP = "spike_up"
    SPIKE_DOWN = "spike_down"
    RECOVERY = "recovery"
    SQUEEZE = "squeeze"
    EXPANSION = "expansion"

def generate_phase(
    phase: Phase,
    n_bars: int,
    start_price: float,
    config: PatternConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate price array for a single phase."""
    ...
```

### Pattern Composition

Patterns are sequences of phases:

```python
PATTERN_SEQUENCES = {
    "trend_up_clean": [
        (Phase.TREND_UP, 0.7),      # 70% of bars trending
        (Phase.RANGE, 0.15),         # 15% consolidation
        (Phase.TREND_UP, 0.15),      # 15% continuation
    ],
    "breakout_false": [
        (Phase.RANGE, 0.5),          # 50% building range
        (Phase.SPIKE_UP, 0.1),       # 10% fake breakout
        (Phase.SPIKE_DOWN, 0.2),     # 20% reversal below range
        (Phase.RECOVERY, 0.2),       # 20% back to range
    ],
    "vol_squeeze_expand": [
        (Phase.SQUEEZE, 0.6),        # 60% tightening volatility
        (Phase.EXPANSION, 0.2),      # 20% volatility expansion
        (Phase.TREND_UP, 0.2),       # 20% directional move
    ],
}
```

### Multi-TF Generation

For multi-timeframe patterns, generate higher TF first then derive lower TFs:

```python
def generate_mtf_pattern(
    pattern: str,
    timeframes: list[str],
    bars_slowest_tf: int,
    config: PatternConfig,
    seed: int,
) -> dict[str, pd.DataFrame]:
    """
    Generate aligned multi-TF data.

    1. Generate slowest TF with pattern
    2. Interpolate to faster TFs with added noise
    3. Ensure OHLCV constraints hold
    """
    ...
```

---

## Validation Play Templates

Each pattern category has a validation Play template:

### Template: Trend Pattern Validation

```yaml
version: "3.0.0"
name: "V_SYNTH_trend_up_clean"
description: "Validate long signals fire on clean uptrend"

# Synthetic data config embedded in Play
synthetic:
  pattern: "trend_up_clean"
  bars: 500
  seed: 42
  config:
    trend_magnitude: 0.25
    pullback_depth: 0.20

symbol: "BTCUSDT"
timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "4h"
  exec: "low_tf"

# Expected behavior assertions
expected:
  min_trades: 3
  max_trades: 10
  win_rate_min: 0.5
  pnl_direction: positive  # Must be profitable on uptrend
```

### Template: False Breakout Validation

```yaml
version: "3.0.0"
name: "V_SYNTH_breakout_false"
description: "Validate strategy handles false breakouts"

synthetic:
  pattern: "breakout_false"
  bars: 300
  seed: 42

expected:
  # Should NOT enter on fake breakout, or should exit quickly
  max_drawdown_pct: 5.0
  # If enters, must exit before reversal completes
  avg_bars_in_trade_max: 20
```

---

## Error Detection Scenarios

### Edge Cases to Test

| Scenario | Pattern | What to Verify |
|----------|---------|----------------|
| Gap through stop | `vol_spike_continue` | Stop executes at gap price, not stop price |
| Rapid reversal | `reversal_v_top` | Exit triggers fast enough |
| No signals | `range_tight` | System waits, doesn't force trades |
| Many signals | `choppy_whipsaw` | System filters, doesn't overtrade |
| Trend exhaustion | `trend_exhaustion` | Recognizes reversal, exits |
| False breakout | `breakout_false` | Doesn't chase, or exits quickly |
| Liquidity hunt | `liquidity_hunt_lows` | Stop not hit, or re-enters |

### Boundary Conditions

```python
EDGE_CASE_SEEDS = {
    "exactly_at_threshold": 100,      # Price exactly at indicator threshold
    "one_tick_above": 101,            # Just above threshold
    "one_tick_below": 102,            # Just below threshold
    "zero_volume_bar": 103,           # Test volume=0 handling
    "identical_ohlc": 104,            # Doji with OHLC all equal
    "max_wick": 105,                  # Extreme wick ratios
}
```

---

## Usage Examples

### Run Single Pattern Validation

```bash
# Run trend validation Play
python trade_cli.py backtest run --play V_SYNTH_trend_up_clean --synthetic

# Run with specific seed
python trade_cli.py backtest run --play V_SYNTH_trend_up_clean --synthetic --synthetic-seed 123
```

### Run Full Pattern Suite

```bash
# Run all synthetic pattern validations
python trade_cli.py forge validate-patterns

# Output:
# Pattern                  | Result | Trades | PnL     | Notes
# -------------------------|--------|--------|---------|------------------
# trend_up_clean           | PASS   | 5      | +12.3%  | Expected: positive
# trend_down_clean         | PASS   | 4      | +8.7%   | Expected: positive (short)
# breakout_false           | PASS   | 1      | -1.2%   | Expected: small loss
# choppy_whipsaw           | PASS   | 0      | 0%      | Expected: no trades
```

### Generate Custom Pattern

```python
from src.forge.validation import generate_synthetic_candles, PatternConfig

config = PatternConfig(
    trend_magnitude=0.30,    # 30% trend move
    volatility_base=0.03,    # 3% daily vol
)

candles = generate_synthetic_candles(
    pattern="trend_up_clean",
    config=config,
    bars_per_tf=500,
    seed=42,
)
```

---

## Implementation Phases

### Phase 1: Core Patterns (MVP)
- [ ] `trend_up_clean`, `trend_down_clean`
- [ ] `range_tight`, `range_wide`
- [ ] `breakout_clean`, `breakout_false`
- [ ] `vol_squeeze_expand`, `vol_spike_recover`
- [ ] `choppy_whipsaw`

### Phase 2: Advanced Patterns
- [ ] `reversal_*` patterns
- [ ] `liquidity_hunt_*` patterns
- [ ] `accumulation`, `distribution`
- [ ] `trend_exhaustion`, `trend_parabolic`

### Phase 3: Multi-TF Patterns
- [ ] `mtf_aligned_*` patterns
- [ ] `mtf_pullback_*` patterns
- [ ] `mtf_divergent`

### Phase 4: Validation Infrastructure
- [ ] Play templates for each pattern
- [ ] Expected behavior assertions
- [ ] `forge validate-patterns` CLI command
- [ ] Regression test suite

---

## File Locations

| Component | Path |
|-----------|------|
| Pattern generators | `src/forge/validation/synthetic_data.py` |
| Pattern configs | `src/forge/validation/pattern_config.py` |
| Validation Plays | `tests/synthetic/plays/` |
| CLI integration | `src/cli/menus/forge_menu.py` |
