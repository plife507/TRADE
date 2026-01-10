# TRADE

**Algorithmic Trading Bot for Bybit Futures with AI-Agent Composable Strategies**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Bybit API](https://img.shields.io/badge/Exchange-Bybit-orange.svg)](https://www.bybit.com/)

A production-grade backtesting and live trading platform for **USDT-margined perpetual futures**. Strategies are defined as composable YAML configurations with built-in leverage controls, liquidation modeling, and comprehensive risk metrics.

---

## Development Tiers & Gated Progress

TRADE enforces a **gated progression** from idea to live trading. Each tier has validation gates that must pass before advancing.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEVELOPMENT PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  TIER 1: FORGE              TIER 2: BACKTEST           TIER 3: VALIDATE    │
│  ─────────────              ────────────────           ─────────────────    │
│  Create Play YAML    ──►    Run historical     ──►    Pass metric gates    │
│  Define indicators          simulation                 Sharpe > 1.0         │
│  Set risk model             62-field metrics           Max DD < 20%         │
│  Configure account          Full margin sim            Win rate > 40%       │
│                                                                             │
│         │                         │                          │              │
│         ▼                         ▼                          ▼              │
│    ┌─────────┐              ┌─────────┐               ┌─────────┐          │
│    │  GATE   │              │  GATE   │               │  GATE   │          │
│    │Normalize│              │ Metrics │               │ Quality │          │
│    └─────────┘              └─────────┘               └─────────┘          │
│         │                         │                          │              │
│         ▼                         ▼                          ▼              │
│                                                                             │
│  TIER 4: DEMO               TIER 5: SHADOW             TIER 6: LIVE        │
│  ───────────                ──────────────             ───────────         │
│  Paper trade on      ──►    Live signals,      ──►    Real capital         │
│  Bybit testnet              no execution              Full automation      │
│  Fake funds                 Compare to sim            Risk controls        │
│  Real market data           Validate fills            Position limits      │
│                                                                             │
│         │                         │                          │              │
│         ▼                         ▼                          ▼              │
│    ┌─────────┐              ┌─────────┐               ┌─────────┐          │
│    │  GATE   │              │  GATE   │               │  GATE   │          │
│    │ 7-day   │              │ Parity  │               │ Profit  │          │
│    │ stable  │              │ Check   │               │ Target  │          │
│    └─────────┘              └─────────┘               └─────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tier Details

| Tier | Environment | Capital | Purpose | Gate Criteria |
|:----:|-------------|---------|---------|---------------|
| **1** | Local | None | Create & normalize Play | YAML validates, indicators exist |
| **2** | Local | Simulated | Run backtest | Completes without errors |
| **3** | Local | Simulated | Quality check | Meets metric thresholds |
| **4** | Bybit Demo | Fake | Paper trading | 7+ days stable, no crashes |
| **5** | Bybit Live | None | Signal validation | Signals match backtest |
| **6** | Bybit Live | Real | Production | Profitable, within risk limits |

### Gate Commands

```bash
# Tier 1: Normalize (validate YAML structure)
python trade_cli.py backtest play-normalize --play T_001_ema_crossover

# Tier 2: Backtest (run simulation)
python trade_cli.py backtest run --play T_001 --start 2025-01-01 --end 2025-06-30

# Tier 3: Quality gate (check metrics)
python trade_cli.py backtest audit-toolkit --play T_001

# Tier 4: Demo trading
python trade_cli.py live run --play T_001 --mode demo

# Tier 5: Shadow mode (signals only, no execution)
python trade_cli.py live run --play T_001 --mode shadow

# Tier 6: Live trading
python trade_cli.py live run --play T_001 --mode live
```

---

## Demo & Live Trading

### Trading Modes

| Mode | API Endpoint | Funds | Execution | Use Case |
|------|--------------|:-----:|:---------:|----------|
| **Demo** | api-demo.bybit.com | Fake | Real orders | Paper trading, testing |
| **Shadow** | api.bybit.com | None | Signals only | Validate before going live |
| **Live** | api.bybit.com | Real | Real orders | Production trading |

### Demo Mode (Tier 4)

Demo mode connects to Bybit's testnet with fake funds:

```bash
# Start demo trading
python trade_cli.py live run --play T_001_ema_crossover --mode demo

# Monitor positions
python trade_cli.py live positions --mode demo

# View trade history
python trade_cli.py live history --mode demo --days 7
```

**What you get:**
- Real market data (live prices)
- Fake capital ($10,000 USDT default)
- Actual order execution on testnet
- Full logging and metrics

**Gate to pass:** 7 days of stable operation, no crashes, reasonable PnL

### Shadow Mode (Tier 5)

Shadow mode generates signals but doesn't execute:

```bash
# Run shadow mode
python trade_cli.py live run --play T_001_ema_crossover --mode shadow

# Compare signals to backtest
python trade_cli.py live shadow-report --play T_001 --days 7
```

**What you get:**
- Live signals logged with timestamps
- No actual trades placed
- Comparison to what backtest would have done
- Fill price estimates vs. actual market

**Gate to pass:** Signal parity with backtest expectations (< 5% deviation)

### Live Mode (Tier 6)

Live mode trades with real capital:

```bash
# Start live trading (requires confirmation)
python trade_cli.py live run --play T_001_ema_crossover --mode live

# Set position limits
python trade_cli.py live run --play T_001 --mode live \
  --max-position-usdt 1000 \
  --daily-loss-limit 100

# Emergency stop
python trade_cli.py live panic --close-all
```

**Safety controls:**
- Maximum position size limits
- Daily loss limits (auto-pause)
- Drawdown circuit breaker
- Panic button (close all positions)

### Environment Configuration

```bash
# .env or api_keys.env
BYBIT_USE_DEMO=true              # true = demo, false = live
BYBIT_DEMO_API_KEY=xxx           # Demo API key
BYBIT_DEMO_API_SECRET=xxx        # Demo API secret
BYBIT_LIVE_API_KEY=xxx           # Live API key (Tier 6 only)
BYBIT_LIVE_API_SECRET=xxx        # Live API secret
```

---

## Why TRADE?

| Problem | TRADE Solution |
|---------|----------------|
| No clear path to production | **6-tier gated progression** - earn your way to live |
| Strategies are scattered code | **Strategies are YAML data** - version controlled, diffable |
| Backtests ignore leverage reality | **Full margin simulation** - liquidation, maintenance margin |
| Risk metrics are an afterthought | **62-field metrics** - VaR, CVaR, Sharpe, tail risk |
| Demo/live behavior mismatch | **Shadow mode validation** - compare signals before risking capital |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         THE FORGE                               │
│              Strategy Development & Validation                  │
│                                                                 │
│    Blocks (atomic)  →  Plays (complete)  →  Systems (blended)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKTEST ENGINE                            │
│                                                                 │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│   │ Indicators │  │ Structures │  │ Actions DSL│               │
│   │    (43)    │  │    (6)     │  │  (v3.0.0)  │               │
│   └────────────┘  └────────────┘  └────────────┘               │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              Simulated Exchange                         │  │
│   │  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐ │  │
│   │  │ Pricing  │ │Execution │ │ Margin &   │ │ Funding  │ │  │
│   │  │  Model   │ │  Model   │ │Liquidation │ │  Rates   │ │  │
│   │  └──────────┘ └──────────┘ └────────────┘ └──────────┘ │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│   62-field metrics · O(1) hot loop · Multi-timeframe           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LIVE ENGINE                               │
│                   Bybit Futures (USDT-M)                        │
│            Demo (Tier 4) · Shadow (Tier 5) · Live (Tier 6)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Leverage & Margin Model

TRADE simulates **isolated margin** mode with realistic leverage mechanics:

### Account Configuration

```yaml
account:
  starting_equity_usdt: 10000
  max_leverage: 10                    # Hard cap on leverage
  margin_mode: isolated_usdt          # Only isolated supported
  maintenance_margin_rate: 0.005      # 0.5% MMR (Bybit default)
  fee_model:
    taker_bps: 5.5                    # 0.055% taker fee
    maker_bps: 2.0                    # 0.02% maker fee
  slippage_bps: 5                     # 0.05% slippage model
```

### How Margin Works

| Concept | Description |
|---------|-------------|
| **Initial Margin** | `position_value / leverage` - capital locked when opening |
| **Maintenance Margin** | `position_value × MMR` - minimum equity to avoid liquidation |
| **Equity** | `cash + unrealized_pnl` - real-time account value |
| **Liquidation** | Triggered when `equity <= maintenance_margin` |

### Leverage Example

```
Account: $10,000 USDT
Leverage: 10x
Position: 1 BTC @ $50,000

Position Value:  $50,000
Initial Margin:  $5,000 (50,000 / 10)
Maint. Margin:   $250   (50,000 × 0.5%)
Free Margin:     $5,000 (10,000 - 5,000)

Liquidation Price (Long): ~$45,250 (when equity = maint. margin)
```

### Funding Rate Simulation

Perpetual futures have 8-hour funding payments:

```yaml
# Tracked in backtest metrics
total_funding_paid_usdt: 127.50      # Paid when long in positive funding
total_funding_received_usdt: 84.20   # Received when short in positive funding
net_funding_usdt: -43.30             # Net impact on PnL
```

---

## Risk Management

### Position Sizing Models

```yaml
risk:
  sizing:
    model: percent_equity    # Size based on equity percentage
    value: 5.0               # Risk 5% of equity per trade
    max_leverage: 10         # Never exceed 10x
```

| Model | Description |
|-------|-------------|
| `percent_equity` | Position = `equity × value%` |
| `fixed_usdt` | Fixed size regardless of equity |
| `risk_based` | Size based on stop distance: `risk_amount / stop_distance` |

### Stop Loss Types

```yaml
risk:
  stop_loss:
    type: atr_multiple       # Dynamic stop based on ATR
    value: 2.0               # 2× ATR distance
    atr_feature_id: atr_14   # Reference to ATR indicator
    buffer_pct: 0.1          # 0.1% buffer beyond level
```

| Type | Description |
|------|-------------|
| `percent` | Fixed percentage from entry |
| `atr_multiple` | Dynamic: `entry ± (ATR × multiplier)` |
| `structure` | Based on swing high/low levels |
| `fixed_points` | Absolute price distance |

### Take Profit Types

```yaml
risk:
  take_profit:
    type: rr_ratio           # Risk:Reward based
    value: 2.0               # 2:1 reward to risk
```

| Type | Description |
|------|-------------|
| `rr_ratio` | Target = `entry + (stop_distance × ratio)` |
| `percent` | Fixed percentage from entry |
| `atr_multiple` | Dynamic: `entry ± (ATR × multiplier)` |
| `fixed_points` | Absolute price distance |

### Exit Modes

```yaml
exit_mode: first_hit  # Which exit triggers position close
```

| Mode | Behavior |
|------|----------|
| `sl_tp_only` | Only SL/TP close positions - pure mechanical |
| `signal` | Only signal-based exits - SL/TP are emergency only |
| `first_hit` | Whichever triggers first wins |

---

## Backtest Metrics (62 Fields)

### Core Performance

| Metric | Description |
|--------|-------------|
| `net_profit` | Final equity - starting equity |
| `net_return_pct` | Percentage return |
| `benchmark_return_pct` | Buy-and-hold return (same period) |
| `alpha_pct` | Strategy return - benchmark return |

### Risk-Adjusted Returns

| Metric | Description |
|--------|-------------|
| `sharpe` | Risk-adjusted return (annualized) |
| `sortino` | Downside-only risk adjustment |
| `calmar` | Return / Max Drawdown |
| `omega_ratio` | Probability-weighted gain/loss ratio |

### Drawdown Analysis

| Metric | Description |
|--------|-------------|
| `max_drawdown_pct` | Worst peak-to-trough decline |
| `max_drawdown_duration_bars` | Longest time underwater |
| `ulcer_index` | Pain-adjusted drawdown measure |
| `recovery_factor` | Net profit / max drawdown |

### Tail Risk (Critical for Leverage)

| Metric | Description |
|--------|-------------|
| `var_95_pct` | 95% Value at Risk - worst 5% daily loss |
| `cvar_95_pct` | Expected Shortfall - avg loss beyond VaR |
| `skewness` | Return asymmetry (negative = blowup risk) |
| `kurtosis` | Fat tails measure (>3 = extreme moves) |

### Leverage-Specific Metrics

| Metric | Description |
|--------|-------------|
| `avg_leverage_used` | Average actual leverage during backtest |
| `max_gross_exposure_pct` | Peak position_value / equity |
| `closest_liquidation_pct` | How close you got to liquidation |
| `margin_calls` | Number of margin warning events |
| `min_margin_ratio` | Lowest margin ratio observed |

### Trade Quality (MAE/MFE)

| Metric | Description |
|--------|-------------|
| `mae_avg_pct` | Avg Maximum Adverse Excursion - worst drawdown per trade |
| `mfe_avg_pct` | Avg Maximum Favorable Excursion - best unrealized profit |
| `payoff_ratio` | Average win / average loss |
| `expectancy_usdt` | Expected $ per trade |

---

## Example Play (Complete)

```yaml
# strategies/plays/T_001_ema_crossover.yml
version: "3.0.0"
id: T_001_ema_crossover

symbol: BTCUSDT
tf: "15m"

# Account & Leverage
account:
  starting_equity_usdt: 10000
  max_leverage: 10
  margin_mode: isolated_usdt
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0
  slippage_bps: 5

# Indicators
features:
  ema_9:
    indicator: ema
    params: { length: 9 }
  ema_21:
    indicator: ema
    params: { length: 21 }
  atr_14:
    indicator: atr
    params: { length: 14 }

# Entry/Exit Logic (Actions DSL)
actions:
  entry_long:
    all:
      - [ema_9, cross_above, ema_21]

  exit_long:
    all:
      - [ema_9, cross_below, ema_21]

# Risk Model
risk:
  stop_loss:
    type: atr_multiple
    value: 2.0
    atr_feature_id: atr_14

  take_profit:
    type: rr_ratio
    value: 2.0

  sizing:
    model: percent_equity
    value: 5.0
    max_leverage: 10

exit_mode: first_hit
```

### Running Through the Tiers

```bash
# Tier 1: Validate YAML
python trade_cli.py backtest play-normalize --play T_001_ema_crossover
# ✅ Play normalized successfully

# Tier 2: Run backtest
python trade_cli.py backtest run --play T_001_ema_crossover \
  --start 2025-01-01 --end 2025-06-30
# ✅ 127 trades, Sharpe: 1.42, Max DD: 12.3%

# Tier 3: Quality gate
python trade_cli.py backtest audit-toolkit --play T_001_ema_crossover
# ✅ All quality gates passed

# Tier 4: Demo trading (7 days minimum)
python trade_cli.py live run --play T_001_ema_crossover --mode demo
# ✅ 7 days stable, +2.3% return

# Tier 5: Shadow mode
python trade_cli.py live run --play T_001_ema_crossover --mode shadow
# ✅ Signal parity: 97% match with backtest

# Tier 6: Live trading
python trade_cli.py live run --play T_001_ema_crossover --mode live \
  --max-position-usdt 1000
# 🚀 Live trading active
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

# Configure (optional - for live trading)
cp env.example api_keys.env
# Edit api_keys.env with your Bybit API keys

# Run
python trade_cli.py          # Interactive CLI
```

---

## DSL Features

The Actions DSL provides TradingView-aligned operators:

### Comparison & Crossover
```yaml
- [ema_9, cross_above, ema_21]      # prev <= rhs AND curr > rhs
- [ema_9, cross_below, ema_21]      # prev >= rhs AND curr < rhs
- [rsi_14, gt, 70]                   # Greater than
- [close, near_pct, support, 1.5]   # Within 1.5% of level
```

### Window Operators
```yaml
# Condition held for N bars
holds_for:
  bars: 3
  anchor_tf: "1h"
  expr: [rsi_14, gt, 50]

# Event occurred within window
occurred_within:
  bars: 10
  expr: [ema_9, cross_above, ema_21]
```

### Structure Access (O(1) Market Structure)
```yaml
- [{feature_id: swing, field: high_level}, gt, 0]
- [{feature_id: trend, field: direction}, eq, 1]
- [{feature_id: fib_zones, field: any_active}, eq, true]
```

---

## Trading Hierarchy

| Level | Purpose | Location |
|:-----:|---------|----------|
| **Block** | Atomic reusable condition | `strategies/blocks/` |
| **Play** | Complete strategy with risk model | `strategies/plays/` |
| **System** | Multiple plays with regime blending | `strategies/systems/` |

---

## Current Status

| Component | Status | Details |
|-----------|:------:|---------|
| Backtest Engine | ✅ | 62-field metrics, deterministic execution |
| Margin & Liquidation | ✅ | Isolated margin, mark-based liquidation |
| Funding Rates | ✅ | 8-hour funding simulation |
| Indicators | ✅ | 43 registered (EMA, RSI, MACD, Bollinger, etc.) |
| Structures | ✅ | 6 types (Swing, Trend, Fibonacci, Zone, Rolling, Derived) |
| DSL v3.0.0 | ✅ | 11 operators, 6 window operators, frozen spec |
| The Forge | ✅ | Validation, audits, 320+ stress tests |
| Demo Trading | ✅ | Bybit testnet integration |
| Live Trading | ✅ | Bybit mainnet with safety controls |

---

## Project Structure

```
TRADE/
├── src/
│   ├── backtest/           # Backtest engine
│   │   ├── sim/            # Simulated exchange (margin, liquidation)
│   │   ├── play/           # Play config, risk model
│   │   └── incremental/    # O(1) structure detection
│   ├── forge/              # Strategy validation
│   ├── core/               # Live trading engine
│   ├── exchanges/          # Bybit API client
│   └── data/               # DuckDB market data
├── strategies/
│   ├── blocks/             # Atomic conditions
│   ├── plays/              # Complete strategies
│   └── systems/            # Multi-play configs
├── tests/
│   ├── validation/         # DSL validation (V_100+)
│   └── stress/             # Structure stress tests (320+)
└── docs/
    ├── guides/             # Usage guides
    ├── specs/              # DSL specification
    └── architecture/       # Design documents
```

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

## Philosophy

### Gated Progression
No shortcuts to live trading. Prove your strategy works at each tier.

### All Forward, No Legacy
No backward compatibility. Delete old code, update all callers.

### Strategies Are Data
YAML-defined, version controlled, AI-generatable.

### Fail Loud
Invalid configurations raise errors immediately. No silent defaults.

---

## License

MIT License - See [LICENSE](LICENSE) file
