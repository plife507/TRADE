# Trade Math Verification: STRUCTURE

> **INCOMPLETE**: 11/14 plays failed due to DuckDB file locking (Windows).
> 3 FAIL results are equity check failures (~$7 diff) from pre-fix artifacts
> (equity curve post-close bug was fixed after these ran). Needs re-run.
> See `docs/REAL_VERIFICATION_REPORT.md` for authoritative results.

**Progress**: 14/14 plays verified
**Results**: 0 PASS | 3 FAIL | 11 RUN_FAIL

---

## Summary Table

| # | Play | Status | Trades | PnL | Checks |
|---|------|--------|--------|-----|--------|
| 1 | STR_001_swing_basic | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 2 | STR_002_trend_direction | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 3 | STR_003_ms_bos | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 4 | STR_004_ms_choch | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 5 | STR_005_fibonacci | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 6 | STR_006_derived_zone | FAIL | 10 | 541.70 | 10P/1F/0W/0S |
| 7 | STR_007_zone_demand | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 8 | STR_008_zone_supply | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 9 | STR_009_rolling_min | FAIL | 11 | 279.33 | 10P/1F/0W/0S |
| 10 | STR_010_rolling_max | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 11 | STR_011_full_chain | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 12 | STR_012_multi_tf | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 13 | STR_013_all_types | FAIL | 10 | 609.41 | 10P/1F/0W/0S |
| 14 | STR_014_trend_short | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |

---

## Detailed Results

### STR_001_swing_basic
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_002_trend_direction
- **Status**: RUN_FAIL
- **Pattern**: trend_up_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_003_ms_bos
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_004_ms_choch
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_005_fibonacci
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_006_derived_zone
- **Status**: FAIL
- **Pattern**: trending
- **Trades**: 10
- **Net PnL**: 541.70 USDT
- **Win Rate**: 0.4%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 10 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | FAIL | PnL sum mismatch: sum(trades)=534.1907 vs result.json net_pnl=541.7000 [diff=7.5093, tol=5.0] |
| METRICS | PASS | Summary metrics consistent (10 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### STR_007_zone_demand
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_008_zone_supply
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_top
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_009_rolling_min
- **Status**: FAIL
- **Pattern**: trending
- **Trades**: 11
- **Net PnL**: 279.33 USDT
- **Win Rate**: 0.4%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 11 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | FAIL | PnL sum mismatch: sum(trades)=272.0002 vs result.json net_pnl=279.3300 [diff=7.3298, tol=5.5] |
| METRICS | PASS | Summary metrics consistent (11 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### STR_010_rolling_max
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_011_full_chain
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_012_multi_tf
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### STR_013_all_types
- **Status**: FAIL
- **Pattern**: trending
- **Trades**: 10
- **Net PnL**: 609.41 USDT
- **Win Rate**: 0.4%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 10 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | FAIL | PnL sum mismatch: sum(trades)=601.8507 vs result.json net_pnl=609.4100 [diff=7.5593, tol=5.0] |
| METRICS | PASS | Summary metrics consistent (10 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### STR_014_trend_short
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

## Failures & Issues

- **STR_001_swing_basic** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_002_trend_direction** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_003_ms_bos** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_004_ms_choch** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_005_fibonacci** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_006_derived_zone** [FAIL]: 10P/1F/0W/0S
- **STR_007_zone_demand** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_008_zone_supply** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_009_rolling_min** [FAIL]: 10P/1F/0W/0S
- **STR_010_rolling_max** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_011_full_chain** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_012_multi_tf** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **STR_013_all_types** [FAIL]: 10P/1F/0W/0S
- **STR_014_trend_short** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
