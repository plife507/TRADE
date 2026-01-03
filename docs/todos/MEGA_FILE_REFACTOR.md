# Refactoring TODO: Mega-File Splits

**Created**: 2026-01-03
**Status**: Ready for execution
**Estimated Effort**: 2-3 hours total

---

## Prerequisites

- [x] All validation passes (confirmed 2026-01-03)
- [x] Type fixes applied (cast, Literal annotations)
- [x] Debug prints removed

---

## Phase 1: Datetime Consolidation (~20 min)

**Goal**: Single source of truth for datetime parsing/validation

### 1.1 Create datetime_utils.py
- [ ] Create `src/utils/datetime_utils.py`
- [ ] Move `_normalize_datetime()` from `data_tools.py:31-82`
- [ ] Move `_validate_time_range()` from `data_tools.py:84-112`
- [ ] Move `_normalize_time_range_params()` from `data_tools.py:114-148`
- [ ] Add `normalize_datetime_for_storage()` (from backtest_ideacard_tools pattern)

### 1.2 Update Consumers
- [ ] Update `data_tools.py` to import from `datetime_utils`
- [ ] Update `backtest_ideacard_tools.py` to import from `datetime_utils`
- [ ] Add backward-compat aliases in original locations

### 1.3 Validate Phase 1
- [ ] `python -m py_compile src/utils/datetime_utils.py`
- [ ] `python trade_cli.py --smoke data` passes

---

## Phase 2: Split data_tools.py (~45 min)

**Goal**: 2,205 LOC -> 4 focused modules

### 2.1 Create data_tools_common.py (~150 LOC)
- [ ] Create `src/tools/data_tools_common.py`
- [ ] Move constants: `TF_GROUP_LOW`, `TF_GROUP_MID`, `TF_GROUP_HIGH`, `MAX_CHUNK_DAYS`, etc.
- [ ] Move `_build_extremes_metadata()` (lines 1969-2044)
- [ ] Move `_persist_extremes_to_db()` (lines 2046-2147)
- [ ] Move `_sync_range_chunked()` (lines 1916-1952)
- [ ] Move `_days_to_period()` (lines 1954-1967)

### 2.2 Create data_tools_status.py (~300 LOC)
- [ ] Create `src/tools/data_tools_status.py`
- [ ] Move `get_database_stats_tool()` (lines 150-238)
- [ ] Move `list_cached_symbols_tool()` (lines 240-317)
- [ ] Move `get_symbol_status_tool()` (lines 319-381)
- [ ] Move `get_symbol_summary_tool()` (lines 383-411)
- [ ] Move `get_symbol_timeframe_ranges_tool()` (lines 413-472)
- [ ] Move `get_data_extremes_tool()` (lines 2149-2205)

### 2.3 Create data_tools_sync.py (~700 LOC)
- [ ] Create `src/tools/data_tools_sync.py`
- [ ] Move `sync_symbols_tool()` (lines 474-549)
- [ ] Move `sync_range_tool()` (lines 551-598)
- [ ] Move `fill_gaps_tool()` (lines 600-645)
- [ ] Move `heal_data_tool()` (lines 647-702)
- [ ] Move `delete_symbol_tool()` (lines 704-744)
- [ ] Move `cleanup_empty_symbols_tool()` (lines 746-775)
- [ ] Move `vacuum_database_tool()` (lines 777-802)
- [ ] Move `delete_all_data_tool()` (lines 804-865)
- [ ] Move `sync_funding_tool()` (lines 870-919)
- [ ] Move `sync_open_interest_tool()` (lines 1146-1199)
- [ ] Move `get_instrument_launch_time_tool()` (lines 1600-1649)
- [ ] Move `sync_full_from_launch_tool()` (lines 1651-1914)

### 2.4 Create data_tools_query.py (~450 LOC)
- [ ] Create `src/tools/data_tools_query.py`
- [ ] Move `get_funding_history_tool()` (lines 921-1020)
- [ ] Move `get_ohlcv_history_tool()` (lines 1025-1141)
- [ ] Move `get_open_interest_history_tool()` (lines 1201-1300)
- [ ] Move `sync_to_now_tool()` (lines 1305-1364)
- [ ] Move `sync_to_now_and_fill_gaps_tool()` (lines 1366-1459)
- [ ] Move `build_symbol_history_tool()` (lines 1461-1580)

### 2.5 Update data_tools.py as Re-export
- [ ] Replace `data_tools.py` with re-export wrapper:
  ```python
  from .data_tools_common import *
  from .data_tools_status import *
  from .data_tools_sync import *
  from .data_tools_query import *
  ```

### 2.6 Validate Phase 2
- [ ] All new files compile: `python -m py_compile src/tools/data_tools_*.py`
- [ ] `python trade_cli.py --smoke data_extensive` passes
- [ ] Imports work: `from src.tools.data_tools import sync_symbols_tool`

---

## Phase 3: Split tool_registry.py (~45 min)

**Goal**: 1,472 LOC -> registry core + 8 spec modules

### 3.1 Create specs/ Directory Structure
- [ ] Create `src/tools/specs/__init__.py`
- [ ] Create `src/tools/specs/shared_params.py`
  - [ ] Move `TRADING_ENV_PARAM` definition
  - [ ] Add `DATA_ENV_PARAM`, `SYMBOL_PARAM`, `TIME_RANGE_PARAMS`

### 3.2 Extract Order Specs (18 tools)
- [ ] Create `src/tools/specs/orders_specs.py`
- [ ] Move specs: `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl`
- [ ] Move specs: `limit_buy`, `limit_sell`, `partial_close`
- [ ] Move specs: `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell`
- [ ] Move specs: `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders`
- [ ] Move specs: `set_leverage`, `batch_*` orders

### 3.3 Extract Position Specs (13 tools)
- [ ] Create `src/tools/specs/positions_specs.py`
- [ ] Move specs: `list_open_positions`, `get_position_info`, `close_position`
- [ ] Move specs: `set_tp`, `set_sl`, `set_tpsl`, `cancel_tpsl`
- [ ] Move specs: `set_trailing_stop`, `cancel_trailing_stop`
- [ ] Move specs: `panic_close_all`, position config tools

### 3.4 Extract Account Specs (8 tools)
- [ ] Create `src/tools/specs/account_specs.py`
- [ ] Move specs: `get_balance`, `get_portfolio_margin`, `get_account_info`
- [ ] Move specs: `get_transaction_log`, `get_trade_history`
- [ ] Move specs: `get_closed_pnl`, `get_order_history`, `get_leverage_info`

### 3.5 Extract Data Specs (15 tools)
- [ ] Create `src/tools/specs/data_specs.py`
- [ ] Move specs: all `*_tool` from data_tools (sync, query, status, maintenance)

### 3.6 Extract Market Specs (3 tools)
- [ ] Create `src/tools/specs/market_specs.py`
- [ ] Move specs: `get_price`, `get_ohlcv`, `get_funding_rate`

### 3.7 Extract System Specs (7 tools)
- [ ] Create `src/tools/specs/system_specs.py`
- [ ] Move specs: `check_connection`, `get_health_status`, `check_time_sync`
- [ ] Move specs: `check_api_environment`, `get_rate_limit_status`
- [ ] Move specs: `get_api_key_info`, `list_instruments`

### 3.8 Extract Backtest Specs (17 tools)
- [ ] Create `src/tools/specs/backtest_specs.py`
- [ ] Move specs: all `backtest_*` tools

### 3.9 Update tool_registry.py
- [ ] Replace inline specs with:
  ```python
  from .specs import (
      orders_specs, positions_specs, account_specs,
      data_specs, market_specs, system_specs, backtest_specs
  )

  def _register_all_tools(self):
      all_specs = (
          orders_specs.SPECS + positions_specs.SPECS + ...
      )
      for spec in all_specs:
          self._register(**spec)
  ```

### 3.10 Validate Phase 3
- [ ] All spec files compile
- [ ] `registry.list_tools()` returns 81 tools
- [ ] `registry.execute("market_buy", ...)` works
- [ ] `python trade_cli.py --smoke orders` passes

---

## Phase 4: Split idea_card.py (~45 min)

**Goal**: 1,705 LOC -> 5 focused modules

### 4.1 Create risk_model.py (~150 LOC)
- [ ] Create `src/backtest/risk_model.py`
- [ ] Move enums: `StopLossType`, `TakeProfitType`, `SizingModel`
- [ ] Move classes: `StopLossRule`, `TakeProfitRule`, `SizingRule`
- [ ] Move class: `RiskModel`

### 4.2 Create signal_rules.py (~180 LOC)
- [ ] Create `src/backtest/signal_rules.py`
- [ ] Move enum: `RuleOperator`
- [ ] Move constant: `BANNED_OPERATORS`
- [ ] Move classes: `Condition`, `EntryRule`, `ExitRule`
- [ ] Move class: `SignalRules`

### 4.3 Create structure_specs.py (~280 LOC)
- [ ] Create `src/backtest/incremental/structure_specs.py`
- [ ] Move class: `IncrementalStructureSpec`
- [ ] Move function: `_parse_structure_specs_list()`
- [ ] Move functions: `_resolve_variable()`, `_resolve_params()`

### 4.4 Create idea_card_loader.py (~100 LOC)
- [ ] Create `src/backtest/idea_card_loader.py`
- [ ] Move constant: `IDEA_CARDS_DIR`
- [ ] Move function: `load_idea_card()`
- [ ] Move function: `list_idea_cards()`

### 4.5 Update idea_card.py
- [ ] Add imports from new modules
- [ ] Remove moved code
- [ ] Keep: `IdeaCard`, `AccountConfig`, `FeeModel`, `Timeframes`, `TFConfig`, `PositionPolicy`, `MarketStructureConfig`

### 4.6 Validate Phase 4
- [ ] All new files compile
- [ ] `python trade_cli.py backtest idea-card-normalize-batch --dir configs/idea_cards/_validation` passes
- [ ] `from src.backtest.idea_card import IdeaCard, load_idea_card` works

---

## Phase 5: Final Validation

- [ ] `python trade_cli.py backtest audit-toolkit` (42/42 indicators)
- [ ] `python trade_cli.py backtest audit-rollup` (11/11 intervals)
- [ ] `python trade_cli.py backtest structure-smoke` (Stage 6 pass)
- [ ] `python trade_cli.py --smoke full` (0 failures)
- [ ] No file > 500 LOC (verify with line counts)
- [ ] Commit with message: `refactor: split mega-files into focused modules`

---

## Rollback Plan

If any phase fails validation:
1. `git checkout -- src/tools/ src/backtest/ src/utils/`
2. Identify failing test
3. Fix specific module
4. Re-run validation

---

## File Summary

**New files (18)**:
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
src/backtest/risk_model.py
src/backtest/signal_rules.py
src/backtest/idea_card_loader.py
src/backtest/incremental/structure_specs.py
```

**Modified files (3)**:
```
src/tools/data_tools.py -> re-export wrapper
src/tools/tool_registry.py -> load from specs/
src/backtest/idea_card.py -> imports from splits
```
