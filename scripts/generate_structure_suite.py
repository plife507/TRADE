"""
Generate Play YAML files for structure type testing suite.

Creates plays in plays/structure_suite/ that test each of the 7 structure types
and their sub-field access patterns.

Usage:
    python scripts/generate_structure_suite.py
"""

from __future__ import annotations

from pathlib import Path

SUITE_DIR = Path("plays/structure_suite")


def write_play(filename: str, content: str) -> None:
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


def main() -> None:
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    # STR_001: Swing detector alone
    write_play("STR_001_swing_basic.yml", f"""\
version: "3.0.0"
name: "str_001_swing_basic"
description: |
  Structure Suite - Swing detector basic test.
  Uses swing high/low detection with simple EMA filter.
  Tests swing.last_high_price and swing.last_low_price access.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_20:
    indicator: ema
    params: {{length: 20}}

structures:
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

actions:
  entry_long:
    all:
      - ["close", ">", "ema_20"]

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

    # STR_002: Trend detector (depends on swing)
    write_play("STR_002_trend_direction.yml", f"""\
version: "3.0.0"
name: "str_002_trend_direction"
description: |
  Structure Suite - Trend detector direction filter test.
  Entry when trend.direction == 1 (bullish swing structure trend).

symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_20:
    indicator: ema
    params: {{length: 20}}

structures:
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: trend
      key: trend
      uses: swing

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["close", ">", "ema_20"]

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

    # STR_003: Market structure BOS
    write_play("STR_003_ms_bos.yml", f"""\
version: "3.0.0"
name: "str_003_market_structure_bos"
description: |
  Structure Suite - Market structure Break of Structure (BOS) test.
  Entry on bullish BOS event with trend filter.

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
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: market_structure
      key: ms
      uses: swing

    - type: trend
      key: trend
      uses: swing

actions:
  entry_long:
    all:
      - ["ms.bos_this_bar", "==", 1]
      - ["ms.bos_direction", "==", "bullish"]
      - ["rsi_14", "<", 60]

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

    # STR_004: Market structure CHoCH
    write_play("STR_004_ms_choch.yml", f"""\
version: "3.0.0"
name: "str_004_market_structure_choch"
description: |
  Structure Suite - Market structure Change of Character (CHoCH) test.
  Entry on bullish CHoCH (reversal from bearish).

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
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: market_structure
      key: ms
      uses: swing

actions:
  entry_long:
    all:
      - ["ms.choch_this_bar", "==", 1]
      - ["ms.choch_direction", "==", "bullish"]

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

    # STR_005: Fibonacci retracement
    write_play("STR_005_fibonacci.yml", f"""\
version: "3.0.0"
name: "str_005_fibonacci_retracement"
description: |
  Structure Suite - Fibonacci retracement level test.
  Entry when price near 0.618 fib level.

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

structures:
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: trend
      key: trend
      uses: swing

    - type: fibonacci
      key: fib
      uses: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["rsi_14", "<", 50]

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

    # STR_006: Derived zone
    write_play("STR_006_derived_zone.yml", f"""\
version: "3.0.0"
name: "str_006_derived_zone"
description: |
  Structure Suite - Derived zone (fib-based zones) test.
  Tests derived_zone with any_touched field.

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
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: trend
      key: trend
      uses: swing

    - type: derived_zone
      key: fib_zones
      uses: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement
        max_active: 5
        width_pct: 0.002

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["rsi_14", "<", 50]

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

    # STR_007: Zone (demand)
    write_play("STR_007_zone_demand.yml", f"""\
version: "3.0.0"
name: "str_007_zone_demand"
description: |
  Structure Suite - Demand zone test.
  Tests zone structure with demand type.

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
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: zone
      key: demand_zone
      uses: swing
      params:
        zone_type: demand
        width_atr: 1.5

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 45]

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

    # STR_008: Zone (supply)
    write_play("STR_008_zone_supply.yml", f"""\
version: "3.0.0"
name: "str_008_zone_supply"
description: |
  Structure Suite - Supply zone test.
  Tests zone structure with supply type for short entries.

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

structures:
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: zone
      key: supply_zone
      uses: swing
      params:
        zone_type: supply
        width_atr: 1.5

actions:
  entry_short:
    all:
      - ["rsi_14", ">", 55]

position_policy:
  mode: "short_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0
""")
    count += 1

    # STR_009: Rolling window min
    write_play("STR_009_rolling_min.yml", f"""\
version: "3.0.0"
name: "str_009_rolling_window_min"
description: |
  Structure Suite - Rolling window min test.
  Uses rolling 20-bar low as support reference.

symbol: "SOLUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_20:
    indicator: ema
    params: {{length: 20}}

structures:
  exec:
    - type: rolling_window
      key: rolling_low_20
      params:
        mode: min
        size: 20
        source: low

actions:
  entry_long:
    all:
      - ["close", ">", "ema_20"]

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

    # STR_010: Rolling window max
    write_play("STR_010_rolling_max.yml", f"""\
version: "3.0.0"
name: "str_010_rolling_window_max"
description: |
  Structure Suite - Rolling window max test.
  Uses rolling 20-bar high as resistance reference.

symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

{COMMON_ACCOUNT}

features:
  ema_20:
    indicator: ema
    params: {{length: 20}}

structures:
  exec:
    - type: rolling_window
      key: rolling_high_20
      params:
        mode: max
        size: 20
        source: high

actions:
  entry_short:
    all:
      - ["close", "<", "ema_20"]

position_policy:
  mode: "short_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0
""")
    count += 1

    # STR_011: Swing + Trend + MS chain
    write_play("STR_011_full_chain.yml", f"""\
version: "3.0.0"
name: "str_011_full_chain"
description: |
  Structure Suite - Full structure chain: swing -> trend + market_structure.
  Tests dependency chain with multiple structure types.

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

structures:
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: trend
      key: trend
      uses: swing

    - type: market_structure
      key: ms
      uses: swing

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["rsi_14", "<", 50]

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

    # STR_012: Multi-TF structures
    write_play("STR_012_multi_tf.yml", f"""\
version: "3.0.0"
name: "str_012_multi_tf_structures"
description: |
  Structure Suite - Multi-timeframe structure test.
  Exec timeframe swing + trend, daily swing + trend.

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
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: trend
      key: trend
      uses: swing

  high_tf:
    "D":
      - type: swing
        key: swing_D
        params: {{left: 3, right: 3}}

      - type: trend
        key: trend_D
        uses: swing_D

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["trend_D.direction", "==", 1]
      - ["rsi_14", "<", 50]

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

    # STR_013: All structure types combined
    write_play("STR_013_all_types.yml", f"""\
version: "3.0.0"
name: "str_013_all_structure_types"
description: |
  Structure Suite - All 7 structure types in one play.
  Tests swing, trend, market_structure, fibonacci, derived_zone, zone, rolling_window.

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
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: trend
      key: trend
      uses: swing

    - type: market_structure
      key: ms
      uses: swing

    - type: fibonacci
      key: fib
      uses: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement

    - type: derived_zone
      key: fib_zones
      uses: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement
        max_active: 5
        width_pct: 0.002

    - type: zone
      key: demand_zone
      uses: swing
      params:
        zone_type: demand
        width_atr: 1.5

    - type: rolling_window
      key: rolling_high_20
      params:
        mode: max
        size: 20
        source: high

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["rsi_14", "<", 50]
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

    # STR_014: Trend direction short
    write_play("STR_014_trend_short.yml", f"""\
version: "3.0.0"
name: "str_014_trend_short"
description: |
  Structure Suite - Trend direction == -1 short test.
  Tests bearish trend detection for short entries.

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

structures:
  exec:
    - type: swing
      key: swing
      params: {{left: 5, right: 5}}

    - type: trend
      key: trend
      uses: swing

actions:
  entry_short:
    all:
      - ["trend.direction", "==", -1]
      - ["rsi_14", ">", 50]

position_policy:
  mode: "short_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0
""")
    count += 1

    print(f"\nDone! {count} structure suite plays written to {SUITE_DIR}/")


if __name__ == "__main__":
    main()
