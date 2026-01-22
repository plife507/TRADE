# TRADE Project Status

**Last Updated**: 2026-01-22
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

---

## Validation Suite: 125 Plays

Comprehensive DSL validation with synthetic data integration:

| Tier | Plays | Coverage |
|------|-------|----------|
| T0: Smoke | 1 | Minimal smoke test |
| T1: Operators | 12 | >, <, >=, <=, ==, !=, between, near, in, cross |
| T2: Boolean | 4 | all, any, not, nested |
| T3: Arithmetic | 6 | add, subtract, multiply, divide, modulo |
| T4: Windows | 6 | holds_for, occurred_within, count_true |
| T5: Indicators | 43 | 27 single-output + 16 multi-output |
| T6: Structures | 7 | swing, trend, zone, fib, derived |
| T7: Price | 5 | close, open, high, low, last_price |
| T8: Multi-TF | 5 | high_tf filter, cross_tf confluence |
| T9: Risk | 11 | stop loss, take profit, sizing |
| T10: Position | 6 | long/short modes, exit modes |
| T11: Actions | 8 | entry/exit, case actions, alerts |
| T12: Combinations | 5 | mtf+indicators, structure+indicator |
| T13: Stress | 6 | many indicators, deep nesting |

**Key**: Validation plays auto-create synthetic data and use same code path as regular backtests.

---

## Directory Layout

```
src/
├── engine/        # Unified PlayEngine (backtest + live) - THE ENGINE
│   ├── play_engine.py      # Main engine (1,166 lines)
│   ├── factory.py          # PlayEngineFactory
│   └── signal/subloop.py   # Signal evaluation
├── indicators/    # 43 indicators
├── structures/    # 7 structure detectors
├── backtest/      # Backtest INFRASTRUCTURE (not an engine)
│   ├── runner.py           # Gate-based runner
│   ├── engine_factory.py   # create_engine_from_play()
│   ├── engine_data_prep.py # Data loading
│   ├── play/play.py        # Play class + SyntheticConfig
│   └── engine_*.py         # Various helpers
├── data/          # DuckDB historical data
├── cli/           # CLI interface
└── tools/         # CLI tools

tests/
├── functional/plays/   # 3 plays
├── validation/plays/   # 125 plays (14 tiers)
│   ├── tier0_smoke/
│   ├── tier1_operators/
│   ├── tier2_boolean/
│   ├── tier3_arithmetic/
│   ├── tier4_windows/
│   ├── tier5_indicators/
│   ├── tier6_structures/
│   ├── tier7_price_features/
│   ├── tier8_mtf/
│   ├── tier9_risk/
│   ├── tier10_position_policy/
│   ├── tier11_actions/
│   ├── tier12_combinations/
│   └── tier13_stress/
└── stress/plays/       # (empty - legacy)

docs/
├── PLAY_DSL_COOKBOOK.md   # DSL reference
├── SESSION_HANDOFF.md     # Session context
├── PROJECT_STATUS.md      # This file
└── TODO.md                # Active work tracking
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

## Current Focus

1. **Validation Suite Testing** - Run all 125 plays, fix failures
2. **Coverage Gaps** - Document any missing DSL features
3. **DSL Enhancement** - Phase 2 per roadmap

---

## Architecture Notes

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
