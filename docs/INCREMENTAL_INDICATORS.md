# Incremental Indicators for Live Trading

## Overview

The incremental indicator system provides O(1) per-bar updates for common technical indicators used in live trading. Instead of recomputing the entire indicator array on each new candle (O(n)), these implementations maintain internal state that allows constant-time updates.

**Location:** `src/indicators/incremental.py`

**Supported Indicators:**
| Indicator | Class | Complexity | State Size |
|-----------|-------|------------|------------|
| EMA | `IncrementalEMA` | O(1) | 3 floats |
| SMA | `IncrementalSMA` | O(1) | Ring buffer (n floats) |
| RSI | `IncrementalRSI` | O(1) | 5 floats + warmup list |
| ATR | `IncrementalATR` | O(1) | 3 floats + warmup list |
| MACD | `IncrementalMACD` | O(1) | 3 EMA instances |
| BBands | `IncrementalBBands` | O(1) | Ring buffer + 2 floats |

---

## Quick Start

```python
from src.indicators import (
    IncrementalEMA,
    IncrementalSMA,
    IncrementalRSI,
    IncrementalATR,
    IncrementalMACD,
    IncrementalBBands,
    create_incremental_indicator,
    supports_incremental,
)

# Check if an indicator supports incremental computation
if supports_incremental("ema"):
    print("EMA supports O(1) updates")

# Create via factory (recommended for dynamic creation)
ema = create_incremental_indicator("ema", {"length": 20})

# Or create directly
rsi = IncrementalRSI(length=14)
```

---

## Indicator Reference

### 1. Exponential Moving Average (EMA)

**Formula:**
```
α = 2 / (length + 1)
ema = α * close + (1 - α) * ema_prev
```

**Usage:**
```python
from src.indicators import IncrementalEMA

ema = IncrementalEMA(length=20)

# Initialize with historical data (warmup)
for candle in historical_candles:
    ema.update(close=candle.close)

# Check if ready (warmup complete)
if ema.is_ready:
    print(f"EMA value: {ema.value}")

# Update with new candle in live loop
ema.update(close=new_candle.close)
current_ema = ema.value
```

**Properties:**
- `value` - Current EMA value (NaN if not ready)
- `is_ready` - True when warmup period complete (count >= length)

**Warmup:** Requires `length` bars. First EMA value is SMA of first `length` bars.

---

### 2. Simple Moving Average (SMA)

**Formula:**
```
sma = (sum of last n closes) / n
```

Uses ring buffer with running sum for O(1) updates.

**Usage:**
```python
from src.indicators import IncrementalSMA

sma = IncrementalSMA(length=20)

# Update with each bar
for candle in candles:
    sma.update(close=candle.close)

if sma.is_ready:
    print(f"SMA value: {sma.value}")
```

**Properties:**
- `value` - Current SMA value (NaN if not ready)
- `is_ready` - True when buffer has `length` values

**Memory:** O(length) for ring buffer

---

### 3. Relative Strength Index (RSI)

**Formula (Wilder's smoothing):**
```
gain = max(0, close - prev_close)
loss = max(0, prev_close - close)
avg_gain = (avg_gain_prev * (n-1) + gain) / n
avg_loss = (avg_loss_prev * (n-1) + loss) / n
rs = avg_gain / avg_loss
rsi = 100 - (100 / (1 + rs))
```

**Usage:**
```python
from src.indicators import IncrementalRSI

rsi = IncrementalRSI(length=14)  # Standard RSI period

# Initialize with history
for candle in historical_candles:
    rsi.update(close=candle.close)

# Live updates
rsi.update(close=new_close)

if rsi.is_ready:
    if rsi.value < 30:
        print("Oversold")
    elif rsi.value > 70:
        print("Overbought")
```

**Properties:**
- `value` - Current RSI (0-100 scale, NaN if not ready)
- `is_ready` - True when count > length

**Warmup:** Requires `length + 1` bars (needs first close for change calculation)

---

### 4. Average True Range (ATR)

**Formula:**
```
tr = max(high - low, |high - prev_close|, |low - prev_close|)
atr = (atr_prev * (n-1) + tr) / n  # Wilder's smoothing
```

**Usage:**
```python
from src.indicators import IncrementalATR

atr = IncrementalATR(length=14)

# ATR requires OHLC data
for candle in historical_candles:
    atr.update(
        high=candle.high,
        low=candle.low,
        close=candle.close,
    )

# Use for stop-loss calculation
if atr.is_ready:
    stop_distance = 2.0 * atr.value
    stop_loss = current_price - stop_distance
```

**Properties:**
- `value` - Current ATR value (NaN if not ready)
- `is_ready` - True when count >= length

**Note:** ATR needs high, low, close - unlike other indicators that only need close.

---

### 5. MACD (Moving Average Convergence Divergence)

**Formula:**
```
macd_line = ema_fast - ema_slow
signal = ema(macd_line, signal_length)
histogram = macd_line - signal
```

Internally uses three `IncrementalEMA` instances.

**Usage:**
```python
from src.indicators import IncrementalMACD

macd = IncrementalMACD(fast=12, slow=26, signal=9)

# Initialize
for candle in historical_candles:
    macd.update(close=candle.close)

# Access all three outputs
if macd.is_ready:
    print(f"MACD Line: {macd.value}")          # Same as macd_line
    print(f"Signal: {macd.signal_value}")
    print(f"Histogram: {macd.histogram_value}")

    # Crossover detection
    if macd.value > macd.signal_value:
        print("Bullish crossover")
```

**Properties:**
- `value` - MACD line (fast EMA - slow EMA)
- `signal_value` - Signal line (EMA of MACD line)
- `histogram_value` - Histogram (MACD - Signal)
- `is_ready` - True when signal EMA is ready

**Warmup:** Requires `slow + signal - 1` bars (26 + 9 - 1 = 34 for defaults)

---

### 6. Bollinger Bands

**Formula:**
```
middle = SMA(n)
std = sqrt(variance)  # Using Welford's online algorithm
upper = middle + k * std
lower = middle - k * std
```

Uses running sum and sum of squares for O(1) variance calculation.

**Usage:**
```python
from src.indicators import IncrementalBBands

bb = IncrementalBBands(length=20, std_dev=2.0)

# Initialize
for candle in historical_candles:
    bb.update(close=candle.close)

# Access all bands
if bb.is_ready:
    print(f"Upper: {bb.upper}")
    print(f"Middle: {bb.middle}")  # Same as bb.value
    print(f"Lower: {bb.lower}")
    print(f"Std Dev: {bb.std}")

    # Band squeeze detection
    band_width = (bb.upper - bb.lower) / bb.middle
    if band_width < 0.05:
        print("Squeeze detected!")
```

**Properties:**
- `value` - Middle band (SMA)
- `middle` - Same as value
- `upper` - Upper band (middle + k * std)
- `lower` - Lower band (middle - k * std)
- `std` - Current standard deviation
- `is_ready` - True when buffer has `length` values

---

## Factory Function

For dynamic indicator creation from Play specifications:

```python
from src.indicators import create_incremental_indicator, supports_incremental

# Check support first
indicator_type = "ema"
params = {"length": 20}

if supports_incremental(indicator_type):
    indicator = create_incremental_indicator(indicator_type, params)

    # Use the indicator
    for close in closes:
        indicator.update(close=close)

    print(f"Value: {indicator.value}")
else:
    # Fall back to vectorized computation
    print(f"{indicator_type} not supported incrementally")
```

**Supported types:** `ema`, `sma`, `rsi`, `atr`, `macd`, `bbands`

---

## Integration with LiveIndicatorCache

The `LiveIndicatorCache` automatically uses incremental computation for supported indicators:

```python
# In src/engine/adapters/live.py

class LiveIndicatorCache:
    def initialize_from_history(self, candles, indicator_specs):
        """
        Classifies indicators into incremental vs vectorized.
        Incremental indicators get O(1) updates.
        """
        for spec in indicator_specs:
            if supports_incremental(spec.indicator_type):
                # Create incremental instance
                inc_ind = create_incremental_indicator(...)
                self._incremental[name] = (inc_ind, feature)
            else:
                # Will use vectorized fallback
                self._vectorized_specs.append(spec)

    def update(self, candle):
        """
        O(1) update for incremental indicators.
        O(n) recompute only for non-incremental.
        """
        # Incremental updates (O(1) each)
        for name, (inc_ind, feature) in self._incremental.items():
            inc_ind.update(close=candle.close)
            self._indicators[name] = np.append(...)

        # Vectorized fallback (O(n) but only for non-supported)
        if self._vectorized_specs:
            self._compute_vectorized()
```

---

## Performance Comparison

| Scenario | Vectorized | Incremental | Speedup |
|----------|------------|-------------|---------|
| 100 bars, EMA(20) | 100 ops | 1 op | 100x |
| 1000 bars, RSI(14) | 1000 ops | 1 op | 1000x |
| 10000 bars, MACD | 30000 ops | 3 ops | 10000x |

**Memory:**
- Vectorized: O(n) for full history array
- Incremental: O(1) for most, O(length) for SMA/BBands

---

## Validation

Incremental indicators MUST produce identical results to pandas_ta:

```python
import numpy as np
import pandas_ta as ta
from src.indicators import IncrementalEMA

# Generate test data
prices = np.random.random(1000) * 100 + 50

# Vectorized (ground truth)
ema_vectorized = ta.ema(pd.Series(prices), length=20).values

# Incremental
ema = IncrementalEMA(length=20)
ema_incremental = []
for price in prices:
    ema.update(close=price)
    ema_incremental.append(ema.value)

# Must match within floating point tolerance
assert np.allclose(
    ema_vectorized[~np.isnan(ema_vectorized)],
    np.array(ema_incremental)[~np.isnan(ema_incremental)],
    rtol=1e-10
)
```

---

## Adding New Incremental Indicators

To add support for a new indicator:

1. **Create class** in `src/indicators/incremental.py`:
```python
@dataclass
class IncrementalNewIndicator(IncrementalIndicator):
    length: int
    _state: float = field(default=0.0, init=False)

    def update(self, close: float, **kwargs) -> None:
        # O(1) update logic
        ...

    def reset(self) -> None:
        self._state = 0.0

    @property
    def value(self) -> float:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._count >= self.length
```

2. **Add to factory** in `create_incremental_indicator()`:
```python
elif indicator_type == "newindicator":
    return IncrementalNewIndicator(length=params.get("length", 14))
```

3. **Update registry**:
```python
INCREMENTAL_INDICATORS = frozenset({
    "ema", "sma", "rsi", "atr", "macd", "bbands", "newindicator"
})
```

4. **Add exports** to `src/indicators/__init__.py`

5. **Write validation test** comparing to pandas_ta

---

## Limitations

1. **Not all indicators supported** - Complex indicators (Supertrend, Ichimoku) still use vectorized computation

2. **Warmup required** - Each indicator needs historical data to initialize state

3. **No lookback modification** - Once computed, can't change lookback period without reset

4. **Single-bar granularity** - Updates happen per closed bar, not tick-by-tick

---

## Future Work (P3)

- **Supertrend** - Requires ATR + trend state tracking
- **Stochastic** - Ring buffer for highest high/lowest low
- **ADX** - Multiple smoothed averages
- **Ichimoku** - Multiple lookback periods with different calculations
