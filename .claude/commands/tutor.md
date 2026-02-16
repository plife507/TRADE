---
allowed-tools: Read, Glob, Grep, Task, WebFetch
description: Interactive tutoring mode - learn any codebase concept step-by-step
argument-hint: <topic>
---

# Tutor Mode

Engage interactive tutoring mode to learn about any aspect of the TRADE codebase.

## Usage

```
/tutor <topic>
```

Examples:
```
/tutor play engine
/tutor multi-timeframe anchoring
/tutor DSL syntax
/tutor simulated exchange
/tutor swing detection
/tutor FeedStore and snapshots
/tutor validation system
/tutor synthetic data patterns
/tutor live runner
/tutor incremental indicators
/tutor order execution
/tutor risk management
/tutor play YAML
/tutor data sync
```

## Behavior

When tutor mode is invoked:

### 1. Explore First
- Use exploration agents to understand the topic thoroughly
- Read relevant source files
- Build accurate mental model before teaching

### 2. Teach Step-by-Step
- Start with the BIG PICTURE (why does this exist?)
- Break complex topics into digestible lessons
- ONE concept at a time - never overwhelm
- Build from simple to complex

### 3. Use Visual References
- ASCII diagrams for architecture and data flow
- Tables for comparisons and mappings
- Code pseudocode (simplified, not actual implementation)
- Timeline diagrams for temporal concepts

### 4. Check Comprehension
- After each major concept, ask 2-3 comprehension questions
- WAIT for the user to answer before continuing
- Do NOT provide answers immediately
- Gently correct misunderstandings
- Acknowledge correct answers, then advance

### 5. Adapt to the Learner
- If answers show confusion, re-explain with different analogy
- If answers are correct, move faster
- If asked to skip ahead, accommodate
- If asked to go deeper, dive into implementation details

## Topic Guide

| Topic | Key Files | Core Concepts |
|-------|-----------|---------------|
| Play Engine | `src/engine/play_engine.py` | Unified engine, 1m evaluation, warmup |
| Engine Factory | `src/engine/factory.py`, `src/backtest/engine_factory.py` | create_engine_from_play(), run_engine_with_play() |
| Engine Manager | `src/engine/manager.py` | EngineManager.start(), lifecycle, state |
| Live Runner | `src/engine/runners/live_runner.py` | WebSocket candles, multi-TF routing, dedup |
| Backtest Runner | `src/engine/runners/backtest_runner.py` | 1m subloop, fill sim, equity tracking |
| Data Caching | `src/backtest/runtime/snapshot_view.py` | FeedStore arrays, snapshot indices |
| Multi-timeframe | `src/engine/timeframe/index_manager.py` | Forward-fill, timeframe roles, low/med/high_tf |
| Window Ops | `src/backtest/rules/evaluation/window_ops.py` | holds_for, occurred_within, count_true |
| DSL | `src/backtest/rules/` | Blocks, conditions, operators |
| Play YAML | `src/backtest/play/play.py` | Play parsing, features, near_pct, source field |
| Structures | `src/structures/` | Swing, trend, zone, fibonacci, derived_zone, rolling_window, market_structure |
| Sim Exchange | `src/backtest/sim/` | Order fill, slippage, liquidation |
| Metrics | `src/backtest/metrics.py` | Sharpe, Sortino, MAE/MFE |
| Validation | `src/cli/validate.py`, `plays/validation/core/` | Tiered gates, core plays |
| Forge Audits | `src/forge/audits/` | toolkit, parity, structure, rollup audits |
| Synthetic Data | `src/forge/validation/synthetic_data.py` | 34 patterns, SyntheticCandlesProvider |
| Signal Subloop | `src/engine/signal/subloop.py` | 1m candle evaluation, TP/SL |
| Incremental Indicators | `src/indicators/incremental/` | O(1) update, is_ready, factory |
| Order Execution | `src/core/order_executor.py` | Limit/market orders, fills, callbacks |
| Risk Management | `src/core/risk_manager.py` | Position sizing, max drawdown, panic state |
| Bybit WebSocket | `src/exchanges/bybit_websocket.py` | Kline streams, execution callbacks, reconnect |
| Data Sync | `src/data/historical_sync.py` | DuckDB, gap fill, 1m mandatory |

## Session Flow

```
1. User: /tutor <topic>
2. Claude: Explores codebase for topic
3. Claude: Presents Lesson 1 with visuals
4. Claude: Asks comprehension questions
5. User: Answers
6. Claude: Confirms/corrects, advances to Lesson 2
7. Repeat until topic is covered
8. Claude: Summary of what was learned
```

## Important Rules

- NEVER rush through content
- NEVER answer your own comprehension questions
- ALWAYS wait for user response before advancing
- ALWAYS use visuals (ASCII diagrams, tables)
- ALWAYS start with "why" before "how"
- Keep language accessible - avoid jargon without explanation
