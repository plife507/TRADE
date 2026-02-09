# Trade Math Verification: PATTERN

> **INCOMPLETE**: 29/34 plays failed due to DuckDB file locking (Windows).
> 2 FAIL results are equity/SL_TP check failures from stale pre-fix artifacts.
> Needs re-run with regenerated artifacts and sequential execution.
> See `docs/REAL_VERIFICATION_REPORT.md` for authoritative results.

**Progress**: 34/34 plays verified
**Results**: 3 PASS | 2 FAIL | 29 RUN_FAIL

---

## Summary Table

| # | Play | Status | Trades | PnL | Checks |
|---|------|--------|--------|-----|--------|
| 1 | PAT_001_trending | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 2 | PAT_002_ranging | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 3 | PAT_003_volatile | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 4 | PAT_004_multi_tf_aligned | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 5 | PAT_005_trend_up_clean | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 6 | PAT_006_trend_down_clean | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 7 | PAT_007_trend_grinding | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 8 | PAT_008_trend_parabolic | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 9 | PAT_009_trend_exhaustion | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 10 | PAT_010_trend_stairs | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 11 | PAT_011_range_tight | PASS | 20 | -1985.16 | 11P/0F/0W/0S |
| 12 | PAT_012_range_wide | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 13 | PAT_013_range_ascending | FAIL | 11 | -1020.75 | 10P/1F/0W/0S |
| 14 | PAT_014_range_descending | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 15 | PAT_015_reversal_v_bottom | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 16 | PAT_016_reversal_v_top | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 17 | PAT_017_reversal_double_bottom | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 18 | PAT_018_reversal_double_top | PASS | 8 | -2017.35 | 11P/0F/0W/0S |
| 19 | PAT_019_breakout_clean | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 20 | PAT_020_breakout_false | FAIL | 35 | -2083.49 | 10P/1F/0W/0S |
| 21 | PAT_021_breakout_retest | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 22 | PAT_022_vol_squeeze_expand | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 23 | PAT_023_vol_spike_recover | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 24 | PAT_024_vol_spike_continue | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 25 | PAT_025_vol_decay | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 26 | PAT_026_liquidity_hunt_lows | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 27 | PAT_027_liquidity_hunt_highs | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 28 | PAT_028_choppy_whipsaw | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 29 | PAT_029_accumulation | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 30 | PAT_030_distribution | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 31 | PAT_031_mtf_aligned_bull | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 32 | PAT_032_mtf_aligned_bear | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 33 | PAT_033_mtf_pullback_bull | PASS | 3 | 1735.18 | 11P/0F/0W/0S |
| 34 | PAT_034_mtf_pullback_bear | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file 
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |

---

## Detailed Results

### PAT_001_trending
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_002_ranging
- **Status**: RUN_FAIL
- **Pattern**: ranging
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_003_volatile
- **Status**: RUN_FAIL
- **Pattern**: volatile
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_004_multi_tf_aligned
- **Status**: RUN_FAIL
- **Pattern**: multi_tf_aligned
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_005_trend_up_clean
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_006_trend_down_clean
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_007_trend_grinding
- **Status**: RUN_FAIL
- **Pattern**: trend_grinding
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_008_trend_parabolic
- **Status**: RUN_FAIL
- **Pattern**: trend_parabolic
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_009_trend_exhaustion
- **Status**: RUN_FAIL
- **Pattern**: trend_exhaustion
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_010_trend_stairs
- **Status**: RUN_FAIL
- **Pattern**: trend_stairs
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_011_range_tight
- **Status**: PASS
- **Pattern**: range_tight
- **Trades**: 20
- **Net PnL**: -1985.16 USDT
- **Win Rate**: 0.2%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 20 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=1.5%, tp=3.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-1985.16 |
| METRICS | PASS | Summary metrics consistent (20 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### PAT_012_range_wide
- **Status**: RUN_FAIL
- **Pattern**: range_wide
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_013_range_ascending
- **Status**: FAIL
- **Pattern**: range_ascending
- **Trades**: 11
- **Net PnL**: -1020.75 USDT
- **Win Rate**: 0.3%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 11 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | FAIL | PnL sum mismatch: sum(trades)=-1027.1551 vs result.json net_pnl=-1020.7500 [diff=6.4051, tol=5.5] |
| METRICS | PASS | Summary metrics consistent (11 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### PAT_014_range_descending
- **Status**: RUN_FAIL
- **Pattern**: range_descending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_015_reversal_v_bottom
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_016_reversal_v_top
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_top
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_017_reversal_double_bottom
- **Status**: RUN_FAIL
- **Pattern**: reversal_double_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_018_reversal_double_top
- **Status**: PASS
- **Pattern**: reversal_double_top
- **Trades**: 8
- **Net PnL**: -2017.35 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 8 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=2.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2017.35 |
| METRICS | PASS | Summary metrics consistent (8 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### PAT_019_breakout_clean
- **Status**: RUN_FAIL
- **Pattern**: breakout_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_020_breakout_false
- **Status**: FAIL
- **Pattern**: breakout_false
- **Trades**: 35
- **Net PnL**: -2083.49 USDT
- **Win Rate**: 0.2%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 35 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | FAIL | 8 trades with SL/TP level issues:   Trade 17: Short SL=49962.35 <= entry=50231.34 (wrong side)   Trade 18: Short SL=5003 |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=-2083.49 |
| METRICS | PASS | Summary metrics consistent (35 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### PAT_021_breakout_retest
- **Status**: RUN_FAIL
- **Pattern**: breakout_retest
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_022_vol_squeeze_expand
- **Status**: RUN_FAIL
- **Pattern**: vol_squeeze_expand
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_023_vol_spike_recover
- **Status**: RUN_FAIL
- **Pattern**: vol_spike_recover
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_024_vol_spike_continue
- **Status**: RUN_FAIL
- **Pattern**: vol_spike_continue
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_025_vol_decay
- **Status**: RUN_FAIL
- **Pattern**: vol_decay
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_026_liquidity_hunt_lows
- **Status**: RUN_FAIL
- **Pattern**: liquidity_hunt_lows
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_027_liquidity_hunt_highs
- **Status**: RUN_FAIL
- **Pattern**: liquidity_hunt_highs
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_028_choppy_whipsaw
- **Status**: RUN_FAIL
- **Pattern**: choppy_whipsaw
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_029_accumulation
- **Status**: RUN_FAIL
- **Pattern**: accumulation
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_030_distribution
- **Status**: RUN_FAIL
- **Pattern**: distribution
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_031_mtf_aligned_bull
- **Status**: RUN_FAIL
- **Pattern**: mtf_aligned_bull
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_032_mtf_aligned_bear
- **Status**: RUN_FAIL
- **Pattern**: mtf_aligned_bear
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### PAT_033_mtf_pullback_bull
- **Status**: PASS
- **Pattern**: mtf_pullback_bull
- **Trades**: 3
- **Net PnL**: 1735.18 USDT
- **Win Rate**: 1.0%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 3 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=1735.18 |
| METRICS | PASS | Summary metrics consistent (3 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### PAT_034_mtf_pullback_bear
- **Status**: RUN_FAIL
- **Pattern**: mtf_pullback_bear
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

## Failures & Issues

- **PAT_001_trending** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_002_ranging** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_003_volatile** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_004_multi_tf_aligned** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_005_trend_up_clean** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_006_trend_down_clean** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_007_trend_grinding** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_008_trend_parabolic** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_009_trend_exhaustion** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_010_trend_stairs** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_012_range_wide** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_013_range_ascending** [FAIL]: 10P/1F/0W/0S
- **PAT_014_range_descending** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_015_reversal_v_bottom** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_016_reversal_v_top** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_017_reversal_double_bottom** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_019_breakout_clean** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_020_breakout_false** [FAIL]: 10P/1F/0W/0S
- **PAT_021_breakout_retest** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_022_vol_squeeze_expand** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_023_vol_spike_recover** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_024_vol_spike_continue** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_025_vol_decay** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_026_liquidity_hunt_lows** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_027_liquidity_hunt_highs** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_028_choppy_whipsaw** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_029_accumulation** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_030_distribution** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_031_mtf_aligned_bull** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_032_mtf_aligned_bear** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **PAT_034_mtf_pullback_bear** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
