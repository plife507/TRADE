# Writing Strategies Guide

**Last Updated:** December 2025

This guide shows how to create new trading strategies for the TRADE backtest engine.

---

## Overview

Strategies are Python functions that:
- Accept a `RuntimeSnapshot` (current market state)
- Accept `params` (configuration from YAML)
- Return a `Signal` object or `None` (no action)

Strategies are registered in the strategy registry and referenced by `(strategy_id, strategy_version)` tuples.

---

## Step 1: Create Strategy File

Create a new file in `src/strategies/` (e.g., `my_strategy.py`):

```python
"""
My Custom Strategy.

Description of what this strategy does.
"""

from typing import Optional, Dict, Any

from ..backtest.runtime.types import RuntimeSnapshot
from ..core.risk_manager import Signal


# Strategy identity (stable across versions)
STRATEGY_ID = "my_strategy"
STRATEGY_DEFAULT_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "My custom trading strategy"


def my_strategy(
    snapshot: RuntimeSnapshot,
    params: Dict[str, Any],
) -> Optional[Signal]:
    """
    My custom strategy function.
    
    Args:
        snapshot: Current market state (RuntimeSnapshot)
        params: Strategy parameters from YAML config
        
    Returns:
        Signal object or None if no action
    """
    # Extract data from snapshot
    symbol = snapshot.symbol
    current_price = snapshot.bar_ltf.close
    position_side = snapshot.exchange_state.position_side
    
    # Access indicators from features
    indicators = snapshot.features_ltf.features
    
    # Example: Get custom indicators (you'll need to add these to indicators.py)
    my_indicator = indicators.get("my_indicator")
    
    # Check if we have required data
    if my_indicator is None:
        return None
    
    # Already in a position - check for exit
    if position_side is not None:
        # Exit logic here
        return None
    
    # Entry logic
    direction = None
    stop_loss = None
    take_profit = None
    
    # Get params with defaults
    my_param = params.get("my_param", 10.0)
    position_size_usd = params.get("position_size_usd", 100.0)
    
    # Your strategy logic here
    if my_indicator > my_param:
        direction = "LONG"
        stop_loss = current_price * 0.98  # 2% stop
        take_profit = current_price * 1.05  # 5% target
    elif my_indicator < -my_param:
        direction = "SHORT"
        stop_loss = current_price * 1.02
        take_profit = current_price * 0.95
    
    if direction is None:
        return None
    
    # Create and return signal
    return Signal(
        symbol=symbol,
        direction=direction,
        size_usd=position_size_usd,
        strategy=STRATEGY_ID,  # Use stable ID, not version
        confidence=1.0,
        metadata={
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "my_indicator": my_indicator,
        },
    )


# Alias for easy import
strategy = my_strategy
```

---

## Step 2: Register Strategy

Update `src/strategies/registry.py` to register your strategy in the `_register_builtin_strategies()` function:

```python
# Register built-in strategies on module load
def _register_builtin_strategies():
    """Register all built-in strategies."""
    from . import ema_rsi_atr
    register_strategy(
        strategy_id=ema_rsi_atr.STRATEGY_ID,
        strategy_version=ema_rsi_atr.STRATEGY_DEFAULT_VERSION,
        strategy_fn=ema_rsi_atr.strategy,
        description=ema_rsi_atr.STRATEGY_DESCRIPTION,
    )
    
    # Add your new strategy
    from . import my_strategy
    register_strategy(
        strategy_id=my_strategy.STRATEGY_ID,
        strategy_version=my_strategy.STRATEGY_DEFAULT_VERSION,
        strategy_fn=my_strategy.strategy,
        description=my_strategy.STRATEGY_DESCRIPTION,
    )
```

---

## Step 3: Add Indicators (if needed)

If you need custom indicators, update `src/backtest/indicators.py`:

### Update `apply_core_indicators()` function:

```python
def apply_core_indicators(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    # ... existing indicators ...
    
    # Add your custom indicator
    if "my_indicator_period" in params:
        period = params["my_indicator_period"]
        df["my_indicator"] = vendor.my_indicator(df, period=period)
    
    return df
```

### Update `REQUIRED_INDICATOR_COLUMNS` if needed:

```python
REQUIRED_INDICATOR_COLUMNS = ["ema_fast", "ema_slow", "rsi", "atr", "my_indicator"]
```

### Update `INDICATOR_PERIOD_KEYS` if your indicator has a period parameter:

```python
INDICATOR_PERIOD_KEYS = [
    "ema_fast_period",
    "ema_slow_period",
    "rsi_period",
    "atr_period",
    "my_indicator_period",  # Add your indicator period key
]
```

---

## Step 4: Create System Config YAML

Create a system config file in `src/strategies/configs/my_system.yml`:

```yaml
# System identifier (filename without .yml)
system_id: my_system
symbol: BTCUSDT          # Must be USDT-quoted (validated)
tf: 1h                   # Single timeframe

# Primary strategy instance (the one that generates signals)
primary_strategy_instance_id: entry

# Strategy instances (can have multiple)
strategies:
  - strategy_instance_id: entry
    strategy_id: my_strategy
    strategy_version: "1.0.0"
    inputs:
      symbol: BTCUSDT
      tf: 1h
    params:
      # Strategy-specific parameters
      my_param: 10.0
      position_size_usd: 100.0
    role: entry

# Time windows for backtesting
windows:
  hygiene:
    start: "2024-01-01"
    end: "2024-06-30"
  test:
    start: "2024-07-01"
    end: "2024-09-30"

# Risk profile (mode locks are auto-validated)
risk_profile:
  initial_equity: 1000.0      # Starting capital in USDT
  sizing_model: percent_equity
  risk_per_trade_pct: 1.0
  max_leverage: 2.0
  # Mode locks (defaults, validated automatically):
  # margin_mode: isolated      # Auto-validated
  # position_mode: oneway      # Auto-validated
  # quote_ccy: USDT            # Auto-validated
  # instrument_type: perp      # Auto-validated

# Risk mode: "none" (pure strategy) or "rules" (with risk manager)
risk_mode: "none"

# Data build settings (must cover window dates + warmup)
data_build:
  env: live
  period: 1Y                 # Must cover all windows
  tfs:
    - 1h                     # Single timeframe for this example
```

---

## RuntimeSnapshot Structure

Your strategy receives a `RuntimeSnapshot` with the following structure:

### Basic Fields

```python
snapshot.ts_close          # Current bar close timestamp (datetime)
snapshot.symbol            # Trading symbol (e.g., "BTCUSDT")
snapshot.ltf_tf            # Low timeframe string (e.g., "1h")
snapshot.mark_price        # Current mark price (float)
snapshot.mark_price_source # How mark was computed ("close"|"hlc3"|"ohlc4")
```

### Current Bar Data

```python
snapshot.bar_ltf           # Current LTF bar (Bar object)
snapshot.bar_ltf.open      # Open price
snapshot.bar_ltf.high      # High price
snapshot.bar_ltf.low       # Low price
snapshot.bar_ltf.close     # Close price
snapshot.bar_ltf.volume    # Trading volume
snapshot.bar_ltf.turnover  # Optional turnover value
snapshot.bar_ltf.ts_open   # Bar open timestamp
snapshot.bar_ltf.ts_close  # Bar close timestamp
```

### Exchange State

```python
snapshot.exchange_state.equity_usdt              # Total equity in USDT
snapshot.exchange_state.cash_usdt                # Available cash in USDT
snapshot.exchange_state.used_margin_usdt         # Margin in use
snapshot.exchange_state.free_margin_usdt          # Free margin
snapshot.exchange_state.available_balance_usdt   # Available balance
snapshot.exchange_state.maintenance_margin_usdt  # Maintenance margin
snapshot.exchange_state.has_position             # True if in position
snapshot.exchange_state.position_side            # "LONG", "SHORT", or None
snapshot.exchange_state.position_size_usdt       # Position size in USDT
snapshot.exchange_state.position_qty             # Position quantity
snapshot.exchange_state.position_entry_price     # Entry price
snapshot.exchange_state.unrealized_pnl_usdt      # Unrealized PnL
snapshot.exchange_state.entries_disabled         # True if entries disabled
snapshot.exchange_state.entries_disabled_reason # Reason if disabled
```

### Indicators

Indicators are accessed from the `features_ltf.features` dictionary:

```python
# Built-in indicators
snapshot.features_ltf.features["ema_fast"]  # Fast EMA
snapshot.features_ltf.features["ema_slow"]  # Slow EMA
snapshot.features_ltf.features["rsi"]        # RSI
snapshot.features_ltf.features["atr"]       # ATR

# Your custom indicators
snapshot.features_ltf.features["my_indicator"]

# Check if features are ready
snapshot.features_ltf.ready  # True if features are valid
```

### Multi-Timeframe Features (Phase 3+)

```python
snapshot.features_htf  # High timeframe features
snapshot.features_mtf  # Medium timeframe features
snapshot.features_ltf  # Low timeframe features
snapshot.tf_mapping    # Dict mapping role -> tf (htf, mtf, ltf keys)
```

---

## Signal Object

Return a `Signal` object when you want to enter a position:

```python
from ..core.risk_manager import Signal

Signal(
    symbol="BTCUSDT",           # Trading symbol
    direction="LONG",           # "LONG" or "SHORT"
    size_usd=100.0,             # Position size in USDT
    strategy="my_strategy",     # Use STRATEGY_ID, not version
    confidence=1.0,             # 0.0 to 1.0 (signal confidence)
    metadata={                  # Optional: any extra data
        "stop_loss": 40000.0,
        "take_profit": 42000.0,
        "custom_field": "value",
    },
)
```

**Important:**
- Use `STRATEGY_ID` (stable name) in the `strategy` field, not the version
- Return `None` if no action should be taken
- `size_usd` is the notional position size in USDT
- `metadata` can contain any additional data (stop loss, take profit, etc.)

---

## Quick Template

Here's a minimal template to get started:

```python
"""Minimal strategy template."""

from typing import Optional, Dict, Any
from ..backtest.runtime.types import RuntimeSnapshot
from ..core.risk_manager import Signal

STRATEGY_ID = "template"
STRATEGY_DEFAULT_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "Template strategy"

def template_strategy(
    snapshot: RuntimeSnapshot,
    params: Dict[str, Any],
) -> Optional[Signal]:
    """Template strategy."""
    # Already in position? Exit logic here
    if snapshot.exchange_state.position_side is not None:
        return None
    
    # Get current price
    price = snapshot.bar_ltf.close
    
    # Get indicators
    indicators = snapshot.features_ltf.features
    rsi = indicators.get("rsi")
    
    # Entry logic
    if rsi and rsi < 30:  # Oversold
        return Signal(
            symbol=snapshot.symbol,
            direction="LONG",
            size_usd=params.get("position_size_usd", 100.0),
            strategy=STRATEGY_ID,
            confidence=1.0,
        )
    
    return None

strategy = template_strategy
```

---

## Example: Complete Strategy

Here's a complete example based on the existing `ema_rsi_atr` strategy:

```python
"""
EMA + RSI + ATR Strategy.

A trend-following strategy that:
- Uses EMA crossover for trend direction
- RSI for confirmation (avoid overbought/oversold entries)
- ATR for stop loss and take profit distances
"""

from typing import Optional, Dict, Any
from ..backtest.runtime.types import RuntimeSnapshot
from ..core.risk_manager import Signal

STRATEGY_ID = "ema_rsi_atr"
STRATEGY_DEFAULT_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "EMA crossover + RSI filter + ATR-based TP/SL"

def ema_rsi_atr_strategy(
    snapshot: RuntimeSnapshot,
    params: Dict[str, Any],
) -> Optional[Signal]:
    """EMA + RSI + ATR strategy."""
    # Extract indicators
    indicators = snapshot.features_ltf.features
    symbol = snapshot.symbol
    current_price = snapshot.bar_ltf.close
    position_side = snapshot.exchange_state.position_side
    
    ema_fast = indicators.get("ema_fast")
    ema_slow = indicators.get("ema_slow")
    rsi = indicators.get("rsi")
    atr = indicators.get("atr")
    
    # Check if we have all required indicators
    if ema_fast is None or ema_slow is None or rsi is None or atr is None:
        return None
    
    # Get params with defaults
    rsi_overbought = params.get("rsi_overbought", 70)
    rsi_oversold = params.get("rsi_oversold", 30)
    atr_sl_mult = params.get("atr_sl_multiplier", 1.5)
    atr_tp_mult = params.get("atr_tp_multiplier", 2.0)
    position_size_usd = params.get("position_size_usd", 100.0)
    
    # Already in a position - check for exit signal
    if position_side is not None:
        # Optional: Generate exit signal on trend reversal
        # For now, rely on TP/SL for exits
        return None
    
    # Entry logic
    direction = None
    stop_loss = None
    take_profit = None
    
    # LONG signal
    if ema_fast > ema_slow and rsi < rsi_overbought:
        # Trend is up and not overbought
        direction = "LONG"
        stop_loss = current_price - (atr * atr_sl_mult)
        take_profit = current_price + (atr * atr_tp_mult)
    
    # SHORT signal
    elif ema_fast < ema_slow and rsi > rsi_oversold:
        # Trend is down and not oversold
        direction = "SHORT"
        stop_loss = current_price + (atr * atr_sl_mult)
        take_profit = current_price - (atr * atr_tp_mult)
    
    if direction is None:
        return None
    
    # Create signal with stable strategy_id
    return Signal(
        symbol=symbol,
        direction=direction,
        size_usd=position_size_usd,
        strategy=STRATEGY_ID,  # Use stable ID, not version
        confidence=1.0,
        metadata={
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_price": current_price,
            "atr": atr,
            "rsi": rsi,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
        },
    )

# Alias for easy import
strategy = ema_rsi_atr_strategy
```

---

## Testing Your Strategy

### 1. Register the Strategy

Make sure your strategy is registered in `src/strategies/registry.py`.

### 2. Create a Test Config

Create a minimal YAML config in `src/strategies/configs/` for testing.

### 3. Run via Tools

```python
from src.tools.backtest_tools import backtest_run_tool

result = backtest_run_tool(
    system_id="my_system",
    window_name="hygiene",
    write_artifacts=True,
)

if result.success:
    metrics = result.data["metrics"]
    print(f"Trades: {metrics['total_trades']}")
    print(f"Net PnL: ${metrics['net_profit']:.2f}")
```

### 4. Run via CLI

```bash
python trade_cli.py
# Backtest menu → Run Backtest → Select your system → Select window
```

---

## Best Practices

1. **Use Stable Strategy IDs**: The `strategy` field in `Signal` should use `STRATEGY_ID`, not the version string.

2. **Check Indicator Availability**: Always check if indicators are available before using them:
   ```python
   rsi = indicators.get("rsi")
   if rsi is None:
       return None
   ```

3. **Handle Position State**: Check if already in a position before generating entry signals:
   ```python
   if snapshot.exchange_state.position_side is not None:
       # Handle exit logic or return None
       return None
   ```

4. **Use Params with Defaults**: Always provide defaults when reading params:
   ```python
   my_param = params.get("my_param", 10.0)  # Default to 10.0
   ```

5. **Return None for No Action**: If conditions aren't met, return `None` instead of creating an invalid signal.

6. **Include Metadata**: Use `metadata` to pass stop loss, take profit, and other strategy-specific data.

7. **Validate Inputs**: Check that required indicators and data are available before processing.

---

## Common Patterns

### Trend Following

```python
if ema_fast > ema_slow:
    direction = "LONG"
elif ema_fast < ema_slow:
    direction = "SHORT"
```

### Mean Reversion

```python
if rsi < 30:  # Oversold
    direction = "LONG"
elif rsi > 70:  # Overbought
    direction = "SHORT"
```

### Breakout

```python
if current_price > resistance_level:
    direction = "LONG"
elif current_price < support_level:
    direction = "SHORT"
```

---

## Troubleshooting

### Strategy Not Found

**Error:** `Strategy 'my_strategy' v1.0.0 not found`

**Solution:** Make sure you've:
1. Created the strategy file in `src/strategies/`
2. Registered it in `src/strategies/registry.py`
3. Used the correct `strategy_id` and `strategy_version` in your YAML config

### Indicator Not Available

**Error:** `KeyError` or `None` when accessing indicators

**Solution:**
1. Check that the indicator is computed in `src/backtest/indicators.py`
2. Verify the indicator name matches exactly (case-sensitive)
3. Use `.get()` with a default value: `indicators.get("my_indicator")`

### Invalid Symbol

**Error:** `ValueError: Symbol 'BTCUSD' is not USDT-quoted`

**Solution:** Use USDT-quoted pairs only (e.g., `BTCUSDT`, `ETHUSDT`). The simulator validates this automatically.

---

## Reference

- **Strategy Registry**: `src/strategies/registry.py`
- **Base Strategy Interface**: `src/strategies/base.py`
- **Example Strategy**: `src/strategies/ema_rsi_atr.py`
- **Runtime Types**: `src/backtest/runtime/types.py`
- **Signal Type**: `src/core/risk_manager.py`
- **Indicators**: `src/backtest/indicators.py`
- **System Config**: `src/backtest/system_config.py`

---

## Next Steps

1. Create your strategy file
2. Register it in the registry
3. Create a system config YAML
4. Test with a small window
5. Iterate and refine

For more examples, see:
- `src/strategies/ema_rsi_atr.py` - Complete working example
- `docs/guides/CODE_EXAMPLES.md` - Additional code examples
- `docs/guides/BACKTEST_ENGINE_INTEGRATION.md` - Backtest engine details



