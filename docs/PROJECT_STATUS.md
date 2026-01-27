# TRADE Project Status

**Last Updated**: 2026-01-25
**Branch**: feature/unified-engine

---

## What This Is

A crypto trading bot with backtesting and live trading capabilities.

---

## Migration Status: COMPLETE

The unified PlayEngine migration is **done**:

| Component | Status | Location |
|-----------|--------|----------|
| PlayEngine | Complete | `src/engine/play_engine.py` (1,166 lines) |
| Factory | Complete | `src/backtest/engine_factory.py` |
| Mode Factory | Complete | `src/engine/factory.py` |
| BacktestEngine | Deleted | `src/backtest/engine.py` (re-exports only) |
| Signal Subloop | Complete | `src/engine/signal/subloop.py` |
| Unified Indicators | Complete | `src/indicators/provider.py` |

---

## Indicator System: COMPLETE

11 incremental O(1) indicators for live trading:

| Indicator | Status |
|-----------|--------|
| ema, sma, rsi, atr | ✓ Original |
| macd, bbands | ✓ Original |
| stoch, adx, supertrend | ✓ Added 2026-01-25 |
| cci, willr | ✓ Added 2026-01-25 |

**Registry-driven**: Adding a new indicator = 1 file change

---

## Validation Suite: 19 Plays

Core validation plays for engine and DSL testing:

| Tier | Plays | Coverage |
|------|-------|----------|
| tier00_smoke | 1 | Engine startup validation |
| tier06_structures | 12 | swing, trend, zone, fib, derived, rolling |
| tier07_indicators | 6 | ema, sma, rsi, atr, macd, bbands |

**Key**: Validation plays use synthetic data and same code path as regular backtests.

---

## Directory Layout

```
src/
├── engine/        # Unified PlayEngine (backtest + live) - THE ENGINE
│   ├── play_engine.py      # Main engine (1,166 lines)
│   ├── factory.py          # PlayEngineFactory
│   └── signal/subloop.py   # Signal evaluation
├── indicators/    # 43 indicators, 11 incremental
│   ├── provider.py         # IndicatorProvider protocol
│   └── incremental.py      # O(1) indicator implementations
├── structures/    # 7 structure detectors
├── backtest/      # Backtest INFRASTRUCTURE (not an engine)
│   ├── runner.py           # Gate-based runner
│   ├── engine_factory.py   # create_engine_from_play()
│   ├── indicator_registry.py # Single source of truth
│   ├── play/play.py        # Play class + SyntheticConfig
│   └── engine_*.py         # Various helpers
├── data/          # DuckDB historical data
├── cli/           # CLI interface
└── tools/         # CLI tools

tests/validation/plays/   # 19 plays (3 active tiers)

docs/
├── PLAY_DSL_COOKBOOK.md   # DSL reference
├── SESSION_HANDOFF.md     # Session context
├── PROJECT_STATUS.md      # This file
└── TODO.md                # **Single source of truth for open work**
```

---

## Quick Commands

```bash
# Smoke test
python trade_cli.py --smoke full

# Run backtest (real data)
python trade_cli.py backtest run --play <name> --fix-gaps

# Run backtest (synthetic)
python trade_cli.py backtest run --play <name> --synthetic --synthetic-pattern trend_up_clean

# Indicator audit
python trade_cli.py backtest audit-toolkit

# Load validation play (Python)
from src.backtest.play import load_play
play = load_play('V_T5_001_ema')  # Auto-finds in tier subdirectories
```

---

## Architecture Patterns

### PlayEngine Pattern
```python
from src.backtest import create_engine_from_play, run_engine_with_play

engine = create_engine_from_play(play, bars, config)
result = run_engine_with_play(engine, play, evaluator)
```

### Mode Factory Pattern
```python
from src.engine import PlayEngineFactory

engine = PlayEngineFactory.create(play, mode="backtest")
```

### Validation Play Pattern
```python
from src.backtest.play import load_play
from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play

play = load_play('V_T5_001_ema')  # Has synthetic config
engine = create_engine_from_play(play)  # Auto-creates synthetic provider
result = run_engine_with_play(engine, play)  # Same code path as regular backtests
```

---

## Open Work

See **`docs/TODO.md`** for all open work items.
