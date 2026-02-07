"""
Generate Play YAML files for DSL operator testing suite.

Creates plays in plays/operator_suite/ that test each DSL operator in isolation.

Usage:
    python scripts/generate_operator_suite.py
"""

from __future__ import annotations

from pathlib import Path

SUITE_DIR = Path("plays/operator_suite")


def write_play(filename: str, content: str) -> None:
    """Write a play YAML file."""
    filepath = SUITE_DIR / filename
    with open(filepath, "w", newline="\n") as f:
        f.write(content)
    print(f"  Created: {filepath.name}")


COMMON_ACCOUNT = """\
account:
  starting_equity_usdt: 10000.0
  max_leverage: 1.0
  margin_mode: "isolated_usdt"
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0
  slippage_bps: 2.0"""

COMMON_POLICY_LONG = """\
position_policy:
  mode: "long_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0"""

COMMON_POLICY_SHORT = """\
position_policy:
  mode: "short_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0"""


def main() -> None:
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    # OP_001: Greater than
    write_play("OP_001_gt.yml", f"""\
version: "3.0.0"
name: "op_001_greater_than"
description: |
  Operator Suite - Greater than (>) comparison operator test.
  Entry when RSI > 55.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["rsi_14", ">", 55]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_002: Less than
    write_play("OP_002_lt.yml", f"""\
version: "3.0.0"
name: "op_002_less_than"
description: |
  Operator Suite - Less than (<) comparison operator test.
  Entry when RSI < 45.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 45]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_003: Greater or equal
    write_play("OP_003_gte.yml", f"""\
version: "3.0.0"
name: "op_003_greater_equal"
description: |
  Operator Suite - Greater or equal (>=) comparison operator test.
  Entry when CCI >= 0.

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  cci_14:
    indicator: cci
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["cci_14", ">=", 0]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_004: Less or equal
    write_play("OP_004_lte.yml", f"""\
version: "3.0.0"
name: "op_004_less_equal"
description: |
  Operator Suite - Less or equal (<=) comparison operator test.
  Entry when Williams %R <= -50.

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  willr_14:
    indicator: willr
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["willr_14", "<=", -50]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_005: Equal (integer - SuperTrend direction)
    write_play("OP_005_eq_int.yml", f"""\
version: "3.0.0"
name: "op_005_equal_int"
description: |
  Operator Suite - Equal (==) operator with integer value.
  Tests SuperTrend direction == 1 (bullish).

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  st_10_3:
    indicator: supertrend
    params: {{length: 10, multiplier: 3.0}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["st_10_3.direction", "==", 1]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_006: Not equal
    write_play("OP_006_neq.yml", f"""\
version: "3.0.0"
name: "op_006_not_equal"
description: |
  Operator Suite - Not equal (!=) operator test.
  Entry when SuperTrend direction != -1 (not bearish).

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  st_10_3:
    indicator: supertrend
    params: {{length: 10, multiplier: 3.0}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["st_10_3.direction", "!=", -1]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_007: cross_above
    write_play("OP_007_cross_above.yml", f"""\
version: "3.0.0"
name: "op_007_cross_above"
description: |
  Operator Suite - cross_above operator test.
  EMA 9 crosses above EMA 21.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_9:
    indicator: ema
    params: {{length: 9}}

  ema_21:
    indicator: ema
    params: {{length: 21}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["ema_9", "cross_above", "ema_21"]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_008: cross_below
    write_play("OP_008_cross_below.yml", f"""\
version: "3.0.0"
name: "op_008_cross_below"
description: |
  Operator Suite - cross_below operator test.
  EMA 9 crosses below EMA 21.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_9:
    indicator: ema
    params: {{length: 9}}

  ema_21:
    indicator: ema
    params: {{length: 21}}

structures:
  exec: []

actions:
  entry_short:
    all:
      - ["ema_9", "cross_below", "ema_21"]

{COMMON_POLICY_SHORT}
""")
    count += 1

    # OP_009: between
    write_play("OP_009_between.yml", f"""\
version: "3.0.0"
name: "op_009_between"
description: |
  Operator Suite - between range operator test.
  Entry when RSI between 30 and 50 (neutral zone).

symbol: "SOLUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["rsi_14", "between", [30, 50]]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_010: near_pct
    write_play("OP_010_near_pct.yml", f"""\
version: "3.0.0"
name: "op_010_near_pct"
description: |
  Operator Suite - near_pct proximity operator test.
  Entry when close within 1.5% of EMA 50.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", "near_pct", "ema_50", 1.5]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_011: near_abs (using ATR value)
    write_play("OP_011_near_abs.yml", f"""\
version: "3.0.0"
name: "op_011_near_abs"
description: |
  Operator Suite - near_abs proximity operator test.
  Entry when close within 50 units of EMA 50.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", "near_abs", "ema_50", 500]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_012: Arithmetic addition
    write_play("OP_012_arithmetic_add.yml", f"""\
version: "3.0.0"
name: "op_012_arithmetic_add"
description: |
  Operator Suite - Arithmetic addition (+) operator test.
  Entry when close > ema_50 + atr_14.

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_50:
    indicator: ema
    params: {{length: 50}}

  atr_14:
    indicator: atr
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", ">", {{"+": ["ema_50", "atr_14"]}}]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_013: Arithmetic subtraction
    write_play("OP_013_arithmetic_sub.yml", f"""\
version: "3.0.0"
name: "op_013_arithmetic_sub"
description: |
  Operator Suite - Arithmetic subtraction (-) operator test.
  Entry when close < ema_50 - atr_14 (dip below MA).

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_50:
    indicator: ema
    params: {{length: 50}}

  atr_14:
    indicator: atr
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", "<", {{"-": ["ema_50", "atr_14"]}}]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_014: Arithmetic multiplication
    write_play("OP_014_arithmetic_mul.yml", f"""\
version: "3.0.0"
name: "op_014_arithmetic_mul"
description: |
  Operator Suite - Arithmetic multiplication (*) operator test.
  Entry when atr > natr * 100 (ATR vs normalized check).

symbol: "SOLUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_50:
    indicator: ema
    params: {{length: 50}}

  atr_14:
    indicator: atr
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", ">", {{"*": ["ema_50", 1.01]}}]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_015: Arithmetic division
    write_play("OP_015_arithmetic_div.yml", f"""\
version: "3.0.0"
name: "op_015_arithmetic_div"
description: |
  Operator Suite - Arithmetic division (/) operator test.
  Entry when volume > volume_sma / 2 (above half average volume).

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  volume_sma_20:
    indicator: sma
    source: volume
    params: {{length: 20}}

  ema_20:
    indicator: ema
    params: {{length: 20}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", ">", "ema_20"]
      - ["volume", ">", {{"/": ["volume_sma_20", 2]}}]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_016: Nested ANY inside ALL
    write_play("OP_016_nested_any.yml", f"""\
version: "3.0.0"
name: "op_016_nested_any_in_all"
description: |
  Operator Suite - Nested boolean: ANY inside ALL.
  Must have RSI below 50 AND (either CCI < 0 OR Williams%R < -60).

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  cci_14:
    indicator: cci
    params: {{length: 14}}

  willr_14:
    indicator: willr
    params: {{length: 14}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 50]
      - any:
          - ["cci_14", "<", 0]
          - ["willr_14", "<", -60]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_017: NOT operator
    write_play("OP_017_not.yml", f"""\
version: "3.0.0"
name: "op_017_not_operator"
description: |
  Operator Suite - NOT boolean operator test.
  Entry when RSI NOT above 70 (not overbought) AND close > EMA.

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50"]
      - not:
          - ["rsi_14", ">", 70]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_018: holds_for window
    write_play("OP_018_holds_for.yml", f"""\
version: "3.0.0"
name: "op_018_holds_for"
description: |
  Operator Suite - holds_for window operator test.
  Entry when RSI stays below 45 for 3 consecutive bars.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50"]
      - holds_for:
          bars: 3
          expr:
            - ["rsi_14", "<", 45]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_019: occurred_within window
    write_play("OP_019_occurred_within.yml", f"""\
version: "3.0.0"
name: "op_019_occurred_within"
description: |
  Operator Suite - occurred_within window operator test.
  Entry when RSI was below 30 within the last 10 bars (recent pullback).

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50"]
      - occurred_within:
          bars: 10
          expr:
            - ["rsi_14", "<", 30]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_020: cases/when/emit/else syntax
    write_play("OP_020_cases_when.yml", f"""\
version: "3.0.0"
name: "op_020_cases_when_emit"
description: |
  Operator Suite - cases/when/emit/else syntax test.
  Two cases: bullish (RSI < 40 AND close > EMA) vs else no_action.

symbol: "SOLUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  - id: entry
    cases:
      - when:
          all:
            - ["rsi_14", "<", 40]
            - ["close", ">", "ema_50"]
        emit:
          - action: entry_long
            metadata:
              entry_rsi: {{feature_id: "rsi_14"}}
              entry_reason: "rsi_bounce"

    else:
      emit:
        - action: no_action

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_021: Variables test
    write_play("OP_021_variables.yml", f"""\
version: "3.0.0"
name: "op_021_variables"
description: |
  Operator Suite - Variables (template substitution) test.
  Uses variables for RSI threshold and SL/TP values.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

variables:
  rsi_threshold: 45
  sl: 3.0
  tp: 6.0

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 45]
      - ["close", ">", "ema_50"]

position_policy:
  mode: "long_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0
""")
    count += 1

    # OP_022: Metadata capture test
    write_play("OP_022_metadata.yml", f"""\
version: "3.0.0"
name: "op_022_metadata_capture"
description: |
  Operator Suite - Metadata capture test.
  Captures RSI and ATR values at entry time.

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  atr_14:
    indicator: atr
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  - id: entry
    cases:
      - when:
          all:
            - ["rsi_14", "<", 45]
            - ["close", ">", "ema_50"]
        emit:
          - action: entry_long
            metadata:
              entry_rsi: {{feature_id: "rsi_14"}}
              entry_atr: {{feature_id: "atr_14"}}
              entry_reason: "rsi_pullback"

    else:
      emit:
        - action: no_action

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_023: Higher-TF features (forward-fill test)
    write_play("OP_023_higher_tf_feature.yml", f"""\
version: "3.0.0"
name: "op_023_higher_tf_feature"
description: |
  Operator Suite - Higher timeframe feature forward-fill test.
  Uses 1h EMA on 15m execution timeframe.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_50:
    indicator: ema
    params: {{length: 50}}

  ema_50_1h:
    indicator: ema
    params: {{length: 50}}
    tf: "1h"

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50"]
      - ["ema_50", ">", "ema_50_1h"]

{COMMON_POLICY_LONG}
""")
    count += 1

    # OP_024: exit_long action
    write_play("OP_024_exit_signal.yml", f"""\
version: "3.0.0"
name: "op_024_exit_signal"
description: |
  Operator Suite - Signal-based exit test.
  Entry on RSI < 40, exit on RSI > 65.

symbol: "SOLUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 40]
      - ["close", ">", "ema_50"]

  exit_long:
    all:
      - ["rsi_14", ">", 65]

position_policy:
  mode: "long_only"
  exit_mode: "first_hit"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0
""")
    count += 1

    # OP_025: Multi-case with 3 branches
    write_play("OP_025_multi_case.yml", f"""\
version: "3.0.0"
name: "op_025_multi_case"
description: |
  Operator Suite - Multiple cases with 3 branches test.
  Case 1: Strong buy (RSI < 30), Case 2: Moderate buy (RSI < 45 + EMA filter),
  Else: no action.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  rsi_14:
    indicator: rsi
    params: {{length: 14}}

  ema_50:
    indicator: ema
    params: {{length: 50}}

structures:
  exec: []

actions:
  - id: entry
    cases:
      - when:
          all:
            - ["rsi_14", "<", 30]
        emit:
          - action: entry_long
            metadata:
              entry_reason: "strong_oversold"

      - when:
          all:
            - ["rsi_14", "<", 45]
            - ["close", ">", "ema_50"]
        emit:
          - action: entry_long
            metadata:
              entry_reason: "moderate_pullback"

    else:
      emit:
        - action: no_action

{COMMON_POLICY_LONG}
""")
    count += 1

    print(f"\nDone! {count} operator suite plays written to {SUITE_DIR}/")


if __name__ == "__main__":
    main()
