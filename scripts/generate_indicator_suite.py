"""
Generate Play YAML files for the full indicator suite test.

Creates plays in plays/indicator_suite/ that test each of the 44 supported
indicators with appropriate conditions and matched synthetic patterns.

Usage:
    python scripts/generate_indicator_suite.py
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Output directory
# --------------------------------------------------------------------------
SUITE_DIR = Path("plays/indicator_suite")

# --------------------------------------------------------------------------
# Play template
# --------------------------------------------------------------------------
PLAY_TEMPLATE = """\
version: "3.0.0"
name: "{name}"
description: |
  Indicator Suite - {desc}

symbol: "{symbol}"

timeframes:
  low_tf: "{low_tf}"
  med_tf: "{med_tf}"
  high_tf: "{high_tf}"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 1.0
  margin_mode: "isolated_usdt"
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0
  slippage_bps: 2.0

features:
{features}
structures:
  exec: []

actions:
{actions}
position_policy:
  mode: "{mode}"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: {sl_pct}
  take_profit_pct: {tp_pct}
  max_position_pct: 100.0
"""

# --------------------------------------------------------------------------
# Indicator -> play spec mapping
# Each entry: (indicator_type, feature_key, params_yaml, conditions, pattern,
#              direction, description, extra_features)
# --------------------------------------------------------------------------

# Common account block helper
def _f(indicator: str, key: str, params: str, source: str = "") -> str:
    """Format a single feature block."""
    lines = [f"  {key}:", f"    indicator: {indicator}"]
    if source:
        lines.append(f"    source: {source}")
    lines.append(f"    params: {params}")
    return "\n".join(lines)


def _multi_f(*features: str) -> str:
    """Combine multiple feature blocks."""
    return "\n\n".join(features)


def _action_long(conditions: list[str]) -> str:
    """Format entry_long action block."""
    lines = ["  entry_long:", "    all:"]
    for c in conditions:
        lines.append(f"      - {c}")
    return "\n".join(lines)


def _action_short(conditions: list[str]) -> str:
    """Format entry_short action block."""
    lines = ["  entry_short:", "    all:"]
    for c in conditions:
        lines.append(f"      - {c}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# TIER 1: Single-Output Indicator Plays (one per indicator, long + short)
# --------------------------------------------------------------------------

SINGLE_OUTPUT_PLAYS = [
    # --- Moving Averages ---
    {
        "id": "001", "name": "ind_001_ema_trend_long",
        "desc": "EMA 50 trend filter - price above EMA in uptrend",
        "features": _f("ema", "ema_50", "{length: 50}"),
        "actions": _action_long(['["close", ">", "ema_50"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "002", "name": "ind_002_ema_trend_short",
        "desc": "EMA 50 trend filter - price below EMA in downtrend",
        "features": _f("ema", "ema_50", "{length: 50}"),
        "actions": _action_short(['["close", "<", "ema_50"]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "BTCUSDT",
    },
    {
        "id": "003", "name": "ind_003_sma_trend_long",
        "desc": "SMA 20 trend filter - price above SMA",
        "features": _f("sma", "sma_20", "{length: 20}"),
        "actions": _action_long(['["close", ">", "sma_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "004", "name": "ind_004_sma_trend_short",
        "desc": "SMA 20 trend filter - price below SMA",
        "features": _f("sma", "sma_20", "{length: 20}"),
        "actions": _action_short(['["close", "<", "sma_20"]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "ETHUSDT",
    },
    {
        "id": "005", "name": "ind_005_wma_trend_long",
        "desc": "WMA 20 trend - weighted moving average above price",
        "features": _f("wma", "wma_20", "{length: 20}"),
        "actions": _action_long(['["close", ">", "wma_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "006", "name": "ind_006_dema_trend_long",
        "desc": "DEMA 20 fast trend - double EMA filter",
        "features": _f("dema", "dema_20", "{length: 20}"),
        "actions": _action_long(['["close", ">", "dema_20"]']),
        "pattern": "trend_stairs", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "007", "name": "ind_007_tema_trend_long",
        "desc": "TEMA 20 fast trend - triple EMA filter",
        "features": _f("tema", "tema_20", "{length: 20}"),
        "actions": _action_long(['["close", ">", "tema_20"]']),
        "pattern": "trend_grinding", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "008", "name": "ind_008_trima_trend_long",
        "desc": "TRIMA 20 smoothed trend - triangular moving average",
        "features": _f("trima", "trima_20", "{length: 20}"),
        "actions": _action_long(['["close", ">", "trima_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "009", "name": "ind_009_zlma_trend_long",
        "desc": "ZLMA 20 zero-lag trend - responsive moving average",
        "features": _f("zlma", "zlma_20", "{length: 20}"),
        "actions": _action_long(['["close", ">", "zlma_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "010", "name": "ind_010_kama_trend_long",
        "desc": "KAMA 10 adaptive trend - Kaufman adaptive moving average",
        "features": _f("kama", "kama_10", "{length: 10}"),
        "actions": _action_long(['["close", ">", "kama_10"]']),
        "pattern": "trend_stairs", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "011", "name": "ind_011_alma_trend_long",
        "desc": "ALMA 10 smooth trend - Arnaud Legoux moving average",
        "features": _f("alma", "alma_10", "{length: 10, sigma: 6.0, offset: 0.85}"),
        "actions": _action_long(['["close", ">", "alma_10"]']),
        "pattern": "trend_grinding", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "012", "name": "ind_012_linreg_trend_long",
        "desc": "LINREG 14 regression trend - linear regression line",
        "features": _f("linreg", "linreg_14", "{length: 14}"),
        "actions": _action_long(['["close", ">", "linreg_14"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },

    # --- Oscillators ---
    {
        "id": "013", "name": "ind_013_rsi_oversold_long",
        "desc": "RSI 14 oversold bounce - buy when RSI drops below 40",
        "features": _f("rsi", "rsi_14", "{length: 14}"),
        "actions": _action_long(['["rsi_14", "<", 40]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "014", "name": "ind_014_rsi_overbought_short",
        "desc": "RSI 14 overbought fade - short when RSI exceeds 60",
        "features": _f("rsi", "rsi_14", "{length: 14}"),
        "actions": _action_short(['["rsi_14", ">", 60]']),
        "pattern": "reversal_v_top", "mode": "short_only", "symbol": "BTCUSDT",
    },
    {
        "id": "015", "name": "ind_015_cci_oversold_long",
        "desc": "CCI 14 oversold - buy when CCI below -50",
        "features": _f("cci", "cci_14", "{length: 14}"),
        "actions": _action_long(['["cci_14", "<", -50]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "016", "name": "ind_016_cci_overbought_short",
        "desc": "CCI 14 overbought - short when CCI above 50",
        "features": _f("cci", "cci_14", "{length: 14}"),
        "actions": _action_short(['["cci_14", ">", 50]']),
        "pattern": "reversal_v_top", "mode": "short_only", "symbol": "ETHUSDT",
    },
    {
        "id": "017", "name": "ind_017_willr_oversold_long",
        "desc": "Williams %R 14 oversold - buy below -60",
        "features": _f("willr", "willr_14", "{length: 14}"),
        "actions": _action_long(['["willr_14", "<", -60]']),
        "pattern": "range_wide", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "018", "name": "ind_018_willr_overbought_short",
        "desc": "Williams %R 14 overbought - short above -40",
        "features": _f("willr", "willr_14", "{length: 14}"),
        "actions": _action_short(['["willr_14", ">", -40]']),
        "pattern": "range_wide", "mode": "short_only", "symbol": "SOLUSDT",
    },
    {
        "id": "019", "name": "ind_019_cmo_oversold_long",
        "desc": "CMO 14 oversold - Chande Momentum below -20",
        "features": _f("cmo", "cmo_14", "{length: 14}"),
        "actions": _action_long(['["cmo_14", "<", -20]']),
        "pattern": "reversal_double_bottom", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "020", "name": "ind_020_mfi_oversold_long",
        "desc": "MFI 14 money flow oversold - buy below 40",
        "features": _f("mfi", "mfi_14", "{length: 14}"),
        "actions": _action_long(['["mfi_14", "<", 40]']),
        "pattern": "accumulation", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "021", "name": "ind_021_mfi_overbought_short",
        "desc": "MFI 14 money flow overbought - short above 60",
        "features": _f("mfi", "mfi_14", "{length: 14}"),
        "actions": _action_short(['["mfi_14", ">", 60]']),
        "pattern": "distribution", "mode": "short_only", "symbol": "ETHUSDT",
    },
    {
        "id": "022", "name": "ind_022_uo_oversold_long",
        "desc": "Ultimate Oscillator oversold - buy below 40",
        "features": _f("uo", "uo_7_14_28", "{fast: 7, medium: 14, slow: 28}"),
        "actions": _action_long(['["uo_7_14_28", "<", 40]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "SOLUSDT",
    },

    # --- Momentum (single-output) ---
    {
        "id": "023", "name": "ind_023_roc_positive_long",
        "desc": "ROC 10 positive rate of change - momentum up",
        "features": _f("roc", "roc_10", "{length: 10}"),
        "actions": _action_long(['["roc_10", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "024", "name": "ind_024_roc_negative_short",
        "desc": "ROC 10 negative rate of change - momentum down",
        "features": _f("roc", "roc_10", "{length: 10}"),
        "actions": _action_short(['["roc_10", "<", 0]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "BTCUSDT",
    },
    {
        "id": "025", "name": "ind_025_mom_positive_long",
        "desc": "MOM 10 positive momentum",
        "features": _f("mom", "mom_10", "{length: 10}"),
        "actions": _action_long(['["mom_10", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "026", "name": "ind_026_mom_negative_short",
        "desc": "MOM 10 negative momentum",
        "features": _f("mom", "mom_10", "{length: 10}"),
        "actions": _action_short(['["mom_10", "<", 0]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "ETHUSDT",
    },

    # --- Volume ---
    {
        "id": "027", "name": "ind_027_obv_rising_long",
        "desc": "OBV positive - on-balance volume rising",
        "features": _f("obv", "obv", "{}"),
        "actions": _action_long(['["obv", ">", 0]']),
        "pattern": "accumulation", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "028", "name": "ind_028_cmf_positive_long",
        "desc": "CMF 20 positive - Chaikin money flow accumulation",
        "features": _f("cmf", "cmf_20", "{length: 20}"),
        "actions": _action_long(['["cmf_20", ">", 0]']),
        "pattern": "accumulation", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "029", "name": "ind_029_cmf_negative_short",
        "desc": "CMF 20 negative - Chaikin money flow distribution",
        "features": _f("cmf", "cmf_20", "{length: 20}"),
        "actions": _action_short(['["cmf_20", "<", 0]']),
        "pattern": "distribution", "mode": "short_only", "symbol": "ETHUSDT",
    },
    {
        "id": "030", "name": "ind_030_vwap_above_long",
        "desc": "VWAP trend - price above VWAP",
        "features": _f("vwap", "vwap_d", '{anchor: "D"}'),
        "actions": _action_long(['["close", ">", "vwap_d"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },

    # --- Volatility (single-output) ---
    {
        "id": "031", "name": "ind_031_atr_filter_long",
        "desc": "ATR 14 volatility filter with EMA trend",
        "features": _multi_f(
            _f("atr", "atr_14", "{length: 14}"),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["close", ">", "ema_20"]', '["atr_14", ">", 0]']),
        "pattern": "vol_squeeze_expand", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "032", "name": "ind_032_natr_filter_long",
        "desc": "NATR 14 normalized volatility with EMA trend",
        "features": _multi_f(
            _f("natr", "natr_14", "{length: 14}"),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["close", ">", "ema_20"]', '["natr_14", ">", 0]']),
        "pattern": "vol_squeeze_expand", "mode": "long_only", "symbol": "BTCUSDT",
    },

    # --- Trivial ---
    {
        "id": "033", "name": "ind_033_ohlc4_above_ema",
        "desc": "OHLC4 average price above EMA 20",
        "features": _multi_f(
            _f("ohlc4", "ohlc4", "{}"),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["ohlc4", ">", "ema_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "034", "name": "ind_034_midprice_above_ema",
        "desc": "Midprice 14 above EMA 20",
        "features": _multi_f(
            _f("midprice", "midprice_14", "{length: 14}"),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["midprice_14", ">", "ema_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "ETHUSDT",
    },

    # --- Volume SMA source override test ---
    {
        "id": "035", "name": "ind_035_volume_sma_above",
        "desc": "Volume above its 20 SMA - volume surge filter",
        "features": _multi_f(
            _f("sma", "volume_sma_20", "{length: 20}", source="volume"),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["volume", ">", "volume_sma_20"]', '["close", ">", "ema_20"]']),
        "pattern": "breakout_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
]

# --------------------------------------------------------------------------
# TIER 2: Multi-Output Indicator Plays (testing sub-fields)
# --------------------------------------------------------------------------

MULTI_OUTPUT_PLAYS = [
    # --- MACD ---
    {
        "id": "036", "name": "ind_036_macd_histogram_long",
        "desc": "MACD histogram positive - bullish momentum",
        "features": _f("macd", "macd_12_26_9", "{fast: 12, slow: 26, signal: 9}"),
        "actions": _action_long(['["macd_12_26_9.histogram", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "037", "name": "ind_037_macd_signal_cross_long",
        "desc": "MACD line crosses above signal - bullish crossover",
        "features": _f("macd", "macd_12_26_9", "{fast: 12, slow: 26, signal: 9}"),
        "actions": _action_long(['["macd_12_26_9.macd", "cross_above", "macd_12_26_9.signal"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "038", "name": "ind_038_macd_signal_cross_short",
        "desc": "MACD line crosses below signal - bearish crossover",
        "features": _f("macd", "macd_12_26_9", "{fast: 12, slow: 26, signal: 9}"),
        "actions": _action_short(['["macd_12_26_9.macd", "cross_below", "macd_12_26_9.signal"]']),
        "pattern": "reversal_v_top", "mode": "short_only", "symbol": "BTCUSDT",
    },

    # --- BBands ---
    {
        "id": "039", "name": "ind_039_bbands_lower_bounce_long",
        "desc": "Bollinger Bands lower bounce - price near lower band",
        "features": _f("bbands", "bb_20_2", "{length: 20, std: 2.0}"),
        "actions": _action_long(['["close", "<", "bb_20_2.lower"]']),
        "pattern": "range_wide", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "040", "name": "ind_040_bbands_upper_bounce_short",
        "desc": "Bollinger Bands upper bounce - price near upper band",
        "features": _f("bbands", "bb_20_2", "{length: 20, std: 2.0}"),
        "actions": _action_short(['["close", ">", "bb_20_2.upper"]']),
        "pattern": "range_wide", "mode": "short_only", "symbol": "ETHUSDT",
    },
    {
        "id": "041", "name": "ind_041_bbands_percent_b_long",
        "desc": "Bollinger Bands percent_b oversold below 0.2",
        "features": _f("bbands", "bb_20_2", "{length: 20, std: 2.0}"),
        "actions": _action_long(['["bb_20_2.percent_b", "<", 0.2]']),
        "pattern": "range_wide", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "042", "name": "ind_042_bbands_bandwidth_expand",
        "desc": "Bollinger Bands bandwidth expanding - volatility breakout",
        "features": _multi_f(
            _f("bbands", "bb_20_2", "{length: 20, std: 2.0}"),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["bb_20_2.bandwidth", ">", 0.02]', '["close", ">", "ema_20"]']),
        "pattern": "vol_squeeze_expand", "mode": "long_only", "symbol": "BTCUSDT",
    },

    # --- Stochastic ---
    {
        "id": "043", "name": "ind_043_stoch_oversold_long",
        "desc": "Stochastic K below 30 oversold",
        "features": _f("stoch", "stoch_14_3_3", "{k: 14, d: 3, smooth_k: 3}"),
        "actions": _action_long(['["stoch_14_3_3.k", "<", 30]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "044", "name": "ind_044_stoch_kd_cross_long",
        "desc": "Stochastic K crosses above D - bullish momentum",
        "features": _f("stoch", "stoch_14_3_3", "{k: 14, d: 3, smooth_k: 3}"),
        "actions": _action_long(['["stoch_14_3_3.k", "cross_above", "stoch_14_3_3.d"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "045", "name": "ind_045_stoch_overbought_short",
        "desc": "Stochastic K above 70 overbought",
        "features": _f("stoch", "stoch_14_3_3", "{k: 14, d: 3, smooth_k: 3}"),
        "actions": _action_short(['["stoch_14_3_3.k", ">", 70]']),
        "pattern": "reversal_v_top", "mode": "short_only", "symbol": "BTCUSDT",
    },

    # --- StochRSI ---
    {
        "id": "046", "name": "ind_046_stochrsi_oversold_long",
        "desc": "StochRSI K below 20 deep oversold",
        "features": _f("stochrsi", "stochrsi_14", "{length: 14, rsi_length: 14, k: 3, d: 3}"),
        "actions": _action_long(['["stochrsi_14.k", "<", 20]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "047", "name": "ind_047_stochrsi_overbought_short",
        "desc": "StochRSI K above 80 overbought",
        "features": _f("stochrsi", "stochrsi_14", "{length: 14, rsi_length: 14, k: 3, d: 3}"),
        "actions": _action_short(['["stochrsi_14.k", ">", 80]']),
        "pattern": "reversal_v_top", "mode": "short_only", "symbol": "SOLUSDT",
    },

    # --- ADX ---
    {
        "id": "048", "name": "ind_048_adx_strong_trend_long",
        "desc": "ADX above 20 strong trend with DM+ > DM-",
        "features": _multi_f(
            _f("adx", "adx_14", "{length: 14}"),
            _f("ema", "ema_50", "{length: 50}"),
        ),
        "actions": _action_long([
            '["adx_14.adx", ">", 20]',
            '["adx_14.dmp", ">", "adx_14.dmn"]',
            '["close", ">", "ema_50"]',
        ]),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "049", "name": "ind_049_adx_bearish_short",
        "desc": "ADX above 20 with DM- > DM+ bearish",
        "features": _multi_f(
            _f("adx", "adx_14", "{length: 14}"),
            _f("ema", "ema_50", "{length: 50}"),
        ),
        "actions": _action_short([
            '["adx_14.adx", ">", 20]',
            '["adx_14.dmn", ">", "adx_14.dmp"]',
            '["close", "<", "ema_50"]',
        ]),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "BTCUSDT",
    },

    # --- Aroon ---
    {
        "id": "050", "name": "ind_050_aroon_bullish_long",
        "desc": "Aroon up above 70 - bullish trend",
        "features": _f("aroon", "aroon_25", "{length: 25}"),
        "actions": _action_long(['["aroon_25.up", ">", 70]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "051", "name": "ind_051_aroon_bearish_short",
        "desc": "Aroon down above 70 - bearish trend",
        "features": _f("aroon", "aroon_25", "{length: 25}"),
        "actions": _action_short(['["aroon_25.down", ">", 70]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "ETHUSDT",
    },
    {
        "id": "052", "name": "ind_052_aroon_osc_positive_long",
        "desc": "Aroon oscillator positive - bullish",
        "features": _f("aroon", "aroon_25", "{length: 25}"),
        "actions": _action_long(['["aroon_25.osc", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "SOLUSDT",
    },

    # --- Keltner Channel ---
    {
        "id": "053", "name": "ind_053_kc_lower_bounce_long",
        "desc": "Keltner Channel lower bounce - price below lower KC",
        "features": _f("kc", "kc_20_2", "{length: 20, scalar: 2.0}"),
        "actions": _action_long(['["close", "<", "kc_20_2.lower"]']),
        "pattern": "range_wide", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "054", "name": "ind_054_kc_upper_break_short",
        "desc": "Keltner Channel upper break - price above upper KC",
        "features": _f("kc", "kc_20_2", "{length: 20, scalar: 2.0}"),
        "actions": _action_short(['["close", ">", "kc_20_2.upper"]']),
        "pattern": "range_wide", "mode": "short_only", "symbol": "BTCUSDT",
    },

    # --- Donchian ---
    {
        "id": "055", "name": "ind_055_donchian_lower_long",
        "desc": "Donchian Channel lower bounce",
        "features": _f("donchian", "dc_20", "{lower_length: 20, upper_length: 20}"),
        "actions": _action_long(['["close", "<", "dc_20.lower"]']),
        "pattern": "range_descending", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "056", "name": "ind_056_donchian_breakout_long",
        "desc": "Donchian Channel breakout - price above upper",
        "features": _f("donchian", "dc_20", "{lower_length: 20, upper_length: 20}"),
        "actions": _action_long(['["close", ">", "dc_20.upper"]']),
        "pattern": "breakout_clean", "mode": "long_only", "symbol": "SOLUSDT",
    },

    # --- SuperTrend ---
    {
        "id": "057", "name": "ind_057_supertrend_bullish_long",
        "desc": "SuperTrend direction bullish (1)",
        "features": _f("supertrend", "st_10_3", "{length: 10, multiplier: 3.0}"),
        "actions": _action_long(['["st_10_3.direction", "==", 1]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "058", "name": "ind_058_supertrend_bearish_short",
        "desc": "SuperTrend direction bearish (-1)",
        "features": _f("supertrend", "st_10_3", "{length: 10, multiplier: 3.0}"),
        "actions": _action_short(['["st_10_3.direction", "==", -1]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "BTCUSDT",
    },

    # --- PSAR ---
    {
        "id": "059", "name": "ind_059_psar_reversal_long",
        "desc": "Parabolic SAR reversal signal - bullish flip",
        "features": _f("psar", "psar", "{af0: 0.02, af: 0.02, max_af: 0.2}"),
        "actions": _action_long(['["psar.reversal", "==", 1]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "060", "name": "ind_060_psar_long_active",
        "desc": "Parabolic SAR long SAR active (uptrend)",
        "features": _multi_f(
            _f("psar", "psar", "{af0: 0.02, af: 0.02, max_af: 0.2}"),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["close", ">", "ema_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "ETHUSDT",
    },

    # --- Squeeze ---
    {
        "id": "061", "name": "ind_061_squeeze_fire_long",
        "desc": "Squeeze momentum fires positive - breakout signal",
        "features": _multi_f(
            _f("squeeze", "sqz", "{bb_length: 20, bb_std: 2.0, kc_length: 20, kc_scalar: 1.5}"),
            _f("ema", "ema_50", "{length: 50}"),
        ),
        "actions": _action_long([
            '["sqz.sqz", ">", 0]',
            '["close", ">", "ema_50"]',
        ]),
        "pattern": "vol_squeeze_expand", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "062", "name": "ind_062_squeeze_on_detect",
        "desc": "Squeeze on detection - inside Keltner (consolidation)",
        "features": _multi_f(
            _f("squeeze", "sqz", "{bb_length: 20, bb_std: 2.0, kc_length: 20, kc_scalar: 1.5}"),
            _f("ema", "ema_50", "{length: 50}"),
        ),
        "actions": _action_long([
            '["sqz.on", "==", 1]',
            '["close", ">", "ema_50"]',
        ]),
        "pattern": "vol_squeeze_expand", "mode": "long_only", "symbol": "ETHUSDT",
    },

    # --- Vortex ---
    {
        "id": "063", "name": "ind_063_vortex_bullish_long",
        "desc": "Vortex VI+ > VI- bullish",
        "features": _f("vortex", "vortex_14", "{length: 14}"),
        "actions": _action_long(['["vortex_14.vip", ">", "vortex_14.vim"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "064", "name": "ind_064_vortex_bearish_short",
        "desc": "Vortex VI- > VI+ bearish",
        "features": _f("vortex", "vortex_14", "{length: 14}"),
        "actions": _action_short(['["vortex_14.vim", ">", "vortex_14.vip"]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "SOLUSDT",
    },

    # --- DM ---
    {
        "id": "065", "name": "ind_065_dm_bullish_long",
        "desc": "DM+ > DM- directional movement bullish",
        "features": _f("dm", "dm_14", "{length: 14}"),
        "actions": _action_long(['["dm_14.dmp", ">", "dm_14.dmn"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "066", "name": "ind_066_dm_bearish_short",
        "desc": "DM- > DM+ directional movement bearish",
        "features": _f("dm", "dm_14", "{length: 14}"),
        "actions": _action_short(['["dm_14.dmn", ">", "dm_14.dmp"]']),
        "pattern": "trend_down_clean", "mode": "short_only", "symbol": "BTCUSDT",
    },

    # --- Fisher ---
    {
        "id": "067", "name": "ind_067_fisher_bullish_long",
        "desc": "Fisher Transform positive - bullish momentum",
        "features": _f("fisher", "fisher_9", "{length: 9}"),
        "actions": _action_long(['["fisher_9.fisher", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "068", "name": "ind_068_fisher_cross_long",
        "desc": "Fisher crosses above signal - bullish crossover",
        "features": _f("fisher", "fisher_9", "{length: 9}"),
        "actions": _action_long(['["fisher_9.fisher", "cross_above", "fisher_9.signal"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "ETHUSDT",
    },

    # --- TSI ---
    {
        "id": "069", "name": "ind_069_tsi_bullish_long",
        "desc": "TSI positive - True Strength Index bullish",
        "features": _f("tsi", "tsi_13_25", "{fast: 13, slow: 25, signal: 13}"),
        "actions": _action_long(['["tsi_13_25.tsi", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "070", "name": "ind_070_tsi_cross_long",
        "desc": "TSI crosses above signal - bullish crossover",
        "features": _f("tsi", "tsi_13_25", "{fast: 13, slow: 25, signal: 13}"),
        "actions": _action_long(['["tsi_13_25.tsi", "cross_above", "tsi_13_25.signal"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "SOLUSDT",
    },

    # --- KVO ---
    {
        "id": "071", "name": "ind_071_kvo_bullish_long",
        "desc": "KVO positive - Klinger Volume Oscillator bullish",
        "features": _f("kvo", "kvo_34_55", "{fast: 34, slow: 55, signal: 13}"),
        "actions": _action_long(['["kvo_34_55.kvo", ">", 0]']),
        "pattern": "accumulation", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "072", "name": "ind_072_kvo_cross_long",
        "desc": "KVO crosses above signal - bullish crossover",
        "features": _f("kvo", "kvo_34_55", "{fast: 34, slow: 55, signal: 13}"),
        "actions": _action_long(['["kvo_34_55.kvo", "cross_above", "kvo_34_55.signal"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "BTCUSDT",
    },

    # --- TRIX ---
    {
        "id": "073", "name": "ind_073_trix_bullish_long",
        "desc": "TRIX positive - triple EMA rate of change bullish",
        "features": _f("trix", "trix_18_9", "{length: 18, signal: 9}"),
        "actions": _action_long(['["trix_18_9.trix", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "074", "name": "ind_074_trix_cross_long",
        "desc": "TRIX crosses above signal - bullish crossover",
        "features": _f("trix", "trix_18_9", "{length: 18, signal: 9}"),
        "actions": _action_long(['["trix_18_9.trix", "cross_above", "trix_18_9.signal"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "ETHUSDT",
    },

    # --- PPO ---
    {
        "id": "075", "name": "ind_075_ppo_histogram_long",
        "desc": "PPO histogram positive - momentum bullish",
        "features": _f("ppo", "ppo_12_26_9", "{fast: 12, slow: 26, signal: 9}"),
        "actions": _action_long(['["ppo_12_26_9.histogram", ">", 0]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "076", "name": "ind_076_ppo_cross_long",
        "desc": "PPO crosses above signal - bullish crossover",
        "features": _f("ppo", "ppo_12_26_9", "{fast: 12, slow: 26, signal: 9}"),
        "actions": _action_long(['["ppo_12_26_9.ppo", "cross_above", "ppo_12_26_9.signal"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "SOLUSDT",
    },
]

# --------------------------------------------------------------------------
# TIER 3: Crossover / MA Combo Plays (EMA cross patterns)
# --------------------------------------------------------------------------

CROSSOVER_PLAYS = [
    {
        "id": "077", "name": "ind_077_ema_cross_9_21_long",
        "desc": "EMA 9/21 golden cross - fast crosses above slow",
        "features": _multi_f(
            _f("ema", "ema_9", "{length: 9}"),
            _f("ema", "ema_21", "{length: 21}"),
        ),
        "actions": _action_long(['["ema_9", "cross_above", "ema_21"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "078", "name": "ind_078_ema_cross_9_21_short",
        "desc": "EMA 9/21 death cross - fast crosses below slow",
        "features": _multi_f(
            _f("ema", "ema_9", "{length: 9}"),
            _f("ema", "ema_21", "{length: 21}"),
        ),
        "actions": _action_short(['["ema_9", "cross_below", "ema_21"]']),
        "pattern": "reversal_v_top", "mode": "short_only", "symbol": "BTCUSDT",
    },
    {
        "id": "079", "name": "ind_079_sma_cross_10_30_long",
        "desc": "SMA 10/30 golden cross",
        "features": _multi_f(
            _f("sma", "sma_10", "{length: 10}"),
            _f("sma", "sma_30", "{length: 30}"),
        ),
        "actions": _action_long(['["sma_10", "cross_above", "sma_30"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "080", "name": "ind_080_dema_cross_10_30_long",
        "desc": "DEMA 10/30 fast cross above slow",
        "features": _multi_f(
            _f("dema", "dema_10", "{length: 10}"),
            _f("dema", "dema_30", "{length: 30}"),
        ),
        "actions": _action_long(['["dema_10", "cross_above", "dema_30"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "SOLUSDT",
    },
    {
        "id": "081", "name": "ind_081_tema_cross_10_30_long",
        "desc": "TEMA 10/30 triple EMA crossover",
        "features": _multi_f(
            _f("tema", "tema_10", "{length: 10}"),
            _f("tema", "tema_30", "{length: 30}"),
        ),
        "actions": _action_long(['["tema_10", "cross_above", "tema_30"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "BTCUSDT",
    },
    {
        "id": "082", "name": "ind_082_wma_cross_10_30_long",
        "desc": "WMA 10/30 weighted MA crossover",
        "features": _multi_f(
            _f("wma", "wma_10", "{length: 10}"),
            _f("wma", "wma_30", "{length: 30}"),
        ),
        "actions": _action_long(['["wma_10", "cross_above", "wma_30"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "ETHUSDT",
    },
    {
        "id": "083", "name": "ind_083_zlma_cross_10_30_long",
        "desc": "ZLMA 10/30 zero-lag crossover",
        "features": _multi_f(
            _f("zlma", "zlma_10", "{length: 10}"),
            _f("zlma", "zlma_30", "{length: 30}"),
        ),
        "actions": _action_long(['["zlma_10", "cross_above", "zlma_30"]']),
        "pattern": "reversal_v_bottom", "mode": "long_only", "symbol": "SOLUSDT",
    },
]

# --------------------------------------------------------------------------
# TIER 4: Anchored VWAP (special test)
# --------------------------------------------------------------------------

SPECIAL_PLAYS = [
    {
        "id": "084", "name": "ind_084_anchored_vwap_long",
        "desc": "Anchored VWAP above price with EMA filter",
        "features": _multi_f(
            _f("anchored_vwap", "avwap", '{anchor_source: "swing_any"}'),
            _f("ema", "ema_20", "{length: 20}"),
        ),
        "actions": _action_long(['["close", ">", "ema_20"]']),
        "pattern": "trend_up_clean", "mode": "long_only", "symbol": "BTCUSDT",
        "needs_structure": True,
    },
]


# --------------------------------------------------------------------------
# Combine all plays
# --------------------------------------------------------------------------

ALL_PLAYS = (
    SINGLE_OUTPUT_PLAYS
    + MULTI_OUTPUT_PLAYS
    + CROSSOVER_PLAYS
    + SPECIAL_PLAYS
)


def generate_play(spec: dict) -> str:
    """Generate a play YAML string from a spec dict."""
    # Determine if anchored_vwap needs swing structure
    structures_block = "structures:\n  exec: []"
    if spec.get("needs_structure"):
        structures_block = (
            "structures:\n"
            "  exec:\n"
            "    - type: swing\n"
            "      key: swing\n"
            "      params: {left: 5, right: 5}"
        )

    play = PLAY_TEMPLATE.format(
        name=spec["name"],
        desc=spec["desc"],
        symbol=spec.get("symbol", "BTCUSDT"),
        low_tf=spec.get("low_tf", "15m"),
        med_tf=spec.get("med_tf", "1h"),
        high_tf=spec.get("high_tf", "D"),
        features=spec["features"],
        actions=spec["actions"],
        mode=spec.get("mode", "long_only"),
        sl_pct=spec.get("sl_pct", 3.0),
        tp_pct=spec.get("tp_pct", 6.0),
    )

    # Replace the empty structures block with the correct one
    if spec.get("needs_structure"):
        play = play.replace("structures:\n  exec: []", structures_block)

    return play


def main() -> None:
    """Generate all indicator suite plays."""
    SUITE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(ALL_PLAYS)} indicator suite plays...")

    for spec in ALL_PLAYS:
        play_id = spec["id"]
        name = spec["name"]
        filename = f"IND_{play_id}_{name.replace('ind_' + play_id + '_', '')}.yml"
        filepath = SUITE_DIR / filename

        content = generate_play(spec)

        with open(filepath, "w", newline="\n") as f:
            f.write(content)

        print(f"  Created: {filepath.name}")

    print(f"\nDone! {len(ALL_PLAYS)} plays written to {SUITE_DIR}/")

    # Summary stats
    long_count = sum(1 for s in ALL_PLAYS if s.get("mode") == "long_only")
    short_count = sum(1 for s in ALL_PLAYS if s.get("mode") == "short_only")
    print(f"  Long-only: {long_count}")
    print(f"  Short-only: {short_count}")

    # Unique indicators
    indicators_used = set()
    for spec in ALL_PLAYS:
        features_text = spec["features"]
        for line in features_text.split("\n"):
            if "indicator:" in line:
                indicators_used.add(line.split("indicator:")[1].strip())
    print(f"  Unique indicators tested: {len(indicators_used)}")
    print(f"  Indicators: {sorted(indicators_used)}")


if __name__ == "__main__":
    main()
