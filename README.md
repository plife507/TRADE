# TRADE

**Algorithmic Trading Bot with AI-Agent Composable Strategies**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Bybit API](https://img.shields.io/badge/Exchange-Bybit-orange.svg)](https://www.bybit.com/)

A production-grade backtesting and live trading platform where strategies are defined as **composable YAML configurations**, validated through a rigorous forge process, and executed with deterministic precision.

---

## Why TRADE?

| Problem | TRADE Solution |
|---------|----------------|
| Strategies are scattered code | **Strategies are YAML data** - version controlled, diffable, AI-generatable |
| Hard to compose strategies | **3-level hierarchy** - Blocks → Plays → Systems |
| Backtests don't match live | **Hash-verified determinism** - every computation traceable |
| Indicator sprawl | **Single registry** - 43 indicators, 6 structures, all validated |
| Complex DSL learning curve | **TradingView-aligned operators** - `cross_above`, `cross_below` work as expected |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         THE FORGE                               │
│              Strategy Development & Validation                  │
│                                                                 │
│    Blocks (atomic)  →  Plays (complete)  →  Systems (blended)  │
│    rsi_oversold        T_001_ema_cross      btc_momentum_v1    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKTEST ENGINE                            │
│                                                                 │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│   │ Indicators │  │ Structures │  │ Blocks DSL │               │
│   │    (43)    │  │    (6)     │  │  (v3.0.0)  │               │
│   └────────────┘  └────────────┘  └────────────┘               │
│          │              │               │                       │
│          └──────────────┴───────────────┘                       │
│                         │                                       │
│   ┌─────────────────────▼─────────────────────┐                │
│   │          Simulated Exchange               │                │
│   │    Pricing · Execution · Margin · Ledger  │                │
│   └───────────────────────────────────────────┘                │
│                                                                 │
│   62-field metrics · O(1) hot loop · Multi-timeframe           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LIVE ENGINE                               │
│                   Bybit Futures (USDT-M)                        │
│              Demo Mode (safe) · Live Mode (real)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# Clone
git clone https://github.com/plife507/TRADE.git
cd TRADE

# Setup
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt

# Configure (optional - needed for live trading)
cp env.example api_keys.env
# Edit api_keys.env with your Bybit API keys

# Run
python trade_cli.py          # Interactive CLI
```

---

## Example Play

Strategies are defined in YAML. Here's a complete EMA crossover strategy:

```yaml
# strategies/plays/T_001_ema_crossover.yml
id: T_001_ema_crossover
version: "3.0.0"

symbol: BTCUSDT
tf: "15m"

features:
  - id: ema_9
    indicator: ema
    params: { length: 9 }

  - id: ema_21
    indicator: ema
    params: { length: 21 }

actions:
  entry_long:
    all:
      - [ema_9, cross_above, ema_21]

  exit_long:
    all:
      - [ema_9, cross_below, ema_21]

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 10.0
```

Run it:
```bash
python trade_cli.py backtest run --play T_001_ema_crossover --start 2025-01-01 --end 2025-01-31
```

---

## Trading Hierarchy

Strategies compose in 3 levels:

| Level | Purpose | Example |
|:-----:|---------|---------|
| **Block** | Atomic reusable condition | `rsi_oversold`, `ema_pullback`, `volume_spike` |
| **Play** | Complete backtest-ready strategy | `T_001_ema_crossover`, `V_100_swing_bounce` |
| **System** | Multiple plays with regime blending | `btc_momentum_v1`, `multi_asset_trend` |

```
Block: rsi_14 < 30           # Reusable condition
       ↓
Play:  Entry when RSI < 30   # Full strategy with risk management
       AND EMA cross
       ↓
System: Run Play A in        # Multiple plays, weighted by regime
        trending markets,
        Play B in ranging
```

---

## DSL Features

The Blocks DSL provides powerful, readable operators:

### Comparison & Crossover
```yaml
# TradingView-aligned crossovers
- [ema_9, cross_above, ema_21]      # prev <= rhs AND curr > rhs
- [ema_9, cross_below, ema_21]      # prev >= rhs AND curr < rhs

# Standard comparisons
- [rsi_14, gt, 70]                   # Greater than
- [close, near_pct, support, 1.5]   # Within 1.5% of level
```

### Window Operators
```yaml
# Condition held for N bars
holds_for:
  bars: 3
  anchor_tf: "1h"                    # Scale to hourly bars
  expr: [rsi_14, gt, 50]

# Event occurred within window
occurred_within:
  bars: 10
  expr: [ema_9, cross_above, ema_21]
```

### Structure Access
```yaml
# Market structure detection (O(1) per bar)
- [{feature_id: swing, field: high_level}, gt, 0]
- [{feature_id: trend, field: direction}, eq, 1]
- [{feature_id: fib_zones, field: any_active}, eq, true]
```

---

## Current Status

| Component | Status | Details |
|-----------|:------:|---------|
| Backtest Engine | ✅ | 62-field metrics, deterministic execution |
| Indicators | ✅ | 43 registered (EMA, RSI, MACD, Bollinger, etc.) |
| Structures | ✅ | 6 types (Swing, Trend, Fibonacci, Zone, Rolling, Derived) |
| DSL v3.0.0 | ✅ | 11 operators, 6 window operators, frozen spec |
| The Forge | ✅ | Validation, audits, 320+ stress tests passing |
| Live Trading | ✅ | Bybit API, demo + live modes |
| Open Bugs | ✅ | 0 open (all fixed) |

---

## Key Commands

```bash
# Backtest
python trade_cli.py backtest run --play T_001 --start 2025-01-01 --end 2025-01-31

# Validate a Play
python trade_cli.py backtest play-normalize --play T_001_ema_crossover

# Batch validate
python trade_cli.py backtest play-normalize-batch --dir strategies/plays/

# Run audits
python trade_cli.py backtest audit-toolkit

# Smoke tests
python trade_cli.py --smoke full     # Full system test (demo mode)
python trade_cli.py --smoke data     # Data pipeline only
```

---

## Project Structure

```
TRADE/
├── src/
│   ├── backtest/           # Backtest engine (sim exchange, metrics)
│   ├── forge/              # Strategy validation & development
│   ├── core/               # Live trading engine
│   ├── exchanges/          # Bybit API client
│   ├── tools/              # 84 CLI/API tools
│   └── data/               # DuckDB market data
├── strategies/
│   ├── blocks/             # Atomic reusable conditions
│   ├── plays/              # Complete strategies
│   └── systems/            # Multi-play configurations
├── tests/
│   ├── validation/         # DSL validation plays (V_100+)
│   └── stress/             # Structure stress tests (320+ plays)
├── docs/
│   ├── guides/             # Usage guides & patterns
│   ├── architecture/       # Design documents
│   └── specs/              # DSL specification
├── CLAUDE.md               # AI assistant guidance
└── trade_cli.py            # CLI entry point
```

---

## Programmatic API

```python
from src.backtest import load_play, create_engine_from_play

# Load and run
play = load_play("T_001_ema_crossover")
engine = create_engine_from_play(play)
result = engine.run()

# Access metrics
print(f"Net PnL: ${result.metrics.net_pnl_usdt:,.2f}")
print(f"Win Rate: {result.metrics.win_rate:.1%}")
print(f"Sharpe: {result.metrics.sharpe_ratio:.2f}")
print(f"Max DD: {result.metrics.max_drawdown_pct:.1%}")
```

---

## Philosophy

### All Forward, No Legacy
No backward compatibility. Delete old code, update all callers. Breaking changes are welcomed.

### Strategies Are Data
YAML-defined, version controlled, AI-generatable. No strategy logic in Python.

### Fail Loud
Invalid configurations raise errors immediately. No silent defaults.

### Hash Everything
Every computation produces a hash. Determinism is verified by comparing hash chains.

---

## Documentation

| Topic | Location |
|-------|----------|
| Engine Concepts | [`docs/guides/BACKTEST_ENGINE_CONCEPTS.md`](docs/guides/BACKTEST_ENGINE_CONCEPTS.md) |
| DSL Cookbook | [`docs/specs/PLAY_DSL_COOKBOOK.md`](docs/specs/PLAY_DSL_COOKBOOK.md) |
| Strategy Patterns | [`docs/guides/DSL_STRATEGY_PATTERNS.md`](docs/guides/DSL_STRATEGY_PATTERNS.md) |
| Code Examples | [`docs/guides/CODE_EXAMPLES.md`](docs/guides/CODE_EXAMPLES.md) |
| AI Guidance | [`CLAUDE.md`](CLAUDE.md) |

---

## Trading Modes

| Mode | Endpoint | Funds | Use Case |
|------|----------|:-----:|----------|
| **Demo** | api-demo.bybit.com | Fake | Development, testing |
| **Live** | api.bybit.com | Real | Production |

Always start with Demo mode. The system defaults to safe settings.

---

## License

MIT License - See [LICENSE](LICENSE) file
