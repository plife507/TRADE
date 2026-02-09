# Trade Math Verification: INDICATOR

> **INCOMPLETE**: 26/35 plays failed due to DuckDB file locking (Windows).
> 8 FAIL results are SL_TP check failures from stale pre-fix artifacts (equity
> curve post-close bug was fixed after these ran). Needs re-run with regenerated
> artifacts. See `docs/REAL_VERIFICATION_REPORT.md` for authoritative results.

**Progress**: 35/84 plays verified
**Results**: 1 PASS | 8 FAIL | 26 RUN_FAIL

---

## Summary Table

| # | Play | Status | Trades | PnL | Checks |
|---|------|--------|--------|-----|--------|
| 1 | IND_001_ema_trend_long | FAIL | 18680 | 2044234198620537344.00 | 10P/1F/0W/0S |
| 2 | IND_002_ema_trend_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 3 | IND_003_sma_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 4 | IND_004_sma_trend_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 5 | IND_005_wma_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 6 | IND_006_dema_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 7 | IND_007_tema_trend_long | FAIL | 21 | -2058.84 | 10P/1F/0W/0S |
| 8 | IND_008_trima_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 9 | IND_009_zlma_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 10 | IND_010_kama_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 11 | IND_011_alma_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 12 | IND_012_linreg_trend_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 13 | IND_013_rsi_oversold_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 14 | IND_014_rsi_overbought_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 15 | IND_015_cci_oversold_long | FAIL | 97 | 1048.02 | 10P/1F/0W/0S |
| 16 | IND_016_cci_overbought_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 17 | IND_017_willr_oversold_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 18 | IND_018_willr_overbought_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 19 | IND_019_cmo_oversold_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 20 | IND_020_mfi_oversold_long | PASS | 21 | -2016.23 | 11P/0F/0W/0S |
| 21 | IND_021_mfi_overbought_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 22 | IND_022_uo_oversold_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 23 | IND_023_roc_positive_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 24 | IND_024_roc_negative_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 25 | IND_025_mom_positive_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 26 | IND_026_mom_negative_short | FAIL | 95 | 1425.69 | 10P/1F/0W/0S |
| 27 | IND_027_obv_rising_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 28 | IND_028_cmf_positive_long | FAIL | 862 | 25221331585798.10 | 10P/1F/0W/0S |
| 29 | IND_029_cmf_negative_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 30 | IND_030_vwap_above_long | FAIL | 17755 | 1912795327568323840.00 | 9P/2F/0W/0S |
| 31 | IND_031_atr_filter_long | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 32 | IND_032_natr_filter_long | FAIL | 2 | -3817.82 | 10P/1F/0W/0S |
| 33 | IND_033_ohlc4_above_ema | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 34 | IND_034_midprice_above_ema | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 35 | IND_035_volume_sma_above | FAIL | 26 | -890.15 | 10P/1F/0W/0S |

---

## Detailed Results

### IND_001_ema_trend_long
- **Status**: FAIL
- **Pattern**: trend_up_clean
- **Trades**: 18680
- **Net PnL**: 2044234198620537344.00 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 18680 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 18350 trades with SL/TP level issues:   Trade 1: Long SL=49902.42 >= entry=49249.50 (wrong side)   Trade 2: Long SL=4992 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=2044234198620537344.00 |
| METRICS | PASS | Summary metrics consistent (18680 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_002_ema_trend_short
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_003_sma_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_004_sma_trend_short
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_005_wma_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_006_dema_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_stairs
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_007_tema_trend_long
- **Status**: FAIL
- **Pattern**: trend_grinding
- **Trades**: 21
- **Net PnL**: -2058.84 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 21 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 14 trades with SL/TP level issues:   Trade 3: Long TP=50188.82 <= entry=50230.93 (wrong side)   Trade 4: Long TP=50163.3 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2058.84 |
| METRICS | PASS | Summary metrics consistent (21 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_008_trima_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_009_zlma_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_010_kama_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_stairs
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_011_alma_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_grinding
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_012_linreg_trend_long
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_013_rsi_oversold_long
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_014_rsi_overbought_short
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_top
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_015_cci_oversold_long
- **Status**: FAIL
- **Pattern**: reversal_v_bottom
- **Trades**: 97
- **Net PnL**: 1048.02 USDT
- **Win Rate**: 0.6%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 97 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 36 trades with SL/TP level issues:   Trade 53: Long TP=51516.38 <= entry=51663.98 (wrong side)   Trade 55: Long TP=51471 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1048.02 |
| METRICS | PASS | Summary metrics consistent (97 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_016_cci_overbought_short
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_top
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_017_willr_oversold_long
- **Status**: RUN_FAIL
- **Pattern**: range_wide
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_018_willr_overbought_short
- **Status**: RUN_FAIL
- **Pattern**: range_wide
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_019_cmo_oversold_long
- **Status**: RUN_FAIL
- **Pattern**: reversal_double_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_020_mfi_oversold_long
- **Status**: PASS
- **Pattern**: accumulation
- **Trades**: 21
- **Net PnL**: -2016.23 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 21 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2016.23 |
| METRICS | PASS | Summary metrics consistent (21 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_021_mfi_overbought_short
- **Status**: RUN_FAIL
- **Pattern**: distribution
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_022_uo_oversold_long
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_023_roc_positive_long
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_024_roc_negative_short
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_025_mom_positive_long
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_026_mom_negative_short
- **Status**: FAIL
- **Pattern**: trend_down_clean
- **Trades**: 95
- **Net PnL**: 1425.69 USDT
- **Win Rate**: 0.7%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 95 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 29 trades with SL/TP level issues:   Trade 64: Short TP=47570.00 >= entry=47378.68 (wrong side)   Trade 65: Short TP=476 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1425.69 |
| METRICS | PASS | Summary metrics consistent (95 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_027_obv_rising_long
- **Status**: RUN_FAIL
- **Pattern**: accumulation
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_028_cmf_positive_long
- **Status**: FAIL
- **Pattern**: accumulation
- **Trades**: 862
- **Net PnL**: 25221331585798.10 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 862 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 829 trades with SL/TP level issues:   Trade 1: Long SL=49644.71 >= entry=49159.89 (wrong side)   Trade 2: Long SL=49652. |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=25221331585798.10 |
| METRICS | PASS | Summary metrics consistent (862 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_029_cmf_negative_short
- **Status**: RUN_FAIL
- **Pattern**: distribution
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_030_vwap_above_long
- **Status**: FAIL
- **Pattern**: trend_up_clean
- **Trades**: 17755
- **Net PnL**: 1912795327568323840.00 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 17755 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 17153 trades with SL/TP level issues:   Trade 1: Long SL=49391.46 >= entry=49249.50 (wrong side)   Trade 2: Long SL=4936 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | FAIL | PnL sum mismatch: sum(trades)=1912795327568333312.0000 vs result.json net_pnl=1912795327568323840.0000 [diff=9472.0000,  |
| METRICS | PASS | Summary metrics consistent (17755 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_031_atr_filter_long
- **Status**: RUN_FAIL
- **Pattern**: vol_squeeze_expand
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_032_natr_filter_long
- **Status**: FAIL
- **Pattern**: vol_squeeze_expand
- **Trades**: 2
- **Net PnL**: -3817.82 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 2 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 2 trades with SL/TP level issues:   Trade 0: Long TP=52455.14 <= entry=65869.33 (wrong side)   Trade 1: Long TP=52407.55 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-3817.82 |
| METRICS | PASS | Summary metrics consistent (2 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### IND_033_ohlc4_above_ema
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_034_midprice_above_ema
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### IND_035_volume_sma_above
- **Status**: FAIL
- **Pattern**: breakout_clean
- **Trades**: 26
- **Net PnL**: -890.15 USDT
- **Win Rate**: 0.3%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 26 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 13 trades with SL/TP level issues:   Trade 13: Long TP=55472.78 <= entry=56137.42 (wrong side)   Trade 14: Long TP=55460 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-890.15 |
| METRICS | PASS | Summary metrics consistent (26 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

## Failures & Issues

- **IND_001_ema_trend_long** [FAIL]: 10P/1F/0W/0S
- **IND_002_ema_trend_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_003_sma_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_004_sma_trend_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_005_wma_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_006_dema_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_007_tema_trend_long** [FAIL]: 10P/1F/0W/0S
- **IND_008_trima_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_009_zlma_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_010_kama_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_011_alma_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_012_linreg_trend_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_013_rsi_oversold_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_014_rsi_overbought_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_015_cci_oversold_long** [FAIL]: 10P/1F/0W/0S
- **IND_016_cci_overbought_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_017_willr_oversold_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_018_willr_overbought_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_019_cmo_oversold_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_021_mfi_overbought_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_022_uo_oversold_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_023_roc_positive_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_024_roc_negative_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_025_mom_positive_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_026_mom_negative_short** [FAIL]: 10P/1F/0W/0S
- **IND_027_obv_rising_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_028_cmf_positive_long** [FAIL]: 10P/1F/0W/0S
- **IND_029_cmf_negative_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_030_vwap_above_long** [FAIL]: 9P/2F/0W/0S
- **IND_031_atr_filter_long** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_032_natr_filter_long** [FAIL]: 10P/1F/0W/0S
- **IND_033_ohlc4_above_ema** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_034_midprice_above_ema** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **IND_035_volume_sma_above** [FAIL]: 10P/1F/0W/0S
