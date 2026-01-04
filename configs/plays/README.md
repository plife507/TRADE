# Play Folder Structure

> **Canonical location for Play YAML files used in backtesting.**

## Folder Tree

```
configs/
└── plays/                    # ← Canonical Plays (for backtesting)
    ├── _TEMPLATE.yml              # Copy this to create new Plays
    ├── README.md                  # This file
    ├── SOLUSDT_5m_ema_crossover.yml
    └── ...

backtests/                         # ← Backtest artifacts (auto-generated)
└── {play_id}/
    └── {symbol}/
        └── run-{NNN}/
            ├── trades.csv
            ├── equity.csv
            ├── result.json
            ├── preflight_report.json
            └── pipeline_signature.json

research/                          # ← Research strategies (future)
└── strategies/
    ├── pending/                   # Ideas being tested
    ├── final/                     # Validated strategies
    └── archived/                  # Retired strategies
```

## Naming Convention

**Format:** `{SYMBOL}_{TF}_{strategy_name}.yml`

| Component | Description | Examples |
|-----------|-------------|----------|
| SYMBOL | Trading pair (USDT suffix) | `SOLUSDT`, `BTCUSDT`, `ETHUSDT` |
| TF | Execution timeframe | `1m`, `5m`, `15m`, `1h`, `4h`, `1d` |
| strategy_name | Descriptive name (snake_case) | `ema_crossover`, `rsi_reversal` |

**Examples:**
- `SOLUSDT_5m_ema_crossover.yml`
- `BTCUSDT_15m_macd_trend.yml`
- `ETHUSDT_1h_bbands_breakout.yml`

## Play Lifecycle

```
1. DRAFT → Create from _TEMPLATE.yml
              └── Validate: backtest indicators --print-keys
              
2. TEST  → Run preflight: backtest preflight --idea YOUR_ID
              └── Run backtest: backtest run --idea YOUR_ID

3. ITERATE → Modify parameters, re-run backtests
              └── Version bump: 1.0.0 → 1.1.0

4. FINAL → Move validated Play to research/strategies/final/
              └── (Future: automated promotion)
```

## File Structure (Required Sections)

```yaml
# Identity
id: {must_match_filename}
version: "1.0.0"
name: "Display Name"
description: "Description"

# Account (REQUIRED - no defaults)
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  margin_mode: "isolated_usdt"
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0
  slippage_bps: 2.0

# Symbol (first used for single-symbol backtest)
symbol_universe:
  - SOLUSDT

# Timeframes Header (REQUIRED)
# Groups: ltf=1m,3m,5m | mtf=15m,30m | htf=1h,4h,1d | exec=any
timeframes:
  exec: "5m"     # Required
  ltf: "5m"      # Optional (1m, 3m, 5m)
  mtf: "15m"     # Optional (15m, 30m)
  htf: "4h"      # Optional (1h, 4h, 1d)

# Timeframe Configs (tf derived from timeframes header)
tf_configs:
  exec: { role, warmup_bars, feature_specs, required_indicators }
  htf:  { ... }  # Optional
  mtf:  { ... }  # Optional
  ltf:  { ... }  # Optional

# Position Policy
position_policy:
  mode: "long_only"  # long_only, short_only, long_short

# Signal Rules
signal_rules:
  entry_rules: [...]
  exit_rules: [...]

# Risk Model
risk_model:
  stop_loss: { type, value }
  take_profit: { type, value }
  sizing: { model, value, max_leverage }
```

## Validation Workflow

```bash
# 1. Check indicator keys are correct
python trade_cli.py backtest indicators --idea YOUR_ID --print-keys

# 2. Validate data coverage
python trade_cli.py backtest preflight --idea YOUR_ID

# 3. Run backtest
python trade_cli.py backtest run --idea YOUR_ID --start 2025-01-01 --end 2025-02-01 --env live
```

## Quick Reference

| What | How |
|------|-----|
| Create new Play | Copy `_TEMPLATE.yml` |
| Validate indicator keys | `backtest indicators --print-keys` |
| Check data coverage | `backtest preflight` |
| Run backtest | `backtest run --start ... --end ...` |
| View artifacts | `backtests/{play_id}/{symbol}/run-NNN/` |

## Common Issues

| Issue | Solution |
|-------|----------|
| "No data found" | Run data sync first via CLI Data Builder |
| "Indicator key not found" | Check `required_indicators` matches `feature_specs` keys |
| "Warmup insufficient" | Increase `warmup_bars` for that TF |
| Zero trades | Check signal conditions and HTF/MTF filters |

---

**See Also:**
- `docs/reviews/PLAY_SYNTAX.md` - Detailed structure docs
- `docs/guides/WRITING_STRATEGIES.md` - Strategy development guide

