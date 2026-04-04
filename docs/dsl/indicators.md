# Indicators

47 total. All incremental O(1) per bar.

## Feature declaration

```yaml
features:
  ema_9:                           # Name encodes params (REQUIRED convention)
    indicator: ema
    params: { length: 9 }
    tf: "1h"                       # Optional: concrete TF or role. Default = exec TF
    source: close                  # Optional: close|open|high|low|volume|hl2|hlc3|ohlc4
```

**Naming rule:** encode params in name. `ema_9` not `ema_fast`. Cross-TF: `ema_50_1h`.

**TF behavior:**
- Not specified → inherits exec TF
- Slower than exec → forward-fills last closed value (no lookahead)
- `tf:` accepts concrete (`"1h"`) or role (`"med_tf"`)

## Single-output (25)

| Indicator | Params | Notes |
|-----------|--------|-------|
| `ema` | `length` | Warmup = 3x length |
| `sma` | `length` | Warmup = length |
| `wma` | `length` | |
| `dema` | `length` | Double EMA |
| `tema` | `length` | Triple EMA |
| `trima` | `length` | Triangular MA |
| `zlma` | `length` | Zero-lag MA |
| `kama` | `length` | Kaufman adaptive |
| `alma` | `length`, `sigma`, `offset` | Arnaud Legoux |
| `rsi` | `length` | Range [0,100] |
| `atr` | `length` | Average true range |
| `natr` | `length` | Normalized ATR (%) |
| `cci` | `length` | Commodity channel |
| `willr` | `length` | Range [-100,0] |
| `roc` | `length` | Rate of change |
| `mom` | `length` | Momentum |
| `mfi` | `length` | Money flow, range [0,100] |
| `obv` | (none) | On-balance volume |
| `cmf` | `length` | Chaikin money flow |
| `cmo` | `length` | Chande momentum |
| `linreg` | `length` | Linear regression |
| `midprice` | `length` | (high+low)/2 over period |
| `ohlc4` | (none) | (O+H+L+C)/4 |
| `uo` | `fast`, `medium`, `slow` | Ultimate oscillator |
| `vwap` | `anchor` | Session VWAP (anchor reset: `"D"`, `"W"`, `"M"`) |

## Multi-output (22)

Access fields: `"macd_12_26_9.histogram"` (dotted) or `{feature_id: "macd_12_26_9", field: "histogram"}`

| Indicator | Outputs | Params |
|-----------|---------|--------|
| `macd` | `macd`, `signal`, `histogram` | `fast`, `slow`, `signal` |
| `bbands` | `lower`, `middle`, `upper`, `bandwidth`, `percent_b` | `length`, `std` |
| `stoch` | `k`, `d` | `k`, `d`, `smooth_k` |
| `stochrsi` | `k`, `d` | `length`, `rsi_length`, `k`, `d` |
| `adx` | `adx`, `dmp`, `dmn`, `adxr` | `length` |
| `aroon` | `up`, `down`, `osc` | `length` |
| `kc` | `lower`, `basis`, `upper` | `length`, `scalar` |
| `donchian` | `lower`, `middle`, `upper` | `lower_length`, `upper_length` |
| `supertrend` | `trend`, `direction`, `long`, `short` | `length`, `multiplier` |
| `psar` | `long`, `short`, `af`, `reversal` | `af0`, `af`, `max_af` |
| `squeeze` | `sqz`, `on`, `off`, `no_sqz` | `bb_length`, `bb_std`, `kc_length`, `kc_scalar` |
| `vortex` | `vip`, `vim` | `length` |
| `dm` | `dmp`, `dmn` | `length` |
| `fisher` | `fisher`, `signal` | `length` |
| `tsi` | `tsi`, `signal` | `fast`, `slow`, `signal` |
| `kvo` | `kvo`, `signal` | `fast`, `slow`, `signal` |
| `ppo` | `ppo`, `histogram`, `signal` | `fast`, `slow`, `signal` |
| `trix` | `trix`, `signal` | `length`, `signal` |
| `anchored_vwap` | `value`, `bars_since_anchor` | `anchor_source` |

## Advanced multi-output (3)

| Indicator | Outputs | Params |
|-----------|---------|--------|
| `volume_profile` | `poc`, `vah`, `val`, `poc_volume`, `above_poc`, `in_value_area` | `num_buckets`, `lookback`, `value_area_pct` |
| `anchored_volume_profile` | same as volume_profile | same params |
| `session_levels` | `prev_day_high`, `prev_day_low`, `current_day_high`, `current_day_low`, `prev_week_high`, `prev_week_low` | (none) |
