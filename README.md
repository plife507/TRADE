# TRADE

**Algorithmic Trading Bot for Bybit Futures with AI-Agent Composable Strategies**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Bybit API](https://img.shields.io/badge/Exchange-Bybit-orange.svg)](https://www.bybit.com/)
[![Status](https://img.shields.io/badge/Status-Engine%20Development-yellow.svg)]()

A production-grade backtesting and live trading platform for **USDT-margined perpetual futures**. Strategies are defined as composable YAML configurations with built-in leverage controls, liquidation modeling, and comprehensive risk metrics.

---

## Current Status: Engine Development

> **Important:** TRADE is currently in **engine development phase**. The backtest engine is production-ready, but live trading with YAML-based Plays is not yet implemented.

### What Works Today

| Component | Status | Description |
|-----------|:------:|-------------|
| Backtest Engine | ✅ Complete | Full simulation with 62-field metrics |
| Margin & Liquidation | ✅ Complete | Isolated margin, mark-based liquidation |
| Funding Rates | ✅ Complete | 8-hour funding simulation |
| 43 Indicators | ✅ Complete | EMA, RSI, MACD, Bollinger, ATR, etc. |
| 6 Structures | ✅ Complete | Swing, Trend, Fibonacci, Zone, Rolling, Derived |
| Actions DSL v3.0 | ✅ Frozen | 11 operators, 6 window operators |
| The Forge | ✅ Complete | Validation, audits, 320+ stress tests |
| Play YAML Schema | ✅ Frozen | Strategy-as-data format |

### Current Limitations

| Feature | Status | Notes |
|---------|:------:|-------|
| Live Trading via YAML | ❌ Not Started | Plays cannot execute on Bybit yet |
| Demo Trading via YAML | ❌ Not Started | Testnet integration pending |
| Shadow Mode | ❌ Not Started | Signal logging without execution |
| Real-time Data Feed | ⏳ Partial | WebSocket stubs exist, not integrated |
| Position Management | ⏳ Partial | REST API tools exist, not Play-driven |

### What You Can Do Now

```bash
# Create and validate strategies
python trade_cli.py backtest play-normalize --play T_001_ema_crossover

# Run historical backtests with full margin simulation
python trade_cli.py backtest run --play T_001 --start 2025-01-01 --end 2025-06-30

# Analyze with 62-field metrics (Sharpe, VaR, MAE/MFE, etc.)
python trade_cli.py backtest audit-toolkit --play T_001

# Stress test your strategies
python trade_cli.py backtest play-normalize-batch --dir strategies/plays/
```

---

## Development Roadmap

### Gated Progress: Past → Current → Future

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEVELOPMENT ROADMAP                               │
│                                                                             │
│  Target: Live Trading in 2 months (Mar 2026)                                │
│  Target: Agent Integration in 3 months (Apr 2026)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ════════════════════════ COMPLETED ════════════════════════               │
│                                                                             │
│  GATE 1: DATA LAYER          GATE 2: INDICATORS         GATE 3: STRUCTURES │
│  ✅ Jan 2025                 ✅ Jan 2025                ✅ Jan 2026         │
│  ──────────────              ──────────────             ─────────────────   │
│  DuckDB storage              43 indicators              6 structure types   │
│  OHLCV sync                  pandas-ta parity           O(1) incremental    │
│  Funding rates               Multi-timeframe            Swing/Trend/Fib     │
│  Gap healing                 Forward-fill               Derived zones       │
│                                                                             │
│  GATE 4: SIM EXCHANGE        GATE 5: DSL v3.0           GATE 6: METRICS    │
│  ✅ Jan 2026                 ✅ Jan 2026                ✅ Jan 2026         │
│  ──────────────              ──────────────             ─────────────────   │
│  Isolated margin             11 operators               62 fields           │
│  Liquidation model           Window operators           Tail risk (VaR)     │
│  Funding simulation          TradingView parity         MAE/MFE analysis    │
│  Slippage/fees               Crossover semantics        Leverage metrics    │
│                                                                             │
│  ════════════════════════ CURRENT ══════════════════════════               │
│                                                                             │
│  GATE 7: THE FORGE                                                          │
│  🔄 In Progress (Jan 2026)                                                  │
│  ─────────────────────────                                                  │
│  Play validation framework                                                  │
│  Stress testing (320+ plays)                                                │
│  Audit suite                                                                │
│  Quality gates                                                              │
│                                                                             │
│  ════════════════════ 2 MONTHS: LIVE TRADING ═══════════════               │
│                                                                             │
│  GATE 8: LIVE ENGINE         GATE 9: DEMO MODE          GATE 10: PRODUCTION│
│  ⏳ Feb 2026                 ⏳ Feb 2026                ⏳ Mar 2026         │
│  ──────────────              ──────────────             ─────────────────   │
│  WebSocket feeds             Bybit testnet              Live execution      │
│  Play → Order bridge         Paper trading              Risk controls       │
│  Position sync               Signal logging             Circuit breakers    │
│  Real-time signals           7-day validation           Position limits     │
│                                                                             │
│  ════════════════════ 3 MONTHS: AGENT INTEGRATION ══════════               │
│                                                                             │
│  GATE 11: SHADOW MODE        GATE 12: AGENT API         GATE 13: SYSTEMS   │
│  ⏳ Mar 2026                 ⏳ Apr 2026                ⏳ Apr 2026         │
│  ──────────────              ──────────────             ─────────────────   │
│  Signal-only mode            AI agent interface         Multi-play configs  │
│  Backtest parity             Strategy generation        Regime blending     │
│  Fill comparison             Auto-validation            Portfolio allocation│
│  Slippage analysis           Prompt → Play pipeline     Risk aggregation    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Gate Details

| Gate | Status | Target | Milestone | Key Deliverables |
|:----:|:------:|:------:|-----------|------------------|
| 1 | ✅ Done | — | Data Layer | DuckDB, OHLCV sync, funding rates |
| 2 | ✅ Done | — | Indicators | 43 indicators, multi-TF, pandas-ta parity |
| 3 | ✅ Done | — | Structures | 6 types, O(1) incremental, derived zones |
| 4 | ✅ Done | — | Sim Exchange | Margin, liquidation, funding, fees |
| 5 | ✅ Done | — | DSL v3.0 | Operators, windows, crossovers (FROZEN) |
| 6 | ✅ Done | — | Metrics | 62 fields, tail risk, leverage metrics |
| 7 | 🔄 Now | Jan | The Forge | Validation, stress tests, quality gates |
| 8 | ⏳ Next | Feb | Live Engine | WebSocket, Play→Order bridge |
| 9 | ⏳ | Feb | Demo Mode | Testnet trading, paper mode |
| 10 | ⏳ | **Mar** | **Production** | **Live execution, circuit breakers** |
| 11 | ⏳ | Mar | Shadow Mode | Signal logging, parity checks |
| 12 | ⏳ | **Apr** | **Agent API** | **AI interface, Prompt→Play pipeline** |
| 13 | ⏳ | Apr | Systems | Multi-play, regime blending |

---

## Future: 6-Tier Trading Pipeline

Once the live engine is complete (Gates 8-10, target: **March 2026**), strategies will follow this gated progression:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FUTURE: TRADING PIPELINE                               │
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
│  (Gate 9 - Feb)             (Gate 11 - Mar)            (Gate 10 - Mar)     │
│  ───────────                ──────────────             ───────────         │
│  Paper trade on      ──►    Live signals,      ──►    Real capital         │
│  Bybit testnet              no execution              Full automation      │
│  Fake funds                 Compare to sim            Risk controls        │
│  Real market data           Validate fills            Position limits      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tiers Available Today

| Tier | Status | What You Can Do | Target |
|:----:|:------:|-----------------|:------:|
| **1** | ✅ Ready | Create and normalize Play YAML | — |
| **2** | ✅ Ready | Run full backtests with margin simulation | — |
| **3** | ✅ Ready | Validate against quality metrics | — |
| **4** | ⏳ Pending | Demo trading (Gate 9) | Feb 2026 |
| **5** | ⏳ Pending | Shadow mode (Gate 11) | Mar 2026 |
| **6** | ⏳ Pending | Live trading (Gate 10) | **Mar 2026** |

---

## Why TRADE?

| Problem | TRADE Solution |
|---------|----------------|
| Strategies are scattered code | **Strategies are YAML data** - version controlled, diffable |
| Backtests ignore leverage reality | **Full margin simulation** - liquidation, maintenance margin |
| Risk metrics are an afterthought | **62-field metrics** - VaR, CVaR, Sharpe, tail risk |
| No clear path to production | **Gated progression** - earn your way to live (when ready) |
| Hard to compose strategies | **3-level hierarchy** - Blocks → Plays → Systems |

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
│                      BACKTEST ENGINE ✅                         │
│                                                                 │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│   │ Indicators │  │ Structures │  │ Actions DSL│               │
│   │  (43) ✅   │  │   (6) ✅   │  │ (v3.0) ✅  │               │
│   └────────────┘  └────────────┘  └────────────┘               │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              Simulated Exchange ✅                      │  │
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
│                       LIVE ENGINE ⏳                            │
│                   Bybit Futures (USDT-M)                        │
│                                                                 │
│   ┌──────────────────────────────────────────────────────────┐ │
│   │                    NOT YET IMPLEMENTED                   │ │
│   │          Demo (Gate 9) · Live (Gate 10)                  │ │
│   └──────────────────────────────────────────────────────────┘ │
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

### Stop Loss & Take Profit Types

**Percentage values are ROI-based** (percentage of margin), not price-based.
With 10x leverage and 2% SL, you lose 2% of margin when price moves 0.2% against you.

```
Formula: price_distance = entry × (roi_pct / 100) / leverage
```

| Leverage | 2% SL (ROI) | Price Move | 4% TP (ROI) | Price Move |
|----------|-------------|------------|-------------|------------|
| 1x | 2% loss | 2.0% | 4% gain | 4.0% |
| 5x | 2% loss | 0.4% | 4% gain | 0.8% |
| 10x | 2% loss | 0.2% | 4% gain | 0.4% |
| 20x | 2% loss | 0.1% | 4% gain | 0.2% |

#### Stop Loss Types

| Type | Description |
|------|-------------|
| `percent` | ROI-based percentage (2% = 2% margin loss) |
| `atr_multiple` | Dynamic: `entry ± (ATR × multiplier)` |
| `structure` | Based on swing high/low levels |
| `fixed_points` | Absolute price distance |

#### Take Profit Types

| Type | Description |
|------|-------------|
| `rr_ratio` | Target = `entry + (stop_distance × ratio)` |
| `percent` | ROI-based percentage (4% = 4% margin gain) |
| `atr_multiple` | Dynamic: `entry ± (ATR × multiplier)` |
| `fixed_points` | Absolute price distance |

### Exit Modes

| Mode | Behavior |
|------|----------|
| `sl_tp_only` | Only SL/TP close positions - pure mechanical |
| `signal` | Only signal-based exits - SL/TP are emergency only |
| `first_hit` | Whichever triggers first wins |

---

## Backtest Metrics (62 Fields)

Complete performance analytics computed for every backtest run.

### Equity Metrics (6)

| Metric | Description |
|--------|-------------|
| `initial_equity` | Starting account balance |
| `final_equity` | Ending account balance |
| `net_profit` | Final - initial equity |
| `net_return_pct` | Total percentage return |
| `benchmark_return_pct` | Buy-and-hold return (same period) |
| `alpha_pct` | Strategy return - benchmark return |

### Drawdown Metrics (4)

| Metric | Description |
|--------|-------------|
| `max_drawdown_abs` | Peak-to-trough drawdown in USDT |
| `max_drawdown_pct` | Peak-to-trough drawdown as % |
| `max_drawdown_duration_bars` | Longest time spent in drawdown |
| `ulcer_index` | Pain-adjusted drawdown (penalizes depth + duration) |

### Risk-Adjusted Returns (5)

| Metric | Description |
|--------|-------------|
| `sharpe` | Annualized Sharpe ratio |
| `sortino` | Sharpe with downside-only volatility |
| `calmar` | CAGR / Max Drawdown |
| `omega_ratio` | Probability-weighted gain/loss ratio |
| `recovery_factor` | Net profit / max drawdown |

### Tail Risk (Critical for Leverage) (4)

| Metric | Description |
|--------|-------------|
| `var_95_pct` | 95% Value at Risk - worst 5% loss |
| `cvar_95_pct` | Expected Shortfall - avg loss beyond VaR |
| `skewness` | Return asymmetry (negative = blowup risk) |
| `kurtosis` | Fat tails measure (>3 = extreme moves) |

### Trade Summary (12)

| Metric | Description |
|--------|-------------|
| `total_trades` | Number of completed trades |
| `win_count` / `loss_count` | Win/loss breakdown |
| `win_rate` | Win percentage |
| `avg_trade_return_pct` | Average trade ROI |
| `profit_factor` | Gross profit / gross loss |
| `avg_win_usdt` / `avg_loss_usdt` | Average win/loss size |
| `largest_win_usdt` / `largest_loss_usdt` | Best/worst trades |
| `max_consecutive_wins` / `max_consecutive_losses` | Streaks |
| `expectancy_usdt` | Expected $ per trade |
| `payoff_ratio` | Average win / average loss |

### Trade Duration (5)

| Metric | Description |
|--------|-------------|
| `avg_trade_duration_bars` | Average trade length (all trades) |
| `avg_winning_trade_duration_bars` | Average duration of winners |
| `avg_losing_trade_duration_bars` | Average duration of losers |
| `bars_in_position` | Total bars with open position |
| `time_in_market_pct` | Percentage of time in market |

### Long/Short Breakdown (6)

| Metric | Description |
|--------|-------------|
| `long_trades` / `short_trades` | Trade count by direction |
| `long_win_rate` / `short_win_rate` | Win rates by direction |
| `long_pnl` / `short_pnl` | PnL by direction |

### Leverage Metrics (6)

| Metric | Description |
|--------|-------------|
| `avg_leverage_used` | Average actual leverage during backtest |
| `max_gross_exposure_pct` | Peak position_value / equity |
| `closest_liquidation_pct` | How close to liquidation (100 = never) |
| `margin_calls` | Number of margin warning events |
| `entry_attempts` / `entry_rejections` | Entry signal attempts vs rejections |
| `entry_rejection_rate` | Rejection percentage |

### Trade Quality - MAE/MFE (3)

| Metric | Description |
|--------|-------------|
| `mae_avg_pct` | Avg Maximum Adverse Excursion (worst intratrade drawdown) |
| `mfe_avg_pct` | Avg Maximum Favorable Excursion (best intratrade profit) |
| `min_margin_ratio` | Lowest margin ratio during backtest |

### Funding Metrics (3)

| Metric | Description |
|--------|-------------|
| `total_funding_paid_usdt` | Funding paid (longs in positive funding) |
| `total_funding_received_usdt` | Funding received (shorts in positive funding) |
| `net_funding_usdt` | Net funding impact on PnL |

### Fees & Costs (3)

| Metric | Description |
|--------|-------------|
| `total_fees` | Total trading fees |
| `gross_profit` | Total profit before fees |
| `gross_loss` | Total losses before fees |

---

## Example Play

```yaml
# strategies/plays/T_001_ema_crossover.yml
version: "3.0.0"
id: T_001_ema_crossover

symbol: BTCUSDT
tf: "15m"

account:
  starting_equity_usdt: 10000
  max_leverage: 10
  margin_mode: isolated_usdt
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0

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

actions:
  entry_long:
    all:
      - [ema_9, cross_above, ema_21]
  exit_long:
    all:
      - [ema_9, cross_below, ema_21]

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

### What You Can Do Today

```bash
# Tier 1: Validate YAML ✅
python trade_cli.py backtest play-normalize --play T_001_ema_crossover

# Tier 2: Run backtest ✅
python trade_cli.py backtest run --play T_001_ema_crossover \
  --start 2025-01-01 --end 2025-06-30

# Tier 3: Quality gate ✅
python trade_cli.py backtest audit-toolkit --play T_001_ema_crossover

# Tier 4-6: Not yet available ❌
# python trade_cli.py live run --play T_001 --mode demo  # Future
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

# Run backtest (what works today)
python trade_cli.py backtest play-normalize --play T_001_ema_crossover
python trade_cli.py backtest run --play T_001 --start 2025-01-01 --end 2025-06-30
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
holds_for:
  bars: 3
  anchor_tf: "1h"
  expr: [rsi_14, gt, 50]

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

## Project Structure

```
TRADE/
├── src/
│   ├── backtest/           # Backtest engine ✅
│   │   ├── sim/            # Simulated exchange
│   │   ├── play/           # Play config, risk model
│   │   └── incremental/    # O(1) structure detection
│   ├── forge/              # Strategy validation ✅
│   ├── core/               # Live trading engine ⏳
│   ├── exchanges/          # Bybit API client
│   └── data/               # DuckDB market data ✅
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

### Engine First
Build a rock-solid backtest engine before touching live trading.

### Gated Progression
No shortcuts. Each gate must pass before advancing.

### Strategies Are Data
YAML-defined, version controlled, AI-generatable.

### Fail Loud
Invalid configurations raise errors immediately. No silent defaults.

---

## License

MIT License - See [LICENSE](LICENSE) file
