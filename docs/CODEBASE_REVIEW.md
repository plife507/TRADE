# Codebase Review

## Review Findings

### Critical

- **Partial close market orders are not sent as reduce-only** in `src/tools/order_tools.py`, so a "close" can become a new opposite exposure if the exchange treats it as an opening market order.

```368:380:src/tools/order_tools.py
# Market order for partial close
if close_side == "Sell":
    result = exchange.market_sell(
        symbol=symbol,
        usd_amount=close_amount_usd,
    )
else:
    result = exchange.market_buy(
        symbol=symbol,
        usd_amount=close_amount_usd,
    )
# Mark as reduce_only for market orders
result.reduce_only = True
```

- **Price sanity guard is fail-open on data/exception paths** in `src/core/order_executor.py`. If ticker retrieval/parsing fails, order execution continues.

```699:717:src/core/order_executor.py
ticker = self.exchange.bybit.get_ticker(signal.symbol)
if not ticker:
    self.logger.warning("Price deviation check: no ticker data, allowing order")
    return None
...
if not last_price_str:
    self.logger.warning("Price deviation check: no lastPrice in ticker, allowing order")
    return None
```

```753:757:src/core/order_executor.py
except Exception as e:
    # Fail open: if we can't check, log warning but allow the order
    self.logger.warning(f"Price deviation check failed (allowing order): {e}")
```

### High

- **WebSocket health-check exceptions also fail-open** in `src/risk/global_risk.py`; exception path returns healthy/allowed, and bypasses threshold-based blocking behavior.

```275:280:src/risk/global_risk.py
except Exception as e:
    # If we can't check health, be conservative
    self.logger.warning(f"Could not check WebSocket health: {e}")
    if self._ws_unhealthy_since is None:
        self._ws_unhealthy_since = now
    return True, ""  # Allow within grace period
```

- **Startup position sync failures are non-fatal and swallowed** in `src/engine/runners/live_runner.py`. This can start live processing without reliable state reconciliation.

```452:487:src/engine/runners/live_runner.py
async def _sync_positions_on_startup(self) -> None:
    ...
    try:
        ...
        positions = em.get_all_positions()
        ...
    except Exception as e:
        logger.warning(f"Position sync warning (non-fatal): {e}")
```

- **Panic callbacks catch only a narrow exception set** in `src/core/safety.py`; other exception types from callbacks can escape during emergency handling flow.

```180:187:src/core/safety.py
for callback in callbacks_copy:
    try:
        callback(reason)
    except (RuntimeError, TypeError, ValueError) as e:
        # Log but continue executing other callbacks - panic must complete
        import logging
        logging.getLogger(__name__).error(f"Panic callback failed: {e}")
```

### Medium

- **Batch limit order path silently drops invalid qty orders** in `src/core/exchange_orders_manage.py` (`continue` with no error object), so caller can receive fewer results than submitted orders without structured failure detail.

```371:379:src/core/exchange_orders_manage.py
batch_orders = []
for order in orders:
    symbol = order["symbol"]
    price = inst.round_price(manager, symbol, order["price"])
    qty = inst.calculate_qty(manager, symbol, order["usd_amount"], price)

    if qty <= 0:
        continue
```

- **`calculate_qty()` relies on `price <= 0` check after fetch** in `src/core/exchange_instruments.py`; if `get_price()` yields invalid non-numeric/`None`, behavior depends on runtime exception type rather than explicit validation path.

```131:136:src/core/exchange_instruments.py
if price is None:
    price = manager.get_price(symbol)

if price <= 0:
    raise ValueError(f"Invalid price for {symbol}: {price}")
```

## Testing and Coverage Gaps

- `tests/` has extensive YAML validation scenarios, but no Python unit/integration tests were found under `tests/**/*.py` in this workspace snapshot.
- CI currently runs smoke jobs in `.github/workflows/smoke.yml`, but not targeted concurrency/fail-closed unit tests for the critical paths above.

```41:56:.github/workflows/smoke.yml
- name: Run data smoke tests
  run: |
    python trade_cli.py --smoke data
...
- name: Run Phase 6 backtest smoke tests
  run: |
    python trade_cli.py --smoke full
```

## Assumptions and Open Questions

- Assumed hedge/position mode behavior does not implicitly enforce reduction for all partial-close market orders; if exchange account mode enforces this elsewhere, severity of finding #1 may reduce.
- Assumed fail-closed is intended across guards (comments and naming suggest that intent in several modules).

No code changes were made in the repo during this review.
