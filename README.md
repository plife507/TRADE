# TRADE - Bybit Trading Bot

A modular, production-ready Bybit futures trading bot with complete UTA support, comprehensive order types, position management, and risk controls.

**Philosophy**: Safety first. Modular always. Tools as the API surface.

## Current Status (January 2026)

**Backtest Engine Complete**:
- 62-field BacktestMetrics (tail risk, leverage, MAE/MFE, benchmark alpha)
- 42 indicators in string-based registry (single source of truth)
- IdeaCard YAML-based strategy specification
- 21 validation IdeaCards for comprehensive testing

**In Progress**: Market Structure Features (Phase 5)
- Swing/pivot/trend detection
- Rule evaluation engine

See `docs/project/PROJECT_OVERVIEW.md` for the full roadmap.

## Quick Start

```bash
# Install
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt

# Configure
cp env.example api_keys.env
# Edit api_keys.env with your Bybit API keys

# Run
python trade_cli.py            # Interactive CLI
python trade_cli.py --smoke full  # Smoke test (demo mode)
```

## Architecture Overview

```
TRADE/
├── src/
│   ├── backtest/          # Backtest engine (USDT-only, isolated margin)
│   │   ├── engine.py      # Orchestrator
│   │   ├── sim/           # Simulated exchange (pricing, execution, ledger)
│   │   ├── runtime/       # Snapshot, FeedStore, TFContext
│   │   └── features/      # FeatureSpec, indicators
│   ├── core/              # Live trading (exchange manager, risk, orders)
│   ├── exchanges/         # Bybit API client
│   ├── tools/             # CLI/API surface (primary interface)
│   ├── data/              # Market data, DuckDB storage
│   └── utils/             # Logging, rate limiting, helpers
├── configs/idea_cards/    # Strategy definitions (YAML)
├── docs/                  # Architecture, guides, TODOs
└── trade_cli.py           # CLI entry point
```

## Key Features

| Domain | Capabilities |
|--------|-------------|
| **Live Trading** | Market/Limit/Stop orders, TP/SL, trailing stops, batch operations |
| **Backtest** | Simulated exchange, multi-timeframe, 42 indicators, 62 metrics |
| **Data** | DuckDB storage, OHLCV/funding/OI sync, gap filling |
| **Safety** | Demo mode default, panic button, risk limits, mode validation |

## Trading Modes

| Mode | API | Description |
|------|-----|-------------|
| Demo | api-demo.bybit.com | Fake funds (safe testing) |
| Live | api.bybit.com | Real funds (production) |

Start with Demo mode. Test thoroughly before switching to Live.

## Documentation

| Topic | Location |
|-------|----------|
| **Detailed guidance** | `CLAUDE.md` |
| **Code examples** | `docs/guides/CODE_EXAMPLES.md` |
| **Project roadmap** | `docs/project/PROJECT_OVERVIEW.md` |
| **Architecture docs** | `docs/architecture/` |
| **Environment vars** | `env.example` |

## License

MIT License - See LICENSE file
