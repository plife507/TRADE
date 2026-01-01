# IdeaCard Backtest Results - 1 Year Summary

**Date:** 2025-12-14  
**Window:** 2024-12-14 to 2025-12-14 (365 days)  
**Data Environment:** Live  
**All IdeaCards Normalized:** ✅ Yes
**Moved from:** `docs/backtest_results_1year_summary.md` (2025-12-17 docs refactor)

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

| Strategy | Mode | Trades | PnL | Status |
|----------|------|--------|-----|--------|
| BTCUSDT_15m_kc_breakout | Multi-TF | 0 | $0 | MTF enabled |
| BTCUSDT_1h_adx_ema_trend_follow | Multi-TF | 0 | $0 | MTF enabled |
| BTCUSDT_1h_ema_crossover_mtf | Multi-TF | 39 | -$2,769 | Trades generated |
| BTCUSDT_1h_ema_crossover_simple | Single-TF | 62 | -$4,208 | Trades generated |
| BTCUSDT_1h_willr_rsi_pullback | Multi-TF | 0 | $0 | MTF enabled |
| ETHUSDT_1h_macd_kama_trend | Single-TF | 0 | $0 | No trades |
| ETHUSDT_1h_stochrsi_cci_pullback | Multi-TF | 0 | $0 | MTF enabled |
| SOLUSDT_4h_supertrend_rsi_momentum | Multi-TF | 0 | $0 | MTF enabled |

### ❌ Failed Runs (1 strategy)

- **SOLUSDT_1h_donchian_breakout** — Insufficient data coverage

### ⚠️ Skipped (3 strategies)

- **BTCUSDT_1h_squeeze_momentum** — Indicator validation failed
- **SOLUSDT_4h_kc_bbands_squeeze** — Indicator validation failed
- **ETHUSDT_15m_bbands_atr_breakout** — No data found

---

## Performance Analysis

| Strategy | Mode | Trades | Win Rate | Net PnL | Max DD | Sharpe |
|----------|------|--------|----------|---------|--------|--------|
| BTCUSDT_1h_ema_crossover_mtf | MTF | 39 | 20.5% | -27.7% | -32.7% | -2.08 |
| BTCUSDT_1h_ema_crossover_simple | Single-TF | 62 | 22.6% | -42.1% | -46.7% | -2.66 |

**Key Observations:**
- MTF version generated fewer trades (39 vs 62) - HTF filter is working
- MTF version had better risk-adjusted returns (Sharpe -2.08 vs -2.66)
- Both strategies showed negative performance over 1 year

---

## Related Documentation

- **Validation Index:** `docs/validation/README.md`
- **Long Horizon Test:** `docs/validation/long_horizon_test_results.md`
- **Low TF Stress Test:** `docs/validation/low_tf_stress_test_results.md`

