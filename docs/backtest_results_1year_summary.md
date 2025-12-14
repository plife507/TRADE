# IdeaCard Backtest Results - 1 Year Summary

**Date:** 2025-12-14  
**Window:** 2024-12-14 to 2025-12-14 (365 days)  
**Data Environment:** Live  
**All IdeaCards Normalized:** ✅ Yes

## Executive Summary

| Total IdeaCards | Successful Runs | Trades Generated | MTF Enabled |
|----------------|-----------------|------------------|-------------|
| 12 | 8 | 2 strategies | 6 strategies |

### Key Findings

- **MTF Execution:** ✅ Working correctly - all MTF strategies initialized in `multi-TF` mode
- **Trading Activity:** Only 2 strategies generated trades over 1 year
- **Performance:** Both trading strategies showed negative returns (-27.7% and -42.1%)

---

## Detailed Results

### ✅ Successful Runs (8 strategies)

#### 1. BTCUSDT_15m_kc_breakout
- **Mode:** Multi-TF (`htf=1h`)
- **Trades:** 0
- **PnL:** $0.00
- **Status:** ✅ MTF enabled, no trades generated
- **Artifacts:** `backtests/BTCUSDT_15m_kc_breakout/BTCUSDT/run-004`

#### 2. BTCUSDT_1h_adx_ema_trend_follow
- **Mode:** Multi-TF (`htf=4h`)
- **Trades:** 0
- **PnL:** $0.00
- **Status:** ✅ MTF enabled, no trades generated
- **Artifacts:** `backtests/BTCUSDT_1h_adx_ema_trend_follow/BTCUSDT/run-006`

#### 3. BTCUSDT_1h_ema_crossover_mtf ⭐
- **Mode:** Multi-TF (`htf=4h`)
- **Trades:** 39 (8W / 31L)
- **Win Rate:** 20.5%
- **Net PnL:** -$2,769.64 (-27.7%)
- **Max DD:** -$3,294.72 (-32.7%)
- **Sharpe:** -2.08
- **Profit Factor:** 0.49
- **Time in Market:** 8.7% (766/8761 bars)
- **Status:** ✅ MTF enabled, trades generated
- **Artifacts:** `backtests/BTCUSDT_1h_ema_crossover_mtf/BTCUSDT/run-010`
- **Note:** Strategy starved at bar 4760 (equity depleted)

#### 4. BTCUSDT_1h_ema_crossover_simple ⭐
- **Mode:** Single-TF
- **Trades:** 62 (14W / 48L)
- **Win Rate:** 22.6%
- **Net PnL:** -$4,207.55 (-42.1%)
- **Max DD:** -$4,875.80 (-46.7%)
- **Sharpe:** -2.66
- **Profit Factor:** 0.50
- **Time in Market:** 12.6% (1102/8761 bars)
- **Status:** ✅ Single-TF mode, trades generated
- **Artifacts:** `backtests/BTCUSDT_1h_ema_crossover_simple/BTCUSDT/run-007`
- **Note:** Strategy starved at bar 4553 (equity depleted)

#### 5. BTCUSDT_1h_willr_rsi_pullback
- **Mode:** Multi-TF (`htf=4h`)
- **Trades:** 0
- **PnL:** $0.00
- **Status:** ✅ MTF enabled, no trades generated
- **Artifacts:** `backtests/BTCUSDT_1h_willr_rsi_pullback/BTCUSDT/run-007`

#### 6. ETHUSDT_1h_macd_kama_trend
- **Mode:** Single-TF
- **Trades:** 0
- **PnL:** $0.00
- **Status:** ✅ Single-TF mode, no trades generated
- **Artifacts:** `backtests/ETHUSDT_1h_macd_kama_trend/ETHUSDT/run-010`

#### 7. ETHUSDT_1h_stochrsi_cci_pullback
- **Mode:** Multi-TF (`htf=4h`)
- **Trades:** 0
- **PnL:** $0.00
- **Status:** ✅ MTF enabled, no trades generated
- **Artifacts:** `backtests/ETHUSDT_1h_stochrsi_cci_pullback/ETHUSDT/run-003`

#### 8. SOLUSDT_4h_supertrend_rsi_momentum
- **Mode:** Multi-TF (`htf=1d`)
- **Trades:** 0
- **PnL:** $0.00
- **Status:** ✅ MTF enabled, no trades generated
- **Artifacts:** `backtests/SOLUSDT_4h_supertrend_rsi_momentum/SOLUSDT/run-005`

---

### ❌ Failed Runs (1 strategy)

#### 9. SOLUSDT_1h_donchian_breakout
- **Issue:** Insufficient data coverage
- **Error:** Effective window starts at 2024-12-03 14:00 but DB earliest is 2024-12-08 11:00
- **Fix Required:** Sync earlier data or reduce warmup
- **Command:** `python trade_cli.py backtest data-fix --idea-card SOLUSDT_1h_donchian_breakout --env live --start 2024-12-03`

---

### ⚠️ Skipped (2 strategies)

#### 10. BTCUSDT_1h_squeeze_momentum
- **Issue:** Indicator validation failed
- **Error:** Missing required indicator `linreg` (should use expanded keys like `linreg_slope`, `linreg_intercept`, etc.)
- **Status:** Needs YAML fix

#### 11. SOLUSDT_4h_kc_bbands_squeeze
- **Issue:** Indicator validation failed
- **Error:** Feature 'trix' referenced but not declared (should use expanded keys like `trix_trix`, `trix_signal`)
- **Status:** Needs YAML fix

#### 12. ETHUSDT_15m_bbands_atr_breakout
- **Issue:** No data found for ETHUSDT 15m
- **Status:** Needs data sync

---

## MTF Verification

### Multi-Timeframe Status

All MTF strategies correctly initialized in `multi-TF` mode:

| Strategy | MTF Mode | tf_mapping | HTF Data Loaded |
|----------|----------|------------|-----------------|
| BTCUSDT_15m_kc_breakout | ✅ Multi-TF | `{'ltf': '15m', 'mtf': '15m', 'htf': '1h'}` | ✅ Yes |
| BTCUSDT_1h_adx_ema_trend_follow | ✅ Multi-TF | `{'ltf': '1h', 'mtf': '1h', 'htf': '4h'}` | ✅ Yes |
| BTCUSDT_1h_ema_crossover_mtf | ✅ Multi-TF | `{'ltf': '1h', 'mtf': '1h', 'htf': '4h'}` | ✅ Yes |
| BTCUSDT_1h_willr_rsi_pullback | ✅ Multi-TF | `{'ltf': '1h', 'mtf': '1h', 'htf': '4h'}` | ✅ Yes |
| ETHUSDT_1h_stochrsi_cci_pullback | ✅ Multi-TF | `{'ltf': '1h', 'mtf': '1h', 'htf': '4h'}` | ✅ Yes |
| SOLUSDT_4h_supertrend_rsi_momentum | ✅ Multi-TF | `{'ltf': '4h', 'mtf': '4h', 'htf': '1d'}` | ✅ Yes |

**Conclusion:** ✅ MTF infrastructure is working correctly. All HTF/MTF data is being loaded and cached properly.

---

## Performance Analysis

### Trading Strategies Comparison

| Strategy | Mode | Trades | Win Rate | Net PnL | Max DD | Sharpe |
|----------|------|--------|----------|---------|--------|--------|
| BTCUSDT_1h_ema_crossover_mtf | MTF | 39 | 20.5% | -27.7% | -32.7% | -2.08 |
| BTCUSDT_1h_ema_crossover_simple | Single-TF | 62 | 22.6% | -42.1% | -46.7% | -2.66 |

**Key Observations:**
- MTF version generated **fewer trades** (39 vs 62) - HTF filter is working
- MTF version had **better risk-adjusted returns** (Sharpe -2.08 vs -2.66)
- Both strategies showed **negative performance** over 1 year
- Both strategies **depleted equity** before end of period

---

## Issues & Recommendations

### 1. Zero Trade Strategies
Most strategies (6/8 successful runs) generated zero trades. Possible causes:
- Entry conditions too strict
- HTF filters too restrictive
- Market conditions not favorable for strategy logic
- **Recommendation:** Review signal rules and HTF filter thresholds

### 2. Indicator Key Issues
Two strategies failed due to incorrect indicator key references:
- `BTCUSDT_1h_squeeze_momentum`: Uses `linreg` instead of expanded keys
- `SOLUSDT_4h_kc_bbands_squeeze`: Uses `trix` instead of expanded keys
- **Fix:** Update YAML to use expanded indicator keys (e.g., `linreg_slope`, `trix_trix`)

### 3. Data Coverage
- `SOLUSDT_1h_donchian_breakout`: Needs earlier data sync
- `ETHUSDT_15m_bbands_atr_breakout`: No 15m data available
- **Fix:** Run data-fix commands to sync missing timeframes

### 4. Strategy Performance
Both trading strategies showed significant drawdowns and negative returns:
- Consider reviewing risk management parameters
- Evaluate entry/exit logic
- Test with different market conditions

---

## Technical Verification

### MTF Infrastructure ✅
- ✅ `tf_mapping` correctly passed from IdeaCard to BacktestEngine
- ✅ Multi-TF data loading working (`prepare_multi_tf_frames()`)
- ✅ HTF/MTF indicators accessible via `snapshot.features_htf` / `snapshot.features_mtf`
- ✅ `IdeaCardSignalEvaluator._get_feature_value()` correctly routes HTF/MTF requests
- ✅ TimeframeCache updating on TF close (TradingView `lookahead_off` semantics)

### Normalization ✅
- ✅ All IdeaCards normalized successfully
- ✅ `required_indicators` auto-generated correctly
- ✅ Indicator validation working

---

## Next Steps

1. **Fix indicator key issues** in squeeze strategies
2. **Sync missing data** for SOLUSDT and ETHUSDT 15m
3. **Review zero-trade strategies** - adjust entry conditions or HTF filters
4. **Analyze trading strategies** - investigate poor performance, consider parameter tuning
5. **Expand test coverage** - run on different time periods and market conditions

---

## Artifacts Location

All backtest artifacts saved to: `backtests/{idea_card_id}/{symbol}/run-{NNN}/`

Key files per run:
- `result.json` - Summary metrics
- `trades.csv` - Trade log
- `equity.csv` - Equity curve
- `preflight_report.json` - Data coverage diagnostics

