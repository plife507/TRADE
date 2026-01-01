## DuckDB Funding / Open Interest / Volume Pipeline Review — TODOs

**Status**: ✅ Complete  
**Date**: 2025-12-17  
**Scope**: Documentation-only (end-to-end review + integration notes)

### Phase 1 — End-to-End Audit Writeup

- [x] Document DuckDB tables + schemas for OHLCV / funding / open interest
- [x] Trace backtest prep vs runtime consumption (what’s used vs dropped)
- [x] Confirm funding cashflow modeling status (supported vs wired)
- [x] Summarize gaps/risks for long-horizon perp backtests

### Phase 2 — Integration Guide (Funding Cashflows)

- [x] Provide minimal engine wiring proposal (DuckDB funding → FundingEvent → `process_bar`)
- [x] Provide validation checklist via CLI commands + expected signals


