# TRADE

**Algorithmic trading system with AI-agent composable strategies.**

A production-grade backtesting and live trading platform where strategies are defined as composable YAML configurations, validated through a rigorous forge process, and executed with deterministic precision.

## Vision

Build a trading system where:
- **Strategies are data, not code** - YAML-defined Plays compose into Playbooks and Systems
- **AI agents can generate and validate strategies** - The Forge provides guardrails for automated strategy creation
- **Every computation is traceable** - Hash chains verify determinism from data to trades
- **Math is pure, control is separate** - Components define calculations, engine orchestrates execution

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              THE FORGE                  │
                    │   Strategy Development & Validation     │
                    │                                         │
                    │  ┌─────────┐  ┌──────────┐  ┌────────┐ │
                    │  │ Setups  │──│  Plays   │──│Playbook│ │
                    │  └─────────┘  └──────────┘  └────────┘ │
                    │       │            │             │      │
                    │       └────────────┼─────────────┘      │
                    │                    ▼                    │
                    │             ┌──────────┐                │
                    │             │  System  │                │
                    │             └──────────┘                │
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

Strategies compose hierarchically:

| Level | Purpose | Example |
|-------|---------|---------|
| **Setup** | Reusable market condition | `rsi_oversold`, `ema_pullback` |
| **Play** | Complete tradeable strategy | `T_001_ema_crossover` |
| **Playbook** | Collection of Plays | `trend_following` |
| **System** | Full trading configuration | `btc_momentum_v1` |

```yaml
# Example Play (configs/plays/T_001_ema_crossover.yml)
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

blocks:
  - id: entry
    cases:
      - when:
          all:
            - lhs: { feature_id: "ema_9" }
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
| **The Forge** | Complete | Validation, audits, stress testing |
| **Trading Hierarchy** | Complete | Setup/Play/Playbook/System |
| **Live Trading** | Ready | Bybit API, demo + live modes |
| **Bugs** | 0 open | 79 fixed, all tests passing |

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
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation

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
│   │   ├── setups/         # Reusable setups
│   │   └── playbooks/      # Playbook runner
│   ├── core/               # Live trading engine
│   ├── exchanges/          # Bybit API client
│   ├── tools/              # 84 registered tools (CLI/API)
│   └── data/               # DuckDB market data storage
├── configs/
│   ├── plays/              # Strategy definitions
│   ├── setups/             # Reusable conditions
│   ├── playbooks/          # Play collections
│   └── systems/            # Full system configs
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

# Use the Trading Hierarchy
from src.forge import load_system, load_playbook

system = load_system("btc_momentum_v1")
for pb_ref in system.get_enabled_playbooks():
    playbook = load_playbook(pb_ref.playbook_id)
    for entry in playbook.get_enabled_plays():
        print(f"Running: {entry.play_id}")

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
