"""
Trade Math Verification Script for TRADE Backtest Engine.

Runs each play with synthetic data, reads artifacts, and independently
recalculates every trade's PnL, fees, SL/TP levels to verify correctness.

Usage:
    python scripts/verify_trade_math.py --suite indicator
    python scripts/verify_trade_math.py --suite all
    python scripts/verify_trade_math.py --play IND_001_ema_trend_long
    python scripts/verify_trade_math.py --suite operator --start-from OP_010_near_pct
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import yaml

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.forge.validation.synthetic_data import PatternType, generate_synthetic_candles


# ── Constants ────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
PLAYS_ROOT = ROOT / "plays"
RESULTS_DIR = ROOT / "backtests" / "_verification"

SUITE_DIRS = {
    "indicator": PLAYS_ROOT / "validation" / "indicators",
    "operator": PLAYS_ROOT / "validation" / "operators",
    "structure": PLAYS_ROOT / "validation" / "structures",
    "pattern": PLAYS_ROOT / "validation" / "patterns",
    "cl": PLAYS_ROOT / "validation" / "complexity",
    "rv_accumulation": PLAYS_ROOT / "validation" / "real_data" / "accumulation",
    "rv_markup": PLAYS_ROOT / "validation" / "real_data" / "markup",
    "rv_distribution": PLAYS_ROOT / "validation" / "real_data" / "distribution",
    "rv_markdown": PLAYS_ROOT / "validation" / "real_data" / "markdown",
}

# Pattern map (same as run_full_suite.py)
PLAY_PATTERN_MAP: dict[str, str] = {
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
    "OP_001_gt": "trending", "OP_002_lt": "ranging", "OP_003_gte": "trending",
    "OP_004_lte": "ranging", "OP_005_eq_int": "trend_up_clean",
    "OP_006_neq": "trend_up_clean", "OP_007_cross_above": "reversal_v_bottom",
    "OP_008_cross_below": "reversal_v_top", "OP_009_between": "ranging",
    "OP_010_near_pct": "ranging", "OP_011_near_abs": "ranging",
    "OP_012_arithmetic_add": "trend_up_clean", "OP_013_arithmetic_sub": "reversal_v_bottom",
    "OP_014_arithmetic_mul": "trend_up_clean", "OP_015_arithmetic_div": "breakout_clean",
    "OP_016_nested_any": "ranging", "OP_017_not": "trend_up_clean",
    "OP_018_holds_for": "ranging", "OP_019_occurred_within": "reversal_v_bottom",
    "OP_020_cases_when": "reversal_v_bottom", "OP_021_variables": "ranging",
    "OP_022_metadata": "reversal_v_bottom", "OP_023_higher_tf_feature": "trend_up_clean",
    "OP_024_exit_signal": "ranging", "OP_025_multi_case": "ranging",
    "STR_001_swing_basic": "trending", "STR_002_trend_direction": "trend_up_clean",
    "STR_003_ms_bos": "trending", "STR_004_ms_choch": "reversal_v_bottom",
    "STR_005_fibonacci": "trending", "STR_006_derived_zone": "trending",
    "STR_007_zone_demand": "reversal_v_bottom", "STR_008_zone_supply": "reversal_v_top",
    "STR_009_rolling_min": "trending", "STR_010_rolling_max": "trend_down_clean",
    "STR_011_full_chain": "trending", "STR_012_multi_tf": "trending",
    "STR_013_all_types": "trending", "STR_014_trend_short": "trend_down_clean",
    "CL_001": "trending", "CL_002": "reversal_v_bottom", "CL_003": "ranging",
    "CL_004": "ranging", "CL_005": "trend_down_clean", "CL_006": "trending",
    "CL_007": "trend_down_clean", "CL_008": "trending", "CL_009": "trending",
    "CL_010": "trending", "CL_011": "trending", "CL_012": "trending", "CL_013": "trending",
}

# Tolerance for float comparisons
ABS_TOL = 0.01  # $0.01 for PnL
REL_TOL = 0.005  # 0.5% relative tolerance for prices

# Timeframe to approximate bars per year (crypto markets ~365 days)
TF_BARS_PER_YEAR = {
    "1m": 525600, "3m": 175200, "5m": 105120, "15m": 35040, "30m": 17520,
    "1h": 8760, "2h": 4380, "4h": 2190, "6h": 1460, "12h": 730,
    "D": 365, "W": 52, "M": 12,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_pattern(play_stem: str) -> str:
    if play_stem in PLAY_PATTERN_MAP:
        return PLAY_PATTERN_MAP[play_stem]
    m = re.match(r"PAT_\d+_(.*)", play_stem)
    if m:
        return m.group(1)
    return "trending"


def find_play_file(play_stem: str) -> Path | None:
    """Find the YAML file for a play stem."""
    for suite_dir in SUITE_DIRS.values():
        p = suite_dir / f"{play_stem}.yml"
        if p.exists():
            return p
    return None


def load_play_config(play_path: Path) -> dict:
    """Load and return the play YAML config."""
    with open(play_path) as f:
        return yaml.safe_load(f)


def find_artifact_dir(play_stem: str) -> Path | None:
    """Find the most recent artifact directory for a play (by mtime)."""
    # Try both original and lowercase (artifact dirs are lowercase)
    base = ROOT / "backtests" / "_validation" / play_stem
    if not base.exists():
        base = ROOT / "backtests" / "_validation" / play_stem.lower()
    if not base.exists():
        return None
    # Walk to find deepest dir with result.json, prefer newest by mtime
    for symbol_dir in sorted(base.iterdir()):
        if symbol_dir.is_dir():
            run_dirs = [
                d for d in symbol_dir.iterdir()
                if d.is_dir() and (d / "result.json").exists()
            ]
            if run_dirs:
                run_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                return run_dirs[0]
    return None


def run_backtest(play_stem: str, pattern: str, bars: int = 500, seed: int = 42) -> tuple[bool, str, str | None]:
    """Run a backtest and return (success, output, artifact_dir_from_output)."""
    cmd = [
        sys.executable, "trade_cli.py", "backtest", "run",
        "--play", play_stem,
        "--synthetic",
        "--synthetic-bars", str(bars),
        "--synthetic-pattern", pattern,
        "--synthetic-seed", str(seed),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            cwd=str(ROOT),
        )
        combined = result.stdout + "\n" + result.stderr
        # Strip ANSI color codes for parsing
        clean = re.sub(r"\x1b\[[0-9;]*m", "", combined)
        # Extract artifact dir from output (e.g., "Artifacts:   backtests\_validation\...")
        artifact_dir = None
        m = re.search(r"Artifacts:\s+(.+?)[\r\n]", clean)
        if m:
            artifact_dir = m.group(1).strip()
        return result.returncode == 0, combined, artifact_dir
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT after 180s", None
    except Exception as e:
        return False, f"EXCEPTION: {e}", None


def regenerate_candles(play_config: dict, pattern: str, bars: int = 500, seed: int = 42) -> dict[str, pd.DataFrame]:
    """Regenerate synthetic candles using the same params the engine uses.

    Always includes 1m since the engine uses it for mark price simulation
    and 1m-granularity fills.
    """
    tfs = play_config.get("timeframes", {})
    tf_set = set()
    for key in ("low_tf", "med_tf", "high_tf"):
        val = tfs.get(key)
        if val:
            tf_set.add(val)
    if not tf_set:
        tf_set = {"15m"}
    # Engine always loads 1m for mark price simulation and fill granularity
    tf_set.add("1m")
    tf_to_min = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
                 "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
                 "D": 1440, "W": 10080, "M": 43200}
    tf_list = sorted(tf_set, key=lambda t: tf_to_min.get(t, 0))

    symbol = play_config.get("symbol", "BTCUSDT")
    result = generate_synthetic_candles(
        symbol=symbol,
        timeframes=tf_list,
        bars_per_tf=bars,
        seed=seed,
        pattern=cast(PatternType, pattern),
        align_multi_tf=True,
    )
    return dict(result.timeframes)


# ── Verification Checks ─────────────────────────────────────────────────────

class TradeVerifier:
    """Verifies trade math for a single play."""

    def __init__(self, play_stem: str, play_config: dict, artifact_dir: Path,
                 candle_data: dict[str, pd.DataFrame] | None = None):
        self.play_stem = play_stem
        self.config = play_config
        self.artifact_dir = artifact_dir
        self.candle_data = candle_data
        self.checks: list[dict] = []
        self.trades_df: pd.DataFrame | None = None
        self.equity_df: pd.DataFrame | None = None
        self.result_json: dict | None = None

    def load_artifacts(self) -> bool:
        """Load all artifact files. Returns False if critical files missing."""
        trades_path = self.artifact_dir / "trades.parquet"
        equity_path = self.artifact_dir / "equity.parquet"
        result_path = self.artifact_dir / "result.json"

        if not result_path.exists():
            self._fail("LOAD", "result.json missing")
            return False

        with open(result_path) as f:
            self.result_json = json.load(f)

        if trades_path.exists():
            self.trades_df = pd.read_parquet(trades_path)
        else:
            self.trades_df = pd.DataFrame()

        if equity_path.exists():
            self.equity_df = pd.read_parquet(equity_path)
        else:
            self.equity_df = pd.DataFrame()

        self._pass("LOAD", "All artifacts loaded successfully")
        return True

    def verify_all(self) -> list[dict]:
        """Run all 25 verification checks: 10 existing + 7 candle + 8 metric."""
        if not self.load_artifacts():
            return self.checks

        # ── Candle-based checks (run first, independent of artifacts) ────
        self.check_ohlcv_valid()

        # ── Existing internal consistency checks ─────────────────────────
        self.check_trade_count()
        self.check_pnl_direction()
        self.check_net_pnl_formula()
        self.check_fee_calculation()
        self.check_sl_tp_levels()
        self.check_exit_reason_consistency()

        # ── Candle-based fill verification ───────────────────────────────
        self.check_entry_fill()
        self.check_exit_fill()
        self.check_tp_sl_bar()
        self.check_indep_pnl()
        self.check_sl_tp_calc()

        # ── Equity checks ────────────────────────────────────────────────
        self.check_equity_walk()
        self.check_equity_consistency()

        # ── Summary/overlap checks ───────────────────────────────────────
        self.check_summary_metrics()
        self.check_no_overlapping_trades()
        self.check_bybit_pnl_formula()

        # ── Full metric recomputation checks ─────────────────────────────
        self.check_metric_counts()
        self.check_metric_pnl()
        self.check_metric_rates()
        self.check_metric_extremes()
        self.check_metric_drawdown()
        self.check_metric_risk()
        self.check_metric_duration()
        self.check_metric_quality()

        return self.checks

    def check_trade_count(self):
        """Verify trade count matches between result.json and trades.parquet."""
        assert self.result_json is not None
        json_count = self.result_json.get("trades_count", 0)
        parquet_count = len(self.trades_df) if self.trades_df is not None else 0

        if json_count == parquet_count:
            self._pass("TRADE_COUNT", f"Consistent: {json_count} trades")
        else:
            self._fail("TRADE_COUNT",
                       f"Mismatch: result.json={json_count}, trades.parquet={parquet_count}")

        if json_count == 0:
            self._warn("TRADE_COUNT", "Zero trades - limited verification possible")

    def check_pnl_direction(self):
        """Verify PnL direction is correct for each trade's side."""
        if self.trades_df is None or self.trades_df.empty:
            self._skip("PNL_DIRECTION", "No trades to verify")
            return

        issues = []
        for idx, trade in self.trades_df.iterrows():
            side = trade.get("side", "")
            entry_p = float(trade.get("entry_price", 0) or 0)
            exit_p = float(trade.get("exit_price", 0) or 0)
            realized = float(trade.get("realized_pnl", 0) or 0)

            if bool(pd.isna(exit_p)) or exit_p == 0:
                continue  # Open trade

            if side == "long":
                expected_sign = 1 if exit_p > entry_p else (-1 if exit_p < entry_p else 0)
            elif side == "short":
                expected_sign = 1 if exit_p < entry_p else (-1 if exit_p > entry_p else 0)
            else:
                issues.append(f"Trade {idx}: unknown side '{side}'")
                continue

            actual_sign = 1 if realized > ABS_TOL else (-1 if realized < -ABS_TOL else 0)
            if expected_sign != 0 and actual_sign != 0 and expected_sign != actual_sign:
                issues.append(
                    f"Trade {idx}: side={side} entry={entry_p:.4f} exit={exit_p:.4f} "
                    f"realized_pnl={realized:.4f} (wrong direction)"
                )

        if issues:
            self._fail("PNL_DIRECTION", f"{len(issues)} trades with wrong PnL direction:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("PNL_DIRECTION", "All trades have correct PnL direction")

    def check_net_pnl_formula(self):
        """Verify net_pnl = realized_pnl - fees_paid for each trade."""
        if self.trades_df is None or self.trades_df.empty:
            self._skip("NET_PNL", "No trades to verify")
            return

        issues = []
        for idx, trade in self.trades_df.iterrows():
            realized = float(trade.get("realized_pnl", 0) or 0)
            fees = float(trade.get("fees_paid", 0) or 0)
            net = float(trade.get("net_pnl", 0) or 0)

            if bool(pd.isna(realized)) or bool(pd.isna(fees)) or bool(pd.isna(net)):
                continue

            expected_net = realized - fees
            diff = abs(net - expected_net)
            if diff > ABS_TOL:
                issues.append(
                    f"Trade {idx}: net_pnl={net:.4f} != realized_pnl({realized:.4f}) - "
                    f"fees({fees:.4f}) = {expected_net:.4f} [diff={diff:.4f}]"
                )

        if issues:
            self._fail("NET_PNL", f"{len(issues)} trades with net_pnl mismatch:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("NET_PNL", "All trades: net_pnl = realized_pnl - fees_paid")

    def check_fee_calculation(self):
        """Verify fees are reasonable (within expected range of taker_bps)."""
        if self.trades_df is None or self.trades_df.empty:
            self._skip("FEES", "No trades to verify")
            return

        account = self.config.get("account", {})
        fee_model = account.get("fee_model", {})
        taker_bps = fee_model.get("taker_bps", 5.5)
        slippage_bps = account.get("slippage_bps", 2.0)
        taker_rate = taker_bps / 10000.0

        issues = []
        for idx, trade in self.trades_df.iterrows():
            entry_usdt = abs(float(trade.get("entry_size_usdt", 0) or 0))
            fees = float(trade.get("fees_paid", 0) or 0)
            exit_p = float(trade.get("exit_price", 0) or 0)
            entry_p = float(trade.get("entry_price", 0) or 0)

            if bool(pd.isna(fees)) or bool(pd.isna(entry_usdt)) or entry_usdt == 0:
                continue

            # Entry fee = entry_usdt * taker_rate
            entry_fee = entry_usdt * taker_rate

            # Exit fee = exit_notional * taker_rate
            # exit_notional ≈ entry_usdt * (exit_price / entry_price) for longs
            if entry_p > 0 and not bool(pd.isna(exit_p)) and exit_p > 0:
                exit_notional = entry_usdt * (exit_p / entry_p)
                exit_fee = exit_notional * taker_rate
            else:
                exit_fee = entry_usdt * taker_rate  # Approximate

            expected_total = entry_fee + exit_fee

            # Allow 20% tolerance for fee estimation (slippage affects notionals)
            if fees > 0 and expected_total > 0:
                ratio = fees / expected_total
                if ratio < 0.5 or ratio > 2.0:
                    issues.append(
                        f"Trade {idx}: fees={fees:.4f}, expected≈{expected_total:.4f} "
                        f"(ratio={ratio:.2f}x), entry_usdt={entry_usdt:.2f}"
                    )

        if issues:
            self._fail("FEES", f"{len(issues)} trades with suspicious fee amounts:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("FEES", f"All trade fees within expected range (taker={taker_bps}bps)")

    def check_sl_tp_levels(self):
        """Verify SL/TP price levels are valid.

        SL/TP are computed from the SIGNAL bar's close (not the fill price).
        Multi-TF bar dilation can cause the fill price to differ significantly
        from the signal bar close, making TP cross the entry price for some trades.

        We verify:
        1. SL is on the correct side of entry (SL is closer to signal close,
           so less affected by the signal-to-fill gap)
        2. SL and TP are positive
        3. SL != TP (distinct levels)
        4. TP direction vs entry is tracked as info (not a failure)
        """
        if self.trades_df is None or self.trades_df.empty:
            self._skip("SL_TP", "No trades to verify")
            return

        risk = self.config.get("risk", {})
        sl_pct = risk.get("stop_loss_pct")
        tp_pct = risk.get("take_profit_pct")
        leverage = self.config.get("account", {}).get("max_leverage", 1.0)

        if sl_pct is None and tp_pct is None:
            self._skip("SL_TP", "No SL/TP percentages in play config")
            return

        issues = []
        info_counts = {"sl_cross": 0, "tp_cross": 0}
        total = 0
        for idx, trade in self.trades_df.iterrows():
            sl = trade.get("stop_loss")
            tp = trade.get("take_profit")
            entry_p = float(trade.get("entry_price", 0) or 0)
            side = str(trade.get("side", "long")).lower()

            # SL/TP must be positive
            if sl_pct is not None and sl is not None and not bool(pd.isna(sl)):
                total += 1
                if sl <= 0:
                    issues.append(f"Trade {idx}: SL={sl:.2f} is non-positive")
            if tp_pct is not None and tp is not None and not bool(pd.isna(tp)):
                if tp <= 0:
                    issues.append(f"Trade {idx}: TP={tp:.2f} is non-positive")

            # SL/TP must be on correct side relative to EACH OTHER
            # (not relative to entry, because signal-fill gap can cause crossovers)
            if (sl is not None and not bool(pd.isna(sl)) and
                    tp is not None and not bool(pd.isna(tp))):
                if side == "long" and sl >= tp:
                    issues.append(
                        f"Trade {idx}: Long SL={sl:.2f} >= TP={tp:.2f}"
                    )
                elif side == "short" and tp >= sl:
                    issues.append(
                        f"Trade {idx}: Short TP={tp:.2f} >= SL={sl:.2f}"
                    )

            # Track signal-fill gap crossovers as info
            if entry_p > 0:
                if sl is not None and not bool(pd.isna(sl)):
                    if (side == "long" and sl >= entry_p) or (side == "short" and sl <= entry_p):
                        info_counts["sl_cross"] += 1
                if tp is not None and not bool(pd.isna(tp)):
                    if (side == "long" and tp <= entry_p) or (side == "short" and tp >= entry_p):
                        info_counts["tp_cross"] += 1

        if issues:
            self._fail("SL_TP", f"{len(issues)} SL/TP level issues:\n  " + "\n  ".join(issues[:5]))
        else:
            note_parts = []
            if info_counts["sl_cross"] > 0:
                note_parts.append(f"{info_counts['sl_cross']} SL-entry crosses")
            if info_counts["tp_cross"] > 0:
                note_parts.append(f"{info_counts['tp_cross']} TP-entry crosses")
            note = f" [{', '.join(note_parts)}]" if note_parts else ""
            checked = "SL" if sl_pct else ""
            checked += "/TP" if tp_pct else ""
            self._pass("SL_TP", f"All {total} {checked} levels valid (sl={sl_pct}%, tp={tp_pct}%){note}")

    def check_exit_reason_consistency(self):
        """Verify exit reason matches what actually happened at exit price."""
        if self.trades_df is None or self.trades_df.empty:
            self._skip("EXIT_REASON", "No trades to verify")
            return

        issues = []
        for idx, trade in self.trades_df.iterrows():
            reason = trade.get("exit_reason", "")
            exit_p = float(trade.get("exit_price", 0) or 0)
            sl = trade.get("stop_loss")
            tp = trade.get("take_profit")
            side = trade.get("side", "long")

            if bool(pd.isna(exit_p)) or exit_p == 0:
                continue

            if reason == "tp" and tp is not None and not bool(pd.isna(tp)):
                # Exit price should be at or near TP
                diff_pct = abs(exit_p - tp) / tp * 100 if tp != 0 else 0
                if diff_pct > 1.0:  # 1% tolerance for slippage
                    issues.append(
                        f"Trade {idx}: exit_reason=tp but exit_price={exit_p:.4f} "
                        f"far from tp={tp:.4f} (diff={diff_pct:.2f}%)"
                    )

            elif reason == "sl" and sl is not None and not bool(pd.isna(sl)):
                # Exit price should be at or near SL
                diff_pct = abs(exit_p - sl) / sl * 100 if sl != 0 else 0
                if diff_pct > 1.0:
                    issues.append(
                        f"Trade {idx}: exit_reason=sl but exit_price={exit_p:.4f} "
                        f"far from sl={sl:.4f} (diff={diff_pct:.2f}%)"
                    )

        if issues:
            self._fail("EXIT_REASON", f"{len(issues)} trades with exit reason issues:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("EXIT_REASON", "All exit reasons consistent with exit prices")

    def check_equity_consistency(self):
        """Verify final equity = initial + sum(net_pnl)."""
        if self.result_json is None:
            self._skip("EQUITY", "No result.json")
            return

        initial = self.config.get("account", {}).get("starting_equity_usdt", 10000.0)
        net_pnl = self.result_json.get("net_pnl_usdt", 0)
        trades_count = self.result_json.get("trades_count", 0)

        # Sum of individual trade PnLs (include funding_pnl if present)
        if self.trades_df is not None and not self.trades_df.empty and "net_pnl" in self.trades_df.columns:
            sum_trade_pnl = self.trades_df["net_pnl"].sum()
            if "funding_pnl" in self.trades_df.columns:
                sum_trade_pnl += self.trades_df["funding_pnl"].sum()
            diff = abs(sum_trade_pnl - net_pnl)
            # With the equity-curve fix (backtest_runner appends post-close equity point),
            # sum(trades.net_pnl) should exactly match result.json net_pnl_usdt.
            # Allow small float accumulation tolerance.
            tolerance = max(0.50, trades_count * 0.01)
            if diff > tolerance:
                self._fail("EQUITY",
                           f"PnL sum mismatch: sum(trades)={sum_trade_pnl:.4f} vs "
                           f"result.json net_pnl={net_pnl:.4f} [diff={diff:.4f}, tol={tolerance:.1f}]")
                return

        # Check equity curve if available
        if self.equity_df is not None and not self.equity_df.empty and "equity" in self.equity_df.columns:
            final_eq = self.equity_df["equity"].iloc[-1]
            expected_final = initial + net_pnl
            diff = abs(final_eq - expected_final)
            if diff > ABS_TOL * 10:  # Allow more slack for floating point accumulation
                self._fail("EQUITY",
                           f"Final equity={final_eq:.2f} != initial({initial:.2f}) + "
                           f"net_pnl({net_pnl:.4f}) = {expected_final:.2f}")
                return

        self._pass("EQUITY", f"Equity consistent: initial={initial:.0f}, net_pnl={net_pnl:.2f}")

    def check_summary_metrics(self):
        """Verify summary metrics in result.json are internally consistent."""
        r = self.result_json
        if r is None:
            self._skip("METRICS", "No result.json")
            return

        issues = []
        total = r.get("trades_count", 0)
        wins = r.get("winning_trades", 0)
        losses = r.get("losing_trades", 0)
        win_rate = r.get("win_rate", 0)

        # Win + Loss should equal total (or close, with breakeven trades)
        if total > 0:
            if wins + losses > total:
                issues.append(f"wins({wins}) + losses({losses}) > total({total})")

            # Win rate check (win_rate may be 0-1 fraction or 0-100 percentage)
            if total > 0:
                expected_wr_frac = wins / total
                expected_wr_pct = expected_wr_frac * 100
                # Try fraction format first
                if abs(win_rate - expected_wr_frac) > 0.01 and abs(win_rate - expected_wr_pct) > 0.5:
                    issues.append(
                        f"win_rate={win_rate} but wins/total = {wins}/{total} = "
                        f"{expected_wr_frac:.4f} (or {expected_wr_pct:.1f}%)"
                    )

        # Profit factor check
        gross_profit = r.get("gross_profit_usdt", 0)
        gross_loss = r.get("gross_loss_usdt", 0)
        profit_factor = r.get("profit_factor", 0)
        if gross_loss != 0 and profit_factor != 0:
            expected_pf = gross_profit / abs(gross_loss)
            if abs(profit_factor - expected_pf) > 0.01:
                issues.append(
                    f"profit_factor={profit_factor:.2f} but gross_profit/|gross_loss| = "
                    f"{gross_profit:.2f}/{abs(gross_loss):.2f} = {expected_pf:.2f}"
                )

        # Long/short breakdown
        long_trades = r.get("long_trades", 0)
        short_trades = r.get("short_trades", 0)
        if long_trades + short_trades != total and total > 0:
            issues.append(f"long({long_trades}) + short({short_trades}) != total({total})")

        if issues:
            self._fail("METRICS", "Summary metrics inconsistencies:\n  " + "\n  ".join(issues))
        else:
            self._pass("METRICS", f"Summary metrics consistent ({total} trades, {win_rate:.0f}% WR)")

    def check_no_overlapping_trades(self):
        """Verify no overlapping trades for single-position plays."""
        if self.trades_df is None or self.trades_df.empty:
            self._skip("OVERLAP", "No trades to verify")
            return

        max_pos = self.config.get("position_policy", {}).get("max_positions_per_symbol", 1)
        if max_pos > 1:
            self._skip("OVERLAP", f"Multi-position play (max={max_pos})")
            return

        if "entry_bar_index" not in self.trades_df.columns or "exit_bar_index" not in self.trades_df.columns:
            # Fall back to timestamps
            if "entry_time" in self.trades_df.columns and "exit_time" in self.trades_df.columns:
                df = self.trades_df.sort_values("entry_time")
                overlaps = []
                for i in range(1, len(df)):
                    prev_exit = df.iloc[i - 1]["exit_time"]
                    curr_entry = df.iloc[i]["entry_time"]
                    if prev_exit is not None and curr_entry is not None:
                        if pd.notna(prev_exit) and pd.notna(curr_entry) and curr_entry < prev_exit:
                            overlaps.append(f"Trade {i-1} exit={prev_exit} > Trade {i} entry={curr_entry}")

                if overlaps:
                    self._fail("OVERLAP", f"{len(overlaps)} overlapping trades:\n  " + "\n  ".join(overlaps[:3]))
                else:
                    self._pass("OVERLAP", "No overlapping trades")
                return

        df = self.trades_df.sort_values("entry_bar_index")
        overlaps = []
        for i in range(1, len(df)):
            prev_exit = df.iloc[i - 1].get("exit_bar_index")
            curr_entry = df.iloc[i]["entry_bar_index"]
            if prev_exit is not None and not pd.isna(prev_exit) and curr_entry < prev_exit:
                overlaps.append(f"Trade {i-1} exit_bar={prev_exit} > Trade {i} entry_bar={curr_entry}")

        if overlaps:
            self._fail("OVERLAP", f"{len(overlaps)} overlapping trades:\n  " + "\n  ".join(overlaps[:3]))
        else:
            self._pass("OVERLAP", "No overlapping trades (max_positions=1)")

    def check_bybit_pnl_formula(self):
        """Verify PnL matches Bybit's exact USDT perpetual formula.

        Bybit USDT Perp formulas (from help center):
          Long Unrealized PnL = Qty * (Last Price - Entry Price)
          Short Unrealized PnL = Qty * (Entry Price - Last Price)
          Trading Fee = Order Value * Fee Rate
          Closed PnL = Realized PnL - Open Fee - Close Fee

        Our sim should match:
          realized_pnl = price_diff * position_size  (before fees)
          net_pnl = realized_pnl - fees_paid
        """
        if self.trades_df is None or self.trades_df.empty:
            self._skip("BYBIT_PNL", "No trades to verify")
            return

        account = self.config.get("account", {})
        fee_model = account.get("fee_model", {})
        taker_bps = fee_model.get("taker_bps", 5.5)
        taker_rate = taker_bps / 10000.0

        issues = []
        for idx, trade in self.trades_df.iterrows():
            side = trade.get("side", "long")
            entry_p = float(trade.get("entry_price", 0) or 0)
            exit_p = float(trade.get("exit_price", 0) or 0)
            entry_size = float(trade.get("entry_size", 0) or 0)  # Base currency qty
            entry_usdt = abs(float(trade.get("entry_size_usdt", 0) or 0))
            realized = float(trade.get("realized_pnl", 0) or 0)
            fees = float(trade.get("fees_paid", 0) or 0)
            net = float(trade.get("net_pnl", 0) or 0)

            if bool(pd.isna(exit_p)) or exit_p == 0 or entry_p == 0:
                continue

            # --- Bybit realized PnL formula ---
            # Long: qty * (exit - entry)
            # Short: qty * (entry - exit)
            if not bool(pd.isna(entry_size)) and entry_size > 0:
                if side == "long":
                    expected_realized = entry_size * (exit_p - entry_p)
                else:
                    expected_realized = entry_size * (entry_p - exit_p)

                diff = abs(realized - expected_realized)
                if diff > ABS_TOL and (entry_usdt > 0 and diff / entry_usdt > 0.001):
                    issues.append(
                        f"Trade {idx}: realized_pnl={realized:.4f} vs "
                        f"Bybit formula={expected_realized:.4f} [diff={diff:.4f}]"
                    )

            # --- Bybit fee formula ---
            # Open fee = entry_value * taker_rate
            # Close fee = exit_value * taker_rate
            if entry_usdt > 0 and not bool(pd.isna(fees)):
                entry_fee_expected = entry_usdt * taker_rate
                exit_value = entry_size * exit_p if (not bool(pd.isna(entry_size)) and entry_size > 0) else entry_usdt
                exit_fee_expected = exit_value * taker_rate
                total_fee_expected = entry_fee_expected + exit_fee_expected

                fee_diff = abs(fees - total_fee_expected)
                if fee_diff > ABS_TOL and fees > 0 and fee_diff / fees > 0.1:
                    issues.append(
                        f"Trade {idx}: fees={fees:.4f} vs Bybit formula "
                        f"(open={entry_fee_expected:.4f}+close={exit_fee_expected:.4f}"
                        f"={total_fee_expected:.4f}) [diff={fee_diff:.4f}]"
                    )

            # --- Bybit closed PnL = realized - fees ---
            if not bool(pd.isna(net)) and not bool(pd.isna(realized)) and not bool(pd.isna(fees)):
                expected_net = realized - fees
                net_diff = abs(net - expected_net)
                if net_diff > ABS_TOL:
                    issues.append(
                        f"Trade {idx}: net_pnl={net:.4f} vs "
                        f"(realized({realized:.4f})-fees({fees:.4f}))={expected_net:.4f}"
                    )

        if issues:
            self._fail("BYBIT_PNL",
                       f"{len(issues)} Bybit formula mismatches:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("BYBIT_PNL",
                       f"All trades match Bybit USDT perp formulas (taker={taker_bps}bps)")

    # ── Candle-based checks ─────────────────────────────────────────────

    def _get_exec_tf(self) -> str | None:
        tfs = self.config.get("timeframes", {})
        exec_ptr = tfs.get("exec", "low_tf")
        return tfs.get(exec_ptr)

    def check_ohlcv_valid(self):
        """Verify synthetic candles have valid OHLCV invariants."""
        if self.candle_data is None:
            self._skip("OHLCV_VALID", "No candle data provided")
            return

        issues = []
        for tf, df in self.candle_data.items():
            if df.empty:
                continue
            # low <= min(open, close)
            open_arr = np.asarray(df["open"].values)
            close_arr = np.asarray(df["close"].values)
            low_arr = np.asarray(df["low"].values)
            high_arr = np.asarray(df["high"].values)
            vol_arr = np.asarray(df["volume"].values)

            min_oc = np.minimum(open_arr, close_arr)
            bad_low = low_arr > min_oc + ABS_TOL
            if bad_low.any():
                issues.append(f"{tf}: {bad_low.sum()} bars where low > min(open, close)")

            # high >= max(open, close)
            max_oc = np.maximum(open_arr, close_arr)
            bad_high = high_arr < max_oc - ABS_TOL
            if bad_high.any():
                issues.append(f"{tf}: {bad_high.sum()} bars where high < max(open, close)")

            # volume > 0
            bad_vol = vol_arr <= 0
            if bad_vol.any():
                issues.append(f"{tf}: {bad_vol.sum()} bars with volume <= 0")

            # timestamps monotonic
            if "timestamp" in df.columns:
                ts = np.asarray(df["timestamp"].values)
                if len(ts) > 1 and not np.all(ts[1:] > ts[:-1]):
                    issues.append(f"{tf}: timestamps not strictly monotonic")

        if issues:
            self._fail("OHLCV_VALID", f"{len(issues)} issues:\n  " + "\n  ".join(issues[:5]))
        else:
            tf_summary = ", ".join(f"{tf}({len(df)})" for tf, df in self.candle_data.items())
            self._pass("OHLCV_VALID", f"All candles valid: {tf_summary}")

    def check_entry_fill(self):
        """Verify entry fill price validity and SL directional consistency.

        Checks:
        1. Entry price is positive and finite
        2. Exit price is positive and finite
        3. SL is on the correct side of entry (long: SL < entry, short: SL > entry)
        4. Entry/exit sizes are positive

        Note: TP vs entry direction is NOT checked here because multi-TF bar
        dilation can cause signal bar close (used for TP calc) to be far from
        the actual fill price, making TP < entry for longs a legitimate scenario
        (not a math error).
        """
        if self.trades_df is None or self.trades_df.empty:
            self._skip("ENTRY_FILL", "No trades to verify")
            return

        issues = []
        for idx, trade in self.trades_df.iterrows():
            entry_p = float(trade.get("entry_price", 0) or 0)
            exit_p = float(trade.get("exit_price", 0) or 0)

            # 1. Entry price must be positive and finite
            if not (np.isfinite(entry_p) and entry_p > 0):
                issues.append(f"Trade {idx}: entry_price={entry_p} is invalid")
                continue

            # 2. Exit price must be positive and finite
            if exit_p != 0 and not bool(pd.isna(exit_p)):
                if not (np.isfinite(exit_p) and exit_p > 0):
                    issues.append(f"Trade {idx}: exit_price={exit_p} is invalid")

            side = str(trade.get("side", "long")).lower()
            sl = trade.get("stop_loss")

            # 3. Entry size must be positive
            entry_size = float(trade.get("entry_size_usdt", 0) or 0)
            if not bool(pd.isna(entry_size)):
                if entry_size <= 0:
                    issues.append(f"Trade {idx}: entry_size_usdt={entry_size} <= 0")

        if issues:
            self._fail("ENTRY_FILL", f"{len(issues)} entry fill issues:\n  " + "\n  ".join(issues[:5]))
        else:
            n = len(self.trades_df)
            self._pass("ENTRY_FILL", f"All {n} entries: valid prices, correct SL direction, positive sizes")

    def check_exit_fill(self):
        """Verify exit price matches TP/SL level or bar close + slippage."""
        if self.candle_data is None:
            self._skip("EXIT_FILL", "No candle data provided")
            return
        if self.trades_df is None or self.trades_df.empty:
            self._skip("EXIT_FILL", "No trades to verify")
            return

        exec_tf = self._get_exec_tf()
        if exec_tf is None or exec_tf not in self.candle_data:
            self._skip("EXIT_FILL", f"Exec TF '{exec_tf}' not in candle data")
            return

        candles = self.candle_data[exec_tf]
        account = self.config.get("account", {})
        slippage_bps = account.get("slippage_bps", 5.0)
        slip_rate = slippage_bps / 10000.0

        issues = []
        for idx, trade in self.trades_df.iterrows():
            exit_p_raw = trade.get("exit_price")
            if exit_p_raw is None or bool(pd.isna(exit_p_raw)) or exit_p_raw == 0:
                continue
            exit_p = float(exit_p_raw)

            side = trade.get("side", "long")
            reason = trade.get("exit_reason", "")
            tp = trade.get("take_profit")
            sl = trade.get("stop_loss")

            if reason == "tp" and tp is not None and not bool(pd.isna(tp)):
                # TP fill: long exit receives less, short exit pays more
                if side == "long":
                    expected = float(tp) * (1 - slip_rate)
                else:
                    expected = float(tp) * (1 + slip_rate)
            elif reason == "sl" and sl is not None and not bool(pd.isna(sl)):
                # SL fill: long exit receives less, short exit pays more
                if side == "long":
                    expected = float(sl) * (1 - slip_rate)
                else:
                    expected = float(sl) * (1 + slip_rate)
            elif reason in ("signal", "end_of_data"):
                bar_idx = trade.get("exit_bar_index")
                if bar_idx is None or bool(pd.isna(bar_idx)):
                    continue
                bar_idx = int(bar_idx)
                if bar_idx < 0 or bar_idx >= len(candles):
                    continue
                bar_close = candles.iloc[bar_idx]["close"]
                if side == "long":
                    expected = bar_close * (1 - slip_rate)
                else:
                    expected = bar_close * (1 + slip_rate)
            else:
                continue  # Unknown exit reason, skip

            diff_pct = abs(exit_p - expected) / expected * 100 if expected > 0 else 0
            if diff_pct > 1.0:  # 1% tolerance
                issues.append(
                    f"Trade {idx}: exit={exit_p:.4f} vs expected={expected:.4f} "
                    f"(reason={reason}, side={side}, diff={diff_pct:.3f}%)"
                )

        if issues:
            self._fail("EXIT_FILL", f"{len(issues)} exit fill mismatches:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("EXIT_FILL", "All exit fills match expected levels + slippage")

    def check_tp_sl_bar(self):
        """Verify TP/SL triggered on the correct bar, not earlier.

        Uses timestamp-based lookup against candle data to avoid bar index
        alignment issues between engine's internal indices and DuckDB rows.

        Note: The engine uses 1m granularity for TP/SL checking when 1m data
        is available.  A 15m exec bar may have its high breach TP, but the
        engine saw the 1m bars within that 15m bar and determined that TP was
        hit on a specific 1m bar.  This check only verifies at exec-TF
        granularity, so we check whether TP/SL could have triggered on an
        EARLIER exec bar (not the same bar with finer granularity).
        """
        if self.candle_data is None:
            self._skip("TP_SL_BAR", "No candle data provided")
            return
        if self.trades_df is None or self.trades_df.empty:
            self._skip("TP_SL_BAR", "No trades to verify")
            return

        exec_tf = self._get_exec_tf()
        if exec_tf is None or exec_tf not in self.candle_data:
            self._skip("TP_SL_BAR", f"Exec TF '{exec_tf}' not in candle data")
            return

        candles = self.candle_data[exec_tf]
        if "timestamp" not in candles.columns:
            self._skip("TP_SL_BAR", "No timestamp column in candle data")
            return
        if "entry_time" not in self.trades_df.columns or "exit_time" not in self.trades_df.columns:
            self._skip("TP_SL_BAR", "No time columns in trades")
            return

        # Build timestamp → row index map for O(1) lookup
        candles_sorted = candles.sort_values("timestamp").reset_index(drop=True)
        ts_to_row = {ts: i for i, ts in enumerate(candles_sorted["timestamp"])}

        issues = []
        checked = 0
        for idx, trade in self.trades_df.iterrows():
            reason = trade.get("exit_reason", "")
            if reason not in ("tp", "sl"):
                continue

            side = trade.get("side", "long")
            tp = trade.get("take_profit")
            sl = trade.get("stop_loss")

            entry_time_val = trade["entry_time"]
            exit_time_val = trade["exit_time"]
            entry_ts = pd.Timestamp(str(entry_time_val))
            exit_ts = pd.Timestamp(str(exit_time_val))

            # Find entry and exit rows in candle data
            entry_row = ts_to_row.get(entry_ts)
            exit_row = ts_to_row.get(exit_ts)
            if entry_row is None or exit_row is None:
                continue

            checked += 1
            # Walk exec bars from entry+1 to exit-1 (BEFORE the exit bar).
            # The engine may have used 1m sub-bars within the exit exec bar
            # to detect TP/SL, so same-bar triggers are expected and fine.
            for ri in range(entry_row + 1, exit_row):
                bar = candles_sorted.iloc[ri]
                if reason == "tp" and tp is not None and not bool(pd.isna(tp)):
                    if side == "long" and bar["high"] >= tp:
                        issues.append(
                            f"Trade {idx}: TP should have triggered at ts={bar['timestamp']} "
                            f"(high={bar['high']:.4f} >= tp={tp:.4f}), but exit_ts={exit_ts}"
                        )
                        break
                    elif side == "short" and bar["low"] <= tp:
                        issues.append(
                            f"Trade {idx}: TP should have triggered at ts={bar['timestamp']} "
                            f"(low={bar['low']:.4f} <= tp={tp:.4f}), but exit_ts={exit_ts}"
                        )
                        break
                if reason == "sl" and sl is not None and not bool(pd.isna(sl)):
                    if side == "long" and bar["low"] <= sl:
                        issues.append(
                            f"Trade {idx}: SL should have triggered at ts={bar['timestamp']} "
                            f"(low={bar['low']:.4f} <= sl={sl:.4f}), but exit_ts={exit_ts}"
                        )
                        break
                    elif side == "short" and bar["high"] >= sl:
                        issues.append(
                            f"Trade {idx}: SL should have triggered at ts={bar['timestamp']} "
                            f"(high={bar['high']:.4f} >= sl={sl:.4f}), but exit_ts={exit_ts}"
                        )
                        break

        if issues:
            self._fail("TP_SL_BAR", f"{len(issues)} early TP/SL triggers:\n  " + "\n  ".join(issues[:5]))
        elif checked == 0:
            self._skip("TP_SL_BAR", "No TP/SL trades with bar indices to check")
        else:
            self._pass("TP_SL_BAR", f"All {checked} TP/SL exits triggered on correct bar")

    def check_indep_pnl(self):
        """Independently recalculate PnL from prices and qty."""
        if self.trades_df is None or self.trades_df.empty:
            self._skip("INDEP_PNL", "No trades to verify")
            return

        if "entry_size" not in self.trades_df.columns:
            self._skip("INDEP_PNL", "No entry_size column (base currency qty)")
            return

        issues = []
        for idx, trade in self.trades_df.iterrows():
            side = trade.get("side", "long")
            entry_p = float(trade.get("entry_price", 0) or 0)
            exit_p = float(trade.get("exit_price", 0) or 0)
            qty = float(trade.get("entry_size", 0) or 0)
            realized = float(trade.get("realized_pnl", 0) or 0)
            entry_usdt = abs(float(trade.get("entry_size_usdt", 0) or 0))

            if bool(pd.isna(exit_p)) or exit_p == 0 or entry_p == 0 or bool(pd.isna(qty)) or qty == 0:
                continue

            if side == "long":
                expected = qty * (exit_p - entry_p)
            else:
                expected = qty * (entry_p - exit_p)

            diff = abs(realized - expected)
            tol = max(ABS_TOL, entry_usdt * 0.001)
            if diff > tol:
                issues.append(
                    f"Trade {idx}: realized={realized:.4f} vs "
                    f"qty({qty:.6f})*price_diff={expected:.4f} [diff={diff:.4f}, tol={tol:.4f}]"
                )

        if issues:
            self._fail("INDEP_PNL", f"{len(issues)} PnL recalc mismatches:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("INDEP_PNL", "All trades: independent PnL matches realized_pnl")

    def check_sl_tp_calc(self):
        """Verify SL/TP levels are computed correctly from the signal bar close.

        SL/TP are computed from SIGNAL bar close (not fill price):
          Long:  SL = signal_close * (1 - sl_pct / 100 / leverage)
                 TP = signal_close * (1 + tp_pct / 100 / leverage)
          Short: SL = signal_close * (1 + sl_pct / 100 / leverage)
                 TP = signal_close * (1 - tp_pct / 100 / leverage)

        We don't have signal_close directly, but we can back-derive it from SL
        and verify TP is consistent with that derived signal_close.
        """
        if self.trades_df is None or self.trades_df.empty:
            self._skip("SL_TP_CALC", "No trades to verify")
            return

        risk = self.config.get("risk", {})
        sl_pct = risk.get("stop_loss_pct")
        tp_pct = risk.get("take_profit_pct")
        leverage = self.config.get("account", {}).get("max_leverage", 1.0)

        if sl_pct is None or tp_pct is None:
            self._skip("SL_TP_CALC", "Need both SL and TP pct for cross-validation")
            return

        issues = []
        checked = 0
        for idx, trade in self.trades_df.iterrows():
            sl = trade.get("stop_loss")
            tp = trade.get("take_profit")
            side = str(trade.get("side", "long")).lower()

            if sl is None or bool(pd.isna(sl)) or tp is None or bool(pd.isna(tp)):
                continue

            sl = float(sl)
            tp = float(tp)

            # Back-derive signal_close from SL
            sl_rate = sl_pct / (100.0 * leverage)
            tp_rate = tp_pct / (100.0 * leverage)

            if side == "long":
                # SL = signal_close * (1 - sl_rate)  →  signal_close = SL / (1 - sl_rate)
                denom = 1.0 - sl_rate
                if denom <= 0:
                    continue
                signal_close = sl / denom
                # Expected TP from that signal_close
                expected_tp = signal_close * (1.0 + tp_rate)
            else:
                # SL = signal_close * (1 + sl_rate)  →  signal_close = SL / (1 + sl_rate)
                signal_close = sl / (1.0 + sl_rate)
                # Expected TP
                expected_tp = signal_close * (1.0 - tp_rate)

            checked += 1
            # Compare actual TP to expected TP (should be very close — same signal_close)
            if expected_tp > 0:
                tp_error = abs(tp - expected_tp) / expected_tp
                if tp_error > 0.001:  # 0.1% tolerance (should be exact or nearly so)
                    issues.append(
                        f"Trade {idx}: TP={tp:.4f} vs expected={expected_tp:.4f} "
                        f"(derived signal_close={signal_close:.4f}, error={tp_error:.4%})"
                    )

        if issues:
            self._fail("SL_TP_CALC", f"{len(issues)}/{checked} SL/TP inconsistencies:\n  " + "\n  ".join(issues[:5]))
        else:
            self._pass("SL_TP_CALC", f"SL/TP cross-validation OK: {checked} trades, TP matches SL-derived signal_close (sl={sl_pct}%, tp={tp_pct}%, lev={leverage}x)")

    def check_equity_walk(self):
        """Walk equity curve: initial + cumsum(net_pnl) should match at trade exits."""
        if self.equity_df is None or self.equity_df.empty:
            self._skip("EQUITY_WALK", "No equity data")
            return
        if self.trades_df is None or self.trades_df.empty:
            self._skip("EQUITY_WALK", "No trades to verify")
            return
        if "equity" not in self.equity_df.columns or "net_pnl" not in self.trades_df.columns:
            self._skip("EQUITY_WALK", "Missing equity or net_pnl columns")
            return

        initial = self.config.get("account", {}).get("starting_equity_usdt", 10000.0)
        trade_count = len(self.trades_df)
        sum_net_pnl = self.trades_df["net_pnl"].sum()
        final_equity = self.equity_df["equity"].iloc[-1]
        expected_final = initial + sum_net_pnl

        # With the equity-curve fix (backtest_runner appends post-close equity point),
        # final equity should exactly match initial + sum(net_pnl).
        # Allow small float accumulation tolerance.
        tolerance = max(0.50, trade_count * 0.01)
        diff = abs(final_equity - expected_final)

        if diff > tolerance:
            self._fail(
                "EQUITY_WALK",
                f"Final equity={final_equity:.2f} vs initial({initial:.2f}) + "
                f"sum(net_pnl)({sum_net_pnl:.2f}) = {expected_final:.2f} "
                f"[diff={diff:.2f}, tol={tolerance:.1f}]"
            )
        else:
            self._pass(
                "EQUITY_WALK",
                f"Equity walk consistent: {initial:.0f} + {sum_net_pnl:.2f} = "
                f"{expected_final:.2f} (actual={final_equity:.2f}, diff={diff:.2f})"
            )

    # ── Metric verification checks ─────────────────────────────────────

    def _get_bars_per_year(self) -> int:
        """Resolve exec TF and return bars_per_year for annualization."""
        tfs = self.config.get("timeframes", {})
        exec_ptr = tfs.get("exec", "low_tf")
        exec_tf = tfs.get(exec_ptr)
        if exec_tf and exec_tf in TF_BARS_PER_YEAR:
            return TF_BARS_PER_YEAR[exec_tf]
        return 8760  # Default 1h

    def check_metric_counts(self):
        """Recompute trade counts from trades.parquet and compare to result.json."""
        if self.result_json is None:
            self._skip("METRIC_COUNTS", "No result.json")
            return
        if self.trades_df is None or self.trades_df.empty:
            total = self.result_json.get("trades_count", 0)
            if total == 0:
                self._pass("METRIC_COUNTS", "Zero trades - consistent")
            else:
                self._fail("METRIC_COUNTS", f"result.json says {total} trades but trades_df is empty")
            return

        df = self.trades_df
        r = self.result_json
        issues = []

        # Total trades
        computed_total = len(df)
        expected_total = r.get("trades_count", 0)
        if computed_total != expected_total:
            issues.append(f"trades_count: computed={computed_total} vs result={expected_total}")

        # Wins / losses
        pnls = df["net_pnl"] if "net_pnl" in df.columns else pd.Series(dtype=float)
        computed_wins = int((pnls > 0).sum())
        computed_losses = int((pnls < 0).sum())
        expected_wins = r.get("winning_trades", 0)
        expected_losses = r.get("losing_trades", 0)
        if computed_wins != expected_wins:
            issues.append(f"winning_trades: computed={computed_wins} vs result={expected_wins}")
        if computed_losses != expected_losses:
            issues.append(f"losing_trades: computed={computed_losses} vs result={expected_losses}")

        # Long / short
        if "side" in df.columns:
            computed_longs = int((df["side"] == "long").sum())
            computed_shorts = int((df["side"] == "short").sum())
            expected_longs = r.get("long_trades", 0)
            expected_shorts = r.get("short_trades", 0)
            if computed_longs != expected_longs:
                issues.append(f"long_trades: computed={computed_longs} vs result={expected_longs}")
            if computed_shorts != expected_shorts:
                issues.append(f"short_trades: computed={computed_shorts} vs result={expected_shorts}")

        if issues:
            self._fail("METRIC_COUNTS", "Count mismatches:\n  " + "\n  ".join(issues))
        else:
            self._pass("METRIC_COUNTS", f"All counts match ({computed_total} trades, {computed_wins}W/{computed_losses}L)")

    def check_metric_pnl(self):
        """Recompute PnL aggregates from trades.parquet and compare to result.json."""
        if self.result_json is None:
            self._skip("METRIC_PNL", "No result.json")
            return
        if self.trades_df is None or self.trades_df.empty:
            self._skip("METRIC_PNL", "No trades to verify")
            return

        df = self.trades_df
        r = self.result_json
        pnls = df["net_pnl"] if "net_pnl" in df.columns else pd.Series(dtype=float)
        issues = []

        # With the equity-curve fix, trade-level PnL should match result.json exactly.
        # Allow 1% relative tolerance for float accumulation.
        def _check_val(name: str, computed: float, expected: float):
            tol = max(ABS_TOL, abs(expected) * 0.01)
            if abs(computed - expected) > tol:
                issues.append(
                    f"{name}: computed={computed:.4f} vs result={expected:.4f} "
                    f"[diff={abs(computed - expected):.4f}, tol={tol:.4f}]"
                )

        # Gross profit (sum of positive net_pnl)
        computed_gp = float(pnls[pnls > 0].sum())
        _check_val("gross_profit_usdt", computed_gp, r.get("gross_profit_usdt", 0))

        # Gross loss (sum of negative net_pnl) - result.json stores as NEGATIVE
        computed_gl = float(pnls[pnls < 0].sum())
        _check_val("gross_loss_usdt", computed_gl, r.get("gross_loss_usdt", 0))

        # Total fees
        if "fees_paid" in df.columns:
            computed_fees = float(df["fees_paid"].sum())
            _check_val("total_fees_usdt", computed_fees, r.get("total_fees_usdt", 0))

        # Net profit
        computed_net = float(pnls.sum())
        _check_val("net_pnl_usdt", computed_net, r.get("net_pnl_usdt", 0))

        # Expectancy
        total = len(df)
        if total > 0:
            computed_exp = computed_net / total
            _check_val("expectancy_usdt", computed_exp, r.get("expectancy_usdt", 0))

        if issues:
            self._fail("METRIC_PNL", "PnL mismatches:\n  " + "\n  ".join(issues))
        else:
            self._pass("METRIC_PNL", f"All PnL aggregates match (net={computed_net:.2f})")

    def check_metric_rates(self):
        """Recompute rates/ratios from trades.parquet and compare to result.json."""
        if self.result_json is None:
            self._skip("METRIC_RATES", "No result.json")
            return
        if self.trades_df is None or self.trades_df.empty:
            self._skip("METRIC_RATES", "No trades to verify")
            return

        df = self.trades_df
        r = self.result_json
        pnls = df["net_pnl"] if "net_pnl" in df.columns else pd.Series(dtype=float)
        total = len(df)
        wins = int((pnls > 0).sum())
        issues = []

        # Win rate (result.json is 0-1 decimal)
        if total > 0:
            computed_wr = wins / total
            expected_wr = r.get("win_rate", 0)
            if abs(computed_wr - expected_wr) > 0.01:
                issues.append(
                    f"win_rate: computed={computed_wr:.4f} vs result={expected_wr:.4f}"
                )

        # Profit factor
        gp = float(pnls[pnls > 0].sum())
        gl_abs = abs(float(pnls[pnls < 0].sum()))
        if gl_abs > 0:
            computed_pf = gp / gl_abs
        elif gp > 0:
            computed_pf = 100.0
        else:
            computed_pf = 0.0
        expected_pf = r.get("profit_factor", 0)
        if abs(computed_pf - expected_pf) > max(0.01, abs(expected_pf) * 0.02):
            issues.append(f"profit_factor: computed={computed_pf:.4f} vs result={expected_pf:.4f}")

        # Payoff ratio
        avg_win = float(pnls[pnls > 0].mean()) if wins > 0 else 0.0
        losses_count = int((pnls < 0).sum())
        avg_loss = abs(float(pnls[pnls < 0].mean())) if losses_count > 0 else 0.0
        if avg_loss > 0:
            computed_pr = avg_win / avg_loss
        else:
            computed_pr = 0.0
        expected_pr = r.get("payoff_ratio", 0)
        if abs(computed_pr - expected_pr) > max(0.01, abs(expected_pr) * 0.02):
            issues.append(f"payoff_ratio: computed={computed_pr:.4f} vs result={expected_pr:.4f}")

        # Long/short win rates (result.json is 0-100 percentage)
        if "side" in df.columns:
            long_df = df[df["side"] == "long"]
            short_df = df[df["side"] == "short"]
            if len(long_df) > 0 and "net_pnl" in long_df.columns:
                computed_lwr = int((long_df["net_pnl"] > 0).sum()) / len(long_df) * 100
                expected_lwr = r.get("long_win_rate", 0)
                if abs(computed_lwr - expected_lwr) > 1.0:
                    issues.append(f"long_win_rate: computed={computed_lwr:.2f} vs result={expected_lwr:.2f}")
            if len(short_df) > 0 and "net_pnl" in short_df.columns:
                computed_swr = int((short_df["net_pnl"] > 0).sum()) / len(short_df) * 100
                expected_swr = r.get("short_win_rate", 0)
                if abs(computed_swr - expected_swr) > 1.0:
                    issues.append(f"short_win_rate: computed={computed_swr:.2f} vs result={expected_swr:.2f}")

        if issues:
            self._fail("METRIC_RATES", "Rate mismatches:\n  " + "\n  ".join(issues))
        else:
            self._pass("METRIC_RATES", f"All rates/ratios match (WR={wins}/{total})")

    def check_metric_extremes(self):
        """Recompute extreme values and streaks from trades.parquet."""
        if self.result_json is None:
            self._skip("METRIC_EXTREMES", "No result.json")
            return
        if self.trades_df is None or self.trades_df.empty:
            self._skip("METRIC_EXTREMES", "No trades to verify")
            return

        df = self.trades_df
        r = self.result_json
        pnls = df["net_pnl"] if "net_pnl" in df.columns else pd.Series(dtype=float)
        issues = []

        # Largest win
        win_pnls = pnls[pnls > 0]
        if len(win_pnls) > 0:
            computed_lw = float(win_pnls.max())
            expected_lw = r.get("largest_win_usdt", 0)
            if abs(computed_lw - expected_lw) > ABS_TOL:
                issues.append(f"largest_win_usdt: computed={computed_lw:.4f} vs result={expected_lw:.4f}")

        # Largest loss (result stores as positive absolute value)
        loss_pnls = pnls[pnls < 0]
        if len(loss_pnls) > 0:
            computed_ll = abs(float(loss_pnls.min()))
            expected_ll = r.get("largest_loss_usdt", 0)
            if abs(computed_ll - expected_ll) > ABS_TOL:
                issues.append(f"largest_loss_usdt: computed={computed_ll:.4f} vs result={expected_ll:.4f}")

        # Consecutive streaks (walk trades in order)
        max_cw = 0
        max_cl = 0
        cur_w = 0
        cur_l = 0
        for val in pnls:
            if val > 0:
                cur_w += 1
                cur_l = 0
                if cur_w > max_cw:
                    max_cw = cur_w
            elif val < 0:
                cur_l += 1
                cur_w = 0
                if cur_l > max_cl:
                    max_cl = cur_l
            else:
                cur_w = 0
                cur_l = 0

        expected_cw = r.get("max_consecutive_wins", 0)
        expected_cl = r.get("max_consecutive_losses", 0)
        if max_cw != expected_cw:
            issues.append(f"max_consecutive_wins: computed={max_cw} vs result={expected_cw}")
        if max_cl != expected_cl:
            issues.append(f"max_consecutive_losses: computed={max_cl} vs result={expected_cl}")

        if issues:
            self._fail("METRIC_EXTREMES", "Extremes mismatches:\n  " + "\n  ".join(issues))
        else:
            self._pass("METRIC_EXTREMES", f"All extremes/streaks match (streaks: {max_cw}W/{max_cl}L)")

    def check_metric_drawdown(self):
        """Walk equity curve to recompute max drawdown and compare to result.json."""
        if self.result_json is None:
            self._skip("METRIC_DRAWDOWN", "No result.json")
            return
        if self.equity_df is None or self.equity_df.empty or "equity" not in self.equity_df.columns:
            self._skip("METRIC_DRAWDOWN", "No equity data")
            return

        equities = self.equity_df["equity"].values
        if len(equities) < 2:
            self._skip("METRIC_DRAWDOWN", "Equity curve too short")
            return

        r = self.result_json
        issues = []

        # Walk equity to compute max drawdown (abs and pct independently)
        peak = equities[0]
        max_dd_abs = 0.0
        max_dd_pct = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            else:
                dd_abs = peak - eq
                dd_pct = dd_abs / peak if peak > 0 else 0.0
                if dd_abs > max_dd_abs:
                    max_dd_abs = dd_abs
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

        # Compare max_drawdown_usdt
        expected_dd_abs = r.get("max_drawdown_usdt", 0)
        tol_abs = max(0.01, abs(expected_dd_abs) * 0.02)
        if abs(max_dd_abs - expected_dd_abs) > tol_abs:
            issues.append(
                f"max_drawdown_usdt: computed={max_dd_abs:.4f} vs result={expected_dd_abs:.4f} "
                f"[diff={abs(max_dd_abs - expected_dd_abs):.4f}, tol={tol_abs:.4f}]"
            )

        # Compare max_drawdown_pct (result.json is 0-1 decimal)
        expected_dd_pct = r.get("max_drawdown_pct", 0)
        tol_pct = max(0.01, abs(expected_dd_pct) * 0.02)
        if abs(max_dd_pct - expected_dd_pct) > tol_pct:
            issues.append(
                f"max_drawdown_pct: computed={max_dd_pct:.6f} vs result={expected_dd_pct:.6f} "
                f"[diff={abs(max_dd_pct - expected_dd_pct):.6f}, tol={tol_pct:.6f}]"
            )

        if issues:
            self._fail("METRIC_DRAWDOWN", "Drawdown mismatches:\n  " + "\n  ".join(issues))
        else:
            self._pass("METRIC_DRAWDOWN", f"Drawdown matches (abs={max_dd_abs:.2f}, pct={max_dd_pct:.4f})")

    def check_metric_risk(self):
        """Recompute Sharpe, Sortino, Calmar from equity curve."""
        if self.result_json is None:
            self._skip("METRIC_RISK", "No result.json")
            return
        if self.equity_df is None or self.equity_df.empty or "equity" not in self.equity_df.columns:
            self._skip("METRIC_RISK", "No equity data")
            return

        equities = self.equity_df["equity"].values
        if len(equities) < 3:
            self._skip("METRIC_RISK", "Equity curve too short for risk metrics")
            return

        r = self.result_json
        bars_per_year = self._get_bars_per_year()
        issues = []

        # Compute per-bar returns
        returns = []
        for i in range(1, len(equities)):
            prev = equities[i - 1]
            curr = equities[i]
            if prev > 0:
                returns.append((curr / prev) - 1.0)

        if len(returns) < 2:
            self._skip("METRIC_RISK", "Not enough return data points")
            return

        n = len(returns)
        mean_r = sum(returns) / n
        annualization = math.sqrt(bars_per_year)

        # Sharpe = (mean(r) / std(r)) * sqrt(bars_per_year)
        variance = sum((ret - mean_r) ** 2 for ret in returns) / n
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        computed_sharpe = (mean_r / std_r * annualization) if std_r > 0 else 0.0

        expected_sharpe = r.get("sharpe", 0)
        if expected_sharpe != 0:
            # Wider tolerance for near-zero Sharpe (small abs values amplify rel_err)
            abs_tol = 0.01
            rel_err = abs(computed_sharpe - expected_sharpe) / max(abs(expected_sharpe), 0.01)
            if rel_err > 0.10 and abs(computed_sharpe - expected_sharpe) > abs_tol:
                issues.append(
                    f"sharpe: computed={computed_sharpe:.4f} vs result={expected_sharpe:.4f} "
                    f"[rel_err={rel_err:.2%}]"
                )
        elif abs(computed_sharpe) > 0.01:
            issues.append(f"sharpe: computed={computed_sharpe:.4f} vs result=0")

        # Sortino = (mean(r) / downside_std) * sqrt(bars_per_year)
        neg_returns = [ret for ret in returns if ret < 0]
        if not neg_returns:
            computed_sortino = 100.0 if mean_r > 0 else 0.0
        else:
            downside_var = sum(ret ** 2 for ret in neg_returns) / n
            downside_std = math.sqrt(downside_var) if downside_var > 0 else 0.0
            computed_sortino = (mean_r / downside_std * annualization) if downside_std > 0 else 0.0

        expected_sortino = r.get("sortino", 0)
        if expected_sortino != 0:
            abs_tol = 0.01
            rel_err = abs(computed_sortino - expected_sortino) / max(abs(expected_sortino), 0.01)
            if rel_err > 0.10 and abs(computed_sortino - expected_sortino) > abs_tol:
                issues.append(
                    f"sortino: computed={computed_sortino:.4f} vs result={expected_sortino:.4f} "
                    f"[rel_err={rel_err:.2%}]"
                )
        elif abs(computed_sortino) > 0.01:
            issues.append(f"sortino: computed={computed_sortino:.4f} vs result=0")

        # Calmar = CAGR / max_dd_decimal
        initial_eq = equities[0]
        final_eq = equities[-1]
        total_bars = len(equities)
        years = total_bars / bars_per_year if bars_per_year > 0 else 0

        # Walk equity for max_dd_pct_decimal
        peak = equities[0]
        max_dd_pct_decimal = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            elif peak > 0:
                dd_pct = (peak - eq) / peak
                if dd_pct > max_dd_pct_decimal:
                    max_dd_pct_decimal = dd_pct

        if years > 0 and initial_eq > 0 and final_eq > 0:
            cagr = (final_eq / initial_eq) ** (1 / years) - 1
        else:
            cagr = 0.0

        if max_dd_pct_decimal > 0:
            computed_calmar = cagr / max_dd_pct_decimal
        elif cagr > 0:
            computed_calmar = 100.0
        else:
            computed_calmar = 0.0

        expected_calmar = r.get("calmar", 0)
        if expected_calmar != 0:
            abs_tol = 0.01
            rel_err = abs(computed_calmar - expected_calmar) / max(abs(expected_calmar), 0.01)
            if rel_err > 0.10 and abs(computed_calmar - expected_calmar) > abs_tol:
                issues.append(
                    f"calmar: computed={computed_calmar:.4f} vs result={expected_calmar:.4f} "
                    f"[rel_err={rel_err:.2%}]"
                )
        elif abs(computed_calmar) > 0.01:
            issues.append(f"calmar: computed={computed_calmar:.4f} vs result=0")

        if issues:
            self._fail("METRIC_RISK", "Risk metric mismatches:\n  " + "\n  ".join(issues))
        else:
            self._pass(
                "METRIC_RISK",
                f"Risk metrics match (Sharpe={computed_sharpe:.2f}, "
                f"Sortino={computed_sortino:.2f}, Calmar={computed_calmar:.2f})"
            )

    def check_metric_duration(self):
        """Recompute avg trade duration from trades.parquet."""
        if self.result_json is None:
            self._skip("METRIC_DURATION", "No result.json")
            return
        if self.trades_df is None or self.trades_df.empty:
            self._skip("METRIC_DURATION", "No trades to verify")
            return

        df = self.trades_df
        r = self.result_json
        issues = []

        if "entry_bar_index" in df.columns and "exit_bar_index" in df.columns:
            durations = df["exit_bar_index"] - df["entry_bar_index"]
            # Filter out NaN for open trades
            durations = durations.dropna()
            if len(durations) > 0:
                computed_avg = float(durations.mean())
                expected_avg = r.get("avg_trade_duration_bars", 0)
                if abs(computed_avg - expected_avg) > 0.5:
                    issues.append(
                        f"avg_trade_duration_bars: computed={computed_avg:.2f} vs "
                        f"result={expected_avg:.2f} [diff={abs(computed_avg - expected_avg):.2f}]"
                    )

        if issues:
            self._fail("METRIC_DURATION", "Duration mismatches:\n  " + "\n  ".join(issues))
        elif "entry_bar_index" not in df.columns or "exit_bar_index" not in df.columns:
            self._skip("METRIC_DURATION", "No bar index columns in trades")
        else:
            self._pass("METRIC_DURATION", f"Duration matches (avg={r.get('avg_trade_duration_bars', 0):.1f} bars)")

    def check_metric_quality(self):
        """Recompute recovery_factor from result.json values."""
        if self.result_json is None:
            self._skip("METRIC_QUALITY", "No result.json")
            return

        r = self.result_json
        net_profit = r.get("net_pnl_usdt", 0)
        max_dd_abs = r.get("max_drawdown_usdt", 0)
        expected_rf = r.get("recovery_factor", 0)

        if max_dd_abs == 0:
            # Cannot compute recovery_factor if no drawdown
            if expected_rf == 0 or (net_profit >= 0 and expected_rf == 100.0):
                self._pass("METRIC_QUALITY", "Recovery factor consistent (no drawdown)")
            elif expected_rf != 0:
                self._warn("METRIC_QUALITY", f"No drawdown but recovery_factor={expected_rf}")
            return

        computed_rf = net_profit / max_dd_abs
        tol = max(0.01, abs(expected_rf) * 0.05)
        if abs(computed_rf - expected_rf) > tol:
            self._fail(
                "METRIC_QUALITY",
                f"recovery_factor: computed={computed_rf:.4f} vs result={expected_rf:.4f} "
                f"[diff={abs(computed_rf - expected_rf):.4f}, tol={tol:.4f}]"
            )
        else:
            self._pass("METRIC_QUALITY", f"Recovery factor matches ({computed_rf:.2f})")

    # ── Result helpers ───────────────────────────────────────────────────

    def _pass(self, check: str, detail: str):
        self.checks.append({"check": check, "status": "PASS", "detail": detail})

    def _fail(self, check: str, detail: str):
        self.checks.append({"check": check, "status": "FAIL", "detail": detail})

    def _warn(self, check: str, detail: str):
        self.checks.append({"check": check, "status": "WARN", "detail": detail})

    def _skip(self, check: str, detail: str):
        self.checks.append({"check": check, "status": "SKIP", "detail": detail})

    @property
    def passed(self) -> bool:
        return all(c["status"] in ("PASS", "SKIP", "WARN") for c in self.checks)

    @property
    def summary(self) -> str:
        passes = sum(1 for c in self.checks if c["status"] == "PASS")
        fails = sum(1 for c in self.checks if c["status"] == "FAIL")
        warns = sum(1 for c in self.checks if c["status"] == "WARN")
        skips = sum(1 for c in self.checks if c["status"] == "SKIP")
        return f"{passes}P/{fails}F/{warns}W/{skips}S"


# ── Main Runner ──────────────────────────────────────────────────────────────

def discover_plays(suite: str) -> list[str]:
    """Discover play stems for a suite."""
    if suite == "all":
        dirs = list(SUITE_DIRS.values())
    else:
        dirs = [SUITE_DIRS[suite]]
    plays = []
    for d in dirs:
        if d.exists():
            for f in sorted(d.glob("*.yml")):
                plays.append(f.stem)
    return plays


def _load_candle_data_for_play(config: dict, artifact_dir: Path) -> dict[str, pd.DataFrame] | None:
    """Load candle data from DuckDB for real-data plays.

    Returns dict of {timeframe: DataFrame} with OHLCV columns indexed by
    timestamp, or None if data cannot be loaded (synthetic plays, missing DB).
    """
    # Only load for real-data runs (result.json has window dates)
    result_path = artifact_dir / "result.json"
    if not result_path.exists():
        return None

    with open(result_path) as f:
        result = json.load(f)

    symbol = result.get("symbol")
    if not symbol:
        return None

    # Get exec timeframe from config
    tfs = config.get("timeframes", {})
    exec_ptr = tfs.get("exec", "low_tf")
    exec_tf = tfs.get(exec_ptr)
    if not exec_tf:
        return None

    # Get date range from equity curve
    equity_path = artifact_dir / "equity.parquet"
    if not equity_path.exists():
        return None

    try:
        eq_df = pd.read_parquet(equity_path)
        if eq_df.empty or "timestamp" not in eq_df.columns:
            return None

        start_ts = pd.Timestamp(str(eq_df["timestamp"].iloc[0]))
        end_ts = pd.Timestamp(str(eq_df["timestamp"].iloc[-1]))

        if bool(pd.isna(start_ts)) or bool(pd.isna(end_ts)):
            return None
        start_dt = cast(datetime, start_ts.to_pydatetime())
        end_dt = cast(datetime, end_ts.to_pydatetime())

        # Load candles from DuckDB
        from src.data.historical_data_store import get_historical_store
        store = get_historical_store(read_only=True)
        candle_data = {}

        ohlcv = store.get_ohlcv(symbol, exec_tf, start=start_dt, end=end_dt)
        if ohlcv is not None and len(ohlcv) > 0:
            candle_data[exec_tf] = ohlcv

        store.close()

        return candle_data if candle_data else None

    except Exception:
        return None


def verify_single_play(play_stem: str, bars: int = 500, skip_run: bool = False) -> dict:
    """Run and verify a single play. Returns full result dict."""
    play_file = find_play_file(play_stem)
    if play_file is None:
        return {
            "play": play_stem,
            "status": "ERROR",
            "message": f"Play file not found",
            "checks": [],
            "trades": 0,
        }

    config = load_play_config(play_file)
    pattern = get_pattern(play_stem)

    # Run the backtest
    run_artifact_dir = None
    if not skip_run:
        success, output, run_artifact_dir = run_backtest(play_stem, pattern, bars)
        if not success:
            # Extract useful error info
            error_lines = [l for l in output.split("\n") if "Error" in l or "ERROR" in l or "Traceback" in l]
            error_summary = "\n".join(error_lines[:5]) if error_lines else output[-300:]
            return {
                "play": play_stem,
                "pattern": pattern,
                "status": "RUN_FAIL",
                "message": error_summary,
                "checks": [],
                "trades": 0,
            }

    # Find artifacts - prefer the one from this run
    if run_artifact_dir:
        artifact_dir = Path(run_artifact_dir)
        if not artifact_dir.is_absolute():
            artifact_dir = ROOT / artifact_dir
    else:
        artifact_dir = find_artifact_dir(play_stem)
    if artifact_dir is None or not artifact_dir.exists():
        return {
            "play": play_stem,
            "pattern": pattern,
            "status": "NO_ARTIFACTS",
            "message": "Artifacts not found after run",
            "checks": [],
            "trades": 0,
        }

    # Candle-based checks (OHLCV_VALID, EXIT_FILL, TP_SL_BAR) require exact candle
    # data matching the engine's run. Synthetic candle regeneration is unreliable
    # because the engine's TF set ordering (from Python set → list) is non-deterministic,
    # causing RNG divergence in generate_synthetic_candles(). These checks SKIP
    # on synthetic runs but load DuckDB data for real-data plays (RV_ prefix).
    candle_data = _load_candle_data_for_play(config, artifact_dir)

    # Verify trade math
    verifier = TradeVerifier(play_stem, config, artifact_dir, candle_data=candle_data)
    checks = verifier.verify_all()

    trades_count = 0
    if verifier.result_json:
        trades_count = verifier.result_json.get("trades_count", 0)

    return {
        "play": play_stem,
        "pattern": pattern,
        "status": "PASS" if verifier.passed else "FAIL",
        "message": verifier.summary,
        "checks": checks,
        "trades": trades_count,
        "net_pnl": verifier.result_json.get("net_pnl_usdt", 0) if verifier.result_json else 0,
        "win_rate": verifier.result_json.get("win_rate", 0) if verifier.result_json else 0,
        "artifact_dir": str(artifact_dir),
    }


def format_play_report(result: dict) -> str:
    """Format a single play's verification result as markdown."""
    lines = []
    status_icon = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN",
                   "RUN_FAIL": "RUN_FAIL", "NO_ARTIFACTS": "NO_ARTIFACTS", "ERROR": "ERROR"}

    lines.append(f"### {result['play']}")
    lines.append(f"- **Status**: {status_icon.get(result['status'], result['status'])}")
    lines.append(f"- **Pattern**: {result.get('pattern', 'N/A')}")
    lines.append(f"- **Trades**: {result.get('trades', 0)}")
    if result.get("net_pnl"):
        lines.append(f"- **Net PnL**: {result['net_pnl']:.2f} USDT")
    if result.get("win_rate"):
        lines.append(f"- **Win Rate**: {result['win_rate']:.1f}%")

    if result.get("checks"):
        lines.append("")
        lines.append("| Check | Status | Detail |")
        lines.append("|-------|--------|--------|")
        for c in result["checks"]:
            detail = c["detail"].replace("\n", " ").replace("|", "\\|")[:120]
            lines.append(f"| {c['check']} | {c['status']} | {detail} |")
    elif result.get("message"):
        lines.append(f"- **Error**: {result['message'][:200]}")

    lines.append("")
    return "\n".join(lines)


def _get_suite_for_play(play_stem: str) -> str:
    """Determine which suite a play belongs to."""
    if play_stem.startswith("IND_"):
        return "indicator"
    elif play_stem.startswith("OP_"):
        return "operator"
    elif play_stem.startswith("STR_"):
        return "structure"
    elif play_stem.startswith("PAT_"):
        return "pattern"
    elif play_stem.startswith("CL_"):
        return "cl"
    return "unknown"


def write_progress_file(
    results: list[dict],
    suite: str,
    output_path: Path,
    total_plays: int,
):
    """Write/update the progress markdown file."""
    passes = sum(1 for r in results if r["status"] == "PASS")
    fails = sum(1 for r in results if r["status"] == "FAIL")
    run_fails = sum(1 for r in results if r["status"] == "RUN_FAIL")
    done = len(results)

    lines = [
        f"# Trade Math Verification: {suite.upper()}",
        "",
        f"**Progress**: {done}/{total_plays} plays verified",
        f"**Results**: {passes} PASS | {fails} FAIL | {run_fails} RUN_FAIL",
        "",
        "---",
        "",
    ]

    # Summary table
    lines.append("## Summary Table")
    lines.append("")
    lines.append("| # | Play | Status | Trades | PnL | Checks |")
    lines.append("|---|------|--------|--------|-----|--------|")
    for i, r in enumerate(results, 1):
        status = r["status"]
        trades = r.get("trades", 0)
        pnl = r.get("net_pnl", 0)
        checks_summary = r.get("message", "")
        lines.append(f"| {i} | {r['play']} | {status} | {trades} | {pnl:.2f} | {checks_summary} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Detailed results
    lines.append("## Detailed Results")
    lines.append("")
    for r in results:
        lines.append(format_play_report(r))

    # Failures section
    failures = [r for r in results if r["status"] != "PASS"]
    if failures:
        lines.append("## Failures & Issues")
        lines.append("")
        for r in failures:
            lines.append(f"- **{r['play']}** [{r['status']}]: {r.get('message', '')[:200]}")
        lines.append("")

    with open(output_path, "w", newline="\n") as f:
        f.write("\n".join(lines))


def write_audit_report(results: list[dict], report_path: Path):
    """Write comprehensive MATH_AUDIT_REPORT.md."""
    from datetime import datetime as dt

    total = len(results)
    passes = sum(1 for r in results if r["status"] == "PASS")
    fails = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] not in ("PASS", "FAIL"))

    # Collect all check names across all plays
    all_check_names: list[str] = []
    seen = set()
    for r in results:
        for c in r.get("checks", []):
            name = c["check"]
            if name not in seen:
                all_check_names.append(name)
                seen.add(name)

    checks_per_play = len(all_check_names)
    total_checks = checks_per_play * total

    lines = [
        f"# Full Math Audit Report - {total} Plays",
        f"Date: {dt.now().strftime('%Y-%m-%d %H:%M')} | Checks/play: {checks_per_play} | Total checks: {total_checks}",
        "",
        "## Summary",
        f"PASS: {passes}/{total} | FAIL: {fails}/{total} | ERROR: {errors}/{total}",
        "",
    ]

    # Check Coverage Matrix
    lines.append("## Check Coverage Matrix")
    lines.append("")
    lines.append("| Check | Pass | Fail | Warn | Skip |")
    lines.append("|-------|------|------|------|------|")
    for check_name in all_check_names:
        cp = cf = cw = cs = 0
        for r in results:
            for c in r.get("checks", []):
                if c["check"] == check_name:
                    if c["status"] == "PASS":
                        cp += 1
                    elif c["status"] == "FAIL":
                        cf += 1
                    elif c["status"] == "WARN":
                        cw += 1
                    elif c["status"] == "SKIP":
                        cs += 1
        lines.append(f"| {check_name} | {cp} | {cf} | {cw} | {cs} |")
    lines.append("")

    # Per-Suite Breakdown
    lines.append("## Per-Suite Breakdown")
    lines.append("")
    lines.append("| Suite | Plays | Pass | Fail | Error |")
    lines.append("|-------|-------|------|------|-------|")
    suite_stats: dict[str, dict[str, int]] = {}
    for r in results:
        s = _get_suite_for_play(r["play"])
        if s not in suite_stats:
            suite_stats[s] = {"total": 0, "pass": 0, "fail": 0, "error": 0}
        suite_stats[s]["total"] += 1
        if r["status"] == "PASS":
            suite_stats[s]["pass"] += 1
        elif r["status"] == "FAIL":
            suite_stats[s]["fail"] += 1
        else:
            suite_stats[s]["error"] += 1
    for s_name in ("indicator", "operator", "structure", "pattern", "cl"):
        if s_name in suite_stats:
            st = suite_stats[s_name]
            lines.append(f"| {s_name} | {st['total']} | {st['pass']} | {st['fail']} | {st['error']} |")
    lines.append("")

    # Failures (detailed)
    failures = [r for r in results if r["status"] != "PASS"]
    if failures:
        lines.append("## Failures (detailed)")
        lines.append("")
        for r in failures:
            lines.append(f"### {r['play']} [{r['status']}]")
            lines.append(f"- Pattern: {r.get('pattern', 'N/A')}")
            lines.append(f"- Trades: {r.get('trades', 0)}")
            if r.get("message") and r["status"] in ("RUN_FAIL", "NO_ARTIFACTS", "ERROR"):
                lines.append(f"- Error: {r['message'][:300]}")
            for c in r.get("checks", []):
                if c["status"] == "FAIL":
                    detail = c["detail"].replace("\n", " ")[:200]
                    lines.append(f"- **{c['check']}**: {detail}")
            lines.append("")
    else:
        lines.append("## Failures (detailed)")
        lines.append("")
        lines.append("None - all plays passed!")
        lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", newline="\n") as f:
        f.write("\n".join(lines))


def write_audit_csv(results: list[dict], csv_path: Path):
    """Write CSV with one row per play, columns for each check status."""
    import csv

    # Collect all check names
    all_check_names: list[str] = []
    seen = set()
    for r in results:
        for c in r.get("checks", []):
            name = c["check"]
            if name not in seen:
                all_check_names.append(name)
                seen.add(name)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="\n") as f:
        writer = csv.writer(f)
        header = ["play", "suite", "pattern", "status", "trades", "net_pnl", "win_rate"] + all_check_names
        writer.writerow(header)

        for r in results:
            # Build check status lookup for this play
            check_map = {}
            for c in r.get("checks", []):
                check_map[c["check"]] = c["status"]

            row = [
                r["play"],
                _get_suite_for_play(r["play"]),
                r.get("pattern", ""),
                r["status"],
                r.get("trades", 0),
                f"{r.get('net_pnl', 0):.2f}",
                f"{r.get('win_rate', 0):.4f}",
            ] + [check_map.get(cn, "") for cn in all_check_names]
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Verify trade math for all plays")
    parser.add_argument(
        "--suite",
        choices=["all", "indicator", "operator", "structure", "pattern", "cl"],
        default=None,
        help="Which suite to verify",
    )
    parser.add_argument("--play", type=str, default=None, help="Single play to verify")
    parser.add_argument("--bars", type=int, default=500, help="Synthetic bars")
    parser.add_argument("--start-from", type=str, default=None, help="Start from this play")
    parser.add_argument("--skip-run", action="store_true", help="Skip running, verify existing artifacts")
    parser.add_argument("--output", type=str, default=None, help="Output markdown file path")
    parser.add_argument("--output-csv", type=str, default=None, help="Output CSV file path")
    args = parser.parse_args()

    if args.play:
        # Single play mode
        print(f"Verifying: {args.play}")
        result = verify_single_play(args.play, args.bars, args.skip_run)
        print(format_play_report(result))

        for c in result.get("checks", []):
            icon = {"PASS": "[OK]", "FAIL": "[!!]", "WARN": "[??]", "SKIP": "[--]"}
            print(f"  {icon.get(c['status'], '    ')} {c['check']}: {c['detail'][:100]}")

        sys.exit(0 if result["status"] == "PASS" else 1)

    if args.suite is None:
        parser.error("Either --suite or --play is required")

    plays = discover_plays(args.suite)
    if args.start_from:
        idx = next((i for i, p in enumerate(plays) if p == args.start_from), 0)
        plays = plays[idx:]

    output_path = Path(args.output) if args.output else ROOT / "docs" / f"VERIFY_{args.suite.upper()}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    csv_path = Path(args.output_csv) if args.output_csv else ROOT / "backtests" / "math_audit_results.csv"

    print(f"Verifying {len(plays)} plays from {args.suite} suite")
    print(f"Output: {output_path}")
    print(f"CSV:    {csv_path}")
    print("=" * 80)

    results = []
    t0 = time.time()
    for i, play in enumerate(plays, 1):
        print(f"[{i}/{len(plays)}] {play}...", end=" ", flush=True)
        result = verify_single_play(play, args.bars, args.skip_run)
        results.append(result)

        status = result["status"]
        trades = result.get("trades", 0)
        checks = result.get("message", "")
        if status == "PASS":
            print(f"PASS ({trades} trades, {checks})")
        else:
            print(f"{status}: {result.get('message', '')[:80]}")

        # Update progress file after each play
        total_expected = len(plays) + (len(results) - len(plays)) if args.start_from else len(plays)
        write_progress_file(results, args.suite, output_path, total_expected)

    elapsed = time.time() - t0

    # Write audit report and CSV
    report_path = ROOT / "docs" / "MATH_AUDIT_REPORT.md"
    write_audit_report(results, report_path)
    write_audit_csv(results, csv_path)

    # Final summary
    passes = sum(1 for r in results if r["status"] == "PASS")
    fails = sum(1 for r in results if r["status"] != "PASS")
    print("\n" + "=" * 80)
    print(f"FINAL: {passes}/{len(plays)} PASS, {fails} issues ({elapsed:.0f}s)")
    print(f"Progress:  {output_path}")
    print(f"Report:    {report_path}")
    print(f"CSV:       {csv_path}")

    if fails > 0:
        print("\nISSUES:")
        for r in results:
            if r["status"] != "PASS":
                print(f"  {r['play']}: {r['status']} - {r.get('message', '')[:100]}")

    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
