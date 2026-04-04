---
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
description: Create plays from natural language via conversational interview
argument-hint: [optional seed prompt]
---

# Forge Play Command

Create a new Play YAML from natural language through a conversational interview, validate it, and organize it by strategy concept.

## Usage

```
/forge-play [optional natural language description]
```

## Process

Delegate to the `forge-play` agent which will:

1. **Interview** — Ask adaptive questions to gather: symbol, direction, timeframes, indicators, structures, entry/exit conditions, risk parameters. Skip questions already answered in the seed prompt.

2. **Generate** — Write valid Play YAML using the modular DSL playbook (`docs/dsl/`). Save to `plays/{concept}/` folder.

3. **Validate** — Run synthetic smoke backtest:
   ```bash
   python trade_cli.py backtest run --play <name> --synthetic
   ```

4. **Fix loop (human-in-the-loop)** — If validation fails: show error, propose fix as diff, ask approval. Repeat until passes or user aborts.

5. **Post-create** — Ask what next (real-data backtest, variants, tweak, done).

## Strategy Concepts → Folders

| Folder | Strategy type |
|--------|--------------|
| `plays/mean_reversion/` | Oscillator extremes, revert to mean |
| `plays/trend_following/` | Ride momentum, trail stops |
| `plays/breakout/` | Range expansion, volume confirmation |
| `plays/scalping/` | Fast timeframe, tight risk |
| `plays/range_trading/` | Fade extremes within bounds |
| `plays/ict/` | ICT structures — BOS, FVG, OB, sweeps |

## DSL Playbook

Modular reference in `docs/dsl/`:

| Module | Content |
|--------|---------|
| `skeleton.md` | Play structure, timeframes, account |
| `indicators.md` | 47 indicators with params |
| `structures.md` | 13 structure types — swing, trend, MS, fib, zone, FVG, OB, liq, PD, breaker |
| `conditions.md` | Operators, logic, setups, windows |
| `risk.md` | SL/TP, trailing, sizing, entries |
| `patterns.md` | 38 synthetic patterns |
| `pitfalls.md` | Critical mistakes |
| `recipes.md` | 7 complete example plays |

## See Also

- `/backtest-smoke` — Quick smoke test for existing plays
- `/validate quick` — Full validation suite
