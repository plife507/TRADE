# Recipes

Complete play examples by strategy concept.

## EMA crossover with trend filter (trend_following)

```yaml
version: "3.0.0"
name: "btc_ema_cross_trend"
symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  ema_9: { indicator: ema, params: { length: 9 } }
  ema_21: { indicator: ema, params: { length: 21 } }
  ema_50_1h: { indicator: ema, params: { length: 50 }, tf: "1h" }

actions:
  entry_long:
    all:
      - ["close", ">", "ema_50_1h"]
      - ["ema_9", "cross_above", "ema_21"]
  exit_long:
    all:
      - ["ema_9", "cross_below", "ema_21"]

position_policy:
  mode: "long_only"
  exit_mode: "first_hit"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 100.0

validation:
  pattern: "trend_up_clean"
```

## RSI mean reversion (mean_reversion)

```yaml
version: "3.0.0"
name: "eth_rsi_reversion"
symbol: "ETHUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "4h"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 2.0
  max_drawdown_pct: 15.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  rsi_14: { indicator: rsi, params: { length: 14 } }
  bbands_20: { indicator: bbands, params: { length: 20, std: 2.0 } }

actions:
  entry_long:
    all:
      - ["rsi_14", "<", 30]
      - ["close", "<", "bbands_20.lower"]
  exit_long:
    any:
      - ["rsi_14", ">", 70]
      - ["close", ">", "bbands_20.middle"]

position_policy:
  mode: "long_only"
  exit_mode: "first_hit"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 3.0
  max_position_pct: 100.0

validation:
  pattern: "range_wide"
```

## ICT BOS entry with cases (long_short)

```yaml
version: "3.0.0"
name: "btc_ict_bos_cases"
symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "4h"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  rsi_14: { indicator: rsi, params: { length: 14 } }
  atr_14: { indicator: atr, params: { length: 14 } }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5, atr_key: atr_14 }
    - type: market_structure
      key: ms
      uses: swing

actions:
  - id: entry
    cases:
      - when:
          all:
            - ["ms.bos_this_bar", "==", 1]
            - ["ms.bias", "==", 1]
            - ["rsi_14", "<", 60]
        emit:
          - action: entry_long
      - when:
          all:
            - ["ms.bos_this_bar", "==", 1]
            - ["ms.bias", "==", -1]
            - ["rsi_14", ">", 40]
        emit:
          - action: entry_short
    else:
      emit:
        - action: no_action

position_policy:
  mode: "long_short"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 3.0
  take_profit_pct: 6.0
  max_position_pct: 100.0

validation:
  pattern: "trend_up_clean"
```

## Fibonacci OTE with trend-wave (trend_following)

```yaml
version: "3.0.0"
name: "btc_fib_ote_trend"
symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  rsi_14: { indicator: rsi, params: { length: 14 } }
  atr_14: { indicator: atr, params: { length: 14 } }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing
    - type: fibonacci
      key: fib
      uses: [swing, trend]
      params:
        levels: [0.618, 0.705, 0.786]
        mode: retracement
        use_trend_anchor: true

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["close", "near_pct", "fib.level[0.705]", 1.5]
      - ["rsi_14", "<", 50]

position_policy:
  mode: "long_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk_model:
  stop_loss: { type: "atr_multiple", value: 2.0, atr_feature_id: "atr_14" }
  take_profit: { type: "rr_ratio", value: 2.0 }
  sizing: { model: "risk_based", value: 1.0, max_leverage: 3.0 }

validation:
  pattern: "trend_up_clean"
```

## FVG + liquidity sweep (ICT)

```yaml
version: "3.0.0"
name: "btc_fvg_liq_sweep"
symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "4h"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  atr_14: { indicator: atr, params: { length: 14 } }
  rsi_14: { indicator: rsi, params: { length: 14 } }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 3, right: 3 }
    - type: fair_value_gap
      key: fvg
      params: { atr_key: atr_14, min_gap_atr: 0.5, max_active: 5 }
    - type: liquidity_zones
      key: liq
      uses: swing
      params: { atr_key: atr_14, min_touches: 2 }

setups:
  bull_fvg_entry:
    all:
      - ["fvg.active_bull_count", ">", 0]
      - ["close", "near_pct", "fvg.nearest_bull_lower", 2]

actions:
  entry_long:
    all:
      - setup: bull_fvg_entry
      - occurred_within:
          bars: 10
          expr:
            - ["liq.sweep_this_bar", "==", 1]
            - ["liq.sweep_direction", "==", -1]
      - ["rsi_14", "<", 50]

position_policy:
  mode: "long_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 100.0

validation:
  pattern: "liquidity_hunt_lows"
```

## Breakout with volume + ATR risk (breakout)

```yaml
version: "3.0.0"
name: "sol_breakout_volume"
symbol: "SOLUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "4h"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 5.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  atr_14: { indicator: atr, params: { length: 14 } }
  volume_sma_20: { indicator: sma, source: volume, params: { length: 20 } }

structures:
  exec:
    - type: rolling_window
      key: rolling_high_20
      params: { mode: max, size: 20, source: high }

actions:
  entry_long:
    all:
      - ["close", ">", "rolling_high_20.value"]
      - lhs: ["volume", "/", "volume_sma_20"]
        op: ">"
        rhs: 2.0

position_policy:
  mode: "long_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk_model:
  stop_loss: { type: "atr_multiple", value: 2.0, atr_feature_id: "atr_14" }
  take_profit: { type: "rr_ratio", value: 2.0 }
  sizing: { model: "risk_based", value: 1.0, max_leverage: 5.0 }

validation:
  pattern: "breakout_clean"
```

## Premium/discount with trailing stop (ICT)

```yaml
version: "3.0.0"
name: "btc_pd_trailing"
symbol: "BTCUSDT"

timeframes:
  low_tf: "15m"
  med_tf: "1h"
  high_tf: "4h"
  exec: "low_tf"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  atr_14: { indicator: atr, params: { length: 14 } }

structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing
    - type: premium_discount
      key: pd
      uses: swing

actions:
  entry_long:
    all:
      - ["trend.direction", "==", 1]
      - ["pd.zone", "==", "discount"]
      - ["pd.depth_pct", "<", 0.3]

position_policy:
  mode: "long_only"
  exit_mode: "sl_tp_only"
  max_positions_per_symbol: 1

risk:
  stop_loss:
    type: "trailing_atr"
    atr_multiplier: 2.0
    atr_feature_id: "atr_14"
    activation_pct: 1.0
  take_profit_pct: 6.0
  max_position_pct: 100.0
  break_even:
    activation_pct: 1.0
    offset_pct: 0.1

validation:
  pattern: "trend_up_clean"
```
