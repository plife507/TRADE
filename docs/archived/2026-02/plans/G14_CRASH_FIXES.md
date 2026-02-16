# G14: Crash Fixes & Safety Blockers

**Entry**: G13 complete, `feature/unified-engine` branch current
**Theme**: Fix things that crash or lose money. No new features.
**Exit**: `python trade_cli.py validate quick` passes + smoke tests pass

## Tasks

- [x] G14.1: BUG -- `store.query_ohlcv()` -> `store.get_ohlcv()` (`src/engine/adapters/live.py:741`)
- [x] G14.2: BUG -- `kline_data.end_time` -> calculated from `start_time + tf_minutes()` (`src/engine/runners/live_runner.py:444`)
- [x] G14.3: Fat finger / price sanity guard -- `_check_price_deviation()` in `OrderExecutor` (`src/core/order_executor.py`)
- [x] G14.4: Activate DCP -- in `ExchangeManager.__init__()` + `panic_close_all()` (`src/core/exchange_manager.py`, `src/core/safety.py`)
- [x] G14.5: Seed DailyLossTracker on startup -- in `LiveRunner.start()` (`src/engine/runners/live_runner.py`)

## Verification

```bash
python -c "from src.engine.adapters.live import LiveDataProvider; print('BUG-1: OK')"
python -c "from src.data.realtime_models import KlineData; assert not hasattr(KlineData, 'end_time'); print('BUG-2: OK')"
python trade_cli.py validate quick
python trade_cli.py --smoke full
```
