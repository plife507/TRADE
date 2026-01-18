# System Vision: Knowledge to Production Pipeline

> **Status**: Active brainstorm
> **Last Updated**: 2026-01-17
> **Purpose**: Define the end-to-end autonomous trading system

---

## The Vision

A system that transforms trading knowledge into live, profitable strategies - autonomously.

```
KNOWLEDGE -> AGENT -> PLAYS -> GE -> DEMO -> LIVE
```

---

## Pipeline Stages

### 1. Knowledge Store

Drop in trading knowledge from any source:
- Academic papers (Simons, quant research)
- Trading methodologies (ICT, SMC, Wyckoff)
- Books and courses
- Personal trading journals
- Market observations

Format: markdown, PDF, structured notes

```
knowledge/
├── sources/
│   ├── simons_markov.md
│   ├── ict_market_structure.md
│   ├── mean_reversion_theory.md
│   └── personal_journal.md
│
├── primitives/              # Extracted concepts
│   ├── regime_detection.yml
│   ├── markov_transitions.yml
│   └── momentum_confirm.yml
│
└── templates/               # Play templates
    ├── regime_based.yml
    └── mean_revert.yml
```

### 2. Translation Agent

Reads knowledge, generates Play candidates.

**Input (knowledge):**
```markdown
# Simons Markov Approach

The market exists in discrete regimes:
- Trending up
- Trending down
- Mean reverting

Use hidden Markov model to detect regime transitions.
Enter on transition confirmation with momentum.
```

**Output (candidate Play with param ranges for GE):**
```yaml
name: regime_markov_candidate_001
description: "Generated from Simons Markov knowledge"

features:
  ema_fast: { indicator: ema, params: { length: [8, 12, 20] } }
  ema_slow: { indicator: ema, params: { length: [50, 100, 200] } }

structures:
  exec:
    - type: trend
      key: regime
      params:
        ema_length: [20, 50]

actions:
  entry_long:
    all:
      - [regime.state, "=", trending_up]
      - [regime.transition, "=", recent]
      - [ema_fast, ">", ema_slow]
```

### 3. Genetic Evolution

Optimize Play parameters at scale.

```
┌─────────────────────────────────────────────┐
│           EVOLUTION ARCHITECTURE            │
├─────────────────────────────────────────────┤
│                                             │
│  DuckDB ──► Load once ──► Ray Object Store  │
│  (source)                 (shared memory)   │
│                                │            │
│                    ┌───────────┼───────────┐│
│                    ▼           ▼           ▼│
│              ┌─────────┐ ┌─────────┐ ┌─────────┐
│              │Worker 1 │ │Worker 2 │ │Worker N │
│              │Backtest │ │Backtest │ │Backtest │
│              └────┬────┘ └────┬────┘ └────┬────┘
│                   └───────────┴───────────┘ │
│                               │             │
│                               ▼             │
│                         PostgreSQL          │
│                      (results, fitness)     │
└─────────────────────────────────────────────┘
```

**Evolution cycle:**
1. Generate population (100 Play variants)
2. Load data (1 market cycle)
3. Run parallel backtests (Ray)
4. Score and rank (fitness function)
5. Select survivors (top 20%)
6. Breed next generation (crossover + mutation)
7. Repeat until convergence
8. Output winners to validation

### 4. Demo Validation

Real-time paper trading to validate:
- Backtest results hold in live conditions
- No overfitting to historical data
- Execution matches expectations

**Pass criteria:**
- 7+ days minimum
- 10+ trades
- Performance within expected range
- No critical errors

### 5. Vetted Play Library

Plays that passed all gates, tagged by:
- Market regime (trending, ranging)
- Asset (BTC, ETH, SOL)
- Timeframe (scalp, swing)
- Risk profile (aggressive, conservative)

```
vetted_plays/
├── trending/
│   ├── btc_momentum_v12.yml    # Sharpe 1.8
│   └── eth_breakout_v7.yml     # Sharpe 1.5
├── ranging/
│   ├── sol_mean_revert_v3.yml  # Sharpe 2.1
│   └── btc_grid_v5.yml         # Sharpe 1.3
└── regime_adaptive/
    └── markov_multi_v2.yml     # Sharpe 1.9
```

### 6. Live Trading Agent

Monitors market conditions, selects appropriate vetted Play.

```
Market State:
  regime: trending
  volatility: low
  funding: neutral

Selected Play: btc_momentum_v12
Reason: trending regime, validated for BTC, matches conditions
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Knowledge Store | Markdown + YAML + Vector DB (embeddings) |
| Translation Agent | LLM + DSL schema validation |
| Evolution Engine | Ray (parallel) + DEAP (genetic algo) |
| Data Layer | DuckDB (cold) + Redis (hot) + PostgreSQL (warm) |
| API | FastAPI + WebSocket |
| Demo/Live | Bybit API (testnet/mainnet) |
| Visualization | TradingView Lightweight Charts |

---

## Data Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      HOT (Real-time)                    │
│                         Redis                           │
│  Current positions, live signals, structure state       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                     WARM (Operational)                  │
│                      PostgreSQL                         │
│  Plays, trades, evolution results, audit trail          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                     COLD (Analytics)                    │
│                        DuckDB                           │
│  Historical bars, backtest source data                  │
└─────────────────────────────────────────────────────────┘
```

---

## The Moat

Most traders: backtest one idea manually, optimize a few params.

This system:
1. Ingest any trading knowledge
2. Auto-generate testable hypotheses
3. Optimize at scale (1000s of backtests)
4. Validate rigorously (out-of-sample, demo)
5. Deploy automatically
6. Adapt to changing conditions

**Knowledge to Production in days, not months.**

---

## Conversation Log

### 2026-01-17: Initial Vision
- User described full pipeline: knowledge to agent to plays to GE to demo to live
- Key insight: knowledge stores are "drop-in" - any methodology
- Agent translates concepts to Play candidates
- GE optimizes params at scale
- Vetted plays available for live agent selection
