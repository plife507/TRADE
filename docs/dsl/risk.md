# Risk Model & Entries

## Shorthand (recommended)

```yaml
risk:
  stop_loss_pct: 2.0               # ROI-based: 2% of margin
  take_profit_pct: 4.0             # ROI-based: 4% of margin
  max_position_pct: 100.0          # % of equity as position
```

**Percentages are ROI-based** (margin %). With 10x leverage: 2% SL = 0.2% price move.

## Full format

```yaml
risk_model:
  stop_loss:
    type: "percent"                # percent | atr_multiple | structure | fixed_points | trailing_atr | trailing_pct
    value: 2.0
  take_profit:
    type: "rr_ratio"               # percent | rr_ratio | atr_multiple | fixed_points
    value: 2.0                     # 2R = 2x stop distance
  sizing:
    model: "percent_equity"        # percent_equity | risk_based | fixed_usdt
    value: 10.0                    # 10% of equity as margin
    max_leverage: 3.0
```

## SL types

| Type | Params | Description |
|------|--------|-------------|
| `percent` | `value` | ROI-based % of margin |
| `atr_multiple` | `value`, `atr_feature_id` | ATR x multiplier. Requires declared ATR feature |
| `structure` | `value` (fallback %) | Dynamic — uses swing levels |
| `fixed_points` | `value` | Absolute price distance |
| `trailing_atr` | `atr_multiplier`, `atr_feature_id`, `activation_pct` | Trail at ATR distance after activation |
| `trailing_pct` | `trail_pct`, `activation_pct` | Trail at % distance after activation |

## TP types

| Type | Params | Description |
|------|--------|-------------|
| `percent` | `value` | ROI-based % of margin |
| `rr_ratio` | `value` | Multiple of SL distance (2.0 = 2R) |
| `atr_multiple` | `value`, `atr_feature_id` | ATR x multiplier |
| `fixed_points` | `value` | Absolute price distance |

## Trailing stop

```yaml
risk:
  stop_loss:
    type: "trailing_atr"
    atr_multiplier: 2.0
    atr_feature_id: "atr_14"      # Must be declared in features
    activation_pct: 1.0            # Start trailing after 1% profit (0 = immediate)
```

## Break-even stop

```yaml
risk:
  break_even:
    activation_pct: 1.0            # Move to BE after 1% profit
    offset_pct: 0.1                # 0.1% above entry (positive = favorable)
```

## Sizing models

| Model | Param | Description |
|-------|-------|-------------|
| `percent_equity` | `value` | % of equity as margin |
| `risk_based` | `value` | Risk % per trade (SL distance determines size) |
| `fixed_usdt` | `value` | Fixed USDT margin per trade |

## TP/SL order types

```yaml
risk:
  tp_order_type: "Market"          # Market | Limit
  sl_order_type: "Market"          # Market | Limit
```

## Entry orders

```yaml
entry:
  order_type: "MARKET"             # MARKET (default) | LIMIT
  limit_offset_pct: 0.05           # % offset from close (LIMIT only)
  time_in_force: "GTC"             # GTC | IOC | FOK | PostOnly
  expire_after_bars: 10            # 0 = no expiry
```

## Defaults

| Field | Default |
|-------|---------|
| `stop_loss_pct` | — (required) |
| `take_profit_pct` | — (required) |
| `max_position_pct` | 100.0 |
| `entry.order_type` | `MARKET` |
| `entry.time_in_force` | `GTC` |
| `tp_order_type` | `Market` |
| `sl_order_type` | `Market` |
| `risk_per_trade_pct` | 1.0 |
