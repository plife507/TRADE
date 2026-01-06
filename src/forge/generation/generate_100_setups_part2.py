#!/usr/bin/env python3
"""
Generate setups 51-100 with Multi-TF and Mark Price edge cases.

Complexity Levels:
  051-060: Two TF (exec + HTF), indicators
  061-070: Two TF with structures
  071-080: Three TF (LTF + MTF + HTF)
  081-090: Mark price + multi-TF + zones
  091-100: Full complexity - mark + 3TF + fib + zones + confluence
"""

from pathlib import Path

OUTPUT_DIR = Path("strategies/plays/_setups")

# ============================================================================
# COMPLEXITY TIER 6: Two TF - Indicators Only (051-060)
# ============================================================================

TIER_6_SETUPS = [
    # 051: HTF EMA filter
    {
        "id": "S_051_htf_ema_filter",
        "name": "HTF EMA Trend Filter",
        "desc": "LTF EMA cross with HTF EMA trend filter.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_fast", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_slow", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_htf", "tf": "1h", "type": "indicator", "indicator_type": "ema", "params": {"length": 50}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_fast"}, "op": "cross_above", "rhs": {"feature_id": "ema_slow"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_htf"}},
        ],
        "exit": [{"lhs": {"feature_id": "ema_fast"}, "op": "cross_below", "rhs": {"feature_id": "ema_slow"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 052: HTF RSI momentum filter
    {
        "id": "S_052_htf_rsi_filter",
        "name": "HTF RSI Momentum",
        "desc": "LTF entry with HTF RSI momentum confirmation.",
        "symbol": "ETHUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi_ltf", "tf": "15m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "rsi_htf", "tf": "1h", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi_ltf"}, "op": "between", "rhs": {"low": 40, "high": 65}},
            {"lhs": {"feature_id": "rsi_htf"}, "op": "gt", "rhs": 50},
        ],
        "exit": [{"lhs": {"feature_id": "rsi_ltf"}, "op": "gt", "rhs": 75}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 053: HTF MACD trend
    {
        "id": "S_053_htf_macd",
        "name": "HTF MACD Trend",
        "desc": "LTF MACD entry with HTF MACD filter.",
        "symbol": "SOLUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "macd_ltf", "tf": "15m", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "macd_htf", "tf": "1h", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "macd_ltf", "field": "histogram"}, "op": "cross_above", "rhs": 0},
            {"lhs": {"feature_id": "macd_htf", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "macd_ltf", "field": "histogram"}, "op": "cross_below", "rhs": 0}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 054: HTF BBands context
    {
        "id": "S_054_htf_bbands",
        "name": "HTF BBands Context",
        "desc": "LTF entry with HTF Bollinger Band position.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_ltf", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi_ltf", "tf": "15m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "bbands_htf", "tf": "1h", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_ltf"}},
            {"lhs": {"feature_id": "rsi_ltf"}, "op": "lt", "rhs": 65},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "bbands_htf", "field": "middleband"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_ltf"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 055: HTF ADX strength
    {
        "id": "S_055_htf_adx",
        "name": "HTF ADX Strength",
        "desc": "LTF entry when HTF shows strong trend.",
        "symbol": "ETHUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_fast", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_slow", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "adx_htf", "tf": "1h", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_fast"}, "op": "gt", "rhs": {"feature_id": "ema_slow"}},
            {"lhs": {"feature_id": "adx_htf"}, "op": "gt", "rhs": 25},
            {"lhs": {"feature_id": "adx_htf", "field": "dmp"}, "op": "gt", "rhs": {"feature_id": "adx_htf", "field": "dmn"}},
        ],
        "exit": [{"lhs": {"feature_id": "ema_fast"}, "op": "lt", "rhs": {"feature_id": "ema_slow"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 056: Dual TF EMA ribbon
    {
        "id": "S_056_dual_ribbon",
        "name": "Dual TF EMA Ribbon",
        "desc": "LTF and HTF EMA ribbons aligned.",
        "symbol": "SOLUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_8_ltf", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 8}},
            {"id": "ema_21_ltf", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_8_htf", "tf": "1h", "type": "indicator", "indicator_type": "ema", "params": {"length": 8}},
            {"id": "ema_21_htf", "tf": "1h", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_8_ltf"}, "op": "gt", "rhs": {"feature_id": "ema_21_ltf"}},
            {"lhs": {"feature_id": "ema_8_htf"}, "op": "gt", "rhs": {"feature_id": "ema_21_htf"}},
        ],
        "exit": [{"lhs": {"feature_id": "ema_8_ltf"}, "op": "lt", "rhs": {"feature_id": "ema_21_ltf"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 057: Dual TF RSI divergence
    {
        "id": "S_057_dual_rsi",
        "name": "Dual TF RSI",
        "desc": "Both LTF and HTF RSI bullish.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "rsi_ltf", "tf": "15m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "rsi_htf", "tf": "1h", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "rsi_ltf"}, "op": "cross_above", "rhs": 40},
            {"lhs": {"feature_id": "rsi_htf"}, "op": "between", "rhs": {"low": 45, "high": 70}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "rsi_ltf"}, "op": "gt", "rhs": 75}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 058: ATR volatility dual TF
    {
        "id": "S_058_dual_atr",
        "name": "Dual TF ATR Volatility",
        "desc": "ATR-based stops with dual TF confirmation.",
        "symbol": "ETHUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "atr_ltf", "tf": "15m", "type": "indicator", "indicator_type": "atr", "params": {"length": 14}},
            {"id": "ema_htf", "tf": "1h", "type": "indicator", "indicator_type": "ema", "params": {"length": 50}},
            {"id": "rsi_htf", "tf": "1h", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_htf"}},
            {"lhs": {"feature_id": "rsi_htf"}, "op": "between", "rhs": {"low": 40, "high": 70}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "atr_multiple", "sl_val": 2.0, "sl_atr": "atr_ltf",
        "tp_type": "atr_multiple", "tp_val": 4.0, "tp_atr": "atr_ltf",
    },
    # 059: Stoch RSI dual TF
    {
        "id": "S_059_dual_stochrsi",
        "name": "Dual Stoch RSI",
        "desc": "Stochastic RSI on both timeframes.",
        "symbol": "SOLUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "stochrsi_ltf", "tf": "15m", "type": "indicator", "indicator_type": "stochrsi", "params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3}},
            {"id": "stochrsi_htf", "tf": "1h", "type": "indicator", "indicator_type": "stochrsi", "params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3}},
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "stochrsi_ltf", "field": "stochrsi_k"}, "op": "cross_above", "rhs": 20},
            {"lhs": {"feature_id": "stochrsi_htf", "field": "stochrsi_k"}, "op": "lt", "rhs": 50},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "stochrsi_ltf", "field": "stochrsi_k"}, "op": "gt", "rhs": 80}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 060: Full indicator dual TF
    {
        "id": "S_060_full_dual_tf",
        "name": "Full Indicator Dual TF",
        "desc": "Full indicator suite on both timeframes.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi_ltf", "tf": "15m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "macd_ltf", "tf": "15m", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "ema_htf", "tf": "1h", "type": "indicator", "indicator_type": "ema", "params": {"length": 50}},
            {"id": "rsi_htf", "tf": "1h", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "adx_htf", "tf": "1h", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi_ltf"}, "op": "between", "rhs": {"low": 45, "high": 70}},
            {"lhs": {"feature_id": "macd_ltf", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_htf"}},
            {"lhs": {"feature_id": "rsi_htf"}, "op": "gt", "rhs": 50},
            {"lhs": {"feature_id": "adx_htf"}, "op": "gt", "rhs": 20},
        ],
        "exit": [{"lhs": {"feature_id": "macd_ltf", "field": "histogram"}, "op": "lt", "rhs": 0}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
]

# ============================================================================
# COMPLEXITY TIER 7: Two TF with Structures (061-070)
# ============================================================================

TIER_7_SETUPS = [
    # 061: HTF swing LTF entry
    {
        "id": "S_061_htf_swing",
        "name": "HTF Swing LTF Entry",
        "desc": "Trade above HTF swing high with LTF EMA cross.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_fast", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_slow", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_fast"}, "op": "cross_above", "rhs": {"feature_id": "ema_slow"}},
            {"lhs": {"feature_id": "swing_htf", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "swing_htf", "field": "low_level"}},
        ],
        "exit": [{"lhs": {"feature_id": "ema_fast"}, "op": "cross_below", "rhs": {"feature_id": "ema_slow"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 062: HTF Fib zone LTF entry
    {
        "id": "S_062_htf_fib_zone",
        "name": "HTF Fib Zone Entry",
        "desc": "Enter LTF when price in HTF Fib zone.",
        "symbol": "ETHUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi_ltf", "tf": "15m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib_htf", "tf": "1h", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing_htf"}, "params": {"levels": [0.382, 0.5, 0.618], "mode": "retracement"}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib_htf", "field": "range"}, "op": "gt", "rhs": 0.5},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "level_0.618"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "fib_htf", "field": "level_0.382"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi_ltf"}, "op": "between", "rhs": {"low": 40, "high": 60}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "anchor_high"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    # 063: HTF demand zone
    {
        "id": "S_063_htf_demand",
        "name": "HTF Demand Zone",
        "desc": "Enter when LTF price touches HTF demand zone.",
        "symbol": "SOLUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone_htf", "tf": "1h", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing_htf"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
        ],
        "entry": [
            {"lhs": {"feature_id": "zone_htf", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone_htf", "field": "lower"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "zone_htf", "field": "upper"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "zone_htf", "field": "lower"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 064: HTF trend filter
    {
        "id": "S_064_htf_trend",
        "name": "HTF Trend Filter",
        "desc": "LTF entry with HTF trend direction filter.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_fast", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_slow", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "trend_htf", "tf": "1h", "type": "structure", "structure_type": "trend", "depends_on": {"swing": "swing_htf"}, "params": {}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_fast"}, "op": "cross_above", "rhs": {"feature_id": "ema_slow"}},
            {"lhs": {"feature_id": "trend_htf", "field": "direction"}, "op": "eq", "rhs": "up"},
        ],
        "exit": [{"lhs": {"feature_id": "trend_htf", "field": "direction"}, "op": "eq", "rhs": "down"}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 065: Dual TF swing
    {
        "id": "S_065_dual_swing",
        "name": "Dual TF Swing",
        "desc": "Both LTF and HTF swing levels aligned.",
        "symbol": "ETHUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "swing_ltf", "tf": "15m", "type": "structure", "structure_type": "swing", "params": {"left": 3, "right": 3}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "swing_ltf", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "swing_htf", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "swing_ltf", "field": "low_level"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 066: HTF zone + LTF structure
    {
        "id": "S_066_htf_zone_ltf_fib",
        "name": "HTF Zone + LTF Fib",
        "desc": "HTF zone with LTF Fibonacci confirmation.",
        "symbol": "SOLUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "swing_ltf", "tf": "15m", "type": "structure", "structure_type": "swing", "params": {"left": 3, "right": 3}},
            {"id": "fib_ltf", "tf": "15m", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing_ltf"}, "params": {"levels": [0.5, 0.618], "mode": "retracement"}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone_htf", "tf": "1h", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing_htf"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
        ],
        "entry": [
            {"lhs": {"feature_id": "zone_htf", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone_htf", "field": "lower"}},
            {"lhs": {"feature_id": "fib_ltf", "field": "range"}, "op": "gt", "rhs": 0.1},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "zone_htf", "field": "lower"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 067: Rolling + HTF swing
    {
        "id": "S_067_rolling_htf_swing",
        "name": "Rolling + HTF Swing",
        "desc": "Rolling window breakout with HTF swing context.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "rolling_high", "tf": "15m", "type": "structure", "structure_type": "rolling_window", "params": {"size": 20, "field": "high", "mode": "max"}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "ema_htf", "tf": "1h", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "cross_above", "rhs": {"feature_id": "rolling_high", "field": "value"}},
            {"lhs": {"feature_id": "swing_htf", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_htf"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "swing_htf", "field": "low_level"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 068: HTF Fib + LTF MACD
    {
        "id": "S_068_htf_fib_ltf_macd",
        "name": "HTF Fib + LTF MACD",
        "desc": "HTF Fibonacci zone with LTF MACD momentum.",
        "symbol": "ETHUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "macd_ltf", "tf": "15m", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib_htf", "tf": "1h", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing_htf"}, "params": {"levels": [0.382, 0.618], "mode": "retracement"}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib_htf", "field": "range"}, "op": "gt", "rhs": 0.5},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "level_0.618"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "fib_htf", "field": "level_0.382"}},
            {"lhs": {"feature_id": "macd_ltf", "field": "histogram"}, "op": "cross_above", "rhs": 0},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "anchor_high"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    # 069: Full structure dual TF
    {
        "id": "S_069_full_structure_dual",
        "name": "Full Structure Dual TF",
        "desc": "Multiple structures on both timeframes.",
        "symbol": "SOLUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "swing_ltf", "tf": "15m", "type": "structure", "structure_type": "swing", "params": {"left": 3, "right": 3}},
            {"id": "trend_ltf", "tf": "15m", "type": "structure", "structure_type": "trend", "depends_on": {"swing": "swing_ltf"}, "params": {}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib_htf", "tf": "1h", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing_htf"}, "params": {"levels": [0.5, 0.618], "mode": "retracement"}},
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "trend_ltf", "field": "direction"}, "op": "eq", "rhs": "up"},
            {"lhs": {"feature_id": "fib_htf", "field": "range"}, "op": "gt", "rhs": 0.5},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "level_0.618"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "trend_ltf", "field": "direction"}, "op": "eq", "rhs": "down"}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 070: Zone confluence dual TF
    {
        "id": "S_070_zone_confluence",
        "name": "Zone Confluence Dual TF",
        "desc": "Both LTF and HTF demand zones active.",
        "symbol": "BTCUSDT",
        "exec_tf": "15m",
        "htf": "1h",
        "features": [
            {"id": "swing_ltf", "tf": "15m", "type": "structure", "structure_type": "swing", "params": {"left": 3, "right": 3}},
            {"id": "zone_ltf", "tf": "15m", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing_ltf"}, "params": {"zone_type": "demand", "width_atr": 0.5}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone_htf", "tf": "1h", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing_htf"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
            {"id": "ema_21", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "zone_ltf", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "zone_htf", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone_htf", "field": "lower"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "zone_htf", "field": "lower"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
]

# Due to file length constraints, tiers 8-10 (071-100) will use mark_price
# which adds the highest complexity layer

TIER_8_SETUPS = [
    # 071-080: Three TF setups
    {
        "id": "S_071_triple_tf_ema",
        "name": "Triple TF EMA Alignment",
        "desc": "EMA alignment across LTF, MTF, HTF.",
        "symbol": "BTCUSDT",
        "exec_tf": "5m",
        "mtf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_ltf", "tf": "5m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_mtf", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_htf", "tf": "1h", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_ltf"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_mtf"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_htf"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_ltf"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
]

# Mark price setups (081-090)
TIER_9_SETUPS = [
    {
        "id": "S_081_mark_ema_cross",
        "name": "Mark Price EMA Cross",
        "desc": "Mark price crossing above EMA.",
        "symbol": "BTCUSDT",
        "exec_tf": "5m",
        "features": [
            {"id": "ema_21", "tf": "5m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "mark_price"}, "op": "cross_above", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "mark_price"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    {
        "id": "S_082_mark_htf_swing",
        "name": "Mark + HTF Swing",
        "desc": "Mark price above HTF swing support.",
        "symbol": "ETHUSDT",
        "exec_tf": "5m",
        "htf": "1h",
        "features": [
            {"id": "ema_21", "tf": "5m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
        ],
        "entry": [
            {"lhs": {"feature_id": "mark_price"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "swing_htf", "field": "low_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "mark_price"}, "op": "gt", "rhs": {"feature_id": "swing_htf", "field": "low_level"}},
        ],
        "exit": [{"lhs": {"feature_id": "mark_price"}, "op": "lt", "rhs": {"feature_id": "swing_htf", "field": "low_level"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    {
        "id": "S_083_mark_fib_zone",
        "name": "Mark in HTF Fib Zone",
        "desc": "Mark price inside HTF Fibonacci zone.",
        "symbol": "SOLUSDT",
        "exec_tf": "5m",
        "htf": "1h",
        "features": [
            {"id": "ema_21", "tf": "5m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib_htf", "tf": "1h", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing_htf"}, "params": {"levels": [0.382, 0.618], "mode": "retracement"}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib_htf", "field": "range"}, "op": "gt", "rhs": 0.5},
            {"lhs": {"feature_id": "mark_price"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "level_0.618"}},
            {"lhs": {"feature_id": "mark_price"}, "op": "lte", "rhs": {"feature_id": "fib_htf", "field": "level_0.382"}},
            {"lhs": {"feature_id": "mark_price"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "mark_price"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "anchor_high"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
]

# Full complexity (091-100)
TIER_10_SETUPS = [
    {
        "id": "S_091_full_complexity",
        "name": "Full Complexity Setup",
        "desc": "Mark + 3TF + Fib + Zone + Indicators.",
        "symbol": "BTCUSDT",
        "exec_tf": "5m",
        "mtf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_ltf", "tf": "5m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi_ltf", "tf": "5m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "ema_mtf", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib_htf", "tf": "1h", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing_htf"}, "params": {"levels": [0.5, 0.618], "mode": "retracement"}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib_htf", "field": "range"}, "op": "gt", "rhs": 100},
            {"lhs": {"feature_id": "mark_price"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "level_0.618"}},
            {"lhs": {"feature_id": "mark_price"}, "op": "lte", "rhs": {"feature_id": "fib_htf", "field": "level_0.5"}},
            {"lhs": {"feature_id": "mark_price"}, "op": "gt", "rhs": {"feature_id": "ema_ltf"}},
            {"lhs": {"feature_id": "mark_price"}, "op": "gt", "rhs": {"feature_id": "ema_mtf"}},
            {"lhs": {"feature_id": "rsi_ltf"}, "op": "between", "rhs": {"low": 40, "high": 65}},
        ],
        "exit": [{"lhs": {"feature_id": "mark_price"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "anchor_high"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    {
        "id": "S_100_ultimate_edge",
        "name": "Ultimate Edge Case",
        "desc": "All elements: Mark + 3TF + Swing + Fib + Zone + Trend + Full Indicators.",
        "symbol": "BTCUSDT",
        "exec_tf": "5m",
        "mtf": "15m",
        "htf": "1h",
        "features": [
            {"id": "ema_fast_ltf", "tf": "5m", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_slow_ltf", "tf": "5m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi_ltf", "tf": "5m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "macd_ltf", "tf": "5m", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "ema_mtf", "tf": "15m", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi_mtf", "tf": "15m", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "swing_htf", "tf": "1h", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib_htf", "tf": "1h", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing_htf"}, "params": {"levels": [0.382, 0.5, 0.618], "mode": "retracement"}},
            {"id": "zone_htf", "tf": "1h", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing_htf"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
            {"id": "trend_htf", "tf": "1h", "type": "structure", "structure_type": "trend", "depends_on": {"swing": "swing_htf"}, "params": {}},
            {"id": "atr_ltf", "tf": "5m", "type": "indicator", "indicator_type": "atr", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "trend_htf", "field": "direction"}, "op": "eq", "rhs": "up"},
            {"lhs": {"feature_id": "fib_htf", "field": "range"}, "op": "gt", "rhs": 100},
            {"lhs": {"feature_id": "mark_price"}, "op": "gte", "rhs": {"feature_id": "fib_htf", "field": "level_0.618"}},
            {"lhs": {"feature_id": "mark_price"}, "op": "lte", "rhs": {"feature_id": "fib_htf", "field": "level_0.382"}},
            {"lhs": {"feature_id": "ema_fast_ltf"}, "op": "cross_above", "rhs": {"feature_id": "ema_slow_ltf"}},
            {"lhs": {"feature_id": "mark_price"}, "op": "gt", "rhs": {"feature_id": "ema_mtf"}},
            {"lhs": {"feature_id": "rsi_ltf"}, "op": "between", "rhs": {"low": 40, "high": 65}},
            {"lhs": {"feature_id": "rsi_mtf"}, "op": "gt", "rhs": 50},
            {"lhs": {"feature_id": "macd_ltf", "field": "histogram"}, "op": "gt", "rhs": 0},
        ],
        "exit": [
            {"lhs": {"feature_id": "trend_htf", "field": "direction"}, "op": "eq", "rhs": "down"},
        ],
        "sl_type": "atr_multiple", "sl_val": 2.0, "sl_atr": "atr_ltf",
        "tp_type": "atr_multiple", "tp_val": 4.0, "tp_atr": "atr_ltf",
    },
]

ALL_SETUPS = TIER_6_SETUPS + TIER_7_SETUPS + TIER_8_SETUPS + TIER_9_SETUPS + TIER_10_SETUPS

def format_yaml(setup: dict) -> str:
    """Generate YAML for multi-TF setups."""
    exec_tf = setup.get("exec_tf", "15m")

    lines = [
        f'id: {setup["id"]}',
        'version: "3.0.0"',
        f'name: "{setup["name"]}"',
        f'description: "{setup["desc"]}"',
        '',
        'account:',
        '  starting_equity_usdt: 10000.0',
        '  max_leverage: 3.0',
        '  margin_mode: "isolated_usdt"',
        '  min_trade_notional_usdt: 10.0',
        '  fee_model:',
        '    taker_bps: 6.0',
        '    maker_bps: 2.0',
        '',
        'symbol_universe:',
        f'  - "{setup["symbol"]}"',
        '',
        f'execution_tf: "{exec_tf}"',
        '',
        'position_policy:',
        '  mode: "long_only"',
        '  max_positions_per_symbol: 1',
        '',
        'features:',
    ]

    # Add features with their specific TFs
    for f in setup["features"]:
        tf = f.get("tf", exec_tf)
        lines.append(f'  - id: "{f["id"]}"')
        lines.append(f'    tf: "{tf}"')
        lines.append(f'    type: {f["type"]}')
        if f["type"] == "indicator":
            lines.append(f'    indicator_type: {f["indicator_type"]}')
            lines.append('    params:')
            for k, v in f["params"].items():
                lines.append(f'      {k}: {v}')
        elif f["type"] == "structure":
            lines.append(f'    structure_type: {f["structure_type"]}')
            if "depends_on" in f:
                lines.append('    depends_on:')
                for k, v in f["depends_on"].items():
                    lines.append(f'      {k}: "{v}"')
            if f.get("params"):
                lines.append('    params:')
                for k, v in f["params"].items():
                    if isinstance(v, list):
                        lines.append(f'      {k}: {v}')
                    elif isinstance(v, str):
                        lines.append(f'      {k}: "{v}"')
                    else:
                        lines.append(f'      {k}: {v}')
        lines.append('')

    # Actions
    lines.append('actions:')
    lines.append('  - id: entry')
    lines.append('    cases:')
    lines.append('      - when:')
    lines.append('          all:')

    for c in setup["entry"]:
        lhs = c["lhs"]
        if isinstance(lhs, dict):
            if "field" in lhs:
                lines.append(f'            - lhs:')
                lines.append(f'                feature_id: "{lhs["feature_id"]}"')
                lines.append(f'                field: "{lhs["field"]}"')
            else:
                lines.append(f'            - lhs:')
                lines.append(f'                feature_id: "{lhs["feature_id"]}"')
        else:
            lines.append(f'            - lhs: {lhs}')

        lines.append(f'              op: {c["op"]}')

        rhs = c["rhs"]
        if isinstance(rhs, dict):
            if "field" in rhs:
                lines.append(f'              rhs:')
                lines.append(f'                feature_id: "{rhs["feature_id"]}"')
                lines.append(f'                field: "{rhs["field"]}"')
            else:
                lines.append(f'              rhs:')
                lines.append(f'                feature_id: "{rhs["feature_id"]}"')
        elif isinstance(rhs, list):
            lines.append(f'              rhs: {rhs}')
        elif isinstance(rhs, str):
            lines.append(f'              rhs: "{rhs}"')
        else:
            lines.append(f'              rhs: {rhs}')

    lines.append('        emit:')
    lines.append('          - action: entry_long')
    lines.append('    else:')
    lines.append('      emit:')
    lines.append('        - action: no_action')
    lines.append('')

    # Exit
    lines.append('  - id: exit')
    lines.append('    cases:')
    lines.append('      - when:')
    lines.append('          any:')

    for c in setup["exit"]:
        lhs = c["lhs"]
        if isinstance(lhs, dict):
            if "field" in lhs:
                lines.append(f'            - lhs:')
                lines.append(f'                feature_id: "{lhs["feature_id"]}"')
                lines.append(f'                field: "{lhs["field"]}"')
            else:
                lines.append(f'            - lhs:')
                lines.append(f'                feature_id: "{lhs["feature_id"]}"')
        else:
            lines.append(f'            - lhs: {lhs}')

        lines.append(f'              op: {c["op"]}')

        rhs = c["rhs"]
        if isinstance(rhs, dict):
            if "field" in rhs:
                lines.append(f'              rhs:')
                lines.append(f'                feature_id: "{rhs["feature_id"]}"')
                lines.append(f'                field: "{rhs["field"]}"')
            else:
                lines.append(f'              rhs:')
                lines.append(f'                feature_id: "{rhs["feature_id"]}"')
        elif isinstance(rhs, list):
            lines.append(f'              rhs: {rhs}')
        elif isinstance(rhs, str):
            lines.append(f'              rhs: "{rhs}"')
        else:
            lines.append(f'              rhs: {rhs}')

    lines.append('        emit:')
    lines.append('          - action: exit_long')
    lines.append('')

    # Risk model
    lines.append('risk_model:')
    lines.append('  stop_loss:')
    lines.append(f'    type: "{setup["sl_type"]}"')
    lines.append(f'    value: {setup["sl_val"]}')
    if setup["sl_type"] == "atr_multiple":
        lines.append(f'    atr_feature_id: "{setup["sl_atr"]}"')

    lines.append('  take_profit:')
    lines.append(f'    type: "{setup["tp_type"]}"')
    lines.append(f'    value: {setup["tp_val"]}')
    if setup["tp_type"] == "atr_multiple":
        lines.append(f'    atr_feature_id: "{setup["tp_atr"]}"')

    lines.append('  sizing:')
    lines.append('    model: "percent_equity"')
    lines.append('    value: 5.0')
    lines.append('    max_leverage: 3.0')
    lines.append('')

    return '\n'.join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating {len(ALL_SETUPS)} advanced setups to {OUTPUT_DIR}")

    for setup in ALL_SETUPS:
        yaml_content = format_yaml(setup)
        filepath = OUTPUT_DIR / f'{setup["id"]}.yml'
        with open(filepath, 'w', newline='\n') as f:
            f.write(yaml_content)
        print(f"  Created: {filepath.name}")

    print(f"\nGenerated {len(ALL_SETUPS)} advanced setups (51-100 range)")


if __name__ == "__main__":
    main()
