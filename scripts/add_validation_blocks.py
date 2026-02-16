"""
One-shot script to add `validation:` blocks to all validation play YAMLs.

For plays that already have `synthetic:` blocks, renames to `validation:` and
drops bars/seed (keeps only pattern).

For plays without, adds `validation:\n  pattern: X` based on the pattern map
or filename-derived pattern.

Run: python scripts/add_validation_blocks.py
"""

from __future__ import annotations

import re
from pathlib import Path

# Pattern map: play_stem -> synthetic pattern
# Sourced from run_full_suite.py PLAY_PATTERN_MAP + derived patterns
PLAY_PATTERN_MAP: dict[str, str] = {
    # Indicator suite
    "IND_001_ema_trend_long": "trend_up_clean",
    "IND_002_ema_trend_short": "trend_down_clean",
    "IND_003_sma_trend_long": "trend_up_clean",
    "IND_004_sma_trend_short": "trend_down_clean",
    "IND_005_wma_trend_long": "trend_up_clean",
    "IND_006_dema_trend_long": "trend_stairs",
    "IND_007_tema_trend_long": "trend_grinding",
    "IND_008_trima_trend_long": "trend_up_clean",
    "IND_009_zlma_trend_long": "trend_up_clean",
    "IND_010_kama_trend_long": "trend_stairs",
    "IND_011_alma_trend_long": "trend_grinding",
    "IND_012_linreg_trend_long": "trend_up_clean",
    "IND_013_rsi_oversold_long": "reversal_v_bottom",
    "IND_014_rsi_overbought_short": "reversal_v_top",
    "IND_015_cci_oversold_long": "reversal_v_bottom",
    "IND_016_cci_overbought_short": "reversal_v_top",
    "IND_017_willr_oversold_long": "range_wide",
    "IND_018_willr_overbought_short": "range_wide",
    "IND_019_cmo_oversold_long": "reversal_double_bottom",
    "IND_020_mfi_oversold_long": "accumulation",
    "IND_021_mfi_overbought_short": "distribution",
    "IND_022_uo_oversold_long": "reversal_v_bottom",
    "IND_023_roc_positive_long": "trend_up_clean",
    "IND_024_roc_negative_short": "trend_down_clean",
    "IND_025_mom_positive_long": "trend_up_clean",
    "IND_026_mom_negative_short": "trend_down_clean",
    "IND_027_obv_rising_long": "accumulation",
    "IND_028_cmf_positive_long": "accumulation",
    "IND_029_cmf_negative_short": "distribution",
    "IND_030_vwap_above_long": "trend_up_clean",
    "IND_031_atr_filter_long": "vol_squeeze_expand",
    "IND_032_natr_filter_long": "vol_squeeze_expand",
    "IND_033_ohlc4_above_ema": "trend_up_clean",
    "IND_034_midprice_above_ema": "trend_up_clean",
    "IND_035_volume_sma_above": "breakout_clean",
    "IND_036_macd_histogram_long": "trend_up_clean",
    "IND_037_macd_signal_cross_long": "reversal_v_bottom",
    "IND_038_macd_signal_cross_short": "reversal_v_top",
    "IND_039_bbands_lower_bounce_long": "range_wide",
    "IND_040_bbands_upper_bounce_short": "range_wide",
    "IND_041_bbands_percent_b_long": "range_wide",
    "IND_042_bbands_bandwidth_expand": "vol_squeeze_expand",
    "IND_043_stoch_oversold_long": "reversal_v_bottom",
    "IND_044_stoch_kd_cross_long": "reversal_v_bottom",
    "IND_045_stoch_overbought_short": "reversal_v_top",
    "IND_046_stochrsi_oversold_long": "reversal_v_bottom",
    "IND_047_stochrsi_overbought_short": "reversal_v_top",
    "IND_048_adx_strong_trend_long": "trend_up_clean",
    "IND_049_adx_bearish_short": "trend_down_clean",
    "IND_050_aroon_bullish_long": "trend_up_clean",
    "IND_051_aroon_bearish_short": "trend_down_clean",
    "IND_052_aroon_osc_positive_long": "trend_up_clean",
    "IND_053_kc_lower_bounce_long": "range_wide",
    "IND_054_kc_upper_break_short": "range_wide",
    "IND_055_donchian_lower_long": "range_descending",
    "IND_056_donchian_breakout_long": "breakout_clean",
    "IND_057_supertrend_bullish_long": "trend_up_clean",
    "IND_058_supertrend_bearish_short": "trend_down_clean",
    "IND_059_psar_reversal_long": "reversal_v_bottom",
    "IND_060_psar_long_active": "trend_up_clean",
    "IND_061_squeeze_fire_long": "vol_squeeze_expand",
    "IND_062_squeeze_on_detect": "vol_squeeze_expand",
    "IND_063_vortex_bullish_long": "trend_up_clean",
    "IND_064_vortex_bearish_short": "trend_down_clean",
    "IND_065_dm_bullish_long": "trend_up_clean",
    "IND_066_dm_bearish_short": "trend_down_clean",
    "IND_067_fisher_bullish_long": "trend_up_clean",
    "IND_068_fisher_cross_long": "reversal_v_bottom",
    "IND_069_tsi_bullish_long": "trend_up_clean",
    "IND_070_tsi_cross_long": "reversal_v_bottom",
    "IND_071_kvo_bullish_long": "accumulation",
    "IND_072_kvo_cross_long": "reversal_v_bottom",
    "IND_073_trix_bullish_long": "trend_up_clean",
    "IND_074_trix_cross_long": "reversal_v_bottom",
    "IND_075_ppo_histogram_long": "trend_up_clean",
    "IND_076_ppo_cross_long": "reversal_v_bottom",
    "IND_077_ema_cross_9_21_long": "reversal_v_bottom",
    "IND_078_ema_cross_9_21_short": "reversal_v_top",
    "IND_079_sma_cross_10_30_long": "reversal_v_bottom",
    "IND_080_dema_cross_10_30_long": "reversal_v_bottom",
    "IND_081_tema_cross_10_30_long": "reversal_v_bottom",
    "IND_082_wma_cross_10_30_long": "reversal_v_bottom",
    "IND_083_zlma_cross_10_30_long": "reversal_v_bottom",
    "IND_084_anchored_vwap_long": "trend_up_clean",
    # Operator suite
    "OP_001_gt": "trending",
    "OP_002_lt": "ranging",
    "OP_003_gte": "trending",
    "OP_004_lte": "ranging",
    "OP_005_eq_int": "trend_up_clean",
    "OP_006_neq": "trend_up_clean",
    "OP_007_cross_above": "reversal_v_bottom",
    "OP_008_cross_below": "reversal_v_top",
    "OP_009_between": "ranging",
    "OP_010_near_pct": "ranging",
    "OP_011_near_abs": "ranging",
    "OP_012_arithmetic_add": "trend_up_clean",
    "OP_013_arithmetic_sub": "reversal_v_bottom",
    "OP_014_arithmetic_mul": "trend_up_clean",
    "OP_015_arithmetic_div": "breakout_clean",
    "OP_016_nested_any": "ranging",
    "OP_017_not": "trend_up_clean",
    "OP_018_holds_for": "ranging",
    "OP_019_occurred_within": "reversal_v_bottom",
    "OP_020_cases_when": "reversal_v_bottom",
    "OP_021_variables": "ranging",
    "OP_022_metadata": "reversal_v_bottom",
    "OP_023_higher_tf_feature": "trend_up_clean",
    "OP_024_exit_signal": "ranging",
    "OP_025_multi_case": "ranging",
    # Structure suite
    "STR_001_swing_basic": "trending",
    "STR_002_trend_direction": "trend_up_clean",
    "STR_003_ms_bos": "trending",
    "STR_004_ms_choch": "reversal_v_bottom",
    "STR_005_fibonacci": "trending",
    "STR_006_derived_zone": "trending",
    "STR_007_zone_demand": "reversal_v_bottom",
    "STR_008_zone_supply": "reversal_v_top",
    "STR_009_rolling_min": "trending",
    "STR_010_rolling_max": "trend_down_clean",
    "STR_011_full_chain": "trending",
    "STR_012_multi_tf": "trending",
    "STR_013_all_types": "trending",
    "STR_014_trend_short": "trend_down_clean",
    # Complexity suite
    "CL_001": "trending",
    "CL_002": "reversal_v_bottom",
    "CL_003": "ranging",
    "CL_004": "ranging",
    "CL_005": "trend_down_clean",
    "CL_006": "trending",
    "CL_007": "trend_down_clean",
    "CL_008": "trending",
    "CL_009": "trending",
    "CL_010": "trending",
    "CL_011": "trending",
    "CL_012": "trending",
    "CL_013": "trending",
    # Core validation
    "V_CORE_001_indicator_cross": "trend_up_clean",
    "V_CORE_002_structure_chain": "trending",
    "V_CORE_003_cases_metadata": "reversal_v_bottom",
    "V_CORE_004_multi_tf": "trend_up_clean",
    "V_CORE_005_arithmetic_window": "trending",
    # Limit orders
    "LO_001_limit_entry_basic": "trend_up_clean",
    "LO_002_tp_as_limit": "trend_up_clean",
    "LO_003_all_defaults": "trend_up_clean",
    "LO_004_tp_fee_comparison": "trend_up_clean",
    "LO_005_limit_with_expiry": "trend_up_clean",
    "LO_006_limit_short_entry": "trend_down_clean",
    "LO_007_postonly_tif": "trend_up_clean",
    "LO_008_ioc_tif": "trend_up_clean",
    # Price features
    "PF_001_last_price_gt_ema": "trend_up_clean",
    "PF_002_mark_price_near_ema": "ranging",
    "PF_003_last_price_cross_ema": "reversal_v_bottom",
    "PF_004_last_price_short": "trend_down_clean",
    "PF_005_both_prices_combined": "trend_up_clean",
    "PF_006_last_price_arithmetic": "trend_up_clean",
}


def get_pattern_for_play(stem: str) -> str:
    """Get the best synthetic pattern for a play stem."""
    # Direct lookup
    if stem in PLAY_PATTERN_MAP:
        return PLAY_PATTERN_MAP[stem]

    # Pattern suite: extract from filename (PAT_001_trending -> trending)
    m = re.match(r"PAT_\d+_(.*)", stem)
    if m:
        return m.group(1)

    # Default fallback
    return "trending"


def process_play(play_path: Path) -> str:
    """Process a single play YAML file.

    Returns a status string: 'added', 'converted', or 'skipped'.
    """
    content = play_path.read_text(encoding="utf-8")
    stem = play_path.stem
    pattern = get_pattern_for_play(stem)

    # Check if it already has a validation: block
    if re.search(r"^validation:\s*$", content, re.MULTILINE):
        return "skipped"

    # Check if it has a synthetic: block — convert it
    if re.search(r"^synthetic:\s*$", content, re.MULTILINE):
        # Replace the entire synthetic: block with validation: block
        # Remove synthetic: and its indented children (bars, seed, pattern)
        # Then add validation: with just pattern

        # Remove the synthetic block (key + indented lines)
        new_content = re.sub(
            r"^synthetic:\s*\n(?:  \w+:.*\n)*",
            f"validation:\n  pattern: \"{pattern}\"\n",
            content,
            flags=re.MULTILINE,
        )
        play_path.write_text(new_content, encoding="utf-8", newline="\n")
        return "converted"

    # No synthetic: or validation: block — add validation: at the end
    # Ensure file ends with a newline before appending
    if not content.endswith("\n"):
        content += "\n"
    content += f"\nvalidation:\n  pattern: \"{pattern}\"\n"
    play_path.write_text(content, encoding="utf-8", newline="\n")
    return "added"


def main() -> None:
    plays_root = Path("plays") / "validation"
    if not plays_root.exists():
        print(f"ERROR: {plays_root} does not exist")
        return

    play_files = sorted(plays_root.rglob("*.yml"))
    print(f"Processing {len(play_files)} validation plays...")

    added = 0
    converted = 0
    skipped = 0

    for pf in play_files:
        status = process_play(pf)
        if status == "added":
            added += 1
            print(f"  + {pf.stem}: added validation block")
        elif status == "converted":
            converted += 1
            print(f"  ~ {pf.stem}: converted synthetic -> validation")
        else:
            skipped += 1
            print(f"  = {pf.stem}: already has validation block")

    print(f"\nDone: {added} added, {converted} converted, {skipped} skipped")


if __name__ == "__main__":
    main()
