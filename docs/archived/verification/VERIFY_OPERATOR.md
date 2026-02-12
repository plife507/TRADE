# Trade Math Verification: OPERATOR

> **INCOMPLETE**: Only 1/25 attempted, failed due to DuckDB file locking.
> Needs re-run with sequential execution. See `docs/REAL_VERIFICATION_REPORT.md`
> for authoritative math verification results.

**Progress**: 1/25 plays verified
**Results**: 0 PASS | 0 FAIL | 1 RUN_FAIL

---

## Summary Table

| # | Play | Status | Trades | PnL | Checks |
|---|------|--------|--------|-----|--------|
| 1 | OP_001_gt | RUN_FAIL | 0 | 0.00 | [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot open file
Traceback (most recent call last):
_duckdb.IOException: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process. |

---

## Detailed Results

### OP_001_gt
- **Status**: RUN_FAIL
- **Pattern**: trending
- **Trades**: 0
- **Error**: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope

## Failures & Issues

- **OP_001_gt** [RUN_FAIL]: [ERROR] Error: IO Error: Cannot open file "c:\code\ai\trade\data\market_data_backtest.duckdb": The process cannot access the file because it is being used by another process.
FAIL IO Error: Cannot ope
