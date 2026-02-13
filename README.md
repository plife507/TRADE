# TRADE

A unified backtest and live trading engine for Bybit perpetual futures, driven by a declarative YAML-based strategy DSL.

## What It Does

Define trading strategies as YAML "Plays" using indicators, market structure detectors, and a rich condition DSL. Run them identically in backtest (historical DuckDB data) or live (Bybit WebSocket + REST). One engine, two modes, zero code changes between them.

```yaml
# Example: Bollinger Band mean reversion scalper
version: "3.0.0"
name: "bb_rsi_scalper"
symbol: "BTCUSDT"

timeframes:
  low_tf: "5m"
  med_tf: "1h"
  high_tf: "D"
  exec: "low_tf"

features:
  rsi_14: { indicator: rsi, params: { length: 14 } }
  bbands_20: { indicator: bbands, params: { length: 20, std: 2.0 } }
  ema_50_1h: { indicator: ema, timeframe: med_tf, params: { length: 50 } }

actions:
  entry_long:
    conditions:
      - ["close", "<", "bbands_20.lower"]
      - ["rsi_14", "<", 35]
      - ["close", ">", "ema_50_1h"]
    sizing: { model: percent_equity, risk_pct: 2.0 }
    sl_pct: 2.0
    tp_pct: 4.0
```

## Architecture

```
src/
  engine/          PlayEngine - unified backtest/live engine (1600 lines)
  indicators/      44 incremental O(1) indicators
  structures/      7 market structure detectors
  backtest/        Backtest infrastructure (sim exchange, data prep, DSL parser)
  data/            DuckDB historical data store
  exchanges/       Bybit REST + WebSocket clients
  cli/             CLI subcommands
  tools/           CLI/API tool layer
  risk/            Risk management + global risk view

plays/             277 strategy definitions (YAML)
config/            System defaults
scripts/           Suite runners and generators
```

### Key Components

| Component | Description |
|-----------|-------------|
| **PlayEngine** | Single engine for both backtest and live. Processes bars, evaluates DSL conditions, manages positions. |
| **Play DSL** | YAML strategy definitions with conditions, operators, arithmetic, window operators, and multi-timeframe support. |
| **SimulatedExchange** | Tick-accurate backtest execution with 1-minute quote data, slippage, and fee modeling. |
| **DuckDB Store** | Historical OHLCV storage with gap detection, auto-repair, and multi-timeframe support. |
| **Incremental Indicators** | All 44 indicators compute in O(1) per bar. No lookback recomputation. |
| **Structure Detectors** | Swing points, trend detection, market structure (BOS/CHoCH), Fibonacci retracements, derived zones, rolling windows. |

### Live Trading Safety

| Feature | Description |
|---------|-------------|
| **Pre-live Gate** | Auto-validates connectivity, balance, and conflicts before live launch. |
| **Fat Finger Guard** | Rejects orders with >5% price deviation from last known price. |
| **Drawdown Circuit Breaker** | Halts trading when drawdown exceeds configured threshold. |
| **DCP (Disconnect Cancel All)** | Exchange cancels all orders if connection drops for >10s. |
| **Daily Loss Tracker** | Tracks realized daily PnL, survives restarts via exchange seeding. |
| **Panic Button** | `panic --confirm` closes all positions and cancels all orders instantly. |
| **Trade Journal** | JSONL log of every signal, fill, and error for post-session review. |
| **Notifications** | Telegram and Discord alerts for signals, fills, and errors. |

## Indicators (44)

**Moving Averages (12):** EMA, SMA, WMA, DEMA, TEMA, TRIMA, ZLMA, KAMA, ALMA, LINREG, Anchored VWAP, VWAP

**Oscillators (10):** RSI, CCI, Williams %R, CMO, MFI, Ultimate Oscillator, Stochastic, StochRSI, Fisher Transform, TSI

**Trend (8):** ADX, Aroon, Supertrend, Parabolic SAR, Vortex, Directional Movement, TRIX, PPO

**Volatility (6):** ATR, NATR, Bollinger Bands, Keltner Channels, Donchian Channels, Squeeze

**Volume (4):** OBV, CMF, KVO, Volume SMA

**Momentum (3):** MACD, ROC, Momentum

**Price (1):** OHLC4/Midprice

## Market Structure Detectors (7)

| Detector | Output Fields | Description |
|----------|--------------|-------------|
| **Swing** | `high_level`, `low_level`, `high_idx`, `low_idx` | Swing high/low pivot detection |
| **Trend** | `direction`, `strength`, `phase` | Trend direction from swing sequence |
| **Market Structure** | `bos_this_bar`, `choch_this_bar`, `bos_direction` | Break of Structure / Change of Character |
| **Fibonacci** | `level[0.236]` through `level[0.786]` | Trend-wave anchored retracements |
| **Derived Zone** | `zone[N].state`, `any_touched`, `first_active_*` | K-slot supply/demand zone model |
| **Rolling Window** | `min`, `max`, `range` | Rolling min/max/range |
| **Zone** | `upper`, `lower`, `state` | Basic zone detection |

## Play DSL

### Operators

| Category | Operators |
|----------|-----------|
| **Comparison** | `>`, `<`, `>=`, `<=`, `==`, `!=` |
| **Crossover** | `cross_above`, `cross_below` |
| **Range** | `between` |
| **Proximity** | `near_pct`, `near_abs` |
| **Boolean** | `all` (implicit), `any`, `not` |
| **Arithmetic** | `+`, `-`, `*`, `/`, `%` |
| **Window** | `holds_for`, `occurred_within`, `count_true` |
| **Control Flow** | `cases`/`when`/`emit`/`else` |
| **State** | `variables`, `metadata` |

### Multi-Timeframe

Three data feeds with an execution pointer:

```yaml
timeframes:
  low_tf: "5m"      # Fast: entries, execution
  med_tf: "1h"      # Medium: structure, bias
  high_tf: "D"      # Slow: trend, context
  exec: "low_tf"    # Which feed to step on
```

Higher timeframe indicator values are forward-filled to the execution timeframe automatically.

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
cp env.example api_keys.env
# Edit api_keys.env with your Bybit API keys
```

### 2. Sync Data

```bash
python trade_cli.py data sync --symbol BTCUSDT --period 3M
```

### 3. Run a Backtest

```bash
python trade_cli.py backtest run --play scalper_btc_production --fix-gaps --start 2025-10-01 --end 2026-01-01
```

### 4. Run Live (Demo)

```bash
python trade_cli.py play run --play scalper_btc_production --mode demo
```

### 5. Run Live (Real Money)

```bash
python trade_cli.py play run --play scalper_btc_production --mode live --confirm
```

## CLI Reference

```bash
# Data
python trade_cli.py data sync --symbol BTCUSDT --period 3M
python trade_cli.py data sync --symbol ETHUSDT --timeframes 15m,1h,D --start 2025-01-01 --end 2025-06-01

# Backtest
python trade_cli.py backtest run --play <name> --fix-gaps
python trade_cli.py backtest run --play <name> --synthetic --synthetic-bars 500
python trade_cli.py backtest run --play <name> --start 2025-10-01 --end 2026-01-01

# Live Trading
python trade_cli.py play run --play <name> --mode demo          # Paper trading
python trade_cli.py play run --play <name> --mode live --confirm # Real money
python trade_cli.py play status [--json]                         # Running instances
python trade_cli.py play stop --play <name> [--close-positions]  # Stop with position handling
python trade_cli.py play watch [--play <name>]                   # Live dashboard (2s refresh)
python trade_cli.py play logs --play <name> [--follow]           # Stream trade journal
python trade_cli.py play pause --play <name>                     # Pause signal evaluation
python trade_cli.py play resume --play <name>                    # Resume signal evaluation

# Account & Positions
python trade_cli.py account balance [--json]       # Account balance
python trade_cli.py account exposure [--json]      # Total exposure
python trade_cli.py position list [--json]         # Open positions
python trade_cli.py position close SYMBOL          # Close a position
python trade_cli.py panic --confirm                # Emergency close all

# Validation
python trade_cli.py validate quick                 # Core plays + audits (~30s)
python trade_cli.py validate standard              # + synthetic suites (~2min)
python trade_cli.py validate full                  # Everything (~10min)
python trade_cli.py validate pre-live --play <name> # Pre-live readiness check

# Suite Runners
python scripts/run_full_suite.py                                    # 170-play synthetic
python scripts/run_full_suite.py --real --start 2025-10-01 --end 2026-01-01  # Real data
```

## Verification

### Backtest Suites (170 Plays)

The engine is validated by 170 plays across 5 suites, tested on both synthetic patterns and real market data:

| Suite | Plays | Coverage |
|-------|-------|----------|
| `plays/indicator_suite/` | 84 | All 44 indicators in long/short/crossover configurations |
| `plays/pattern_suite/` | 34 | 34 synthetic market patterns (trending, ranging, volatile, reversals, etc.) |
| `plays/operator_suite/` | 25 | All DSL operators (comparison, crossover, arithmetic, window, control flow) |
| `plays/structure_suite/` | 14 | All 7 structure types with dependency chains |
| `plays/complexity_ladder/` | 13 | Progressive complexity from 0% to 100% DSL coverage |

Results: 170/170 pass on synthetic data, 170/170 pass on real data (BTC, ETH, SOL, ARB, OP).

Additionally, a 60-play Wyckoff real-data verification suite validates 41/43 indicators, 7/7 structures, and 19/24 DSL operators across 4 symbols (BTC, ETH, SOL, LTC) with 23 math checks per play.

### Demo Readiness Stress Test (84 Checks)

`scripts/test_demo_readiness.py` exercises the REAL engine code through the REAL Bybit demo API. 84 checks across 12 phases:

| Phase | What | Checks |
|-------|------|--------|
| 1 | Play Loading & Config | 5 |
| 2 | REST Connectivity | 7 |
| 3 | DataProvider + Indicator Warmup | 7 |
| 4 | WebSocket Data Feed | 8 |
| 5 | Order Execution (market orders) | 12 |
| 6 | Error Edge Cases | 6 |
| 7 | Full EngineManager Integration | 8 |
| 8 | Journal & State Persistence | 5 |
| 9 | Safety & Circuit Breakers | 6 |
| 10 | Multi-TF Data Routing | 5 |
| 11 | Advanced Order Lifecycle | 5 |
| 12 | Runner State Machine & Limits | 10 |

```bash
python scripts/test_demo_readiness.py                # Full run (~5min)
python scripts/test_demo_readiness.py --skip-orders  # Read-only mode (~3min)
```

## Exchange Support

- **Bybit** perpetual futures (USDT-margined)
- Four-leg API architecture: separate keys for live trading, demo trading, live data, demo data
- WebSocket streaming for real-time execution
- Isolated margin, one-way position mode

## Tech Stack

- Python 3.12+
- DuckDB (historical data)
- Bybit REST + WebSocket (pybit SDK)
- NumPy, Pandas (data processing)
- Rich (CLI output)
- Pyright (static type checking, 0 errors / 0 warnings)

## Configuration

System defaults are in `config/defaults.yml`. Plays override any default. Key defaults:

| Setting | Default |
|---------|---------|
| Taker fee | 5.5 bps |
| Maker fee | 2.0 bps |
| Slippage | 2.0 bps |
| Max leverage | 1.0x |
| Risk per trade | 1.0% |
| Max drawdown | 20% |
| Min trade size | $10 USDT |

## Documentation

| Document | Description |
|----------|-------------|
| `docs/PLAY_DSL_REFERENCE.md` | Unified DSL syntax reference (frozen semantics) |
| `docs/TODO.md` | Project status and gate tracking |
| `docs/SESSION_HANDOFF.md` | Session handoff with quick commands |
| `docs/plans/LIVE_READINESS_GLOBAL.md` | Live readiness gate overview (G14-G17) |
| `config/defaults.yml` | All system defaults with sources |
| `CLAUDE.md` | Development conventions |

## License

MIT
