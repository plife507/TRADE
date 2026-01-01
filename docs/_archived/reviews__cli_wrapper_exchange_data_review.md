# CLI Wrapper Review: Exchange & Data Operations

**Date:** 2024-12-19  
**Scope:** CLI wrapper architecture for exchange and data operations  
**Files Reviewed:**
- `trade_cli.py`
- `src/cli/menus/data_menu.py`
- `src/cli/menus/market_data_menu.py`
- `src/tools/data_tools.py`
- `src/tools/market_data_tools.py`
- `src/tools/order_tools.py`
- `src/tools/shared.py`
- `src/core/exchange_manager.py`
- `src/exchanges/bybit_client.py`

## Architecture Overview

The CLI follows a clean layered architecture:

```
CLI Layer (trade_cli.py + menus/)
    ↓
Tools Layer (src/tools/*)
    ↓
Domain Layer (ExchangeManager / HistoricalDataStore)
    ↓
Exchange/API Layer (BybitClient / pybit)
```

### Key Principles

1. **Pure Shell Pattern**: CLI handles only UI/input, delegates all business logic to tools
2. **Tool Layer Abstraction**: Consistent `ToolResult` interface across all operations
3. **Environment Separation**: Four-leg API architecture (Trading LIVE/DEMO, Data LIVE/DEMO)
4. **Domain Isolation**: Clear boundaries between SIMULATOR, LIVE, and SHARED domains

## Strengths

### 1. Clear Separation of Concerns

- **CLI Layer**: Pure shell - only gets user input, calls tools, prints results
- **Tools Layer**: Provides consistent API surface for CLI and orchestrators/bots
- **Domain Layer**: Encapsulates business logic (ExchangeManager, HistoricalDataStore)
- **Exchange Layer**: Abstracts API details (BybitClient wraps pybit)

**Example:**
```python
# CLI (trade_cli.py)
def data_menu(self):
    """Historical data builder menu. Delegates to src.cli.menus.data_menu."""
    data_menu_handler(self)

# Menu (src/cli/menus/data_menu.py)
result = run_tool_action("data.stats", get_database_stats_tool, env=data_env)
print_data_result("data.stats", result)

# Tool (src/tools/data_tools.py)
def get_database_stats_tool(env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult:
    store = _get_historical_store(env=env)
    stats = store.get_database_stats()
    return ToolResult(success=True, message=..., data=stats)
```

### 2. Consistent Tool Interface

- All tools return `ToolResult` with standardized fields:
  - `success: bool`
  - `message: str`
  - `symbol: Optional[str]`
  - `data: Optional[Dict[str, Any]]`
  - `error: Optional[str]`
  - `source: Optional[str]` ("rest_api", "websocket", "duckdb")

- Consistent error handling and messaging
- Environment-aware (LIVE/DEMO) with validation

### 3. Environment Management

**Four-Leg API Architecture:**
- **Trading LIVE**: Real money trading (api.bybit.com)
- **Trading DEMO**: Fake money trading (api-demo.bybit.com)
- **Data LIVE**: Canonical historical data for backtesting (api.bybit.com)
- **Data DEMO**: Demo-only history for validation (api-demo.bybit.com)

**Implementation:**
- Clear separation between trading and data environments
- Data environment toggle in CLI (option 23 in data menu)
- Trading environment validation via `trading_env` parameter for agent/orchestrator use
- Process-level environment is fixed at startup; tools validate but don't switch

### 4. Comprehensive Data Tools

**Features:**
- Complete DuckDB operations (sync, query, heal, gap fill)
- Flexible time range queries (period strings or explicit start/end datetimes)
- Environment-aware (`env` parameter defaults to "live")
- Composite operations (`build_symbol_history_tool`, `sync_to_now_and_fill_gaps_tool`)
- Full bootstrap from launch (`sync_full_from_launch_tool`)

**Example:**
```python
# Period-based query
result = get_ohlcv_history_tool(
    symbol="BTCUSDT",
    timeframe="1h",
    period="1M",
    env="live"
)

# Explicit date range
result = get_ohlcv_history_tool(
    symbol="BTCUSDT",
    timeframe="1h",
    start="2024-01-01",
    end="2024-01-31",
    env="live"
)
```

### 5. Market Data Tools

- Simple, focused wrappers around ExchangeManager
- Consistent error handling
- Clear return types
- Comprehensive test suite (`run_market_data_tests_tool`)

## Areas for Improvement

### 1. Inconsistent Environment Handling

**Issue:**
- **Market data tools**: No `env` parameter; always use trading API
- **Data tools**: Explicit `env` parameter with defaults

**Current Behavior:**
```python
# Market data - uses trading API (no env param)
get_price_tool(symbol: str) -> ToolResult

# Historical data - explicit env param
get_ohlcv_history_tool(symbol: str, env: DataEnv = DEFAULT_DATA_ENV) -> ToolResult
```

**Recommendation:**
- Document that market data tools use trading API (not data API)
- OR: Add `env` parameter to market data tools for consistency (though this may not be needed since market data is always "live" from trading API)

### 2. Error Message Consistency

**Issue:**
- Some tools return detailed errors with context
- Others return generic messages

**Examples:**
```python
# Good - detailed error
return ToolResult(
    success=False,
    symbol=symbol,
    error=f"Failed to get OHLCV history: {str(e)}"
)

# Could be better - generic error
return ToolResult(
    success=False,
    error="Order failed"
)
```

**Recommendation:**
- Standardize error messages to include context (symbol, timeframe, operation type)
- Use consistent error message format: `"Operation failed: {context}: {error}"`

### 3. Progress Feedback

**Issue:**
- Long-running operations (sync, gap fill) support `progress_callback`
- CLI doesn't always utilize progress callbacks
- Users see no feedback during long operations

**Current:**
```python
# Tool supports callback
def sync_symbols_tool(
    symbols: List[str],
    progress_callback: Optional[Callable] = None,
    ...
) -> ToolResult:
    store.sync(..., progress_callback=progress_callback)
```

**Recommendation:**
- Add progress indicators in CLI menus for long-running operations
- Use Rich library's `Progress` component for visual feedback
- Show per-symbol/timeframe progress during sync operations

### 4. Data Validation

**Issue:**
- Tools validate inputs, but error messages could be more specific
- Some edge cases not clearly handled

**Example:**
```python
# Current validation
start_dt, end_dt, range_error = _normalize_time_range_params(start, end)
if range_error:
    return ToolResult(success=False, error=range_error)
```

**Recommendation:**
- Add validation helpers with clearer error messages
- Include suggestions for fixing invalid inputs
- Validate symbol format (e.g., must end in "USDT" for simulator)

### 5. Tool Result Display

**Issue:**
- CLI uses `print_data_result()` which is good
- Large datasets (e.g., OHLCV queries) show summaries only
- No way to view full results or export data

**Current:**
```python
# Shows summary for large results
if count > 20:
    console.print(f"\n[dim]Showing summary ({count:,} candles total)[/]")
```

**Recommendation:**
- Add pagination for large result sets
- Add export options (CSV, JSON)
- Allow user to choose summary vs full display

### 6. Market Data vs Historical Data Distinction

**Issue:**
- Market data tools: Live/real-time via ExchangeManager
- Data tools: Historical via DuckDB
- Distinction not always clear in CLI menus

**Recommendation:**
- Add clear labels in CLI menus (e.g., "Live Market Data" vs "Historical Data")
- Document which tools are for live vs historical data
- Consider separate menu sections or icons to distinguish

## Specific Observations

### Data Tools (`src/tools/data_tools.py`)

**Strengths:**
- Comprehensive datetime normalization (`_normalize_datetime`, `_normalize_time_range_params`)
- Range validation (max 365 days to prevent bloat)
- Composite operations for common workflows
- Environment-aware with clear defaults
- Full bootstrap from launch with chunked syncing

**Issues:**
- `sync_full_from_launch_tool` is complex (200+ lines); consider splitting into smaller functions
- Some helper functions (`_sync_range_chunked`, `_build_extremes_metadata`) are private but could be useful as public utilities
- Extremes metadata persistence could be more modular

**Recommendation:**
- Split `sync_full_from_launch_tool` into:
  - `_get_launch_time()`
  - `_sync_ohlcv_from_launch()`
  - `_sync_funding_from_launch()`
  - `_sync_oi_from_launch()`
  - `_post_sync_cleanup()` (gaps, heal, extremes)

### Market Data Tools (`src/tools/market_data_tools.py`)

**Strengths:**
- Simple, focused wrappers
- Good error handling
- Consistent return types
- Comprehensive test suite

**Issues:**
- No environment parameter (always uses trading API)
- `run_market_data_tests_tool` is useful but could be more comprehensive (e.g., test rate limits, error handling)

**Recommendation:**
- Document that market data always uses trading API
- Expand test suite to include edge cases and error scenarios

### Exchange Integration (`src/tools/shared.py`)

**Strengths:**
- Lazy imports prevent circular dependencies
- Trading environment validation for agent/orchestrator use
- Clear separation between trading and data environments
- WebSocket management with cooldown to prevent spam

**Issues:**
- `_get_exchange_manager()` uses singleton pattern that could be clearer
- WebSocket management (`_ensure_websocket_running`) has hardcoded cooldown (60s) that could be configurable

**Recommendation:**
- Document singleton pattern and thread-safety considerations
- Make WebSocket cooldown configurable via config
- Add metrics for WebSocket connection attempts/failures

## Recommendations

### Short Term (Immediate)

1. **Add Progress Indicators**
   - Use Rich `Progress` component for long-running operations
   - Show per-symbol/timeframe progress during sync
   - Example: `[████████░░] 80% - Syncing BTCUSDT 1h...`

2. **Standardize Error Messages**
   - Include context (symbol, timeframe, operation) in all errors
   - Use consistent format: `"{operation} failed for {symbol}: {error}"`

3. **Add Pagination/Export**
   - Allow viewing full results for large datasets
   - Add export options (CSV, JSON) for query results
   - Add "View Full" option when showing summaries

4. **Document Environment Handling**
   - Clarify market data vs historical data distinction
   - Document why market data tools don't have `env` parameter
   - Add tooltips/help text in CLI menus

### Medium Term (Next Phase)

1. **Refactor Complex Tools**
   - Split `sync_full_from_launch_tool` into smaller functions
   - Extract reusable helpers (chunked sync, extremes metadata)

2. **Expand Test Coverage**
   - Add more comprehensive market data tests
   - Test error scenarios and edge cases
   - Add integration tests for tool chains

3. **Improve WebSocket Management**
   - Make cooldown configurable
   - Add connection health metrics
   - Better error recovery

4. **Add Batch Operations**
   - Batch sync for multiple symbols with progress
   - Parallel operations where safe (e.g., query multiple symbols)

### Long Term (Future Enhancements)

1. **Unified Environment Parameter**
   - Consider unified `env` parameter across all tools (if needed)
   - Document when/why environment matters

2. **Caching Layer**
   - Cache frequently accessed data (instrument info, prices)
   - Add cache invalidation strategies

3. **Async Operations**
   - Consider async for parallel data syncs
   - Async query operations for better responsiveness

4. **Data Quality Metrics**
   - Add data quality health checks
   - Track data freshness, completeness, gaps
   - Alert on data quality issues

## Overall Assessment

**Rating: 8.5/10**

The CLI wrapper is **well-structured** and follows excellent separation of concerns. The tools layer provides a clean API, and environment management is solid. The main areas for improvement are:

1. **Consistency**: Environment handling differences between market data and historical data tools
2. **User Experience**: Progress feedback and result display for large datasets
3. **Documentation**: Clearer distinction between live and historical data operations

The architecture supports the project's goals of:
- ✅ **Modularity**: Clear layer separation
- ✅ **Safety**: Environment validation and separation
- ✅ **Agent-Ready**: Tool registry and consistent interfaces
- ✅ **Maintainability**: Clean code organization

The four-leg API architecture is well-implemented, and the tools layer provides a solid foundation for both CLI and orchestrator/bot integration.

## Related Documentation

- [Code Examples Guide](../guides/CODE_EXAMPLES.md)
- [Data Architecture](../architecture/DATA_ARCHITECTURE.md)
- [Project Rules](../project/PROJECT_RULES.md)
- [Project Overview](../project/PROJECT_OVERVIEW.md)

