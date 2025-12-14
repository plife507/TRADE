"""
EMA + RSI + ATR Strategy.

A trend-following strategy that:
- Uses EMA crossover for trend direction
- RSI for confirmation (avoid overbought/oversold entries)
- ATR for stop loss and take profit distances

Config-driven: all parameters come from system YAML.

Identifier model:
- STRATEGY_ID: Stable family name (does not change between versions)
- STRATEGY_DEFAULT_VERSION: Used when system YAML doesn't specify version
- Version in signals uses the stable STRATEGY_ID

Phase 2: RuntimeSnapshot is the only supported snapshot type.
"""

from typing import Optional, Dict, Any

from ..backtest.runtime.types import RuntimeSnapshot
from ..core.risk_manager import Signal


# Strategy identity (stable across versions)
STRATEGY_ID = "ema_rsi_atr"
STRATEGY_DEFAULT_VERSION = "1.0.0"
STRATEGY_DESCRIPTION = "EMA crossover + RSI filter + ATR-based TP/SL"


def ema_rsi_atr_strategy(
    snapshot: RuntimeSnapshot,
    params: Dict[str, Any],
) -> Optional[Signal]:
    """
    EMA + RSI + ATR strategy.
    
    Entry conditions:
    - LONG: ema_fast > ema_slow AND RSI < overbought
    - SHORT: ema_fast < ema_slow AND RSI > oversold
    
    Exit via TP/SL calculated from ATR.
    
    Args:
        snapshot: Current market state (RuntimeSnapshot)
        params: Strategy parameters including:
            - ema_fast_period, ema_slow_period
            - rsi_period, rsi_overbought, rsi_oversold
            - atr_period, atr_sl_multiplier, atr_tp_multiplier
            
    Returns:
        Signal or None
    """
    # Extract indicators from RuntimeSnapshot
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
    
    # Default position size (will be adjusted by risk policy if enabled)
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
        strategy=STRATEGY_ID,  # Use stable ID, not versioned
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
