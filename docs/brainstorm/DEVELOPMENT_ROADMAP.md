# Development Roadmap

> **Status**: Active planning
> **Last Updated**: 2026-01-17
> **Approach**: Bicycle before spaceship - each phase delivers value

---

## Overview

```
Phase 1: Foundation     → Working backtest with clean DSL
Phase 2: Validation     → DSL validator + schema enforcement
Phase 3: Data Layer     → Multi-DB architecture (hot/warm/cold)
Phase 4: Live Trading   → Demo + Live execution
Phase 5: Interfaces     → CLI refinement + Web dashboard
Phase 6: Evolution      → GE parameter optimization
Phase 7: Intelligence   → LLM translation + Market eye
```

---

## Phase 1: Foundation (Current - Complete)

**Goal**: Working backtest engine with Play DSL

### Deliverables
- [x] Play YAML schema
- [x] Feature registry (indicators + structures)
- [x] 43 indicators
- [x] 7 structure types
- [x] Backtest engine execution
- [x] Risk model
- [x] CLI for running backtests

### Status: ~60% complete
- Engine works
- Need to delete old BacktestEngine
- Need to complete PlayEngine adapters

---

## Phase 2: DSL Validation & Expansion

**Goal**: Bulletproof DSL with clear schema and validation

### 2.1 Schema Definition
```yaml
# Formal JSON Schema for Play validation
# Every field documented, typed, constrained
play_schema:
  version: string (semver)
  name: string (unique identifier)
  features: map<string, FeatureDef>
  structures: map<tf_role, StructureDef[]>
  actions: map<action_name, ConditionTree>
  risk: RiskDef
```

### 2.2 Validator Implementation
```python
# src/dsl/validator.py
class PlayValidator:
    def validate(play_yaml: str) -> ValidationResult
    def check_schema(play: dict) -> list[SchemaError]
    def check_references(play: dict) -> list[RefError]
    def check_logic(play: dict) -> list[LogicError]
    def suggest_fixes(errors: list) -> list[Suggestion]
```

### 2.3 Block Layer (NEW)
```yaml
# Reusable blocks
blocks:
  trend_filter_v1:
    type: filter
    requires: [ema_20, ema_50]
    logic:
      all:
        - [ema_20, ">", ema_50]

# Plays reference blocks
plays:
  my_strategy:
    filters:
      - use: trend_filter_v1
```

### 2.4 DSL Expansion Points
- Sequence operators: `then`, `within`
- Aggregation: `count_true`, `score`
- State references: `entry_price`, `bars_in_trade`
- Crypto-native: `funding_rate`, `oi_delta`

### Deliverables
- [ ] JSON Schema for Play validation
- [ ] PlayValidator class with clear error messages
- [ ] Block definition schema
- [ ] Block registry and loader
- [ ] CLI command: `trade validate --play X`
- [ ] Documentation: DSL reference guide

---

## Phase 3: Data Layer Architecture

**Goal**: Right database for each use case

### 3.1 Database Roles
```
┌─────────────┬─────────────┬─────────────┐
│    Redis    │ PostgreSQL  │   DuckDB    │
│    (hot)    │   (warm)    │   (cold)    │
├─────────────┼─────────────┼─────────────┤
│ Live state  │ Trades      │ Historical  │
│ Positions   │ Play configs│ OHLCV bars  │
│ Signals     │ Audit log   │ Backtest    │
│ Pub/sub     │ Evolution   │ results     │
│ Cache       │ results     │ (read-only) │
└─────────────┴─────────────┴─────────────┘
```

### 3.2 Implementation
```python
# src/data/stores/
├── redis_store.py      # Hot data, real-time
├── postgres_store.py   # Warm data, operational
├── duckdb_store.py     # Cold data, analytics
└── store_factory.py    # Unified interface
```

### 3.3 Data Flow
```
Live feed → Redis (current state)
              ↓
         PostgreSQL (persist trades)
              ↓
         DuckDB (archive for analysis)
```

### Deliverables
- [ ] Redis integration (aioredis)
- [ ] PostgreSQL integration (asyncpg)
- [ ] Store abstraction layer
- [ ] Migration scripts
- [ ] Data flow documentation

---

## Phase 4: Live Trading

**Goal**: Demo and live execution with same engine

### 4.1 Adapter Completion
```python
# src/engine/adapters/
├── backtest.py    # Complete (wraps FeedStore)
├── demo.py        # NEW: Bybit testnet
└── live.py        # NEW: Bybit mainnet
```

### 4.2 Demo Mode
- Connect to Bybit testnet API
- WebSocket for live bars
- Paper trading execution
- Position tracking
- Same Play, different adapter

### 4.3 Live Mode
- Connect to Bybit mainnet API
- Real order execution
- Safety limits (max position, daily loss)
- Kill switch
- Audit logging

### 4.4 State Persistence
- Survive restarts
- Resume mid-trade
- Checkpoint structure state

### Deliverables
- [ ] LiveDataProvider (WebSocket feed)
- [ ] LiveExchange (order execution)
- [ ] DemoExchange (testnet wrapper)
- [ ] State persistence (FileStateStore → PostgreSQL)
- [ ] Safety controls (limits, kill switch)
- [ ] CLI commands: `trade demo start`, `trade live start`

---

## Phase 5: Interfaces

**Goal**: CLI for dev/ops, Web for visualization

### 5.1 CLI Refinement
```bash
# Validation
trade validate --play X
trade validate --block Y

# Backtesting
trade backtest run --play X --from 2024-01 --to 2024-06
trade backtest compare --plays X,Y,Z

# Live operations
trade demo start --play X
trade demo stop
trade live start --play X --risk-profile conservative
trade live status
trade live kill  # Emergency stop

# Evolution
trade evolve --base-play X --generations 50 --population 100
trade evolve status --job-id abc123
```

### 5.2 Web Dashboard
```
Pages:
├── /dashboard        # Overview, active positions, PnL
├── /plays            # Play library, validation status
├── /backtest         # Run backtests, view results
├── /charts           # TradingView charts + structure overlay
├── /evolution        # GE jobs, progress, results
└── /settings         # API keys, risk limits
```

### 5.3 Tech Stack
```
Backend:  FastAPI + WebSocket
Frontend: React + TradingView Lightweight Charts + Tailwind
Auth:     Simple token (single user initially)
```

### Deliverables
- [ ] FastAPI application structure
- [ ] REST endpoints for all operations
- [ ] WebSocket streams (bars, signals, positions)
- [ ] React app scaffold
- [ ] TradingView chart integration
- [ ] Structure overlay on charts
- [ ] Dashboard pages

---

## Phase 6: Genetic Evolution

**Goal**: Automated parameter optimization at scale

### 6.1 Evolution Engine
```python
# src/evolution/
├── population.py     # Generate Play variants
├── fitness.py        # Scoring function
├── selection.py      # Tournament/elite selection
├── crossover.py      # Combine winning traits
├── mutation.py       # Random param changes
└── runner.py         # Parallel execution via Ray
```

### 6.2 Param Ranges in DSL
```yaml
features:
  ema_fast:
    indicator: ema
    params:
      length: { min: 5, max: 20, step: 1 }  # GE searches this range
```

### 6.3 Fitness Function
```python
def fitness(result: BacktestResult) -> float:
    # Multi-objective optimization
    sharpe = result.sharpe_ratio
    max_dd = result.max_drawdown
    trade_count = result.trade_count

    # Penalize overfitting signals
    if trade_count < 30:
        return 0

    return sharpe * (1 - max_dd) * min(1, trade_count / 50)
```

### 6.4 Parallel Execution
```
DuckDB → Load to Ray object store
           ↓
    Workers run backtests (100+ parallel)
           ↓
    Results → PostgreSQL
           ↓
    Next generation
```

### Deliverables
- [ ] Ray integration
- [ ] Evolution engine classes
- [ ] Param range syntax in DSL
- [ ] Fitness function (configurable)
- [ ] Walk-forward validation
- [ ] CLI: `trade evolve`
- [ ] Web: evolution progress view

---

## Phase 7: Intelligence Layer

**Goal**: LLM-assisted strategy generation + market awareness

### 7.1 Knowledge Store
```
knowledge/
├── sources/           # Raw knowledge (markdown, notes)
├── primitives/        # Extracted concepts (structured YAML)
└── prompts/           # LLM prompts for translation
```

### 7.2 Translation Prompts
```python
# Prompt templates for Claude
KNOWLEDGE_TO_PLAY = """
Given this trading concept:
{knowledge}

Generate a Play YAML that implements this strategy.
Use only these available indicators: {available_indicators}
Use only these available structures: {available_structures}

Output valid YAML matching this schema:
{play_schema}
"""
```

### 7.3 Human-in-the-Loop
```
Knowledge → LLM generates candidate → Human reviews → GE optimizes
                                           ↑
                                    NOT fully autonomous
```

### 7.4 Market Eye
```python
# src/market/eye.py
class MarketEye:
    """Real-time market condition assessment"""

    def get_regime(symbol) -> Regime
    def get_sentiment(symbol) -> Sentiment
    def get_volatility_state(symbol) -> VolState
    def recommend_plays(conditions) -> list[Play]
```

### 7.5 Data Sources
```
Market Eye Inputs:
├── Price action (from engine)
├── Funding rates (Bybit API)
├── Open interest (Bybit API)
├── Liquidation data (API or derived)
├── Fear & Greed index (external API)
└── Social sentiment (future: Twitter/CT)
```

### Deliverables
- [ ] Knowledge store structure
- [ ] LLM prompt templates
- [ ] Play generation from knowledge (human-reviewed)
- [ ] MarketEye class
- [ ] Regime detection
- [ ] Sentiment data integration
- [ ] Play recommendation engine
- [ ] CLI: `trade generate --from knowledge/x.md`
- [ ] Web: knowledge management UI

---

## Milestone Summary

| Phase | Milestone | Validates |
|-------|-----------|-----------|
| 1 | Backtest runs with Play | Engine works |
| 2 | `trade validate` catches errors | DSL is solid |
| 3 | Data flows through all DBs | Architecture works |
| 4 | Demo trade executes | Live path works |
| 5 | See structure on chart | Visualization works |
| 6 | GE finds better params | Optimization works |
| 7 | LLM generates valid Play | Intelligence works |

---

## Time Estimates (Solo Dev, Focused)

| Phase | Effort | Cumulative |
|-------|--------|------------|
| 1 (finish) | 1-2 weeks | 2 weeks |
| 2 | 2-3 weeks | 5 weeks |
| 3 | 2 weeks | 7 weeks |
| 4 | 3-4 weeks | 11 weeks |
| 5 | 4-6 weeks | 17 weeks |
| 6 | 3-4 weeks | 21 weeks |
| 7 | 4-6 weeks | 27 weeks |

**Total: ~6 months to full system**

Note: These overlap. You can trade (Phase 4) while building UI (Phase 5).

---

## Definition of Done (Each Phase)

- [ ] Code complete
- [ ] CLI commands work
- [ ] Tests pass (smoke tests minimum)
- [ ] Documentation updated
- [ ] Brainstorm docs archived/updated
