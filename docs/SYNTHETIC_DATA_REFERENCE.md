# Synthetic Data Reference

> Best practices for using the synthetic data module in TRADE.
> Source: `src/forge/validation/synthetic_data.py`

## 1. Overview

Every Play MUST have a `synthetic:` block. The `--synthetic` CLI flag requires it and will **fail loudly** if missing. There are no default fallbacks -- this is intentional (ALL FORWARD, NO LEGACY).

Synthetic data enables:
- **Validation without DB access** -- test play logic on deterministic generated data
- **Reproducible testing** -- same seed + pattern = identical price data every time
- **Strategy-concept matching** -- pick a pattern that exercises your strategy's signals
- **CI-friendly** -- no external data dependencies

## 2. Play YAML Syntax

```yaml
synthetic:
  pattern: "range_wide"     # REQUIRED: which price pattern to generate
  bars: 500                 # REQUIRED: bars per slowest timeframe
  seed: 42                  # REQUIRED: random seed for reproducibility
  config:                   # Optional: override PatternConfig defaults
    trend_magnitude: 0.25
    pullback_depth: 0.20

expected:                   # Optional: assertions checked after backtest
  min_trades: 3
  pnl_direction: positive   # positive | negative
```

## 3. CLI Usage

```bash
# Use play's synthetic: block (required)
python trade_cli.py backtest run --play my_play --synthetic

# Override specific settings (play's block still required)
python trade_cli.py backtest run --play my_play --synthetic --synthetic-pattern trend_stairs
python trade_cli.py backtest run --play my_play --synthetic --synthetic-bars 1000 --synthetic-seed 99

# Fails if play has no synthetic: block
python trade_cli.py backtest run --play play_without_block --synthetic
# ERROR: Play 'play_without_block' has no synthetic: block.
```

Priority: CLI args override play's block. Play's block is the baseline.

## 4. Pattern Catalog (34 patterns)

### Trend (6 patterns)

| Pattern | Description | Best for |
|---------|-------------|----------|
| `trend_up_clean` | 70% up, 15% pullback, 15% continue | Trend following long |
| `trend_down_clean` | Mirror of trend_up_clean | Trend following short |
| `trend_grinding` | Slow, steady grind with small noise | Low-volatility trend |
| `trend_parabolic` | Accelerating exponential move | Momentum detection |
| `trend_exhaustion` | Trend that slows and stalls | Trend reversal detection |
| `trend_stairs` | Step-wise up: flat/up/flat/up | Breakout + consolidation |

### Range (4 patterns)

| Pattern | Description | Best for |
|---------|-------------|----------|
| `range_tight` | Narrow consolidation (low vol) | Squeeze detection, scalping |
| `range_wide` | Broad oscillation (high vol) | Mean reversion, range trading |
| `range_ascending` | Rising lows, flat highs (ascending triangle) | Breakout bias |
| `range_descending` | Flat lows, falling highs (descending triangle) | Breakdown bias |

### Reversal (4 patterns)

| Pattern | Description | Best for |
|---------|-------------|----------|
| `reversal_v_bottom` | Sharp drop then sharp recovery | V-reversal detection |
| `reversal_v_top` | Sharp rise then sharp drop | Distribution detection |
| `reversal_double_bottom` | Drop, bounce, retest low, recover | Pattern recognition |
| `reversal_double_top` | Rise, pullback, retest high, drop | Pattern recognition |

### Breakout (3 patterns)

| Pattern | Description | Best for |
|---------|-------------|----------|
| `breakout_clean` | Range then decisive break above | Breakout entry strategies |
| `breakout_false` | Range, break above, fail back into range | False breakout exits |
| `breakout_retest` | Break above, pull back to test, continue | Retest entry strategies |

### Volatility (4 patterns)

| Pattern | Description | Best for |
|---------|-------------|----------|
| `vol_squeeze_expand` | Low vol compression then expansion | Squeeze-based entries |
| `vol_spike_recover` | Sudden spike then mean reversion | Spike fade strategies |
| `vol_spike_continue` | Spike then continuation in spike direction | Momentum continuation |
| `vol_decay` | High vol decaying to low vol | Volatility contraction |

### Liquidity / Manipulation (5 patterns)

| Pattern | Description | Best for |
|---------|-------------|----------|
| `liquidity_hunt_lows` | Sweep below support then reverse up | Stop hunt detection |
| `liquidity_hunt_highs` | Sweep above resistance then reverse down | Stop hunt detection |
| `choppy_whipsaw` | Random direction changes, no trend | Strategy robustness testing |
| `accumulation` | Sideways with rising volume undertone | Accumulation phase detection |
| `distribution` | Sideways with falling volume | Distribution phase detection |

### Multi-Timeframe (4 patterns)

| Pattern | Description | Best for |
|---------|-------------|----------|
| `mtf_aligned_bull` | All TFs trending up with small waves | Multi-TF confirmation |
| `mtf_aligned_bear` | All TFs trending down with small waves | Multi-TF confirmation |
| `mtf_pullback_bull` | Higher TF up, lower TF pulling back 40-60% | Pullback entries |
| `mtf_pullback_bear` | Higher TF down, lower TF rallying 40-60% | Pullback entries |

### Legacy (4 patterns)

| Pattern | Description | Notes |
|---------|-------------|-------|
| `trending` | Up then partial down | Backwards-compatible, prefer `trend_up_clean` |
| `ranging` | Mean-reverting around base | Backwards-compatible, prefer `range_wide` |
| `volatile` | High vol with random spikes | Backwards-compatible, prefer `vol_spike_recover` |
| `multi_tf_aligned` | Layered sine waves | Backwards-compatible, prefer `mtf_aligned_bull` |

## 5. Concept-to-Pattern Mapping

| Strategy Concept | Recommended Patterns | Avoid |
|-----------------|---------------------|-------|
| **Mean reversion** | `range_wide`, `range_tight`, `vol_squeeze_expand` | `trend_up_clean` (no reversion) |
| **Trend following** | `trend_up_clean`, `trend_down_clean`, `trend_stairs` | `choppy_whipsaw` (no trend) |
| **Breakout** | `breakout_clean`, `breakout_retest`, `vol_squeeze_expand` | `range_tight` (no breakout) |
| **Scalping** | `range_tight`, `range_wide`, `choppy_whipsaw` | `trend_parabolic` (one-way) |
| **Range trading** | `range_tight`, `range_wide`, `range_ascending` | `trend_grinding` (no range) |
| **Reversal** | `reversal_v_bottom`, `reversal_double_bottom` | `trend_up_clean` (no reversal) |
| **Multi-TF** | `mtf_aligned_bull`, `mtf_pullback_bull` | `choppy_whipsaw` (random) |

For **short** strategies, use the corresponding down/bear patterns (e.g., `trend_down_clean` instead of `trend_up_clean`).

For **long_short** strategies, use patterns with both directions: `range_wide`, `choppy_whipsaw`, `reversal_v_bottom`.

## 6. PatternConfig Overrides

Override defaults via the `config:` block in the play's `synthetic:` section:

```yaml
synthetic:
  pattern: "trend_up_clean"
  bars: 500
  seed: 42
  config:
    trend_magnitude: 0.25    # Default: 0.20 (20% price move)
    pullback_depth: 0.20     # Default: 0.30 (30% retracement)
    noise_level: 0.5         # Default: 0.3 (0-1 scale)
```

### All config parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trend_magnitude` | 0.20 | Total price move as fraction (0.20 = 20%) |
| `pullback_depth` | 0.30 | Pullback as fraction of trend move |
| `stairs_steps` | 4 | Number of steps in `trend_stairs` |
| `volatility_base` | 0.02 | Base daily volatility (2%) |
| `volatility_spike` | 0.10 | Spike volatility (10%) |
| `volatility_squeeze` | 0.005 | Squeeze period volatility (0.5%) |
| `range_width` | 0.08 | Range width as fraction (8%) |
| `triangle_slope` | 0.001 | Slope for ascending/descending triangles |
| `trend_fraction` | 0.6 | Fraction of bars in trend phase |
| `range_fraction` | 0.3 | Fraction of bars in range phase |
| `spike_fraction` | 0.1 | Fraction of bars in spike phase |
| `noise_level` | 0.3 | Random noise overlay (0-1 scale) |
| `hunt_depth` | 0.02 | Liquidity hunt depth (2% beyond level) |
| `hunt_recovery` | 0.8 | Recovery after hunt (80%) |

## 7. Multi-TF Bar Dilation

When using 3 timeframes with `bars_per_tf=500`, the lowest TF gets approximately:
- `500 * (highest_tf_minutes / lowest_tf_minutes)` bars

Example: `low_tf=3m`, `high_tf=1h` with `bars=500`:
- 1h = 500 bars
- 3m = 500 * 20 = 10,000 bars on low_tf

**Important**: This dilation dilutes patterns on the lower timeframe. A structure signal that occurs once per 100 bars on 1h occurs ~once per 2000 bars on 3m. Compensate with:
- `near_pct` instead of strict `<`/`>` for structure comparisons
- Wider `near_pct` values on dilated data
- More bars if testing structure-heavy strategies

## 8. Deterministic Hashing

Every synthetic run produces a `data_hash` (SHA256[:12]) for verification:

```
[SYNTHETIC] Data hash: a3f2b1c4d5e6
```

Same `pattern + bars + seed + timeframes` always produces the same hash. Use this to verify reproducibility.

## 9. Common Pitfalls

### Zero trades on synthetic data
- Pattern doesn't match strategy concept (e.g., trend_following on `range_tight`)
- Conditions too strict -- use `near_pct` with wider tolerance
- Warmup consuming too many bars -- increase `bars`
- Multi-TF dilation making patterns invisible on exec TF

### Play without synthetic block
- `--synthetic` will fail with clear error message
- Add a `synthetic:` block before testing

### Pattern choice
- Don't use `trending` (legacy) -- use `trend_up_clean` or `trend_down_clean`
- Don't use `choppy_whipsaw` for trend strategies -- no trend signal possible
- For `long_short` plays, pick patterns with both up and down movement

### Config overrides
- `trend_magnitude: 0.25` means 25% move, not 0.25% -- these are fractions, not percentages
- `noise_level` above 0.5 may obscure pattern signals
- Low `bars` (< 200) may not generate enough signals after warmup

## 10. Programmatic API

```python
from src.forge.validation import generate_synthetic_candles
from src.forge.validation.synthetic_data import PatternType, PatternConfig

candles = generate_synthetic_candles(
    symbol="BTCUSDT",
    timeframes=["1m", "15m", "1h"],
    bars_per_tf=500,
    seed=42,
    pattern="trend_up_clean",
    config=PatternConfig(trend_magnitude=0.30),
)

# Access data
df_15m = candles.get_tf("15m")  # DataFrame with open/high/low/close/volume/timestamp
print(candles.data_hash)         # Deterministic hash
print(candles.bar_counts)        # {"1m": 30000, "15m": 2000, "1h": 500}
```
