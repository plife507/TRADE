# Refactoring TODO: Mega-File Splits

**Created**: 2026-01-03
**Updated**: 2026-01-04
**Status**: Phases 1-3 COMPLETE, Phase 4 pending

---

## Prerequisites

- [x] All validation passes (confirmed 2026-01-03)
- [x] Type fixes applied (cast, Literal annotations)
- [x] Debug prints removed

---

## Phase 1: Datetime Consolidation - COMPLETE

**Goal**: Single source of truth for datetime parsing/validation

### 1.1 Create datetime_utils.py
- [x] Create `src/utils/datetime_utils.py`
- [x] Move `_normalize_datetime()` from `data_tools.py:31-82`
- [x] Move `_validate_time_range()` from `data_tools.py:84-112`
- [x] Move `_normalize_time_range_params()` from `data_tools.py:114-148`
- [x] Add `normalize_datetime_for_storage()` (from backtest_ideacard_tools pattern)

### 1.2 Update Consumers
- [x] Update `data_tools.py` to import from `datetime_utils`
- [x] Update `backtest_ideacard_tools.py` to import from `datetime_utils`
- [x] Add backward-compat aliases in original locations

### 1.3 Validate Phase 1
- [x] `python -m py_compile src/utils/datetime_utils.py`
- [x] `python trade_cli.py --smoke data` passes

---

## Phase 2: Split data_tools.py - COMPLETE

**Goal**: 2,205 LOC -> 4 focused modules

### 2.1 Create data_tools_common.py (~150 LOC)
- [x] Create `src/tools/data_tools_common.py`
- [x] Move constants: `TF_GROUP_LOW`, `TF_GROUP_MID`, `TF_GROUP_HIGH`, `MAX_CHUNK_DAYS`, etc.
- [x] Move `_build_extremes_metadata()` (lines 1969-2044)
- [x] Move `_persist_extremes_to_db()` (lines 2046-2147)
- [x] Move `_sync_range_chunked()` (lines 1916-1952)
- [x] Move `_days_to_period()` (lines 1954-1967)

### 2.2 Create data_tools_status.py (~300 LOC)
- [x] Create `src/tools/data_tools_status.py`
- [x] Move `get_database_stats_tool()` (lines 150-238)
- [x] Move `list_cached_symbols_tool()` (lines 240-317)
- [x] Move `get_symbol_status_tool()` (lines 319-381)
- [x] Move `get_symbol_summary_tool()` (lines 383-411)
- [x] Move `get_symbol_timeframe_ranges_tool()` (lines 413-472)
- [x] Move `get_data_extremes_tool()` (lines 2149-2205)

### 2.3 Create data_tools_sync.py (~700 LOC)
- [x] Create `src/tools/data_tools_sync.py`
- [x] Move `sync_symbols_tool()` (lines 474-549)
- [x] Move `sync_range_tool()` (lines 551-598)
- [x] Move `fill_gaps_tool()` (lines 600-645)
- [x] Move `heal_data_tool()` (lines 647-702)
- [x] Move `delete_symbol_tool()` (lines 704-744)
- [x] Move `cleanup_empty_symbols_tool()` (lines 746-775)
- [x] Move `vacuum_database_tool()` (lines 777-802)
- [x] Move `delete_all_data_tool()` (lines 804-865)
- [x] Move `sync_funding_tool()` (lines 870-919)
- [x] Move `sync_open_interest_tool()` (lines 1146-1199)
- [x] Move `get_instrument_launch_time_tool()` (lines 1600-1649)
- [x] Move `sync_full_from_launch_tool()` (lines 1651-1914)

### 2.4 Create data_tools_query.py (~450 LOC)
- [x] Create `src/tools/data_tools_query.py`
- [x] Move `get_funding_history_tool()` (lines 921-1020)
- [x] Move `get_ohlcv_history_tool()` (lines 1025-1141)
- [x] Move `get_open_interest_history_tool()` (lines 1201-1300)
- [x] Move `sync_to_now_tool()` (lines 1305-1364)
- [x] Move `sync_to_now_and_fill_gaps_tool()` (lines 1366-1459)
- [x] Move `build_symbol_history_tool()` (lines 1461-1580)

### 2.5 Update data_tools.py as Re-export
- [x] Replace `data_tools.py` with re-export wrapper

### 2.6 Validate Phase 2
- [x] All new files compile: `python -m py_compile src/tools/data_tools_*.py`
- [x] `python trade_cli.py --smoke data_extensive` passes
- [x] Imports work: `from src.tools.data_tools import sync_symbols_tool`

---

## Phase 3: Split tool_registry.py - COMPLETE

**Goal**: 1,472 LOC -> registry core + 8 spec modules

### 3.1 Create specs/ Directory Structure
- [x] Create `src/tools/specs/__init__.py`
- [x] Create `src/tools/specs/shared_params.py`
  - [x] Move `TRADING_ENV_PARAM` definition
  - [x] Add `DATA_ENV_PARAM`, `SYMBOL_PARAM`, `TIME_RANGE_PARAMS`

### 3.2 Extract Order Specs (18 tools)
- [x] Create `src/tools/specs/orders_specs.py`
- [x] Move specs: `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl`
- [x] Move specs: `limit_buy`, `limit_sell`, `partial_close`
- [x] Move specs: `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell`
- [x] Move specs: `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders`
- [x] Move specs: `set_leverage`, `batch_*` orders

### 3.3 Extract Position Specs (13 tools)
- [x] Create `src/tools/specs/positions_specs.py`
- [x] Move specs: `list_open_positions`, `get_position_info`, `close_position`
- [x] Move specs: `set_tp`, `set_sl`, `set_tpsl`, `cancel_tpsl`
- [x] Move specs: `set_trailing_stop`, `cancel_trailing_stop`
- [x] Move specs: `panic_close_all`, position config tools

### 3.4 Extract Account Specs (8 tools)
- [x] Create `src/tools/specs/account_specs.py`
- [x] Move specs: `get_balance`, `get_portfolio_margin`, `get_account_info`
- [x] Move specs: `get_transaction_log`, `get_trade_history`
- [x] Move specs: `get_closed_pnl`, `get_order_history`, `get_leverage_info`

### 3.5 Extract Data Specs (15 tools)
- [x] Create `src/tools/specs/data_specs.py`
- [x] Move specs: all `*_tool` from data_tools (sync, query, status, maintenance)

### 3.6 Extract Market Specs (3 tools)
- [x] Create `src/tools/specs/market_specs.py`
- [x] Move specs: `get_price`, `get_ohlcv`, `get_funding_rate`

### 3.7 Extract System Specs (7 tools)
- [x] Create `src/tools/specs/system_specs.py`
- [x] Move specs: `check_connection`, `get_health_status`, `check_time_sync`
- [x] Move specs: `check_api_environment`, `get_rate_limit_status`
- [x] Move specs: `get_api_key_info`, `list_instruments`

### 3.8 Extract Backtest Specs (17 tools)
- [x] Create `src/tools/specs/backtest_specs.py`
- [x] Move specs: all `backtest_*` tools

### 3.9 Update tool_registry.py
- [x] Replace inline specs with imports from specs/

### 3.10 Validate Phase 3
- [x] All spec files compile
- [x] `registry.list_tools()` returns 80 tools
- [x] `registry.execute("market_buy", ...)` works
- [x] `python trade_cli.py --smoke orders` passes

---

## Phase 4: Split play.py (PENDING - After Forge Migration)

**Goal**: 1,705 LOC -> 5 focused modules

**NOTE**: This phase depends on the Forge Migration (see TODO.md). The file will be renamed from `idea_card.py` to `play.py` as part of migration Phase F1.

### 4.1 Create risk_model.py (~150 LOC)
- [ ] Create `src/forge/risk_model.py`
- [ ] Move enums: `StopLossType`, `TakeProfitType`, `SizingModel`
- [ ] Move classes: `StopLossRule`, `TakeProfitRule`, `SizingRule`
- [ ] Move class: `RiskModel`

### 4.2 Create signal_rules.py (~180 LOC)
- [ ] Create `src/forge/signal_rules.py`
- [ ] Move enum: `RuleOperator`
- [ ] Move constant: `BANNED_OPERATORS`
- [ ] Move classes: `Condition`, `EntryRule`, `ExitRule`
- [ ] Move class: `SignalRules`

### 4.3 Create structure_specs.py (~280 LOC)
- [ ] Create `src/forge/incremental/structure_specs.py`
- [ ] Move class: `IncrementalStructureSpec`
- [ ] Move function: `_parse_structure_specs_list()`
- [ ] Move functions: `_resolve_variable()`, `_resolve_params()`

### 4.4 Create play_loader.py (~100 LOC)
- [ ] Create `src/forge/play_loader.py`
- [ ] Move constant: `PLAYS_DIR`
- [ ] Move function: `load_play()`
- [ ] Move function: `list_plays()`

### 4.5 Update play.py
- [ ] Add imports from new modules
- [ ] Remove moved code
- [ ] Keep: `Play`, `AccountConfig`, `FeeModel`, `Timeframes`, `TFConfig`, `PositionPolicy`, `MarketStructureConfig`

### 4.6 Validate Phase 4
- [ ] All new files compile
- [ ] `python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation` passes
- [ ] `from src.forge.play import Play, load_play` works

---

## Phase 5: Final Validation

- [ ] `python trade_cli.py backtest audit-toolkit` (42/42 indicators)
- [ ] `python trade_cli.py backtest audit-rollup` (11/11 intervals)
- [ ] `python trade_cli.py backtest structure-smoke` (Stage 6 pass)
- [ ] `python trade_cli.py --smoke full` (0 failures)
- [ ] No file > 500 LOC (verify with line counts)
- [ ] Commit with message: `refactor: split mega-files into focused modules`

---

## Phase 6: Forge Migration (See TODO.md)

This phase is tracked in detail in [TODO.md](TODO.md) under "Active Work: Forge Migration".

Summary:
- Phase F1: Rename paths and references (IdeaCard → Play, idea_cards → plays)
- Phase F2: Create `src/forge/` structure
- Phase F3: Implement hierarchy (Setup → Play → Playbook → System)

---

## Rollback Plan

If any phase fails validation:
1. `git checkout -- src/tools/ src/backtest/ src/utils/`
2. Identify failing test
3. Fix specific module
4. Re-run validation

---

## File Summary

**Completed files (14)**:
```
src/utils/datetime_utils.py
src/tools/data_tools_common.py
src/tools/data_tools_status.py
src/tools/data_tools_sync.py
src/tools/data_tools_query.py
src/tools/specs/__init__.py
src/tools/specs/shared_params.py
src/tools/specs/orders_specs.py
src/tools/specs/positions_specs.py
src/tools/specs/account_specs.py
src/tools/specs/data_specs.py
src/tools/specs/market_specs.py
src/tools/specs/system_specs.py
src/tools/specs/backtest_specs.py
```

**Pending files (4)** - will be under `src/forge/` after migration:
```
src/forge/risk_model.py
src/forge/signal_rules.py
src/forge/play_loader.py
src/forge/incremental/structure_specs.py
```

**Modified files (3)**:
```
src/tools/data_tools.py -> re-export wrapper
src/tools/tool_registry.py -> load from specs/
src/forge/play.py -> imports from splits (pending, after migration)
```
