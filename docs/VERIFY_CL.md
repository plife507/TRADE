# Trade Math Verification: CL

> **INCOMPLETE**: 9/13 plays failed due to DuckDB file locking (Windows).
> 4/4 that ran all PASS with 11/11 checks. Needs re-run with sequential execution.
> See `docs/REAL_VERIFICATION_REPORT.md` for authoritative math verification results.

**Progress**: 13/13 plays verified
**Results**: 4 PASS | 0 FAIL | 9 RUN_FAIL

---

## Summary Table

| # | Play | Status | Trades | PnL | Checks |
|---|------|--------|--------|-----|--------|
| 1 | CL_001 | PASS | 12 | 147.35 | 11P/0F/0W/0S |
| 2 | CL_002 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 3 | CL_003 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 4 | CL_004 | PASS | 310 | -1002.90 | 11P/0F/0W/0S |
| 5 | CL_005 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 6 | CL_006 | PASS | 718 | 94.69 | 11P/0F/0W/0S |
| 7 | CL_007 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 8 | CL_008 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 9 | CL_009 | PASS | 19 | -1028.18 | 11P/0F/0W/0S |
| 10 | CL_010 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 11 | CL_011 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 12 | CL_012 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |
| 13 | CL_013 | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |

---

## Detailed Results

### CL_001
- **Status**: PASS
- **Pattern**: trending
- **Trades**: 12
- **Net PnL**: 147.35 USDT
- **Win Rate**: 0.3%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 12 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=6.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=147.35 |
| METRICS | PASS | Summary metrics consistent (12 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### CL_002
- **Status**: RUN_FAIL
- **Pattern**: reversal_v_bottom
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_003
- **Status**: RUN_FAIL
- **Pattern**: ranging
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_004
- **Status**: PASS
- **Pattern**: ranging
- **Trades**: 310
- **Net PnL**: -1002.90 USDT
- **Win Rate**: 0.1%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 310 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.0%, tp=5.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=5000, net_pnl=-1002.90 |
| METRICS | PASS | Summary metrics consistent (310 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### CL_005
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_006
- **Status**: PASS
- **Pattern**: trending
- **Trades**: 718
- **Net PnL**: 94.69 USDT
- **Win Rate**: 0.5%

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 718 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=2.0%, tp=4.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=10000, net_pnl=94.69 |
| METRICS | PASS | Summary metrics consistent (718 trades, 1% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### CL_007
- **Status**: RUN_FAIL
- **Pattern**: trend_down_clean
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_008
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_009
- **Status**: PASS
- **Pattern**: trending
- **Trades**: 19
- **Net PnL**: -1028.18 USDT

| Check | Status | Detail |
|-------|--------|--------|
| LOAD | PASS | All artifacts loaded successfully |
| TRADE_COUNT | PASS | Consistent: 19 trades |
| PNL_DIRECTION | PASS | All trades have correct PnL direction |
| NET_PNL | PASS | All trades: net_pnl = realized_pnl - fees_paid |
| FEES | PASS | All trade fees within expected range (taker=5.5bps) |
| SL_TP | PASS | All SL/TP distances match config (sl=3.5%, tp=7.0%) |
| EXIT_REASON | PASS | All exit reasons consistent with exit prices |
| EQUITY | PASS | Equity consistent: initial=5000, net_pnl=-1028.18 |
| METRICS | PASS | Summary metrics consistent (19 trades, 0% WR) |
| OVERLAP | PASS | No overlapping trades (max_positions=1) |
| BYBIT_PNL | PASS | All trades match Bybit USDT perp formulas (taker=5.5bps) |

### CL_010
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_011
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_012
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

### CL_013
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

## Failures & Issues

- **CL_002** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_003** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_005** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_007** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_008** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_010** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_011** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_012** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
- **CL_013** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
