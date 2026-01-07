# TRADE

**Algorithmic trading system with AI-agent composable strategies.**

A production-grade backtesting and live trading platform where strategies are defined as composable YAML configurations, validated through a rigorous forge process, and executed with deterministic precision.

## Vision

Build a trading system where:
- **Strategies are data, not code** - YAML-defined Blocks compose into Plays and Systems
- **AI agents can generate and validate strategies** - The Forge provides guardrails for automated strategy creation
- **Every computation is traceable** - Hash chains verify determinism from data to trades
- **Math is pure, control is separate** - Components define calculations, engine orchestrates execution

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              THE FORGE                  │
                    │   Strategy Development & Validation     │
                    │                                         │
                    │     ┌─────────┐                        │
                    │     │ Blocks  │ (atomic conditions)     │
                    │     └────┬────┘                         │
                    │          ▼                              │
                    │     ┌─────────┐                         │
                    │     │  Plays  │ (complete strategies)   │
                    │     └────┬────┘                         │
                    │          ▼                              │
                    │     ┌─────────┐                         │
                    │     │ Systems │ (regime-based blending) │
                    │     └─────────┘                         │
                    └────────────────────┬────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │           BACKTEST ENGINE               │
                    │                                         │
                    │  ┌──────────┐  ┌──────────┐  ┌───────┐ │
                    │  │Indicators│  │Structures│  │ Rules │ │
                    │  │   (42)   │  │   (6)    │  │(Blocks│ │
                    │  └──────────┘  └──────────┘  │ DSL)  │ │
                    │       │            │         └───────┘ │
                    │       └────────────┼─────────────┘     │
                    │                    ▼                    │
                    │  ┌─────────────────────────────────┐   │
                    │  │      Simulated Exchange         │   │
                    │  │  (Pricing, Execution, Ledger)   │   │
                    │  └─────────────────────────────────┘   │
                    └────────────────────┬────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │              LIVE ENGINE                │
                    │         (Bybit Futures API)             │
                    └─────────────────────────────────────────┘
```

## Trading Hierarchy

Strategies compose hierarchically (3 levels):

| Level | Purpose | Example |
|-------|---------|---------|
| **Block** | Atomic reusable condition | `rsi_oversold`, `ema_pullback` |
| **Play** | Complete backtest-ready strategy | `V_001_ema_basic` |
| **System** | Multiple plays with regime blending | `btc_momentum_v1` |

```yaml
# Example Play (strategies/plays/T_001_ema_crossover.yml)
id: T_001_ema_crossover
version: "3.0.0"

features:
  - id: "ema_9"
    type: indicator
    indicator_type: ema
    params: { length: 9 }

  - id: "ema_21"
    type: indicator
    indicator_type: ema
    params: { length: 21 }

actions:
  - id: entry
    cases:
      - when:
          lhs: { feature_id: "ema_9" }
          op: cross_above
          rhs: { feature_id: "ema_21" }
        emit:
          - action: entry_long

  - id: exit
    cases:
      - when:
          lhs: { feature_id: "ema_9" }
          op: cross_below
          rhs: { feature_id: "ema_21" }
        emit:
          - action: exit_long
```

## Current Status (January 2026)

| Component | Status | Details |
|-----------|--------|---------|
| **Backtest Engine** | Production | 62-field metrics, deterministic execution |
| **Indicators** | 42 registered | EMA, RSI, MACD, Bollinger, Stochastic, ADX, etc. |
| **Structures** | 6 registered | Swing, Fibonacci, Zone, Trend, Rolling Window, Derived Zone |
| **DSL v3.0** | Complete | TradingView crossovers, window operators, anchor_tf |
| **The Forge** | Complete | Validation, audits, stress testing |
| **Trading Hierarchy** | Complete | Block/Play/System (3-level) |
| **Live Trading** | Ready | Bybit API, demo + live modes |
| **Bugs** | 0 open | 84 fixed, all tests passing |

## DSL Features

The Blocks DSL provides powerful operators for strategy logic:

### Crossover Operators (TradingView-aligned)
```yaml
# cross_above: prev <= rhs AND curr > rhs
- lhs: {feature_id: "ema_9"}
  op: cross_above
  rhs: {feature_id: "ema_21"}
```

### Window Operators with anchor_tf
```yaml
# Check condition held for 3 bars at 1h granularity
holds_for:
  bars: 3
  anchor_tf: "1h"
  expr:
    lhs: {feature_id: "rsi_14"}
    op: gt
    rhs: 50
```

### Duration-Based Windows
```yaml
# Time-based (wall clock) - always 1m granularity
holds_for_duration:
  duration: "30m"
  expr:
    lhs: {feature_id: "rsi_14"}
    op: gt
    rhs: 70
```

See [DSL Strategy Patterns](docs/guides/DSL_STRATEGY_PATTERNS.md) for 7 complete strategy examples.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/plife507/TRADE.git
cd TRADE
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Configure API keys
cp env.example api_keys.env
# Edit api_keys.env with your Bybit keys

# Run smoke tests (demo mode - safe)
python trade_cli.py --smoke forge    # Forge validation
python trade_cli.py --smoke full     # Full system test

# Interactive CLI
python trade_cli.py
```

## Key Commands

```bash
# Validate a Play
python trade_cli.py backtest play-normalize --play T_001_ema_crossover

# Run a backtest
python trade_cli.py backtest run --play T_001_ema_crossover --start 2025-01-01 --end 2025-01-31

# Batch validate all Plays
python trade_cli.py backtest play-normalize-batch --dir strategies/plays/_validation

# Run audit suite
python trade_cli.py backtest audit-toolkit
```

## Project Structure

```
TRADE/
├── src/
│   ├── backtest/           # Backtest engine
│   │   ├── engine.py       # Orchestrator
│   │   ├── sim/            # Simulated exchange
│   │   ├── incremental/    # O(1) structure detection
│   │   └── rules/          # Blocks DSL evaluation
│   ├── forge/              # Strategy forge
│   │   ├── validation/     # Play validation + synthetic data
│   │   ├── audits/         # Math parity, plumbing checks
│   │   ├── blocks/         # Atomic condition blocks
│   │   └── systems/        # System configs
│   ├── core/               # Live trading engine
│   ├── exchanges/          # Bybit API client
│   ├── tools/              # 84 registered tools (CLI/API)
│   └── data/               # DuckDB market data storage
├── strategies/
│   ├── blocks/             # Atomic reusable conditions
│   ├── plays/              # Strategy definitions
│   └── systems/            # Full system configs (multiple plays)
├── docs/
│   ├── architecture/       # Design documents
│   ├── guides/             # Usage guides
│   └── todos/              # Work tracking
└── trade_cli.py            # CLI entry point
```

## Philosophy

### ALL FORWARD, NO LEGACY
No backward compatibility. Delete old code, update all callers. Breaking changes are expected and welcomed.

### Pure Math
Components define calculations only. No side effects, no control flow about when to run. The engine orchestrates invocation.

### Fail Loud
Invalid configurations raise errors immediately. No silent defaults. If something is wrong, you'll know.

### Hash Everything
Every computation step produces a hash. Determinism is verified by comparing hash chains across runs.

## Documentation

| Topic | Location |
|-------|----------|
| AI Assistant Guidance | `CLAUDE.md` |
| DSL Strategy Patterns | `docs/guides/DSL_STRATEGY_PATTERNS.md` |
| Play Best Practices | `docs/guides/PLAY_BEST_PRACTICES.md` |
| Code Examples | `docs/guides/CODE_EXAMPLES.md` |
| Backtest Architecture | `src/backtest/CLAUDE.md` |
| Forge Architecture | `src/forge/CLAUDE.md` |
| Environment Variables | `env.example` |

## Programmatic API

```python
# Load and run a Play
from src.backtest import load_play, create_engine_from_play

play = load_play("T_001_ema_crossover")
engine = create_engine_from_play(play, data_loader=my_loader)
result = engine.run()
print(f"Net PnL: {result.metrics.net_pnl_usdt}")

# Use the Trading Hierarchy (Block -> Play -> System)
from src.forge import load_system

system = load_system("btc_momentum_v1")
for play_ref in system.get_enabled_plays():
    print(f"Play: {play_ref.play_id} (weight={play_ref.base_weight})")
    if play_ref.regime_weight:
        print(f"  Regime multiplier: {play_ref.regime_weight.multiplier}")

# Generate synthetic test data
from src.forge.validation import generate_synthetic_candles

candles = generate_synthetic_candles(
    symbol="BTCUSDT",
    timeframes=["1m", "5m", "1h"],
    bars_per_tf=1000,
    seed=42,
    pattern="trending",
)
```

## Trading Modes

| Mode | Endpoint | Funds | Use Case |
|------|----------|-------|----------|
| **Demo** | api-demo.bybit.com | Fake | Development, testing |
| **Live** | api.bybit.com | Real | Production trading |

Always start with Demo mode. The system defaults to safe settings.

## Roadmap

| Feature | Priority | Status |
|---------|----------|--------|
| BOS/CHoCH Detection | Medium | Planned |
| Complex Order Types | Medium | Planned |
| Multi-Symbol Backtests | Future | Planned |
| Live Engine WebSocket | Future | Stubs ready |

## License

MIT License - See LICENSE file
