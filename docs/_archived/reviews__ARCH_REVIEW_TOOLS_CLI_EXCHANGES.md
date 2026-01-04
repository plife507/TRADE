# Architecture Review: Tools, CLI & Exchanges

**Review Date**: 2026-01-02
**Reviewer**: Claude Code (Opus 4.5)
**Scope**: `src/tools/`, `src/cli/`, `src/exchanges/`

---

## Executive Summary

This review covers the three primary interface layers of the TRADE trading bot:

1. **Tools Layer** (`src/tools/`): The canonical API surface for all operations
2. **CLI Layer** (`src/cli/`): Interactive menu-driven interface
3. **Exchanges Layer** (`src/exchanges/`): Bybit API client implementation

**Overall Assessment**: The architecture is well-structured with clear separation of concerns. The tool registry pattern provides a solid foundation for AI agent integration. However, there are opportunities for consistency improvements and some structural concerns noted below.

---

## Part 1: Tools Layer (`src/tools/`)

### 1.1 tool_registry.py

**Purpose**: Central registry for all trading tools, enabling dynamic discovery and execution for orchestrators/bots/AI agents.

**Key Structures**:
- `ToolSpec` dataclass: Encapsulates tool metadata (name, function, description, category, parameters, required)
- `ToolRegistry` class: Singleton registry with methods for listing, discovery, and execution
- `TRADING_ENV_PARAM`: Shared parameter definition for trading environment validation

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `list_tools(category)` | List available tools, optionally filtered by category |
| `list_categories()` | Get all unique tool categories |
| `get_tool_info(name)` | Get OpenAI-compatible function calling spec |
| `get_all_tools_info()` | Get all tool specs for AI agent initialization |
| `execute(name, **kwargs)` | Execute a tool with structured logging |
| `execute_batch(actions)` | Execute multiple tools sequentially |
| `get_registry()` | Get singleton instance |

**Dependencies**:
- `src/tools/shared.py` (ToolResult)
- All individual tool modules (order_tools, position_tools, etc.)
- `src/utils/logger.py`, `src/utils/log_context.py`

**Issues Found**:
1. **Massive Registration Method**: `_register_all_tools()` is ~1200 lines long. This monolithic approach makes it hard to maintain and increases risk of merge conflicts.
2. **No Tool Versioning**: No mechanism for tool versioning or deprecation. If tool signatures change, there's no backward compatibility layer.
3. **Category Inconsistency**: Categories use both dots (`orders.market`) and underscores. Should be standardized.

**Structural Concerns**:
- The singleton pattern via `_registry` global could cause issues in testing scenarios where registry reset is needed.
- Tool execution logging is comprehensive but adds overhead to every call.

---

### 1.2 shared.py

**Purpose**: Shared types and utilities for the tools layer. Defines the canonical `ToolResult` return type.

**Key Structures**:
```python
@dataclass
class ToolResult:
    success: bool
    message: str = ""
    symbol: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    source: Optional[str] = None
```

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `_get_exchange_manager()` | Lazy singleton for ExchangeManager |
| `get_trading_env_summary()` | Get current process trading environment |
| `_get_exchange_manager_for_env(trading_env)` | Get manager with env validation |
| `validate_trading_env_or_error(trading_env)` | Convenience wrapper for tool validation |
| `_ensure_websocket_running()` | Auto-start WebSocket with cooldown |
| `_get_historical_store(env)` | Get DuckDB store for env |

**Dependencies**:
- `src/core/exchange_manager.py`
- `src/config/config.py`, `src/config/constants.py`
- `src/data/realtime_state.py`, `src/data/historical_data_store.py`
- `src/risk/global_risk.py`

**Issues Found**:
1. **WebSocket Startup State**: Global variables `_ws_startup_failed` and `_ws_startup_attempt_time` are not thread-safe.
2. **Hardcoded Cooldown**: 60-second WebSocket retry cooldown is hardcoded, not configurable.

**Structural Concerns**:
- The lazy import pattern (`_get_*` functions) is necessary to avoid circular dependencies but adds complexity.
- `TradingEnvMismatchError` could be in a dedicated exceptions module.

---

### 1.3 order_tools.py

**Purpose**: Order placement tools (market, limit, stop, batch operations).

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `market_buy_tool(symbol, usd_amount)` | Open long at market |
| `market_sell_tool(symbol, usd_amount)` | Open short at market |
| `market_buy_with_tpsl_tool(...)` | Long with TP/SL |
| `market_sell_with_tpsl_tool(...)` | Short with TP/SL |
| `limit_buy_tool(symbol, usd_amount, price)` | Limit buy |
| `limit_sell_tool(symbol, usd_amount, price)` | Limit sell |
| `stop_market_buy_tool(...)` | Stop market buy |
| `stop_market_sell_tool(...)` | Stop market sell |
| `stop_limit_buy_tool(...)` | Stop limit buy |
| `stop_limit_sell_tool(...)` | Stop limit sell |
| `set_leverage_tool(symbol, leverage)` | Set leverage |
| `get_open_orders_tool(symbol)` | List open orders |
| `cancel_order_tool(symbol, order_id)` | Cancel order |
| `amend_order_tool(symbol, order_id, ...)` | Modify order |
| `cancel_all_orders_tool(symbol)` | Cancel all orders |
| `batch_market_orders_tool(orders)` | Batch market orders |
| `batch_limit_orders_tool(orders)` | Batch limit orders |
| `batch_cancel_orders_tool(cancels)` | Batch cancel |

**Dependencies**:
- `src/tools/shared.py`
- `src/core/exchange_manager.py`
- `src/config/config.py`

**Issues Found**:
1. **Inconsistent Error Handling**: Some functions catch broad `Exception`, others catch specific types. Should standardize.
2. **Duplicate Symbol Subscription**: `_ensure_symbol_subscribed(symbol)` called in many places. Could be a decorator.

**Structural Concerns**:
- Functions are well-organized by order type but could benefit from a base class or decorator pattern to reduce repetition.

---

### 1.4 position_tools.py

**Purpose**: Position management and TP/SL tools.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `list_open_positions_tool()` | List all positions |
| `get_position_detail_tool(symbol)` | Get position details |
| `close_position_tool(symbol)` | Close position at market |
| `partial_close_position_tool(symbol, percent, price)` | Partial close |
| `set_take_profit_tool(symbol, take_profit)` | Set TP |
| `set_stop_loss_tool(symbol, stop_loss)` | Set SL |
| `remove_take_profit_tool(symbol)` | Remove TP |
| `remove_stop_loss_tool(symbol)` | Remove SL |
| `set_trailing_stop_tool(symbol, distance)` | Set trailing stop |
| `set_trailing_stop_by_percent_tool(symbol, callback_rate)` | Set trailing % |
| `get_risk_limits_tool(symbol)` | Get risk limits |
| `panic_close_all_tool(reason)` | Emergency close all |

**Dependencies**:
- `src/tools/shared.py`
- `src/core/exchange_manager.py`
- `src/data/realtime_state.py`

**Issues Found**:
1. **WebSocket Fallback Logic**: Position retrieval tries WebSocket first, then REST. The fallback logic is duplicated across functions.
2. **No Position Validation**: Tools like `set_take_profit_tool` don't validate that a position exists before attempting to set TP.

---

### 1.5 account_tools.py

**Purpose**: Account balance, portfolio, and history tools.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `get_account_balance_tool()` | Get wallet balance |
| `get_total_exposure_tool()` | Get total position exposure |
| `get_account_info_tool()` | Get account info |
| `get_portfolio_snapshot_tool()` | Get portfolio snapshot |
| `get_order_history_tool(window)` | Get order history |
| `get_closed_pnl_tool(window)` | Get closed P&L |
| `get_transaction_log_tool(window)` | Get transaction log |
| `get_borrow_history_tool(window)` | Get borrow history |
| `get_collateral_info_tool()` | Get collateral info |
| `get_fee_rates_tool(symbol)` | Get fee rates |

**Dependencies**:
- `src/tools/shared.py`
- `src/core/exchange_manager.py`
- `src/utils/time_range.py`

**Issues Found**:
1. **TimeRange Handling**: Time window parsing is duplicated. Could use a shared helper.
2. **Magic Numbers**: Default limits (50) are hardcoded in multiple places.

---

### 1.6 market_data_tools.py

**Purpose**: Market data query tools.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `get_price_tool(symbol)` | Get current price |
| `get_ohlcv_tool(symbol, interval, limit)` | Get OHLCV candles |
| `get_funding_rate_tool(symbol)` | Get funding rate |
| `get_open_interest_tool(symbol)` | Get open interest |
| `get_orderbook_tool(symbol, limit)` | Get orderbook |
| `get_instruments_tool(symbol)` | Get instrument info |

**Dependencies**:
- `src/tools/shared.py`
- `src/core/exchange_manager.py`

**Issues Found**:
- **No Caching**: Repeated calls for the same data hit the API. Could benefit from short-term caching.

---

### 1.7 diagnostics_tools.py

**Purpose**: Connection testing and health check tools.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `test_connection_tool()` | Test API connection |
| `get_server_time_offset_tool()` | Get time sync offset |
| `get_rate_limit_status_tool()` | Get rate limit status |
| `get_websocket_status_tool()` | Get WebSocket status |
| `exchange_health_check_tool(symbol)` | Comprehensive health check |
| `get_api_environment_tool()` | Get API environment info |
| `is_healthy_for_trading_tool()` | Quick health check |

**Dependencies**:
- `src/tools/shared.py`
- `src/core/exchange_manager.py`
- `src/data/realtime_state.py`

**Issues Found**:
- **Health Check Thresholds**: Time offset thresholds (e.g., 2000ms warning) are hardcoded.

---

### 1.8 data_tools.py

**Purpose**: Historical data management tools (DuckDB operations).

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `get_database_stats_tool()` | Get DB statistics |
| `list_cached_symbols_tool()` | List cached symbols |
| `get_symbol_status_tool(symbol)` | Get symbol status |
| `sync_symbols_tool(symbols, period)` | Sync OHLCV by period |
| `sync_range_tool(symbols, start, end)` | Sync by date range |
| `sync_funding_tool(symbols, period)` | Sync funding rates |
| `sync_open_interest_tool(symbols, period)` | Sync open interest |
| `fill_gaps_tool(symbol)` | Fill data gaps |
| `heal_data_tool(symbol)` | Heal data integrity |
| `delete_symbol_tool(symbol)` | Delete symbol data |
| `vacuum_database_tool()` | Vacuum database |
| `delete_all_data_tool()` | Delete all data |
| `get_funding_history_tool(symbol, period)` | Query funding history |
| `get_open_interest_history_tool(symbol, period)` | Query OI history |
| `get_ohlcv_history_tool(symbol, timeframe)` | Query OHLCV history |

**Dependencies**:
- `src/tools/shared.py`
- `src/data/historical_data_store.py`
- `src/data/data_sync.py`

**Issues Found**:
1. **Environment Parameter**: `env` parameter defaults to "live" but isn't always validated.
2. **No Progress Feedback**: Long-running syncs don't provide progress callbacks.

---

### 1.9 backtest_tools.py

**Purpose**: Legacy backtest tools (system config based).

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `backtest_list_systems_tool()` | List system configs |
| `backtest_get_system_tool(system_id)` | Get system details |
| `backtest_run_tool(system_id)` | Run backtest |
| `backtest_prepare_data_tool(system_id)` | Prepare data |
| `backtest_verify_data_tool(system_id)` | Verify data quality |
| `backtest_list_strategies_tool()` | List strategies |

**Dependencies**:
- `src/tools/shared.py`
- `src/backtest/` modules

**Issues Found**:
- **Legacy Pattern**: These tools use the older "system config" approach. The newer IdeaCard-based tools are the "golden path".

---

### 1.10 backtest_ideacard_tools.py

**Purpose**: IdeaCard-based backtest tools (Golden Path).

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `backtest_list_idea_cards_tool()` | List IdeaCards |
| `backtest_preflight_idea_card_tool(idea_card_id)` | Preflight check |
| `backtest_run_idea_card_tool(idea_card_id)` | Run backtest |
| `backtest_data_fix_tool(idea_card_id)` | Fix data gaps |
| `backtest_indicators_tool(idea_card_id)` | Discover indicators |
| `backtest_idea_card_normalize_tool(idea_card_id)` | Validate/normalize |
| `backtest_idea_card_normalize_batch_tool()` | Batch normalize |

**Key Constants**:
```python
CANONICAL_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
BYBIT_API_INTERVALS = ["1", "5", "15", "60", "240", "D"]
BYBIT_TO_CANONICAL = {"1": "1m", "5": "5m", ...}
```

**Dependencies**:
- `src/tools/shared.py`
- `src/backtest/runtime/preflight.py`
- `src/backtest/engine_factory.py`
- `src/backtest/features/idea_card.py`
- `src/data/data_sync.py`

**Issues Found**:
1. **Long File**: At 1316 lines, this file is doing too much. Could be split by function area.
2. **Duplicate Timeframe Validation**: `validate_canonical_tf()` and `normalize_timestamp()` could be in a shared utility.

**Structural Concerns**:
- The preflight gate pattern is well-designed and should be documented as a pattern for other modules.

---

### 1.11 backtest_audit_tools.py

**Purpose**: Backtest audit and verification tools.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `backtest_audit_math_from_snapshots_tool(run_dir)` | Audit from snapshots |
| `backtest_audit_toolkit_tool()` | Toolkit contract audit |
| `backtest_audit_in_memory_parity_tool(idea_card)` | In-memory parity |
| `backtest_math_parity_tool(idea_card)` | Combined parity audit |
| `verify_artifact_parity_tool(idea_card_id)` | CSV/Parquet parity |
| `backtest_audit_snapshot_plumbing_tool(idea_card_id)` | Data flow validation |
| `backtest_audit_rollup_parity_tool()` | 1m rollup validation |

**Dependencies**:
- `src/tools/shared.py`
- `src/backtest/audits/` modules
- `src/backtest/artifact_parity_verifier.py`

**Issues Found**:
- Well-structured. No significant issues.

---

### 1.12 backtest_cli_wrapper.py

**Purpose**: Re-export facade for backward compatibility.

**Structure**: Simple re-export module that imports from `backtest_ideacard_tools.py` and `backtest_audit_tools.py`.

**Dependencies**:
- `backtest_ideacard_tools.py`
- `backtest_audit_tools.py`

**Issues Found**:
- **Consider Deprecation**: If this is purely for backward compatibility, consider adding deprecation warnings.

---

## Part 2: CLI Layer (`src/cli/`)

### 2.1 menus/__init__.py

**Purpose**: Menu module exports.

**Exports**:
- `data_menu`, `market_data_menu`
- `orders_menu`, `market_orders_menu`, `limit_orders_menu`, `stop_orders_menu`, `manage_orders_menu`
- `positions_menu`, `account_menu`, `backtest_menu`

---

### 2.2 menus/orders_menu.py

**Purpose**: Order placement and management menus.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `orders_menu(cli)` | Main orders menu |
| `market_orders_menu(cli)` | Market orders submenu |
| `limit_orders_menu(cli)` | Limit orders submenu |
| `stop_orders_menu(cli)` | Stop orders submenu |
| `manage_orders_menu(cli)` | Order management submenu |
| `_get_time_in_force_with_hints()` | TIF selection helper |

**Dependencies**:
- `rich` (Console, Panel, Table, Prompt, Confirm)
- `src/cli/styles.py` (CLIStyles, CLIColors, CLIIcons, BillArtWrapper)
- `src/tools/` (order tools)
- `src/config/config.py`
- `trade_cli.py` (get_input, get_choice, run_tool_action, etc.)

**Issues Found**:
1. **Circular Import Pattern**: Imports from `trade_cli` inside functions to avoid circular imports. This is a code smell.
2. **Duplicate Input Validation**: Similar input handling patterns repeated across menus.
3. **Magic Sentinel**: Uses `BACK` sentinel from `trade_cli.py` without type hints.

**Structural Concerns**:
- Menu functions are long (100+ lines each). Could benefit from extraction of common patterns.
- Error handling is consistent but verbose.

---

### 2.3 smoke_tests/__init__.py

**Purpose**: Smoke test module exports.

**Exports**:
- `run_smoke_suite`, `run_full_cli_smoke`
- `run_data_builder_smoke`, `run_extensive_data_smoke`
- `run_comprehensive_order_smoke`, `run_live_check_smoke`
- `run_backtest_smoke`, `run_backtest_mixed_smoke`
- `run_phase6_backtest_smoke`, `run_backtest_suite_smoke`
- `run_metadata_smoke`
- `run_mark_price_smoke`
- `run_structure_smoke`, `run_state_tracking_smoke`, `run_state_tracking_parity_smoke`
- `run_rules_smoke`

---

### 2.4 smoke_tests/core.py

**Purpose**: Main smoke test entry points.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `run_smoke_suite(mode, app, config)` | Main entry point |
| `run_full_cli_smoke(smoke_config, app, config)` | Full CLI smoke test |

**Dependencies**:
- `rich` (Console, Panel)
- `src/tools/` (all tool imports)
- Sibling smoke test modules

**Issues Found**:
1. **Large Import Block**: 45+ tool imports at top of file. Could use `ToolRegistry` instead.
2. **Hardcoded Test Counts**: Test numbering (2.1, 2.2, etc.) is hardcoded, making reordering error-prone.

---

### 2.5 utils.py & styles.py

**Purpose**: CLI utility functions and styling constants.

**Key Components** (styles.py):
- `CLIColors`: Color constants (NEON_CYAN, NEON_GREEN, etc.)
- `CLIIcons`: Unicode icon constants
- `CLIStyles`: Menu table creation, panel styling
- `BillArtWrapper`: ASCII art borders

---

## Part 3: Exchanges Layer (`src/exchanges/`)

### 3.1 bybit_client.py

**Purpose**: Main Bybit API client using official pybit library.

**Key Class**: `BybitClient`

**Key Methods**:
| Method | Purpose |
|--------|---------|
| `__init__(use_demo, use_live_for_market_data)` | Initialize with mode |
| `connect()` | Establish connection |
| `disconnect()` | Clean disconnect |
| `_sync_server_time()` | Time synchronization |
| Property accessors for pybit sessions |

**Key Patterns**:
- **Delegation**: Delegates to helper modules (bybit_market, bybit_account, bybit_trading, bybit_websocket)
- **Error Wrapping**: `@handle_pybit_errors` decorator wraps pybit exceptions
- **Rate Limiting**: `create_bybit_limiters()` creates tiered rate limiters

**Dependencies**:
- `pybit` (official Bybit SDK)
- `src/utils/rate_limiter.py`
- `src/utils/logger.py`
- Helper modules (bybit_*.py)

**Issues Found**:
1. **Session Management**: Multiple pybit session types (HTTP, WebSocket) are managed separately. Cleanup on disconnect could be more robust.
2. **Error Class**: `BybitAPIError` wraps pybit errors but loses stack trace context in some cases.

---

### 3.2 bybit_account.py

**Purpose**: Account operations delegated from main client.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `get_wallet_balance(client)` | Get wallet balance |
| `get_positions(client, symbol)` | Get positions |
| `get_account_info(client)` | Get UTA account info |
| `get_fee_rates(client, symbol)` | Get fee rates |
| `get_transaction_log(client, ...)` | Get transaction log |
| `get_collateral_info(client, currency)` | Get collateral info |
| `get_borrow_history(client, ...)` | Get borrow history |
| `set_mmp(client, ...)` | Set market maker protection |

**Dependencies**:
- Parent client for pybit session access

**Issues Found**:
- Functions take `client` as first parameter (module-level, not OOP). Consider whether this should be a class method pattern.

---

### 3.3 bybit_trading.py

**Purpose**: Order execution and position management.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `create_order(client, ...)` | Create order |
| `amend_order(client, ...)` | Modify order |
| `cancel_order(client, ...)` | Cancel order |
| `cancel_all_orders(client, ...)` | Cancel all |
| `get_open_orders(client, ...)` | List open orders |
| `get_order_history(client, ...)` | Order history |
| `get_closed_pnl(client, ...)` | Closed P&L |
| `set_leverage(client, symbol, leverage)` | Set leverage |
| `set_trading_stop(client, ...)` | Set TP/SL |
| `set_margin_mode(client, ...)` | Set margin mode |
| `batch_create_orders(client, orders)` | Batch create |
| `batch_amend_orders(client, amends)` | Batch amend |
| `batch_cancel_orders(client, cancels)` | Batch cancel |

**Dependencies**:
- Parent client
- `src/utils/time_range.py`

**Issues Found**:
1. **Order Type Mapping**: Order type string mapping is hardcoded. Could be an enum.
2. **Batch Validation**: Batch operations don't validate order count limits before API call.

---

### 3.4 bybit_market.py

**Purpose**: Market data methods.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `get_klines(client, symbol, interval, limit)` | Get OHLCV as DataFrame |
| `get_ticker(client, symbol)` | Get ticker |
| `get_funding_rate(client, symbol)` | Get funding rate |
| `get_open_interest(client, symbol, interval)` | Get OI |
| `get_orderbook(client, symbol, limit)` | Get orderbook |
| `get_instruments(client, symbol)` | Get instrument info |
| `get_instrument_launch_time(client, symbol)` | Get launch time |

**Dependencies**:
- Parent client
- `pandas` (for DataFrame return)

**Issues Found**:
- **Inconsistent Return Types**: `get_klines` returns DataFrame, others return dicts. Should document clearly.

---

### 3.5 bybit_websocket.py

**Purpose**: WebSocket connection and subscription management.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `start_websocket(client)` | Start WS connection |
| `stop_websocket(client)` | Stop WS connection |
| `subscribe_public(client, symbol, topic)` | Subscribe public stream |
| `subscribe_private(client, topic)` | Subscribe private stream |
| `_install_ws_cleanup_hook()` | Suppress close errors |

**Key Attributes**:
- `use_live_for_market_data`: Flag for hybrid mode (demo trading + live market data)

**Dependencies**:
- Parent client
- `pybit.unified_trading` (WebSocket classes)

**Issues Found**:
1. **Cleanup Hook**: `_install_ws_cleanup_hook()` patches `atexit._run_exitfuncs` which is fragile.
2. **No Reconnection Logic**: WebSocket doesn't have built-in reconnection on disconnect.

---

## Cross-Cutting Concerns

### Error Handling Pattern

The codebase uses a consistent pattern:
1. Tools return `ToolResult(success=False, error="...")` on failure
2. Exchange layer raises `BybitAPIError` wrapped around pybit errors
3. CLI displays errors via `print_error_below_menu()`

**Recommendation**: Create a unified error taxonomy with error codes for programmatic handling.

### Logging Pattern

The codebase uses structured event logging:
```python
logger.event("tool.call.start", component="...", tool_name="...", ...)
logger.event("tool.call.end", success=True, elapsed_ms=...)
```

**Recommendation**: Consider adding trace IDs for distributed tracing support.

### Trading Environment Validation

The `trading_env` parameter pattern is well-designed:
- Process has fixed env at startup
- Tools validate caller intent
- Clear error messages on mismatch

**Recommendation**: Document this pattern in a developer guide.

---

## Summary of Issues

### High Priority

| Issue | Location | Description |
|-------|----------|-------------|
| Monolithic registration | `tool_registry.py` | `_register_all_tools()` is 1200+ lines |
| Circular imports | `menus/*.py` | Import from `trade_cli` inside functions |
| Thread safety | `shared.py` | WebSocket state globals not thread-safe |
| File size | `backtest_ideacard_tools.py` | 1316 lines, should be split |

### Medium Priority

| Issue | Location | Description |
|-------|----------|-------------|
| No tool versioning | `tool_registry.py` | No deprecation mechanism |
| Inconsistent categories | `tool_registry.py` | Mix of dots and underscores |
| Duplicate patterns | `order_tools.py`, `position_tools.py` | Similar code repeated |
| Hardcoded values | Various | Magic numbers, thresholds |

### Low Priority

| Issue | Location | Description |
|-------|----------|-------------|
| No caching | `market_data_tools.py` | Repeated API calls |
| Legacy tools | `backtest_tools.py` | Old system config pattern |
| Import block | `smoke_tests/core.py` | 45+ imports could use registry |

---

## Recommendations

1. **Refactor tool_registry.py**: Split `_register_all_tools()` into category-specific registration methods or use decorators.

2. **Standardize error handling**: Create base exception classes and error codes.

3. **Add tool versioning**: Implement deprecation warnings and version metadata in ToolSpec.

4. **Fix circular imports**: Consider dependency injection or a mediator pattern for CLI-tool communication.

5. **Split large files**: `backtest_ideacard_tools.py` should be split by function area (preflight, run, normalize, etc.).

6. **Add caching layer**: Implement short-term caching for market data tools.

7. **Document patterns**: Create developer guides for the trading_env validation pattern and preflight gate pattern.

8. **Thread safety audit**: Review all global state for thread safety, especially WebSocket-related.

---

*End of Review*
