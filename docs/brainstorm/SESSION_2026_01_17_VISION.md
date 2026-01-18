# Brainstorm Session: 2026-01-17

## Session Focus
Full system vision and development roadmap for autonomous trading system.

## Key Decisions Made

### 1. Keep Current Codebase
- Foundation is solid (7/10)
- 60% complete, ~50 hours to finish vs 480 hours to rebuild
- Play/DSL system is production-grade
- Delete old BacktestEngine, complete PlayEngine adapters

### 2. System Architecture
```
KNOWLEDGE → AGENT → PLAYS → GE → DEMO → LIVE
```

Knowledge stores (trading methodologies) get translated by LLM agent into Play candidates, optimized by genetic evolution, validated in demo, deployed to live.

### 3. Block Layer Design
- Logic → Blocks → Plays (composition order)
- Typed blocks: filter, entry, exit, invalidation
- Blocks are reusable, Plays compose them

### 4. Crypto-Native Focus
- Removed forex session concepts (weak evidence in crypto)
- Prioritized: funding rates, OI, liquidations, on-chain data
- Kept: CME open, weekly open (real events)

### 5. Data Architecture
```
Redis (hot)      → Real-time state, positions, pub/sub
PostgreSQL (warm) → Trades, plays, evolution results
DuckDB (cold)    → Historical bars, backtest source
```

DuckDB limitation (single writer) solved by:
- Pre-load data to Ray shared memory for parallel backtests
- Results write to PostgreSQL

### 6. Tech Stack
- Backend: FastAPI + Redis + PostgreSQL + DuckDB
- Evolution: Ray + DEAP
- Frontend: React + TradingView Lightweight Charts
- CLI: Thin client to API

### 7. Development Phases
1. Foundation (finish engine) - 1-2 weeks
2. DSL validator + blocks - 2-3 weeks
3. Data layer - 2 weeks
4. Demo + Live trading - 3-4 weeks
5. CLI + Web dashboard - 4-6 weeks
6. Genetic evolution - 3-4 weeks
7. LLM + Market eye - 4-6 weeks

~6 months total

## Documents Created
- `SYSTEM_VISION.md` - Full pipeline vision
- `DEVELOPMENT_ROADMAP.md` - Phased development plan
- `TRADING_DSL_BLOCKS.md` - Block architecture
- `CODEBASE_EVALUATION.md` - Keep vs rebuild assessment
- `STRUCTURE_TRADING_SYSTEM.md` - Pivot history design (from earlier)

## Open Questions
1. Block versioning - how to evolve without breaking Plays?
2. LLM translation reliability - needs human review loop
3. Overfitting in GE - walk-forward validation critical
4. Market Eye data sources - which sentiment APIs?

## Next Steps
1. Finish Phase 1 (delete old engine, complete adapters)
2. Start Phase 2 (DSL validator)
3. Begin trading manually with system to validate

## User Context
- 4 years hand trading experience
- Learning to code while building
- Using Claude Code for development
- Goal: automate what works, scale with GE
