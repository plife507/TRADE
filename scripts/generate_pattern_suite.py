"""
Generate Play YAML files for synthetic pattern coverage.

Creates one simple play per synthetic pattern to verify the engine handles
all 34 available patterns without error.

Usage:
    python scripts/generate_pattern_suite.py
"""

from __future__ import annotations

from pathlib import Path

SUITE_DIR = Path("plays/pattern_suite")

PATTERNS = [
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

# Most patterns need different indicators to be realistic
# Downtrend patterns -> short_only; uptrend/neutral -> long_only
SHORT_PATTERNS = {
    "trend_down_clean", "reversal_v_top", "reversal_double_top",
    "distribution", "mtf_aligned_bear", "liquidity_hunt_highs",
}

PLAY_TEMPLATE = """\
version: "3.0.0"
name: "pat_{idx:03d}_{pattern}"
description: |
  Pattern Suite - Synthetic pattern '{pattern}' coverage test.
  Simple EMA crossover strategy to verify engine handles this pattern.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
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
  ema_9:
    indicator: ema
    params: {{length: 9}}

  ema_21:
    indicator: ema
    params: {{length: 21}}

  rsi_14:
    indicator: rsi
    params: {{length: 14}}

structures:
  exec: []

actions:
  {action_block}

position_policy:
  mode: "{mode}"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0
"""


def main() -> None:
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    for idx, pattern in enumerate(PATTERNS, start=1):
        is_short = pattern in SHORT_PATTERNS
        if is_short:
            action_block = (
                'entry_short:\n'
                '    all:\n'
                '      - ["ema_9", "cross_below", "ema_21"]'
            )
            mode = "short_only"
        else:
            action_block = (
                'entry_long:\n'
                '    all:\n'
                '      - ["ema_9", "cross_above", "ema_21"]'
            )
            mode = "long_only"

        content = PLAY_TEMPLATE.format(
            idx=idx,
            pattern=pattern,
            action_block=action_block,
            mode=mode,
        )

        filename = f"PAT_{idx:03d}_{pattern}.yml"
        filepath = SUITE_DIR / filename
        with open(filepath, "w", newline="\n") as f:
            f.write(content)
        print(f"  Created: {filepath.name}")
        count += 1

    print(f"\nDone! {count} pattern suite plays written to {SUITE_DIR}/")


if __name__ == "__main__":
    main()
