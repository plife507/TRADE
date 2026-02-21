# Dead Code Audit — Live/Demo Trading Path

**Date**: 2026-02-20
**Scope**: `src/core/`, `src/data/`, `src/engine/`, `src/cli/` (excludes `src/backtest/`)
**Trigger**: Event queue spam bug revealed speculative code pattern

## Summary

44 findings, ~800 lines of dead code. All HIGH confidence (zero callers confirmed via grep).

**Resolution (2026-02-20)**: 471 lines deleted (commit 9fba245). ~200 lines kept for P2 (Live Trading). See resolution status on each cluster below.

Pattern: interfaces built speculatively for future features but never connected to any CLI command, menu, or runner.

---

## Cluster 1: RiskManager RR Utilities (~140 lines) — PARTIALLY KEPT FOR P2

Entire risk/reward position sizing feature built but never wired. Kept for P2 live trading integration.

| Method | File | Status |
|--------|------|--------|
| `calculate_stop_loss_price()` | `src/core/risk_manager.py` | **KEPT** — P2 position sizing |
| `calculate_take_profit_price()` | `src/core/risk_manager.py` | **KEPT** — P2 position sizing |
| `calculate_trade_levels()` | `src/core/risk_manager.py` | **KEPT** — P2 position sizing |
| `get_max_position_size()` | `src/core/risk_manager.py` | **KEPT** — P2 risk limits |
| `get_global_risk_snapshot()` | `src/core/risk_manager.py` | **KEPT** — P2 risk monitoring |
| `get_global_risk_summary()` | `src/core/risk_manager.py` | **KEPT** — P2 risk monitoring |
| `start_websocket_if_needed()` | `src/core/risk_manager.py` | **DELETED** (9fba245) |
| `_reset_daily_if_needed()` | `src/core/risk_manager.py` | **KEPT** — actively called by `check()` and `get_status()` |
| `open_position_with_rr()` | `src/core/exchange_manager.py` | **KEPT** — P2 bracket orders |

---

## Cluster 2: MarketData Convenience Methods (~100 lines) — DELETED

All 10 methods deleted in 9fba245. Zero callers, speculative agent/CLI surface.

| Method | File | Status |
|--------|------|--------|
| `get_latest_candle()` | `src/data/market_data.py` | **DELETED** |
| `get_market_snapshot()` | `src/data/market_data.py` | **DELETED** |
| `get_multi_tf_ohlcv()` | `src/data/market_data.py` | **DELETED** |
| `get_multiple_timeframes()` | `src/data/market_data.py` | **DELETED** |
| `get_source_stats()` | `src/data/market_data.py` | **DELETED** |
| `get_realtime_status()` | `src/data/market_data.py` | **DELETED** |
| `clear_cache()` | `src/data/market_data.py` | **DELETED** |
| `set_prefer_websocket()` | `src/data/market_data.py` | **DELETED** |
| `get_data_source()` | `src/data/market_data.py` | **DELETED** |
| `get_demo_market_data()` | `src/data/market_data.py` | **DELETED** |

---

## Cluster 3: OrderExecutor Pending Order API (~80 lines) — KEPT FOR P2

Query/wait API kept for P2 live order management. Internal `PendingOrder` tracking is actively used.

| Method | File | Status |
|--------|------|--------|
| `get_pending_order()` | `src/core/order_executor.py` | **KEPT** — P2 order management |
| `get_all_pending_orders()` | `src/core/order_executor.py` | **KEPT** — P2 order management |
| `wait_for_fill()` | `src/core/order_executor.py` | **KEPT** — P2 synchronous confirmation |
| `execute_with_leverage()` | `src/core/order_executor.py` | **KEPT** — P2 leverage-aware execution |

---

## Cluster 4: ExchangeManager Methods (~80 lines) — PARTIALLY KEPT FOR P2

| Method | File | Status |
|--------|------|--------|
| `get_account_value()` | `src/core/exchange_manager.py` | **DELETED** (9fba245) |
| `get_bid_ask()` | `src/core/exchange_manager.py` | **DELETED** (9fba245) |
| `set_position_mode()` | `src/core/exchange_manager.py` | **DELETED** (9fba245) |
| `add_margin()` | `src/core/exchange_manager.py` | **DELETED** (9fba245) |
| `reconcile_orphaned_orders()` | `src/core/exchange_manager.py` | **KEPT** — P2 crash recovery |

---

## Cluster 5: RealtimeState Callbacks & Queries (~50 lines) — DELETED

All 16 methods deleted in 9fba245. Callback architecture was over-engineered — WebSocket events flow directly to handlers.

| Method | File | Status |
|--------|------|--------|
| `on_trade()` | `src/data/realtime_state.py` | **DELETED** |
| `on_orderbook_update()` | `src/data/realtime_state.py` | **DELETED** |
| `on_ticker_update()` | `src/data/realtime_state.py` | **DELETED** |
| `on_wallet_update()` | `src/data/realtime_state.py` | **DELETED** |
| `on_account_metrics_update()` | `src/data/realtime_state.py` | **DELETED** |
| `get_recent_trades()` | `src/data/realtime_state.py` | **DELETED** |
| `get_recent_executions()` | `src/data/realtime_state.py` | **DELETED** |
| `get_all_wallets()` | `src/data/realtime_state.py` | **DELETED** |
| `is_orderbook_stale()` | `src/data/realtime_state.py` | **DELETED** |
| `is_position_stale()` | `src/data/realtime_state.py` | **DELETED** |
| `get_order()` | `src/data/realtime_state.py` | **DELETED** |
| `get_orderbook()` | `src/data/realtime_state.py` | **DELETED** |
| `clear_market_data()` | `src/data/realtime_state.py` | **DELETED** |
| `clear_account_data()` | `src/data/realtime_state.py` | **DELETED** |
| `clear_callbacks()` | `src/data/realtime_state.py` | **DELETED** |
| `clear_bar_buffers()` | `src/data/realtime_state.py` | **DELETED** |

---

## Cluster 6: PositionManager Methods (~50 lines) — PARTIALLY KEPT FOR P2

| Method | File | Status |
|--------|------|--------|
| `set_prefer_websocket()` | `src/core/position_manager.py` | **DELETED** (9fba245) |
| `get_performance_summary()` | `src/core/position_manager.py` | **KEPT** — P2 dashboard/reporting |
| `get_trade_history()` | `src/core/position_manager.py` | **KEPT** — P2 dashboard/reporting |

---

## Cluster 7: SubscriptionConfig Factories (~45 lines) — DELETED

All 3 factory classmethods deleted in 9fba245. Only default constructor was ever used.

| Method | File | Status |
|--------|------|--------|
| `market_data_only()` | `src/data/realtime_bootstrap.py` | **DELETED** |
| `full()` | `src/data/realtime_bootstrap.py` | **DELETED** |
| `demo_safe()` | `src/data/realtime_bootstrap.py` | **DELETED** |

---

## Cluster 8: Application & Misc (~30 lines) — DELETED

| Item | File | Status |
|------|------|--------|
| `get_websocket_health()` | `src/core/application.py` | **DELETED** (9fba245) |
| `on_shutdown()` | `src/core/application.py` | **DELETED** (9fba245) |
| `ExchangeManager._trading_mode` | `src/core/exchange_manager.py` | **DELETED** (9fba245) — set but never read |
| `ConnectionStatus.last_message_at` | `src/data/realtime_models.py` | **DELETED** (9fba245) — always None |
| `Application._lock` (class-level) | `src/core/application.py` | **DELETED** (9fba245) — module-level `_app_lock` used instead |

---

## Resolution Summary

| Category | Lines | Commit |
|----------|-------|--------|
| Deleted (truly dead) | ~471 | 9fba245 |
| Kept for P2 (live trading) | ~200 | — |
| Previously fixed (event queue) | ~30 | d578351 |

### P2 Candidates Retained

These form a coherent live position management feature set for P2 (Live Trading Integration):

- **RR Position Sizing**: `calculate_trade_levels()` orchestrates SL/TP calculation + position sizing
- **Bracket Orders**: `open_position_with_rr()` wires SL/TP to exchange calls
- **Order Management**: `wait_for_fill()`, `execute_with_leverage()`, pending order query API
- **Crash Recovery**: `reconcile_orphaned_orders()` finds conditional orders for closed positions
- **Risk Monitoring**: `get_global_risk_snapshot()`, `get_global_risk_summary()`, `get_max_position_size()`
- **Dashboard**: `get_performance_summary()`, `get_trade_history()`

### Validation

`python trade_cli.py validate full` — **ALL 15 GATES PASSED** after cleanup (1044s).
