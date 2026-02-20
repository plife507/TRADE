# Dead Code Audit — Live/Demo Trading Path

**Date**: 2026-02-20
**Scope**: `src/core/`, `src/data/`, `src/engine/`, `src/cli/` (excludes `src/backtest/`)
**Trigger**: Event queue spam bug revealed speculative code pattern

## Summary

44 findings, ~800 lines of dead code. All HIGH confidence (zero callers confirmed via grep).

Pattern: interfaces built speculatively for future features but never connected to any CLI command, menu, or runner.

---

## Cluster 1: RiskManager RR Utilities (~140 lines)

Entire risk/reward position sizing feature built but never wired.

| Method | File | Line | Lines |
|--------|------|------|-------|
| `calculate_stop_loss_price()` | `src/core/risk_manager.py` | 570 | ~30 |
| `calculate_take_profit_price()` | `src/core/risk_manager.py` | 598 | ~30 |
| `calculate_trade_levels()` | `src/core/risk_manager.py` | 629 | ~70 |
| `get_max_position_size()` | `src/core/risk_manager.py` | 493 | ~15 |
| `get_global_risk_snapshot()` | `src/core/risk_manager.py` | 545 | ~10 |
| `get_global_risk_summary()` | `src/core/risk_manager.py` | 556 | ~10 |
| `start_websocket_if_needed()` | `src/core/risk_manager.py` | 105 | ~15 |
| `_reset_daily_if_needed()` | `src/core/risk_manager.py` | 141 | stub (`pass`) |
| `open_position_with_rr()` | `src/core/exchange_manager.py` | 413 | ~60 |

**Note**: The RR calculations may be useful for P2 (Live Trading Integration). Consider keeping them if P2 will use them, or delete and rebuild when needed.

---

## Cluster 2: MarketData Convenience Methods (~100 lines)

Multi-TF and snapshot methods built for a future agent/CLI surface.

| Method | File | Line |
|--------|------|------|
| `get_latest_candle()` | `src/data/market_data.py` | 445 |
| `get_market_snapshot()` | `src/data/market_data.py` | 597 |
| `get_multi_tf_ohlcv()` | `src/data/market_data.py` | 632 |
| `get_multiple_timeframes()` | `src/data/market_data.py` | 662 |
| `get_source_stats()` | `src/data/market_data.py` | 706 |
| `get_realtime_status()` | `src/data/market_data.py` | 718 |
| `clear_cache()` | `src/data/market_data.py` | 690 |
| `set_prefer_websocket()` | `src/data/market_data.py` | 208 |
| `get_data_source()` | `src/data/market_data.py` | 204 |
| `get_demo_market_data()` | `src/data/market_data.py` | 775 |

---

## Cluster 3: OrderExecutor Pending Order API (~80 lines)

Internal tracking works (for idempotency) but the query/wait API is never called.

| Method | File | Line |
|--------|------|------|
| `get_pending_order()` | `src/core/order_executor.py` | 576 |
| `get_all_pending_orders()` | `src/core/order_executor.py` | 581 |
| `wait_for_fill()` | `src/core/order_executor.py` | 621 |
| `execute_with_leverage()` | `src/core/order_executor.py` | 550 |

---

## Cluster 4: ExchangeManager Methods (~80 lines)

| Method | File | Line |
|--------|------|------|
| `get_account_value()` | `src/core/exchange_manager.py` | 313 |
| `get_bid_ask()` | `src/core/exchange_manager.py` | 275 |
| `set_position_mode()` | `src/core/exchange_manager.py` | 347 |
| `add_margin()` | `src/core/exchange_manager.py` | 351 |
| `reconcile_orphaned_orders()` | `src/core/exchange_manager.py` | 481 |

---

## Cluster 5: RealtimeState Callbacks & Queries (~50 lines)

Callback registration methods with zero subscribers:

| Method | File | Line |
|--------|------|------|
| `on_trade()` | `src/data/realtime_state.py` | 494 |
| `on_orderbook_update()` | `src/data/realtime_state.py` | 269 |
| `on_ticker_update()` | `src/data/realtime_state.py` | 214 |
| `on_wallet_update()` | `src/data/realtime_state.py` | 627 |
| `on_account_metrics_update()` | `src/data/realtime_state.py` | 657 |

Query methods with zero callers:

| Method | File | Line |
|--------|------|------|
| `get_recent_trades()` | `src/data/realtime_state.py` | 487 |
| `get_recent_executions()` | `src/data/realtime_state.py` | 583 |
| `get_all_wallets()` | `src/data/realtime_state.py` | 613 |
| `is_orderbook_stale()` | `src/data/realtime_state.py` | 260 |
| `is_position_stale()` | `src/data/realtime_state.py` | 524 |
| `get_order()` | `src/data/realtime_state.py` | 553 |
| `get_orderbook()` | `src/data/realtime_state.py` | 255 |
| `clear_market_data()` | `src/data/realtime_state.py` | 814 |
| `clear_account_data()` | `src/data/realtime_state.py` | 822 |
| `clear_callbacks()` | `src/data/realtime_state.py` | 781 |
| `clear_bar_buffers()` | `src/data/realtime_state.py` | 460 |

---

## Cluster 6: PositionManager Methods (~50 lines)

| Method | File | Line |
|--------|------|------|
| `set_prefer_websocket()` | `src/core/position_manager.py` | 189 |
| `get_performance_summary()` | `src/core/position_manager.py` | 465 |
| `get_trade_history()` | `src/core/position_manager.py` | 457 |

---

## Cluster 7: SubscriptionConfig Factories (~45 lines)

| Method | File | Line |
|--------|------|------|
| `market_data_only()` | `src/data/realtime_bootstrap.py` | 109 |
| `full()` | `src/data/realtime_bootstrap.py` | 123 |
| `demo_safe()` | `src/data/realtime_bootstrap.py` | 137 |

---

## Cluster 8: Application & Misc (~30 lines)

| Method | File | Line |
|--------|------|------|
| `get_websocket_health()` | `src/core/application.py` | 515 |
| `on_shutdown()` | `src/core/application.py` | 584 |

Dead attributes:

| Attribute | File | Line | Issue |
|-----------|------|------|-------|
| `ExchangeManager._trading_mode` | `src/core/exchange_manager.py` | 213 | Set but never read |
| `ConnectionStatus.last_message_at` | `src/data/realtime_models.py` | 1038 | Always `None` |
| `Application._lock` (class-level) | `src/core/application.py` | 83 | Module-level `_app_lock` used instead |

---

## Cleanup Strategy

### Delete Now (no future use expected)
- Event queue system (DONE - removed in d578351)
- Stub methods (`_reset_daily_if_needed`)
- Dead attributes (`_trading_mode`, `last_message_at`, `Application._lock`)
- SubscriptionConfig factory classmethods
- MarketData convenience methods (rebuild when needed)
- RealtimeState unused callbacks and granular clear methods

### Evaluate for P2 (Live Trading Integration)
- RiskManager RR utilities (may be needed for live position sizing)
- OrderExecutor `wait_for_fill()` (may be needed for live order management)
- ExchangeManager `reconcile_orphaned_orders()` (may be needed for live safety)
- PositionManager `get_performance_summary()` (may be needed for dashboard)

### Already Fixed
- RealtimeState event queue (removed 2026-02-20, commit d578351)
