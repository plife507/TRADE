# Session Handoff - 2026-01-06

## Summary

Focused session on strategy backtesting mechanics. Added ExitMode enum, verified Bybit math parity, created test plays for SOL/ETH backtesting.

---

## What Was Accomplished

### 1. ExitMode Enum (Strategy Exit Type Declaration)

**Problem Identified**: Strategies had no explicit declaration of how positions exit (SL/TP only vs signal-based exits). This led to ambiguity.

**Solution**: Added `ExitMode` enum to `src/backtest/play.py`:

```python
class ExitMode(str, Enum):
    SL_TP_ONLY = "sl_tp_only"   # Exit ONLY via stop loss or take profit
    SIGNAL = "signal"           # Exit via exit_long/exit_short signals
    FIRST_HIT = "first_hit"     # Hybrid - whichever triggers first
```

**Files Modified**:
- `src/backtest/play.py` - Added ExitMode enum and exit_mode field to PositionPolicy
- `src/backtest/execution_validation.py` - Added validation rules for exit_mode
- All 34 validation plays - Added explicit `exit_mode` field

### 2. Bybit Math Verification

Verified all 17 core formulas in the simulator match Bybit documentation:
- PnL calculation (long/short)
- Initial margin (IM = size / leverage)
- Maintenance margin (MM = size × MMR)
- Trading fees (taker/maker bps)
- Funding rate settlement
- Liquidation price
- Position sizing

**Result**: All math verified correct. Slippage (5 bps) explains minor discrepancies.

### 3. Test Plays Created

| Play ID | Strategy | Period | Result |
|---------|----------|--------|--------|
| TF_001_eth_trend | ETH EMA crossover long/short | - | Created |
| TF_002_sol_long_only | SOL long-only, EMA 50 filter, 9/21 cross | Jan-Mar 2025 | -31% (bad market) |
| TF_003_sol_short_only | SOL short-only, EMA 200 filter, 13/21 cross | Jan-Mar 2025 | +19% (2% risk) |

**Key Finding**: EMA 200 trend filter significantly outperformed EMA 50 for the SOL short strategy. Win rate improved from 0% (6 trades) to 33.8% (74 trades).

### 4. Leverage/Risk Testing

Tested various leverage/risk combinations on TF_003:

| Risk % | Leverage | Trades | Net PnL | Notes |
|--------|----------|--------|---------|-------|
| 2% | 3x | 74 | +$1,899 | Best risk-adjusted |
| 5% | 5x | 47 | -$4,933 | Too aggressive |
| 10% | 5x | 3 | -$2,934 | High rejection rate |
| 90%+ | 5x | 0 | $0 | 100% rejection |

**Lesson**: Higher leverage/risk doesn't scale linearly - position rejection and drawdown compound.

---

## Git Status

```
Commit: 5f3e401
Branch: main
Message: feat: add ExitMode enum and test plays for strategy backtesting
Files: 63 changed, 2808 insertions(+), 229 deletions(-)
```

New files:
- `strategies/plays/_validation/TF_001_eth_trend.yml`
- `strategies/plays/_validation/TF_002_sol_long_only.yml`
- `strategies/plays/_validation/TF_003_sol_short_only.yml`
- `strategies/plays/_validation/T_001_single_15m.yml`
- `strategies/plays/_validation/M_002_mtf_4h.yml`
- `strategies/plays/_validation/M_003_triple_tf.yml`

---

## Current Play Configuration (TF_003)

```yaml
id: TF_003_sol_short_only
version: "3.0.0"
name: "Short Only: SOL EMA Trend + Crossover"

position_policy:
  mode: "short_only"
  exit_mode: "sl_tp_only"  # NEW FIELD

features:
  - id: "ema_13"      # Fast EMA for crossover
  - id: "ema_21"      # Slow EMA for crossover
  - id: "ema_200"     # Trend filter
  - id: "atr_14"      # For stop calculation

actions:
  - id: entry
    cases:
      - when:
          all:
            - close < ema_200     # Downtrend filter
            - ema_13 cross_below ema_21  # Crossover entry
        emit:
          - action: entry_short

risk_model:
  stop_loss:
    type: "atr_multiple"
    value: 1.5
  take_profit:
    type: "rr_ratio"
    value: 3.0
  sizing:
    model: "percent_equity"
    value: 5.0            # 5% risk per trade
    max_leverage: 5.0
```

---

## Backtest Artifacts Location

```
backtests/_validation/TF_003_sol_short_only/SOLUSDT/b557a42b8be5/
├── result.json          # Summary metrics
├── run_manifest.json    # Run metadata + hashes
├── trades.parquet       # 74 trades with full details
├── equity.parquet       # 8,545 equity points
├── pipeline_signature.json
└── logs/
```

---

## Next Priorities

### P1: Strategy Iteration
- Test more EMA combinations
- Try RSI/momentum filters
- Multi-timeframe confirmation

### P2: Visualization of Backtests
- View trade markers on candlestick charts
- Equity curve analysis
- Drawdown visualization

### P3: ICT Market Structure
- Continue implementation per `ICT_MARKET_STRUCTURE.md`

---

## Key Commands

```bash
# Run backtest via CLI
python trade_cli.py backtest run --play TF_003_sol_short_only \
  --dir strategies/plays/_validation --start 2025-01-01 --end 2025-03-31

# View play
cat strategies/plays/_validation/TF_003_sol_short_only.yml

# Sync historical data
python -c "
from src.data.historical_data_store import HistoricalDataStore
store = HistoricalDataStore()
store.sync_range(['SOLUSDT'], datetime(2024,12,1), datetime(2025,4,1), ['15m'])
"
```

---

## Open Questions

1. **Sizing Model**: `percent_equity` calculates size from risk/stop distance. For max leverage deployment, may need different approach.

2. **Entry Rejections**: High risk % causes margin exhaustion → 100% rejection rate. Need better feedback in UI.

3. **Market Regime**: Long-only failed badly in Jan-Mar 2025 bearish SOL market. Regime detection would help.

---

## Session Stats

- Duration: ~2 hours
- Commits: 1
- Files changed: 63
- Lines: +2,808 / -229
- Backtests run: 8+
- Key feature: ExitMode enum
