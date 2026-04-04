# Play Skeleton

## Minimal valid play

```yaml
version: "3.0.0"
name: "strategy_name"          # snake_case, encode key params
symbol: "BTCUSDT"              # Bybit perpetual symbol
description: "What it does"    # Optional

timeframes:
  low_tf: "15m"                # Fast: execution, entries
  med_tf: "1h"                 # Medium: structure, bias
  high_tf: "D"                 # Slow: trend, context
  exec: "low_tf"              # POINTER to role (never raw "15m")

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  max_drawdown_pct: 20.0
  margin_mode: "isolated_usdt"
  fee_model: { taker_bps: 5.5, maker_bps: 2.0 }
  slippage_bps: 2.0

features:
  ema_9: { indicator: ema, params: { length: 9 } }

structures:                    # Optional — see structures.md
  exec: []

setups: {}                     # Optional — see conditions.md

actions:
  entry_long:
    all:
      - ["ema_9", ">", "close"]

position_policy:
  mode: "long_only"            # long_only | short_only | long_short
  exit_mode: "sl_tp_only"     # sl_tp_only | signal | first_hit
  max_positions_per_symbol: 1

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 100.0

validation:                    # REQUIRED for --synthetic backtest
  pattern: "trend_up_clean"
```

## Backtest config (optional)

Simulation-only overrides. No effect in live/shadow mode.

```yaml
backtest:
  equity: 10000.0              # Override account starting equity for this sim
  slippage_bps: 2.0            # Override account slippage for this sim
```

Defaults come from `config/defaults.yml` if section is omitted.

## Deploy config (optional)

Live trading and shadow deployment parameters.

```yaml
deploy:
  capital: 1000.0              # Fund sub-account with this amount
  settle_coin: "USDT"          # USDT or USDC (must match symbol category)
  dcp_window: 30               # Disconnect Cancel All timeout (seconds)
```

| Field | Default | Notes |
|-------|---------|-------|
| `capital` | 10000.0 | Amount transferred to sub-account on deploy |
| `settle_coin` | `"USDT"` | Must be `"USDT"` or `"USDC"` |
| `dcp_window` | 30 | DCP auto-cancel timeout for sub-account |

## Timeframe rules

| Rule | Detail |
|------|--------|
| YAML keys | `low_tf`, `med_tf`, `high_tf`, `exec` only. Never `ltf`/`htf`/`LTF`/`HTF`/`MTF` |
| `exec` | Pointer to role (`"low_tf"`, `"med_tf"`, `"high_tf"`), never raw value |
| Hierarchy | `high_tf >= med_tf >= low_tf` (in minutes) |
| Valid intervals | `1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,D,W,M` (no 8h) |
| 1m candles | Always loaded regardless of exec (drives fill sim, TP/SL, subloop) |

## Account defaults (from config/defaults.yml)

| Field | Default |
|-------|---------|
| `starting_equity_usdt` | 10000.0 |
| `max_leverage` | 1.0 |
| `max_drawdown_pct` | 20.0 |
| `margin_mode` | `"isolated_usdt"` |
| `taker_bps` | 5.5 |
| `maker_bps` | 2.0 |
| `slippage_bps` | 2.0 |
| `min_trade_notional_usdt` | 10.0 |
| `maintenance_margin_rate` | 0.005 |

## Position policy

| Field | Values | Default |
|-------|--------|---------|
| `mode` | `long_only`, `short_only`, `long_short` | `long_only` |
| `exit_mode` | `sl_tp_only`, `signal`, `first_hit` | `sl_tp_only` |
| `max_positions_per_symbol` | 1+ | 1 |

**Exit mode behavior:**
- `sl_tp_only` — exits ONLY via SL/TP. Signal exits ignored.
- `signal` — exits via signal. SL/TP as emergency stops.
- `first_hit` — whichever triggers first: signal OR SL/TP.
- TP/SL always fire BEFORE signal-based closes.
- `allow_flip`, `allow_scale_in`, `allow_scale_out` are reserved and not supported. Do not set them.

## Action types

`entry_long`, `entry_short`, `exit_long`, `exit_short`, `exit_all`, `no_action`

## Built-in price features (no declaration needed)

| Feature | Resolution | Notes |
|---------|-----------|-------|
| `open`, `high`, `low`, `close`, `volume` | Per exec bar | Standard OHLCV |
| `last_price` | Every 1m | Actual trade price |
| `mark_price` | Every 1m | Index price |
