# Visualization Module

TradingView-style backtest visualization. FastAPI backend + React frontend.

## Quick Start

```bash
# Start visualization server
python trade_cli.py viz serve

# Start on custom port
python trade_cli.py viz serve --port 3000

# Development with auto-reload
python trade_cli.py viz serve --reload

# Development mode (separate terminals)
# Terminal 1: Start API server
python trade_cli.py viz serve --no-browser

# Terminal 2: Start React dev server
cd ui && npm run dev
```

Then visit `http://localhost:8765` to view backtest results.

## Architecture

```
src/viz/           # Python backend (FastAPI)
├── server.py      # FastAPI entry point
├── api/           # REST endpoints
│   ├── runs.py    # /api/runs - list/get runs
│   ├── charts.py  # /api/charts - OHLCV + indicators
│   ├── trades.py  # /api/trades - trade markers
│   ├── equity.py  # /api/equity - equity curve
│   └── metrics.py # /api/metrics - stats
└── data/          # Data loaders
    ├── artifact_loader.py    # Run discovery
    ├── ohlcv_loader.py       # OHLCV from snapshots/DuckDB
    ├── indicator_loader.py   # Indicator overlays/panes
    ├── trades_loader.py      # Trade markers
    └── equity_loader.py      # Equity curve

ui/                # React frontend
├── src/
│   ├── components/
│   │   ├── charts/
│   │   │   ├── CandlestickChart.tsx   # Main price chart
│   │   │   ├── IndicatorPane.tsx      # RSI/MACD panes
│   │   │   └── EquityCurve.tsx        # Equity + drawdown
│   │   ├── metrics/
│   │   │   └── MetricsDashboard.tsx   # Stat cards
│   │   └── layout/
│   │       ├── Sidebar.tsx            # Run list
│   │       └── Header.tsx             # Run info
│   └── api/
│       └── client.ts                  # API types + fetch
├── package.json
├── vite.config.ts
└── tailwind.config.js
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/runs` | GET | List all backtest runs |
| `/api/runs/{run_id}` | GET | Run metadata + metrics |
| `/api/charts/{run_id}/ohlcv` | GET | Candlestick data |
| `/api/charts/{run_id}/volume` | GET | Volume bars |
| `/api/charts/{run_id}/indicators` | GET | Indicator overlays + panes |
| `/api/trades/{run_id}/markers` | GET | Entry/exit markers |
| `/api/equity/{run_id}` | GET | Equity curve + drawdown |
| `/api/metrics/{run_id}/summary` | GET | Stats for cards |
| `/api/health` | GET | Health check |

## Features

### Charts
- **Candlestick chart**: TradingView-style with volume overlay
- **Trade markers**: Entry (arrow up/down) and exit (circle) markers
- **Indicator overlays**: EMA, SMA lines on price chart
- **Indicator panes**: RSI, MACD in separate synchronized panes
- **Equity curve**: Equity line with drawdown area

### Non-Repaint Guarantee
- **Closed candles only**: All data uses `ts_close` timestamps
- **Forward-fill preserved**: MTF/HTF values shown as they were at each exec bar
- **Warmup indicator**: Shows warmup bar count in footer
- **Badge**: "Closed candles only" + "Non-repaint" badges on chart

### Theme
Dark mode (TradingView default):
- Background: `#131722`
- Candles: Green `#26a69a` / Red `#ef5350`
- Grid: `#363c4e`
- Text: `#d1d4dc`

## Data Sources

- **Artifacts**: `backtests/{category}/{play_id}/{symbol}/{run_id}/`
  - `result.json` - Run metadata
  - `trades.parquet` - Trade records
  - `equity.parquet` - Equity curve
  - `snapshots/exec_frame.parquet` - OHLCV + indicators
- **DuckDB fallback**: Via `src/data/historical_data_store.py`

## Critical Rules

- **Read-Only**: This module only reads from artifact files. No writes.
- **No Live Data**: Visualization is for historical backtest results only.
- **Non-Repaint**: Only show closed candle data.

## Production Build

```bash
# Build React frontend
cd ui && npm run build

# The build output goes to ui/dist/
# FastAPI serves it automatically when present
```

## Development

```bash
# Install UI dependencies
cd ui && npm install

# Start dev server (with hot reload)
npm run dev

# Type check
npm run type-check

# Lint
npm run lint
```
