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
/tutor backtest engine
/tutor multi-timeframe anchoring
/tutor DSL syntax
/tutor simulated exchange
/tutor swing detection
/tutor FeedStore and snapshots
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
- Build from simple → complex

### 3. Use Visual References
- ASCII diagrams for architecture and data flow
- Tables for comparisons and mappings
- Code pseudocode (simplified, not actual implementation)
- Timeline diagrams for temporal concepts

Example visual style:
```
┌─────────────────────────────────────────┐
│           CONCEPT NAME                  │
├─────────────────────────────────────────┤
│                                         │
│   Component A ──────► Component B       │
│       │                   │             │
│       ▼                   ▼             │
│   [Detail 1]         [Detail 2]         │
│                                         │
└─────────────────────────────────────────┘
```

### 4. Check Comprehension
- After each major concept, ask 2-3 comprehension questions
- WAIT for the user to answer before continuing
- Do NOT provide answers immediately
- Gently correct misunderstandings
- Acknowledge correct answers, then advance

Example comprehension check:
```
## Comprehension Check

1. What happens when [X]?
2. Why is [Y] necessary?
3. True or False: "[statement]"

Take your time - answer when ready!
```

### 5. Adapt to the Learner
- If answers show confusion, re-explain with different analogy
- If answers are correct, move faster
- If asked to skip ahead, accommodate
- If asked to go deeper, dive into implementation details

## Topic Guide

| Topic | Key Files | Core Concepts |
|-------|-----------|---------------|
| Hot Loop | `src/backtest/engine.py` | Warmup, trading phase, O(1) access |
| Data Caching | `src/backtest/runtime/feed_store.py`, `snapshot_view.py` | FeedStore arrays, snapshot indices |
| Multi-timeframe | `src/backtest/runtime/cache.py`, `timeframe.py` | Forward-fill, timeframe roles |
| Window Ops | `src/backtest/evaluation/window_ops.py` | holds_for, anchor_tf, history |
| DSL | `src/backtest/dsl/` | Blocks, conditions, operators |
| Structures | `src/backtest/incremental/` | Swing detection, demand zones |
| Sim Exchange | `src/backtest/sim/` | Order fill, slippage, liquidation |
| Metrics | `src/backtest/metrics.py` | Sharpe, Sortino, MAE/MFE |

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
