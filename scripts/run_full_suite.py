"""
Run the full indicator/operator/structure/pattern test suite.

Runs all plays sequentially on synthetic or real data.
Outputs a summary CSV and identifies failures, zero-trade plays, and bugs.

Usage:
    python scripts/run_full_suite.py [--suite SUITE] [--bars N]
    python scripts/run_full_suite.py --real --start 2025-10-01 --end 2026-01-01
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Map play IDs to their best synthetic pattern
# If not specified, defaults to "trending"
PLAY_PATTERN_MAP: dict[str, str] = {
    # Indicator suite - matched to indicator use case
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
    # CL plays
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
}

# Pattern suite plays use their own pattern (embedded in filename)
PATTERN_SUITE_PATTERNS = [
    "trending", "ranging", "volatile", "multi_tf_aligned",
    "trend_up_clean", "trend_down_clean", "trend_grinding",
    "trend_parabolic", "trend_exhaustion", "trend_stairs",
    "range_tight", "range_wide", "range_ascending", "range_descending",
    "reversal_v_bottom", "reversal_v_top", "reversal_double_bottom",
    "reversal_double_top", "breakout_clean", "breakout_false",
    "breakout_retest", "vol_squeeze_expand", "vol_spike_recover",
    "vol_spike_continue", "vol_decay", "liquidity_hunt_lows",
    "liquidity_hunt_highs", "choppy_whipsaw", "accumulation",
    "distribution", "mtf_aligned_bull", "mtf_aligned_bear",
    "mtf_pullback_bull", "mtf_pullback_bear",
]


def discover_plays(suite_dirs: list[Path]) -> list[str]:
    """Discover all play file stems from suite directories."""
    plays = []
    for d in suite_dirs:
        if d.exists():
            for f in sorted(d.glob("*.yml")):
                plays.append(f.stem)
    return plays


def get_pattern_for_play(play_stem: str) -> str:
    """Get the best synthetic pattern for a play."""
    # Direct lookup
    if play_stem in PLAY_PATTERN_MAP:
        return PLAY_PATTERN_MAP[play_stem]

    # Pattern suite: extract pattern from filename
    # PAT_001_trending -> trending
    m = re.match(r"PAT_\d+_(.*)", play_stem)
    if m:
        return m.group(1)

    return "trending"  # Default fallback


def run_play(
    play_stem: str,
    bars: int,
    pattern: str,
    max_retries: int = 5,
    real_data: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Run a single play and return results. Retries on DuckDB lock."""
    if real_data:
        cmd = [
            sys.executable, "trade_cli.py", "backtest", "run",
            "--play", play_stem,
            "--fix-gaps",
        ]
        if start_date:
            cmd.extend(["--start", start_date])
        if end_date:
            cmd.extend(["--end", end_date])
    else:
        cmd = [
            sys.executable, "trade_cli.py", "backtest", "run",
            "--play", play_stem,
            "--synthetic",
            "--synthetic-bars", str(bars),
            "--synthetic-pattern", pattern,
            "--no-artifacts",
        ]

    timeout_s = 600 if real_data else 120

    for attempt in range(max_retries):
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s,
                cwd=str(Path(__file__).parent.parent),
            )
            elapsed = time.time() - start_time

            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

            # Retry on DuckDB lock
            if exit_code != 0 and "being used by another process" in stderr:
                if attempt < max_retries - 1:
                    wait = 3 * (attempt + 1)
                    print(f"DB locked, retry {attempt+1}/{max_retries} in {wait}s...", end=" ", flush=True)
                    time.sleep(wait)
                    continue

            # Parse trade count and PnL from output
            trades = 0
            pnl = 0.0
            m = re.search(r"Trades:\s*(\d+)", stdout)
            if m:
                trades = int(m.group(1))
            m = re.search(r"PnL:\s*([-\d.]+)", stdout)
            if m:
                pnl = float(m.group(1))

            # Check for errors in stderr
            error_count = stderr.count("ERROR") + stderr.count("Error")
            warn_count = stderr.count("WARNING") + stderr.count("Warning")

            return {
                "play": play_stem,
                "pattern": pattern,
                "exit_code": exit_code,
                "trades": trades,
                "pnl": pnl,
                "elapsed_s": round(elapsed, 1),
                "errors": error_count,
                "warnings": warn_count,
                "status": "PASS" if exit_code == 0 else "FAIL",
                "error_msg": stderr[-200:] if exit_code != 0 else "",
            }

        except subprocess.TimeoutExpired:
            return {
                "play": play_stem,
                "pattern": pattern,
                "exit_code": -1,
                "trades": 0,
                "pnl": 0.0,
                "elapsed_s": float(timeout_s),
                "errors": 1,
                "warnings": 0,
                "status": "TIMEOUT",
                "error_msg": f"Timed out after {timeout_s}s",
            }
        except Exception as e:
            return {
                "play": play_stem,
                "pattern": pattern,
                "exit_code": -2,
                "trades": 0,
                "pnl": 0.0,
                "elapsed_s": 0,
                "errors": 1,
                "warnings": 0,
                "status": "ERROR",
                "error_msg": str(e)[:200],
            }

    # All retries exhausted (DuckDB lock)
    return {
        "play": play_stem,
        "pattern": pattern,
        "exit_code": -3,
        "trades": 0,
        "pnl": 0.0,
        "elapsed_s": 0,
        "errors": 1,
        "warnings": 0,
        "status": "DB_LOCKED",
        "error_msg": f"DuckDB locked after {max_retries} retries",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full test suite")
    parser.add_argument(
        "--suite", choices=["all", "indicator", "operator", "structure", "pattern", "cl"],
        default="all", help="Which suite(s) to run",
    )
    parser.add_argument("--bars", type=int, default=500, help="Synthetic bars")
    parser.add_argument("--start-from", type=str, default=None, help="Start from play ID")
    parser.add_argument("--real", action="store_true", help="Use real market data instead of synthetic")
    parser.add_argument("--start", type=str, default="2025-10-01", help="Start date for real data")
    parser.add_argument("--end", type=str, default="2026-01-01", help="End date for real data")
    args = parser.parse_args()

    plays_root = Path("plays")
    suite_map = {
        "cl": [plays_root / "complexity_ladder"],
        "indicator": [plays_root / "indicator_suite"],
        "operator": [plays_root / "operator_suite"],
        "structure": [plays_root / "structure_suite"],
        "pattern": [plays_root / "pattern_suite"],
    }

    if args.suite == "all":
        dirs = []
        for v in suite_map.values():
            dirs.extend(v)
    else:
        dirs = suite_map[args.suite]

    plays = discover_plays(dirs)

    if args.start_from:
        idx = next((i for i, p in enumerate(plays) if p == args.start_from), 0)
        plays = plays[idx:]

    mode = "real data" if args.real else f"synthetic data ({args.bars} bars each)"
    print(f"Running {len(plays)} plays on {mode}...")
    if args.real:
        print(f"  Date range: {args.start} to {args.end}")
    print("=" * 80)

    results = []
    pass_count = 0
    fail_count = 0
    zero_trade_count = 0

    for i, play in enumerate(plays, 1):
        pattern = get_pattern_for_play(play)
        label = f"{args.start}..{args.end}" if args.real else pattern
        print(f"[{i}/{len(plays)}] {play} ({label})...", end=" ", flush=True)

        result = run_play(
            play, args.bars, pattern,
            real_data=args.real,
            start_date=args.start if args.real else None,
            end_date=args.end if args.real else None,
        )
        results.append(result)

        status = result["status"]
        trades = result["trades"]
        elapsed = result["elapsed_s"]

        if status == "PASS":
            pass_count += 1
            if trades == 0:
                zero_trade_count += 1
                print(f"WARN 0-trades ({elapsed}s)")
            else:
                print(f"OK {trades} trades ({elapsed}s)")
        else:
            fail_count += 1
            print(f"FAIL: {result['error_msg'][:80]}")

    # Write CSV report
    report_name = "suite_report_real.csv" if args.real else "suite_report.csv"
    report_path = Path("backtests") / report_name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "play", "pattern", "status", "exit_code", "trades", "pnl",
            "elapsed_s", "errors", "warnings", "error_msg",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Summary
    print("\n" + "=" * 80)
    print(f"SUMMARY: {len(plays)} plays")
    print(f"  PASS:       {pass_count}")
    print(f"  FAIL:       {fail_count}")
    print(f"  0-trades:   {zero_trade_count}")
    print(f"  Report:     {report_path}")

    if fail_count > 0:
        print("\nFAILED PLAYS:")
        for r in results:
            if r["status"] != "PASS":
                print(f"  {r['play']}: {r['error_msg'][:100]}")

    if zero_trade_count > 0:
        print("\nZERO-TRADE PLAYS:")
        for r in results:
            if r["status"] == "PASS" and r["trades"] == 0:
                print(f"  {r['play']} ({r['pattern']})")


if __name__ == "__main__":
    main()
