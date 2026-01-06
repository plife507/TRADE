#!/usr/bin/env python3
"""
Generate 100 Trading Setups with Progressive Complexity.

Complexity Levels:
  001-010: Single indicator, single TF, percent TP/SL
  011-020: Two indicators, single TF, percent TP/SL
  021-030: Three+ indicators, single TF, ATR TP/SL
  031-040: Single structure (swing), single TF
  041-050: Structure + indicators, single TF
  051-060: Two TF (exec + HTF), indicators
  061-070: Two TF with structures
  071-080: Three TF (LTF + MTF + HTF)
  081-090: Mark price + multi-TF + zones
  091-100: Full complexity - mark + 3TF + fib + zones + confluence

All setups use:
  - Market orders only
  - 1 stop loss + 1 take profit
  - 3x max leverage
  - BTCUSDT, ETHUSDT, or SOLUSDT
"""

from pathlib import Path

OUTPUT_DIR = Path("configs/plays/_setups")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
EXEC_TFS = ["5m", "15m", "30m", "1h"]

# ============================================================================
# COMPLEXITY TIER 1: Single Indicator (001-010)
# ============================================================================

TIER_1_SETUPS = [
    # 001: EMA crossover - simplest possible
    {
        "id": "S_001_ema_cross",
        "name": "EMA 9/21 Crossover",
        "desc": "Classic fast/slow EMA crossover. Entry on cross_above, exit on cross_below.",
        "symbol": "BTCUSDT",
        "tf": "15m",
        "features": [
            {"id": "ema_fast", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_slow", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [{"lhs": {"feature_id": "ema_fast"}, "op": "cross_above", "rhs": {"feature_id": "ema_slow"}}],
        "exit": [{"lhs": {"feature_id": "ema_fast"}, "op": "cross_below", "rhs": {"feature_id": "ema_slow"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 002: Price above EMA trend
    {
        "id": "S_002_ema_trend",
        "name": "EMA Trend Follow",
        "desc": "Enter when price above EMA, exit when below.",
        "symbol": "ETHUSDT",
        "tf": "15m",
        "features": [
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [{"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}}],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 1.5,
        "tp_type": "percent", "tp_val": 3.0,
    },
    # 003: SMA crossover
    {
        "id": "S_003_sma_cross",
        "name": "SMA 10/30 Crossover",
        "desc": "Simple moving average crossover strategy.",
        "symbol": "SOLUSDT",
        "tf": "15m",
        "features": [
            {"id": "sma_fast", "type": "indicator", "indicator_type": "sma", "params": {"length": 10}},
            {"id": "sma_slow", "type": "indicator", "indicator_type": "sma", "params": {"length": 30}},
        ],
        "entry": [{"lhs": {"feature_id": "sma_fast"}, "op": "cross_above", "rhs": {"feature_id": "sma_slow"}}],
        "exit": [{"lhs": {"feature_id": "sma_fast"}, "op": "cross_below", "rhs": {"feature_id": "sma_slow"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 004: RSI oversold bounce
    {
        "id": "S_004_rsi_oversold",
        "name": "RSI Oversold Bounce",
        "desc": "Enter when RSI crosses above 30, exit when crosses above 70.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [{"lhs": {"feature_id": "rsi"}, "op": "cross_above", "rhs": 30}],
        "exit": [{"lhs": {"feature_id": "rsi"}, "op": "cross_above", "rhs": 70}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    # 005: RSI momentum
    {
        "id": "S_005_rsi_momentum",
        "name": "RSI Momentum",
        "desc": "Enter when RSI > 50 (bullish momentum), exit when < 50.",
        "symbol": "ETHUSDT",
        "tf": "30m",
        "features": [
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [{"lhs": {"feature_id": "rsi"}, "op": "cross_above", "rhs": 50}],
        "exit": [{"lhs": {"feature_id": "rsi"}, "op": "cross_below", "rhs": 50}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 006: MACD signal cross
    {
        "id": "S_006_macd_signal",
        "name": "MACD Signal Crossover",
        "desc": "Enter when MACD crosses above signal, exit when crosses below.",
        "symbol": "SOLUSDT",
        "tf": "15m",
        "features": [
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ],
        "entry": [{"lhs": {"feature_id": "macd", "field": "macd"}, "op": "cross_above", "rhs": {"feature_id": "macd", "field": "signal"}}],
        "exit": [{"lhs": {"feature_id": "macd", "field": "macd"}, "op": "cross_below", "rhs": {"feature_id": "macd", "field": "signal"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 007: MACD histogram positive
    {
        "id": "S_007_macd_histogram",
        "name": "MACD Histogram Positive",
        "desc": "Enter when histogram turns positive, exit when negative.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ],
        "entry": [{"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "cross_above", "rhs": 0}],
        "exit": [{"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "cross_below", "rhs": 0}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 008: Bollinger Band bounce
    {
        "id": "S_008_bbands_bounce",
        "name": "Bollinger Band Lower Bounce",
        "desc": "Enter when price crosses above lower band, exit at middle.",
        "symbol": "ETHUSDT",
        "tf": "15m",
        "features": [
            {"id": "bbands", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
        ],
        "entry": [{"lhs": {"feature_id": "close"}, "op": "cross_above", "rhs": {"feature_id": "bbands", "field": "lowerband"}}],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "bbands", "field": "middleband"}}],
        "sl_type": "percent", "sl_val": 1.5,
        "tp_type": "percent", "tp_val": 3.0,
    },
    # 009: ATR breakout
    {
        "id": "S_009_atr_breakout",
        "name": "ATR Volatility Breakout",
        "desc": "Enter when ATR spikes (volatility expansion).",
        "symbol": "SOLUSDT",
        "tf": "1h",
        "features": [
            {"id": "atr", "type": "indicator", "indicator_type": "atr", "params": {"length": 14}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "atr_multiple", "sl_val": 1.5, "sl_atr": "atr",
        "tp_type": "atr_multiple", "tp_val": 3.0, "tp_atr": "atr",
    },
    # 010: ADX trend strength
    {
        "id": "S_010_adx_trend",
        "name": "ADX Strong Trend",
        "desc": "Enter when ADX > 25 and +DI > -DI.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 25},
            {"lhs": {"feature_id": "adx", "field": "dmp"}, "op": "gt", "rhs": {"feature_id": "adx", "field": "dmn"}},
        ],
        "exit": [{"lhs": {"feature_id": "adx", "field": "dmp"}, "op": "lt", "rhs": {"feature_id": "adx", "field": "dmn"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
]

# ============================================================================
# COMPLEXITY TIER 2: Two Indicators (011-020)
# ============================================================================

TIER_2_SETUPS = [
    # 011: EMA + RSI filter
    {
        "id": "S_011_ema_rsi",
        "name": "EMA Trend + RSI Filter",
        "desc": "EMA crossover with RSI confirmation (not overbought).",
        "symbol": "BTCUSDT",
        "tf": "15m",
        "features": [
            {"id": "ema_fast", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_slow", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_fast"}, "op": "cross_above", "rhs": {"feature_id": "ema_slow"}},
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 70},
        ],
        "exit": [{"lhs": {"feature_id": "ema_fast"}, "op": "cross_below", "rhs": {"feature_id": "ema_slow"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 012: MACD + EMA filter
    {
        "id": "S_012_macd_ema",
        "name": "MACD + EMA Trend",
        "desc": "MACD signal cross with EMA trend filter.",
        "symbol": "ETHUSDT",
        "tf": "15m",
        "features": [
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "ema_50", "type": "indicator", "indicator_type": "ema", "params": {"length": 50}},
        ],
        "entry": [
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "cross_above", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_50"}},
        ],
        "exit": [{"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "cross_below", "rhs": 0}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 013: RSI + BBands
    {
        "id": "S_013_rsi_bbands",
        "name": "RSI Oversold + BBand Touch",
        "desc": "RSI oversold at lower Bollinger Band.",
        "symbol": "SOLUSDT",
        "tf": "1h",
        "features": [
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "bbands", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
        ],
        "entry": [
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 35},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "bbands", "field": "lowerband"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "bbands", "field": "middleband"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    # 014: Double EMA + ADX
    {
        "id": "S_014_ema_adx",
        "name": "EMA Cross + ADX Strength",
        "desc": "EMA crossover only when ADX shows strong trend.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "ema_fast", "type": "indicator", "indicator_type": "ema", "params": {"length": 12}},
            {"id": "ema_slow", "type": "indicator", "indicator_type": "ema", "params": {"length": 26}},
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_fast"}, "op": "gt", "rhs": {"feature_id": "ema_slow"}},
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 20},
        ],
        "exit": [{"lhs": {"feature_id": "ema_fast"}, "op": "lt", "rhs": {"feature_id": "ema_slow"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 015: Stoch RSI + EMA
    {
        "id": "S_015_stochrsi_ema",
        "name": "Stoch RSI Oversold + EMA",
        "desc": "Stochastic RSI oversold with EMA trend confirmation.",
        "symbol": "ETHUSDT",
        "tf": "15m",
        "features": [
            {"id": "stochrsi", "type": "indicator", "indicator_type": "stochrsi", "params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "cross_above", "rhs": 20},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "cross_below", "rhs": 80}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 016: MACD + RSI momentum
    {
        "id": "S_016_macd_rsi",
        "name": "MACD + RSI Momentum",
        "desc": "MACD positive with RSI above 50.",
        "symbol": "SOLUSDT",
        "tf": "30m",
        "features": [
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "rsi"}, "op": "gt", "rhs": 50},
        ],
        "exit": [
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "lt", "rhs": 0},
        ],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 017: Triple EMA ribbon
    {
        "id": "S_017_ema_ribbon",
        "name": "Triple EMA Ribbon",
        "desc": "Three EMAs aligned (8 > 21 > 55).",
        "symbol": "BTCUSDT",
        "tf": "15m",
        "features": [
            {"id": "ema_8", "type": "indicator", "indicator_type": "ema", "params": {"length": 8}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_55", "type": "indicator", "indicator_type": "ema", "params": {"length": 55}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_8"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "ema_21"}, "op": "gt", "rhs": {"feature_id": "ema_55"}},
        ],
        "exit": [{"lhs": {"feature_id": "ema_8"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 018: BBands squeeze
    {
        "id": "S_018_bbands_squeeze",
        "name": "Bollinger Squeeze Breakout",
        "desc": "Enter when bands narrow then price breaks upper.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "bbands", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "cross_above", "rhs": {"feature_id": "bbands", "field": "upperband"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 019: RSI divergence setup
    {
        "id": "S_019_rsi_range",
        "name": "RSI Range Trade",
        "desc": "RSI between 40-60 with price trend filter.",
        "symbol": "SOLUSDT",
        "tf": "15m",
        "features": [
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "ema_50", "type": "indicator", "indicator_type": "ema", "params": {"length": 50}},
        ],
        "entry": [
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 40, "high": 60}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_50"}},
        ],
        "exit": [{"lhs": {"feature_id": "rsi"}, "op": "gt", "rhs": 75}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 020: ATR + EMA volatility
    {
        "id": "S_020_atr_ema",
        "name": "ATR Volatility + EMA",
        "desc": "Trade with ATR-based stops when above EMA.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "atr", "type": "indicator", "indicator_type": "atr", "params": {"length": 14}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 40, "high": 70}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "atr_multiple", "sl_val": 2.0, "sl_atr": "atr",
        "tp_type": "atr_multiple", "tp_val": 4.0, "tp_atr": "atr",
    },
]

# ============================================================================
# COMPLEXITY TIER 3: Multi-Indicator (021-030)
# ============================================================================

TIER_3_SETUPS = [
    # 021: EMA + MACD + RSI triple confirm
    {
        "id": "S_021_triple_confirm",
        "name": "Triple Confirmation",
        "desc": "EMA trend + MACD positive + RSI bullish.",
        "symbol": "BTCUSDT",
        "tf": "15m",
        "features": [
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 45, "high": 70}},
        ],
        "exit": [{"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "lt", "rhs": 0}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 022: BBands + RSI + EMA
    {
        "id": "S_022_bbands_combo",
        "name": "BBands RSI EMA Combo",
        "desc": "BBand bounce with RSI oversold and EMA support.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "bbands", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "ema_50", "type": "indicator", "indicator_type": "ema", "params": {"length": 50}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "bbands", "field": "lowerband"}},
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 35},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_50"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "bbands", "field": "middleband"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 023: ADX + MACD + EMA trend
    {
        "id": "S_023_adx_macd_ema",
        "name": "ADX MACD EMA Trend",
        "desc": "Strong ADX trend with MACD and EMA alignment.",
        "symbol": "SOLUSDT",
        "tf": "15m",
        "features": [
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 25},
            {"lhs": {"feature_id": "adx", "field": "dmp"}, "op": "gt", "rhs": {"feature_id": "adx", "field": "dmn"}},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "adx", "field": "dmp"}, "op": "lt", "rhs": {"feature_id": "adx", "field": "dmn"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 024: Stoch RSI + MACD + EMA
    {
        "id": "S_024_stoch_macd_ema",
        "name": "Stoch MACD EMA Combo",
        "desc": "Stochastic RSI cross with MACD and EMA filter.",
        "symbol": "BTCUSDT",
        "tf": "30m",
        "features": [
            {"id": "stochrsi", "type": "indicator", "indicator_type": "stochrsi", "params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "cross_above", "rhs": {"feature_id": "stochrsi", "field": "stochrsi_d"}},
            {"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "lt", "rhs": 50},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "gt", "rhs": 80}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 025: RSI + ATR breakout
    {
        "id": "S_025_rsi_atr_breakout",
        "name": "RSI ATR Breakout",
        "desc": "RSI momentum with ATR-based stops.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "atr", "type": "indicator", "indicator_type": "atr", "params": {"length": 14}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "rsi"}, "op": "cross_above", "rhs": 55},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 45}],
        "sl_type": "atr_multiple", "sl_val": 1.5, "sl_atr": "atr",
        "tp_type": "atr_multiple", "tp_val": 3.0, "tp_atr": "atr",
    },
    # 026: EMA ribbon + RSI filter
    {
        "id": "S_026_ribbon_rsi",
        "name": "EMA Ribbon + RSI",
        "desc": "Four EMA ribbon with RSI filter.",
        "symbol": "SOLUSDT",
        "tf": "15m",
        "features": [
            {"id": "ema_8", "type": "indicator", "indicator_type": "ema", "params": {"length": 8}},
            {"id": "ema_13", "type": "indicator", "indicator_type": "ema", "params": {"length": 13}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_55", "type": "indicator", "indicator_type": "ema", "params": {"length": 55}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_8"}, "op": "gt", "rhs": {"feature_id": "ema_13"}},
            {"lhs": {"feature_id": "ema_13"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "ema_21"}, "op": "gt", "rhs": {"feature_id": "ema_55"}},
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 45, "high": 65}},
        ],
        "exit": [{"lhs": {"feature_id": "ema_8"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 027: MACD + ADX + BBands
    {
        "id": "S_027_macd_adx_bbands",
        "name": "MACD ADX BBands Combo",
        "desc": "MACD cross with ADX strength at BBand touch.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
            {"id": "bbands", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
        ],
        "entry": [
            {"lhs": {"feature_id": "macd", "field": "macd"}, "op": "cross_above", "rhs": {"feature_id": "macd", "field": "signal"}},
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 20},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "bbands", "field": "middleband"}},
        ],
        "exit": [{"lhs": {"feature_id": "macd", "field": "macd"}, "op": "cross_below", "rhs": {"feature_id": "macd", "field": "signal"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 028: RSI + Stoch RSI double confirmation
    {
        "id": "S_028_rsi_stochrsi",
        "name": "RSI + Stoch RSI Double",
        "desc": "Both RSI and Stoch RSI oversold.",
        "symbol": "ETHUSDT",
        "tf": "15m",
        "features": [
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "stochrsi", "type": "indicator", "indicator_type": "stochrsi", "params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 40},
            {"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "cross_above", "rhs": 20},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "rsi"}, "op": "gt", "rhs": 70}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 029: Multi-EMA + MACD + ADX
    {
        "id": "S_029_multi_ema_macd",
        "name": "Multi-EMA MACD ADX",
        "desc": "Triple EMA with MACD and ADX confirmation.",
        "symbol": "SOLUSDT",
        "tf": "30m",
        "features": [
            {"id": "ema_9", "type": "indicator", "indicator_type": "ema", "params": {"length": 9}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_50", "type": "indicator", "indicator_type": "ema", "params": {"length": 50}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "ema_9"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "ema_21"}, "op": "gt", "rhs": {"feature_id": "ema_50"}},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 20},
        ],
        "exit": [{"lhs": {"feature_id": "ema_9"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 030: Full indicator suite
    {
        "id": "S_030_full_indicator",
        "name": "Full Indicator Suite",
        "desc": "EMA + MACD + RSI + ADX + BBands all aligned.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
            {"id": "bbands", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
            {"id": "atr", "type": "indicator", "indicator_type": "atr", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 45, "high": 70}},
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 20},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "bbands", "field": "middleband"}},
        ],
        "exit": [
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "lt", "rhs": 0},
        ],
        "sl_type": "atr_multiple", "sl_val": 2.0, "sl_atr": "atr",
        "tp_type": "atr_multiple", "tp_val": 4.0, "tp_atr": "atr",
    },
]

# ============================================================================
# COMPLEXITY TIER 4: Single Structure (031-040)
# ============================================================================

TIER_4_SETUPS = [
    # 031: Swing high/low basic
    {
        "id": "S_031_swing_basic",
        "name": "Swing Pivot Basic",
        "desc": "Trade above swing high with EMA filter.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "swing", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "swing", "field": "low_level"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 032: Swing support bounce
    {
        "id": "S_032_swing_support",
        "name": "Swing Support Bounce",
        "desc": "Bounce from swing low support level.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 3, "right": 3}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "swing", "field": "low_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "near_pct", "rhs": {"feature_id": "swing", "field": "low_level"}, "tolerance": 1.0},
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 40},
        ],
        "exit": [{"lhs": {"feature_id": "rsi"}, "op": "gt", "rhs": 70}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 033: Fibonacci retracement entry
    {
        "id": "S_033_fib_retrace",
        "name": "Fib 61.8 Retracement",
        "desc": "Enter at 61.8% Fibonacci retracement.",
        "symbol": "SOLUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing"}, "params": {"levels": [0.382, 0.5, 0.618], "mode": "retracement"}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib", "field": "range"}, "op": "gt", "rhs": 0.5},
            {"lhs": {"feature_id": "close"}, "op": "near_pct", "rhs": {"feature_id": "fib", "field": "level_0.618"}, "tolerance": 1.0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "anchor_high"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    # 034: Fibonacci golden zone
    {
        "id": "S_034_fib_golden",
        "name": "Fib Golden Zone",
        "desc": "Trade from 50-61.8% retracement zone.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing"}, "params": {"levels": [0.5, 0.618, 0.786], "mode": "retracement"}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib", "field": "range"}, "op": "gt", "rhs": 100},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "fib", "field": "level_0.5"}},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "level_0.618"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "fib", "field": "level_0.786"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 035: Demand zone basic
    {
        "id": "S_035_zone_demand",
        "name": "Demand Zone Entry",
        "desc": "Enter when price touches demand zone.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "zone", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone", "field": "lower"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "zone", "field": "upper"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "zone", "field": "lower"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 036: Trend direction filter
    {
        "id": "S_036_trend_direction",
        "name": "Trend Direction Filter",
        "desc": "Trade with trend using trend structure.",
        "symbol": "SOLUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "trend", "type": "structure", "structure_type": "trend", "depends_on": {"swing": "swing"}, "params": {}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": "up"},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": "down"}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 037: Rolling window breakout
    {
        "id": "S_037_rolling_high",
        "name": "Rolling High Breakout",
        "desc": "Breakout above rolling 20-bar high.",
        "symbol": "BTCUSDT",
        "tf": "15m",
        "features": [
            {"id": "rolling_high", "type": "structure", "structure_type": "rolling_window", "params": {"size": 20, "field": "high", "mode": "max"}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "cross_above", "rhs": {"feature_id": "rolling_high", "field": "value"}},
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 70},
        ],
        "exit": [{"lhs": {"feature_id": "rsi"}, "op": "gt", "rhs": 80}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 038: Swing + EMA + RSI
    {
        "id": "S_038_swing_ema_rsi",
        "name": "Swing EMA RSI Combo",
        "desc": "Swing pivot with EMA and RSI confirmation.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "swing", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 40, "high": 70}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 039: Fib extension target
    {
        "id": "S_039_fib_extension",
        "name": "Fib Extension Target",
        "desc": "Enter retracement, target extension.",
        "symbol": "SOLUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing"}, "params": {"levels": [0.382, 0.5, 0.618], "mode": "retracement"}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib", "field": "range"}, "op": "gt", "rhs": 0.5},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "level_0.618"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "fib", "field": "level_0.382"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "anchor_high"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    # 040: Zone + MACD combo
    {
        "id": "S_040_zone_macd",
        "name": "Zone MACD Combo",
        "desc": "Demand zone entry with MACD confirmation.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ],
        "entry": [
            {"lhs": {"feature_id": "zone", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone", "field": "lower"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "zone", "field": "upper"}},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "cross_above", "rhs": 0},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "zone", "field": "lower"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
]

# ============================================================================
# COMPLEXITY TIER 5: Structure + Multi-Indicator (041-050)
# ============================================================================

TIER_5_SETUPS = [
    # 041: Swing + Triple indicator
    {
        "id": "S_041_swing_triple",
        "name": "Swing Triple Indicator",
        "desc": "Swing pivot with EMA, RSI, MACD all aligned.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ],
        "entry": [
            {"lhs": {"feature_id": "swing", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 45, "high": 70}},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
        ],
        "exit": [{"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "lt", "rhs": 0}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 042: Fib + RSI + MACD
    {
        "id": "S_042_fib_rsi_macd",
        "name": "Fib RSI MACD Combo",
        "desc": "Fibonacci zone with RSI and MACD momentum.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing"}, "params": {"levels": [0.382, 0.5, 0.618], "mode": "retracement"}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib", "field": "range"}, "op": "gt", "rhs": 0.5},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "level_0.618"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "fib", "field": "level_0.382"}},
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 50},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "cross_above", "rhs": 0},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "anchor_high"}}],
        "sl_type": "percent", "sl_val": 3.0,
        "tp_type": "percent", "tp_val": 6.0,
    },
    # 043: Zone + ADX + EMA
    {
        "id": "S_043_zone_adx_ema",
        "name": "Zone ADX EMA Combo",
        "desc": "Demand zone with strong ADX trend and EMA filter.",
        "symbol": "SOLUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "zone", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone", "field": "lower"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "zone", "field": "upper"}},
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 20},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "zone", "field": "lower"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 044: Trend + BBands + RSI
    {
        "id": "S_044_trend_bbands",
        "name": "Trend BBands RSI",
        "desc": "Trend structure with BBands and RSI.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "trend", "type": "structure", "structure_type": "trend", "depends_on": {"swing": "swing"}, "params": {}},
            {"id": "bbands", "type": "indicator", "indicator_type": "bbands", "params": {"length": 20, "std": 2.0}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": "up"},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "bbands", "field": "lowerband"}},
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 40},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "bbands", "field": "upperband"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 045: Rolling + EMA ribbon
    {
        "id": "S_045_rolling_ribbon",
        "name": "Rolling EMA Ribbon",
        "desc": "Rolling high breakout with EMA ribbon.",
        "symbol": "ETHUSDT",
        "tf": "15m",
        "features": [
            {"id": "rolling_high", "type": "structure", "structure_type": "rolling_window", "params": {"size": 20, "field": "high", "mode": "max"}},
            {"id": "ema_8", "type": "indicator", "indicator_type": "ema", "params": {"length": 8}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "ema_55", "type": "indicator", "indicator_type": "ema", "params": {"length": 55}},
        ],
        "entry": [
            {"lhs": {"feature_id": "close"}, "op": "cross_above", "rhs": {"feature_id": "rolling_high", "field": "value"}},
            {"lhs": {"feature_id": "ema_8"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "ema_21"}, "op": "gt", "rhs": {"feature_id": "ema_55"}},
        ],
        "exit": [{"lhs": {"feature_id": "ema_8"}, "op": "lt", "rhs": {"feature_id": "ema_21"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 046: Swing + Stoch RSI + MACD
    {
        "id": "S_046_swing_stoch_macd",
        "name": "Swing Stoch MACD",
        "desc": "Swing pivot with Stochastic RSI and MACD.",
        "symbol": "SOLUSDT",
        "tf": "30m",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "stochrsi", "type": "indicator", "indicator_type": "stochrsi", "params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ],
        "entry": [
            {"lhs": {"feature_id": "swing", "field": "low_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "near_pct", "rhs": {"feature_id": "swing", "field": "low_level"}, "tolerance": 2.0},
            {"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "cross_above", "rhs": 20},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
        ],
        "exit": [{"lhs": {"feature_id": "stochrsi", "field": "stochrsi_k"}, "op": "gt", "rhs": 80}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 047: Fib + ATR stops
    {
        "id": "S_047_fib_atr",
        "name": "Fib ATR Stops",
        "desc": "Fibonacci entry with ATR-based stops.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing"}, "params": {"levels": [0.5, 0.618], "mode": "retracement"}},
            {"id": "atr", "type": "indicator", "indicator_type": "atr", "params": {"length": 14}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "fib", "field": "range"}, "op": "gt", "rhs": 100},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "level_0.618"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "fib", "field": "level_0.5"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "anchor_high"}}],
        "sl_type": "atr_multiple", "sl_val": 2.0, "sl_atr": "atr",
        "tp_type": "atr_multiple", "tp_val": 4.0, "tp_atr": "atr",
    },
    # 048: Zone + full indicator
    {
        "id": "S_048_zone_full",
        "name": "Zone Full Indicators",
        "desc": "Zone entry with EMA, RSI, MACD, ADX all aligned.",
        "symbol": "ETHUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
            {"id": "macd", "type": "indicator", "indicator_type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"id": "adx", "type": "indicator", "indicator_type": "adx", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "zone", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone", "field": "lower"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "zone", "field": "upper"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi"}, "op": "lt", "rhs": 50},
            {"lhs": {"feature_id": "macd", "field": "histogram"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "adx"}, "op": "gt", "rhs": 20},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "lt", "rhs": {"feature_id": "zone", "field": "lower"}}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
    # 049: Double structure
    {
        "id": "S_049_double_structure",
        "name": "Double Structure Combo",
        "desc": "Swing + Fibonacci + EMA alignment.",
        "symbol": "SOLUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "fib", "type": "structure", "structure_type": "fibonacci", "depends_on": {"swing": "swing"}, "params": {"levels": [0.382, 0.618], "mode": "retracement"}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
            {"id": "rsi", "type": "indicator", "indicator_type": "rsi", "params": {"length": 14}},
        ],
        "entry": [
            {"lhs": {"feature_id": "swing", "field": "high_level"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "fib", "field": "range"}, "op": "gt", "rhs": 0.3},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "fib", "field": "level_0.618"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
            {"lhs": {"feature_id": "rsi"}, "op": "between", "rhs": {"low": 40, "high": 60}},
        ],
        "exit": [{"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "swing", "field": "high_level"}}],
        "sl_type": "percent", "sl_val": 2.5,
        "tp_type": "percent", "tp_val": 5.0,
    },
    # 050: Triple structure
    {
        "id": "S_050_triple_structure",
        "name": "Triple Structure Setup",
        "desc": "Swing + Zone + Trend all aligned.",
        "symbol": "BTCUSDT",
        "tf": "1h",
        "features": [
            {"id": "swing", "type": "structure", "structure_type": "swing", "params": {"left": 5, "right": 5}},
            {"id": "zone", "type": "structure", "structure_type": "zone", "depends_on": {"swing": "swing"}, "params": {"zone_type": "demand", "width_atr": 1.0}},
            {"id": "trend", "type": "structure", "structure_type": "trend", "depends_on": {"swing": "swing"}, "params": {}},
            {"id": "ema_21", "type": "indicator", "indicator_type": "ema", "params": {"length": 21}},
        ],
        "entry": [
            {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": "up"},
            {"lhs": {"feature_id": "zone", "field": "lower"}, "op": "gt", "rhs": 0},
            {"lhs": {"feature_id": "close"}, "op": "gte", "rhs": {"feature_id": "zone", "field": "lower"}},
            {"lhs": {"feature_id": "close"}, "op": "lte", "rhs": {"feature_id": "zone", "field": "upper"}},
            {"lhs": {"feature_id": "close"}, "op": "gt", "rhs": {"feature_id": "ema_21"}},
        ],
        "exit": [{"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": "down"}],
        "sl_type": "percent", "sl_val": 2.0,
        "tp_type": "percent", "tp_val": 4.0,
    },
]

# Continue with tiers 6-10 in next part...
ALL_SETUPS = TIER_1_SETUPS + TIER_2_SETUPS + TIER_3_SETUPS + TIER_4_SETUPS + TIER_5_SETUPS

def format_feature(f: dict, tf: str) -> dict:
    """Format a feature for YAML output."""
    result = {
        "id": f["id"],
        "tf": tf,
        "type": f["type"],
    }
    if f["type"] == "indicator":
        result["indicator_type"] = f["indicator_type"]
        result["params"] = f["params"]
    elif f["type"] == "structure":
        result["structure_type"] = f["structure_type"]
        if "depends_on" in f:
            result["depends_on"] = f["depends_on"]
        result["params"] = f.get("params", {})
    return result


def format_condition(c: dict) -> dict:
    """Format a condition for YAML output."""
    result = {"lhs": c["lhs"], "op": c["op"], "rhs": c["rhs"]}
    if "tolerance" in c:
        result["tolerance"] = c["tolerance"]
    return result


def generate_yaml(setup: dict) -> str:
    """Generate YAML content for a setup."""
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
        f'execution_tf: "{setup["tf"]}"',
        '',
        'position_policy:',
        '  mode: "long_only"',
        '  max_positions_per_symbol: 1',
        '',
        'features:',
    ]

    # Add features
    for f in setup["features"]:
        feat = format_feature(f, setup["tf"])
        lines.append(f'  - id: "{feat["id"]}"')
        lines.append(f'    tf: "{feat["tf"]}"')
        lines.append(f'    type: {feat["type"]}')
        if feat["type"] == "indicator":
            lines.append(f'    indicator_type: {feat["indicator_type"]}')
            lines.append('    params:')
            for k, v in feat["params"].items():
                lines.append(f'      {k}: {v}')
        elif feat["type"] == "structure":
            lines.append(f'    structure_type: {feat["structure_type"]}')
            if "depends_on" in feat:
                lines.append('    depends_on:')
                for k, v in feat["depends_on"].items():
                    lines.append(f'      {k}: "{v}"')
            if feat["params"]:
                lines.append('    params:')
                for k, v in feat["params"].items():
                    if isinstance(v, list):
                        lines.append(f'      {k}: {v}')
                    elif isinstance(v, str):
                        lines.append(f'      {k}: "{v}"')
                    else:
                        lines.append(f'      {k}: {v}')
        lines.append('')

    # Add actions
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

        if "tolerance" in c:
            lines.append(f'              tolerance: {c["tolerance"]}')

    lines.append('        emit:')
    lines.append('          - action: entry_long')
    lines.append('    else:')
    lines.append('      emit:')
    lines.append('        - action: no_action')
    lines.append('')

    # Exit action
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
    """Generate all setup files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(ALL_SETUPS)} setups to {OUTPUT_DIR}")

    for setup in ALL_SETUPS:
        yaml_content = generate_yaml(setup)
        filepath = OUTPUT_DIR / f'{setup["id"]}.yml'
        with open(filepath, 'w', newline='\n') as f:
            f.write(yaml_content)
        print(f"  Created: {filepath.name}")

    print(f"\nGenerated {len(ALL_SETUPS)} setups")


if __name__ == "__main__":
    main()
